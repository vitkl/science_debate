#!/usr/bin/env python3
"""Find YouTube videos *by or featuring as speaker* a named scientist.

Search strategy:
  - **Multi-query**: run several searches per scientist covering the typical
    appearance formats (lecture, talk, keynote, seminar, interview, podcast,
    conversation, plus one topic-boosted query). Dedupe by video_id.
  - **Speaker filter**: keep only videos where the scientist is plausibly
    speaking. Heuristic: (a) channel name contains scientist surname or full
    name (own channel / lab channel), OR (b) title OR description contains
    scientist's name AND title OR description contains a speaking-context word.
    Drops third-party talks ABOUT the scientist that don't feature them.
  - **Tier assignment** (mirrors the abstract-search tier model):
    - Tier 1: speaker-confirmed AND topic-matching (title or description hits
      a primary keyword)
    - Tier 2: speaker-confirmed but no topic match

Two backends:
  - **YouTube Data API v3** (preferred when ``YOUTUBE_API_KEY`` is set):
    faster, more reliable, 100 quota units per search → ~700 units per
    scientist for the 7 multi-queries.
  - **yt-dlp** (zero-config fallback): scrapes YouTube. ~10-15 s per scientist
    for the 7 queries. yt-dlp's extract_flat returns shorter descriptions, so
    description-based filtering on the yt-dlp path will miss content the API
    path would catch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fire
import requests
from _common import atomic_write_json, http_get, load_json, slug

YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"

SPEAKER_VERBS = (
    "talks",
    "talk",
    "lecture",
    "lectures",
    "interview",
    "interviews",
    "interviewed",
    "speaks",
    "presents",
    "presented",
    "keynote",
    "seminar",
)

QUERY_TEMPLATES = (
    '"{scientist}" lecture',
    '"{scientist}" talk',
    '"{scientist}" keynote',
    '"{scientist}" seminar',
    '"{scientist}" interview',
    '"{scientist}" podcast',
    '"{scientist}" conversation',
)

PER_QUERY_RESULTS = 10  # 7 queries × 10 = up to 70 candidates pre-dedupe


def _is_speaker(scientist: str, title: str, channel: str, description: str) -> bool:
    """Strict speaker filter: does the scientist actually speak in this video?

    Three signals (any one suffices):
      1. **Channel match** — scientist's own channel or lab channel (surname or full
         name appears in channel title).
      2. **Title speaker patterns** — name appears in the title in a pattern that
         CLAIMS the scientist as the subject/speaker:
            - Title starts with the name ("Judea Pearl on causality")
            - Colon-prefix to name (": Judea Pearl") — common for interview series
              like "Lex Fridman #56: Judea Pearl"
            - Name adjacent to a speaker verb ("Pearl talks", "interview with Pearl")
            - Preposition + name ("with Pearl", "by Pearl")
      3. **Description speaker attribution** — explicit "interview with NAME",
         "by NAME", "featuring NAME", "guest: NAME", "speaker: NAME", etc.

    Drops false positives like third-party talks that *mention* the scientist
    in passing (e.g. "Sara Mostafavi on graphs (Pearl framework reference)").
    """
    if not scientist:
        return False
    surname = scientist.lower().split()[-1]
    full = scientist.lower()
    title_l = (title or "").lower()
    chan_l = (channel or "").lower()
    desc_l = (description or "").lower()

    # 1. Channel match
    if surname in chan_l or full in chan_l:
        return True

    # 2. Title speaker patterns
    if full in title_l or surname in title_l:
        for n in (full, surname):
            # Name at the very start of the title
            if title_l.startswith(n):
                return True
            # Colon-prefix to name (e.g., "Lex Fridman #56: Judea Pearl")
            if f": {n}" in title_l:
                return True
            # Name adjacent to speaker verb (both orders)
            for v in SPEAKER_VERBS:
                if f"{n} {v}" in title_l or f"{v} {n}" in title_l or f"{v} with {n}" in title_l:
                    return True
            # Preposition + name
            if f"with {n}" in title_l or f"by {n}" in title_l:
                return True

    # 3. Description speaker attribution
    if full in desc_l or surname in desc_l:
        for n in (full, surname):
            for pat in (
                f"interview with {n}",
                f"podcast with {n}",
                f"conversation with {n}",
                f"in conversation with {n}",
                f"with {n},",
                f"with {n}.",
                f"by {n}",
                f"featuring {n}",
                f"guest: {n}",
                f"speaker: {n}",
                f"speakers: {n}",
                f"presenter: {n}",
            ):
                if pat in desc_l:
                    return True

    return False


def _assign_yt_tier(title: str, description: str, primary_terms: list[str]) -> int:
    """Tier 1 if topic-matching, tier 2 if speaker-only (caller already confirmed speaker)."""
    if not primary_terms:
        return 2
    haystack = f"{title or ''} {description or ''}".lower()
    if any(term.lower() in haystack for term in primary_terms):
        return 1
    return 2


def _queries_for(scientist: str) -> list[str]:
    return [tpl.format(scientist=scientist) for tpl in QUERY_TEMPLATES]


def _topic_boost_query(scientist: str, keywords_data: dict) -> str | None:
    primary = keywords_data.get("primary_terms", [])
    if not primary:
        return None
    topic = " ".join(f'"{t}"' for t in primary[:2])
    return f'"{scientist}" {topic}'.strip()


def _search_via_api(scientist: str, query: str, api_key: str, max_results: int) -> list[dict] | dict:
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
        description = snippet.get("description", "") or ""
        results.append(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": snippet.get("title", ""),
                "channel": channel,
                "published_at": snippet.get("publishedAt", ""),
                "description_excerpt": description[:1500],
                "description_full": description,
            }
        )
    return results


def _search_via_ytdlp(scientist: str, query: str, max_results: int) -> list[dict] | dict:
    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except ImportError as exc:
        return {"failure_reason": f"yt-dlp not installed: {exc}. Run pip install -e . to install."}

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
        description = entry.get("description") or ""
        results.append(
            {
                "video_id": video_id,
                "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                "title": entry.get("title", ""),
                "channel": channel,
                "published_at": entry.get("upload_date", "") or "",
                "description_excerpt": description[:1500],
                "description_full": description,
            }
        )
    return results


def _run_searches(
    scientist: str,
    queries: list[str],
    *,
    api_key: str | None,
    max_results: int,
) -> tuple[list[dict], list[dict]]:
    """Run all queries, dedupe by video_id, return (results, failures_log)."""
    seen: dict[str, dict] = {}
    failures: list[dict] = []
    for q in queries:
        if api_key:
            outcome = _search_via_api(scientist, q, api_key, max_results)
        else:
            outcome = _search_via_ytdlp(scientist, q, max_results)
        if isinstance(outcome, dict):  # failure dict
            failures.append({"query": q, **outcome})
            continue
        for hit in outcome:
            vid = hit["video_id"]
            if vid not in seen:
                seen[vid] = hit
    return list(seen.values()), failures


def main(
    scientist: str,
    out: str,
    *,
    keywords: str,
    max_results: int = PER_QUERY_RESULTS,
    api_key_env: str = "YOUTUBE_API_KEY",
) -> Path:
    """Multi-query YouTube search filtered for scientist-as-speaker, tier-assigned."""
    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))
    keywords_data = load_json(Path(keywords))

    queries = _queries_for(scientist)
    topic_q = _topic_boost_query(scientist, keywords_data)
    if topic_q:
        queries.append(topic_q)

    api_key = os.environ.get(api_key_env, "").strip()
    if api_key:
        backend = "api"
        print(
            f"[search_youtube] {scientist}: using YouTube Data API v3 (key from ${api_key_env}); {len(queries)} queries",
            file=sys.stderr,
        )
    else:
        backend = "ytdlp"
        print(
            f"[search_youtube] {scientist}: no ${api_key_env} set — falling back to yt-dlp; {len(queries)} queries. "
            f"For higher reliability and richer descriptions, add a free API key to ~/.claude/settings.json env block.",
            file=sys.stderr,
        )

    candidates, failures = _run_searches(scientist, queries, api_key=(api_key or None), max_results=max_results)
    primary_terms = list(keywords_data.get("primary_terms", []))

    kept: list[dict] = []
    rejected: list[dict] = []
    for hit in candidates:
        if not _is_speaker(scientist, hit.get("title", ""), hit.get("channel", ""), hit.get("description_full", "")):
            rejected.append(
                {
                    "video_id": hit["video_id"],
                    "title": hit.get("title", ""),
                    "channel": hit.get("channel", ""),
                    "reason": "not_speaker",
                }
            )
            continue
        tier = _assign_yt_tier(hit.get("title", ""), hit.get("description_full", ""), primary_terms)
        kept.append(
            {
                "video_id": hit["video_id"],
                "url": hit["url"],
                "title": hit["title"],
                "channel": hit["channel"],
                "published_at": hit["published_at"],
                "description_excerpt": hit.get("description_excerpt", ""),
                "tier": tier,
                "scientist_channel_match": (slug(scientist).split("-")[-1] in (hit.get("channel", "").lower()))
                or (scientist.lower() in (hit.get("channel", "").lower())),
                # Filled by the Moderator after AskUserQuestion confirmation. Until set
                # true, fetch_fulltext.py will skip transcript download for this video.
                "user_confirmed": False,
            }
        )

    payload = {
        "scientist": scientist,
        "queries": queries,
        "backend": backend,
        "results": kept,
        "rejected_count": len(rejected),
        "rejected_sample": rejected[:5],
        "failures": failures,
    }
    atomic_write_json(out_path, payload)
    tier1 = sum(1 for r in kept if r["tier"] == 1)
    tier2 = sum(1 for r in kept if r["tier"] == 2)
    print(f"{out_path} ({len(kept)} kept [{tier1} tier1, {tier2} tier2], {len(rejected)} rejected, backend={backend})")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
