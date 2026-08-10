"""
register_oneoff.py  —  register a single reel URL in Brain/Reels_Log.xlsx.
===========================================================================
Adds a row for the URL's shortcode with:

    Category    NICHE (override with --category)
    Reel Link   the given URL
    Status      SCRAPED
    Source      ONE_OFF

The pipeline then picks the row up via the normal scrape → process → analyze
chain (Status=SCRAPED). Existing shortcodes are deduplicated safely — the row
is never duplicated. All pre-existing workbook columns (incl. Source) are
preserved via the shared styled Excel I/O from process_reels.py.

Usage:
    uv run System/register_oneoff.py https://www.instagram.com/reel/AbC123/
    uv run System/register_oneoff.py <url> --category BRANDING
"""

import os
import sys
import re
import json
import argparse
import datetime
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

# ---------------------------------------------------------------------------
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from process_reels import load_sheet, save_sheet, SPREADSHEET_PATH
from workspace_lock import locked

SOURCE_ONE_OFF = "ONE_OFF"
DEFAULT_CATEGORY = "NICHE"

SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


# ---------------------------------------------------------------------------
def shortcode_from_url(url: str) -> str:
    """Extract the shortcode from /reel/, /reels/ or /p/ URLs ('' on failure)."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    for key in ("reel", "reels", "p"):
        if key in parts:
            idx = parts.index(key)
            if idx + 1 < len(parts):
                candidate = parts[idx + 1]
                if SHORTCODE_RE.match(candidate):
                    return candidate
    m = re.search(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


@locked
def register(url: str, category: str = DEFAULT_CATEGORY) -> tuple[str, bool]:
    """Register the URL; returns (shortcode, newly_registered)."""
    shortcode = shortcode_from_url(url)
    if not shortcode:
        raise ValueError(f"could not extract a valid Instagram shortcode from URL: {url!r}")

    df = load_sheet()
    codes = df["Shortcode"].astype(str).str.strip()
    exists = (codes == shortcode).any()

    if exists:
        return shortcode, False

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = url[:120] + "..." if len(url) > 120 else url
    row = {col: "" for col in df.columns}
    row["Shortcode"]        = shortcode
    row["Category"]         = category
    row["Reel Link"]        = url
    row["Topic/Summary"]    = summary
    row["Scraped Date"]     = now
    row["Status"]           = "SCRAPED"
    if "Source" in row:
        row["Source"] = SOURCE_ONE_OFF

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_sheet(df)
    return shortcode, True


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Register a single Instagram reel URL in Brain/Reels_Log.xlsx "
                    "with Source=ONE_OFF, Status=SCRAPED.")
    parser.add_argument("url", help="Instagram reel/post URL")
    parser.add_argument("--category", choices=["NICHE", "BRANDING"],
                        default=DEFAULT_CATEGORY, help="Category for the new row")
    parser.add_argument("--json", action="store_true",
                        help="Print a machine-readable result")
    args = parser.parse_args(argv)

    try:
        shortcode, newly = register(args.url, category=args.category)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 2

    if args.json:
        print(json.dumps({
            "shortcode": shortcode,
            "newly_registered": newly,
            "category": args.category,
            "status": "SCRAPED",
            "source": SOURCE_ONE_OFF,
            "spreadsheet": SPREADSHEET_PATH,
        }, indent=2))
    else:
        verb = "registered" if newly else "already present (no change)"
        print(f"[REGISTER] {shortcode}  —  {verb}  (Category={args.category}, "
              f"Status=SCRAPED, Source={SOURCE_ONE_OFF})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
