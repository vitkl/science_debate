"""Shared HTTP, caching, slug, and word-count utilities for debate/scripts/*.

Patterns: rate-limited HTTP with exponential backoff, atomic file writes
(temp-file + os.replace), URL-/string-derived slugs and stable cache keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPERS_CACHE = REPO_ROOT / "papers_cache"
DEBATE_EVENTS = REPO_ROOT / "debate_events"

DEFAULT_USER_AGENT = "science_debate/0.0.1 (https://github.com/vitkl/science_debate; mailto:vitkl@protonmail.com)"
DEFAULT_TIMEOUT = 30
DEFAULT_BACKOFF = (1.0, 2.0, 4.0)


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF,
) -> requests.Response:
    """GET with rate-limit-aware exponential backoff. Returns the final Response.

    Raises ``requests.HTTPError`` if all retries fail with a non-success status.
    Honours ``Retry-After`` headers when present on 429/503 responses.
    """
    hdrs = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0.0, *backoff], start=1):
        if delay > 0:
            time.sleep(delay)
        try:
            response = requests.get(url, headers=hdrs, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            continue
        if response.status_code < 400:
            return response
        if response.status_code in {429, 503}:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(int(retry_after))
            continue
        if response.status_code < 500 and attempt > 1:
            response.raise_for_status()
        last_exc = requests.HTTPError(f"{response.status_code} for {url}", response=response)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"http_get failed for {url} with no exception captured")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via temp-file + ``os.replace`` so partial writes are never visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(obj, indent=indent, ensure_ascii=False, default=str) + "\n")


def slug(value: str) -> str:
    """Filesystem-safe lower-kebab-case slug for names, titles, etc."""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", normalised).strip("-").lower()
    return cleaned or "unnamed"


def author_slug(name: str) -> str:
    """Slug suitable for `papers_cache/works/<slug>.json`."""
    return slug(name)


def scientist_in_authors(name: str, author_list_str: str) -> bool:
    """Token-boundary surname match in a free-text author list.

    Drops false positives where the surname appears only as a substring of a
    longer name (e.g., surname "Lee" inside "Banerjee"). Accepts standard
    punctuation boundaries ("Pearl, J.", "J. Pearl").
    """
    if not name or not author_list_str:
        return False
    parts = name.lower().split()
    if not parts:
        return False
    surname = parts[-1].strip()
    if not surname:
        return False
    pattern = r"\b" + re.escape(surname) + r"\b"
    return re.search(pattern, author_list_str.lower()) is not None


def url_hash(url: str) -> str:
    """Stable short hash for keying cached web fetches by URL."""
    return hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def content_hash(text: str) -> str:
    """Stable short hash for inline notes / arbitrary content."""
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def word_count(text: str) -> int:
    return len(text.split())


def ensure_dirs() -> None:
    PAPERS_CACHE.mkdir(parents=True, exist_ok=True)
    for sub in (
        "works",
        "blogs",
        "youtube_search",
        "fulltext",
        "web",
        "transcripts",
        "manual",
        "manual/uploads",
        "manual/notes",
    ):
        (PAPERS_CACHE / sub).mkdir(parents=True, exist_ok=True)
    DEBATE_EVENTS.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
