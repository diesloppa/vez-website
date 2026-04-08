"""
Builds playlist_meta.json from VK discussions plus playlist name heuristics.

Sources:
  vk_discussions.json
  vk_raw_data.enc.json / vk_raw_data.json
  playlist_meta.json (optional seed with manual fixes)

Output:
  playlist_meta.json
"""
import json
import os
import re
from crypto_utils import load_json

DISCUSSIONS = "vk_discussions.json"
RAW = "vk_raw_data.json"
RAW_ENCRYPTED = "vk_raw_data.enc.json"
META = "playlist_meta.json"

TOPIC_CATEGORY = {
    "СЕРИАЛЫ": "сериалы",
    "ИГРЫ": "игры",
    "ТОПЫ": "топы",
    "РЕАКЦИИ": "реакции",
    "РАСПРЕДЕЛИТЕЛЬ": "распределитель",
}

TOPIC_COLOR = {
    "ЗЕЛЁНЫЙ": "green",
    "ЖЁЛТЫЙ": "yellow",
    "ЖЕЛТЫЙ": "yellow",
    "СИНИЙ": "blue",
    "СЕРЫЙ": "grey",
    "КРАСНЫЙ": "red",
    "КОРИЧНЕВЫЙ": "brown",
}

PLAYLIST_LINK_RE = re.compile(
    r"(?:vk\.com/video/playlist|vkvideo\.ru/playlist)/-(?:\d+)_(-?\d+)",
    flags=re.IGNORECASE,
)


def topic_meta(title: str) -> dict | None:
    title_up = title.upper().strip()
    if title_up == "ТОПЫ":
        return {"category": "топы", "color": None, "topic": title}
    if title_up == "РАСПРЕДЕЛИТЕЛЬ":
        return {"category": "распределитель", "color": None, "topic": title}

    parts = title_up.split()
    if not parts:
        return None

    category = TOPIC_CATEGORY.get(parts[0])
    color = next((TOPIC_COLOR[p] for p in parts[1:] if p in TOPIC_COLOR), None)
    if category:
        return {"category": category, "color": color, "topic": title}
    return None


def detect_from_name(name: str) -> dict | None:
    upper = name.upper().strip()

    for label, color in TOPIC_COLOR.items():
        if upper == f"ФИЛЬМЫ {label}":
            return {"category": "фильмы", "color": color, "topic": "name_detected"}

    if upper == "РАСПРЕДЕЛИТЕЛЬ":
        return {"category": "распределитель", "color": None, "topic": "name_detected"}

    if upper.startswith("ТОП "):
        return {"category": "топы", "color": None, "topic": "name_detected"}

    return None


def ordered_dict_by_numeric_key(d: dict) -> dict:
    return {k: d[k] for k in sorted(d, key=lambda x: int(x))}


def main():
    with open(DISCUSSIONS, encoding="utf-8") as f:
        discussions = json.load(f)
    raw = load_json(RAW, RAW_ENCRYPTED)

    existing = {}
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            existing = json.load(f)

    # Keep previous curated values for existing raw playlists, but allow fresh
    # discussion-derived metadata to override them.
    result = {
        pid: meta
        for pid, meta in existing.items()
        if pid in raw["playlists"]
    }

    linked = 0
    for topic in discussions.values():
        meta = topic_meta(topic.get("title", ""))
        if not meta:
            continue
        for comment in topic.get("comments", []):
            text = comment.get("text", "")
            for match in PLAYLIST_LINK_RE.finditer(text):
                pid = match.group(1)
                result[pid] = meta
                linked += 1

    name_detected = 0
    for pid, pl in raw["playlists"].items():
        inferred = detect_from_name(pl["name"])
        if inferred:
            result[pid] = inferred
            name_detected += 1

    with open(META, "w", encoding="utf-8") as f:
        json.dump(ordered_dict_by_numeric_key(result), f, ensure_ascii=False, indent=2)

    print(f"Discussion links processed: {linked}")
    print(f"Name-detected playlists: {name_detected}")
    print(f"Final meta entries: {len(result)}")


if __name__ == "__main__":
    main()
