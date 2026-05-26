#!/usr/bin/env python3
"""Find YouTube videos likely featuring a named scientist on a given topic.

Two backends with automatic fallback:
  - **YouTube Data API v3** (preferred when ``YOUTUBE_API_KEY`` is set): faster,
    more reliable, uses 100 quota units per search.
  - **yt-dlp** (zero-config fallback): scrapes YouTube search pages, no API key
    needed. Slightly slower (~1-2s per search) and occasionally fragile when
    YouTube changes their pages, but works out of the box.

Both backends emit the same JSON schema so downstream consumers don't care
which one ran. The script prints to stderr which backend was used so the
Moderator (and the user) see it in conversation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fire
import requests
from _common import atomic_write_json, http_get, load_json, slug

YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"


def _channel_matches_scientist(channel: str, scientist: str) -> bool:
    surname = scientist.lower().split()[-1]
    return surname in channel.lower() or all(part.lower() in channel.lower() for part in scientist.split())


def _query_for(scientist: str, keywords_data: dict) -> str:
    primary = " OR ".join(f'"{t}"' for t in keywords_data.get("primary_terms", [])) or keywords_data.get("topic", "")
    return f'"{scientist}" {primary}'.strip()


def _search_via_api(scientist: str, query: str, api_key: str, max_results: int) -> list[dict] | dict:
    """Return list of result dicts, or a dict ``{"failure_reason": ...}`` on error."""
    try:
        response = http_get(
            YOUTUBE_SEARCH,
            params={
                "key": api_key,
                "q": query,
                "type": "video",
                "part": "snippet",
                "maxResults": min(max(int(max_results), 1), 50),
                "relevanceLanguage": "en",
                "order": "relevance",
            },
        )
    except requests.HTTPError as exc:
        return {"failure_reason": f"YouTube API HTTPError: {exc}"}
    hits = response.json().get("items", [])
    results: list[dict] = []
    for item in hits:
        snippet = item.get("snippet", {})
        channel = snippet.get("channelTitle", "")
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue
        results.append(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": snippet.get("title", ""),
                "channel": channel,
                "published_at": snippet.get("publishedAt", ""),
                "description_excerpt": (snippet.get("description", "") or "")[:400],
                "scientist_channel_match": _channel_matches_scientist(channel, scientist),
            }
        )
    return results


def _search_via_ytdlp(scientist: str, query: str, max_results: int) -> list[dict] | dict:
    """No-API-key fallback via yt-dlp. Same return contract as ``_search_via_api``."""
    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except ImportError as exc:
        return {"failure_reason": f'yt-dlp not installed: {exc}. Run pip install -e ".[dev,test]" to install.'}

    n = min(max(int(max_results), 1), 50)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": f"ytsearch{n}",
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as exc:  # noqa: BLE001 — yt-dlp raises many subtypes
        return {"failure_reason": f"yt-dlp search error: {exc}"}

    entries = (info or {}).get("entries", []) or []
    results: list[dict] = []
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id", "")
        if not video_id:
            continue
        channel = entry.get("channel") or entry.get("uploader", "")
        results.append(
            {
                "video_id": video_id,
                "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                "title": entry.get("title", ""),
                "channel": channel,
                "published_at": entry.get("upload_date", "") or "",
                "description_excerpt": (entry.get("description") or "")[:400],
                "scientist_channel_match": _channel_matches_scientist(channel, scientist),
            }
        )
    return results


def main(
    scientist: str,
    out: str,
    *,
    keywords: str,
    max_results: int = 20,
    api_key_env: str = "YOUTUBE_API_KEY",
) -> Path:
    """Search YouTube for ``scientist`` + the debate's primary keywords.

    Picks backend automatically based on ``YOUTUBE_API_KEY``; prints which one
    is in use so the Moderator can surface it to the user.
    """
    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))
    keywords_data = load_json(Path(keywords))
    query = _query_for(scientist, keywords_data)

    api_key = os.environ.get(api_key_env, "").strip()
    if api_key:
        print(f"[search_youtube] using YouTube Data API v3 (key from ${api_key_env})", file=sys.stderr)
        outcome = _search_via_api(scientist, query, api_key, max_results)
        backend = "api"
    else:
        print(
            f"[search_youtube] no ${api_key_env} set — falling back to yt-dlp (slower, may be fragile). "
            f"For higher reliability, get a free key at https://console.cloud.google.com → enable "
            f"'YouTube Data API v3' → create credentials → API key, then set it in your "
            f"~/.claude/settings.json env block. The key is FREE up to 10 000 queries/day.",
            file=sys.stderr,
        )
        outcome = _search_via_ytdlp(scientist, query, max_results)
        backend = "ytdlp"

    if isinstance(outcome, dict):  # failure path
        atomic_write_json(
            out_path, {"scientist": scientist, "query": query, "backend": backend, "results": [], **outcome}
        )
        print(f"{out_path} (failure: {outcome.get('failure_reason')})")
        return out_path

    atomic_write_json(out_path, {"scientist": scientist, "query": query, "backend": backend, "results": outcome})
    print(f"{out_path} ({len(outcome)} videos via {backend})")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
