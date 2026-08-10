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
    uv run System/process_reels.py --checkpoint-every 10   # workbook save cadence
    uv run System/process_reels.py --username viralish     # only this creator
"""

import os, sys, json, re, glob, datetime, argparse, shutil, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from ingest_reel import download_reel, extract_assets, derived_assets_valid
from workspace_lock import atomic_path, locked
import preflight

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
    # Appended LAST on purpose: Category/Status are addressed positionally
    # (row[1] / row[13]), so extra columns must never shift them. Keep any
    # other pre-existing columns (e.g. Source) in the sheet.
    "Source",
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
    directory = os.path.dirname(SPREADSHEET_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".reels_log_", suffix=".xlsx", dir=directory)
    os.close(fd)
    try:
        with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
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
        os.replace(temp_path, SPREADSHEET_PATH)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
def delete_reel_assets(video_id: str) -> int:
    """Delete only exact media files for this id (no broad <id>* matching)."""
    if not video_id:
        return 0
    files = []
    for name in (f"{video_id}.mp4", f"{video_id}.wav", f"{video_id}.txt",
                 f"{video_id}_5s.mp4"):
        path = os.path.join(ASSETS_DIR, name)
        if os.path.exists(path):
            files.append(path)
    files += glob.glob(os.path.join(ASSETS_DIR, f"{video_id}_keyframe_*.jpg"))
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
def create_brain_note(shortcode: str, row: dict) -> tuple[str, bool]:
    """Return (note_path, created). An existing note is NEVER overwritten —
    it may have been populated by an analyst, and retries must not clobber it."""
    category = str(row.get("Category", "NICHE")).upper()
    if category == "BRANDING":
        note_path = os.path.join(BRAND_BRAIN_DIR, f"{shortcode}.md")
        writer    = create_branding_note
    else:
        note_path = os.path.join(REELS_BRAIN_DIR, f"{shortcode}.md")
        writer    = create_niche_note
    if os.path.exists(note_path):
        return note_path, False
    return writer(shortcode, row), True


# ---------------------------------------------------------------------------
def fetch_media(row: pd.Series) -> str:
    """Download + extract for one reel. Thread-safe (network/disk only,
    no shared state). Returns the video_id. Raises on failure."""
    shortcode = str(row.get("Shortcode", "")).strip()
    reel_url  = str(row.get("Reel Link", "")).strip()

    if not shortcode or not reel_url:
        raise RuntimeError("missing shortcode or reel URL")

    print(f"   [DOWNLOAD] {shortcode} ...")
    # Use the Excel shortcode as the canonical output id so derived assets
    # always land on <shortcode>.wav / <shortcode>_keyframe_*.jpg.
    video_path, video_id = download_reel(reel_url, ASSETS_DIR, video_id=shortcode)
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError("download failed — video file not found")

    print(f"   [EXTRACT]  {shortcode} ...")
    extract_assets(video_path, ASSETS_DIR, video_id)

    # Validate the derived assets BEFORE pruning the source mp4 — a failed
    # extraction must not look like a successful process.
    if not derived_assets_valid(ASSETS_DIR, video_id):
        raise RuntimeError(
            f"extraction produced invalid assets for {video_id} "
            "(missing/empty wav or keyframes)")

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
        note_path, created = create_brain_note(shortcode, row.to_dict())
        rel_path  = os.path.relpath(note_path, WORKSPACE)
        print(f"   [BRAIN]    {rel_path}" + ("" if created else " (reused existing)"))

        # 4. Optional cleanup (default: KEEP assets for analysis) ------------
        if delete_assets:
            deleted = delete_reel_assets(video_id)
            print(f"   [CLEANUP]  {deleted} files deleted (--delete-assets)")

        # Keep the row SCRAPED until the scoped transcript is validated. This
        # preserves the documented PROCESSED contract across crashes.
        df.at[idx, "Status"]          = "SCRAPED"
        df.at[idx, "Processed Date"]  = ""
        df.at[idx, "Brain Note Path"] = note_path
        return True

    except Exception as e:
        print(f"   [FAILED]   {shortcode}: {e}")
        df.at[idx, "Status"]         = "FAILED"
        df.at[idx, "Processed Date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return False


# ---------------------------------------------------------------------------
def update_registry_processed(shortcodes: list[str]) -> None:
    """Atomically add processed shortcodes to _registry.json in ONE write.

    The workbook transaction already holds the workspace lock, so the
    read-modify-write below cannot race with scrape.py. Writes go through
    atomic_path: a failed write never truncates a valid registry.
    """
    shortcodes = [s for s in (shortcodes or []) if s and s.strip()]
    if not shortcodes or not os.path.exists(REGISTRY_PATH):
        return
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        reg = json.load(f)
    changed = False
    for creator in reg.get("creators", []):
        scraped   = set(creator.get("scraped_reels", []))
        processed = set(creator.get("processed_reels", []))
        for shortcode in shortcodes:
            if shortcode in scraped:
                processed.add(shortcode)
        if processed != set(creator.get("processed_reels", [])):
            creator["processed_reels"] = list(processed)
            changed = True
    if not changed:
        return
    with atomic_path(REGISTRY_PATH) as temp_path:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)


# ---------------------------------------------------------------------------
@locked
def main(category_filter: str = "ALL", limit: int = 0, workers: int = 3,
         delete_assets: bool = False, skip_transcribe: bool = False,
         username: str = "", shortcode: str = "",
         shortcodes: list[str] | None = None,
         checkpoint_every: int = 5) -> None:
    df = load_sheet()

    requested_shortcodes = {
        str(sc).strip() for sc in (shortcodes or []) if str(sc).strip()
    }
    if shortcodes is not None and not requested_shortcodes:
        raise ValueError("--shortcodes requires at least one non-empty shortcode")

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

    # Filter by shortcode if specified. An explicit list is authoritative and
    # must never fall back to global pending-row selection.
    if requested_shortcodes:
        sc_mask = df["Shortcode"].astype(str).str.strip().isin(requested_shortcodes)
        pending_mask = pending_mask & sc_mask
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
        if requested_shortcodes:
            parts.append(f"shortcodes={','.join(sorted(requested_shortcodes))}")
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
    if requested_shortcodes:
        scope_parts.append(f"shortcodes={len(requested_shortcodes)}")
    print(f"\n[PROCESS] {total} reels pending  |  {' | '.join(scope_parts)}  |  cap={cap}")
    print(f"[PARALLEL] {workers} download threads  |  assets kept for analysis")
    print(f"{'='*60}")

    targets = [(idx, row) for idx, row in pending.iterrows()][:cap]
    done = failed = 0
    successful_shortcodes: list[str] = []
    processed_since_checkpoint = 0

    if checkpoint_every > 0:
        print(f"[CHECKPOINT] workbook saved every {checkpoint_every} reel(s) + once at the end")

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

            if success:
                successful_shortcodes.append(shortcode)
                done += 1
            else:
                failed += 1

            # Persist at checkpoints (not after every reel) — in-memory row
            # updates stay current for all reels, but the workbook is only
            # restyled/re-written every `checkpoint_every` reels. On a crash
            # the worst case is losing the last partial checkpoint's rows.
            processed_since_checkpoint += 1
            if checkpoint_every > 0 and processed_since_checkpoint >= checkpoint_every:
                save_sheet(df)
                print(f"   [CHECKPOINT] workbook saved after {processed_since_checkpoint} reel(s)")
                processed_since_checkpoint = 0
            print(f"   Progress -> {done} done  |  {failed} failed")

    # Final save so every row updated since the last checkpoint is persisted,
    # even when the batch ended before a checkpoint boundary.
    save_sheet(df)
    print("[SAVE] final workbook write")

    # Final summary
    print(f"\n{'='*60}")
    print(f"[COMPLETE] Extracted:{done}  Failed:{failed}")
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
    elif successful_shortcodes:
        print(f"\n[TRANSCRIBE] Handing off to transcribe.py "
              f"({len(successful_shortcodes)} reel(s)) ...")
        try:
            import transcribe
            transcribe.transcribe_pending(shortcodes=successful_shortcodes)
        except Exception as e:
            print(f"[WARN] Transcription step skipped: {e}")

        # Do not leave an extraction marked PROCESSED when its transcript was
        # missing or invalid. The documented PROCESSED contract includes txt.
        transcript_failed = []
        transcript_succeeded = []
        for rid in successful_shortcodes:
            txt_path = os.path.join(ASSETS_DIR, f"{rid}.txt")
            issues = preflight.transcript_issues_for_path(txt_path)
            if any(issue.severity == "error" for issue in issues):
                transcript_failed.append(rid)
                rows = df.index[df["Shortcode"].astype(str).str.strip() == rid]
                for idx in rows:
                    df.at[idx, "Status"] = "FAILED"
                    df.at[idx, "Processed Date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            else:
                rows = df.index[df["Shortcode"].astype(str).str.strip() == rid]
                for idx in rows:
                    df.at[idx, "Status"] = "PROCESSED"
                    df.at[idx, "Processed Date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                transcript_succeeded.append(rid)
        # One registry read/write for the whole scoped batch, never per reel.
        if transcript_succeeded:
            update_registry_processed(transcript_succeeded)
        if transcript_failed or transcript_succeeded:
            save_sheet(df)
        if transcript_failed:
            print(f"[FAILED] Transcript validation: {', '.join(transcript_failed)}")


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
    parser.add_argument("--shortcodes", nargs="+", default=None,
                        help="Process only these exact reel shortcodes")
    parser.add_argument("--checkpoint-every", type=int, default=5,
                        help="Save the Excel sheet every N reels (0 = only at the end)")
    args = parser.parse_args()
    main(category_filter=args.category.upper(), limit=args.limit,
         workers=args.workers, delete_assets=args.delete_assets,
          skip_transcribe=args.skip_transcribe, username=args.username,
          shortcode=args.shortcode, shortcodes=args.shortcodes,
          checkpoint_every=args.checkpoint_every)
