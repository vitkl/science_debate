"""Live smoke tests for every external API the data-collection scripts call.

Opt-in only::

    pytest -m network tests/test_api_health.py

Each test makes one tiny real request and asserts the response shape the
scripts depend on. Run before a long /run-debate invocation, or via cron,
to catch API breakage (endpoint moved, schema changed, auth required).

Skipped automatically when a required key / dependency is missing — these
tests should never produce false negatives in CI.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.network


# ---- OpenAlex (search_works.py) ----


def test_openalex_works_lookup_returns_authorships():
    from _common import http_get

    r = http_get("https://api.openalex.org/works/W2741809807")
    r.raise_for_status()
    payload = r.json()
    assert "id" in payload
    assert isinstance(payload.get("authorships"), list) and payload["authorships"]


# ---- bioRxiv (fetch_fulltext.py) ----


def test_biorxiv_pdf_endpoint_responds():
    """bioRxiv must return a PDF for a known preprint via the script's http_get.

    If this fails with 403, bioRxiv is blocking our User-Agent (DEFAULT_USER_AGENT
    in _common.py) and ``_fetch_biorxiv`` will silently return None for every
    preprint in /run-debate. Fix the UA before relying on bioRxiv ingestion.
    """
    import requests
    from _common import http_get

    try:
        r = http_get("https://www.biorxiv.org/content/10.1101/2020.04.10.036418v1.full.pdf")
    except requests.HTTPError as exc:
        pytest.fail(f"bioRxiv blocked the request: {exc} — update DEFAULT_USER_AGENT or use a browser-like UA")
    assert r.content[:5].startswith(b"%PDF"), "bioRxiv didn't return a PDF body"


# ---- Europe PMC / PMC OAI (fetch_fulltext.py via _pmc_client) ----


def test_pmc_efetch_returns_jats_xml():
    from _common import http_get

    r = http_get("https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3000000/fullTextXML")
    if r.status_code == 404:
        pytest.skip("PMC3000000 not in Europe PMC index; pick another known PMCID if this fails persistently")
    r.raise_for_status()
    head = r.content[:5000].lower()
    assert b"<article" in head or b"<!doctype" in head[:200]


# ---- YouTube Data API v3 (search_youtube.py) ----


def test_youtube_data_api_v3_search_returns_items():
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        pytest.skip("YOUTUBE_API_KEY not set")
    from _common import http_get

    r = http_get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"key": key, "q": "Judea Pearl lecture", "type": "video", "part": "snippet", "maxResults": 1},
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    assert items, "API returned 0 items"
    snippet = items[0]["snippet"]
    for field in ("title", "channelTitle", "description"):
        assert field in snippet


# ---- yt-dlp fallback (search_youtube.py) ----


def test_yt_dlp_search_returns_entries():
    """yt-dlp scraping can be flaky / rate-limited; we just confirm it doesn't error AND returns ≥1 entry on a popular query."""
    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except ImportError:
        pytest.skip("yt-dlp not installed")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": "ytsearch3",
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info("TED talk", download=False)
    entries = (info or {}).get("entries", []) or []
    if not entries:
        pytest.skip("yt-dlp returned 0 entries — likely transient YouTube rate-limit; retry later")
    assert entries[0].get("id")


# ---- youtube-transcript-api (fetch_fulltext.py) ----


def test_youtube_transcript_api_fetch_known_video():
    """Asserts the migrated `YouTubeTranscriptApi().fetch(...).to_raw_data()` path still works."""
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

    fetched = YouTubeTranscriptApi().fetch("dQw4w9WgXcQ")  # always-captioned
    segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    assert segments and "text" in segments[0]


# ---- Google Books (search_books.py) ----


def test_google_books_inauthor_query_returns_volume():
    import requests
    from _common import http_get

    try:
        r = http_get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": 'inauthor:"Judea Pearl"', "maxResults": 1},
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            pytest.skip("Google Books rate-limited (429) even after backoff; retry later")
        raise
    r.raise_for_status()
    items = r.json().get("items", [])
    assert items, "no items returned"
    info = items[0]["volumeInfo"]
    assert info.get("title") and info.get("authors")


# ---- Open Library (fetch_fulltext.py book path) ----


def test_open_library_isbn_lookup():
    import requests
    from _common import http_get

    isbn = "9780521895606"  # Pearl, Causality (2nd ed.)
    try:
        r = http_get(
            "https://openlibrary.org/api/books",
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 429):
            pytest.skip(f"Open Library returned {exc.response.status_code}; retry later")
        raise
    r.raise_for_status()
    payload = r.json()
    assert f"ISBN:{isbn}" in payload


# ---- Blog crawl (search_blogs.py) — uses a registry URL ----


def test_blog_registry_url_returns_extractable_links():
    """Pachter's blog from blog_registry.yaml — index page must yield ≥1 dated post URL."""
    import re

    from _common import http_get

    r = http_get("https://liorpachter.wordpress.com/")
    r.raise_for_status()
    assert re.search(r"/\d{4}/\d{2}/", r.text), "no dated post URLs found on index page"


# ---- Anthropic API (LLM classifier) ----


def test_anthropic_haiku_call_returns_content():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError:
        pytest.skip("anthropic SDK not installed")
    client = Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with exactly the word OK."}],
    )
    assert msg.content and msg.content[0].text.strip()
