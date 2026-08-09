"""
fetch_messages.py  —  Pull new reel links out of the Telegram chat.
================================================================================
One-shot `getUpdates` call against the Telegram Bot API (plain HTTP via
requests — no long-polling bot process is started). For every message from the
allowed chat/user it:

  1. Finds Instagram reel URLs in the text / caption / link entities
  2. Extracts the shortcode and de-dupes against telegram_reels.json AND
     Brain/Reels_Log.xlsx
  3. Detects "draft N scripts" intent
  4. Registers new reels in the JSON store and appends a
     Category=NICHE / Status=SCRAPED / Source=TELEGRAM row to Reels_Log.xlsx
  5. Advances last_update_id so the same message is never handled twice

A structured JSON summary is printed to stdout (progress/warnings go to stderr),
so the telegram agent can consume it directly.

Usage:
    uv run telegram_bot/fetch_messages.py
    uv run telegram_bot/fetch_messages.py --dry-run
    uv run telegram_bot/fetch_messages.py --limit 20
"""

import sys
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests  # type: ignore

try:                                     # package import
    from . import config, store
except ImportError:                      # script import (uv run telegram_bot/fetch_messages.py)
    import config                        # type: ignore
    import store                         # type: ignore

MESSAGE_KEYS = ("message", "edited_message", "channel_post", "edited_channel_post")
ALLOWED_UPDATES = ["message", "edited_message", "channel_post", "edited_channel_post"]
TELEGRAM_MAX_LIMIT = 100


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def get_updates(offset: int, limit: int) -> list:
    """Single getUpdates call. Raises RuntimeError on API/transport failure."""
    params: dict = {
        "limit": max(1, min(limit, TELEGRAM_MAX_LIMIT)),
        "timeout": 0,
        "allowed_updates": json.dumps(ALLOWED_UPDATES),
    }
    if offset > 0:
        params["offset"] = offset

    try:
        resp = requests.get(config.api_url("getUpdates"), params=params,
                            timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Telegram request failed: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError(
            f"Telegram returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}"
        ) from e

    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram API error {payload.get('error_code')}: {payload.get('description')}"
        )
    return payload.get("result", [])


def message_text(msg: dict) -> str:
    return msg.get("text") or msg.get("caption") or ""


def message_urls(msg: dict) -> list[str]:
    """Reel URLs from the visible text plus any hidden text_link entities."""
    urls = store.find_reel_urls(message_text(msg))
    for key in ("entities", "caption_entities"):
        for ent in msg.get(key) or []:
            if ent.get("type") == "text_link" and ent.get("url"):
                urls += store.find_reel_urls(ent["url"])
    return list(dict.fromkeys(urls))


def process(limit: int, dry_run: bool) -> dict:
    data = store.load_store()
    offset = int(data.get("last_update_id", 0) or 0)
    updates = get_updates(offset + 1 if offset else 0, limit)
    log(f"[FETCH] {len(updates)} update(s) returned (offset={offset})")

    new_reels: list[dict] = []
    already_processed: list[dict] = []
    errors: list[dict] = []
    seen_this_run: set[str] = set()

    scanned = 0
    skipped_not_allowed = 0
    draft_requests = 0
    max_update_id = offset

    for update in updates:
        update_id = int(update.get("update_id", 0) or 0)
        max_update_id = max(max_update_id, update_id)

        msg = next((update[k] for k in MESSAGE_KEYS if k in update), None)
        if not msg:
            continue
        scanned += 1

        chat_id = (msg.get("chat") or {}).get("id")
        user_id = (msg.get("from") or {}).get("id")
        if not config.is_allowed(chat_id, user_id):
            skipped_not_allowed += 1
            log(f"   [SKIP] update {update_id}: chat={chat_id} user={user_id} not allowed")
            continue

        text = message_text(msg)
        message_id = msg.get("message_id")
        urls = message_urls(msg)
        if not urls:
            continue

        for url in urls:
            shortcode = store.extract_shortcode(url)
            if not shortcode:
                errors.append({"url": url, "error": "could not extract shortcode"})
                log(f"   [WARN] no shortcode in {url}")
                continue

            if shortcode in seen_this_run:
                already_processed.append({
                    "shortcode": shortcode, "url": url,
                    "reason": "duplicate link in this batch",
                })
                continue

            if store.is_duplicate(shortcode, data):
                reason = store.duplicate_reason(shortcode, data) or "already tracked"
                already_processed.append({
                    "shortcode": shortcode, "url": url, "reason": reason,
                })
                log(f"   [DUP]  {shortcode} — {reason}")
                continue

            draft_requested, draft_count = store.detect_draft_intent(text)
            seen_this_run.add(shortcode)

            if dry_run:
                excel_result = "skipped (dry-run)"
            else:
                store.add_reel(url, message_id, text, store=data, save=False)
                try:
                    excel_result = store.sync_to_excel(shortcode, url, text)
                except Exception as e:                    # never lose the store update
                    excel_result = f"failed: {e}"
                    errors.append({"shortcode": shortcode, "error": f"excel sync failed: {e}"})
                    log(f"   [ERROR] Excel sync failed for {shortcode}: {e}")

            new_reels.append({
                "shortcode": shortcode,
                "url": url,
                "message_id": message_id,
                "message_text": text,
                "draft_requested": draft_requested,
                "draft_count": draft_count,
                "excel": excel_result,
            })
            if draft_requested:
                draft_requests += 1
            log(f"   [NEW]  {shortcode}  drafts={draft_count if draft_requested else 0}  excel={excel_result}")

    if not dry_run:
        store.update_last_update_id(max_update_id, store=data, save=False)
        store.save_store(data)
        log(f"[STORE] saved — last_update_id={data['last_update_id']}")
    else:
        log("[DRY-RUN] store and Excel left untouched")

    result = {
        "new_reels": new_reels,
        "already_processed": already_processed,
        "summary": {
            "total_messages_scanned": scanned,
            "new_reels_found": len(new_reels),
            "duplicates_skipped": len(already_processed),
            "draft_requests": draft_requests,
            "skipped_not_allowed": skipped_not_allowed,
            "last_update_id": max_update_id,
            "dry_run": dry_run,
        },
    }
    if errors:
        result["errors"] = errors
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch new Instagram reel links from the Telegram chat.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan only — do not update the store or Excel")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max updates to request (1-100, default 50)")
    args = parser.parse_args()

    try:
        config.require_token()
        result = process(limit=args.limit, dry_run=args.dry_run)
    except Exception as e:
        print(json.dumps({
            "new_reels": [],
            "already_processed": [],
            "summary": {
                "total_messages_scanned": 0,
                "new_reels_found": 0,
                "duplicates_skipped": 0,
                "draft_requests": 0,
                "dry_run": args.dry_run,
            },
            "error": str(e),
        }, indent=2, ensure_ascii=False))
        log(f"[ERROR] {e}")
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
