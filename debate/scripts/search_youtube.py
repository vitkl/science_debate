#!/usr/bin/env python3
"""Find YouTube videos *by or featuring as speaker* a named scientist.

Search strategy:
  - **Multi-query**: run several searches per scientist covering the typical
    appearance formats (lecture, talk, keynote, seminar, interview, podcast,
    conversation, plus one topic-boosted query). Dedupe by video_id.
  - **Speaker filter**: keep only videos where the scientist is plausibly
    speaking. Signals (any one suffices, see ``_is_speaker``):
      1. Channel is on the institutional allowlist (publisher/conference
         channel, OR per-scientist affiliation from blog_registry.yaml)
         AND the scientist's name appears in the title or description.
      2. Channel contains BOTH first AND last name (personal channel).
      3. Title speaker patterns (name + speaker verb, colon prefix, etc.).
      4. Description speaker attribution patterns
         ("interview with NAME", "speaker: NAME", …).
    Surname-only channel match is NOT a signal — it admits namesakes
    (musicians, realtors) without adding real institutional talks.
  - **Tier assignment**: tier 1 = speaker + topic match, tier 2 = speaker only.

Two backends:
  - **YouTube Data API v3** (preferred when ``YOUTUBE_API_KEY`` is set).
  - **yt-dlp** (zero-config fallback).

CLI extras:
  - ``--dump-rejected SLUG``: print the full rejected list from the cache
    JSON at ``papers_cache/youtube_search/<SLUG>.json`` and exit. Use for
    diagnosing recall problems.
  - ``--use-llm-filter``: route borderline candidates (multi-speaker or no
    topic-keyword in title) through a Haiku call asking "is this a
    scientific talk by X?". Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fire
import requests
from _common import PAPERS_CACHE, atomic_write_json, http_get, load_json, slug
from _registry import YoutubeHints, get_entry

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

# Always-on institutional / conference / publisher channels that frequently
# host scientific talks. Matched case-insensitively as substring of the
# channel name. Per-scientist affiliations (from blog_registry.yaml) are
# unioned with this set at filter time.
INSTITUTIONAL_CHANNELS = (
    "allen institute",
    "company of biologists",
    "embo",
    "ictp",
    "hhmi",
    "howard hughes",
    "mbl",
    "marine biological laboratory",
    "royal society",
    "ted",
    "tedx",
    "lex fridman",
    "mindscape",
    "sean carroll",
    "huberman lab",
    "santa fe institute",
    "perimeter institute",
    "kavli",
    "francis crick",
    "crick institute",
    "wellcome",
    "embl",
    "cshl",
    "cold spring harbor",
    "janelia",
    "mpg",
    "max planck",
    "caltech",
    "mit opencourseware",
    "mit ",
    "stanford",
    "berkeley",
    "cambridge university",
    "oxford",
    "princeton",
    "harvard",
    "ucl",
    "ucsf",
    "lex clips",
    "world science festival",
)

# Long-form interview / podcast channels that frequently host scientists.
# Per-channel queries surface episodes where the title is just "Episode #N: Name"
# (the host's channel) — channel handles are stable, human-readable, and resolve
# to channel IDs at runtime via the YouTube Data API channels.list endpoint.
PODCAST_CHANNELS = (
    ("Sam Harris", "Making Sense", "@samharrisorg"),
    ("Lex Fridman", "Lex Fridman Podcast", "@lexfridman"),
    ("Joe Rogan", "PowerfulJRE", "@joerogan"),
    ("Tyler Cowen", "Conversations with Tyler", "@conversationswithtyler"),
    ("Russ Roberts", "EconTalk", "@econtalk"),
    ("Sean Carroll", "Mindscape", "@seancarroll"),
    ("Andrew Huberman", "Huberman Lab", "@hubermanlab"),
)

MULTI_SPEAKER_TITLE_HINTS = (
    "interview",
    "podcast",
    "conversation with",
    "in conversation",
    "fireside",
    "q&a",
    "roundtable",
    "panel",
)

PER_QUERY_RESULTS = 10


def _channel_is_institutional(chan_l: str, hints: YoutubeHints) -> bool:
    """True if channel matches the global allowlist OR a per-scientist affiliation."""
    if not chan_l:
        return False
    for tag in INSTITUTIONAL_CHANNELS:
        if tag in chan_l:
            return True
    for aff in hints.affiliations:
        if aff and aff.lower() in chan_l:
            return True
    return False


def _personal_channel(chan_l: str, scientist: str) -> bool:
    """True only if BOTH first and last name appear in channel (e.g. 'Judea Pearl Channel').

    Surname-only is intentionally rejected — admits 'Eric Davidson Music' /
    'Davidson Realty' false positives.
    """
    if not chan_l or not scientist:
        return False
    parts = scientist.lower().split()
    if len(parts) < 2:
        return False
    first, last = parts[0], parts[-1]
    return first in chan_l and last in chan_l


def _name_in(text_l: str, scientist: str, hints: YoutubeHints) -> bool:
    """Scientist's full name (or any registry-provided variant) appears in text."""
    if not text_l:
        return False
    if scientist and scientist.lower() in text_l:
        return True
    for variant in hints.name_variants:
        if variant and variant.lower() in text_l:
            return True
    return False


def _is_speaker(
    scientist: str,
    title: str,
    channel: str,
    description: str,
    hints: YoutubeHints | None = None,
) -> bool:
    """Strict speaker filter: does the scientist actually speak in this video?

    Signals (any one suffices):
      1. Channel is institutional / known affiliation AND scientist's name appears
         in title or description.
      2. Channel is a personal channel (both first AND last name in channel).
      3. Title speaker patterns (name + speaker verb, colon prefix, etc.).
      4. Description speaker attribution patterns
         ("interview with NAME", "speaker: NAME", …).

    Surname-only channel match is intentionally NOT a signal.
    """
    if not scientist:
        return False
    hints = hints or YoutubeHints()
    surname = scientist.lower().split()[-1]
    full = scientist.lower()
    title_l = (title or "").lower()
    chan_l = (channel or "").lower()
    desc_l = (description or "").lower()

    # 1. Institutional channel + name appears anywhere.
    if _channel_is_institutional(chan_l, hints) and (
        _name_in(title_l, scientist, hints) or _name_in(desc_l, scientist, hints)
    ):
        return True

    # 2. Personal channel (first AND last name).
    if _personal_channel(chan_l, scientist):
        return True

    # 3. Title speaker patterns.
    if full in title_l or surname in title_l:
        for n in (full, surname):
            if title_l.startswith(n):
                return True
            if f": {n}" in title_l:
                return True
            for v in SPEAKER_VERBS:
                if f"{n} {v}" in title_l or f"{v} {n}" in title_l or f"{v} with {n}" in title_l:
                    return True
            if f"with {n}" in title_l or f"by {n}" in title_l:
                return True

    # 4. Description speaker attribution.
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
    if not primary_terms:
        return 2
    haystack = f"{title or ''} {description or ''}".lower()
    if any(term.lower() in haystack for term in primary_terms):
        return 1
    return 2


def _is_multi_speaker(channel: str, title: str, channel_ids: dict[str, str]) -> bool:
    chan_l = (channel or "").lower()
    if any(host.lower() in chan_l or name.lower() in chan_l for host, name, _ in PODCAST_CHANNELS):
        return True
    if channel_ids:
        for handle, cid in channel_ids.items():
            if cid and cid.lower() == chan_l:
                return True
            if handle.lstrip("@").lower() == chan_l:
                return True
    title_l = (title or "").lower()
    return any(hint in title_l for hint in MULTI_SPEAKER_TITLE_HINTS)


def _is_borderline(hit: dict, primary_terms: list[str], channel_ids: dict[str, str]) -> bool:
    """Borderline candidate: passes speaker filter but warrants extra scrutiny.

    Triggered when (a) the video is multi-speaker (host + scientist; risk of
    mis-attribution) or (b) the title doesn't contain any topic keyword
    (could be a tangentially-related appearance).
    """
    if _is_multi_speaker(hit.get("channel", ""), hit.get("title", ""), channel_ids):
        return True
    if not primary_terms:
        return False
    title_l = (hit.get("title", "") or "").lower()
    return not any(t.lower() in title_l for t in primary_terms)


def _llm_verdict(
    scientist: str,
    hit: dict,
    primary_terms: list[str],
    cache: dict[str, dict],
) -> tuple[bool, str]:
    """Ask Haiku-4.5 whether this is a real scientific talk by ``scientist``.

    Thin wrapper around the shared ``_llm_classify.classify_candidate``.
    """
    from _llm_classify import classify_candidate

    return classify_candidate(
        cache_key=hit.get("video_id", ""),
        scientist=scientist,
        primary_terms=primary_terms,
        kind="youtube_video",
        item_fields={
            "Title": hit.get("title", ""),
            "Channel": hit.get("channel", ""),
            "Description": (hit.get("description_full") or "")[:2000],
        },
        question_template=(
            "Is this a scientific talk, lecture, or interview in which "
            "{scientist} is the featured speaker, on a topic plausibly related to {topic}?"
        ),
        cache=cache,
    )


def _resolve_channel_handles(api_key: str, cache_path: Path) -> dict[str, str]:
    cache: dict[str, str] = {}
    if cache_path.exists():
        try:
            cache = load_json(cache_path) or {}
        except Exception:  # noqa: BLE001
            cache = {}
    if not api_key:
        return cache
    missing = [h for _, _, h in PODCAST_CHANNELS if h and h not in cache]
    for handle in missing:
        try:
            response = http_get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"key": api_key, "part": "id", "forHandle": handle.lstrip("@")},
            )
            items = response.json().get("items", [])
            if items:
                cache[handle] = items[0].get("id", "")
        except Exception:  # noqa: BLE001
            continue
    if missing:
        try:
            atomic_write_json(cache_path, cache)
        except Exception:  # noqa: BLE001
            pass
    return cache


def _channel_queries(scientist: str, channel_ids: dict[str, str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _host, _name, handle in PODCAST_CHANNELS:
        cid = channel_ids.get(handle, "")
        if cid:
            out.append((f'"{scientist}"', cid))
    return out


def _queries_for(scientist: str, hints: YoutubeHints | None = None) -> list[str]:
    hints = hints or YoutubeHints()
    queries = [tpl.format(scientist=scientist) for tpl in QUERY_TEMPLATES]
    # Add affiliation-anchored queries — surface institutional talks that
    # don't carry the scientist's name in channel title.
    for aff in hints.affiliations[:3]:
        queries.append(f'"{scientist}" "{aff}"')
    # Variant names (e.g. "Eric H. Davidson") as bare lecture queries.
    for variant in hints.name_variants[:2]:
        queries.append(f'"{variant}" lecture')
    return queries


def _topic_boost_query(scientist: str, keywords_data: dict) -> str | None:
    primary = keywords_data.get("primary_terms", [])
    if not primary:
        return None
    topic = " ".join(f'"{t}"' for t in primary[:2])
    return f'"{scientist}" {topic}'.strip()


def _search_via_api(
    scientist: str,
    query: str,
    api_key: str,
    max_results: int,
    *,
    channel_id: str | None = None,
) -> list[dict] | dict:
    params: dict[str, object] = {
        "key": api_key,
        "q": query,
        "type": "video",
        "part": "snippet",
        "maxResults": min(max(int(max_results), 1), 50),
        "relevanceLanguage": "en",
        "order": "relevance",
    }
    if channel_id:
        params["channelId"] = channel_id
    try:
        response = http_get(YOUTUBE_SEARCH, params=params)
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
    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": f"ytsearch{n}",
    }
    try:
        with YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as exc:  # noqa: BLE001 — yt-dlp raises many subtypes
        return {"failure_reason": f"yt-dlp search error: {exc}"}

    entries = (info or {}).get("entries", []) or []
    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    surname = scientist.lower().split()[-1] if scientist else ""
    results: list[dict] = []
    with YoutubeDL(full_opts) as ydl:
        for entry in entries:
            if not entry:
                continue
            video_id = entry.get("id", "")
            if not video_id:
                continue
            channel = entry.get("channel") or entry.get("uploader", "")
            title = entry.get("title", "")
            description = entry.get("description") or ""
            needs_full = (surname and surname in (title.lower() + " " + channel.lower())) or (
                not description and bool(surname)
            )
            if needs_full:
                try:
                    detail = ydl.extract_info(
                        entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                        download=False,
                    )
                except Exception:  # noqa: BLE001
                    detail = None
                if detail:
                    description = detail.get("description") or description
                    channel = detail.get("channel") or detail.get("uploader") or channel
                    title = detail.get("title") or title
            results.append(
                {
                    "video_id": video_id,
                    "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                    "title": title,
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
    channel_queries: list[tuple[str, str]],
    *,
    api_key: str | None,
    max_results: int,
) -> tuple[list[dict], list[dict]]:
    seen: dict[str, dict] = {}
    failures: list[dict] = []
    for q in queries:
        if api_key:
            outcome = _search_via_api(scientist, q, api_key, max_results)
        else:
            outcome = _search_via_ytdlp(scientist, q, max_results)
        if isinstance(outcome, dict):
            failures.append({"query": q, **outcome})
            continue
        for hit in outcome:
            vid = hit["video_id"]
            if vid not in seen:
                seen[vid] = hit
    if api_key:
        for q, cid in channel_queries:
            outcome = _search_via_api(scientist, q, api_key, min(int(max_results), 5), channel_id=cid)
            if isinstance(outcome, dict):
                failures.append({"query": q, "channel_id": cid, **outcome})
                continue
            for hit in outcome:
                vid = hit["video_id"]
                if vid not in seen:
                    seen[vid] = hit
    return list(seen.values()), failures


def _dump_rejected(scientist_slug: str) -> int:
    """Print the full rejected list for a slug from its cache JSON.

    Use to diagnose recall complaints ("why isn't talk X kept?").
    """
    path = PAPERS_CACHE / "youtube_search" / f"{scientist_slug}.json"
    if not path.exists():
        print(f"no cache at {path}", file=sys.stderr)
        return 1
    payload = load_json(path)
    rejected = payload.get("rejected", []) or payload.get("rejected_sample", [])
    print(f"# {scientist_slug} — {len(rejected)} rejected videos")
    for r in rejected:
        print(f"- [{r.get('reason', '?')}] {r.get('title', '')[:90]}")
        print(f"    channel: {r.get('channel', '')}")
        if r.get("description_excerpt"):
            print(f"    desc:    {r['description_excerpt'][:200].replace(chr(10), ' ')}")
        if r.get("url"):
            print(f"    url:     {r['url']}")
    return 0


def main(
    scientist: str = "",
    out: str = "",
    *,
    keywords: str = "",
    max_results: int = PER_QUERY_RESULTS,
    api_key_env: str = "YOUTUBE_API_KEY",
    use_llm_filter: bool = False,
    dump_rejected: str = "",
) -> Path | int:
    """Multi-query YouTube search filtered for scientist-as-speaker, tier-assigned."""
    if dump_rejected:
        return _dump_rejected(dump_rejected)
    if not scientist or not out or not keywords:
        raise ValueError("scientist, out, and keywords are required (unless --dump-rejected is set)")

    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))
    keywords_data = load_json(Path(keywords))

    hints = get_entry(scientist).youtube_hints

    queries = _queries_for(scientist, hints)
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

    channel_ids: dict[str, str] = {}
    if api_key:
        channel_ids = _resolve_channel_handles(
            api_key,
            Path(out_path).parent.parent / "youtube_handles.json"
            if "youtube_search" in str(out_path)
            else out_path.parent / "youtube_handles.json",
        )
    channel_queries = _channel_queries(scientist, channel_ids)

    candidates, failures = _run_searches(
        scientist,
        queries,
        channel_queries,
        api_key=(api_key or None),
        max_results=max_results,
    )
    primary_terms = list(keywords_data.get("primary_terms", []))

    from _llm_classify import load_cache, save_cache

    llm_cache_path = out_path.parent / "_llm_verdict_cache_youtube.json"
    llm_cache: dict[str, dict] = load_cache(llm_cache_path) if use_llm_filter else {}

    kept: list[dict] = []
    rejected: list[dict] = []
    for hit in candidates:
        title = hit.get("title", "")
        channel = hit.get("channel", "")
        desc_full = hit.get("description_full", "")
        if not _is_speaker(scientist, title, channel, desc_full, hints):
            rejected.append(
                {
                    "video_id": hit["video_id"],
                    "title": title,
                    "channel": channel,
                    "description_excerpt": hit.get("description_excerpt", ""),
                    "url": hit.get("url", ""),
                    "reason": "not_speaker",
                }
            )
            continue
        # Optional LLM "is-it-a-science-talk" gate for borderline candidates.
        if use_llm_filter and _is_borderline(hit, primary_terms, channel_ids):
            keep, reason = _llm_verdict(scientist, hit, primary_terms, llm_cache)
            if not keep:
                rejected.append(
                    {
                        "video_id": hit["video_id"],
                        "title": title,
                        "channel": channel,
                        "description_excerpt": hit.get("description_excerpt", ""),
                        "url": hit.get("url", ""),
                        "reason": f"llm_rejected: {reason}",
                    }
                )
                continue
        tier = _assign_yt_tier(title, desc_full, primary_terms)
        multi = _is_multi_speaker(channel, title, channel_ids)
        needs_review = _is_borderline(hit, primary_terms, channel_ids)
        kept.append(
            {
                "video_id": hit["video_id"],
                "url": hit["url"],
                "title": title,
                "channel": channel,
                "published_at": hit["published_at"],
                "description_excerpt": hit.get("description_excerpt", ""),
                "tier": tier,
                "channel_institutional": _channel_is_institutional(channel.lower(), hints),
                "multi_speaker": multi,
                # Moderator-review hint: passed cheap heuristics but is borderline
                # (multi-speaker, OR no topic keyword in title). Default review path
                # is the Moderator scanning these before B3a confirmation.
                "needs_review": needs_review,
                # Filled by the Moderator after AskUserQuestion confirmation. Until set
                # true, fetch_fulltext.py will skip transcript download for this video.
                "user_confirmed": False,
            }
        )

    if use_llm_filter:
        save_cache(llm_cache_path, llm_cache)

    payload = {
        "scientist": scientist,
        "queries": queries,
        "backend": backend,
        "results": kept,
        "rejected_count": len(rejected),
        "rejected_sample": rejected[:5],
        "rejected": rejected,
        "failures": failures,
    }
    atomic_write_json(out_path, payload)
    tier1 = sum(1 for r in kept if r["tier"] == 1)
    tier2 = sum(1 for r in kept if r["tier"] == 2)
    print(f"{out_path} ({len(kept)} kept [{tier1} tier1, {tier2} tier2], {len(rejected)} rejected, backend={backend})")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
