"""Telegram interface for the Instagram.AI workflow.

Run from the repository root with:

    uv run System/telegram_bot.py

The bot uses long polling, so the local Windows machine must remain online.
Only the configured Telegram chat/user can invoke it.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Awaitable

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from telegram_workflow import (
        BotSettings,
        OpenCodeBridge,
        WorkflowError,
        changed_generated_files,
        generated_file_snapshot,
        run_uv_script,
        status_summary,
    )
except ModuleNotFoundError as exc:
    if exc.name != "telegram_workflow":
        raise
    from System.telegram_workflow import (
        BotSettings,
        OpenCodeBridge,
        WorkflowError,
        changed_generated_files,
        generated_file_snapshot,
        run_uv_script,
        status_summary,
    )


LOGGER = logging.getLogger(__name__)

MAX_TELEGRAM_TEXT = 4000
MAX_TOPIC_LENGTH = 1200
MAX_SCRIPT_LENGTH = 50_000
MAX_DOCUMENT_BYTES = 1_000_000
MAX_FILE_UPLOAD_BYTES = 49 * 1024 * 1024

INSTAGRAM_URL_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?(?:\?.*)?$",
    re.IGNORECASE,
)
SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,80}$")


class TelegramBot:
    def __init__(self, settings: BotSettings) -> None:
        self.settings = settings
        self.bridge = OpenCodeBridge(settings)
        self.active_task: asyncio.Task[None] | None = None
        self.active_chat_id: int | None = None
        self.active_label = ""
        self.pending_cleanup: set[int] = set()

    def authorized(self, update: Update) -> bool:
        message = update.effective_message
        user = update.effective_user
        if message is None or message.chat is None:
            return False
        user_id = user.id if user else None
        return self.settings.is_authorized(message.chat.id, user_id)

    async def post_init(self, application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Show the Instagram.AI Telegram menu"),
                BotCommand("help", "Show available workflow commands"),
                BotCommand("draft", "Create reel script drafts"),
                BotCommand("redraft", "Analyze and adapt an Instagram reel"),
                BotCommand("refine", "Refine a pasted or uploaded script"),
                BotCommand("analyze", "Analyze pending or selected reels"),
                BotCommand("sync", "Run the full ingestion and analysis pipeline"),
                BotCommand("status", "Show reel and analysis status"),
                BotCommand("cleanup", "Preview and confirm media cleanup"),
                BotCommand("cancel", "Cancel the active workflow"),
            ]
        )

    async def post_shutdown(self, application: Application) -> None:
        await self.bridge.close()

    async def help_message(self, update: Update) -> None:
        if not self.authorized(update):
            return
        await update.effective_message.reply_text(
            "Instagram.AI Telegram control\n\n"
            "/draft <topic>\n"
            "/redraft <Instagram reel URL>\n"
            "/refine <script text>\n"
            "/analyze [pending|shortcode]\n"
            "/sync [NICHE|BRANDING|ALL] [--max-reels N]\n"
            "/status\n"
            "/cleanup\n"
            "/cancel\n\n"
            "You can also write natural requests such as "
            "'draft a reel about discipline'. Unknown requests are not executed."
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.help_message(update)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.authorized(update):
            return
        await update.effective_message.reply_text(status_summary())

    async def draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        topic = self._raw_arguments(update).strip()
        if not topic:
            await update.effective_message.reply_text(
                "Usage: /draft <topic>\nExample: /draft discipline when motivation disappears"
            )
            return
        if len(topic) > MAX_TOPIC_LENGTH:
            await update.effective_message.reply_text(
                f"The topic must be {MAX_TOPIC_LENGTH} characters or fewer."
            )
            return
        await self.schedule_opencode(update, "draft", topic, "drafting scripts")

    async def redraft(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        url = " ".join(context.args).strip()
        if not INSTAGRAM_URL_RE.fullmatch(url):
            await update.effective_message.reply_text(
                "Usage: /redraft <Instagram reel URL>\n"
                "Only instagram.com/reel/... and instagram.com/p/... URLs are accepted."
            )
            return
        await self.schedule_opencode(update, "redraft", url, "redrafting the reel")

    async def refine(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        script = self._raw_arguments(update).strip()
        if not script:
            script = context.chat_data.pop("refine_text", "").strip()
        if not script:
            await update.effective_message.reply_text(
                "Paste the script after /refine, or upload a .md/.txt script first."
            )
            return
        if len(script) > MAX_SCRIPT_LENGTH:
            await update.effective_message.reply_text(
                f"The script must be {MAX_SCRIPT_LENGTH} characters or fewer."
            )
            return
        await self.schedule_opencode(update, "refine", script, "refining the script")

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        target = " ".join(context.args).strip() or "pending"
        if target.lower() == "pending":
            target = "pending"
        elif not SHORTCODE_RE.fullmatch(target):
            await update.effective_message.reply_text(
                "Usage: /analyze [pending|shortcode]"
            )
            return
        await self.schedule_opencode(update, "analyze", target, f"analyzing {target}")

    async def sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            category, max_reels = self._parse_sync_args(context.args)
        except WorkflowError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        arguments = f"{category} --max-reels {max_reels}"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Run sync", callback_data=f"sync:run:{category}:{max_reels}"
                    ),
                    InlineKeyboardButton("Cancel", callback_data="sync:cancel"),
                ]
            ]
        )
        await update.effective_message.reply_text(
            f"This will run the full {category} pipeline with up to {max_reels} reels "
            "per creator. Continue?",
            reply_markup=keyboard,
        )

    async def cleanup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.authorized(update):
            return
        if self.busy():
            await update.effective_message.reply_text(
                f"A workflow is already running ({self.active_label}). Use /cancel first."
            )
            return
        await update.effective_message.reply_text("Preparing a cleanup preview...")
        await self._schedule(
            update,
            "cleanup preview",
            self._cleanup_preview(update.effective_chat.id),
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.authorized(update):
            return
        if not self.busy():
            await update.effective_message.reply_text("No workflow is running.")
            return
        if self.active_chat_id == update.effective_chat.id:
            await self.bridge.abort(update.effective_chat.id)
            assert self.active_task is not None
            self.active_task.cancel()
            await update.effective_message.reply_text("Cancellation requested.")
        else:
            await update.effective_message.reply_text(
                f"Another chat is currently running {self.active_label}."
            )

    async def document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.authorized(update):
            return
        document = update.effective_message.document
        if document is None:
            return
        name = (document.file_name or "").lower()
        if not name.endswith((".md", ".txt")):
            await update.effective_message.reply_text(
                "Only Markdown and plain-text script files can be refined."
            )
            return
        if document.file_size and document.file_size > MAX_DOCUMENT_BYTES:
            await update.effective_message.reply_text(
                "That script file is too large. The limit is 1 MB."
            )
            return

        inbox = Path(__file__).resolve().parent.parent / ".runtime" / "telegram"
        inbox.mkdir(parents=True, exist_ok=True)
        target = inbox / f"refine_{document.file_unique_id}{Path(name).suffix}"
        try:
            telegram_file = await context.bot.get_file(document.file_id)
            await telegram_file.download_to_drive(custom_path=str(target))
            script = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            LOGGER.exception("Could not download Telegram document")
            await update.effective_message.reply_text(
                f"Could not read that script file: {exc}"
            )
            return
        finally:
            target.unlink(missing_ok=True)

        if not script.strip():
            await update.effective_message.reply_text("The uploaded script is empty.")
            return
        if len(script) > MAX_SCRIPT_LENGTH:
            await update.effective_message.reply_text(
                f"The script must be {MAX_SCRIPT_LENGTH} characters or fewer."
            )
            return
        context.chat_data["refine_text"] = script
        await update.effective_message.reply_text(
            "Script received. Send /refine to run the style critic."
        )

    async def text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.authorized(update):
            return
        message = update.effective_message
        if message is None or not message.text:
            return
        request = self._natural_request(message.text)
        if request is None:
            await message.reply_text(
                "I can route these requests: draft, redraft, refine, analyze, "
                "sync, status, and cleanup. Use /help for examples."
            )
            return
        kind, argument = request
        if kind == "status":
            await self.status(update, context)
        elif kind == "cleanup":
            await self.cleanup(update, context)
        elif kind == "draft":
            await self.schedule_opencode(update, "draft", argument, "drafting scripts")
        elif kind == "redraft":
            await self.schedule_opencode(
                update, "redraft", argument, "redrafting the reel"
            )
        elif kind == "analyze":
            await self.schedule_opencode(
                update, "analyze", argument, f"analyzing {argument}"
            )
        elif kind == "sync":
            await self._show_sync_confirmation(update, argument)

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or not self.authorized(update):
            return
        await query.answer()
        data = query.data or ""
        chat_id = query.message.chat.id if query.message else None
        if chat_id is None:
            return

        if data == "cleanup:cancel":
            self.pending_cleanup.discard(chat_id)
            await query.edit_message_text("Cleanup cancelled.")
            return
        if data == "cleanup:confirm":
            if chat_id not in self.pending_cleanup:
                await query.edit_message_text("That cleanup confirmation has expired.")
                return
            self.pending_cleanup.discard(chat_id)
            await query.edit_message_text("Cleanup confirmed. Removing eligible media...")
            await self._schedule(
                update,
                "cleanup",
                self._cleanup_execute(chat_id),
            )
            return
        if data == "sync:cancel":
            await query.edit_message_text("Sync cancelled.")
            return
        if data.startswith("sync:run:"):
            if self.busy():
                await query.edit_message_text(
                    f"A workflow is already running ({self.active_label})."
                )
                return
            parts = data.split(":")
            if len(parts) != 4:
                await query.edit_message_text("Invalid sync request.")
                return
            category, max_reels = parts[2], parts[3]
            await query.edit_message_text(
                f"Sync started for {category}, up to {max_reels} reels per creator."
            )
            await self._schedule(
                update,
                "sync",
                self._run_opencode(
                    chat_id,
                    "sync",
                    f"{category} --max-reels {max_reels}",
                ),
            )

    async def schedule_opencode(
        self,
        update: Update,
        command: str,
        arguments: str,
        label: str,
    ) -> None:
        if not self.authorized(update):
            return
        if self.busy():
            await update.effective_message.reply_text(
                f"A workflow is already running ({self.active_label}). Use /cancel first."
            )
            return
        await update.effective_message.reply_text(f"Started: {label}. I will send the result here.")
        await self._schedule(
            update,
            label,
            self._run_opencode(update.effective_chat.id, command, arguments),
        )

    async def _schedule(
        self,
        update: Update,
        label: str,
        operation: Awaitable[tuple[str, list[Path]] | str],
    ) -> None:
        if self.busy():
            await update.effective_message.reply_text(
                f"A workflow is already running ({self.active_label})."
            )
            return
        chat_id = update.effective_chat.id
        self.active_chat_id = chat_id
        self.active_label = label
        self.active_task = asyncio.create_task(
            self._job(update, label, operation),
            name=f"telegram-{label}",
        )

    def busy(self) -> bool:
        return self.active_task is not None and not self.active_task.done()

    async def _job(
        self,
        update: Update,
        label: str,
        operation: Awaitable[tuple[str, list[Path]] | str],
    ) -> None:
        task = asyncio.current_task()
        try:
            result = await self._with_heartbeat(update, label, operation)
            if isinstance(result, tuple):
                output, files = result
            else:
                output, files = result, []
            await self._send_output(update, output or f"{label.capitalize()} complete.")
            if label == "cleanup preview" and update.effective_chat.id in self.pending_cleanup:
                await update.effective_message.reply_text(
                    "Confirm deletion? This only targets reels already marked ANALYZED.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "Delete eligible media",
                                    callback_data="cleanup:confirm",
                                ),
                                InlineKeyboardButton(
                                    "Cancel",
                                    callback_data="cleanup:cancel",
                                ),
                            ]
                        ]
                    ),
                )
            await self._send_files(update, files)
        except asyncio.CancelledError:
            await update.effective_message.reply_text(f"{label.capitalize()} cancelled.")
        except WorkflowError as exc:
            await update.effective_message.reply_text(f"{label.capitalize()} failed: {exc}")
        except Exception as exc:
            LOGGER.exception("Telegram workflow failed: %s", label)
            await update.effective_message.reply_text(
                f"{label.capitalize()} failed unexpectedly: {exc}"
            )
        finally:
            if self.active_task is task:
                self.active_task = None
                self.active_chat_id = None
                self.active_label = ""

    async def _with_heartbeat(
        self,
        update: Update,
        label: str,
        operation: Awaitable[tuple[str, list[Path]] | str],
    ) -> tuple[str, list[Path]] | str:
        task = asyncio.create_task(operation)
        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=self.settings.heartbeat_seconds,
                )
            except asyncio.TimeoutError:
                await update.effective_message.reply_text(
                    f"Still working on {label}. The pipeline may take several minutes."
                )
            except asyncio.CancelledError:
                task.cancel()
                raise

    async def _run_opencode(
        self,
        chat_id: int,
        command: str,
        arguments: str,
    ) -> tuple[str, list[Path]]:
        before = generated_file_snapshot()
        try:
            output = await asyncio.wait_for(
                self.bridge.run_command(chat_id, command, arguments),
                timeout=self.settings.command_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            await self.bridge.abort(chat_id)
            raise WorkflowError(
                f"The OpenCode command exceeded the "
                f"{self.settings.command_timeout_seconds}-second timeout."
            ) from exc
        return output, changed_generated_files(before)

    async def _cleanup_preview(self, chat_id: int) -> str:
        self.pending_cleanup.discard(chat_id)
        result = await run_uv_script(
            "cleanup_assets.py",
            ["--dry-run"],
            timeout_seconds=self.settings.command_timeout_seconds,
        )
        if result.returncode != 0:
            raise WorkflowError(self._tail(result.output))
        output = result.output or "No eligible media found."
        if "No ANALYZED reels found" not in output:
            self.pending_cleanup.add(chat_id)
        return output

    async def _cleanup_execute(self, chat_id: int) -> str:
        result = await run_uv_script(
            "cleanup_assets.py",
            timeout_seconds=self.settings.command_timeout_seconds,
        )
        if result.returncode != 0:
            raise WorkflowError(self._tail(result.output))
        return result.output or "Cleanup complete."

    async def _send_output(self, update: Update, output: str) -> None:
        chunks = self._split_text(output)
        for chunk in chunks:
            await update.effective_message.reply_text(chunk)

    async def _send_files(self, update: Update, files: list[Path]) -> None:
        for path in files:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_UPLOAD_BYTES:
                await update.effective_message.reply_text(
                    f"Created {path.name}, but it is too large to upload through Telegram."
                )
                continue
            caption = f"Instagram.AI output: {path.name}"
            with path.open("rb") as handle:
                await update.effective_message.reply_document(
                    document=InputFile(handle, filename=path.name),
                    caption=caption,
                )

    @staticmethod
    def _split_text(text: str) -> list[str]:
        if len(text) <= MAX_TELEGRAM_TEXT:
            return [text]
        chunks: list[str] = []
        remaining = text.strip()
        while len(remaining) > MAX_TELEGRAM_TEXT:
            cut = remaining.rfind("\n", 0, MAX_TELEGRAM_TEXT)
            if cut < MAX_TELEGRAM_TEXT // 2:
                cut = MAX_TELEGRAM_TEXT
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _tail(text: str, limit: int = 2500) -> str:
        clean = text.strip()
        return clean[-limit:] if clean else "No output was returned."

    @staticmethod
    def _parse_sync_args(args: list[str]) -> tuple[str, int]:
        category = "ALL"
        max_reels = 5
        index = 0
        if args and args[0].upper() in {"NICHE", "BRANDING", "ALL"}:
            category = args[0].upper()
            index = 1
        elif args and not args[0].startswith("--"):
            raise WorkflowError("Category must be NICHE, BRANDING, or ALL.")

        while index < len(args):
            if args[index] != "--max-reels" or index + 1 >= len(args):
                raise WorkflowError("Usage: /sync [NICHE|BRANDING|ALL] [--max-reels N]")
            try:
                max_reels = int(args[index + 1])
            except ValueError as exc:
                raise WorkflowError("--max-reels must be a positive integer.") from exc
            if not 1 <= max_reels <= 50:
                raise WorkflowError("--max-reels must be between 1 and 50.")
            index += 2
        return category, max_reels

    async def _show_sync_confirmation(self, update: Update, arguments: str) -> None:
        parts = arguments.split()
        category, max_reels = self._parse_sync_args(
            [parts[0], "--max-reels", parts[2]]
        )
        await update.effective_message.reply_text(
            f"This will run the full {category} pipeline with up to {max_reels} reels "
            "per creator. Continue?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Run sync",
                            callback_data=f"sync:run:{category}:{max_reels}",
                        ),
                        InlineKeyboardButton("Cancel", callback_data="sync:cancel"),
                    ]
                ]
            ),
        )

    @staticmethod
    def _raw_arguments(update: Update) -> str:
        text = update.effective_message.text if update.effective_message else ""
        if not text:
            return ""
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) == 2 else ""

    @staticmethod
    def _natural_request(text: str) -> tuple[str, str] | None:
        clean = text.strip()
        lower = clean.lower()
        if lower in {"status", "show status", "how is the pipeline"}:
            return "status", ""
        if lower in {"cleanup", "clean up", "clean up assets"}:
            return "cleanup", ""

        draft_match = re.match(
            r"^(?:please\s+)?(?:draft|write|create)(?:\s+(?:a|an))?"
            r"(?:\s+(?:reel|script|reel script))?\s+(?:about|on)\s+(.+)$",
            clean,
            re.IGNORECASE,
        )
        if draft_match:
            topic = draft_match.group(1).strip()
            if 1 <= len(topic) <= MAX_TOPIC_LENGTH:
                return "draft", topic

        redraft_match = re.search(
            r"https?://(?:www\.)?instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?(?:\?.*)?",
            clean,
            re.IGNORECASE,
        )
        if redraft_match and re.search(r"redraft|adapt|analyze", lower):
            url = redraft_match.group(0).rstrip(".,)")
            if INSTAGRAM_URL_RE.fullmatch(url):
                return "redraft", url

        if lower in {"analyze pending", "analyze the pending reels"}:
            return "analyze", "pending"
        analyze_match = re.match(r"^analyze\s+([A-Za-z0-9_-]{2,80})$", clean, re.I)
        if analyze_match:
            return "analyze", analyze_match.group(1)

        sync_match = re.match(
            r"^sync(?:\s+(NICHE|BRANDING|ALL))?(?:\s+(?:up to\s+)?(\d+))?$",
            clean,
            re.IGNORECASE,
        )
        if sync_match:
            category = (sync_match.group(1) or "ALL").upper()
            max_reels = int(sync_match.group(2) or 5)
            if 1 <= max_reels <= 50:
                return "sync", f"{category} --max-reels {max_reels}"
        return None


def build_application(settings: BotSettings) -> Application:
    bot = TelegramBot(settings)
    application = (
        Application.builder()
        .token(settings.token)
        .post_init(bot.post_init)
        .post_shutdown(bot.post_shutdown)
        .build()
    )
    application.bot_data["telegram_bot"] = bot

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_message))
    application.add_handler(CommandHandler("draft", bot.draft))
    application.add_handler(CommandHandler("redraft", bot.redraft))
    application.add_handler(CommandHandler("refine", bot.refine))
    application.add_handler(CommandHandler("analyze", bot.analyze))
    application.add_handler(CommandHandler("sync", bot.sync))
    application.add_handler(CommandHandler("status", bot.status))
    application.add_handler(CommandHandler("cleanup", bot.cleanup))
    application.add_handler(CommandHandler("cancel", bot.cancel))
    application.add_handler(CallbackQueryHandler(bot.callback))
    application.add_handler(
        MessageHandler(filters.Document.ALL & ~filters.COMMAND, bot.document)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.text)
    )
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        settings = BotSettings.from_env()
    except WorkflowError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    application = build_application(settings)
    LOGGER.info("Starting Instagram.AI Telegram bot with long polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
