"""Shared loader for debate/blog_registry.yaml.

Supports two per-scientist shapes (see registry header):
  - list of blog URLs (legacy flat form)
  - mapping with optional ``blogs`` + ``youtube_hints``

Both shapes are normalized to a uniform dict so call sites in
``search_blogs.py`` and ``search_youtube.py`` don't need to branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from _common import REPO_ROOT


@dataclass
class YoutubeHints:
    name_variants: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    topic_aliases: list[str] = field(default_factory=list)


@dataclass
class ScientistEntry:
    name: str
    blogs: list[str] = field(default_factory=list)
    youtube_hints: YoutubeHints = field(default_factory=YoutubeHints)


def _normalize_entry(name: str, raw: object) -> ScientistEntry:
    if isinstance(raw, list):
        return ScientistEntry(name=name, blogs=list(raw))
    if isinstance(raw, dict):
        hints_raw = raw.get("youtube_hints") or {}
        hints = YoutubeHints(
            name_variants=list(hints_raw.get("name_variants", []) or []),
            affiliations=list(hints_raw.get("affiliations", []) or []),
            topic_aliases=list(hints_raw.get("topic_aliases", []) or []),
        )
        return ScientistEntry(name=name, blogs=list(raw.get("blogs", []) or []), youtube_hints=hints)
    return ScientistEntry(name=name)


def load_registry(path: str | Path = "debate/blog_registry.yaml") -> dict[str, ScientistEntry]:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {name: _normalize_entry(name, raw) for name, raw in data.items()}


def get_entry(name: str, path: str | Path = "debate/blog_registry.yaml") -> ScientistEntry:
    return load_registry(path).get(name, ScientistEntry(name=name))
