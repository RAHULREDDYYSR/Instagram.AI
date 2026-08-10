"""
transcribe.py  —  STEP 3: Whisper transcription for downloaded reels.
=====================================================================
Finds every Assets/<shortcode>.wav that has no valid sibling transcript and
transcribes it via the OpenAI Whisper API (uses OPENAI_API_KEY from .env).
Transcripts are the input for the audio-analysis skill — agents cannot read
.wav files directly.

Only a NONEMPTY, valid-UTF-8 <id>.txt counts as cached; empty or corrupt
transcripts are re-transcribed. Transcripts are written atomically (temp file
+ os.replace) so a crash mid-write can never leave a partial file.

Usage:
    uv run System/transcribe.py                                  # all pending transcripts
    uv run System/transcribe.py --shortcode DbniTzWOl-H          # single reel
    uv run System/transcribe.py --shortcodes DbniTzWOl-H AbC123  # several reels
    uv run System/transcribe.py --limit 5
    uv run System/transcribe.py --workers 4
"""

import os, sys, glob, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from preflight import count_words   # canonical word counter (shared)

# ---------------------------------------------------------------------------
WORKSPACE  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ASSETS_DIR     = os.path.join(WORKSPACE, "Assets")
MODEL          = "whisper-1"


# ---------------------------------------------------------------------------
def _valid_transcript(txt_path: str) -> bool:
    """True only when the transcript is nonempty and decodes as UTF-8."""
    if not os.path.exists(txt_path) or os.path.getsize(txt_path) == 0:
        return False
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, OSError):
        return False
    return count_words(text) > 0


def find_pending(shortcode: str = "", limit: int = 0,
                 shortcodes: list[str] | None = None) -> list:
    """WAV files in Assets/ that need a transcript.

    A sibling .txt only counts as cached when it is valid (nonempty UTF-8);
    empty/corrupt transcripts are treated as pending and re-transcribed.
    """
    if shortcodes:
        wavs = [os.path.join(ASSETS_DIR, f"{s.strip()}.wav")
                for s in shortcodes if s and s.strip()]
    elif shortcode:
        wavs = [os.path.join(ASSETS_DIR, f"{shortcode.strip()}.wav")]
    else:
        wavs = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.wav")))

    pending = []
    for wav in wavs:
        if not os.path.exists(wav):
            continue  # missing targets are reported by the caller
        txt = os.path.splitext(wav)[0] + ".txt"
        if not _valid_transcript(txt):
            pending.append(wav)
    if limit > 0:
        pending = pending[:limit]
    return pending


def transcribe_file(client, wav_path: str) -> str:
    """Transcribe one WAV via Whisper; write <id>.txt atomically next to it."""
    txt_path = os.path.splitext(wav_path)[0] + ".txt"
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=MODEL,
            file=f,
            response_format="text",
        )
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    text = text.strip()
    if not text:
        raise RuntimeError("Whisper returned an empty transcript")

    # Atomic write: temp file in the same dir, then os.replace.
    tmp_path = txt_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(tmp_path, txt_path)
    return txt_path


# ---------------------------------------------------------------------------
def transcribe_pending(shortcode: str = "", limit: int = 0,
                       workers: int = 3,
                       shortcodes: list[str] | None = None) -> int:
    """Entry point used by CLI and by process_reels.py. Returns count done."""
    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY not set in .env — skipping transcription")
        return 0

    explicit = [s.strip() for s in (list(shortcodes or []) + ([shortcode] if shortcode else []))
                if s and s.strip()]

    failed = 0
    if explicit:
        # Report explicit targets that have no wav on disk as per-target failures.
        existing = {os.path.splitext(os.path.basename(w))[0]
                    for w in glob.glob(os.path.join(ASSETS_DIR, "*.wav"))}
        for rid in explicit:
            if rid not in existing:
                print(f"   [FAIL] {rid}: no Assets/{rid}.wav")
                failed += 1
        pending = find_pending(shortcodes=explicit)
    else:
        pending = find_pending(limit=limit)

    if not pending:
        if explicit:
            print(f"[TRANSCRIBE] Done:0  Failed:{failed}")
        else:
            print("[INFO] No reels awaiting transcription.")
        return 0

    try:
        from openai import OpenAI
    except ImportError:
        print("[WARN] 'openai' package missing — run: uv add openai")
        return 0

    client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"\n[TRANSCRIBE] {len(pending)} reel(s) pending  |  model={MODEL}  |  workers={workers}")

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(transcribe_file, client, wav): wav
                   for wav in pending}
        for fut in as_completed(futures):
            wav = futures[fut]
            rid = os.path.splitext(os.path.basename(wav))[0]
            try:
                txt_path = fut.result()
                with open(txt_path, encoding="utf-8") as f:
                    words = count_words(f.read())
                print(f"   [OK]   {rid}  ({words} words)")
                done += 1
            except Exception as e:
                print(f"   [FAIL] {rid}: {e}")
                failed += 1

    print(f"[TRANSCRIBE] Done:{done}  Failed:{failed}")
    return done


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortcode", default="",
                        help="Transcribe a single reel by shortcode")
    parser.add_argument("--shortcodes", nargs="+", default=None,
                        help="Transcribe one or more reels by shortcode (exact targeting)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max reels to transcribe (0 = all pending)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel Whisper API calls")
    args = parser.parse_args()
    transcribe_pending(shortcode=args.shortcode, limit=args.limit,
                       workers=args.workers, shortcodes=args.shortcodes)
