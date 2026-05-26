"""Tests for debate/scripts/search_blogs.py — registry load, keyword tiering, link extract, --urls flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import search_blogs as sb


def test_load_registry_parses_yaml(tmp_path: Path):
    path = tmp_path / "blog_registry.yaml"
    path.write_text(
        "Lior Pachter:\n  - https://liorpachter.wordpress.com/\nEwan Birney:\n  - https://ewanbirney.wordpress.com/\n",
        encoding="utf-8",
    )
    reg = sb._load_registry(path)
    assert reg["Lior Pachter"] == ["https://liorpachter.wordpress.com/"]
    assert reg["Ewan Birney"] == ["https://ewanbirney.wordpress.com/"]


def test_matches_keywords_true_when_primary_matches():
    assert sb._matches_keywords(
        "A post on Gene Regulatory Networks", {"primary_terms": ["gene regulatory networks"], "synonyms": []}
    )


def test_matches_keywords_true_when_synonym_matches():
    assert sb._matches_keywords("Cis-Regulatory architecture", {"primary_terms": [], "synonyms": ["cis-regulatory"]})


def test_matches_keywords_false_when_nothing_matches():
    assert not sb._matches_keywords("a totally unrelated post", {"primary_terms": ["foo"], "synonyms": ["bar"]})


def test_matches_keywords_false_when_no_keywords_given():
    # Behaviour change: returns False so the caller decides tier (tier 2, not auto-include).
    assert not sb._matches_keywords("any text", {"primary_terms": [], "synonyms": []})


def test_extract_links_returns_href_and_anchor_pairs():
    html = '<html><a href="/post/1">Post One</a><a href="/post/2">Post Two</a></html>'
    links = sb._extract_links(html, "https://blog.example.com/")
    urls = [u for u, _ in links]
    titles = [t for _, t in links]
    assert "https://blog.example.com/post/1" in urls
    assert "https://blog.example.com/post/2" in urls
    assert "Post One" in titles
    assert "Post Two" in titles


def test_crawl_blog_index_tiers_all_posts():
    """Behaviour change: keep ALL posts (registered blog = author-confirmed),
    tier 1 if keyword match, tier 2 otherwise. No filtering-out at this stage."""
    html = '<a href="/p1">GRN post</a><a href="/p2">Unrelated cat post</a>'
    response = MagicMock()
    response.text = html
    keywords = {"primary_terms": ["GRN"], "synonyms": []}
    with patch.object(sb, "http_get", return_value=response):
        posts = sb._crawl_blog_index("https://blog.example.com/", keywords)
    titles = [p["title"] for p in posts]
    assert "GRN post" in titles
    assert "Unrelated cat post" in titles  # NOT filtered out anymore
    tiers_by_title = {p["title"]: p["tier"] for p in posts}
    assert tiers_by_title["GRN post"] == 1
    assert tiers_by_title["Unrelated cat post"] == 2


def test_main_discovery_mode_writes_suggestion_only(tmp_path: Path):
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"primary_terms": ["GRN"]}), encoding="utf-8")
    registry_path = tmp_path / "reg.yaml"
    registry_path.write_text("dummy: []\n", encoding="utf-8")
    out = tmp_path / "out.json"
    sb.main(
        scientist="Unknown Person",
        out=str(out),
        keywords=str(keywords_path),
        registry=str(registry_path),
        discover=True,
    )
    payload = json.loads(out.read_text())
    assert payload["scientist"] == "Unknown Person"
    assert "suggested_web_search" in payload


def test_main_urls_flag_overrides_registry(tmp_path: Path):
    """When --urls is passed, it takes precedence over the registry lookup
    (this is the Moderator-confirmed-URLs path)."""
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"primary_terms": ["GRN"]}), encoding="utf-8")
    registry_path = tmp_path / "reg.yaml"
    registry_path.write_text("dummy: ['https://wrong-blog.example.com/']\n", encoding="utf-8")
    out = tmp_path / "out.json"
    response = MagicMock()
    response.text = '<a href="/p1">GRN post</a>'
    with patch.object(sb, "http_get", return_value=response):
        sb.main(
            scientist="Whoever",
            out=str(out),
            keywords=str(keywords_path),
            registry=str(registry_path),
            urls="https://right-blog.example.com/",
        )
    payload = json.loads(out.read_text())
    assert payload["url_source"] == "moderator-confirmed"
    assert payload["index_urls"] == ["https://right-blog.example.com/"]
    assert any(p["title"] == "GRN post" for p in payload["posts"])
