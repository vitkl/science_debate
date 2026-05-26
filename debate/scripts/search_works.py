#!/usr/bin/env python3
"""Search Europe PMC (primary) and OpenAlex (fallback) for a scientist's works.

Tiers — assigned per record:
  - tier 1: title or abstract overlaps with ``keywords.primary_terms``
  - tier 2: scientist is first or last author
  - tier 3: everything else returned for that scientist

The opinion-piece publication-type filter (``editorial``, ``letter``,
``commentary``, ``opinion``, ``news``) is always *added to*, never replaces,
the research-article net — opinions live there and matter for capturing
how a scientist publicly speaks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fire
from _common import atomic_write_json, author_slug, http_get, load_json

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENALEX_WORKS = "https://api.openalex.org/works"
PAGE_SIZE = 100


def _europepmc(author: str, since_year: int, max_results: int = 500) -> list[dict[str, Any]]:
    query = f'AUTH:"{author}" AND (FIRST_PDATE:[{since_year} TO 3000])'
    out: list[dict[str, Any]] = []
    cursor = "*"
    while True:
        response = http_get(
            EUROPE_PMC,
            params={
                "query": query,
                "format": "json",
                "resultType": "lite",
                "pageSize": PAGE_SIZE,
                "cursorMark": cursor,
            },
        )
        payload = response.json()
        hits = payload.get("resultList", {}).get("result", [])
        if not hits:
            break
        out.extend(hits)
        next_cursor = payload.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor or len(out) >= max_results:
            break
        cursor = next_cursor
    return out[:max_results]


def _openalex(author: str, since_year: int, max_results: int = 500) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = "*"
    while True:
        response = http_get(
            OPENALEX_WORKS,
            params={
                "search": author,
                "filter": f"from_publication_date:{since_year}-01-01",
                "per-page": PAGE_SIZE,
                "cursor": cursor,
            },
        )
        payload = response.json()
        hits = payload.get("results", [])
        if not hits:
            break
        out.extend(hits)
        cursor = payload.get("meta", {}).get("next_cursor")
        if not cursor or len(out) >= max_results:
            break
    return out[:max_results]


def _is_first_or_last_author(name: str, author_list_str: str) -> bool:
    """Tier-2 author check: first/co-first or last/co-last by position.

    Co-first / co-last aren't reliably marked in PMC or OpenAlex metadata,
    so we use a positional heuristic tuned per author-list length:
      - n=1: position 0
      - n=2: positions 0, 1 (both first-or-last)
      - n=3: positions 0, 2 (skip the middle author)
      - n=4: positions 0, 1, 2, 3 (in a 4-author paper, all positions are
        first-or-last-adjacent — first/co-first or co-last/last)
      - n>=5: positions 0, 1, n-2, n-1 (first 2 + last 2 = co-first / co-last)
    """
    names = [a.strip().lower() for a in author_list_str.split(",") if a.strip()]
    n = len(names)
    if n == 0:
        return False
    target = name.lower().split()[-1]
    if n == 1:
        check = {0}
    elif n == 2:
        check = {0, 1}
    elif n == 3:
        check = {0, 2}
    elif n == 4:
        check = {0, 1, 2, 3}
    else:
        check = {0, 1, n - 2, n - 1}
    return any(target in names[i] for i in check)


def _scientist_in_authors(name: str, author_list_str: str) -> bool:
    """Pre-filter for OpenAlex false positives.

    Drops papers where the scientist's surname doesn't appear in the author list
    at all (a name-only OpenAlex search can return papers by other people).
    """
    target = name.lower().split()[-1]
    return any(target in a.lower() for a in author_list_str.split(",") if a.strip())


def _assign_tier(record: dict[str, Any], name: str, primary_terms: list[str]) -> int:
    """Unified tier model.

    - Tier 1 = (first/last author) AND (topic-matching)  — strongest signal
    - Tier 2 = (first/last author) XOR (topic-matching)  — one signal
    - Tier 3 = neither                                    — random-sampled downstream

    "First/last author" preference order:
      1. OpenAlex `author_position` ('first' or 'last') OR `is_corresponding` — when
         present (only on records sourced from OpenAlex), use the structured signal.
      2. Positional heuristic on the comma-joined author string (EuropePMC fallback).
    """
    haystack = " ".join([record.get("title", ""), record.get("abstract", "")]).lower()
    has_topic = bool(primary_terms) and any(term.lower() in haystack for term in primary_terms)

    # Prefer structured OpenAlex fields when available
    oa_pos = record.get("openalex_author_position")
    if oa_pos in ("first", "last") or record.get("openalex_is_corresponding"):
        is_first_last = True
    elif oa_pos == "middle":
        is_first_last = False
    else:
        is_first_last = _is_first_or_last_author(name, record.get("authors", ""))

    record["is_first_last"] = is_first_last
    record["topic_match"] = has_topic
    if is_first_last and has_topic:
        return 1
    if is_first_last or has_topic:
        return 2
    return 3


def _from_europepmc(hit: dict[str, Any], name: str, primary_terms: list[str]) -> dict[str, Any]:
    rec = {
        "id": f"europepmc:{hit.get('id', '')}",
        "doi": hit.get("doi", ""),
        "pmid": hit.get("pmid", ""),
        "pmcid": hit.get("pmcid", ""),
        "year": str(hit.get("pubYear", "")),
        "title": hit.get("title", ""),
        "authors": hit.get("authorString", ""),
        "abstract": hit.get("abstractText", ""),
        "source": "europepmc",
        "pub_type": hit.get("pubType", ""),
        "url": f"https://europepmc.org/article/{hit.get('source', 'med')}/{hit.get('id', '')}",
    }
    rec["tier"] = _assign_tier(rec, name, primary_terms)
    return rec


def _from_openalex(hit: dict[str, Any], name: str, primary_terms: list[str]) -> dict[str, Any]:
    abstract_idx = hit.get("abstract_inverted_index") or {}
    abstract = ""
    if abstract_idx:
        positions: dict[int, str] = {}
        for word, where in abstract_idx.items():
            for pos in where:
                positions[pos] = word
        abstract = " ".join(positions[i] for i in sorted(positions))
    authorships = hit.get("authorships", []) or []
    authors_list = ", ".join(a.get("author", {}).get("display_name", "") for a in authorships)
    # OpenAlex provides structured per-author fields we can use instead of the
    # positional heuristic — preferred over `_is_first_or_last_author(name, ...)`.
    target_surname = name.lower().split()[-1]
    scientist_authorships = [
        a for a in authorships if target_surname in (a.get("author", {}).get("display_name", "") or "").lower()
    ]
    is_first_oa = any(a.get("author_position") == "first" for a in scientist_authorships)
    is_last_oa = any(a.get("author_position") == "last" for a in scientist_authorships)
    is_corresponding_oa = any(a.get("is_corresponding") for a in scientist_authorships)
    rec = {
        "id": f"openalex:{hit.get('id', '').rsplit('/', 1)[-1]}",
        "doi": (hit.get("doi", "") or "").replace("https://doi.org/", ""),
        "pmid": "",
        "pmcid": "",
        "year": str(hit.get("publication_year", "")),
        "title": hit.get("title", "") or "",
        "authors": authors_list,
        "abstract": abstract,
        "source": "openalex",
        "pub_type": hit.get("type", ""),
        "url": hit.get("id", ""),
        "openalex_author_position": ("first" if is_first_oa else "last" if is_last_oa else "middle"),
        "openalex_is_corresponding": bool(is_corresponding_oa),
    }
    rec["tier"] = _assign_tier(rec, name, primary_terms)
    return rec


def _dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        key = (rec.get("doi") or rec.get("pmid") or rec["id"]).lower()
        if not key:
            continue
        existing = seen.get(key)
        if existing is None or (existing["source"] == "openalex" and rec["source"] == "europepmc"):
            seen[key] = rec
    return list(seen.values())


def main(
    author: str,
    out: str,
    *,
    keywords: str | None = None,
    tier: str = "all",
    years: int = 25,
    abstracts_only: bool = False,
    max_results: int = 500,
) -> Path:
    """Search Europe PMC + OpenAlex for ``author``'s works since ``today - years``."""
    primary_terms: list[str] = []
    if keywords:
        primary_terms = list(load_json(Path(keywords)).get("primary_terms", []))

    import datetime as _dt

    since_year = _dt.date.today().year - int(years)
    epmc_hits = _europepmc(author, since_year, max_results)
    oa_hits = _openalex(author, since_year, max_results)
    records = [
        *(_from_europepmc(hit, author, primary_terms) for hit in epmc_hits),
        *(_from_openalex(hit, author, primary_terms) for hit in oa_hits),
    ]
    records = _dedupe(records)
    # Author-presence filter: PMC AUTH:"..." search guarantees author in list,
    # but OpenAlex's broader name search can return false positives (other people
    # with similar names). Drop records where the surname doesn't appear in any
    # author position.
    pre_filter = len(records)
    records = [r for r in records if _scientist_in_authors(author, r.get("authors", ""))]
    dropped_falsepos = pre_filter - len(records)
    if tier != "all":
        wanted = {int(t) for t in str(tier).split(",")}
        records = [r for r in records if r["tier"] in wanted]
    if abstracts_only:
        for rec in records:
            rec["body_text"] = ""

    out_path = Path(out)
    if "{author}" in str(out_path):
        out_path = Path(str(out_path).format(author=author_slug(author)))
    atomic_write_json(out_path, records)
    print(f"{out_path} ({len(records)} works; dropped {dropped_falsepos} false-positive name matches)")
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
