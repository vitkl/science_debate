#!/usr/bin/env python3
"""Find blog posts by a named scientist that match the debate's keyword set.

Two modes:
  - registry mode (default): look up the scientist in ``blog_registry.yaml``
    and crawl each listed URL for posts matching ``keywords.primary_terms``
    or ``synonyms``.
  - discovery mode (``--discover``): emit a single web-search query the user
    can run to surface candidate blogs to add to the registry (we don't crawl
    arbitrary search results — the registry is the safelist).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import fire
import yaml

try:
    import trafilatura
except ImportError:  # pragma: no cover - dep is declared but may not be installed yet
    trafilatura = None

from _common import REPO_ROOT, atomic_write_json, http_get, load_json, slug, url_hash


def _load_registry(registry_path: Path) -> dict[str, list[str]]:
    with registry_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {name: list(urls) for name, urls in data.items()}


def _matches_keywords(text: str, keywords: dict[str, Any]) -> bool:
    haystack = text.lower()
    primary = [t.lower() for t in keywords.get("primary_terms", [])]
    synonyms = [t.lower() for t in keywords.get("synonyms", [])]
    if not primary and not synonyms:
        return True  # no keywords given → keep everything
    return any(term in haystack for term in primary + synonyms)


def _extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return [(href, anchor_text), ...] for ``<a>`` tags. Lightweight parser."""
    import re

    out: list[tuple[str, str]] = []
    for match in re.finditer(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href = urljoin(base_url, match.group(1))
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if href.startswith("http") and text:
            out.append((href, text))
    return out


def _crawl_blog_index(index_url: str, keywords: dict[str, Any], max_posts: int = 40) -> list[dict[str, str]]:
    try:
        response = http_get(index_url)
    except Exception as exc:  # noqa: BLE001
        return [{"_error": f"fetch failed: {exc}", "url": index_url}]
    html = response.text
    links = _extract_links(html, index_url)
    posts: list[dict[str, str]] = []
    for href, anchor in links:
        if any(p["url"] == href for p in posts):
            continue
        if not _matches_keywords(anchor, keywords):
            continue
        posts.append({"url": href, "title": anchor, "source": "blog", "key": url_hash(href)})
        if len(posts) >= max_posts:
            break
    return posts


def main(
    scientist: str,
    out: str,
    *,
    keywords: str,
    registry: str = "debate/blog_registry.yaml",
    discover: bool = False,
) -> Path:
    """Find matching blog posts for ``scientist``; write the result to ``out``."""
    keywords_data: dict[str, Any] = load_json(Path(keywords))
    registry_path = Path(registry)
    if not registry_path.is_absolute():
        registry_path = REPO_ROOT / registry_path
    registry_map = _load_registry(registry_path)

    if discover:
        query = f'"{scientist}" (blog OR substack OR wordpress)'
        suggestion = {
            "scientist": scientist,
            "suggested_web_search": query,
            "registry_path": str(registry_path),
            "note": "Add the scientist + URL(s) to the registry, then re-run without --discover.",
        }
        out_path = Path(out)
        atomic_write_json(out_path, suggestion)
        print(f"{out_path} (discovery suggestion)")
        return out_path

    urls = registry_map.get(scientist) or []
    posts: list[dict[str, str]] = []
    if not urls:
        posts.append(
            {
                "_warning": f"{scientist} not in {registry_path.name}; run with --discover to get a search query.",
                "url": "",
                "title": "",
            }
        )
    for index_url in urls:
        posts.extend(_crawl_blog_index(index_url, keywords_data))
    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))
    atomic_write_json(out_path, posts)
    print(f"{out_path} ({len(posts)} candidate posts)")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
