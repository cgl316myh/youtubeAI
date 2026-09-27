#!/usr/bin/env python3
"""Fetch popular YouTube videos by category and write local HTML digests."""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
TEMPLATE_PATH = ROOT / "templates" / "base.html"
YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        print("缺少环境变量 YOUTUBE_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key


def published_after(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def search_ids(key: str, query: str, after: str, page_size: int = 25) -> list[str]:
    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "q": query,
        "maxResults": min(page_size, 50),
        "publishedAfter": after,
        "key": key,
    }
    r = requests.get(YOUTUBE_SEARCH, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def fetch_video_details(key: str, video_ids: list[str]) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    out: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "key": key,
        }
        r = requests.get(YOUTUBE_VIDEOS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        out.extend(data.get("items", []))
    return out


def parse_iso8601_duration(duration: str) -> str:
    """Convert PT#H#M#S to H:MM:SS or M:SS."""
    if not duration or not duration.startswith("PT"):
        return ""
    s = duration[2:]
    hours = minutes = seconds = 0
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            minutes = int(num or 0)
            num = ""
        elif ch == "S":
            seconds = int(num or 0)
            num = ""
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def normalize(item: dict[str, Any]) -> dict[str, Any]:
    sn = item.get("snippet", {})
    st = item.get("statistics", {})
    cd = item.get("contentDetails", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (
        thumbs.get("medium")
        or thumbs.get("high")
        or thumbs.get("default")
        or {}
    )
    views = int(st.get("viewCount") or 0)
    published = sn.get("publishedAt", "")
    return {
        "id": item["id"],
        "title": sn.get("title", ""),
        "channel": sn.get("channelTitle", ""),
        "published_at": published[:10],
        "views": views,
        "duration": parse_iso8601_duration(cd.get("duration", "")),
        "thumbnail": thumb.get("url", ""),
        "url": f"https://www.youtube.com/watch?v={item['id']}",
    }


def format_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def collect_category(
    key: str,
    category: dict[str, Any],
    after: str,
    limit: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for q in category.get("queries", []):
        try:
            ids = search_ids(key, q, after)
        except Exception as e:
            print(f"[warn] search failed for {q!r}: {e}", file=sys.stderr)
            continue
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                ordered_ids.append(vid)

    details = fetch_video_details(key, ordered_ids)
    videos = [normalize(x) for x in details]
    videos.sort(key=lambda v: v["views"], reverse=True)
    return videos[:limit]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_video_cards(videos: list[dict[str, Any]]) -> str:
    if not videos:
        return '<p class="empty">暂无结果</p>'
    parts: list[str] = []
    for i, v in enumerate(videos, 1):
        parts.append(
            f"""
      <article class="card">
        <a href="{esc(v['url'])}" target="_blank" rel="noopener">
          <img class="thumb" src="{esc(v['thumbnail'])}" alt="" loading="lazy" />
        </a>
        <div>
          <div>
            <span class="rank">{i}.</span>
            <a class="title" href="{esc(v['url'])}" target="_blank" rel="noopener">{esc(v['title'])}</a>
          </div>
          <div class="info">
            {esc(v['channel'])} · {esc(v['published_at'])} ·
            {esc(format_views(v['views']))} 次观看 · {esc(v['duration'])}
          </div>
        </div>
      </article>"""
        )
    return "\n".join(parts)


def render_page(page_title: str, page_meta: str, body: str) -> str:
    tpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        tpl.replace("{{ page_title }}", esc(page_title))
        .replace("{{ page_meta }}", esc(page_meta))
        .replace("{{ body }}", body)
    )


def write_daily_html(
    out_dir: Path,
    date_str: str,
    sections: list[tuple[str, str, list[dict[str, Any]]]],
    days: int,
) -> Path:
    body_parts: list[str] = []
    for cat_id, title, videos in sections:
        body_parts.append(
            f'<section class="{esc(cat_id)}">'
            f"<h2>{esc(title)} · Top {len(videos)}</h2>"
            f"{render_video_cards(videos)}</section>"
        )
    body = "\n".join(body_parts)
    meta = f"生成时间（UTC）{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} · 近 {days} 天 · 按播放量排序"
    html_doc = render_page(f"YouTube 日报 {date_str}", meta, body)

    out_dir.mkdir(parents=True, exist_ok=True)
    day_path = out_dir / f"{date_str}.html"
    day_path.write_text(html_doc, encoding="utf-8")

    latest = out_dir / "latest.html"
    latest.write_text(html_doc, encoding="utf-8")
    return day_path


def list_daily_files(out_dir: Path) -> list[str]:
    names = sorted(
        (p.stem for p in out_dir.glob("????-??-??.html")),
        reverse=True,
    )
    return names


def write_index(out_dir: Path, dates: list[str]) -> None:
    rows: list[str] = []
    if dates:
        rows.append(
            f'<p><a href="latest.html"><strong>打开最新一期 →</strong></a>'
            f"（{esc(dates[0])}）</p>"
        )
        rows.append("<section><h2>历史日报</h2>")
        for d in dates:
            rows.append(
                f'<p><a href="{esc(d)}.html">{esc(d)}</a></p>'
            )
        rows.append("</section>")
    else:
        rows.append('<p class="empty">尚无日报，等待首次抓取。</p>')

    html_doc = render_page(
        "YouTube 日报索引",
        "每日 AI / VPN / 云服务器 人气视频快链",
        "\n".join(rows),
    )
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")


def write_manifest(out_dir: Path, payload: dict[str, Any]) -> None:
    (out_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    cfg = load_config()
    key = api_key()

    days = int(cfg.get("published_within_days", 30))
    limit = int(cfg.get("max_results_per_category", 15))
    out_dir = ROOT / cfg.get("output_dir", "docs")
    after = published_after(days)

    sections: list[tuple[str, str, list[dict[str, Any]]]] = []
    manifest_cats: dict[str, Any] = {}

    for cat in cfg.get("categories", []):
        print(f"Fetching: {cat['title']} ...")
        videos = collect_category(key, cat, after, limit)
        print(f"  -> {len(videos)} videos")
        sections.append((cat["id"], cat["title"], videos))
        manifest_cats[cat["id"]] = {
            "title": cat["title"],
            "videos": videos,
        }

    # Use Asia/Shanghai calendar date for filenames
    shanghai = timezone(timedelta(hours=8))
    date_str = datetime.now(shanghai).strftime("%Y-%m-%d")

    day_path = write_daily_html(out_dir, date_str, sections, days)
    dates = list_daily_files(out_dir)
    write_index(out_dir, dates)
    write_manifest(
        out_dir,
        {
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "published_within_days": days,
            "categories": manifest_cats,
        },
    )
    print(f"Wrote {day_path}")
    print(f"Index: {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
