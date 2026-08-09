"""
send_file.py  —  Send a file (PDF) or a status message back to Telegram.
================================================================================
Plain HTTP calls to the Telegram Bot API via requests — no bot process needed.

    send_document(path, caption, chat_id)  ->  sendDocument
    send_message(text, chat_id)            ->  sendMessage

The chat defaults to TELEGRAM_ALLOWED_CHAT_ID (then OWNER / ALLOWED_USER).
A JSON result is printed to stdout; progress goes to stderr.

Usage:
    uv run telegram_bot/send_file.py --file draft_result/Script.pdf
    uv run telegram_bot/send_file.py --file out.pdf --caption "2 drafts ready"
    uv run telegram_bot/send_file.py --message "Processing your reel…"
    uv run telegram_bot/send_file.py --file out.pdf --chat-id 123456789
"""

import os
import sys
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests  # type: ignore

try:                                     # package import
    from . import config
except ImportError:                      # script import (uv run telegram_bot/send_file.py)
    import config                        # type: ignore

MAX_MESSAGE_LEN = 4096
MAX_CAPTION_LEN = 1024


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_chat_id(chat_id: str | int | None) -> str:
    resolved = str(chat_id) if chat_id not in (None, "") else config.default_chat_id()
    if not resolved:
        raise RuntimeError(
            "No chat id — set TELEGRAM_ALLOWED_CHAT_ID in .env or pass --chat-id."
        )
    return resolved


def _check(payload: dict, what: str) -> dict:
    if not payload.get("ok"):
        raise RuntimeError(
            f"{what} failed — Telegram error {payload.get('error_code')}: "
            f"{payload.get('description')}"
        )
    return payload.get("result", {})


def send_message(text: str, chat_id: str | int | None = None,
                 parse_mode: str | None = None,
                 disable_preview: bool = True) -> dict:
    """Send a plain text status message. Returns the Telegram Message object."""
    if not text or not text.strip():
        raise ValueError("send_message() requires non-empty text")

    target = _resolve_chat_id(chat_id)
    if len(text) > MAX_MESSAGE_LEN:
        log(f"[WARN] Message truncated to {MAX_MESSAGE_LEN} chars")
        text = text[: MAX_MESSAGE_LEN - 1] + "…"

    data: dict = {
        "chat_id": target,
        "text": text,
        "disable_web_page_preview": disable_preview,
    }
    if parse_mode:
        data["parse_mode"] = parse_mode

    try:
        resp = requests.post(config.api_url("sendMessage"), data=data,
                             timeout=config.HTTP_TIMEOUT)
        payload = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"sendMessage request failed: {e}") from e
    except ValueError as e:
        raise RuntimeError(f"sendMessage returned non-JSON: {resp.text[:200]}") from e

    result = _check(payload, "sendMessage")
    log(f"[SENT] message -> chat {target}")
    return result


def send_document(file_path: str, caption: str | None = None,
                  chat_id: str | int | None = None) -> dict:
    """Upload a file (PDF, etc). Returns the Telegram Message object."""
    path = os.path.abspath(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    if not os.path.isfile(path):
        raise ValueError(f"Not a file: {path}")

    target = _resolve_chat_id(chat_id)
    data: dict = {"chat_id": target}
    if caption:
        if len(caption) > MAX_CAPTION_LEN:
            log(f"[WARN] Caption truncated to {MAX_CAPTION_LEN} chars")
            caption = caption[: MAX_CAPTION_LEN - 1] + "…"
        data["caption"] = caption

    size_kb = os.path.getsize(path) / 1024
    log(f"[UPLOAD] {os.path.basename(path)} ({size_kb:.1f} KB) -> chat {target}")

    try:
        with open(path, "rb") as fh:
            files = {"document": (os.path.basename(path), fh)}
            resp = requests.post(config.api_url("sendDocument"), data=data,
                                 files=files, timeout=config.UPLOAD_TIMEOUT)
        payload = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"sendDocument request failed: {e}") from e
    except ValueError as e:
        raise RuntimeError(f"sendDocument returned non-JSON: {resp.text[:200]}") from e

    result = _check(payload, "sendDocument")
    log(f"[SENT] document -> chat {target} (message_id={result.get('message_id')})")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a file or a status message to the Telegram chat.")
    parser.add_argument("--file", default=None, help="Path to the file (PDF) to send")
    parser.add_argument("--caption", default=None, help="Optional caption for the file")
    parser.add_argument("--message", default=None,
                        help="Send a plain text message instead of / alongside a file")
    parser.add_argument("--chat-id", dest="chat_id", default=None,
                        help="Override the target chat (default: TELEGRAM_ALLOWED_CHAT_ID)")
    args = parser.parse_args()

    if not args.file and not args.message:
        parser.error("provide --file and/or --message")

    out: dict = {"ok": True, "sent": []}
    try:
        config.require_token()
        if args.message:
            msg = send_message(args.message, chat_id=args.chat_id)
            out["sent"].append({"type": "message", "message_id": msg.get("message_id")})
        if args.file:
            doc = send_document(args.file, caption=args.caption, chat_id=args.chat_id)
            out["sent"].append({
                "type": "document",
                "file": os.path.abspath(args.file),
                "message_id": doc.get("message_id"),
            })
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2, ensure_ascii=False))
        log(f"[ERROR] {e}")
        sys.exit(1)

    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
