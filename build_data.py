"""
Converts scraped data → encrypted site payload for browser-side decryption.

Sources:
  vk_raw_data.enc.json / vk_raw_data.json — all playlists + videos (from scrape_vk_api.py)
  playlist_meta.json                    — category + color per playlist (from discussion board parsing)

Output payload contains:
  videos    — deduplicated video list, sorted newest-first
  playlists — playlist objects with date ranges
  colors    — color summary (ordered, non-zero counts only)
  color_hex / color_label — lookup dicts
"""
import json
import os
from datetime import datetime, timezone
from crypto_utils import dump_encrypted_json, get_password, load_json

RAW = "vk_raw_data.json"
RAW_ENCRYPTED = "vk_raw_data.enc.json"
META = "playlist_meta.json"
OUT_ENCRYPTED = "site/data.enc.json"
OUT_LOCAL_JS = "site-local/data.js"
OUT_LOCAL_JSON = "site-local/data/db.json"

# ── Color system ──────────────────────────────────────────────────────────────
# Colors come from VK discussion board topic names, e.g. "СЕРИАЛЫ ЗЕЛЁНЫЙ"
# Black = not yet rated

COLOR_HEX = {
    "green":  "#4caf50",
    "yellow": "#fdd835",
    "blue":   "#42a5f5",
    "grey":   "#9e9e9e",
    "red":    "#ef5350",
    "brown":  "#8d6e63",
    "black":  "#222222",
}

COLOR_LABEL = {
    "green":  "Зелёный",
    "yellow": "Жёлтый",
    "blue":   "Синий",
    "grey":   "Серый",
    "red":    "Красный",
    "brown":  "Коричневый",
    "black":  "Не оценено",
}

# Display order for the color filter (black always last)
COLOR_ORDER = ["green", "yellow", "blue", "grey", "red", "brown", "black"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_date(ts: int) -> str:
    """Format a Unix timestamp as DD.MM.YYYY (UTC). Returns '' for 0 / None."""
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")


def unique_in_order(items: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def unique_tag_pairs(items: list[dict]) -> list[dict]:
    seen = set()
    out: list[dict] = []
    for item in items:
        category = item.get("category")
        color = item.get("color")
        if not category or not color:
            continue
        key = (category, color)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "category": category,
            "color": color,
            "hex": COLOR_HEX[color],
        })
    return out


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    os.makedirs("site/data", exist_ok=True)
    os.makedirs("site-local/data", exist_ok=True)

    raw = load_json(RAW, RAW_ENCRYPTED)
    with open(META, encoding="utf-8") as f:
        pl_meta = json.load(f)  # playlist_id (str) → {category, color}

    # ── Build unique video index ──────────────────────────────────────────────
    # A video can appear in multiple playlists; keep one canonical entry.
    video_map:       dict[str, dict]  = {}   # video_id → video dict
    video_playlists: dict[str, list]  = {}   # video_id → [playlist_ids]

    for pid, pl in raw["playlists"].items():
        for v in pl["videos"]:
            vid = v["id"]
            if vid not in video_map:
                video_map[vid] = v
            video_playlists.setdefault(vid, [])
            if pid not in video_playlists[vid]:
                video_playlists[vid].append(pid)

    # ── Build playlist objects ────────────────────────────────────────────────
    playlists = {}
    for pid, pl in raw["playlists"].items():
        meta     = pl_meta.get(pid, {})
        category = meta.get("category") or None
        color    = meta.get("color") or "black"

        video_ids  = [v["id"] for v in pl["videos"]]
        dates      = [v.get("date", 0) for v in pl["videos"] if v.get("date", 0)]
        date_start = min(dates) if dates else 0
        date_end   = max(dates) if dates else 0

        playlists[pid] = {
            "id":         pid,
            "name":       pl["name"],
            "category":   category,
            "color":      color,
            "hex":        COLOR_HEX[color],
            "count":      len(video_ids),
            "video_ids":  video_ids,
            "date_start": date_start,
            "date_end":   date_end,
        }

    # ── Build video list ──────────────────────────────────────────────────────
    videos = []
    for vid, v in video_map.items():
        # Skip system/unnamed entries that VK creates automatically
        if not v.get("title") or v["title"] in ("Videos on the wall", "Добавленные"):
            continue

        pids = video_playlists.get(vid, [])

        eligible_playlists = []
        for pid in pids:
            pl = playlists.get(pid)
            if not pl:
                continue
            if str(pid).startswith("-"):
                continue
            if pl.get("category") == "распределитель":
                continue
            eligible_playlists.append(pl)

        color_ids = unique_in_order([pl.get("color", "black") for pl in eligible_playlists])
        category_ids = unique_in_order([pl.get("category") for pl in eligible_playlists if pl.get("category")])
        category_color_pairs = unique_tag_pairs(eligible_playlists)

        if not color_ids:
            color_ids = ["black"]

        primary_color = next((c for c in color_ids if c != "black"), color_ids[0])
        primary_category = category_ids[0] if category_ids else None

        videos.append({
            "id":           vid,
            "title":        v["title"],
            "url":          v["url"],
            "thumbnail":    v.get("thumbnail", ""),
            "duration":     v.get("duration", ""),
            "duration_sec": v.get("duration_sec", 0),
            "date":         fmt_date(v.get("date", 0)),
            "date_ts":      v.get("date", 0),
            "color":        primary_color,
            "hex":          COLOR_HEX[primary_color],
            "category":     primary_category,
            "color_ids":    color_ids,
            "color_hexes":  [COLOR_HEX[c] for c in color_ids],
            "category_ids": category_ids,
            "category_color_pairs": category_color_pairs,
            "playlists":    pids,
        })

    # Sort newest first (by upload date)
    videos.sort(key=lambda v: v["date_ts"], reverse=True)

    # ── Color stats ───────────────────────────────────────────────────────────
    color_counts: dict[str, int] = {}
    for v in videos:
        for c in v["color_ids"]:
            color_counts[c] = color_counts.get(c, 0) + 1

    colors = [
        {
            "id":    c,
            "label": COLOR_LABEL[c],
            "hex":   COLOR_HEX[c],
            "count": color_counts.get(c, 0),
        }
        for c in COLOR_ORDER
        if color_counts.get(c, 0) > 0
    ]

    # ── Category stats (for reporting) ───────────────────────────────────────
    cat_stats: dict[str, int] = {}
    for pl in playlists.values():
        cat = pl["category"] or "прочее"
        cat_stats[cat] = cat_stats.get(cat, 0) + 1

    # ── Assemble output ───────────────────────────────────────────────────────
    site_data = {
        "videos":      videos,
        "playlists":   playlists,
        "colors":      colors,
        "color_hex":   COLOR_HEX,
        "color_label": COLOR_LABEL,
    }

    password = get_password(required=True)
    dump_encrypted_json(site_data, OUT_ENCRYPTED, password, compact=True)

    with open(OUT_LOCAL_JS, "w", encoding="utf-8") as f:
        f.write("window.siteData = ")
        json.dump(site_data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")

    with open(OUT_LOCAL_JSON, "w", encoding="utf-8") as f:
        json.dump(site_data, f, ensure_ascii=False, indent=2)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"Уникальных видео : {len(videos)}")
    print(f"Плейлистов       : {len(playlists)}")
    print(f"\nЦвета:")
    for c in colors:
        print(f"  {c['label']:12s}  {c['count']:4d} видео  {c['hex']}")
    print(f"\nКатегории (плейлисты):")
    for cat, cnt in sorted(cat_stats.items(), key=lambda x: -x[1]):
        print(f"  {cat:16s}  {cnt:3d} плейлистов")
    print(f"\ndata.enc.json: {os.path.getsize(OUT_ENCRYPTED) // 1024} KB")
    print(f"local data.js: {os.path.getsize(OUT_LOCAL_JS) // 1024} KB")


if __name__ == "__main__":
    main()
