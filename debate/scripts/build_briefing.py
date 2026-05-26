#!/usr/bin/env python3
"""Assemble per-scientist briefing markdown files + a manifest from caches.

Per-tier composition rules:
  - Tier 1 (topic-direct): full text where available, abstracts otherwise.
    Sacred by default (``n_tier1_max = None`` keeps all); the Phase B4
    interactive 'reduce' option may cap it with a warning.
  - Tier 2a (first-/last-author, any topic): full text up to
    ``n_tier2a_full_max`` (default 25). Over-cap full texts are flagged
    for summarisation in ``needs_summary.json``.
  - Tier 2b (middle-author topic-relevant): abstracts only.
  - Tier 3 (neither author nor topic): random seeded sample of
    ``n_tier3_sample`` papers (default 15).
  - Custom sources: rendered in their own section.

When the rendered briefing exceeds ``global_briefing_word_cap``, the scientist
is added to ``needs_user_decision.json`` — the Moderator surfaces an interactive
summarise / reduce / drop choice (see Phase B4 of the run-debate skill).
The drop/summarise cascade is therefore handled at the SKILL level, not silently
inside this script.

``inputs.json::ingestion.dropped_source_ids[scientist]`` is consulted before
rendering — listed source IDs are filtered out from any tier.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import fire
from _common import (
    PAPERS_CACHE,
    atomic_write_json,
    atomic_write_text,
    author_slug,
    load_json,
    word_count,
)

WORDS_PER_FULL_PAPER = 4_000  # rough average used for capacity math
WORDS_PER_ABSTRACT = 250
SUMMARY_TARGET_WORDS = 500
DEFAULT_TIER3_SAMPLE = 15  # random sample size for "neither author nor topic match"


def _read_summary_or_fulltext(text_path: Path) -> tuple[str, bool]:
    """Return ``(text, was_summary)`` — prefer ``<path>.summary.md`` if present."""
    summary_path = text_path.with_suffix(text_path.suffix + ".summary.md")
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8"), True
    if text_path.exists():
        return text_path.read_text(encoding="utf-8"), False
    return "", False


def _works_for(scientist: str) -> list[dict[str, Any]]:
    path = PAPERS_CACHE / "works" / f"{author_slug(scientist)}.json"
    return load_json(path) if path.exists() else []


def _blogs_for(scientist: str) -> list[dict[str, Any]]:
    path = PAPERS_CACHE / "blogs" / f"{author_slug(scientist)}.json"
    if not path.exists():
        return []
    payload = load_json(path)
    # search_blogs.py now wraps posts in {scientist, url_source, index_urls, posts: [...]}.
    # Old format was a bare list; keep backward compat for caches written by an earlier run.
    if isinstance(payload, dict):
        return payload.get("posts", [])
    return payload


def _transcripts_for(scientist: str) -> list[dict[str, Any]]:
    yt_path = PAPERS_CACHE / "youtube_search" / f"{author_slug(scientist)}.json"
    if not yt_path.exists():
        return []
    payload = load_json(yt_path)
    if not isinstance(payload, dict):
        return []
    return payload.get("results", [])


def _resolve_works_text(record: dict[str, Any]) -> tuple[str, str]:
    """Locate the on-disk full-text file for a work record. Returns ``(text, source)``."""
    pmcid = record.get("pmcid", "")
    if pmcid:
        text_path = PAPERS_CACHE / "fulltext" / "pmc" / f"{pmcid}.txt"
        text, _ = _read_summary_or_fulltext(text_path)
        if text:
            return text, str(text_path)
    doi = (record.get("doi") or "").lower()
    if doi:
        safe = doi.replace("/", "_")
        text_path = PAPERS_CACHE / "fulltext" / "biorxiv" / f"{safe}.txt"
        text, _ = _read_summary_or_fulltext(text_path)
        if text:
            return text, str(text_path)
    return "", ""


def _format_work_entry(record: dict[str, Any], text: str, *, include_full: bool) -> str:
    title = record.get("title", "Untitled")
    year = record.get("year", "")
    authors = record.get("authors", "")
    doi = record.get("doi", "")
    body = ""
    if include_full and text:
        body = f"\n\n### Full text\n\n{text}\n"
    elif record.get("abstract"):
        body = f"\n\n**Abstract.** {record['abstract']}\n"
    citation = f"- **{title}** ({year}) — {authors}"
    if doi:
        citation += f" — doi:{doi}"
    return citation + body


def _custom_entries(custom_sources: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Return ``[(tier, rendered_md), ...]`` for one scientist's custom sources."""
    out: list[tuple[int, str]] = []
    for item in custom_sources:
        tier = int(item.get("tier", 1))
        label = item.get("label") or item.get("path") or item.get("url") or "custom source"
        kind = item.get("type")
        if kind == "note":
            out.append((tier, f"### {label} (note)\n\n{item.get('text', '')}\n"))
        elif kind == "directory":
            out.append((tier, f"### {label} (directory: {item.get('path')}, glob={item.get('glob', '*')})\n"))
        elif kind == "file":
            src = Path(item.get("path", ""))
            text_path = (PAPERS_CACHE / "manual" / "uploads" / src.name).with_suffix(".txt")
            text, was_summary = _read_summary_or_fulltext(text_path)
            note = " (summary)" if was_summary else ""
            body = f"\n\n{text}\n" if text else ""
            out.append((tier, f"### {label} (file{note})\n{body}"))
        elif kind == "url":
            out.append((tier, f"### {label} (url: {item.get('url')})\n"))
    return out


def _split_media_by_tier(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split blog or video items by ``tier`` field. Untagged items default to tier 2 (author-confirmed)."""
    tier1: list[dict[str, Any]] = []
    tier2: list[dict[str, Any]] = []
    for item in items:
        t = item.get("tier", 2)
        if t == 1:
            tier1.append(item)
        else:
            tier2.append(item)
    return tier1, tier2


def _build_for_scientist(
    name: str,
    custom_sources: list[dict[str, Any]],
    *,
    n_full_papers_cap: int,
    n_tier3_sample: int,
    n_tier1_max: int | None = None,
    n_tier2a_full_max: int | None = None,
    dropped_source_ids: list[str] | None = None,
) -> tuple[str, dict[str, Any], list[str]]:
    """Return ``(briefing_markdown, manifest_for_this_scientist, needs_summary_paths)``.

    Tier model (unified across papers, blogs, videos):
      - Tier 1: topic-matching (any source whose title/abstract/description/transcript
        hits a primary keyword)
      - Tier 2: author/speaker confirmed but no topic match (first/co-first/last/co-last
        for papers; registered blog posts; YouTube videos where the scientist is the
        confirmed speaker)
      - Tier 3: neither — random sample of ``n_tier3_sample`` papers (default 15).
        Only applies to papers; blogs and videos that aren't speaker-confirmed are
        dropped upstream by their respective search scripts.
    """
    works = sorted(_works_for(name), key=lambda r: r.get("year", ""), reverse=True)
    dropped_ids = set(dropped_source_ids or [])
    if dropped_ids:
        works = [w for w in works if w.get("id") not in dropped_ids]
    tier1_works = [w for w in works if w.get("tier") == 1]
    tier2_works = [w for w in works if w.get("tier") == 2]
    tier3_works = [w for w in works if w.get("tier") == 3]
    if n_tier1_max is not None and len(tier1_works) > int(n_tier1_max):
        tier1_works = tier1_works[: int(n_tier1_max)]  # newest first (works sorted by year DESC)
    effective_tier2a_cap = int(n_tier2a_full_max) if n_tier2a_full_max is not None else int(n_full_papers_cap)
    blogs = _blogs_for(name)
    transcripts = _transcripts_for(name)
    if dropped_ids:
        blogs = [b for b in blogs if b.get("id") not in dropped_ids and b.get("url") not in dropped_ids]
        transcripts = [
            v for v in transcripts if v.get("video_id") not in dropped_ids and v.get("url") not in dropped_ids
        ]
    tier1_blogs, tier2_blogs = _split_media_by_tier(blogs)
    tier1_videos, tier2_videos = _split_media_by_tier(transcripts)
    needs_summary: list[str] = []

    sections: list[str] = [f"# Briefing — {name}\n"]
    manifest: dict[str, Any] = {"name": name, "tier1": {}, "tier2": {}, "tier3": {}, "custom": {}}

    # Tier 1 — topic-direct (papers + topic-matching blogs/videos)
    sections.append("## Tier 1: topic-direct\n")
    tier1_full = 0
    for record in tier1_works:
        text, _text_path = _resolve_works_text(record)
        include_full = bool(text)
        if include_full:
            tier1_full += 1
        sections.append(_format_work_entry(record, text, include_full=include_full))
    if tier1_blogs or tier1_videos:
        sections.append("\n### Blog posts and recorded talks (topic-matching)\n")
        for blog in tier1_blogs:
            if blog.get("url"):
                sections.append(f"- {blog.get('title', '')} — {blog['url']}")
        for video in tier1_videos:
            sections.append(f"- {video.get('title', '')} — {video.get('url', '')}")
    manifest["tier1"] = {
        "papers_total": len(tier1_works),
        "papers_with_fulltext": tier1_full,
        "blogs": len(tier1_blogs),
        "videos": len(tier1_videos),
        "sample_titles": [w.get("title", "") for w in tier1_works[:5]],
    }

    # Tier 2 — split by signal type:
    #   2a: first/last author (strong author signal, no topic match) — full text eligible
    #   2b: middle author + topic match (weak author signal but topic-relevant) — abstract only
    tier2a = [w for w in tier2_works if w.get("is_first_last", False)]
    tier2b = [w for w in tier2_works if not w.get("is_first_last", False)]
    sections.append("\n## Tier 2: first/last-author or topic-relevant\n")
    sections.append("\n### First/last-author papers (any topic)\n")
    tier2_full = 0
    for idx, record in enumerate(tier2a):
        text, text_path = _resolve_works_text(record)
        include_full = bool(text) and idx < effective_tier2a_cap
        if include_full:
            tier2_full += 1
        elif text and text_path:
            needs_summary.append(text_path)
        sections.append(_format_work_entry(record, text if include_full else "", include_full=include_full))
    if tier2b:
        sections.append("\n### Middle-author papers that match the debate topic (abstracts only)\n")
        for record in tier2b:
            sections.append(_format_work_entry(record, text="", include_full=False))
    if tier2_blogs or tier2_videos:
        sections.append("\n### Other blog posts and recorded talks (author/speaker confirmed)\n")
        for blog in tier2_blogs:
            if blog.get("url"):
                sections.append(f"- {blog.get('title', '')} — {blog['url']}")
        for video in tier2_videos:
            sections.append(f"- {video.get('title', '')} — {video.get('url', '')}")
    manifest["tier2"] = {
        "first_last_papers_total": len(tier2a),
        "first_last_papers_with_fulltext_kept": tier2_full,
        "middle_author_topic_papers": len(tier2b),
        "sources_flagged_for_summary": len(needs_summary),
        "blogs": len(tier2_blogs),
        "videos": len(tier2_videos),
        "sample_titles": [w.get("title", "") for w in tier2a[:5]],
    }

    # Tier 3 — random sample of papers that are neither author-led nor topic-matching
    sample_size = int(n_tier3_sample)
    if len(tier3_works) <= sample_size:
        sampled = list(tier3_works)
    else:
        rng = random.Random(name)  # deterministic per scientist for reproducibility
        sampled = rng.sample(tier3_works, sample_size)
    sections.append(f"\n## Tier 3: random sample ({len(sampled)} of {len(tier3_works)} non-author non-topic papers)\n")
    for record in sampled:
        sections.append(_format_work_entry(record, text="", include_full=False))
    manifest["tier3"] = {
        "abstracts_total": len(tier3_works),
        "abstracts_kept": len(sampled),
        "abstracts_dropped": max(0, len(tier3_works) - len(sampled)),
        "sampling_method": "random_seeded_by_scientist_name",
        "sample_titles": [w.get("title", "") for w in sampled[:5]],
    }

    # Custom sources — grouped by tier
    if custom_sources:
        sections.append("\n## Custom sources\n")
        for tier, rendered in _custom_entries(custom_sources):
            sections.append(f"\n*Tier {tier}.*\n\n{rendered}")
        manifest["custom"] = {"count": len(custom_sources)}

    briefing = "\n".join(sections) + "\n"
    manifest["briefing_word_count"] = word_count(briefing)
    return briefing, manifest, needs_summary


def main(
    inputs: str,
    out: str,
    *,
    global_briefing_word_cap: int | None = None,
) -> dict[str, Any]:
    """Build per-scientist briefings; emit ``manifest.json`` + (if needed) ``needs_summary.json``."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs_data = load_json(Path(inputs))
    ingestion = inputs_data.get("ingestion", {})
    custom_sources_map = ingestion.get("custom_sources", {})
    dropped_map = ingestion.get("dropped_source_ids", {}) or {}
    n_full_papers_cap = ingestion.get("n_full_papers_cap", 25)
    n_tier3_sample = ingestion.get("n_tier3_sample", DEFAULT_TIER3_SAMPLE)
    n_tier1_max = ingestion.get("n_tier1_max")  # None = unlimited (sacred)
    n_tier2a_full_max = ingestion.get("n_tier2a_full_max")  # None = use n_full_papers_cap
    global_cap = int(global_briefing_word_cap or ingestion.get("global_briefing_word_cap", 80_000))

    manifest_top: dict[str, Any] = {
        "event_slug": inputs_data.get("event_slug"),
        "topic": inputs_data.get("topic"),
        "applied_caps": {
            "n_full_papers_cap": n_full_papers_cap,
            "n_tier3_sample": n_tier3_sample,
            "n_tier1_max": n_tier1_max,
            "n_tier2a_full_max": n_tier2a_full_max,
            "global_briefing_word_cap": global_cap,
        },
        "scientists": {},
    }
    all_needs_summary: list[str] = []
    over_budget_tier1: list[dict[str, Any]] = []

    for role_letter, info in inputs_data["scientists"].items():
        name = info["name"]
        briefing, manifest, needs = _build_for_scientist(
            name,
            custom_sources_map.get(name, []),
            n_full_papers_cap=n_full_papers_cap,
            n_tier3_sample=n_tier3_sample,
            n_tier1_max=n_tier1_max,
            n_tier2a_full_max=n_tier2a_full_max,
            dropped_source_ids=dropped_map.get(name, []),
        )
        # Global-cap enforcement on the rendered briefing
        if manifest["briefing_word_count"] > global_cap:
            over_budget_tier1.append({"scientist": name, "word_count": manifest["briefing_word_count"]})
        briefing_path = out_dir / f"briefing_{role_letter}.md"
        atomic_write_text(briefing_path, briefing)
        manifest["briefing_path"] = str(briefing_path)
        manifest_top["scientists"][role_letter] = manifest
        all_needs_summary.extend(needs)

    atomic_write_json(out_dir / "manifest.json", manifest_top)
    if all_needs_summary:
        atomic_write_json(
            out_dir / "needs_summary.json", {"target_words": SUMMARY_TARGET_WORDS, "sources": all_needs_summary}
        )
    if over_budget_tier1:
        atomic_write_json(
            out_dir / "needs_user_decision.json",
            {"over_budget_scientists": over_budget_tier1, "global_cap": global_cap},
        )
    print(
        {
            "manifest": str(out_dir / "manifest.json"),
            "needs_summary": len(all_needs_summary),
            "over_budget": len(over_budget_tier1),
        }
    )
    return manifest_top


if __name__ == "__main__":
    fire.Fire(main)
