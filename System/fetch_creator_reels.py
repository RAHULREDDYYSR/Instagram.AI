import argparse
import os
import json
import http.cookiejar
import instaloader
from datetime import datetime
from ingest_reel import download_reel, extract_assets

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(WORKSPACE, "Assets")
REGISTRY_PATH = os.path.join(WORKSPACE, "Brain", "Creators", "_registry.json")
COOKIES_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")

def load_registry():
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {"creators": []}

def save_registry(registry):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)

def get_creator_info(registry, username):
    for creator in registry["creators"]:
        if creator["username"].lower() == username.lower():
            return creator
    return None

def update_creator_info(registry, username, new_reels):
    creator = get_creator_info(registry, username)
    if not creator:
        creator = {
            "username": username,
            "processed_reels": [],
            "added_on": datetime.now().isoformat()
        }
        registry["creators"].append(creator)
    
    creator["processed_reels"].extend(new_reels)
    creator["processed_reels"] = list(set(creator["processed_reels"]))
    save_registry(registry)
    return creator

def main():
    parser = argparse.ArgumentParser(description="Fetch and ingest reels from an Instagram creator.")
    parser.add_argument("--username", required=True, help="Instagram username of the creator")
    parser.add_argument("--max-reels", type=int, default=10, help="Max number of new reels to process")
    args = parser.parse_args()

    # 1. Setup Instaloader and Cookies
    L = instaloader.Instaloader(quiet=True)
    L.context._session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    })
    
    if os.path.exists(COOKIES_PATH):
        print(f"Loading cookies from {COOKIES_PATH}...")
        cj = http.cookiejar.MozillaCookieJar(COOKIES_PATH)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            for cookie in cj:
                L.context._session.cookies.set_cookie(cookie)
            
            # Extract CSRF token
            csrf_token = L.context._session.cookies.get("csrftoken", domain=".instagram.com")
            if csrf_token:
                L.context._session.headers.update({"X-CSRFToken": csrf_token})
        except Exception as e:
            print(f"Error loading cookies: {e}")
    else:
        print(f"Warning: {COOKIES_PATH} not found. Proceeding without authentication (may be rate-limited).")

    # 2. Load Registry
    registry = load_registry()
    creator = get_creator_info(registry, args.username)
    processed_reels = set(creator["processed_reels"]) if creator else set()

    # 3. Fetch Profile and Reels
    print(f"\nFetching profile data for @{args.username}...")
    try:
        profile = instaloader.Profile.from_username(L.context, args.username)
    except Exception as e:
        print(f"Failed to fetch profile: {e}")
        return

    print(f"Found profile: {profile.full_name} ({profile.followers} followers)")
    
    new_reels_found = []
    processed_count = 0

    print(f"Scanning for new reels (up to {args.max_reels})...")
    for post in profile.get_posts():
        if processed_count >= args.max_reels:
            break
            
        if not post.is_video:
            continue
            
        shortcode = post.shortcode
        if shortcode in processed_reels:
            print(f"Skipping {shortcode} - already processed.")
            continue
            
        print(f"\nProcessing new reel: {shortcode}...")
        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
        
        # Download and extract using existing logic
        video_path, video_id = download_reel(reel_url, ASSETS_DIR)
        
        if video_path and os.path.exists(video_path):
            try:
                extract_assets(video_path, ASSETS_DIR, video_id)
                new_reels_found.append(shortcode)
                processed_count += 1
                print(f"Successfully fully ingested {shortcode}")
            except Exception as e:
                print(f"Failed to extract assets for {shortcode}: {e}")
        else:
            print(f"Download failed for {shortcode}.")

    # 4. Update Registry
    if new_reels_found:
        update_creator_info(registry, args.username, new_reels_found)
        print(f"\nDone! Processed {len(new_reels_found)} new reels.")
    else:
        print("\nNo new reels found or successfully processed.")

if __name__ == "__main__":
    main()
