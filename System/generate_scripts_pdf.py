"""Generate a polished premium PDF from 1–3 markdown script drafts.

Sole public wrapper around the premium renderer in System/_build_script_pdf.py.
Dynamically parses each source file (title, length, pillars, score, core
concept, hook teaser) — no hardcoded scripts. The produced PDF is validated
with the preflight check function (imported, no shelling out).

Usage:
    uv run System/generate_scripts_pdf.py --scripts file1.md file2.md [file3.md]
                                         [--output draft_result/Topic.pdf]
                                         [--topic "Topic Name"]

Default output: draft_result/<topic-slug>.pdf
Exit codes: 0 = OK, 1 = build/validation failure, 2 = usage error.
"""

import argparse
import re
import sys
from pathlib import Path

from preflight import check_pdf, check_script
from _build_script_pdf import build_pdf


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a premium PDF from 1–3 script drafts")
    parser.add_argument("--scripts", nargs="+", required=True,
                        help="Paths to 1–3 markdown script files")
    parser.add_argument("--output", default=None,
                        help="Output PDF path (default draft_result/<topic-slug>.pdf)")
    parser.add_argument("--topic", default="Script Drafts",
                        help="Topic name for the cover page")
    args = parser.parse_args(argv)

    # Validate requested count (1–3).
    if not 1 <= len(args.scripts) <= 3:
        print(f"[ERROR] --scripts expects 1–3 files, got {len(args.scripts)}",
              file=sys.stderr)
        return 2

    # Validate input paths.
    missing = [p for p in args.scripts if not Path(p).is_file()]
    if missing:
        for p in missing:
            print(f"[ERROR] script file not found: {p}", file=sys.stderr)
        return 2

    # Block malformed new drafts before they become polished-looking PDFs.
    script_errors = 0
    for path in args.scripts:
        issues = check_script(path)
        for issue in issues:
            if issue.severity in ("warning", "error"):
                print(f"   [{issue.severity.upper():7s}] {issue.code}: "
                      f"{issue.message}  [{path}]")
        script_errors += sum(issue.severity == "error" for issue in issues)
    if script_errors:
        print(f"[FAIL] script preflight: {script_errors} error(s); PDF not built",
              file=sys.stderr)
        return 1

    # Default output remains draft_result/<topic-slug>.pdf.
    output = args.output
    if not output:
        topic_slug = re.sub(r"[^\w\s-]", "", args.topic).strip().replace(" ", "_") \
                     or "Script_Drafts"
        output = f"draft_result/{topic_slug}.pdf"
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    # Build with the premium renderer.
    try:
        build_pdf(args.scripts, output, topic=args.topic)
    except Exception as e:
        print(f"[ERROR] failed to build PDF: {e}", file=sys.stderr)
        return 1

    # Validate the produced PDF with preflight's check function (imported).
    issues = check_pdf(output, requested_title=args.topic or None)
    for i in issues:
        where = f"  [{i.file}]" if i.file else ""
        print(f"   [{i.severity.upper():7s}] {i.code}: {i.message}{where}")
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        print(f"[FAIL] PDF validation: {len(errors)} error(s) — see above",
              file=sys.stderr)
        return 1
    print(f"[OK] PDF generated and validated: {output}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
