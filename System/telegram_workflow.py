"""Shared runtime helpers for the Instagram.AI Telegram bot.

The Telegram adapter deliberately exposes only a small set of operations. This
module owns the two execution paths used by those operations:

* OpenCode commands run through a localhost headless server.
* Deterministic status/cleanup commands run through ``uv run``.

No user-provided value is ever interpolated into a shell command.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv


WORKSPACE = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE / ".env")

ANALYSES_DIR = WORKSPACE / "Brain" / "Analyses"
SCRIPTS_DIR = WORKSPACE / "Brain" / "Scripts"
DRAFT_RESULT_DIR = WORKSPACE / "draft_result"
SPREADSHEET_PATH = WORKSPACE / "Brain" / "Reels_Log.xlsx"

LOGGER = logging.getLogger(__name__)


class WorkflowError(RuntimeError):
    """A safe, user-facing workflow error."""


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise WorkflowError(f"{name} must be an integer") from exc


def _positive_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise WorkflowError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise WorkflowError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class BotSettings:
    token: str
    allowed_chat_id: int | None
    allowed_user_id: int | None
    opencode_bin: str
    opencode_host: str
    opencode_port: int
    opencode_username: str
    opencode_password: str
    command_timeout_seconds: int
    heartbeat_seconds: int

    @classmethod
    def from_env(cls) -> "BotSettings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise WorkflowError("TELEGRAM_BOT_TOKEN is not set in .env")

        allowed_chat_id = _optional_int("TELEGRAM_ALLOWED_CHAT_ID")
        allowed_user_id = _optional_int("TELEGRAM_ALLOWED_USER_ID")
        if allowed_chat_id is None and allowed_user_id is None:
            raise WorkflowError(
                "Set TELEGRAM_ALLOWED_CHAT_ID or TELEGRAM_ALLOWED_USER_ID in .env"
            )

        return cls(
            token=token,
            allowed_chat_id=allowed_chat_id,
            allowed_user_id=allowed_user_id,
            opencode_bin=os.getenv("OPENCODE_BIN", "opencode").strip() or "opencode",
            opencode_host=os.getenv("OPENCODE_HOST", "127.0.0.1").strip()
            or "127.0.0.1",
            opencode_port=_positive_int("OPENCODE_PORT", 4096),
            opencode_username=os.getenv("OPENCODE_SERVER_USERNAME", "opencode").strip()
            or "opencode",
            opencode_password=os.getenv("OPENCODE_SERVER_PASSWORD", "").strip(),
            command_timeout_seconds=_positive_int(
                "TELEGRAM_COMMAND_TIMEOUT_SECONDS", 60 * 60
            ),
            heartbeat_seconds=_positive_int("TELEGRAM_HEARTBEAT_SECONDS", 30),
        )

    def is_authorized(self, chat_id: int, user_id: int | None) -> bool:
        if self.allowed_chat_id is not None and chat_id != self.allowed_chat_id:
            return False
        if self.allowed_user_id is not None and user_id != self.allowed_user_id:
            return False
        return True


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output: str


@dataclass(frozen=True)
class GeneratedFile:
    path: Path
    size: int
    modified_ns: int


class OpenCodeBridge:
    """Start and call a project-local OpenCode server over localhost."""

    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._server_process: subprocess.Popen[bytes] | None = None
        self._owns_server = False
        self._sessions: dict[int, str] = {}

    @property
    def base_url(self) -> str:
        return f"http://{self.settings.opencode_host}:{self.settings.opencode_port}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            auth = None
            if self.settings.opencode_password:
                auth = httpx.BasicAuth(
                    self.settings.opencode_username,
                    self.settings.opencode_password,
                )
            timeout = httpx.Timeout(
                connect=10.0,
                read=None,
                write=30.0,
                pool=10.0,
            )
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=auth,
                timeout=timeout,
            )
        return self._client

    async def _health_status(self) -> int | None:
        client = await self._get_client()
        try:
            response = await client.get("/global/health")
        except httpx.HTTPError:
            return None
        if response.status_code in (401, 403):
            raise WorkflowError(
                "The OpenCode server requires authentication. Set "
                "OPENCODE_SERVER_PASSWORD to the same value used by OpenCode."
            )
        return response.status_code

    def _resolve_executable(self) -> str:
        configured = self.settings.opencode_bin
        if Path(configured).exists():
            return configured
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        if configured == "opencode":
            for candidate in ("opencode.cmd", "opencode.exe"):
                resolved = shutil.which(candidate)
                if resolved:
                    return resolved
        raise WorkflowError(
            "OpenCode CLI was not found. Install it and verify `opencode --version`, "
            "or set OPENCODE_BIN in .env."
        )

    async def ensure_server(self) -> None:
        status = await self._health_status()
        if status is not None and 200 <= status < 300:
            return

        executable = self._resolve_executable()
        command = [
            executable,
            "serve",
            "--hostname",
            self.settings.opencode_host,
            "--port",
            str(self.settings.opencode_port),
        ]
        LOGGER.info("Starting OpenCode server on %s", self.base_url)
        try:
            self._server_process = subprocess.Popen(
                command,
                cwd=str(WORKSPACE),
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise WorkflowError(f"Could not start OpenCode server: {exc}") from exc
        self._owns_server = True

        for _ in range(50):
            if self._server_process.poll() is not None:
                break
            await asyncio.sleep(0.2)
            status = await self._health_status()
            if status is not None and 200 <= status < 300:
                return

        await self.close()
        raise WorkflowError(
            "OpenCode server did not become ready. Run `opencode serve` manually "
            "from the project root to inspect its startup error."
        )

    async def _create_session(self, chat_id: int) -> str:
        client = await self._get_client()
        response = await client.post(
            "/session",
            json={"title": f"Instagram.AI Telegram {chat_id}"},
        )
        if response.is_error:
            raise WorkflowError(
                f"OpenCode could not create a session ({response.status_code})."
            )
        data = response.json()
        session_id = data.get("id") or data.get("sessionID")
        if not isinstance(session_id, str) or not session_id:
            raise WorkflowError("OpenCode returned an invalid session identifier.")
        self._sessions[chat_id] = session_id
        return session_id

    async def session_for(self, chat_id: int) -> str:
        await self.ensure_server()
        session_id = self._sessions.get(chat_id)
        if session_id:
            return session_id
        return await self._create_session(chat_id)

    async def run_command(self, chat_id: int, command: str, arguments: str) -> str:
        """Execute one known OpenCode slash command and return its text output."""
        client = await self._get_client()
        session_id = await self.session_for(chat_id)
        payload = {"command": command, "arguments": arguments}
        response = await client.post(f"/session/{session_id}/command", json=payload)

        if response.status_code == 404:
            self._sessions.pop(chat_id, None)
            session_id = await self._create_session(chat_id)
            response = await client.post(
                f"/session/{session_id}/command",
                json=payload,
            )

        if response.is_error:
            detail = response.text[:300].replace("\n", " ")
            raise WorkflowError(
                f"OpenCode command failed ({response.status_code}): {detail}"
            )
        return self._response_text(response.json())

    async def send_message(self, chat_id: int, text: str) -> str:
        """Continue a session for a narrowly scoped confirmation or follow-up."""
        client = await self._get_client()
        session_id = await self.session_for(chat_id)
        response = await client.post(
            f"/session/{session_id}/message",
            json={"parts": [{"type": "text", "text": text}]},
        )
        if response.is_error:
            detail = response.text[:300].replace("\n", " ")
            raise WorkflowError(
                f"OpenCode follow-up failed ({response.status_code}): {detail}"
            )
        return self._response_text(response.json())

    async def abort(self, chat_id: int) -> None:
        session_id = self._sessions.get(chat_id)
        if not session_id:
            return
        client = await self._get_client()
        try:
            await client.post(f"/session/{session_id}/abort")
        except httpx.HTTPError:
            LOGGER.warning("Could not abort OpenCode session %s", session_id)

    @staticmethod
    def _response_text(data: dict[str, Any]) -> str:
        parts = data.get("parts", [])
        texts: list[str] = []
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        if texts:
            return "\n\n".join(texts)
        return json.dumps(data, ensure_ascii=True, indent=2)[:30_000]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._owns_server and self._server_process is not None:
            process = self._server_process
            self._server_process = None
            self._owns_server = False
            if os.name == "nt":
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            elif process.poll() is None:
                process.terminate()
            if process.poll() is None:
                try:
                    await asyncio.to_thread(process.wait, 5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait)


async def run_uv_script(
    script_name: str,
    args: list[str] | tuple[str, ...] = (),
    timeout_seconds: int = 60 * 60,
) -> ProcessResult:
    """Run one repository script through the project's required uv entrypoint."""
    command = ["uv", "run", f"System/{script_name}", *args]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(WORKSPACE),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        raise WorkflowError(f"Could not start `{command[0]}`: {exc}") from exc

    try:
        output, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        raise WorkflowError(
            f"`{' '.join(command)}` exceeded the {timeout_seconds}-second timeout."
        ) from exc
    except asyncio.CancelledError:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        raise

    text = output.decode("utf-8", errors="replace") if output else ""
    return ProcessResult(process.returncode or 0, text.strip())


def status_summary() -> str:
    """Read-only summary of the spreadsheet of truth."""
    if not SPREADSHEET_PATH.exists():
        return "No reel log exists yet. Run /sync to start the pipeline."

    try:
        frame = pd.read_excel(SPREADSHEET_PATH)
    except Exception as exc:
        LOGGER.exception("Could not read reel log")
        return f"Could not read Brain/Reels_Log.xlsx: {exc}"

    if frame.empty:
        return "The reel log is empty. Run /sync to scrape creators."

    status_counts = frame.get("Status", pd.Series(dtype=str)).fillna("").astype(str)
    category_counts = frame.get("Category", pd.Series(dtype=str)).fillna("").astype(str)
    lines = [f"Reels: {len(frame)}"]
    lines.append(
        "Status: "
        + ", ".join(
            f"{name or 'UNKNOWN'}={count}"
            for name, count in status_counts.str.upper().value_counts().items()
        )
    )
    if not category_counts.empty:
        lines.append(
            "Category: "
            + ", ".join(
                f"{name or 'UNKNOWN'}={count}"
                for name, count in category_counts.str.upper().value_counts().items()
            )
        )

    pending_transcripts = max(
        0,
        len(list((WORKSPACE / "Assets").glob("*.wav")))
        - len(list((WORKSPACE / "Assets").glob("*.txt"))),
    )
    if pending_transcripts > 0:
        lines.append(f"Audio awaiting transcript: {pending_transcripts}")
    lines.append(
        "Analysis trios: "
        f"{len(list(ANALYSES_DIR.glob('*_visual.json')))} visual files"
    )
    return "\n".join(lines)


def generated_file_snapshot() -> dict[Path, GeneratedFile]:
    """Capture only deliverables that are safe to send through Telegram."""
    snapshot: dict[Path, GeneratedFile] = {}
    paths = list(SCRIPTS_DIR.glob("*.md")) + list(DRAFT_RESULT_DIR.glob("*.pdf"))
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path] = GeneratedFile(path, stat.st_size, stat.st_mtime_ns)
    return snapshot


def changed_generated_files(
    before: dict[Path, GeneratedFile],
) -> list[Path]:
    changed: list[Path] = []
    for path, current in generated_file_snapshot().items():
        previous = before.get(path)
        if previous is None or (
            previous.size != current.size
            or previous.modified_ns != current.modified_ns
        ):
            changed.append(path)
    return sorted(changed, key=lambda item: item.stat().st_mtime_ns)
