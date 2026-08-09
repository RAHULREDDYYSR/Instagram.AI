"""
process_reels.py  —  STEP 2: Download, extract, update Brain. KEEP assets.
================================================================================
Reads all rows with Status="SCRAPED" from Brain/Reels_Log.xlsx and for each:
  1. Downloads the video via yt-dlp                       (in parallel, 3 threads)
  2. Extracts audio (.wav), 5-second hook clip, and keyframes
  3. Creates a category-specific Brain note:
       NICHE    -> Brain/Reels/<shortcode>.md      (hook, visuals, pacing)
       BRANDING -> Brain/Branding/<shortcode>.md   (script structure, CTA, audience)
  4. KEEPS keyframes (.jpg), .wav, and .txt in Assets/ — those are the
     only inputs the analysis agents (video-analysis / audio-analysis
     skills) actually read. The full .mp4 is pruned immediately after
     extraction to keep storage lean.
  5. Updates the Excel row: Status="PROCESSED", Processed Date, Brain Note Path
  6. Chains into transcribe.py (Whisper) so every reel gets Assets/<id>.txt

Assets are deleted LATER by System/cleanup_assets.py once a reel reaches
Status=ANALYZED. Pass --delete-assets to restore the old immediate-deletion
behavior (NOT recommended — analysis then becomes impossible).

Usage:
    uv run System/process_reels.py                         # all pending
    uv run System/process_reels.py --category NICHE        # only niche
    uv run System/process_reels.py --category BRANDING     # only branding
    uv run System/process_reels.py --limit 5               # process N at a time
    uv run System/process_reels.py --workers 4             # download threads
    uv run System/process_reels.py --skip-transcribe       # no Whisper step
    uv run System/process_reels.py --username viralish     # only this creator
"""

import os, sys, json, re, glob, datetime, argparse, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from ingest_reel import download_reel, extract_assets

from dotenv import load_dotenv
import pandas as pd

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

ASSETS_DIR       = os.path.join(WORKSPACE, "Assets")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")
REELS_BRAIN_DIR  = os.path.join(WORKSPACE, "Brain", "Reels")      # NICHE
BRAND_BRAIN_DIR  = os.path.join(WORKSPACE, "Brain", "Branding")   # BRANDING
REGISTRY_PATH    = os.path.join(WORKSPACE, "Brain", "Creators", "_registry.json")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(REELS_BRAIN_DIR, exist_ok=True)
os.makedirs(BRAND_BRAIN_DIR, exist_ok=True)

COLUMNS = [
    "Shortcode", "Category", "Creator Name", "Username", "Reel Link", "Video URL",
    "Publication Date", "Like Count", "Comments Count", "Shares Count",
    "Caption", "Topic/Summary", "Scraped Date", "Status",
    "Processed Date", "Brain Note Path",
]

# ---------------------------------------------------------------------------
def load_sheet() -> pd.DataFrame:
    if not os.path.exists(SPREADSHEET_PATH):
        print("[ERROR] Reels_Log.xlsx not found. Run 'scrape' first.")
        sys.exit(1)
    df = pd.read_excel(SPREADSHEET_PATH)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


def save_sheet(df: pd.DataFrame) -> None:
    with pd.ExcelWriter(SPREADSHEET_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reels Log")
        ws = writer.sheets["Reels Log"]
        from openpyxl.styles import Font, PatternFill, Alignment
        header_row = ws[1]
        for cell in header_row:
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="1F3864")
            cell.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
        for row in ws.iter_rows(min_row=2):
            cat_cell = row[1]
            if str(cat_cell.value).upper() == "BRANDING":
                cat_cell.fill = PatternFill("solid", fgColor="FFE699")
            elif str(cat_cell.value).upper() == "NICHE":
                cat_cell.fill = PatternFill("solid", fgColor="C6EFCE")
            st_cell = row[13]
            val = str(st_cell.value).upper()
            if val == "PROCESSED":
                st_cell.fill = PatternFill("solid", fgColor="C6EFCE")
            elif val == "SCRAPED":
                st_cell.fill = PatternFill("solid", fgColor="FFEB9C")
            elif val == "FAILED":
                st_cell.fill = PatternFill("solid", fgColor="FFC7CE")
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 80)


# ---------------------------------------------------------------------------
def delete_reel_assets(video_id: str) -> int:
    pattern = os.path.join(ASSETS_DIR, f"{video_id}*")
    files   = glob.glob(pattern)
    for f in files:
        try:
            os.remove(f)
        except Exception as e:
            print(f"   [WARN] Could not delete {f}: {e}")
    return len(files)


# ---------------------------------------------------------------------------
def create_niche_note(shortcode: str, row: dict) -> str:
    """Brain/Reels/<sc>.md — focus: hook, visuals, pacing, topic ideas."""
    note_path = os.path.join(REELS_BRAIN_DIR, f"{shortcode}.md")
    creator   = str(row.get("Creator Name", "") or "")
    username  = str(row.get("Username", "") or "").strip()
    reel_url  = str(row.get("Reel Link", "") or "")
    caption   = str(row.get("Caption", "") or "")
    pub_date  = str(row.get("Publication Date", "") or "")
    likes     = row.get("Like Count", 0)
    comments  = row.get("Comments Count", 0)
    shares    = str(row.get("Shares Count", "") or "")
    now       = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    note = f"""# Reel: {shortcode}
**Category:** NICHE

## Metadata
| Field | Value |
|---|---|
| Creator | {creator} ({username}) |
| URL | {reel_url} |
| Published | {pub_date} |
| Likes | {likes} |
| Comments | {comments} |
| Shares | {shares} |
| Processed | {now} |

## Caption
{caption}

---

## Visual Analysis
> *Run visual_agent on keyframes + 5s clip to populate.*

### Opening Shot (0–1s)
- **Camera Angle:**
- **Motion:**
- **Subject:**

### Hook Archetype
- [ ] Action Hook
- [ ] Authority Hook
- [ ] Curiosity Hook
- [ ] Aesthetic Hook

### Editing Style
- **Pattern Interrupts:**
- **Scene Transitions:**
- **Visual Pacing:**

### Text Overlays / Captions
- **Hook Text:**
- **Caption Style:**

---

## Audio Analysis
> *Run audio_agent on .wav file to populate.*

### Hook (0–3s)
**First words:**

### Narrative Structure
- **Story Framework:**
- **Payoff/Value:**
- **CTA:**

### Vocal Delivery
- **Tone:**
- **Energy:**
- **Words/sec:**

---

## Retention Psychology
> *Run retention_agent to populate.*

| Factor | Score (1–10) | Notes |
|---|---|---|
| Curiosity | | |
| Open Loops | | |
| Identity Trigger | | |
| Novelty | | |
| Emotion | | |
| Story Tension | | |

---

## Pattern Tags
_Add tags after analysis: #hook-type #editing-style #topic_

## Links
- Creator: [[{username.lstrip('@') if username else 'unknown'}]]
- [[Pattern_Library]]
- [[Hook_Database]]
- [[Playbook]]
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    return note_path


# ---------------------------------------------------------------------------
def create_branding_note(shortcode: str, row: dict) -> str:
    """Brain/Branding/<sc>.md — focus: script structure, CTA, audience targeting."""
    note_path = os.path.join(BRAND_BRAIN_DIR, f"{shortcode}.md")
    creator   = str(row.get("Creator Name", "") or "")
    username  = str(row.get("Username", "") or "").strip()
    reel_url  = str(row.get("Reel Link", "") or "")
    caption   = str(row.get("Caption", "") or "")
    pub_date  = str(row.get("Publication Date", "") or "")
    likes     = row.get("Like Count", 0)
    comments  = row.get("Comments Count", 0)
    shares    = str(row.get("Shares Count", "") or "")
    now       = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    note = f"""# Branding Reel: {shortcode}
**Category:** BRANDING / PERSONAL BRAND STRATEGY

## Metadata
| Field | Value |
|---|---|
| Creator | {creator} ({username}) |
| URL | {reel_url} |
| Published | {pub_date} |
| Likes | {likes} |
| Comments | {comments} |
| Shares | {shares} |
| Processed | {now} |

## Caption
{caption}

---

## Script Structure Analysis
> *Run audio_agent + visual_agent to populate.*

### Framework Used
- [ ] Problem → Agitate → Solution (PAS)
- [ ] Hook → Story → Lesson → CTA
- [ ] Listicle (e.g. "3 things you...")
- [ ] Contrarian Take
- [ ] Authority Statement
- [ ] Before → After
- [ ] Other:

### Opening Hook (0–3s)
- **Hook Type:**
- **First sentence:**
- **Why it works:**

### Body / Value Delivery
- **Core message:**
- **Proof / social proof used:**
- **Pacing (fast/medium/slow):**
- **Edu vs Promotional ratio:**

### CTA (Call to Action)
- **CTA type:** (Follow / DM / Comment / Share / Save / Link in bio)
- **CTA exact words:**
- **CTA placement:** (start / middle / end)
- **CTA strength (1–10):**

---

## Audience Targeting Signals
> *What signals in this reel attract the right audience?*

- **Pain point addressed:**
- **Aspiration tapped:**
- **Who this speaks to:**
- **Identity trigger:**
- **Language / vocabulary style:**

---

## Tone & Delivery
- **Tone:** (Educational / Inspirational / Direct / Conversational / Authority)
- **Energy level:**
- **Confidence signals:**
- **Vulnerability used:** (Y/N)

---

## Personal Brand Positioning
- **What authority is being demonstrated:**
- **Trust-building mechanism used:**
- **Niche clarity (1–10):**
- **Relatability factor:**

---

## Reusable Frameworks Extracted
> *Patterns that can be applied to our own scripts*

### Script Template Extracted
```
[HOOK]:
[PROBLEM/CONTEXT]:
[VALUE/STORY]:
[LESSON/INSIGHT]:
[CTA]:
```

### Transferable Tactics
-
-
-

---

## Links
- Creator: [[{username.lstrip('@') if username else 'unknown'}]]
- [[Script_Framework_Library]]
- [[Personal_Brand_Playbook]]
- [[Audience_Targeting_Guide]]
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    return note_path


# ---------------------------------------------------------------------------
def create_brain_note(shortcode: str, row: dict) -> str:
    category = str(row.get("Category", "NICHE")).upper()
    if category == "BRANDING":
        return create_branding_note(shortcode, row)
    return create_niche_note(shortcode, row)


# ---------------------------------------------------------------------------
def fetch_media(row: pd.Series) -> str:
    """Download + extract for one reel. Thread-safe (network/disk only,
    no shared state). Returns the video_id. Raises on failure."""
    shortcode = str(row.get("Shortcode", "")).strip()
    reel_url  = str(row.get("Reel Link", "")).strip()

    if not shortcode or not reel_url:
        raise RuntimeError("missing shortcode or reel URL")

    print(f"   [DOWNLOAD] {shortcode} ...")
    video_path, video_id = download_reel(reel_url, ASSETS_DIR)
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError("download failed — video file not found")

    print(f"   [EXTRACT]  {shortcode} ...")
    extract_assets(video_path, ASSETS_DIR, video_id)

    # Prune the full .mp4 — /analyze only reads keyframes + .wav + .txt.
    # The .wav is needed for transcribe.py; cleanup_assets.py reclaims it
    # later once the reel reaches Status=ANALYZED.
    try:
        os.remove(video_path)
        print(f"   [PRUNE]    {os.path.basename(video_path)}")
    except OSError as e:
        print(f"   [WARN]     could not prune {video_path}: {e}")

    return video_id


def finalize_reel(idx: int, row: pd.Series, df: pd.DataFrame,
                  video_id: str, delete_assets: bool) -> bool:
    """Main-thread finalization: Brain note, optional cleanup, Excel row."""
    shortcode = str(row.get("Shortcode", "")).strip()
    try:
        # 3. Create Brain note -----------------------------------------------
        note_path = create_brain_note(shortcode, row.to_dict())
        rel_path  = os.path.relpath(note_path, WORKSPACE)
        print(f"   [BRAIN]    {rel_path}")

        # 4. Optional cleanup (default: KEEP assets for analysis) ------------
        if delete_assets:
            deleted = delete_reel_assets(video_id)
            print(f"   [CLEANUP]  {deleted} files deleted (--delete-assets)")

        # 5. Update Excel row ------------------------------------------------
        df.at[idx, "Status"]          = "PROCESSED"
        df.at[idx, "Processed Date"]  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        df.at[idx, "Brain Note Path"] = note_path
        return True

    except Exception as e:
        print(f"   [FAILED]   {shortcode}: {e}")
        df.at[idx, "Status"]         = "FAILED"
        df.at[idx, "Processed Date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return False


# ---------------------------------------------------------------------------
def update_registry_processed(shortcode: str) -> None:
    if not os.path.exists(REGISTRY_PATH):
        return
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        reg = json.load(f)
    for creator in reg.get("creators", []):
        scraped = creator.get("scraped_reels", [])
        if shortcode in scraped:
            processed = set(creator.get("processed_reels", []))
            processed.add(shortcode)
            creator["processed_reels"] = list(processed)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)


# ---------------------------------------------------------------------------
def main(category_filter: str = "ALL", limit: int = 0, workers: int = 3,
         delete_assets: bool = False, skip_transcribe: bool = False,
         username: str = "", shortcode: str = "") -> None:
    df = load_sheet()

    # Filter by status
    pending_mask = df["Status"].astype(str).str.upper().isin(["SCRAPED", "FAILED", ""])

    # Filter by category if specified
    if category_filter != "ALL":
        cat_mask     = df["Category"].astype(str).str.upper() == category_filter
        pending_mask = pending_mask & cat_mask

    # Filter by username if specified
    if username:
        handle    = username.lstrip("@").lower()
        user_mask = df["Username"].astype(str).str.lower() == f"@{handle}"
        pending_mask = pending_mask & user_mask

    # Filter by shortcode if specified
    if shortcode:
        sc_mask = df["Shortcode"].astype(str).str.strip() == shortcode
        pending_mask = pending_mask & sc_mask

    pending = df[pending_mask]

    if pending.empty:
        parts = []
        if category_filter != "ALL":
            parts.append(f"category={category_filter}")
        if username:
            parts.append(f"@{username.lstrip('@')}")
        if shortcode:
            parts.append(f"shortcode={shortcode}")
        scope = f"[{', '.join(parts)}]" if parts else ""
        print(f"\n[INFO] No SCRAPED reels found {scope}.")
        print(f"       Run 'uv run System/scrape.py' first.")
        return

    total = len(pending)
    cap   = limit if limit > 0 else total
    scope_parts = [f"category={category_filter}"]
    if username:
        scope_parts.append(f"@{username.lstrip('@')}")
    if shortcode:
        scope_parts.append(f"shortcode={shortcode}")
    print(f"\n[PROCESS] {total} reels pending  |  {' | '.join(scope_parts)}  |  cap={cap}")
    print(f"[PARALLEL] {workers} download threads  |  assets kept for analysis")
    print(f"{'='*60}")

    targets = [(idx, row) for idx, row in pending.iterrows()][:cap]
    done = failed = 0

    # 1. Download + extract in parallel; finalize on the main thread ---------
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_media, row): (idx, row)
                   for idx, row in targets}
        for fut in as_completed(futures):
            idx, row = futures[fut]
            shortcode = str(row.get("Shortcode", "")).strip()
            try:
                video_id = fut.result()
                success  = finalize_reel(idx, row, df, video_id, delete_assets)
            except Exception as e:
                print(f"   [FAILED]   {shortcode}: {e}")
                df.at[idx, "Status"]         = "FAILED"
                df.at[idx, "Processed Date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                success = False

            save_sheet(df)   # save after every reel — progress never lost
            if success:
                update_registry_processed(shortcode)
                done += 1
            else:
                failed += 1
            print(f"   Progress -> {done} done  |  {failed} failed")

    # Final summary
    print(f"\n{'='*60}")
    print(f"[COMPLETE] Processed:{done}  Failed:{failed}")
    for cat in ["NICHE", "BRANDING"]:
        sub = df[df["Category"].astype(str).str.upper() == cat]
        sc  = len(sub[sub["Status"].astype(str).str.upper() == "SCRAPED"])
        pr  = len(sub[sub["Status"].astype(str).str.upper() == "PROCESSED"])
        print(f"  {cat:10s}  Total:{len(sub)}  SCRAPED:{sc}  PROCESSED:{pr}")
    print(f"[FILE]     {SPREADSHEET_PATH}")
    print(f"{'='*60}")

    # 2. Chain into Whisper transcription ------------------------------------
    if skip_transcribe:
        print("[SKIP] Transcription disabled via --skip-transcribe")
    elif done > 0:
        print(f"\n[TRANSCRIBE] Handing off to transcribe.py ...")
        try:
            import transcribe
            transcribe.transcribe_pending(limit=0)
        except Exception as e:
            print(f"[WARN] Transcription step skipped: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=["NICHE", "BRANDING", "ALL"],
                        default="ALL", help="Which category to process")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max reels to process (0 = all pending)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel download threads")
    parser.add_argument("--delete-assets", action="store_true",
                        help="Delete media right after processing (breaks later analysis)")
    parser.add_argument("--skip-transcribe", action="store_true",
                        help="Do not chain into transcribe.py")
    parser.add_argument("--username", default="",
                        help="Process only this creator handle (filter on Username column)")
    parser.add_argument("--shortcode", default="",
                        help="Process a single reel by shortcode")
    args = parser.parse_args()
    main(category_filter=args.category.upper(), limit=args.limit,
         workers=args.workers, delete_assets=args.delete_assets,
         skip_transcribe=args.skip_transcribe, username=args.username,
         shortcode=args.shortcode)
