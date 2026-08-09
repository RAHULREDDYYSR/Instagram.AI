"""
fetch_multiple_creators.py
==========================
Fetches the latest N reels from a list of favourite Instagram creators using
the Apify platform (handles residential-proxy rotation + TLS fingerprinting).

For every reel it:
  1. Downloads the video via yt-dlp  (existing ingest_reel.py logic)
  2. Extracts audio, first-5-second clip, and keyframes
  3. Logs all metadata to Brain/Reels_Log.xlsx
  4. Updates Brain/Creators/_registry.json (de-duplication guard)
  5. Creates / updates a per-creator Obsidian note in Brain/Creators/

Usage:
    uv run System/fetch_multiple_creators.py --max-reels 5
"""

import os
import sys
import json
import time
import datetime
import re

# Force UTF-8 output on Windows so emoji in captions don't crash
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# -- path so we can import sibling scripts ------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from ingest_reel import download_reel, extract_assets

from dotenv import load_dotenv
from apify_client import ApifyClient
import pandas as pd

# -- load env -----------------------------------------------------------------
WORKSPACE     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

APIFY_API_KEY     = os.getenv("APIFY_API_KEY", "")
ASSETS_DIR        = os.path.join(WORKSPACE, "Assets")
REGISTRY_PATH     = os.path.join(WORKSPACE, "Brain", "Creators", "_registry.json")
SPREADSHEET_PATH  = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")
CREATORS_DIR      = os.path.join(WORKSPACE, "Brain", "Creators")

# -- favourite creators -------------------------------------------------------
CREATORS = [
    "brandon_c_clark",
    "lakshyaa.h",
    "beastbrain_",
    "thatzonaguy",
    "doctormikereilly_ifbb",
]

BRANDING_CREATORS = [
    "artgrowthclub",
    "personalbrandlaunch",
    "kallawaymarketing"
]

# apify/instagram-reel-scraper returns per-reel records:
# likesCount, commentsCount, videoUrl, caption, timestamp, shortCode, etc.
APIFY_ACTOR = "apify/instagram-reel-scraper"

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(CREATORS_DIR, exist_ok=True)


# -- registry helpers ---------------------------------------------------------
def load_registry() -> dict:
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"creators": []}


def save_registry(registry: dict) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def get_creator_record(registry: dict, username: str) -> dict | None:
    for c in registry["creators"]:
        if c["username"].lower() == username.lower():
            return c
    return None


def mark_processed(registry: dict, username: str, shortcodes: list[str]) -> None:
    rec = get_creator_record(registry, username)
    if not rec:
        rec = {
            "username": username,
            "processed_reels": [],
            "added_on": datetime.datetime.now().isoformat(),
        }
        registry["creators"].append(rec)
    rec["processed_reels"] = list(set(rec["processed_reels"] + shortcodes))
    save_registry(registry)


# -- spreadsheet helper -------------------------------------------------------
def log_to_spreadsheet(row: dict) -> None:
    df_new = pd.DataFrame([row])
    if os.path.exists(SPREADSHEET_PATH):
        try:
            df_old = pd.read_excel(SPREADSHEET_PATH)
            df = pd.concat([df_old, df_new], ignore_index=True)
        except Exception:
            df = df_new
    else:
        df = df_new

    with pd.ExcelWriter(SPREADSHEET_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reels Log")
        ws = writer.sheets["Reels Log"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    print(f"   [LOGGED] {os.path.basename(SPREADSHEET_PATH)}")


# -- Obsidian creator note helper ---------------------------------------------
def update_creator_note(username: str, full_name: str, followers: int,
                         shortcodes: list[str]) -> None:
    note_path = os.path.join(CREATORS_DIR, f"{username}.md")
    existing_reels = []
    if os.path.exists(note_path):
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
        for m in re.findall(r"\[\[([A-Za-z0-9_\-]+)\]\]", content):
            existing_reels.append(m)

    all_reels  = list(dict.fromkeys(existing_reels + shortcodes))
    reel_links = "\n".join(f"- [[{sc}]]" for sc in all_reels)

    note = f"""# Creator: {full_name or username}

- **Username:** @{username}
- **Followers:** {followers:,}
- **Last Updated:** {datetime.datetime.now().strftime('%Y-%m-%d')}

## Known Reels
{reel_links}

*Links:* [[Playbook]], [[Pattern_Library]]
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    print(f"   [NOTE] Updated Brain/Creators/{username}.md")


# -- extract shortcode from URL -----------------------------------------------
def shortcode_from_url(url: str) -> str:
    m = re.search(r"/(reel|p)/([A-Za-z0-9_\-]+)", url)
    return m.group(2) if m else url.rstrip("/").split("/")[-1]


# -- main ---------------------------------------------------------------------
def main(max_reels: int = 5, category: str = "NICHE") -> None:
    if not APIFY_API_KEY:
        print("[ERROR] APIFY_API_KEY not set in .env")
        sys.exit(1)

    client   = ApifyClient(APIFY_API_KEY)
    registry = load_registry()

    all_summary = []

    target_creators = BRANDING_CREATORS if category == "BRANDING" else CREATORS

    for username in target_creators:
        print(f"\n{'='*60}")
        print(f"[CREATOR] @{username}")
        print(f"{'='*60}")

        rec          = get_creator_record(registry, username)
        already_done = set(rec["processed_reels"]) if rec else set()

        # 1. Apify: scrape reel list ------------------------------------------
        run_input = {
            "username":     [username],
            "resultsLimit": max_reels * 3,   # over-fetch so we can skip dupes
        }

        try:
            print(f"   [APIFY] Running actor {APIFY_ACTOR} ...")
            run = client.actor(APIFY_ACTOR).call(run_input=run_input)
        except Exception as e:
            print(f"   [ERROR] Apify run failed: {e}")
            continue

        # apify-client v3 returns a Run Pydantic model
        dataset_id = run.default_dataset_id
        items      = list(client.dataset(dataset_id).iterate_items())
        print(f"   [APIFY] Returned {len(items)} items from dataset {dataset_id}")

        if not items:
            print(f"   [WARN] No items returned for @{username} — skipping")
            continue

        # Debug: show available keys from first item
        print(f"   [DEBUG] Available keys: {list(items[0].keys())[:12]}")

        new_shortcodes  = []
        processed_count = 0

        for item in items:
            if processed_count >= max_reels:
                break

            # Normalise field names — keys confirmed from Apify actor debug output:
            # id, type, shortCode, caption, hashtags, mentions, url, commentsCount,
            # dimensionsHeight, dimensionsWidth, images, videoUrl, likesCount,
            # timestamp, ownerFullName, ownerFollowersCount (may vary by plan)
            shortcode = (item.get("shortCode") or
                         item.get("shortcode") or
                         item.get("id") or "")
            video_url = (item.get("videoUrl") or
                         item.get("url") or "")
            if not shortcode and video_url:
                shortcode = shortcode_from_url(video_url)

            if not shortcode:
                print("   [WARN] Could not determine shortcode, skipping item")
                continue

            reel_url  = f"https://www.instagram.com/reel/{shortcode}/"
            caption   = item.get("caption") or item.get("text") or ""
            pub_date  = (item.get("timestamp") or
                         item.get("taken_at_timestamp") or
                         item.get("date") or "")
            likes     = item.get("likesCount") or item.get("likes") or item.get("like_count") or 0
            comments  = item.get("commentsCount") or item.get("comments") or item.get("comment_count") or 0
            shares    = item.get("sharesCount") or item.get("shares") or item.get("reshare_count") or ""
            full_name = (item.get("ownerFullName") or
                         item.get("ownerUsername") or
                         item.get("owner", {}).get("full_name") or username)
            followers = (item.get("ownerFollowersCount") or
                         item.get("owner", {}).get("follower_count") or 0)

            if shortcode in already_done:
                print(f"   [SKIP] {shortcode} already processed")
                continue

            print(f"\n   [REEL] {shortcode}")
            cap_preview = caption[:70] + "..." if len(caption) > 70 else caption
            print(f"   [CAP]  {cap_preview}")
            print(f"   [STAT] Likes: {likes}  Comments: {comments}")

            # 2. Download + extract assets ------------------------------------
            video_path, video_id = download_reel(reel_url, ASSETS_DIR)

            assets_path = ""
            audio_path  = ""
            if video_path and os.path.exists(video_path):
                try:
                    extract_assets(video_path, ASSETS_DIR, video_id)
                    assets_path = os.path.join(ASSETS_DIR, video_id)
                    audio_path  = os.path.join(ASSETS_DIR, f"{video_id}.wav")
                    print(f"   [OK]   Assets extracted -> {video_id}")
                except Exception as exc:
                    print(f"   [WARN] Asset extraction error: {exc}")
            else:
                print(f"   [WARN] Download failed, logging metadata only")

            new_shortcodes.append(shortcode)
            processed_count += 1

            # 3. Log to spreadsheet ------------------------------------------
            row = {
                "Creator Name":     full_name,
                "Username":         f"@{username}",
                "Category":         category,
                "Reel Link":        reel_url,
                "Video URL":        video_url,
                "Publication Date": str(pub_date),
                "Like Count":       likes,
                "Comments Count":   comments,
                "Shares Count":     shares,
                "Caption":          caption,
                "Topic/Summary":    caption[:120] + "..." if len(caption) > 120 else caption,
                "Audio Path":       audio_path,
                "Assets Path":      assets_path,
                "Processed Date":   datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Status":           "SCRAPED",
            }
            log_to_spreadsheet(row)
            all_summary.append(row)
            time.sleep(1)

        # 4. Update registry + Brain note ------------------------------------
        if new_shortcodes:
            mark_processed(registry, username, new_shortcodes)
            _fn  = items[0].get("ownerFullName") or items[0].get("ownerUsername") or username
            _fol = items[0].get("ownerFollowersCount") or 0
            update_creator_note(username, _fn, _fol, new_shortcodes)
            print(f"\n   [DONE] {len(new_shortcodes)} reels processed for @{username}")
        else:
            print(f"\n   [INFO] No new reels for @{username}")

    # Final summary -----------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"[COMPLETE] All creators processed.")
    print(f"[TOTAL]    {len(all_summary)} rows logged")
    print(f"[FILE]     {SPREADSHEET_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-reels", type=int, default=5)
    parser.add_argument("--category", choices=["NICHE", "BRANDING"], default="NICHE")
    args = parser.parse_args()
    main(max_reels=args.max_reels, category=args.category)
