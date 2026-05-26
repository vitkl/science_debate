#!/usr/bin/env python3
"""Download full-text content for everything surfaced by the search scripts.

Dispatch table:
  - PMC OA articles  → JATS XML via Europe PMC (``_pmc_client.fetch_pmc_xml``)
  - bioRxiv preprints → PDF via constructed URL → text via ``pymupdf``
  - Generic web pages (blogs, lab sites) → ``trafilatura``
  - YouTube transcripts → ``youtube-transcript-api``
  - Custom sources (``inputs.custom_sources``) — file / directory / url / note

All writes go to ``papers_cache/{fulltext,web,transcripts,manual}/`` keyed by
stable IDs (DOI, URL hash, video ID, content hash). Already-cached items are
skipped silently.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fire
from _common import (
    PAPERS_CACHE,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    content_hash,
    ensure_dirs,
    http_get,
    load_json,
    url_hash,
)
from _pmc_client import fetch_pmc_xml, parse_pmc_xml, pmid_to_pmcid


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Best-effort PDF text extraction; returns empty string if pymupdf can't parse."""
    try:
        import pymupdf  # type: ignore

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:  # noqa: BLE001 — encrypted / corrupted PDFs raise many subtypes
        return ""


def _fetch_biorxiv(doi: str) -> dict[str, Any] | None:
    if not doi:
        return None
    out_dir = PAPERS_CACHE / "fulltext" / "biorxiv"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = doi.replace("/", "_")
    pdf_path = out_dir / f"{safe}.pdf"
    text_path = out_dir / f"{safe}.txt"
    if text_path.exists():
        return {"path": str(text_path), "doi": doi, "source": "biorxiv", "cached": True}
    url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
    try:
        response = http_get(url)
    except Exception:  # noqa: BLE001 — any HTTP failure means "bioRxiv PDF not available"
        return None
    body = response.content
    if not body or not body[:5].startswith(b"%PDF"):
        return None
    atomic_write_bytes(pdf_path, body)
    try:
        text = _extract_pdf_text(body)
    except Exception as exc:  # noqa: BLE001
        return {"path": str(pdf_path), "doi": doi, "source": "biorxiv", "warning": f"pdf extract failed: {exc}"}
    atomic_write_text(text_path, text)
    return {"path": str(text_path), "doi": doi, "source": "biorxiv", "cached": False}


def _fetch_pmc(record: dict[str, Any]) -> dict[str, Any] | None:
    pmcid = record.get("pmcid") or ""
    if not pmcid and record.get("pmid"):
        try:
            pmcid = pmid_to_pmcid(record["pmid"]) or ""
        except Exception:  # noqa: BLE001 — network blip shouldn't kill the whole fetch run
            return None
    if not pmcid:
        return None
    try:
        xml_path = fetch_pmc_xml(pmcid)
    except Exception:  # noqa: BLE001
        return None
    if xml_path is None:
        return None
    parsed = parse_pmc_xml(xml_path)
    text_path = xml_path.with_suffix(".txt")
    was_cached = text_path.exists()
    if not was_cached:
        atomic_write_text(text_path, parsed.get("body_text", "") or parsed.get("abstract", ""))
    return {"path": str(text_path), "pmcid": pmcid, "source": "pmc", "cached": was_cached}


def _fetch_web(url: str) -> dict[str, Any] | None:
    import trafilatura  # type: ignore

    out_dir = PAPERS_CACHE / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{url_hash(url)}.txt"
    if text_path.exists():
        return {"path": str(text_path), "url": url, "source": "web", "cached": True}
    try:
        html = trafilatura.fetch_url(url)
    except Exception as exc:  # noqa: BLE001 — bad URL / network shouldn't kill the fetch run
        return {"url": url, "source": "web", "warning": f"fetch_url failed: {exc}"}
    if not html:
        return None
    try:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "source": "web", "warning": f"extract failed: {exc}"}
    if not extracted:
        return None
    atomic_write_text(text_path, extracted)
    return {"path": str(text_path), "url": url, "source": "web", "cached": False}


OPEN_LIBRARY_BOOKS = "https://openlibrary.org/api/books"
INTERNET_ARCHIVE_TEXT = "https://archive.org/download"


def _open_library_lookup(isbn: str) -> dict[str, Any] | None:
    """Return Open Library bibkey payload for an ISBN, or None on miss."""
    if not isbn:
        return None
    try:
        response = http_get(
            OPEN_LIBRARY_BOOKS,
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
        )
        payload = response.json()
    except Exception:  # noqa: BLE001
        return None
    return payload.get(f"ISBN:{isbn}")


def _ia_djvu_text(ol_payload: dict[str, Any]) -> tuple[str, str] | None:
    """Try to extract Internet Archive ``_djvu.txt`` plaintext from an Open Library payload.

    Returns (text, ia_id) or None.
    """
    if not ol_payload:
        return None
    ebooks = ol_payload.get("ebooks") or []
    for entry in ebooks:
        # Prefer the structured 'formats.text' if present
        formats = entry.get("formats") or {}
        text_url = formats.get("text")
        if text_url:
            try:
                response = http_get(text_url)
                return response.text, entry.get("identifier") or ""
            except Exception:  # noqa: BLE001
                continue
        # Otherwise try to derive a _djvu.txt URL from the IA identifier
        ia_id = entry.get("identifier") or ""
        if ia_id:
            url = f"{INTERNET_ARCHIVE_TEXT}/{ia_id}/{ia_id}_djvu.txt"
            try:
                response = http_get(url)
                if response.text and "DOCTYPE html" not in response.text[:200]:
                    return response.text, ia_id
            except Exception:  # noqa: BLE001
                continue
    return None


def _fetch_book(book: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve full text for one book record. Priority chain:

    1. Open Library (by ISBN) → Internet Archive ``_djvu.txt`` (plaintext OCR).
    2. trafilatura on Google Books preview link (best-effort; may be empty for SPA pages).
    3. Description + snippet from Google Books metadata (final fallback).

    Always writes ``.meta.json`` alongside the text for the briefing renderer.
    """
    import trafilatura  # type: ignore

    book_id = (book.get("google_books_id") or book.get("openalex_id") or "").replace("/", "_")
    if not book_id:
        book_id = content_hash(book.get("title", "") + book.get("year", ""))
    out_dir = PAPERS_CACHE / "books_text"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{book_id}.txt"
    meta_path = out_dir / f"{book_id}.meta.json"

    if text_path.exists() and meta_path.exists():
        existing_meta = load_json(meta_path)
        return {
            "path": str(text_path),
            "book_id": book_id,
            "text_source": existing_meta.get("text_source"),
            "source": "book",
            "cached": True,
        }

    # 1) Open Library + IA
    isbn = book.get("isbn", "") or ""
    text = ""
    text_source = ""
    if isbn:
        ol_payload = _open_library_lookup(isbn)
        ia_result = _ia_djvu_text(ol_payload) if ol_payload else None
        if ia_result:
            text, ia_id = ia_result
            text_source = "internet_archive_djvu"

    # 2) trafilatura on Google Books preview
    preview = book.get("preview_link", "") or ""
    if not text and preview:
        try:
            html = trafilatura.fetch_url(preview)
            extracted = trafilatura.extract(html, include_comments=False, include_tables=False) if html else None
        except Exception:  # noqa: BLE001
            extracted = None
        if extracted and len(extracted.split()) >= 500:
            text = extracted
            text_source = "google_books_preview"

    # 3) Metadata fallback (description + snippet)
    if not text:
        text_parts = [s for s in (book.get("description", ""), book.get("snippet", "")) if s]
        text = "\n\n".join(text_parts)
        text_source = "google_books_metadata"

    if not text:
        meta = {
            "title": book.get("title", ""),
            "authors": book.get("authors", ""),
            "isbn": isbn,
            "preview_link": preview,
            "text_source": "missing",
            "word_count": 0,
        }
        atomic_write_json(meta_path, meta)
        return {"book_id": book_id, "warning": "no text source available", "source": "book"}

    atomic_write_text(text_path, text)
    meta = {
        "title": book.get("title", ""),
        "authors": book.get("authors", ""),
        "isbn": isbn,
        "preview_link": preview,
        "text_source": text_source,
        "word_count": len(text.split()),
    }
    atomic_write_json(meta_path, meta)
    return {
        "path": str(text_path),
        "book_id": book_id,
        "text_source": text_source,
        "source": "book",
        "cached": False,
    }


def _fetch_youtube_transcript(video_id: str) -> dict[str, Any] | None:
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    from youtube_transcript_api._errors import (  # type: ignore
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )

    out_dir = PAPERS_CACHE / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{video_id}.txt"
    if text_path.exists():
        return {"path": str(text_path), "video_id": video_id, "source": "youtube", "cached": True}
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as exc:
        return {"video_id": video_id, "source": "youtube", "warning": f"transcript unavailable: {exc}"}
    segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    text = " ".join(seg["text"] for seg in segments)
    atomic_write_text(text_path, text)
    return {"path": str(text_path), "video_id": video_id, "source": "youtube", "cached": False}


def _ingest_custom_file(item: dict[str, Any]) -> dict[str, Any] | None:
    src = Path(item["path"]).expanduser()
    if not src.exists():
        return {"warning": f"custom file missing: {src}", "source": "custom_file"}
    dest_dir = PAPERS_CACHE / "manual" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists():
        shutil.copy2(src, dest)
    out: dict[str, Any] = {
        "path": str(dest),
        "source": "custom_file",
        "tier": item.get("tier"),
        "label": item.get("label"),
    }
    if src.suffix.lower() == ".pdf":
        text_path = dest.with_suffix(".txt")
        if not text_path.exists():
            try:
                text = _extract_pdf_text(dest.read_bytes())
                atomic_write_text(text_path, text)
                out["text_path"] = str(text_path)
            except Exception as exc:  # noqa: BLE001
                out["warning"] = f"pdf extract failed: {exc}"
        else:
            out["text_path"] = str(text_path)
    elif src.suffix.lower() in {".txt", ".md", ".markdown"}:
        out["text_path"] = str(dest)
    else:
        out["warning"] = f"unhandled extension: {src.suffix}; copied verbatim"
    return out


def _ingest_custom_directory(item: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(item["path"]).expanduser()
    if not root.exists() or not root.is_dir():
        return [{"warning": f"custom directory missing: {root}", "source": "custom_directory"}]
    pattern = item.get("glob") or "*"
    out: list[dict[str, Any]] = []
    for child in sorted(root.rglob(pattern)):
        if child.is_file():
            out.append(
                _ingest_custom_file(
                    {"path": str(child), "tier": item.get("tier"), "label": item.get("label") or child.name}
                )
                or {}
            )
    return out


def _ingest_custom_note(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text", "") or ""
    out_dir = PAPERS_CACHE / "manual" / "notes"
    out_dir.mkdir(parents=True, exist_ok=True)
    note_path = out_dir / f"{content_hash(text)}.md"
    if not note_path.exists():
        atomic_write_text(note_path, text)
    return {"path": str(note_path), "source": "custom_note", "tier": item.get("tier"), "label": item.get("label")}


def _ingest_custom_url(item: dict[str, Any]) -> dict[str, Any] | None:
    url = item["url"]
    if "linkedin.com" in (urlparse(url).netloc or ""):
        return {
            "url": url,
            "source": "custom_url",
            "warning": "LinkedIn has no free public API; paste content as a 'note' custom source instead.",
        }
    return _fetch_web(url) or {"url": url, "source": "custom_url", "warning": "web fetch returned no content"}


def main(
    *,
    works: str | None = None,
    blogs: str | None = None,
    youtube: str | None = None,
    books: str | None = None,
    inputs: str | None = None,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Fetch all sources surfaced by upstream scripts. Returns a per-source summary."""
    ensure_dirs()
    summary: dict[str, list[dict[str, Any]]] = {
        "pmc": [],
        "biorxiv": [],
        "blogs": [],
        "youtube": [],
        "books": [],
        "custom": [],
    }

    if works:
        # Filter-then-fetch: only pull full text for tier-1 + tier-2a first/last-author records.
        # Tier-2b middle-author topic-match papers and tier-3 abstracts stay metadata-only;
        # fetching their full text wastes API quota and disk.
        all_records = load_json(Path(works))
        full_text_eligible = [r for r in all_records if r.get("tier") in (1, 2) and r.get("is_first_last")]
        for record in full_text_eligible:
            res = _fetch_pmc(record)
            if res:
                summary["pmc"].append(res)
                continue
            doi = (record.get("doi") or "").lower()
            if "biorxiv" in doi or "10.1101/" in doi:
                res = _fetch_biorxiv(doi)
                if res:
                    summary["biorxiv"].append(res)

    if blogs:
        blogs_payload = load_json(Path(blogs))
        # search_blogs.py now wraps posts in {scientist, url_source, index_urls, posts: [...]}
        post_list = blogs_payload.get("posts", []) if isinstance(blogs_payload, dict) else blogs_payload
        for post in post_list:
            url = post.get("url")
            if not url or post.get("_warning") or post.get("_error"):
                continue
            res = _fetch_web(url)
            if res:
                summary["blogs"].append({**res, "tier": post.get("tier", 2)})

    if youtube:
        payload = load_json(Path(youtube))
        for video in payload.get("results", []) if isinstance(payload, dict) else []:
            # Gate on user confirmation — Moderator marks user_confirmed=true after
            # presenting candidates via AskUserQuestion. Unconfirmed videos are kept
            # in the search results (so the briefing can link to them) but their
            # transcripts are NOT downloaded here.
            if not video.get("user_confirmed", False):
                summary["youtube"].append({"video_id": video.get("video_id"), "skipped_reason": "not_user_confirmed"})
                continue
            res = _fetch_youtube_transcript(video["video_id"])
            if res:
                summary["youtube"].append({**res, "tier": video.get("tier", 2)})

    if books:
        books_payload = load_json(Path(books))
        book_list = books_payload.get("books", []) if isinstance(books_payload, dict) else []
        for book in book_list:
            res = _fetch_book(book)
            if res:
                summary["books"].append({**res, "tier": book.get("tier", 2), "title": book.get("title")})

    if inputs:
        inputs_data = load_json(Path(inputs))
        custom_sources = inputs_data.get("ingestion", {}).get("custom_sources", {})
        for _scientist, items in custom_sources.items():
            for item in items:
                kind = item.get("type")
                if kind == "file":
                    res = _ingest_custom_file(item)
                    if res:
                        summary["custom"].append(res)
                elif kind == "directory":
                    summary["custom"].extend(_ingest_custom_directory(item))
                elif kind == "url":
                    res = _ingest_custom_url(item)
                    if res:
                        summary["custom"].append(res)
                elif kind == "note":
                    summary["custom"].append(_ingest_custom_note(item))

    if out_dir:
        atomic_write_json(Path(out_dir) / "fetch_summary.json", summary)
    print({k: len(v) for k, v in summary.items()})
    return summary


if __name__ == "__main__":
    fire.Fire(main)
