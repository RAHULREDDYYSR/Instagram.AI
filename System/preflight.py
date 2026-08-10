"""
preflight.py  —  READ-ONLY health checks for pipeline assets, transcripts,
analysis trios, script drafts and generated PDFs. Never writes or mutates.

Commands:
    uv run System/preflight.py assets --shortcode <id>            # full asset suite for a reel
    uv run System/preflight.py assets --file Assets/<id>.wav      # single asset file
    uv run System/preflight.py analysis --shortcode <id>          # analysis trio for a reel
    uv run System/preflight.py script --file Brain/Scripts/X.md   # script draft
    uv run System/preflight.py pdf --file X.pdf [--title "Topic"] # generated PDF
    uv run System/preflight.py all --shortcode <id> [--file ...]  # everything applicable

Flags:
    --strict   treat warnings as errors (affects exit code)
    --json     machine-readable report on stdout

Exit codes: 0 = clean, 1 = errors found (or warnings with --strict).
Issue codes are stable identifiers — treat them as an API, not text.
"""

import os
import re
import sys
import json
import glob
import wave
import argparse
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
WORKSPACE        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR       = os.path.join(WORKSPACE, "Assets")
ANALYSES_DIR     = os.path.join(WORKSPACE, "Brain", "Analyses")
SPREADSHEET_PATH = os.path.join(WORKSPACE, "Brain", "Reels_Log.xlsx")

# The canonical eight retention factors (source of truth for both Brain
# retention reports and script rubric self-scores).
RETENTION_FACTORS = [
    "curiosity & open loops",
    "identity triggers",
    "novelty & specificity",
    "social proof & authority",
    "contrarian framing & conflict",
    "humor & emotion",
    "story tension & pacing",
    "loopability",
]

# Sections every visual analysis JSON should carry (both the modern full
# format and the legacy compact format include these).
VISUAL_REQUIRED_SECTIONS = [
    "opening_shot",
    "editing_style",
    "text_overlays",
    "hook_archetype",
    "transferable_tactics",
    "niche_fit",
]

# Headings every audio analysis markdown should carry.
AUDIO_REQUIRED_LABELS = [
    "## Transcription",
    "## Structure",
    "## Vocal Delivery",
    "## Pacing",
]

SEVERITIES = ("info", "warning", "error")


@dataclass
class Issue:
    code: str
    severity: str          # info | warning | error
    message: str
    file: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity: {self.severity!r}")


# ---------------------------------------------------------------------------
# Small shared helpers -------------------------------------------------------
def count_words(text: str) -> int:
    """Canonical word counter shared with System/transcribe.py."""
    return len(text.split())


def round_half_up(value) -> Decimal:
    """Round a numeric mean to 1 decimal place using ROUND_HALF_UP."""
    return Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def normalize_factor(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.strip().lower()).strip()


def _read_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _read_text_lossy(path: str) -> str:
    """Read text, tolerating encoding damage (analysis files carry mojibake)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _strict_utf8(path: str) -> bool:
    """True when the file decodes as valid UTF-8."""
    data = _read_bytes(path)
    if data is None:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def jpeg_magic(path: str) -> bool:
    data = _read_bytes(path)
    return bool(data) and data[:3] == b"\xff\xd8\xff"


def is_riff_wave(path: str) -> tuple[bool, str]:
    """True when the file is a real RIFF/WAVE container with audio frames."""
    data = _read_bytes(path)
    if data is None:
        return False, "unreadable"
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False, "not a RIFF/WAVE container"
    try:
        with wave.open(path, "rb") as w:
            if w.getnframes() <= 0:
                return False, "zero audio frames"
            if w.getframerate() <= 0:
                return False, "invalid sample rate"
    except (wave.Error, EOFError, OSError) as e:
        return False, f"corrupt wave header: {e}"
    return True, ""


def shortcode_status(shortcode: str) -> str:
    """Upper-cased Status from Reels_Log.xlsx for a shortcode ('' when unknown)."""
    sc = (shortcode or "").strip()
    if not sc or not os.path.exists(SPREADSHEET_PATH):
        return ""
    try:
        import pandas as pd
        df = pd.read_excel(SPREADSHEET_PATH)
    except Exception:
        return ""
    if "Shortcode" not in df.columns or "Status" not in df.columns:
        return ""
    match = df[df["Shortcode"].astype(str).str.strip() == sc]
    if match.empty:
        return ""
    return str(match.iloc[0]["Status"]).strip().upper()


# ---------------------------------------------------------------------------
# Assets: wav / keyframes / mp4 / transcript ---------------------------------
def check_wav(path: str) -> list[Issue]:
    issues: list[Issue] = []
    if not os.path.exists(path):
        issues.append(Issue("ASSET_WAV_MISSING", "error", "wav file missing", path))
        return issues
    if os.path.getsize(path) == 0:
        issues.append(Issue("ASSET_WAV_EMPTY", "error", "wav file is empty", path))
        return issues
    ok, reason = is_riff_wave(path)
    if not ok:
        issues.append(Issue("ASSET_WAV_INVALID", "error", f"wav invalid: {reason}", path))
    else:
        with wave.open(path, "rb") as w:
            issues.append(Issue(
                "ASSET_WAV_OK", "info",
                f"wav valid: {w.getnframes()} frames, {w.getframerate()} Hz, "
                f"{os.path.getsize(path)} bytes", path))
    return issues


def check_keyframes(shortcode: str, expected: bool) -> list[Issue]:
    """Keyframe checks. `expected=False` when media was already pruned
    (ANALYZED reels) — then absence is a warning, corruption still an error."""
    issues: list[Issue] = []
    if not shortcode:
        issues.append(Issue("ASSET_KF_BAD_ID", "error", "blank shortcode"))
        return issues
    kfs = sorted(glob.glob(os.path.join(ASSETS_DIR, f"{shortcode}_keyframe_*.jpg")))
    if not kfs:
        sev = "warning" if not expected else "error"
        issues.append(Issue("ASSET_KF_MISSING", sev, "no keyframes found", shortcode))
        return issues
    for kf in kfs:
        if os.path.getsize(kf) == 0:
            issues.append(Issue("ASSET_KF_EMPTY", "error", "empty keyframe", kf))
        elif not jpeg_magic(kf):
            issues.append(Issue("ASSET_KF_NOT_JPEG", "error",
                                "not a JPEG (missing FF D8 FF signature)", kf))
    # Sequential numbering: indices must be exactly 1..N with no gaps.
    idxs = []
    for kf in kfs:
        m = re.search(r"_(\d{3,})\.jpg$", kf)
        idxs.append(int(m.group(1)) if m else 0)
    if idxs and idxs != list(range(1, len(idxs) + 1)):
        issues.append(Issue("ASSET_KF_GAP", "error",
                            f"keyframe sequence broken: {idxs} (expected 1..{len(idxs)})",
                            shortcode))
    issues.append(Issue("ASSET_KF_OK", "info", f"{len(kfs)} keyframe(s) present", shortcode))
    return issues


def check_mp4(shortcode: str) -> list[Issue]:
    """MP4 is optional in the pipeline (pruned after extraction). Report
    presence + size; a present-but-empty mp4 is always an error."""
    issues: list[Issue] = []
    for suffix in (".mp4", "_5s.mp4"):
        path = os.path.join(ASSETS_DIR, f"{shortcode}{suffix}")
        if not os.path.exists(path):
            issues.append(Issue("ASSET_MP4_ABSENT", "info", f"no {suffix} (optional)", shortcode))
        elif os.path.getsize(path) == 0:
            issues.append(Issue("ASSET_MP4_EMPTY", "error", f"{suffix} present but empty", path))
        else:
            issues.append(Issue("ASSET_MP4_OK", "info",
                                f"{suffix} present: {os.path.getsize(path)} bytes", path))
    return issues


def transcript_issues_for_path(txt: str) -> list[Issue]:
    issues: list[Issue] = []
    if not os.path.exists(txt):
        issues.append(Issue("TRANSCRIPT_MISSING", "error", "transcript missing", txt))
        return issues
    if os.path.getsize(txt) == 0:
        issues.append(Issue("TRANSCRIPT_EMPTY", "error", "transcript is empty", txt))
        return issues
    if not _strict_utf8(txt):
        issues.append(Issue("TRANSCRIPT_NOT_UTF8", "error", "transcript is not valid UTF-8", txt))
        return issues
    text = _read_text_lossy(txt)
    words = count_words(text)
    if words == 0:
        issues.append(Issue("TRANSCRIPT_EMPTY", "error", "transcript has no words", txt))
        return issues
    issues.append(Issue("TRANSCRIPT_OK", "info", f"transcript valid: {words} words", txt))
    return issues


def check_assets(shortcode: str) -> list[Issue]:
    """Full asset suite for one reel. Status-aware: once a reel is ANALYZED
    its media may legitimately have been pruned by cleanup_assets.py."""
    issues: list[Issue] = []
    sc = (shortcode or "").strip()
    if not sc:
        issues.append(Issue("ASSET_BAD_ID", "error", "blank shortcode"))
        return issues
    status = shortcode_status(sc)
    media_expected = status != "ANALYZED"
    if status:
        issues.append(Issue("ASSET_STATUS", "info", f"status={status}", sc))
    else:
        issues.append(Issue("ASSET_STATUS", "warning",
                            "shortcode not found in Reels_Log.xlsx", sc))

    wav = os.path.join(ASSETS_DIR, f"{sc}.wav")
    if not os.path.exists(wav):
        sev = "warning" if not media_expected else "error"
        issues.append(Issue("ASSET_WAV_MISSING", sev, "wav missing", wav))
    else:
        issues += check_wav(wav)

    issues += check_keyframes(sc, expected=media_expected)
    issues += check_mp4(sc)

    # Transcript is required once a reel is at PROCESSED or ANALYZED.
    txt = os.path.join(ASSETS_DIR, f"{sc}.txt")
    if status in ("PROCESSED", "ANALYZED"):
        issues += transcript_issues_for_path(txt)
    elif os.path.exists(txt):
        # Corrupt transcripts are flagged at any stage when present.
        issues += transcript_issues_for_path(txt)
    else:
        issues.append(Issue("TRANSCRIPT_NOT_DUE", "info", "transcript not expected yet", sc))
    return issues


def check_transcript(shortcode: str) -> list[Issue]:
    sc = (shortcode or "").strip()
    if not sc:
        return [Issue("TRANSCRIPT_BAD_ID", "error", "blank shortcode")]
    return transcript_issues_for_path(os.path.join(ASSETS_DIR, f"{sc}.txt"))


def check_asset_file(path: str) -> list[Issue]:
    """Single-file dispatch for `assets --file`."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        return check_wav(path)
    if ext == ".txt":
        return transcript_issues_for_path(path)
    if ext == ".jpg":
        if not os.path.exists(path):
            return [Issue("ASSET_FILE_MISSING", "error", "file missing", path)]
        if os.path.getsize(path) == 0:
            return [Issue("ASSET_KF_EMPTY", "error", "empty jpeg", path)]
        if not jpeg_magic(path):
            return [Issue("ASSET_KF_NOT_JPEG", "error",
                          "not a JPEG (missing FF D8 FF signature)", path)]
        return [Issue("ASSET_KF_OK", "info", f"jpeg valid: {os.path.getsize(path)} bytes", path)]
    if ext == ".mp4":
        if not os.path.exists(path):
            return [Issue("ASSET_FILE_MISSING", "error", "file missing", path)]
        if os.path.getsize(path) == 0:
            return [Issue("ASSET_MP4_EMPTY", "error", "mp4 present but empty", path)]
        return [Issue("ASSET_MP4_OK", "info", f"mp4 present: {os.path.getsize(path)} bytes", path)]
    return [Issue("ASSET_FILE_UNSUPPORTED", "error",
                  f"unsupported asset file type: {ext or '(none)'}", path)]


# ---------------------------------------------------------------------------
# Analysis trio: visual.json + audio.md + retention.md -----------------------
def _parse_factor_rows(lines: list[str]) -> list[tuple[str, int]]:
    """Parse `| **Name** | 7 |` or `| **1. Name** | 8/10 |` table rows."""
    row_re = re.compile(
        r"^\|\s*\*?\*?\s*(?:(\d+)\.\s*)?(.+?)\s*\*?\*?\s*\|\s*(\d+)\s*(?:/\s*10)?\s*(?:\*\*)?\|")
    rows = []
    for line in lines:
        m = row_re.match(line.strip())
        if not m:
            continue
        rows.append((m.group(2).strip(), int(m.group(3))))
    return rows


def _factor_name_warnings(rows: list[tuple[str, int]], code: str) -> list[Issue]:
    issues = []
    canonical = {normalize_factor(f) for f in RETENTION_FACTORS}
    for name, _score in rows:
        if normalize_factor(name) not in canonical:
            issues.append(Issue(code, "warning", f"non-canonical factor name: {name!r}"))
    return issues


def _rubric_section_body(text: str) -> str | None:
    """Body of the '## Rubric Scoring' / '## Rubric Scores' section, or None."""
    m = re.search(r"(?m)^##\s*Rubric\b", text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"(?m)^##\s+", rest)
    return rest if nxt is None else rest[:nxt.start()]


def _retention_overall(text: str) -> Decimal | None:
    m = re.search(r"overall\s+retention\s+score\s*:\s*([\d.]+)\s*/\s*10", text,
                  re.IGNORECASE)
    return Decimal(m.group(1)) if m else None


def check_analysis(shortcode: str) -> list[Issue]:
    issues: list[Issue] = []
    sc = (shortcode or "").strip()
    if not sc:
        issues.append(Issue("ANALYSIS_BAD_ID", "error", "blank shortcode"))
        return issues

    visual    = os.path.join(ANALYSES_DIR, f"{sc}_visual.json")
    audio     = os.path.join(ANALYSES_DIR, f"{sc}_audio.md")
    retention = os.path.join(ANALYSES_DIR, f"{sc}_retention.md")

    for path, code in ((visual, "ANALYSIS_VISUAL_MISSING"),
                       (audio, "ANALYSIS_AUDIO_MISSING"),
                       (retention, "ANALYSIS_RETENTION_MISSING")):
        if not os.path.exists(path):
            issues.append(Issue(code, "error", "analysis file missing", path))
    if not (os.path.exists(visual) and os.path.exists(audio) and os.path.exists(retention)):
        return issues  # can't validate content for a partial trio

    # ---- visual.json ------------------------------------------------------
    data = None
    try:
        with open(visual, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        issues.append(Issue("ANALYSIS_VISUAL_INVALID_JSON", "error",
                            f"invalid JSON: {e}", visual))
    if data is not None:
        if not isinstance(data, dict):
            issues.append(Issue("ANALYSIS_VISUAL_NOT_OBJECT", "error",
                                "visual analysis must be a JSON object", visual))
        else:
            reel_id = data.get("reel_id")
            if reel_id is None:
                issues.append(Issue("ANALYSIS_VISUAL_NO_REELID", "warning",
                                    "legacy visual format: no reel_id key", visual))
            elif str(reel_id) != sc:
                issues.append(Issue("ANALYSIS_VISUAL_REELID_MISMATCH", "error",
                                    f"reel_id {reel_id!r} != {sc!r}", visual))
            for section in VISUAL_REQUIRED_SECTIONS:
                if section not in data:
                    issues.append(Issue("ANALYSIS_VISUAL_SECTION_MISSING", "error",
                                        f"missing section: {section}", visual))
            tactics = data.get("transferable_tactics")
            if isinstance(tactics, list) and not 2 <= len(tactics) <= 4:
                issues.append(Issue(
                    "ANALYSIS_VISUAL_TACTIC_COUNT", "error",
                    f"expected 2-4 transferable tactics, found {len(tactics)}", visual))

    # ---- audio.md ----------------------------------------------------------
    audio_text = _read_text_lossy(audio)
    if not audio_text.strip():
        issues.append(Issue("ANALYSIS_AUDIO_EMPTY", "error", "audio report is empty", audio))
    else:
        transcript_path = os.path.join(ASSETS_DIR, f"{sc}.txt")
        word_count_match = re.search(
            r"(?:word|words)\s+count\s*:\s*(?:\*\*)?\s*(\d+)",
            audio_text, re.IGNORECASE)
        if word_count_match and os.path.exists(transcript_path):
            actual_words = count_words(_read_text_lossy(transcript_path))
            declared_words = int(word_count_match.group(1))
            if declared_words != actual_words:
                issues.append(Issue(
                    "ANALYSIS_AUDIO_WORD_COUNT_MISMATCH", "error",
                    f"audio report declares {declared_words} words; transcript contains "
                    f"{actual_words}", audio))
        for label in AUDIO_REQUIRED_LABELS:
            if not re.search(re.escape(label), audio_text, re.MULTILINE):
                issues.append(Issue("ANALYSIS_AUDIO_LABEL_MISSING", "error",
                                    f"missing section label: {label}", audio))

    # ---- retention.md ------------------------------------------------------
    ret_text = _read_text_lossy(retention)
    if not ret_text.strip():
        issues.append(Issue("ANALYSIS_RETENTION_EMPTY", "error",
                            "retention report is empty", retention))
    rubric = _rubric_section_body(ret_text) if ret_text.strip() else None
    if rubric is None and ret_text.strip():
        issues.append(Issue("ANALYSIS_RETENTION_RUBRIC_SECTION_MISSING", "error",
                            "no '## Rubric Scoring' section", retention))

    if rubric is not None:
        rows = _parse_factor_rows(rubric.splitlines())
        if len(rows) != 8:
            issues.append(Issue("ANALYSIS_RETENTION_FACTOR_COUNT", "error",
                                f"expected exactly 8 retention factors, found {len(rows)}",
                                retention))
        else:
            for name, score in rows:
                if not 1 <= score <= 10:
                    issues.append(Issue("ANALYSIS_RETENTION_SCORE_RANGE", "error",
                                        f"factor {name!r} score {score} outside 1-10", retention))
            issues += _factor_name_warnings(rows, "ANALYSIS_RETENTION_FACTOR_NAME_UNKNOWN")

        overall = _retention_overall(rubric) or _retention_overall(ret_text)
        if overall is None:
            issues.append(Issue("ANALYSIS_RETENTION_OVERALL_MISSING", "error",
                                "no 'Overall Retention Score: X / 10' line", retention))
        elif len(rows) == 8:
            mean = Decimal(sum(s for _n, s in rows)) / Decimal(len(rows))
            if round_half_up(mean) != overall:
                issues.append(Issue(
                    "ANALYSIS_RETENTION_OVERALL_ARITHMETIC", "error",
                    f"overall {overall} != ROUND_HALF_UP mean {round_half_up(mean)} "
                    f"(factors {[s for _n, s in rows]})", retention))
    return issues


def analysis_ok(shortcode: str) -> tuple[bool, list[Issue]]:
    """True when the trio is complete and every check passes (warnings ok)."""
    issues = check_analysis(shortcode)
    return not any(i.severity == "error" for i in issues), issues


# ---------------------------------------------------------------------------
# Script drafts: metadata, rubric table, timestamped shooting script ---------
_TS_RE = re.compile(
    r"^#{3}\s*(\d+:\d+)\s*(?:[–—\-]|to)\s*(\d+:\d+)"
    r"(?:\s*\([^)]*\))?\s*$", re.IGNORECASE)
# Length forms: "**Length:** ~38 seconds (0:00–0:38)"  or  "**Length (s):** 30"
_LENGTH_RANGE_RE = re.compile(r"\*\*Length:\*\*[^\n]*\((\d+:\d+)[^)]*?[–—\-]\s*(\d+:\d+)\)")
_LENGTH_SECONDS_RE = re.compile(r"\*\*Length\s*\(s\):\*\*\s*(\d+)")


def _ts_to_sec(ts: str) -> int:
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def _fmt_sec(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def _parse_declared_length(text: str) -> int | None:
    m = _LENGTH_RANGE_RE.search(text)
    if m:
        return _ts_to_sec(m.group(2))
    m = _LENGTH_SECONDS_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split on `## ` headings. Preamble (H1 title) is excluded."""
    sections = []
    for part in re.split(r"(?m)^##\s+", text)[1:]:
        lines = part.splitlines()
        sections.append((lines[0].strip(), "\n".join(lines[1:])))
    return sections


def _parse_timestamp_blocks(body: str) -> list[tuple[int, int, str]]:
    """Blocks `### 0:00–0:03` ... body until next block / section / rule."""
    blocks = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        m = _TS_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        start, end = _ts_to_sec(m.group(1)), _ts_to_sec(m.group(2))
        chunk = []
        i += 1
        while i < len(lines):
            line = lines[i]
            if _TS_RE.match(line.strip()) or line.strip() == "---":
                break
            chunk.append(line)
            i += 1
        blocks.append((start, end, "\n".join(chunk)))
    return blocks


def _block_field(body: str, field: str) -> str:
    m = re.search(rf"\*\*{field}:\*\*\s*(.+?)(?=\n\*\*|\n#{2,3}|\Z)", body, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Legacy variant: bare 'Voice:' / 'Visual:' / 'On-Screen Text:' labels.
    m = re.search(rf"(?m)^{re.escape(field)}:\s*(.*)$", body)
    return m.group(1).strip() if m else ""


def _script_overall_score(text: str) -> Decimal | None:
    m = re.search(r"\*\*Overall(?: Retention Score)?[^\d]*\s*([\d.]+)\s*/\s*10\b", text)
    return Decimal(m.group(1)) if m else None


def check_script(path: str) -> list[Issue]:
    issues: list[Issue] = []
    text = _read_text_lossy(path)
    if not text.strip():
        issues.append(Issue("SCRIPT_EMPTY", "error", "script file is empty", path))
        return issues

    # ---- canonical metadata -------------------------------------------------
    title_m = re.search(r"(?m)^#\s+(?:Script:?\s*)?(.+?)\s*$", text)
    if not title_m:
        issues.append(Issue("SCRIPT_TITLE_MISSING", "error", "no '# Title' heading", path))
    else:
        issues.append(Issue("SCRIPT_TITLE_OK", "info",
                            f"title: {title_m.group(1).strip()}", path))

    length = _parse_declared_length(text)
    if length is None:
        issues.append(Issue("SCRIPT_LENGTH_MISSING", "error",
                            "no declared length ('**Length:** ~Xs (0:00–0:Xs)' or "
                            "'**Length (s):** N')", path))
    else:
        issues.append(Issue("SCRIPT_LENGTH_OK", "info",
                            f"declared length: {_fmt_sec(length)}", path))

    if "**Framework:**" not in text and "**Pattern tags:**" not in text:
        issues.append(Issue("SCRIPT_FRAMEWORK_MISSING", "warning",
                            "no '**Framework:**' (or '**Pattern tags:**') in metadata", path))
    if not re.search(r"\*\*Estimated Performance Score:\*\*", text) and \
       not re.search(r"\*\*Overall Retention Score:\s*[\d.]+\s*/\s*10", text, re.IGNORECASE):
        issues.append(Issue("SCRIPT_EST_SCORE_MISSING", "warning",
                            "no 'Estimated Performance Score' in metadata", path))

    # ---- eight-factor rubric table -----------------------------------------
    sections = _split_sections(text)
    rubric_section = next((b for h, b in sections
                           if re.search(r"Rubric", h, re.IGNORECASE)), None)
    legacy_bullets = False
    if rubric_section is None:
        # Legacy drafts carry the rubric as a bulleted list under a
        # "Retention & Psychology Explanation (Rubric Scoring)" section.
        legacy_section = next((b for h, b in sections
                               if re.search(r"Retention", h, re.IGNORECASE) and
                               re.search(r"Rubric", h, re.IGNORECASE)), None)
        if legacy_section is not None:
            rubric_section = legacy_section
            legacy_bullets = True
            issues.append(Issue("SCRIPT_LEGACY_RUBRIC", "warning",
                                "legacy rubric format (bulleted, not a table)", path))

    if rubric_section is None:
        issues.append(Issue("SCRIPT_RUBRIC_SECTION_MISSING", "error",
                            "no rubric section ('## Rubric Self-Score' or "
                            "'Retention & Psychology Explanation')", path))
    else:
        rows = []
        if legacy_bullets:
            for line in rubric_section.splitlines():
                m = re.match(r"^-\s*\*{1,2}([^*:]+):\s*(\d+)/10\*{0,2}", line.strip())
                if m:
                    rows.append((m.group(1).strip(), int(m.group(2))))
        else:
            rows = _parse_factor_rows(rubric_section.splitlines())
        if len(rows) != 8:
            issues.append(Issue("SCRIPT_RUBRIC_FACTOR_COUNT", "error",
                                f"expected exactly 8 rubric factors, found {len(rows)}", path))
        else:
            for name, score in rows:
                if not 1 <= score <= 10:
                    issues.append(Issue("SCRIPT_RUBRIC_SCORE_RANGE", "error",
                                        f"factor {name!r} score {score} outside 1-10", path))
            issues += _factor_name_warnings(rows, "SCRIPT_RUBRIC_FACTOR_NAME_UNKNOWN")

            overall = _script_overall_score(text)
            if overall is None:
                issues.append(Issue("SCRIPT_RUBRIC_OVERALL_MISSING", "error",
                                    "no '| **Overall** | **X / 10** |' row", path))
            else:
                mean = Decimal(sum(s for _n, s in rows)) / Decimal(len(rows))
                if round_half_up(mean) != overall:
                    issues.append(Issue(
                        "SCRIPT_RUBRIC_OVERALL_ARITHMETIC", "error",
                        f"overall {overall} != ROUND_HALF_UP mean {round_half_up(mean)} "
                        f"(factors {[s for _n, s in rows]})", path))

    # ---- timestamped shooting script (final section only) -------------------
    final_blocks: list[tuple[int, int, str]] = []
    for _h, body in sections:
        blocks = _parse_timestamp_blocks(body)
        if blocks:
            final_blocks = blocks   # last section with blocks wins
    if not final_blocks:
        if re.search(r"\d+:\d+\s*(?:[–—\-]|to)\s*\d+:\d+", text, re.IGNORECASE):
            issues.append(Issue("SCRIPT_LEGACY_TIMESTAMPS", "warning",
                                "timestamps found but not in '### MM:SS–MM:SS' blocks", path))
        else:
            issues.append(Issue("SCRIPT_TIMESTAMP_SECTION_MISSING", "warning",
                                "no timestamped shooting-script section", path))
        return issues

    seen: set[tuple[int, int]] = set()
    legacy_labels = False
    for i, (start, end, body) in enumerate(final_blocks):
        if not legacy_labels and not re.search(r"\*\*Voice:\*\*", body) and \
                re.search(r"(?m)^Voice:\s*", body):
            legacy_labels = True
        if (start, end) in seen:
            issues.append(Issue("SCRIPT_TIMESTAMP_DUPLICATE", "error",
                                f"duplicate block {_fmt_sec(start)}–{_fmt_sec(end)}", path))
        seen.add((start, end))
        if end < start:
            issues.append(Issue("SCRIPT_TIMESTAMP_REVERSED", "error",
                                f"block {_fmt_sec(start)}–{_fmt_sec(end)} reversed", path))
        if i > 0:
            prev_end = final_blocks[i - 1][1]
            if start < prev_end:
                issues.append(Issue("SCRIPT_TIMESTAMP_OVERLAP", "error",
                                    f"block {_fmt_sec(start)} overlaps previous end "
                                    f"{_fmt_sec(prev_end)}", path))
            elif start > prev_end:
                issues.append(Issue("SCRIPT_TIMESTAMP_GAP", "error",
                                    f"gap: {_fmt_sec(prev_end)} -> {_fmt_sec(start)}", path))
        if i == 0 and start != 0:
            issues.append(Issue("SCRIPT_TIMESTAMP_FIRST_NOT_ZERO", "error",
                                f"first block starts at {_fmt_sec(start)}, not 0:00", path))
        voice  = _block_field(body, "Voice")
        visual = _block_field(body, "Visual")
        ost    = _block_field(body, "On-Screen Text")
        if not voice:
            issues.append(Issue("SCRIPT_BLOCK_VOICE_MISSING", "error",
                                f"block {_fmt_sec(start)}–{_fmt_sec(end)} has no '**Voice:**'", path))
        if not visual:
            issues.append(Issue("SCRIPT_BLOCK_VISUAL_MISSING", "error",
                                f"block {_fmt_sec(start)}–{_fmt_sec(end)} has no '**Visual:**'", path))
        if not ost:
            issues.append(Issue("SCRIPT_BLOCK_OST_MISSING", "warning",
                                f"block {_fmt_sec(start)}–{_fmt_sec(end)} has no '**On-Screen Text:**'",
                                path))
    issues.append(Issue("SCRIPT_TIMESTAMP_BLOCKS", "info",
                        f"{len(final_blocks)} timestamp block(s) parsed", path))
    if legacy_labels:
        issues.append(Issue("SCRIPT_LEGACY_BLOCK_LABELS", "warning",
                            "legacy block labels ('Voice:'/'Visual:' without **bold**)",
                            path))

    if length is not None:
        last_end = final_blocks[-1][1]
        if last_end != length:
            issues.append(Issue("SCRIPT_TIMESTAMP_END_MISMATCH", "error",
                                f"last block ends at {_fmt_sec(last_end)}, declared length "
                                f"{_fmt_sec(length)}", path))

    # CTA / complete-ending advisory on the closing block.
    last_voice = _block_field(final_blocks[-1][2], "Voice")
    if last_voice and not re.search(
            r"\b(save|screenshot|comment|follow|dm\b|message me|share|tag\b|link in bio|"
            r"subscribe|send this)\b", last_voice, re.IGNORECASE):
        issues.append(Issue("SCRIPT_CTA_MISSING", "warning",
                            "closing line has no CTA (save/comment/follow/dm/share)", path))
    if last_voice and re.search(r"(…|\.\.\.|—)\s*$", last_voice.strip()):
        issues.append(Issue("SCRIPT_OPEN_ENDING", "warning",
                            "closing line trails off (ellipsis) — not a complete ending", path))
    return issues


# ---------------------------------------------------------------------------
# PDF: pypdf open, nonempty pages/text, fallback-marker scan -----------------
def check_pdf(path: str, requested_title: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
    except Exception as e:
        issues.append(Issue("PDF_OPEN_FAILED", "error", f"could not open with pypdf: {e}", path))
        return issues
    try:
        if reader.is_encrypted:
            issues.append(Issue("PDF_ENCRYPTED", "error", "PDF is encrypted", path))
            return issues
    except Exception:
        pass
    if not reader.pages:
        issues.append(Issue("PDF_EMPTY_PAGES", "error", "PDF has no pages", path))
        return issues
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:
            issues.append(Issue("PDF_TEXT_EXTRACT_FAILED", "error",
                                f"could not extract text from page: {e}", path))
    text = "\n".join(parts)
    if not text.strip():
        issues.append(Issue("PDF_NO_TEXT", "error", "PDF has no extractable text", path))
        return issues
    if "Untitled" in text:
        issues.append(Issue("PDF_TITLE_FALLBACK", "error",
                            "fallback title 'Untitled' present (missing '# Title' in source)", path))
    if re.search(r"Framework\s*:\s*(?:—|–|-)", text):
        issues.append(Issue("PDF_FRAMEWORK_FALLBACK", "error",
                            "fallback 'Framework: —' present (missing framework metadata)", path))
    if requested_title and requested_title.lower() not in text.lower():
        issues.append(Issue("PDF_TITLE_MISSING", "error",
                            f"requested title {requested_title!r} not found in PDF text", path))
    issues.append(Issue("PDF_OK", "info",
                        f"PDF valid: {len(reader.pages)} page(s), {len(text.strip())} chars", path))
    return issues


# ---------------------------------------------------------------------------
# CLI ------------------------------------------------------------------------
def _dispatch(command: str, shortcode: str, file: str,
              requested_title: str | None) -> list[tuple[str, list[Issue]]]:
    sc = (shortcode or "").strip()
    if command == "assets":
        if file:
            return [("assets-file", check_asset_file(file))]
        return [("assets", check_assets(sc))]
    if command == "analysis":
        return [("analysis", check_analysis(sc))]
    if command == "script":
        return [("script", check_script(file))]
    if command == "pdf":
        return [("pdf", check_pdf(file, requested_title))]
    if command == "all":
        checks = []
        if sc:
            checks.append(("assets", check_assets(sc)))
            checks.append(("transcript", check_transcript(sc)))
            checks.append(("analysis", check_analysis(sc)))
        if file:
            ext = os.path.splitext(file)[1].lower()
            if ext == ".pdf":
                checks.append(("pdf", check_pdf(file, requested_title)))
            elif ext == ".md":
                checks.append(("script", check_script(file)))
            else:
                checks.append(("assets-file", check_asset_file(file)))
        return checks
    raise ValueError(f"unknown command: {command}")


def _print_human(checks: list[tuple[str, list[Issue]]], strict: bool) -> int:
    total = {"info": 0, "warning": 0, "error": 0}
    for group, issues in checks:
        for issue in issues:
            total[issue.severity] += 1
            tag = issue.severity.upper()
            where = f"  [{issue.file}]" if issue.file else ""
            print(f"   [{tag:7s}] {issue.code}: {issue.message}{where}")
    fail = total["error"] or (strict and total["warning"])
    print(f"\n[{ 'FAIL' if fail else 'PASS' }] "
          f"info={total['info']} warning={total['warning']} error={total['error']}"
          f"{'  (--strict: warnings count as errors)' if strict else ''}")
    return 1 if fail else 0


def _print_json(checks: list[tuple[str, list[Issue]]], strict: bool) -> int:
    issues = []
    for group, group_issues in checks:
        for issue in group_issues:
            issues.append({
                "group": group,
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "file": issue.file,
            })
    summary = {"info": 0, "warning": 0, "error": 0}
    for issue in issues:
        summary[issue["severity"]] += 1
    fail = summary["error"] or (strict and summary["warning"])
    print(json.dumps({
        "ok": not fail,
        "strict": strict,
        "summary": summary,
        "issues": issues,
    }, indent=2))
    return 1 if fail else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="preflight",
        description="Read-only health checks for assets, transcripts, analysis trios, "
                    "script drafts and generated PDFs. Never mutates files.")
    parser.add_argument("command", choices=["assets", "analysis", "script", "pdf", "all"],
                        help="What to check")
    parser.add_argument("--shortcode", default="", help="Reel shortcode to check")
    parser.add_argument("--file", default="", help="Path to a specific file to check")
    parser.add_argument("--title", default=None, help="Expected title inside the PDF (pdf command)")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors (affects exit code)")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable JSON report")
    args = parser.parse_args(argv)

    if args.command in ("analysis", "assets", "all") and \
            not args.shortcode.strip() and not args.file.strip():
        print(f"[ERROR] '{args.command}' needs --shortcode <id> or --file <path>")
        return 2
    if args.command in ("script", "pdf") and not args.file.strip():
        print(f"[ERROR] '{args.command}' needs --file <path>")
        return 2

    try:
        checks = _dispatch(args.command, args.shortcode, args.file, args.title)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 2

    if not checks:
        print("[INFO] Nothing to check.")
        return 0
    return _print_json(checks, args.strict) if args.json else \
        _print_human(checks, args.strict)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
