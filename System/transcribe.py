"""
transcribe.py  —  STEP 3: Whisper transcription for downloaded reels.
=====================================================================
Finds every Assets/<shortcode>.wav that has no matching
Assets/<shortcode>.txt and transcribes it via the OpenAI Whisper API
(uses OPENAI_API_KEY from .env). Transcripts are the input for the
audio-analysis skill — agents cannot read .wav files directly.

Usage:
    uv run System/transcribe.py                      # all pending transcripts
    uv run System/transcribe.py --shortcode DbniTzWOl-H
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

# ---------------------------------------------------------------------------
WORKSPACE  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(WORKSPACE, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ASSETS_DIR     = os.path.join(WORKSPACE, "Assets")
MODEL          = "whisper-1"


# ---------------------------------------------------------------------------
def find_pending(shortcode: str = "", limit: int = 0) -> list:
    """WAV files in Assets/ that have no sibling .txt transcript yet."""
    if shortcode:
        wav = os.path.join(ASSETS_DIR, f"{shortcode}.wav")
        wavs = [wav] if os.path.exists(wav) else []
    else:
        wavs = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.wav")))

    pending = []
    for wav in wavs:
        txt = os.path.splitext(wav)[0] + ".txt"
        if not os.path.exists(txt):
            pending.append(wav)
    if limit > 0:
        pending = pending[:limit]
    return pending


def transcribe_file(client, wav_path: str) -> str:
    """Transcribe one WAV via Whisper; write <id>.txt next to it."""
    txt_path = os.path.splitext(wav_path)[0] + ".txt"
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=MODEL,
            file=f,
            response_format="text",
        )
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    return txt_path


# ---------------------------------------------------------------------------
def transcribe_pending(shortcode: str = "", limit: int = 0,
                       workers: int = 3) -> int:
    """Entry point used by CLI and by process_reels.py. Returns count done."""
    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY not set in .env — skipping transcription")
        return 0

    pending = find_pending(shortcode=shortcode, limit=limit)
    if not pending:
        print("[INFO] No reels awaiting transcription.")
        return 0

    try:
        from openai import OpenAI
    except ImportError:
        print("[WARN] 'openai' package missing — run: uv add openai")
        return 0

    client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"\n[TRANSCRIBE] {len(pending)} reel(s) pending  |  model={MODEL}  |  workers={workers}")

    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(transcribe_file, client, wav): wav
                   for wav in pending}
        for fut in as_completed(futures):
            wav = futures[fut]
            rid = os.path.splitext(os.path.basename(wav))[0]
            try:
                txt_path = fut.result()
                words = len(open(txt_path, encoding="utf-8").read().split())
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
    parser.add_argument("--limit", type=int, default=0,
                        help="Max reels to transcribe (0 = all pending)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel Whisper API calls")
    args = parser.parse_args()
    transcribe_pending(shortcode=args.shortcode, limit=args.limit,
                       workers=args.workers)
