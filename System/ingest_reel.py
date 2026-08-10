"""
ingest_reel.py  —  STEP 2a: download one Instagram Reel + extract derived assets.
==================================================================================
Downloads a reel via yt-dlp, then extracts:

    <id>.wav                 mono-ish audio for Whisper transcription
    <id>_keyframe_%03d.jpg   1 frame per second for the first 5 seconds

The full .mp4 is kept by ingest_reel (the batch processor prunes it itself).

Usage:
    uv run System/ingest_reel.py <reel_url> [--cookies cookies.txt]
"""

import os
import re
import sys
import glob
import wave
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import yt_dlp

# Instagram shortcodes are base64-ish: letters, digits, '_' and '-'.
SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def get_video_id(url: str) -> str:
    """Extract an Instagram shortcode from /reel/, /reels/ or /p/ URLs.

    Returns "" (never "unknown_video") when nothing valid can be parsed, so
    callers can reject malformed URLs instead of silently proceeding.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    for key in ("reel", "reels", "p"):
        if key in parts:
            idx = parts.index(key)
            if idx + 1 < len(parts):
                candidate = parts[idx + 1]
                if SHORTCODE_RE.match(candidate):
                    return candidate
    m = re.search(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def derived_assets_valid(output_dir: str, video_id: str) -> bool:
    """True when a previous run left usable wav + keyframes on disk.

    Existence alone is never enough — an empty or corrupt file is treated as
    missing so it is re-extracted rather than reused as a cache hit.
    """
    if not video_id:
        return False
    wav_path = os.path.join(output_dir, f"{video_id}.wav")
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        return False
    try:
        with wave.open(wav_path, "rb") as w:
            if w.getnframes() <= 0 or w.getframerate() <= 0:
                return False
    except (wave.Error, EOFError, OSError):
        return False
    keyframes = glob.glob(os.path.join(output_dir, f"{video_id}_keyframe_*.jpg"))
    if not keyframes:
        return False
    for kf in keyframes:
        if os.path.getsize(kf) == 0:
            return False
        with open(kf, "rb") as f:
            if f.read(3) != b"\xff\xd8\xff":
                return False
    return True


def download_reel(url: str, output_dir: str, cookies_path: str | None = None,
                  video_id: str | None = None):
    """Download a reel into output_dir and return (video_path, video_id).

    `video_id` is an optional canonical override — the batch processor passes
    the Excel row shortcode so derived assets always use that id even when the
    URL path differs. On malformed/unknown URLs a ValueError is raised; on a
    download failure the error is printed and (None, None) is returned (legacy
    callers rely on the tuple contract).
    """
    rid = (video_id or "").strip() if video_id else ""
    if not rid:
        rid = get_video_id(url)
    if not rid:
        raise ValueError(f"could not extract a valid Instagram shortcode from URL: {url!r}")
    if not SHORTCODE_RE.match(rid):
        raise ValueError(f"invalid shortcode derived from URL: {rid!r}")

    base_name = os.path.join(output_dir, rid)

    # Reuse a previously downloaded, nonempty source file when present.
    for ext in (".mp4", ".m4a", ".webm", ".mkv"):
        existing = f"{base_name}{ext}"
        if os.path.exists(existing) and os.path.getsize(existing) > 0:
            print(f"Reusing existing media {existing}")
            return existing, rid

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{base_name}.%(ext)s',
        'quiet': False,
        'no_warnings': True,
        'extract_flat': False,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    print(f"Downloading {url}...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info_dict)
            if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
                # Fallback to base_name if ydl's prepare_filename is weird.
                video_path = f"{base_name}.mp4"
                if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
                    raise RuntimeError(f"downloaded file missing or empty for {url}")
            print(f"Video downloaded to {video_path}")
            return video_path, rid
    except Exception as e:
        print(f"Failed to download Reel: {e}")
        return None, None


def _run_ffmpeg(cmd: list[str], step: str) -> None:
    """Run ffmpeg and fail loudly on a nonzero return code."""
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-5:]
        detail = "\n".join(tail) if tail else "(no ffmpeg stderr)"
        raise RuntimeError(f"ffmpeg {step} failed (rc={result.returncode}):\n{detail}")


def extract_assets(video_path: str, output_dir: str, video_id: str) -> dict:
    """Extract .wav + keyframes for video_id. Raises on any failure so callers
    never treat a half-finished extraction as success.

    Audio extraction and first-5-second keyframe extraction are independent
    FFmpeg jobs, so they run in parallel inside a small bounded executor
    (max 2 workers). If either job fails the function raises — a partial
    extraction is never reported as success.

    Valid derived assets from a previous run are reused (content-checked, so
    empty/corrupt files are never mistaken for cache hits). Stale keyframes
    from a failed run are removed before a fresh extraction.
    """
    if not video_id:
        raise ValueError("extract_assets requires a video_id")

    wav_path          = os.path.join(output_dir, f"{video_id}.wav")
    keyframes_pattern = os.path.join(output_dir, f"{video_id}_keyframe_%03d.jpg")

    if derived_assets_valid(output_dir, video_id):
        print(f"Reusing valid derived assets for {video_id}")
        return {
            "full_video": video_path,
            "audio": wav_path,
            "keyframes": os.path.join(output_dir, f"{video_id}_keyframe_*.jpg"),
        }

    # Remove stale artifacts from a previous failed run before extracting.
    for stale in glob.glob(os.path.join(output_dir, f"{video_id}_keyframe_*.jpg")):
        try:
            os.remove(stale)
        except OSError:
            pass
    if os.path.exists(wav_path):
        try:
            os.remove(wav_path)
        except OSError:
            pass

    def _audio_job() -> None:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', video_path,
            '-q:a', '0', '-map', 'a', wav_path,
        ], "audio extraction")

    def _keyframe_job() -> None:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', video_path,
            '-t', '5', '-vf', 'fps=1', keyframes_pattern,
        ], "keyframe extraction")

    print("Extracting audio + keyframes in parallel...")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_audio_job), pool.submit(_keyframe_job)]
        # The first failing job re-raises here; the executor's shutdown still
        # waits for the sibling job before this function returns.
        for fut in futures:
            fut.result()

    if not derived_assets_valid(output_dir, video_id):
        raise RuntimeError(
            f"extraction produced invalid assets for {video_id} "
            "(missing/empty wav or keyframes)")

    print("Extraction complete.")
    return {
        "full_video": video_path,
        "audio": wav_path,
        "keyframes": os.path.join(output_dir, f"{video_id}_keyframe_*.jpg"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest an Instagram Reel into the Assets directory.")
    parser.add_argument("url", help="Instagram Reel URL")
    parser.add_argument("--cookies", dest="cookies", default=None,
                        help="Path to a cookies.txt file to pass to yt-dlp as cookiefile")
    args = parser.parse_args()

    if args.cookies and not os.path.exists(args.cookies):
        print(f"Error: cookies file not found at '{args.cookies}'")
        sys.exit(1)

    # Setup directories
    workspace  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assets_dir = os.path.join(workspace, "Assets")
    os.makedirs(assets_dir, exist_ok=True)

    # Download and extract
    try:
        video_path, video_id = download_reel(args.url, assets_dir, cookies_path=args.cookies)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    if not video_path:
        print("Error: download failed — see messages above.")
        sys.exit(1)

    try:
        assets = extract_assets(video_path, assets_dir, video_id)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("\n--- Asset Paths ---")
    for key, val in assets.items():
        print(f"{key}: {val}")
