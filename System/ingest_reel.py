import os
import sys
import argparse
import subprocess
from urllib.parse import urlparse

import yt_dlp

def get_video_id(url):
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    if 'reel' in path_parts or 'p' in path_parts:
        try:
            return path_parts[path_parts.index('reel') + 1]
        except ValueError:
            pass
        try:
            return path_parts[path_parts.index('p') + 1]
        except ValueError:
            pass
    return "unknown_video"

def download_reel(url, output_dir, cookies_path=None):
    video_id = get_video_id(url)
    base_name = os.path.join(output_dir, video_id)
    
    # yt-dlp options
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
            if not os.path.exists(video_path):
                # Fallback to base_name if ydl prepare filename is weird
                video_path = f"{base_name}.mp4"
            print(f"Video downloaded to {video_path}")
            return video_path, video_id
    except Exception as e:
        print(f"Failed to download Reel: {e}")
        return None, None

def extract_assets(video_path, output_dir, video_id):
    print("Extracting audio...")
    audio_path = os.path.join(output_dir, f"{video_id}.wav")
    subprocess.run([
        'ffmpeg', '-y', '-i', video_path,
        '-q:a', '0', '-map', 'a', audio_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Extracting keyframes (1 per second for first 5s)...")
    keyframes_pattern = os.path.join(output_dir, f"{video_id}_keyframe_%03d.jpg")
    subprocess.run([
        'ffmpeg', '-y', '-i', video_path,
        '-t', '5', '-vf', 'fps=1', keyframes_pattern
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Extraction complete.")
    return {
        "full_video": video_path,
        "audio": audio_path,
        "keyframes": os.path.join(output_dir, f"{video_id}_keyframe_*.jpg")
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest an Instagram Reel into the Assets directory.")
    parser.add_argument("url", help="Instagram Reel URL")
    parser.add_argument("--cookies", dest="cookies", default=None,
                        help="Path to a cookies.txt file to pass to yt-dlp as cookiefile")
    args = parser.parse_args()

    url = args.url
    cookies_path = args.cookies

    if cookies_path and not os.path.exists(cookies_path):
        print(f"Error: cookies file not found at '{cookies_path}'")
        sys.exit(1)
    
    # Setup directories
    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assets_dir = os.path.join(workspace, "Assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # Download and extract
    video_path, video_id = download_reel(url, assets_dir, cookies_path=cookies_path)
    if video_path:
        assets = extract_assets(video_path, assets_dir, video_id)
        print("\n--- Asset Paths ---")
        for key, val in assets.items():
            print(f"{key}: {val}")
