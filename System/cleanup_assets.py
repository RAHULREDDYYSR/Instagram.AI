"""
cleanup_assets.py  —  STEP 6: delete media for ANALYZED reels only.
===================================================================
Reads Brain/Reels_Log.xlsx and deletes Assets/<shortcode>* files for
reels whose Status is ANALYZED (their Brain notes are fully populated,
so the media is no longer needed).

Reels still at PROCESSED keep their media — analysis agents need the
keyframes and transcripts.

Usage:
    uv run System/cleanup_assets.py              # delete for ANALYZED reels
    uv run System/cleanup_assets.py --dry-run    # show what would be deleted
"""

import os, sys, glob, argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR       = os.path.join(WORKSPACE, "Assets")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")

# Files in Assets/ that are NOT reel media and must never be deleted.
PROTECTED = {"workflow.png"}


# ---------------------------------------------------------------------------
def analyzed_reels() -> list:
    if not os.path.exists(SPREADSHEET_PATH):
        return []
    df = pd.read_excel(SPREADSHEET_PATH)
    if "Status" not in df.columns or "Shortcode" not in df.columns:
        return []
    mask = df["Status"].astype(str).str.upper() == "ANALYZED"
    return [str(sc).strip() for sc in df[mask]["Shortcode"].dropna().tolist()]


def delete_for(shortcode: str, dry_run: bool) -> int:
    files = [f for f in glob.glob(os.path.join(ASSETS_DIR, f"{shortcode}*"))
             if os.path.basename(f) not in PROTECTED]
    for f in files:
        if dry_run:
            print(f"   [WOULD DELETE] {os.path.basename(f)}")
        else:
            try:
                os.remove(f)
                print(f"   [DELETED] {os.path.basename(f)}")
            except Exception as e:
                print(f"   [WARN] Could not delete {f}: {e}")
    return len(files)


# ---------------------------------------------------------------------------
def prune_raw_assets(dry_run: bool) -> None:
    """Delete the full .mp4 (and any orphan _5s.mp4) for every PROCESSED
    or ANALYZED reel. Keeps keyframes + .wav + .txt — those are the only
    inputs the analysis agents actually read. Use this for the one-time
    reclaim of historical reels that pre-date the inline prune in
    process_reels.py."""
    if not os.path.exists(SPREADSHEET_PATH):
        print("[ERROR] Reels_Log.xlsx not found.")
        return
    df = pd.read_excel(SPREADSHEET_PATH)
    if "Status" not in df.columns or "Shortcode" not in df.columns:
        print("[ERROR] Reels_Log.xlsx missing required columns.")
        return

    mask = df["Status"].astype(str).str.upper().isin(["PROCESSED", "ANALYZED"])
    shortcodes = [str(sc).strip() for sc in df[mask]["Shortcode"].dropna().tolist()]
    if not shortcodes:
        print("[INFO] No PROCESSED/ANALYZED reels found — nothing to prune.")
        return

    print(f"\n[PRUNE] {len(shortcodes)} reel(s) eligible"
          f"{'  [DRY RUN]' if dry_run else ''}")
    total = 0
    for sc in shortcodes:
        # Match <sc>.mp4 and <sc>_5s.mp4 but NOT <sc>_keyframe_*.jpg
        candidates = [f for f in glob.glob(os.path.join(ASSETS_DIR, f"{sc}*.mp4"))
                      if "_keyframe" not in os.path.basename(f)
                      and os.path.basename(f) not in PROTECTED]
        if not candidates:
            continue
        print(f"   [REEL] {sc}")
        for f in candidates:
            if dry_run:
                print(f"   [WOULD DELETE] {os.path.basename(f)}")
            else:
                try:
                    os.remove(f)
                    print(f"   [DELETED] {os.path.basename(f)}")
                except OSError as e:
                    print(f"   [WARN] Could not delete {f}: {e}")
            total += 1

    print(f"\n[{'WOULD DELETE' if dry_run else 'DELETED'}] {total} file(s) total.")


# ---------------------------------------------------------------------------
def main(dry_run: bool = False, prune_raw: bool = False) -> None:
    if prune_raw:
        prune_raw_assets(dry_run)
        return

    reels = analyzed_reels()
    if not reels:
        print("[INFO] No ANALYZED reels found — nothing to clean up.")
        print("       (Reels become eligible after /analyze + mark_analyzed.py)")
        return

    print(f"\n[CLEANUP] {len(reels)} ANALYZED reel(s) eligible"
          f"{'  [DRY RUN]' if dry_run else ''}")
    total = 0
    for sc in reels:
        print(f"   [REEL] {sc}")
        total += delete_for(sc, dry_run)

    print(f"\n[{'WOULD DELETE' if dry_run else 'DELETED'}] {total} file(s) total.")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without deleting them")
    parser.add_argument("--prune-raw", action="store_true",
                        help="Delete .mp4 (and _5s.mp4) for every PROCESSED/ANALYZED reel; "
                             "keeps keyframes + .wav + .txt. Use for the one-time reclaim "
                             "of historical reels.")
    args = parser.parse_args()
    main(dry_run=args.dry_run, prune_raw=args.prune_raw)
