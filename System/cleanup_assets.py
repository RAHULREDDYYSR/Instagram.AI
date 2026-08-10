"""
cleanup_assets.py  —  STEP 6: delete media for ANALYZED reels only.
===================================================================
Reads Brain/Reels_Log.xlsx and deletes the exact media files of reels whose
Status is ANALYZED AND whose analysis trio is complete and content-valid
(validated via preflight — deletion is never based on file existence alone).

Only exact patterns are ever deleted — never a broad <shortcode>* glob:

    <shortcode>.mp4
    <shortcode>_5s.mp4            (optional hook clip)
    <shortcode>.wav
    <shortcode>.txt
    <shortcode>_keyframe_*.jpg

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

sys.path.insert(0, os.path.dirname(__file__))
import preflight

# Files in Assets/ that are NOT reel media and must never be deleted.
PROTECTED = {"workflow.png"}


# ---------------------------------------------------------------------------
def analyzed_reels() -> list:
    """ANALYZED shortcodes from the sheet (blank/whitespace ids rejected)."""
    if not os.path.exists(SPREADSHEET_PATH):
        return []
    df = pd.read_excel(SPREADSHEET_PATH)
    if "Status" not in df.columns or "Shortcode" not in df.columns:
        return []
    mask = df["Status"].astype(str).str.upper() == "ANALYZED"
    return [str(sc).strip() for sc in df[mask]["Shortcode"].dropna().tolist()
            if str(sc).strip()]


def media_files_for(shortcode: str) -> list:
    """Exact media files for a shortcode — never a broad <id>* match."""
    files = []
    for name in (f"{shortcode}.mp4", f"{shortcode}_5s.mp4",
                 f"{shortcode}.wav", f"{shortcode}.txt"):
        path = os.path.join(ASSETS_DIR, name)
        if os.path.exists(path):
            files.append(path)
    files += glob.glob(os.path.join(ASSETS_DIR, f"{shortcode}_keyframe_*.jpg"))
    return [f for f in files if os.path.basename(f) not in PROTECTED]


def delete_for(shortcode: str, dry_run: bool) -> int:
    """Delete media for one shortcode, but only after the analysis trio is
    validated — invalid trios never lose their media."""
    if not shortcode:
        return 0
    ok, issues = preflight.analysis_ok(shortcode)
    if not ok:
        codes = ", ".join(i.code for i in issues if i.severity == "error")
        print(f"   [SKIP-UNVALIDATED] {shortcode}: analysis trio invalid ({codes})")
        return 0
    files = media_files_for(shortcode)
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
    shortcodes = [str(sc).strip() for sc in df[mask]["Shortcode"].dropna().tolist()
                  if str(sc).strip()]
    if not shortcodes:
        print("[INFO] No PROCESSED/ANALYZED reels found — nothing to prune.")
        return

    print(f"\n[PRUNE] {len(shortcodes)} reel(s) eligible"
          f"{'  [DRY RUN]' if dry_run else ''}")
    total = 0
    for sc in shortcodes:
        # Exact names only: <sc>.mp4 and <sc>_5s.mp4, never keyframes.
        candidates = []
        for name in (f"{sc}.mp4", f"{sc}_5s.mp4"):
            path = os.path.join(ASSETS_DIR, name)
            if os.path.exists(path) and os.path.basename(path) not in PROTECTED:
                candidates.append(path)
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
