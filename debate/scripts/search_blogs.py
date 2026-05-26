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

try:
    import trafilatura
except ImportError:  # pragma: no cover - dep is declared but may not be installed yet
    trafilatura = None

from _common import REPO_ROOT, atomic_write_json, http_get, load_json, slug, url_hash
from _registry import load_registry


def _load_registry(registry_path: Path) -> dict[str, list[str]]:
    return {name: entry.blogs for name, entry in load_registry(registry_path).items()}


def _matches_keywords(text: str, keywords: dict[str, Any]) -> bool:
    """Return True if any primary term or synonym appears in text."""
    haystack = text.lower()
    primary = [t.lower() for t in keywords.get("primary_terms", [])]
    synonyms = [t.lower() for t in keywords.get("synonyms", [])]
    if not primary and not synonyms:
        return False  # cannot match without keywords; caller decides tier
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
    """Crawl the index page; keep ALL posts (registered blog = author-confirmed).

    Tier assignment: tier 1 if title hits a keyword, tier 2 otherwise. Built so
    that ``build_briefing.py`` can split blog content into topic-relevant vs.
    author-confirmed-only buckets matching the unified tier model.
    """
    try:
        response = http_get(index_url)
    except Exception as exc:  # noqa: BLE001
        return [{"_error": f"fetch failed: {exc}", "url": index_url}]
    html = response.text
    links = _extract_links(html, index_url)
    posts: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for href, anchor in links:
        if href in seen_urls:
            continue
        seen_urls.add(href)
        tier = 1 if _matches_keywords(anchor, keywords) else 2
        posts.append({"url": href, "title": anchor, "source": "blog", "tier": tier, "key": url_hash(href)})
        if len(posts) >= max_posts:
            break
    return posts


def main(
    scientist: str,
    out: str,
    *,
    keywords: str,
    registry: str = "debate/blog_registry.yaml",
    urls: str | None = None,
    discover: bool = False,
    use_llm_filter: bool = False,
) -> Path:
    """Crawl blog index pages for posts authored by ``scientist`` and tier-tag them.

    URL source resolution (highest precedence first):
      1. ``--urls "u1,u2,..."`` — Moderator-confirmed list (after asking the user).
         This is the recommended path: the Moderator does a WebSearch for blogs
         by the scientist, presents candidates via AskUserQuestion, then passes
         the user-confirmed subset here.
      2. ``--registry blog_registry.yaml`` lookup by scientist name — only used
         when ``--urls`` is absent.
      3. ``--discover`` — emit a web-search query suggestion (for manual flows).
    """
    keywords_data: dict[str, Any] = load_json(Path(keywords))
    registry_path = Path(registry)
    if not registry_path.is_absolute():
        registry_path = REPO_ROOT / registry_path

    if discover:
        query = f'"{scientist}" (blog OR substack OR wordpress)'
        suggestion = {
            "scientist": scientist,
            "suggested_web_search": query,
            "registry_path": str(registry_path),
            "note": "Run this WebSearch, present candidates to the user, then re-run with --urls 'u1,u2,...'.",
        }
        out_path = Path(out)
        atomic_write_json(out_path, suggestion)
        print(f"{out_path} (discovery suggestion)")
        return out_path

    if urls:
        index_urls = [u.strip() for u in urls.split(",") if u.strip()]
        url_source = "moderator-confirmed"
    else:
        registry_map = _load_registry(registry_path)
        index_urls = registry_map.get(scientist) or []
        url_source = "registry"

    posts: list[dict[str, Any]] = []
    if not index_urls:
        posts.append(
            {
                "_warning": (
                    f"No blog URLs for {scientist}. Use --discover for a search query, "
                    f"present candidates to the user, then re-run with --urls 'u1,u2,...'."
                ),
                "url": "",
                "title": "",
                "tier": 2,
            }
        )
    for index_url in index_urls:
        posts.extend(_crawl_blog_index(index_url, keywords_data))
    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))

    rejected: list[dict[str, Any]] = []
    if use_llm_filter and posts:
        from _llm_classify import classify_candidate, load_cache, save_cache

        primary_terms = list(keywords_data.get("primary_terms", []))
        llm_cache_path = out_path.parent / "_llm_verdict_cache_blogs.json"
        llm_cache = load_cache(llm_cache_path)
        kept: list[dict[str, Any]] = []
        for post in posts:
            # Only gate tier-2 posts (no keyword in title); tier-1 are already
            # topic-confirmed by the cheap matcher and don't need an LLM call.
            if post.get("tier") == 2 and post.get("url") and not post.get("_warning"):
                keep, reason = classify_candidate(
                    cache_key=post["url"],
                    scientist=scientist,
                    primary_terms=primary_terms,
                    kind="blog_post",
                    item_fields={"Title": post.get("title", ""), "URL": post.get("url", "")},
                    question_template=(
                        "Is this a blog post written by {scientist} "
                        "(or directly summarising their own work) on a topic plausibly "
                        "related to {topic}?"
                    ),
                    cache=llm_cache,
                )
                if not keep:
                    rejected.append({**post, "reason": f"llm_rejected: {reason}"})
                    continue
            kept.append(post)
        save_cache(llm_cache_path, llm_cache)
        posts = kept

    payload = {
        "scientist": scientist,
        "url_source": url_source,
        "index_urls": index_urls,
        "posts": posts,
        "rejected": rejected,
    }
    atomic_write_json(out_path, payload)
    print(f"{out_path} ({len(posts)} candidate posts from {len(index_urls)} index URLs; source={url_source})")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
