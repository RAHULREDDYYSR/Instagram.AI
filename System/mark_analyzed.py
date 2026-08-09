"""
mark_analyzed.py  —  STEP 5: flip fully-analyzed reels to Status=ANALYZED.
==========================================================================
A reel counts as analyzed when all three agent outputs exist in
Brain/Analyses/:

    <shortcode>_visual.json     (video-analysis skill)
    <shortcode>_audio.md        (audio-analysis skill)
    <shortcode>_retention.md    (retention scoring vs Brain/Rubric.md)

Rows in Brain/Reels_Log.xlsx with Status=PROCESSED and a complete trio
are flipped to ANALYZED. Once ANALYZED, the reel's media in Assets/
becomes eligible for deletion by cleanup_assets.py.

Usage:
    uv run System/mark_analyzed.py
    uv run System/mark_analyzed.py --dry-run
"""

import os, sys, glob, argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")
ANALYSES_DIR     = os.path.join(WORKSPACE, "Brain", "Analyses")

sys.path.insert(0, os.path.dirname(__file__))
from process_reels import load_sheet, save_sheet   # reuse styled Excel I/O


# ---------------------------------------------------------------------------
def analyzed_shortcodes() -> set:
    """Shortcodes with a complete analysis trio in Brain/Analyses/."""
    complete = set()
    for path in glob.glob(os.path.join(ANALYSES_DIR, "*_visual.json")):
        rid  = os.path.basename(path).replace("_visual.json", "")
        audio    = os.path.join(ANALYSES_DIR, f"{rid}_audio.md")
        retention = os.path.join(ANALYSES_DIR, f"{rid}_retention.md")
        if os.path.exists(audio) and os.path.exists(retention):
            complete.add(rid)
    return complete


# ---------------------------------------------------------------------------
def main(dry_run: bool = False) -> None:
    if not os.path.exists(SPREADSHEET_PATH):
        print("[ERROR] Reels_Log.xlsx not found — nothing to mark.")
        sys.exit(1)

    df       = load_sheet()
    complete = analyzed_shortcodes()

    if not complete:
        print("[INFO] No complete analysis trios in Brain/Analyses/ yet.")
        return

    flipped = []
    for idx, row in df.iterrows():
        sc     = str(row.get("Shortcode", "")).strip()
        status = str(row.get("Status", "")).strip().upper()
        if status == "PROCESSED" and sc in complete:
            flipped.append(sc)
            if not dry_run:
                df.at[idx, "Status"] = "ANALYZED"

    if not flipped:
        print("[INFO] No PROCESSED reels have complete analyses yet.")
        return

    print(f"\n[ANALYZED] {len(flipped)} reel(s) {'would be ' if dry_run else ''}marked ANALYZED:")
    for sc in flipped:
        print(f"   - {sc}")

    if not dry_run:
        save_sheet(df)
        print(f"[SAVED] {SPREADSHEET_PATH}")
        print(f"[NEXT]  Media for these reels can now be removed:")
        print(f"        uv run System/cleanup_assets.py")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would flip to ANALYZED without saving")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
