"""Tests for debate/scripts/search_books.py — Google Books filter, OpenAlex merge, tier assignment."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import search_books as sb


def _google_volume(title: str, authors: list[str], description: str = "", isbn13: str = "") -> dict:
    return {
        "id": "vol-" + title.replace(" ", "-").lower(),
        "volumeInfo": {
            "title": title,
            "authors": authors,
            "description": description,
            "publishedDate": "2018-01-01",
            "previewLink": f"https://books.google.com/{title.replace(' ', '_')}",
            "industryIdentifiers": [{"type": "ISBN_13", "identifier": isbn13}] if isbn13 else [],
        },
        "searchInfo": {"textSnippet": "snippet text"},
        "accessInfo": {"viewability": "PARTIAL"},
    }


def test_from_google_books_keeps_books_by_target_scientist():
    vol = _google_volume(
        "The Book of Why", ["Judea Pearl", "Dana Mackenzie"], description="causal inference", isbn13="9780465097609"
    )
    rec = sb._from_google_books(vol, "Judea Pearl", ["causal"])
    assert rec is not None
    assert rec["title"] == "The Book of Why"
    assert rec["isbn"] == "9780465097609"
    assert rec["topic_match"] is True
    assert rec["tier"] == 1
    assert rec["is_first_last"] is True  # author search guarantees authorship


def test_from_google_books_drops_books_without_scientist_in_authors():
    """A book that just mentions Pearl in the foreword should be filtered out."""
    vol = _google_volume("Statistical Methods", ["John Smith"], description="", isbn13="111")
    rec = sb._from_google_books(vol, "Judea Pearl", ["causal"])
    assert rec is None


def test_from_google_books_tier_2_without_topic():
    vol = _google_volume("Memoir", ["Judea Pearl"], description="biography")
    rec = sb._from_google_books(vol, "Judea Pearl", ["causal", "do-calculus"])
    assert rec is not None
    assert rec["topic_match"] is False
    assert rec["tier"] == 2


def test_from_google_books_handles_substring_surname_safely():
    # 'Lee' must not match 'Banerjee'
    vol = _google_volume("Some Book", ["Banerjee S"], isbn13="222")
    rec = sb._from_google_books(vol, "Anna Lee", [])
    assert rec is None


def test_isbn_from_volume_prefers_isbn13():
    vol = {
        "volumeInfo": {
            "industryIdentifiers": [
                {"type": "ISBN_10", "identifier": "0465097600"},
                {"type": "ISBN_13", "identifier": "9780465097609"},
            ]
        }
    }
    assert sb._isbn_from_volume(vol) == "9780465097609"


def test_dedup_books_merges_by_isbn():
    google = sb._from_google_books(
        _google_volume("The Book of Why", ["Judea Pearl"], description="causal inference", isbn13="9780465097609"),
        "Judea Pearl",
        ["causal"],
    )
    openalex = {
        "id": "openalex:W1",
        "title": "The Book of Why",
        "authors": "Judea Pearl",
        "year": "2018",
        "abstract": "",
        "isbn": "9780465097609",
        "is_book": True,
        "openalex_author_position": "first",
        "openalex_is_corresponding": False,
    }
    oa_rec = sb._from_openalex_book(openalex, ["causal"])
    merged = sb._dedupe_books([google, oa_rec], ["causal"])
    assert len(merged) == 1
    kept = merged[0]
    # Google Books has rich description; OpenAlex contributes structured author info
    assert kept["isbn"] == "9780465097609"
    # OA's first-author signal should propagate
    assert kept["is_first_last"] is True


def test_dedup_books_no_isbn_falls_back_to_title_year():
    google_a = sb._from_google_books(_google_volume("Causality", ["Judea Pearl"], description=""), "Judea Pearl", [])
    google_b = sb._from_google_books(_google_volume("Causality", ["Judea Pearl"], description=""), "Judea Pearl", [])
    # Same title + year → dedup to 1
    google_a["year"] = "2009"
    google_b["year"] = "2009"
    merged = sb._dedupe_books([google_a, google_b], [])
    assert len(merged) == 1


def test_main_writes_payload_with_tier_sorted_books(tmp_path: Path, monkeypatch):
    out_path = tmp_path / "{scientist}.json"
    # Mock http_get to return two Google Books volumes
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "items": [
            _google_volume("The Book of Why", ["Judea Pearl"], description="causal inference", isbn13="111"),
            _google_volume("Memoir", ["Judea Pearl"], description="biography", isbn13="222"),
        ]
    }
    monkeypatch.setattr(sb, "http_get", lambda *args, **kwargs: mock_response)

    result_path = sb.main(
        scientist="Judea Pearl",
        out=str(out_path),
        keywords=None,
        works=None,
    )
    assert result_path.exists()
    payload = json.loads(result_path.read_text())
    assert payload["scientist"] == "Judea Pearl"
    assert payload["n_google"] == 2
    assert payload["n_openalex"] == 0
    assert payload["n_merged"] == 2
    # No keywords passed → no topic match → all tier 2
    assert all(b["tier"] == 2 for b in payload["books"])


def test_main_merges_openalex_works_when_works_path_provided(tmp_path: Path, monkeypatch):
    works_path = tmp_path / "judea-pearl.json"
    works_path.write_text(
        json.dumps(
            [
                {
                    "id": "openalex:W42",
                    "title": "The Book of Why",
                    "authors": "Judea Pearl",
                    "year": "2018",
                    "abstract": "causal inference and the new science",
                    "isbn": "9780465097609",
                    "is_book": True,
                    "openalex_author_position": "first",
                    "openalex_is_corresponding": False,
                },
                {
                    "id": "openalex:W43",
                    "title": "Regular paper",
                    "authors": "Judea Pearl",
                    "year": "2020",
                    "abstract": "...",
                    "is_book": False,  # NOT a book — must be skipped by search_books
                },
            ]
        )
    )
    out_path = tmp_path / "judea-pearl-books.json"

    # No Google Books results — only OpenAlex books should surface
    mock_response = MagicMock()
    mock_response.json.return_value = {"items": []}
    monkeypatch.setattr(sb, "http_get", lambda *args, **kwargs: mock_response)

    keywords_path = tmp_path / "keywords.json"
    keywords_path.write_text(json.dumps({"primary_terms": ["causal"]}))

    sb.main(
        scientist="Judea Pearl",
        out=str(out_path),
        keywords=str(keywords_path),
        works=str(works_path),
    )
    payload = json.loads(out_path.read_text())
    assert payload["n_google"] == 0
    assert payload["n_openalex"] == 1  # only the book — regular paper excluded
    book = payload["books"][0]
    assert book["title"] == "The Book of Why"
    assert book["topic_match"] is True
    assert book["tier"] == 1  # author + topic
