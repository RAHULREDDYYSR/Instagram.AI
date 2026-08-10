"""
scrape.py  —  STEP 1: Metadata only, no downloads.
=====================================================
Invokes Apify to collect reel metadata and appends new rows to
Brain/Reels_Log.xlsx. Creator lists live in System/creators.json:

  --category NICHE     (default) favourite niche creators (fitness/lifestyle)
  --category BRANDING  personal-branding / business-growth accounts
  --category ALL       both lists in one run

Apify actor runs execute IN PARALLEL (one run per creator, 4 threads).
All Excel / registry / note writes happen on the main thread afterwards.
Reels already present in the sheet are skipped automatically.

Usage:
    uv run System/scrape.py                          # scrape niche creators
    uv run System/scrape.py --category BRANDING      # scrape branding accounts
    uv run System/scrape.py --category ALL           # everything
    uv run System/scrape.py --max-reels 10           # fetch more per creator
    uv run System/scrape.py --username viralish      # single creator only
"""

import os, sys, json, re, datetime, argparse, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from apify_client import ApifyClient
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from workspace_lock import atomic_path, locked

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

APIFY_API_KEY    = os.getenv("APIFY_API_KEY", "")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")
REGISTRY_PATH    = os.path.join(WORKSPACE, "Brain", "Creators", "_registry.json")
CREATORS_DIR     = os.path.join(WORKSPACE, "Brain", "Creators")
APIFY_ACTOR      = "apify/instagram-reel-scraper"

# ── Creator lists ────────────────────────────────────────────────────────────
# Single source of truth: System/creators.json (edit that file, never here).
# NICHE:    personal content style reference — hooks, visuals, topic ideas
# BRANDING: script structure, CTA strategy, audience targeting, personal brand
CREATORS_PATH = os.path.join(os.path.dirname(__file__), "creators.json")

def load_creators() -> dict:
    with open(CREATORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Fixed column schema ──────────────────────────────────────────────────────
COLUMNS = [
    "Shortcode",
    "Category",          # NICHE | BRANDING
    "Creator Name",
    "Username",
    "Reel Link",
    "Video URL",
    "Publication Date",
    "Like Count",
    "Comments Count",
    "Shares Count",
    "Caption",
    "Topic/Summary",
    "Scraped Date",
    "Status",            # SCRAPED | PROCESSED | FAILED
    "Processed Date",
    "Brain Note Path",
    # Keep source tracking for Telegram and registered one-off reels.
    "Source",
]

os.makedirs(CREATORS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
def load_sheet() -> pd.DataFrame:
    if os.path.exists(SPREADSHEET_PATH):
        try:
            df = pd.read_excel(SPREADSHEET_PATH)
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            # Keep columns introduced by other ingestion paths instead of
            # silently dropping Source or future outcome metadata.
            extras = [col for col in df.columns if col not in COLUMNS]
            return df[COLUMNS + extras]
        except Exception as exc:
            raise RuntimeError(
                f"Could not read {SPREADSHEET_PATH}; refusing to replace it: {exc}"
            ) from exc
    return pd.DataFrame(columns=COLUMNS)


def save_sheet(df: pd.DataFrame) -> None:
    """Write the styled sheet atomically.

    Uses a sibling temp file with an .xlsx suffix (pandas/openpyxl reject
    other extensions) and os.replace, so a failed write never truncates a
    valid workbook.
    """
    directory = os.path.dirname(SPREADSHEET_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".reels_log_", suffix=".xlsx", dir=directory)
    os.close(fd)
    try:
        with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Reels Log")
            ws = writer.sheets["Reels Log"]
            # Style: freeze top row, bold headers
            from openpyxl.styles import Font, PatternFill, Alignment
            header_row = ws[1]
            for cell in header_row:
                cell.font      = Font(bold=True, color="FFFFFF")
                cell.fill      = PatternFill("solid", fgColor="1F3864")
                cell.alignment = Alignment(horizontal="center")
            ws.freeze_panes = "A2"
            # Colour-code Category column (col B = index 2)
            for row in ws.iter_rows(min_row=2):
                cat_cell = row[1]  # Category column
                if str(cat_cell.value).upper() == "BRANDING":
                    cat_cell.fill = PatternFill("solid", fgColor="FFE699")
                elif str(cat_cell.value).upper() == "NICHE":
                    cat_cell.fill = PatternFill("solid", fgColor="C6EFCE")
            # Colour-code Status column (col N = index 13)
            for row in ws.iter_rows(min_row=2):
                st_cell = row[13]  # Status column
                val = str(st_cell.value).upper()
                if val == "PROCESSED":
                    st_cell.fill = PatternFill("solid", fgColor="C6EFCE")
                elif val == "SCRAPED":
                    st_cell.fill = PatternFill("solid", fgColor="FFEB9C")
                elif val == "FAILED":
                    st_cell.fill = PatternFill("solid", fgColor="FFC7CE")
            # Auto column widths
            for col in ws.columns:
                max_len = max((len(str(cell.value or "")) for cell in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 80)
        os.replace(temp_path, SPREADSHEET_PATH)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    print(f"   [SAVED] {SPREADSHEET_PATH}")


def load_registry() -> dict:
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"creators": []}


def save_registry(reg: dict) -> None:
    """Write _registry.json atomically — a failed write never truncates it."""
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with atomic_path(REGISTRY_PATH) as temp_path:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    print(f"   [REGISTRY] saved {REGISTRY_PATH}")


def get_creator_record(reg: dict, username: str):
    for c in reg["creators"]:
        if c["username"].lower() == username.lower():
            return c
    return None


def mark_scraped(reg: dict, username: str, shortcodes: list,
                 save: bool = True) -> None:
    rec = get_creator_record(reg, username)
    if not rec:
        rec = {"username": username, "category": "",
               "scraped_reels": [], "processed_reels": [],
               "added_on": datetime.datetime.now().isoformat()}
        reg["creators"].append(rec)
    existing = set(rec.get("scraped_reels", []))
    rec["scraped_reels"] = list(existing | set(shortcodes))
    if save:
        save_registry(reg)


def shortcode_from_url(url: str) -> str:
    m = re.search(r"/(reel|p)/([A-Za-z0-9_\-]+)", url)
    return m.group(2) if m else url.rstrip("/").split("/")[-1]


def update_creator_note(username: str, full_name: str, followers: int,
                        shortcodes: list, category: str) -> None:
    note_path = os.path.join(CREATORS_DIR, f"{username}.md")
    existing  = []
    if os.path.exists(note_path):
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
        existing = re.findall(r"\[\[([A-Za-z0-9_\-]+)\]\]", content)
    all_sc     = list(dict.fromkeys(existing + shortcodes))
    reel_links = "\n".join(f"- [[{sc}]]" for sc in all_sc)

    tag = "Personal Branding / Growth Strategy" if category == "BRANDING" else "Niche Content"
    note = f"""# Creator: {full_name or username}

- **Username:** @{username}
- **Category:** {tag}
- **Followers:** {followers:,}
- **Last Updated:** {datetime.datetime.now().strftime('%Y-%m-%d')}

## Known Reels
{reel_links}

*Links:* [[Playbook]], [[Pattern_Library]], [[Script_Framework_Library]]
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    print(f"   [NOTE] Brain/Creators/{username}.md updated")


# ---------------------------------------------------------------------------
def fetch_creator_items(client: ApifyClient, username: str, max_reels: int):
    """Blocking Apify call for one creator — runs inside the thread pool."""
    run_input = {"username": [username], "resultsLimit": max_reels * 3}
    run   = client.actor(APIFY_ACTOR).call(run_input=run_input)
    items = list(client.dataset(run.default_dataset_id).iterate_items())
    return items


@locked
def main(category: str | None = None, max_reels: int = 5, workers: int = 4,
         username: str = "") -> None:
    if not APIFY_API_KEY:
        print("[ERROR] APIFY_API_KEY not set in .env")
        sys.exit(1)

    # Resolve effective category for display + search scope
    if category is None:
        effective_category = "ALL" if username else "NICHE"
    else:
        effective_category = category

    all_creators = load_creators()
    targets = []

    if username:
        # When --username is given, auto-detect the creator's list across
        # both categories (unless --category explicitly restricts the search).
        search_cats = ["NICHE", "BRANDING"] if effective_category == "ALL" else [effective_category]
        handle = username.lstrip("@").lower()
        for cat in search_cats:
            for u in all_creators.get(cat, []):
                if u.lower() == handle:
                    targets.append((cat, u))
                    break
        if not targets:
            scope = " or ".join(search_cats)
            print(f"[ERROR] @{handle} not found in {scope} of {CREATORS_PATH}")
            sys.exit(1)
    else:
        if effective_category in ("NICHE", "ALL"):
            targets += [("NICHE", u) for u in all_creators.get("NICHE", [])]
        if effective_category in ("BRANDING", "ALL"):
            targets += [("BRANDING", u) for u in all_creators.get("BRANDING", [])]
        if not targets:
            print(f"[ERROR] No creators found for category {effective_category} in {CREATORS_PATH}")
            sys.exit(1)

    print(f"\n[MODE]    Category = {effective_category}")
    if username:
        print(f"[FILTER]  Only @{username.lstrip('@')}")
    print(f"[TARGET]  {len(targets)} creators: {', '.join('@' + u for _, u in targets)}")
    print(f"[PARALLEL] {workers} Apify runs at a time")

    client  = ApifyClient(APIFY_API_KEY)
    df      = load_sheet()
    reg     = load_registry()

    existing_shortcodes = set(df["Shortcode"].dropna().astype(str).tolist())
    total_new = 0
    registry_dirty = False

    # 1. Fire all Apify runs in parallel (network-bound) ---------------------
    fetched = {}  # username -> (category, items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_creator_items, client, username, max_reels): (cat, username)
            for cat, username in targets
        }
        for fut in as_completed(futures):
            cat, username = futures[fut]
            try:
                items = fut.result()
                fetched[username] = (cat, items)
                print(f"   [APIFY] @{username}: {len(items)} items returned")
            except Exception as e:
                print(f"   [ERROR] @{username}: {e}")

    # 2. Process results sequentially (dedupe, rows, registry, notes) --------
    for cat, username in targets:
        if username not in fetched:
            continue
        items = fetched[username][1]

        print(f"\n{'='*60}")
        print(f"[SCRAPE] @{username}  [{cat}]")
        print(f"{'='*60}")

        if not items:
            print(f"   [WARN] No items — skipping @{username}")
            continue

        new_rows       = []
        new_shortcodes = []

        for item in items:
            if len(new_rows) >= max_reels:
                break

            shortcode = (item.get("shortCode") or item.get("shortcode") or item.get("id") or "")
            video_url = item.get("videoUrl") or item.get("url") or ""
            if not shortcode and video_url:
                shortcode = shortcode_from_url(video_url)
            if not shortcode:
                continue

            if shortcode in existing_shortcodes:
                print(f"   [SKIP] {shortcode} already in sheet")
                continue

            caption   = item.get("caption") or item.get("text") or ""
            pub_date  = (item.get("timestamp") or item.get("taken_at_timestamp") or
                         item.get("date") or "")
            likes     = (item.get("likesCount") or item.get("likes") or
                         item.get("like_count") or 0)
            comments  = (item.get("commentsCount") or item.get("comments") or
                         item.get("comment_count") or 0)
            shares    = (item.get("sharesCount") or item.get("shares") or
                         item.get("reshare_count") or "")
            full_name = (item.get("ownerFullName") or item.get("ownerUsername") or
                         item.get("owner", {}).get("full_name") or username)
            followers = (item.get("ownerFollowersCount") or
                         item.get("owner", {}).get("follower_count") or 0)
            reel_url  = f"https://www.instagram.com/reel/{shortcode}/"
            summary   = caption[:120] + "..." if len(caption) > 120 else caption

            row = {
                "Shortcode":        shortcode,
                "Category":         cat,
                "Creator Name":     full_name,
                "Username":         f"@{username}",
                "Reel Link":        reel_url,
                "Video URL":        video_url,
                "Publication Date": str(pub_date),
                "Like Count":       likes,
                "Comments Count":   comments,
                "Shares Count":     shares,
                "Caption":          caption,
                "Topic/Summary":    summary,
                "Scraped Date":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Status":           "SCRAPED",
                "Processed Date":   "",
                "Brain Note Path":  "",
            }
            new_rows.append(row)
            new_shortcodes.append(shortcode)
            existing_shortcodes.add(shortcode)
            print(f"   [NEW]  {shortcode}  Likes:{likes}  {summary[:55]}...")

        if new_rows:
            df = pd.concat([df, pd.DataFrame(new_rows, columns=COLUMNS)],
                           ignore_index=True)
            # Batch registry updates in memory; one atomic write at the end.
            mark_scraped(reg, username, new_shortcodes, save=False)
            registry_dirty = True
            _fn  = items[0].get("ownerFullName") or username
            _fol = items[0].get("ownerFollowersCount") or 0
            update_creator_note(username, _fn, _fol, new_shortcodes, cat)
            total_new += len(new_rows)
            print(f"\n   [DONE] {len(new_rows)} new reels scraped for @{username}")
        else:
            print(f"\n   [INFO] No new reels for @{username}")

    if registry_dirty:
        save_registry(reg)

    save_sheet(df)

    # Print summary by category
    print(f"\n{'='*60}")
    print(f"[COMPLETE] {total_new} new {category} reels added.")
    if not df.empty and "Category" in df.columns:
        for cat in ["NICHE", "BRANDING"]:
            sub = df[df["Category"].astype(str).str.upper() == cat]
            sc  = len(sub[sub["Status"].astype(str).str.upper() == "SCRAPED"])
            pr  = len(sub[sub["Status"].astype(str).str.upper() == "PROCESSED"])
            print(f"  {cat:10s}  Total:{len(sub)}  SCRAPED:{sc}  PROCESSED:{pr}")
    print(f"[FILE]    {SPREADSHEET_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=["NICHE", "BRANDING", "ALL"],
                        default=None,
                        help="Which creator list to scrape (default: NICHE, or ALL when --username is used)")
    parser.add_argument("--max-reels", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel Apify runs (one per creator)")
    parser.add_argument("--username", default="",
                        help="Scrape only this creator handle (must exist in creators.json)")
    args = parser.parse_args()
    cat_arg = args.category.upper() if args.category else None
    main(category=cat_arg, max_reels=args.max_reels,
         workers=args.workers, username=args.username)
