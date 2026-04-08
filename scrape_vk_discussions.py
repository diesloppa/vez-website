"""
Fetches VK discussion topics and comments for the archive community.

Output: vk_discussions.json
  {
    "<topic_id>": {
      "title": "СЕРИАЛЫ ЗЕЛЁНЫЙ",
      "comments": [{ "id": 1, "text": "..." }]
    }
  }
"""
import json
import os
import time
import requests
from vk_config import load_vk_config

API_VERSION = "5.199"
OUTPUT = "vk_discussions.json"

_cfg = load_vk_config()
TOKEN = _cfg["vk_token"]
GROUP_ID = _cfg["group_id"]

session = requests.Session()


def api(method: str, **params):
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
    if not os.path.exists(OUTPUT):
        return {}
    with open(OUTPUT, encoding="utf-8") as f:
        return json.load(f)


def get_all_topics() -> list:
    topics = []
    offset = 0
    while True:
        resp = api("board.getTopics", group_id=GROUP_ID, count=100, offset=offset, extended=0)
        if not resp:
            break
        items = resp.get("items", [])
        topics.extend(items)
        print(f"  Topics loaded: {len(topics)} / {resp.get('count', '?')}")
        if len(topics) >= resp.get("count", 0):
            break
        offset += 100
        time.sleep(0.34)
    return topics


def get_all_comments(topic_id: int) -> list:
    comments = []
    offset = 0
    while True:
        resp = api(
            "board.getComments",
            group_id=GROUP_ID,
            topic_id=topic_id,
            count=100,
            offset=offset,
            extended=0,
            sort="asc",
        )
        if not resp:
            break
        items = resp.get("items", [])
        comments.extend(items)
        total = resp.get("count", 0)
        if not items or len(comments) >= total:
            break
        offset += 100
        time.sleep(0.34)
    return comments


def main():
    existing = load_existing()

    print("=== Fetching board topics ===")
    topics = get_all_topics()
    print(f"Total topics: {len(topics)}")

    result = {}
    for topic in topics:
        tid = topic["id"]
        tid_s = str(tid)
        title = topic.get("title", "")
        comment_count = topic.get("comments", 0)

        cached = existing.get(tid_s)
        can_reuse = (
            cached
            and cached.get("title") == title
            and len(cached.get("comments", [])) == comment_count
        )

        if can_reuse:
            print(f"  Topic: [{tid}] {title} — reuse cached")
            comments = cached["comments"]
        else:
            print(f"  Topic: [{tid}] {title} — fetch")
            fetched = get_all_comments(tid)
            comments = [
                {
                    "id": c["id"],
                    "text": c.get("text", ""),
                }
                for c in fetched
            ]

        result[str(tid)] = {
            "title": title,
            "comments": comments,
        }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {OUTPUT}")
    print(f"Topics: {len(result)}")
    print(f"Comments: {sum(len(v['comments']) for v in result.values())}")


if __name__ == "__main__":
    main()
