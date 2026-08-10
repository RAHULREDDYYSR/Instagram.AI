"""
record_outcome.py — append an Instagram performance snapshot.

The log is deliberately append-only and separate from Reels_Log.xlsx. It can
capture real outcome data later without making the ingestion writers rewrite a
larger shared workbook.

Usage:
    uv run System/record_outcome.py --shortcode ABC123 --views 1000 \
        --likes 80 --saves 20 --captured-at 2026-08-10T12:00:00
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys


WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTCOMES_DIR = os.path.join(WORKSPACE, "Brain", "Outcomes")
OUTCOMES_PATH = os.path.join(OUTCOMES_DIR, "reel_outcomes.jsonl")

NONNEGATIVE_FIELDS = (
    "views", "reach", "replays", "likes", "comments", "saves", "shares",
    "follows", "follower_count",
)
RATE_FIELDS = ("completion_rate",)


def _number(value: str | None, name: str) -> int | float | None:
    if value is None:
        return None
    try:
        parsed = float(value) if "." in value else int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed < 0:
        raise ValueError(f"{name} cannot be negative")
    return parsed


def append_outcome(values: dict) -> str:
    shortcode = str(values.get("shortcode", "")).strip()
    if not shortcode:
        raise ValueError("shortcode is required")

    record = {
        "recorded_at": values.get("recorded_at") or dt.datetime.now().isoformat(timespec="seconds"),
        "shortcode": shortcode,
    }
    for key, value in values.items():
        if key in ("shortcode", "recorded_at") or value is None:
            continue
        record[key] = value

    os.makedirs(OUTCOMES_DIR, exist_ok=True)
    # A single append is atomic enough for normal one-record CLI use and keeps
    # the file append-only. Each line remains independently recoverable.
    with open(OUTCOMES_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    return OUTCOMES_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append an Instagram outcome snapshot")
    parser.add_argument("--shortcode", required=True)
    parser.add_argument("--script-id", default=None)
    parser.add_argument("--published-at", default=None)
    parser.add_argument("--captured-at", dest="recorded_at", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--note", default=None)
    for field in NONNEGATIVE_FIELDS:
        parser.add_argument(f"--{field.replace('_', '-')}", default=None)
    for field in RATE_FIELDS:
        parser.add_argument(f"--{field.replace('_', '-')}", default=None)
    args = parser.parse_args(argv)

    try:
        values = {
            "shortcode": args.shortcode,
            "script_id": args.script_id,
            "published_at": args.published_at,
            "recorded_at": args.recorded_at,
            "source": args.source,
            "note": args.note,
        }
        for field in NONNEGATIVE_FIELDS:
            values[field] = _number(getattr(args, field), field)
        for field in RATE_FIELDS:
            rate = _number(getattr(args, field), field)
            if rate is not None and rate > 100:
                raise ValueError(f"{field} must be between 0 and 100")
            values[field] = rate
        path = append_outcome(values)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, "path": path, "shortcode": args.shortcode}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
