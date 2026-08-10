"""
mark_analyzed.py  —  STEP 5: flip fully-analyzed reels to Status=ANALYZED.
==========================================================================
A reel counts as analyzed when the complete analysis trio exists in
Brain/Analyses/ AND its content passes validation:

    <shortcode>_visual.json     (valid JSON object, required sections, reel_id match)
    <shortcode>_audio.md        (required section labels present)
    <shortcode>_retention.md    (8 factors, 1-10 integer scores, arithmetic overall)

Invalid trios never flip status — content is checked, not just file existence.
Rows in Brain/Reels_Log.xlsx with Status=PROCESSED and a valid trio are flipped
to ANALYZED. Once ANALYZED, the reel's media becomes eligible for deletion by
cleanup_assets.py (which re-validates the trio before deleting).

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
import preflight
from workspace_lock import locked


# ---------------------------------------------------------------------------
def analyzed_shortcodes(requested: set[str] | None = None) -> set:
    """Shortcodes with a complete AND content-valid analysis trio."""
    complete = set()
    for path in glob.glob(os.path.join(ANALYSES_DIR, "*_visual.json")):
        rid       = os.path.basename(path).replace("_visual.json", "")
        if requested and rid not in requested:
            continue
        audio     = os.path.join(ANALYSES_DIR, f"{rid}_audio.md")
        retention = os.path.join(ANALYSES_DIR, f"{rid}_retention.md")
        if not (os.path.exists(audio) and os.path.exists(retention)):
            continue
        ok, issues = preflight.analysis_ok(rid)
        if ok:
            complete.add(rid)
        else:
            codes = ", ".join(i.code for i in issues if i.severity == "error")
            print(f"   [SKIP-INVALID] {rid}: {codes}")
    return complete


# ---------------------------------------------------------------------------
@locked
def main(dry_run: bool = False, shortcodes: list[str] | None = None) -> None:
    if not os.path.exists(SPREADSHEET_PATH):
        print("[ERROR] Reels_Log.xlsx not found — nothing to mark.")
        sys.exit(1)

    df       = load_sheet()
    requested = {
        str(sc).strip() for sc in (shortcodes or []) if str(sc).strip()
    }
    if shortcodes is not None and not requested:
        print("[ERROR] --shortcodes requires at least one non-empty shortcode.")
        return

    complete = analyzed_shortcodes(requested or None)
    if not complete:
        print("[INFO] No complete, valid analysis trios in Brain/Analyses/ yet.")
        return

    flipped = []
    invalid = []
    for idx, row in df.iterrows():
        sc     = str(row.get("Shortcode", "")).strip()
        status = str(row.get("Status", "")).strip().upper()
        if requested and sc not in requested:
            continue
        if status == "PROCESSED" and sc in complete:
            valid, issues = preflight.analysis_ok(sc)
            if not valid:
                invalid.append((sc, issues))
                continue
            flipped.append(sc)
            if not dry_run:
                df.at[idx, "Status"] = "ANALYZED"

    if not flipped:
        print("[INFO] No PROCESSED reels have complete, valid analyses yet.")
        return

    print(f"\n[ANALYZED] {len(flipped)} reel(s) {'would be ' if dry_run else ''}marked ANALYZED:")
    for sc in flipped:
        print(f"   - {sc}")

    for sc, issues in invalid:
        print(f"   [SKIP-INVALID] {sc}  ({len(issues)} validation issue(s))")

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
    parser.add_argument("--shortcodes", nargs="+", default=None,
                        help="Mark only these exact shortcodes")
    args = parser.parse_args()
    main(dry_run=args.dry_run, shortcodes=args.shortcodes)
