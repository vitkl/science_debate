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

import re
from pathlib import Path
from typing import Any

import fire
from _common import atomic_write_json, author_slug, http_get, load_json, scientist_in_authors

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
                "resultType": "core",
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


def _assign_tier(record: dict[str, Any], name: str, primary_terms: list[str]) -> int:
    """Unified tier model.

    - Tier 1 = (first/last author) AND (topic-matching)  — strongest signal
    - Tier 2 = (first/last author) XOR (topic-matching)  — one signal
    - Tier 3 = neither                                    — random-sampled downstream

    "First/last author" preference order:
      1. EuropePMC structured fields (epmc_author_position / epmc_is_corresponding)
      2. OpenAlex structured fields (openalex_author_position / openalex_is_corresponding)
      3. Positional heuristic on the comma-joined author string (fallback)

    A 'middle' verdict from a structured source is definitive; None means
    "no structured info" and the next preference level is consulted.
    """
    haystack = " ".join([record.get("title", ""), record.get("abstract", "")]).lower()
    has_topic = bool(primary_terms) and any(term.lower() in haystack for term in primary_terms)

    epmc_pos = record.get("epmc_author_position")
    oa_pos = record.get("openalex_author_position")
    if epmc_pos in ("first", "last") or record.get("epmc_is_corresponding"):
        is_first_last = True
    elif epmc_pos == "middle":
        is_first_last = False
    elif oa_pos in ("first", "last") or record.get("openalex_is_corresponding"):
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


def _epmc_author_position(hit: dict[str, Any], name: str) -> tuple[str | None, bool]:
    """Extract structured first/last + corresponding flag from EuropePMC `core` payload.

    Returns (position, is_corresponding) where position is "first"/"last"/"middle"
    or None when the scientist has no matched authorship in the authorList.
    """
    author_list = (hit.get("authorList") or {}).get("author") or []
    if not author_list:
        return None, False
    parts = name.lower().split()
    if not parts:
        return None, False
    target = parts[-1].strip()
    if not target:
        return None, False
    matched_idxs: list[int] = []
    is_corresponding = False
    for idx, author in enumerate(author_list):
        last_name = (author.get("lastName") or "").lower()
        full_name = (author.get("fullName") or "").lower()
        # Token-boundary match in lastName field or fullName
        if not last_name and not full_name:
            continue
        haystack = f"{last_name} {full_name}"
        pat = r"\b" + re.escape(target) + r"\b"
        if re.search(pat, haystack):
            matched_idxs.append(idx)
            if author.get("authorIsCorresponding") in ("Y", True, "true"):
                is_corresponding = True
    if not matched_idxs:
        return None, False
    n = len(author_list)
    last_pos = n - 1
    if any(i == 0 for i in matched_idxs):
        return "first", is_corresponding
    if any(i == last_pos for i in matched_idxs):
        return "last", is_corresponding
    return "middle", is_corresponding


def _from_europepmc(hit: dict[str, Any], name: str, primary_terms: list[str]) -> dict[str, Any]:
    epmc_pos, epmc_corr = _epmc_author_position(hit, name)
    rec: dict[str, Any] = {
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
    if epmc_pos is not None:
        rec["epmc_author_position"] = epmc_pos
    rec["epmc_is_corresponding"] = epmc_corr
    rec["tier"] = _assign_tier(rec, name, primary_terms)
    return rec


def _extract_openalex_isbn(hit: dict[str, Any]) -> str:
    ids = hit.get("ids") or {}
    for key in ("isbn13", "isbn10", "isbn"):
        v = ids.get(key)
        if v:
            return str(v)
    return ""


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
    # Token-boundary surname match on each authorship display_name.
    parts = name.lower().split()
    target_surname = parts[-1].strip() if parts else ""
    scientist_authorships = []
    if target_surname:
        pat = r"\b" + re.escape(target_surname) + r"\b"
        scientist_authorships = [
            a for a in authorships if re.search(pat, (a.get("author", {}).get("display_name", "") or "").lower())
        ]
    is_first_oa = any(a.get("author_position") == "first" for a in scientist_authorships)
    is_last_oa = any(a.get("author_position") == "last" for a in scientist_authorships)
    is_corresponding_oa = any(a.get("is_corresponding") for a in scientist_authorships)
    if not scientist_authorships:
        oa_position: str | None = None
    elif is_first_oa:
        oa_position = "first"
    elif is_last_oa:
        oa_position = "last"
    else:
        oa_position = "middle"
    work_type = hit.get("type", "") or ""
    is_book = work_type in {"book", "book-chapter"}
    rec: dict[str, Any] = {
        "id": f"openalex:{hit.get('id', '').rsplit('/', 1)[-1]}",
        "doi": (hit.get("doi", "") or "").replace("https://doi.org/", ""),
        "pmid": "",
        "pmcid": "",
        "year": str(hit.get("publication_year", "")),
        "title": hit.get("title", "") or "",
        "authors": authors_list,
        "abstract": abstract,
        "source": "openalex",
        "pub_type": work_type,
        "url": hit.get("id", ""),
        "is_book": is_book,
        "isbn": _extract_openalex_isbn(hit),
        "openalex_is_corresponding": bool(is_corresponding_oa),
    }
    if oa_position is not None:
        rec["openalex_author_position"] = oa_position
    rec["tier"] = _assign_tier(rec, name, primary_terms)
    return rec


_STRUCTURED_MERGE_FIELDS = (
    "openalex_author_position",
    "openalex_is_corresponding",
    "epmc_author_position",
    "epmc_is_corresponding",
    "is_book",
    "isbn",
)


def _merge_structured(into: dict[str, Any], from_rec: dict[str, Any]) -> None:
    """Copy useful structured fields from ``from_rec`` onto ``into`` when missing."""
    for field in _STRUCTURED_MERGE_FIELDS:
        if field in from_rec and field not in into:
            into[field] = from_rec[field]


def _dedupe(records: list[dict[str, Any]], name: str, primary_terms: list[str]) -> list[dict[str, Any]]:
    """Dedup by DOI / PMID / id, MERGING structured fields when duplicates collide.

    Preference: EuropePMC wins (better abstract quality). When OpenAlex is dropped,
    its structured author-position fields are copied onto the kept EPMC record so
    tier assignment can use them. Tier is recomputed after merge.
    """
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        key = (rec.get("doi") or rec.get("pmid") or rec["id"]).lower()
        if not key:
            continue
        existing = seen.get(key)
        if existing is None:
            seen[key] = rec
            continue
        # Always merge structured fields between duplicates
        if existing["source"] == "openalex" and rec["source"] == "europepmc":
            # EPMC wins; merge OA fields onto rec, then replace
            _merge_structured(rec, existing)
            rec["tier"] = _assign_tier(rec, name, primary_terms)
            seen[key] = rec
        else:
            # Keep existing; merge any fields it doesn't have from rec
            _merge_structured(existing, rec)
            existing["tier"] = _assign_tier(existing, name, primary_terms)
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
    import sys

    if not author or not author.strip():
        raise ValueError("author name is required and must be non-empty")

    since_year = _dt.date.today().year - int(years)
    try:
        epmc_hits = _europepmc(author, since_year, max_results)
    except Exception as exc:  # noqa: BLE001 — one backend failure shouldn't kill the script
        print(f"WARNING: EuropePMC search failed for {author}: {exc}", file=sys.stderr)
        epmc_hits = []
    try:
        oa_hits = _openalex(author, since_year, max_results)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: OpenAlex search failed for {author}: {exc}", file=sys.stderr)
        oa_hits = []
    records = [
        *(_from_europepmc(hit, author, primary_terms) for hit in epmc_hits),
        *(_from_openalex(hit, author, primary_terms) for hit in oa_hits),
    ]
    records = _dedupe(records, author, primary_terms)
    # Author-presence filter: PMC AUTH:"..." search guarantees author in list,
    # but OpenAlex's broader name search can return false positives (other people
    # with similar names). Drop records where the surname doesn't appear in any
    # author position. Uses token-boundary matching to avoid 'Lee' inside 'Banerjee'.
    pre_filter = len(records)
    records = [r for r in records if scientist_in_authors(author, r.get("authors", ""))]
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
