"""
config.py  —  Shared configuration for the Telegram integration.
================================================================================
Loads credentials from the workspace .env and exposes:

  * TELEGRAM_BOT_TOKEN / OWNER / ALLOWED chat + user ids
  * OPENAI_API_KEY (reserved for future use)
  * Resolved paths (workspace root, JSON store, Reels_Log.xlsx)
  * Helpers: api_url(), require_token(), default_chat_id(), is_allowed()

Nothing here performs network or disk writes — import it freely.

Usage:
    uv run telegram_bot/config.py        # print a masked config health check
"""

import os
import sys

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

BOT_DIR = os.path.abspath(os.path.dirname(__file__))

# ── Credentials ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_OWNER_ID        = os.getenv("TELEGRAM_OWNER_ID", "").strip()
TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "").strip()

# ── Paths ───────────────────────────────────────────────────────────────────
STORE_PATH       = os.path.join(BOT_DIR, "telegram_reels.json")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")
ASSETS_DIR       = os.path.join(WORKSPACE, "Assets")

# ── Telegram HTTP API ───────────────────────────────────────────────────────
API_BASE     = "https://api.telegram.org"
HTTP_TIMEOUT = 60          # seconds, for plain API calls
UPLOAD_TIMEOUT = 300       # seconds, for sendDocument uploads


def api_url(method: str) -> str:
    """Full Bot API endpoint for `method` (e.g. 'getUpdates')."""
    return f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/{method}"


def require_token() -> str:
    """Return the bot token or raise a clear error if it is missing."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set in .env — cannot call the Telegram API."
        )
    return TELEGRAM_BOT_TOKEN


def default_chat_id() -> str:
    """Chat to send replies/files to when no --chat-id override is given."""
    return TELEGRAM_ALLOWED_CHAT_ID or TELEGRAM_OWNER_ID or TELEGRAM_ALLOWED_USER_ID


def allowed_chat_ids() -> set[str]:
    return {v for v in (TELEGRAM_ALLOWED_CHAT_ID,) if v}


def allowed_user_ids() -> set[str]:
    return {v for v in (TELEGRAM_ALLOWED_USER_ID, TELEGRAM_OWNER_ID) if v}


def is_allowed(chat_id: object, user_id: object) -> bool:
    """
    True when a message comes from the owner's chat/user.

    If NO allowlist is configured at all, everything is allowed (dev mode) —
    otherwise a match on either the chat id or the user id is required.
    """
    chats = allowed_chat_ids()
    users = allowed_user_ids()
    if not chats and not users:
        return True
    return str(chat_id) in chats or str(user_id) in users


def _mask(value: str) -> str:
    if not value:
        return "MISSING"
    if len(value) <= 8:
        return f"SET ({len(value)} chars)"
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def main() -> None:
    print("[TELEGRAM CONFIG]")
    print(f"  WORKSPACE                = {WORKSPACE}")
    print(f"  STORE_PATH               = {STORE_PATH}")
    print(f"  SPREADSHEET_PATH         = {SPREADSHEET_PATH}")
    print(f"  TELEGRAM_BOT_TOKEN       = {_mask(TELEGRAM_BOT_TOKEN)}")
    print(f"  TELEGRAM_OWNER_ID        = {TELEGRAM_OWNER_ID or 'MISSING'}")
    print(f"  TELEGRAM_ALLOWED_CHAT_ID = {TELEGRAM_ALLOWED_CHAT_ID or 'MISSING'}")
    print(f"  TELEGRAM_ALLOWED_USER_ID = {TELEGRAM_ALLOWED_USER_ID or 'MISSING'}")
    print(f"  OPENAI_API_KEY           = {_mask(OPENAI_API_KEY)}")
    print(f"  default_chat_id()        = {default_chat_id() or 'MISSING'}")
    if not TELEGRAM_BOT_TOKEN:
        print("\n[ERROR] TELEGRAM_BOT_TOKEN missing — the bot cannot run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
