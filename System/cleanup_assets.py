"""
cleanup_assets.py — clear completed-run Assets or validated ANALYZED media.
===================================================================
The default mode reads Brain/Reels_Log.xlsx and deletes exact media for reels whose
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
    uv run System/cleanup_assets.py --all-assets # empty this workspace's Assets

--all-assets is an explicit, workbook-independent mode. Invoke it only after
satisfactory results are validated and persisted and all asset consumers finish.
It includes hidden files, directories, links and workflow.png, retaining Assets.
"""

import os, sys, glob, argparse, stat

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR       = os.path.join(WORKSPACE, "Assets")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")

# Protected only in legacy, per-reel cleanup; --all-assets includes these.
PROTECTED = {"workflow.png"}


# ---------------------------------------------------------------------------
def cleanup_all_assets(dry_run: bool = False) -> int:
    """Empty the literal workspace Assets directory without following links.

    All traversal and deletion use directory descriptors plus O_NOFOLLOW, so
    replacing a child directory with a symlink cannot redirect traversal.
    Every open directory's ancestry is revalidated before traversal/deletion;
    a subtree moved outside Assets is refused even if its descriptor stays open.
    No arbitrary target argument is accepted, and no Brain/workbook is read.
    """
    expected = os.path.join(os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..")), "Assets")
    print(f"[ALL ASSETS] Target: {expected}{' [DRY RUN]' if dry_run else ''}")
    counts = {"files": 0, "directories": 0, "symlinks": 0, "other": 0}
    failures = []

    def report_error(path, error):
        failures.append((path, str(error)))
        print(f"[ERROR] {path}: {error}")

    def kind(mode):
        if stat.S_ISLNK(mode):
            return "symlinks"
        if stat.S_ISDIR(mode):
            return "directories"
        return "files" if stat.S_ISREG(mode) else "other"

    def summary(remaining):
        label = "Would remove" if dry_run else "Removed"
        details = ", ".join(f"{number} {name}" for name, number in counts.items())
        print(f"[SUMMARY] {label}: {sum(counts.values())} entries ({details}).")
        print(f"[SUMMARY] Remaining entries: {remaining}; failures: {len(failures)}.")

    # Constants cannot redirect this mode; reject aliases through any ancestor.
    if ASSETS_DIR != expected or WORKSPACE != os.path.dirname(expected):
        report_error(expected, "Assets path redirection refused")
        summary("unknown")
        return 1
    if os.path.realpath(expected) != expected:
        report_error(expected, "Symlink root or ancestor/path redirection refused")
        summary("unknown")
        return 1
    try:
        root_info = os.lstat(expected)
    except FileNotFoundError:
        print("[INFO] Assets is absent; nothing to remove (directory not created).")
        summary(0)
        return 0
    except OSError as error:
        report_error(expected, error)
        summary("unknown")
        return 1
    if not stat.S_ISDIR(root_info.st_mode):
        report_error(expected, "Assets root must be a directory, never a file or symlink")
        summary("unknown")
        return 1
    if os.path.ismount(expected):
        report_error(expected, "Mounted Assets root refused")
        summary("unknown")
        return 1
    required = {os.open, os.stat, os.unlink, os.rmdir}
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or not required.issubset(os.supports_dir_fd)
            or os.stat not in os.supports_follow_symlinks):
        report_error(expected, "Safe descriptor-based cleanup unsupported on this platform")
        summary("unknown")
        return 1

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = None
    try:
        root_fd = os.open(expected, flags)
        opened = os.fstat(root_fd)
        if (opened.st_dev, opened.st_ino) != (root_info.st_dev, root_info.st_ino):
            raise OSError("Assets root changed while opening it")

        def check_root():
            current = os.lstat(expected)
            if (not stat.S_ISDIR(current.st_mode)
                    or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
                    or os.path.realpath(expected) != expected):
                raise OSError("Assets root changed; further deletion refused")

        def check_ancestry(ancestry):
            check_root()
            for parent_fd, name, device, inode in ancestry:
                try:
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError as error:
                    raise OSError("Directory ancestry changed; moved subtree refused") from error
                if (not stat.S_ISDIR(current.st_mode)
                        or (current.st_dev, current.st_ino) != (device, inode)):
                    raise OSError("Directory ancestry changed; moved subtree refused")

        def visit(directory_fd, relative="", remove=False, ancestry=()):
            """Return a recursive entry count, or None if inspection failed."""
            total = 0
            try:
                check_ancestry(ancestry)
                names = sorted(os.listdir(directory_fd))
            except OSError as error:
                report_error(os.path.join(expected, relative), error)
                return None
            for name in names:
                child = os.path.join(relative, name)
                display = os.path.join(expected, child)
                child_fd = None
                try:
                    check_ancestry(ancestry)
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    entry_kind = kind(info.st_mode)
                    if total is not None:
                        total += 1
                    if entry_kind == "directories":
                        if info.st_dev != opened.st_dev or os.path.ismount(display):
                            raise OSError("Mounted directory refused")
                        child_fd = os.open(name, flags, dir_fd=directory_fd)
                        child_info = os.fstat(child_fd)
                        if (child_info.st_dev, child_info.st_ino) != (info.st_dev, info.st_ino):
                            raise OSError("Directory changed while opening it")
                        child_ancestry = ancestry + ((directory_fd, name,
                                                     child_info.st_dev, child_info.st_ino),)
                        nested = visit(child_fd, child, remove=remove,
                                       ancestry=child_ancestry)
                        if nested is None:
                            total = None
                        elif total is not None:
                            total += nested
                    if remove:
                        check_ancestry(ancestry)
                        if dry_run:
                            print(f"[WOULD REMOVE] {child!r}")
                        elif entry_kind == "directories":
                            os.rmdir(name, dir_fd=directory_fd)
                            print(f"[REMOVED] {child!r}")
                        else:
                            os.unlink(name, dir_fd=directory_fd)
                            print(f"[REMOVED] {child!r}")
                        counts[entry_kind] += 1
                except OSError as error:
                    report_error(display, error)
                    total = None
                finally:
                    if child_fd is not None:
                        os.close(child_fd)
            return total

        visit(root_fd, remove=True)
        remaining = visit(root_fd)
        check_root()
        summary(remaining if remaining is not None else "unknown")
        return 1 if failures or (not dry_run and remaining != 0) else 0
    except OSError as error:
        report_error(expected, error)
        summary("unknown")
        return 1
    finally:
        if root_fd is not None:
            os.close(root_fd)


# ---------------------------------------------------------------------------
def analyzed_reels() -> list:
    """ANALYZED shortcodes from the sheet (blank/whitespace ids rejected)."""
    if not os.path.exists(SPREADSHEET_PATH):
        return []
    import pandas as pd
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
    sys.path.insert(0, os.path.dirname(__file__))
    import preflight
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
    import pandas as pd
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
def main(dry_run: bool = False, prune_raw: bool = False,
         all_assets: bool = False) -> int:
    if all_assets:
        if prune_raw:
            print("[ERROR] --all-assets and --prune-raw are mutually exclusive.")
            return 1
        return cleanup_all_assets(dry_run)
    if prune_raw:
        prune_raw_assets(dry_run)
        return 0

    reels = analyzed_reels()
    if not reels:
        print("[INFO] No ANALYZED reels found — nothing to clean up.")
        print("       (Reels become eligible after /analyze + mark_analyzed.py)")
        return 0

    print(f"\n[CLEANUP] {len(reels)} ANALYZED reel(s) eligible"
          f"{'  [DRY RUN]' if dry_run else ''}")
    total = 0
    for sc in reels:
        print(f"   [REEL] {sc}")
        total += delete_for(sc, dry_run)

    print(f"\n[{'WOULD DELETE' if dry_run else 'DELETED'}] {total} file(s) total.")
    return 0


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without deleting them")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--all-assets", action="store_true",
                       help="Empty every entry in this workspace's Assets, including "
                            "hidden files and workflow.png; retain the directory. "
                            "Requires completed consumers and satisfactory results "
                            "already validated and persisted.")
    modes.add_argument("--prune-raw", action="store_true",
                        help="Delete .mp4 (and _5s.mp4) for every PROCESSED/ANALYZED reel; "
                             "keeps keyframes + .wav + .txt. Use for the one-time reclaim "
                             "of historical reels.")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run, prune_raw=args.prune_raw,
                  all_assets=args.all_assets))
