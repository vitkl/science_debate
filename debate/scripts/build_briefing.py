#!/usr/bin/env python3
"""Assemble per-scientist briefing markdown files + a manifest from caches.

Per-tier composition rules:
  - Tier 1 (topic-direct): full text where available, abstracts otherwise.
    **Never dropped, never summarised.**
  - Tier 2 (first-/last-author): all abstracts; full text up to
    ``n_full_papers_cap``; over-cap full texts are flagged for summarisation
    to ``~500 words`` each via an external Task subagent (the Moderator
    spawns one summary task per source listed in ``needs_summary.json``;
    re-run this script to merge the resulting ``<path>.summary.md`` files).
  - Tier 3 (other): all abstracts up to ``n_abstracts_cap``.
  - Custom sources: rendered in their own section.

Global cap (default 80 000 words / Opus-safe): drop oldest Tier-3 abstracts,
then drop oldest Tier-2 full text, then summarise Tier-2 full text, then
summarise Tier-3 abstracts in thematic batches, then surface the over-budget
**Tier-1** list to the user via ``needs_user_decision.json``.
"""

from __future__ import annotations

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
    return load_json(path) if path.exists() else []


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


def _build_for_scientist(
    name: str,
    custom_sources: list[dict[str, Any]],
    *,
    n_full_papers_cap: int,
    n_abstracts_cap: int,
) -> tuple[str, dict[str, Any], list[str]]:
    """Return ``(briefing_markdown, manifest_for_this_scientist, needs_summary_paths)``."""
    works = sorted(_works_for(name), key=lambda r: r.get("year", ""), reverse=True)
    tier1 = [w for w in works if w.get("tier") == 1]
    tier2 = [w for w in works if w.get("tier") == 2]
    tier3 = [w for w in works if w.get("tier") == 3]
    needs_summary: list[str] = []

    sections: list[str] = [f"# Briefing — {name}\n"]
    manifest: dict[str, Any] = {"name": name, "tier1": {}, "tier2": {}, "tier3": {}, "custom": {}}

    # Tier 1 — full text always
    sections.append("## Tier 1: topic-direct\n")
    tier1_full = 0
    for record in tier1:
        text, text_path = _resolve_works_text(record)
        include_full = bool(text)
        if include_full:
            tier1_full += 1
        sections.append(_format_work_entry(record, text, include_full=include_full))
    blogs = _blogs_for(name)
    transcripts = _transcripts_for(name)
    if blogs or transcripts:
        sections.append("\n### Blog posts and recorded talks\n")
        for blog in blogs:
            if blog.get("url"):
                sections.append(f"- {blog.get('title', '')} — {blog['url']}")
        for video in transcripts:
            sections.append(f"- {video.get('title', '')} — {video.get('url', '')}")
    manifest["tier1"] = {
        "papers_total": len(tier1),
        "papers_with_fulltext": tier1_full,
        "blogs": len(blogs),
        "transcripts": len(transcripts),
        "sample_titles": [w.get("title", "") for w in tier1[:5]],
    }

    # Tier 2 — abstracts always; full text up to cap; flag extras for summary
    sections.append("\n## Tier 2: first/last-author\n")
    tier2_full = 0
    for idx, record in enumerate(tier2):
        text, text_path = _resolve_works_text(record)
        include_full = bool(text) and idx < int(n_full_papers_cap)
        if include_full:
            tier2_full += 1
        elif text and text_path:
            needs_summary.append(text_path)
        sections.append(_format_work_entry(record, text if include_full else "", include_full=include_full))
    manifest["tier2"] = {
        "papers_total": len(tier2),
        "papers_with_fulltext_kept": tier2_full,
        "sources_flagged_for_summary": len(needs_summary),
        "sample_titles": [w.get("title", "") for w in tier2[:5]],
    }

    # Tier 3 — abstracts only, capped
    sections.append("\n## Tier 3: other\n")
    kept_tier3 = tier3[: int(n_abstracts_cap)]
    for record in kept_tier3:
        sections.append(_format_work_entry(record, text="", include_full=False))
    manifest["tier3"] = {
        "abstracts_total": len(tier3),
        "abstracts_kept": len(kept_tier3),
        "abstracts_dropped": max(0, len(tier3) - len(kept_tier3)),
        "sample_titles": [w.get("title", "") for w in tier3[:5]],
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
    n_full_papers_cap = ingestion.get("n_full_papers_cap", 25)
    n_abstracts_cap = ingestion.get("n_abstracts_cap", 500)
    global_cap = int(global_briefing_word_cap or ingestion.get("global_briefing_word_cap", 80_000))

    manifest_top: dict[str, Any] = {
        "event_slug": inputs_data.get("event_slug"),
        "topic": inputs_data.get("topic"),
        "applied_caps": {
            "n_full_papers_cap": n_full_papers_cap,
            "n_abstracts_cap": n_abstracts_cap,
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
            n_abstracts_cap=n_abstracts_cap,
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
