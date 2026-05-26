#!/usr/bin/env python3
"""Find books by a scientist via OpenAlex + Google Books.

Discovery layers (free, no API key required):
  - OpenAlex book records (already pulled by ``search_works.py``; filtered here
    by ``is_book == True``). Source of structured per-author position info.
  - Google Books volumes (``inauthor:"<name>"`` query) for descriptions,
    snippets, ISBNs, and preview links.

Records are merged by ISBN (preferred) or normalized title+year; OpenAlex
structured fields are preserved on the kept record. ``fetch_fulltext.py``
later resolves full text via Open Library + Internet Archive ``_djvu.txt``,
falling back to trafilatura on Google Books preview, then to description +
snippet metadata only.

Tier model mirrors ``search_works.py::_assign_tier``:
  - tier 1: author AND (any primary keyword in title / description / snippet)
  - tier 2: author only (no topic match)
Books where the scientist's surname does not appear as a token in the
authors list are dropped before tier assignment.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import fire
from _common import atomic_write_json, http_get, load_json, scientist_in_authors, slug

GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"


def _strip(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _normalised_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _strip(title).lower()).strip()


def _isbn_from_volume(volume: dict[str, Any]) -> str:
    info = (volume.get("volumeInfo") or {}).get("industryIdentifiers", []) or []
    # Prefer ISBN_13, then ISBN_10, then anything else
    for kind in ("ISBN_13", "ISBN_10"):
        for entry in info:
            if entry.get("type") == kind and entry.get("identifier"):
                return str(entry["identifier"])
    for entry in info:
        if entry.get("identifier"):
            return str(entry["identifier"])
    return ""


def _has_topic(text: str, primary_terms: list[str]) -> bool:
    if not primary_terms or not text:
        return False
    haystack = text.lower()
    return any(term.lower() in haystack for term in primary_terms)


def _from_google_books(volume: dict[str, Any], scientist: str, primary_terms: list[str]) -> dict[str, Any] | None:
    info = volume.get("volumeInfo") or {}
    access = volume.get("accessInfo") or {}
    search = volume.get("searchInfo") or {}
    authors = ", ".join(info.get("authors") or [])
    if not scientist_in_authors(scientist, authors):
        return None  # surname not present — drop
    title = info.get("title", "") or ""
    description = info.get("description", "") or ""
    snippet = search.get("textSnippet", "") or ""
    haystack = " ".join([title, description, snippet])
    has_topic = _has_topic(haystack, primary_terms)
    record: dict[str, Any] = {
        "id": f"google_books:{volume.get('id', '')}",
        "google_books_id": volume.get("id", ""),
        "title": title,
        "subtitle": info.get("subtitle", "") or "",
        "authors": authors,
        "published_date": info.get("publishedDate", "") or "",
        "year": (info.get("publishedDate", "") or "")[:4],
        "description": description,
        "snippet": snippet,
        "preview_link": info.get("previewLink", "") or "",
        "info_link": info.get("infoLink", "") or "",
        "viewability": access.get("viewability", "") or "",
        "isbn": _isbn_from_volume(volume),
        "is_book": True,
        "source": "google_books",
        "topic_match": has_topic,
        "is_first_last": True,  # author search guarantees authorship
        "tier": 1 if has_topic else 2,
    }
    return record


def _from_openalex_book(record: dict[str, Any], primary_terms: list[str]) -> dict[str, Any]:
    title = record.get("title", "") or ""
    abstract = record.get("abstract", "") or ""
    haystack = " ".join([title, abstract])
    has_topic = _has_topic(haystack, primary_terms)
    is_first_last = bool(
        record.get("openalex_author_position") in ("first", "last")
        or record.get("epmc_author_position") in ("first", "last")
        or record.get("openalex_is_corresponding")
        or record.get("epmc_is_corresponding")
    )
    return {
        "id": record.get("id", ""),
        "openalex_id": record.get("id", "").replace("openalex:", "") if "openalex:" in record.get("id", "") else "",
        "title": title,
        "subtitle": "",
        "authors": record.get("authors", ""),
        "published_date": record.get("year", "") or "",
        "year": record.get("year", "") or "",
        "description": abstract,
        "snippet": "",
        "preview_link": record.get("url", "") or "",
        "info_link": record.get("url", "") or "",
        "viewability": "",
        "isbn": record.get("isbn", "") or "",
        "is_book": True,
        "source": "openalex",
        "topic_match": has_topic,
        "is_first_last": is_first_last,
        "tier": 1 if (is_first_last and has_topic) else 2 if (is_first_last or has_topic) else 2,
    }


def _merge_book_records(existing: dict[str, Any], incoming: dict[str, Any], primary_terms: list[str]) -> dict[str, Any]:
    """Merge incoming book record into existing and recompute tier.

    Prefers Google Books for descriptions and OpenAlex for structured author info.
    """
    out = {**existing}
    for k, v in incoming.items():
        if k in ("topic_match", "is_first_last", "tier"):
            continue
        if not out.get(k) and v:
            out[k] = v
    # Preserve OpenAlex structured author signals if either record has them
    out["is_first_last"] = bool(existing.get("is_first_last") or incoming.get("is_first_last"))
    haystack = " ".join([out.get("title", ""), out.get("description", ""), out.get("snippet", "")])
    out["topic_match"] = _has_topic(haystack, primary_terms)
    if out["is_first_last"] and out["topic_match"]:
        out["tier"] = 1
    elif out["is_first_last"] or out["topic_match"]:
        out["tier"] = 2
    else:
        out["tier"] = 2  # author-confirmed books stay at tier 2 even without topic
    return out


def _dedup_key(record: dict[str, Any]) -> str:
    isbn = (record.get("isbn") or "").strip()
    if isbn:
        return f"isbn:{isbn}"
    title = _normalised_title(record.get("title", ""))
    year = record.get("year", "") or ""
    return f"title:{title}|{year}"


def _dedupe_books(records: list[dict[str, Any]], primary_terms: list[str]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        key = _dedup_key(rec)
        if not key or key.startswith("title:|") or key == "title:":
            # Can't dedup without title or ISBN — keep separately
            seen[f"unmerged:{rec.get('id', id(rec))}"] = rec
            continue
        if key in seen:
            seen[key] = _merge_book_records(seen[key], rec, primary_terms)
        else:
            seen[key] = rec
    return list(seen.values())


def main(
    scientist: str,
    out: str,
    *,
    keywords: str | None = None,
    works: str | None = None,
    max_results: int = 40,
    use_llm_filter: bool = False,
) -> Path:
    """Discover books by ``scientist`` via OpenAlex (from --works) + Google Books."""
    primary_terms: list[str] = []
    if keywords:
        primary_terms = list(load_json(Path(keywords)).get("primary_terms", []))

    google_records: list[dict[str, Any]] = []
    # Google Books query: inauthor:"<name>"
    try:
        response = http_get(
            GOOGLE_BOOKS,
            params={
                "q": f'inauthor:"{scientist}"',
                "maxResults": min(40, int(max_results)),
                "printType": "books",
            },
        )
        for vol in response.json().get("items", []) or []:
            rec = _from_google_books(vol, scientist, primary_terms)
            if rec:
                google_records.append(rec)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: Google Books fetch failed for {scientist}: {exc}")

    openalex_books: list[dict[str, Any]] = []
    if works:
        works_path = Path(str(works).format(author=slug(scientist)))
        if works_path.exists():
            for record in load_json(works_path):
                if record.get("is_book"):
                    openalex_books.append(_from_openalex_book(record, primary_terms))

    merged = _dedupe_books(google_records + openalex_books, primary_terms)
    merged.sort(
        key=lambda r: (r.get("tier", 3), -int(r.get("year", "0") or 0) if (r.get("year") or "").isdigit() else 0)
    )

    rejected: list[dict[str, Any]] = []
    if use_llm_filter and merged:
        from _llm_classify import classify_candidate, load_cache, save_cache

        out_path_tmp = Path(out)
        if "{scientist}" in str(out_path_tmp):
            out_path_tmp = Path(str(out_path_tmp).format(scientist=slug(scientist)))
        llm_cache_path = out_path_tmp.parent / "_llm_verdict_cache_books.json"
        llm_cache = load_cache(llm_cache_path)
        kept: list[dict[str, Any]] = []
        for book in merged:
            # Author-match alone admits namesakes ("Religion Is Raced" for Eric
            # Davidson). LLM checks whether title+description+authors are a
            # plausible match for the named scientist.
            keep, reason = classify_candidate(
                cache_key=book.get("isbn") or book.get("id", ""),
                scientist=scientist,
                primary_terms=primary_terms,
                kind="book",
                item_fields={
                    "Title": book.get("title", ""),
                    "Subtitle": book.get("subtitle", ""),
                    "Authors": book.get("authors", ""),
                    "Year": book.get("year", ""),
                    "Description": (book.get("description", "") or "")[:1500],
                },
                question_template=(
                    "Is this book authored by {scientist} (the scientist), "
                    "and plausibly relevant to {topic} or to the scientist's research more broadly? "
                    "Reject namesakes (different person with the same name)."
                ),
                cache=llm_cache,
            )
            if not keep:
                rejected.append({**book, "reason": f"llm_rejected: {reason}"})
                continue
            kept.append(book)
        save_cache(llm_cache_path, llm_cache)
        merged = kept

    payload = {
        "scientist": scientist,
        "query": f'inauthor:"{scientist}"',
        "n_google": len(google_records),
        "n_openalex": len(openalex_books),
        "n_merged": len(merged),
        "books": merged,
        "rejected": rejected,
    }
    out_path = Path(out)
    if "{scientist}" in str(out_path):
        out_path = Path(str(out_path).format(scientist=slug(scientist)))
    atomic_write_json(out_path, payload)
    print(f"{out_path} ({len(merged)} books from {len(google_records)} Google Books + {len(openalex_books)} OpenAlex)")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
