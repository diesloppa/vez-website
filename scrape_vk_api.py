"""
Fetches all videos and playlists from a VK community using the VK API.

Reads credentials from config.json:
  vk_token  — permanent offline token (obtain via Kate Mobile OAuth)
  owner_id  — community owner_id (negative for communities, e.g. -123456789)

Output: vk_raw_data.enc.json
  {
    "owner_id": int,
    "playlists": {
      "<album_id>": {
        "id": int, "name": str, "count": int,
        "videos": [<normalized_video>, ...]
      }
    },
    "all_videos": [<normalized_video>, ...]
  }
"""
import os
import time
import requests
from crypto_utils import dump_encrypted_json, get_password, load_json
from vk_config import load_vk_config

API_VERSION = "5.199"
OUTPUT = "vk_raw_data.json"
OUTPUT_ENCRYPTED = "vk_raw_data.enc.json"

# ── Load credentials ──────────────────────────────────────────────────────────
_cfg = load_vk_config()
TOKEN    = _cfg["vk_token"]
OWNER_ID = _cfg["owner_id"]

session = requests.Session()


# ── API wrapper ───────────────────────────────────────────────────────────────
def api(method: str, **params):
    """Call a VK API method. Returns response['response'] or None on error."""
    params.update({"access_token": TOKEN, "v": API_VERSION})
    delay = 0.5
    for attempt in range(8):
        try:
            r = session.get(f"https://api.vk.com/method/{method}", params=params, timeout=30)
            data = r.json()
        except requests.RequestException as e:
            if attempt == 7:
                print(f"  Request error [{method}]: {e}")
                return None
            time.sleep(delay)
            delay *= 2
            continue

        if "error" not in data:
            return data.get("response")

        err = data["error"]
        if err.get("error_code") == 6 and attempt < 7:
            time.sleep(delay)
            delay = min(delay * 2, 8)
            continue

        print(f"  API error [{method}]: {err}")
        return None

    return None


def load_existing() -> dict:
    if not os.path.exists(OUTPUT) and not os.path.exists(OUTPUT_ENCRYPTED):
        return {}
    data = load_json(OUTPUT, OUTPUT_ENCRYPTED)
    if data.get("owner_id") != OWNER_ID:
        return {}
    return data


# ── Albums (playlists) ────────────────────────────────────────────────────────
def get_all_albums() -> list:
    """Fetch every video album from the community, paginating as needed."""
    albums = []
    offset = 0
    while True:
        resp = api(
            "video.getAlbums",
            owner_id=OWNER_ID,
            count=100,
            offset=offset,
            need_system=1,
            extended=1,
        )
        if not resp:
            break
        items = resp.get("items", [])
        albums.extend(items)
        print(f"  Albums loaded: {len(albums)} / {resp.get('count', '?')}")
        if len(albums) >= resp.get("count", 0):
            break
        offset += 100
        time.sleep(0.34)
    return albums


# ── Videos ───────────────────────────────────────────────────────────────────
def get_videos_in_album(album_id: int | None = None) -> list:
    """
    Fetch all videos from a specific album, or all community videos if album_id is None.
    Uses video.get with extended=1 to get image arrays and other metadata.
    """
    videos = []
    offset = 0
    while True:
        kwargs = dict(owner_id=OWNER_ID, count=200, offset=offset, extended=1)
        if album_id is not None:
            kwargs["album_id"] = album_id
        resp = api("video.get", **kwargs)
        if not resp:
            break
        items = resp.get("items", [])
        videos.extend(items)
        total = resp.get("count", 0)
        if offset == 0:
            print(f"    Total in album: {total}")
        if not items or len(videos) >= total:
            break
        offset += 200
        time.sleep(0.34)
    return videos


def best_thumbnail(v: dict) -> str:
    """
    Pick the largest thumbnail URL from the video's image array.
    VK API v5.199+ returns image: [{url, width, height}, ...] instead of photo_640 / photo_800.
    """
    images = v.get("image") or v.get("first_frame") or []
    if not images:
        return ""
    best = max(images, key=lambda x: x.get("width", 0))
    return best.get("url", "")


def normalize_video(v: dict) -> dict:
    """Convert a raw VK API video object to a clean, flat dict."""
    vid_id   = f"{v['owner_id']}_{v['id']}"
    dur_sec  = v.get("duration", 0)
    hours, remainder = divmod(dur_sec, 3600)
    mins, secs       = divmod(remainder, 60)
    duration = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"

    return {
        "id":           vid_id,
        "title":        v.get("title", ""),
        "description":  v.get("description", ""),
        "url":          f"https://vk.com/video{vid_id}",
        "thumbnail":    best_thumbnail(v),
        "duration":     duration,
        "duration_sec": dur_sec,
        "date":         v.get("date", 0),         # Unix timestamp
        "views":        v.get("views", 0),
        "added_at":     v.get("adding_date", 0),  # when added to community
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    existing = load_existing()
    existing_playlists = existing.get("playlists", {})

    print("=== Fetching albums ===")
    albums_raw = get_all_albums()
    print(f"Total albums: {len(albums_raw)}")
    for a in albums_raw:
        print(f"  [{a['id']}] {a['title']} — {a.get('count', '?')} videos")

    print("\n=== Fetching videos per album ===")
    playlists = {}
    for album in albums_raw:
        aid  = album["id"]
        name = album["title"]
        pid = str(aid)
        updated_time = album.get("updated_time", 0)
        album_count = album.get("count", 0)

        cached = existing_playlists.get(pid)
        can_reuse = (
            cached
            and cached.get("name") == name
            and cached.get("count") == album_count
            and cached.get("updated_time", 0) == updated_time
            and isinstance(cached.get("videos"), list)
            and len(cached.get("videos", [])) == album_count
        )

        if can_reuse:
            print(f"  Album: {name} (id={aid}) — reuse cached")
            normalized_videos = cached["videos"]
        else:
            print(f"  Album: {name} (id={aid}) — fetch")
            vids = get_videos_in_album(album_id=aid)
            normalized_videos = [normalize_video(v) for v in vids]

        playlists[str(aid)] = {
            "id":           aid,
            "name":         name,
            "count":        album.get("count", len(normalized_videos)),
            "updated_time": updated_time,
            "videos":       normalized_videos,
        }

    # video.get without album_id only returns the system "Добавленные" album.
    # It is not used by the site builder, so keep the previous snapshot if present
    # instead of spending extra requests every run.
    all_videos = existing.get("all_videos", [])
    print(f"\nReuse all_videos snapshot: {len(all_videos)}")

    result = {
        "owner_id":  OWNER_ID,
        "playlists": playlists,
        "all_videos": all_videos,
    }

    password = get_password(required=True)
    dump_encrypted_json(result, OUTPUT_ENCRYPTED, password)

    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)

    print(f"\nSaved to {OUTPUT_ENCRYPTED}")
    all_ids = {v["id"] for v in all_videos}
    pl_ids  = {v["id"] for pl in playlists.values() for v in pl["videos"]}
    print(f"Unique in playlists : {len(pl_ids)}")
    print(f"Unique in all       : {len(all_ids)}")
    print(f"Combined unique     : {len(all_ids | pl_ids)}")


if __name__ == "__main__":
    main()
