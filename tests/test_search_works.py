"""Tests for debate/scripts/search_works.py — author check, tier semantics, dedupe MERGE, structured-field parsing."""

from __future__ import annotations

import _common
import search_works as sw

# ---- _is_first_or_last_author (n-aware positional heuristic) ----


def test_author_check_n1_first_only():
    assert sw._is_first_or_last_author("Eric Davidson", "Davidson E")


def test_author_check_n2_both_positions():
    assert sw._is_first_or_last_author("Eric Davidson", "Davidson E, Smith J")
    assert sw._is_first_or_last_author("Eric Davidson", "Smith J, Davidson E")


def test_author_check_n3_first_and_last_only_middle_excluded():
    assert sw._is_first_or_last_author("Eric Davidson", "Davidson E, Smith J, Roe T")  # first
    assert sw._is_first_or_last_author("Eric Davidson", "Smith J, Roe T, Davidson E")  # last
    assert not sw._is_first_or_last_author("Eric Davidson", "Smith J, Davidson E, Roe T")  # MIDDLE excluded


def test_author_check_n4_all_positions_eligible():
    # In a 4-author paper, all positions are first-or-last-adjacent
    for pos in range(4):
        authors = ["X" + str(i) for i in range(4)]
        authors[pos] = "Davidson E"
        assert sw._is_first_or_last_author("Eric Davidson", ", ".join(authors)), f"position {pos} failed"


def test_author_check_n5_first_2_last_2_only_middle_excluded():
    # n=5: positions {0,1,3,4} eligible; position 2 (middle) excluded
    assert sw._is_first_or_last_author("Eric Davidson", "Davidson E, A, B, C, D")
    assert sw._is_first_or_last_author("Eric Davidson", "A, Davidson E, B, C, D")  # co-first
    assert sw._is_first_or_last_author("Eric Davidson", "A, B, C, Davidson E, D")  # co-last
    assert sw._is_first_or_last_author("Eric Davidson", "A, B, C, D, Davidson E")  # last
    assert not sw._is_first_or_last_author("Eric Davidson", "A, B, Davidson E, C, D")  # MIDDLE excluded


def test_author_check_empty_list():
    assert not sw._is_first_or_last_author("Eric Davidson", "")


# ---- scientist_in_authors (token-boundary surname match, in _common) ----


def test_scientist_in_authors_true_at_any_position():
    assert _common.scientist_in_authors("Eric Davidson", "Smith J, Davidson E, Roe T")


def test_scientist_in_authors_false_when_absent():
    assert not _common.scientist_in_authors("Eric Davidson", "Smith J, Other E, Roe T")


def test_scientist_in_authors_rejects_substring_match():
    # 'Lee' must NOT match 'Banerjee'; 'Wang' must NOT match inside a longer name
    assert not _common.scientist_in_authors("Anna Lee", "Banerjee S, Other T")
    assert not _common.scientist_in_authors("Mei Wang", "Huangwang C")


def test_scientist_in_authors_accepts_punctuation_boundary():
    # 'Pearl' should match 'Pearl, J.' and 'J. Pearl'
    assert _common.scientist_in_authors("Judea Pearl", "Pearl, J., Other A")
    assert _common.scientist_in_authors("Judea Pearl", "J. Pearl, Other A")


def test_scientist_in_authors_handles_empty_inputs():
    assert not _common.scientist_in_authors("", "Davidson E")
    assert not _common.scientist_in_authors("Eric Davidson", "")
    assert not _common.scientist_in_authors("   ", "Davidson E")


# ---- _assign_tier (Tier 1 = BOTH author AND topic) ----


def test_assign_tier_1_requires_both_author_and_topic():
    record = {"title": "Gene regulatory networks", "abstract": "", "authors": "Davidson E, Smith J"}
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 1


def test_assign_tier_2_topic_only_when_middle_author():
    record = {"title": "Gene regulatory networks", "abstract": "", "authors": "Smith J, Davidson E, Roe T"}
    # Davidson is middle (position 2 of 3) — author signal absent; topic matches → tier 2
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 2


def test_assign_tier_2_author_only_when_no_keyword_match():
    record = {"title": "Quantum chromodynamics", "abstract": "particle physics", "authors": "Davidson E"}
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 2


def test_assign_tier_3_neither():
    record = {
        "title": "Quantum chromodynamics",
        "abstract": "particle physics",
        "authors": "Smith J, Davidson E, Roe T",
    }
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 3


# ---- _assign_tier prefers structured fields ----


def test_assign_tier_uses_openalex_first_position():
    record = {
        "title": "Other topic",
        "abstract": "",
        "authors": "Smith J, Davidson E, Roe T",
        "openalex_author_position": "first",
        "openalex_is_corresponding": False,
    }
    # Heuristic would say middle (position 2 of 3); OpenAlex says first → tier 2
    assert sw._assign_tier(record, "Eric Davidson", ["unrelated"]) == 2
    assert record["is_first_last"] is True


def test_assign_tier_uses_openalex_corresponding_flag():
    record = {
        "title": "Other",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",
        "openalex_author_position": "middle",
        "openalex_is_corresponding": True,
    }
    # Position says middle; corresponding flag overrides
    assert sw._assign_tier(record, "Eric Davidson", []) == 2
    assert record["is_first_last"] is True


def test_assign_tier_uses_openalex_middle_when_no_corresponding():
    record = {
        "title": "Gene regulatory networks",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",
        "openalex_author_position": "middle",
        "openalex_is_corresponding": False,
    }
    # Topic matches but not author → tier 2
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 2


def test_assign_tier_falls_back_to_positional_when_openalex_position_is_none():
    # OA returns None when scientist had no matched authorship — heuristic should run
    record = {
        "title": "Other",
        "abstract": "",
        "authors": "Davidson E, Other T",  # heuristic: position 0 → first/last
        "openalex_is_corresponding": False,
    }
    assert sw._assign_tier(record, "Eric Davidson", []) == 2
    assert record["is_first_last"] is True


def test_assign_tier_prefers_epmc_over_openalex_when_both_present():
    # EPMC says first (true); OA says middle (false). EPMC wins → tier 2.
    record = {
        "title": "Other",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",
        "epmc_author_position": "first",
        "epmc_is_corresponding": False,
        "openalex_author_position": "middle",
        "openalex_is_corresponding": False,
    }
    assert sw._assign_tier(record, "Eric Davidson", []) == 2
    assert record["is_first_last"] is True


def test_assign_tier_uses_epmc_corresponding_flag():
    record = {
        "title": "Other",
        "abstract": "",
        "authors": "A, B, Davidson E",
        "epmc_author_position": "middle",
        "epmc_is_corresponding": True,
    }
    assert sw._assign_tier(record, "Eric Davidson", []) == 2
    assert record["is_first_last"] is True


# ---- _epmc_author_position (structured EPMC author parsing) ----


def test_epmc_author_position_first_with_corresponding():
    hit = {
        "authorList": {
            "author": [
                {"lastName": "Davidson", "fullName": "Davidson E", "authorIsCorresponding": "Y"},
                {"lastName": "Smith", "fullName": "Smith J"},
                {"lastName": "Roe", "fullName": "Roe T"},
            ],
        },
    }
    pos, corr = sw._epmc_author_position(hit, "Eric Davidson")
    assert pos == "first"
    assert corr is True


def test_epmc_author_position_last():
    hit = {
        "authorList": {
            "author": [
                {"lastName": "Smith", "fullName": "Smith J"},
                {"lastName": "Roe", "fullName": "Roe T"},
                {"lastName": "Davidson", "fullName": "Davidson E"},
            ],
        },
    }
    pos, corr = sw._epmc_author_position(hit, "Eric Davidson")
    assert pos == "last"
    assert corr is False


def test_epmc_author_position_middle():
    hit = {
        "authorList": {
            "author": [
                {"lastName": "Smith", "fullName": "Smith J"},
                {"lastName": "Davidson", "fullName": "Davidson E"},
                {"lastName": "Roe", "fullName": "Roe T"},
            ],
        },
    }
    pos, _corr = sw._epmc_author_position(hit, "Eric Davidson")
    assert pos == "middle"


def test_epmc_author_position_none_when_no_match():
    hit = {
        "authorList": {
            "author": [
                {"lastName": "Smith", "fullName": "Smith J"},
                {"lastName": "Roe", "fullName": "Roe T"},
            ],
        },
    }
    pos, corr = sw._epmc_author_position(hit, "Eric Davidson")
    assert pos is None
    assert corr is False


def test_epmc_author_position_handles_empty_authorlist():
    pos, corr = sw._epmc_author_position({}, "Eric Davidson")
    assert pos is None
    assert corr is False


def test_epmc_author_position_rejects_substring_match():
    # 'Lee' must not match 'Banerjee'
    hit = {
        "authorList": {
            "author": [{"lastName": "Banerjee", "fullName": "Banerjee S"}],
        },
    }
    pos, _corr = sw._epmc_author_position(hit, "Anna Lee")
    assert pos is None


# ---- dedupe (MERGE structured fields, recompute tier) ----


def test_dedupe_prefers_europepmc_over_openalex():
    epmc = {"id": "europepmc:1", "doi": "10.1/x", "pmid": "", "source": "europepmc", "tier": 3}
    oa = {"id": "openalex:1", "doi": "10.1/x", "pmid": "", "source": "openalex", "tier": 3}
    deduped = sw._dedupe([oa, epmc], "Eric Davidson", [])
    assert len(deduped) == 1
    assert deduped[0]["source"] == "europepmc"


def test_dedupe_keeps_distinct_dois():
    records = [
        {"id": "a", "doi": "10.1/a", "pmid": "", "source": "europepmc", "tier": 3},
        {"id": "b", "doi": "10.1/b", "pmid": "", "source": "europepmc", "tier": 3},
    ]
    assert len(sw._dedupe(records, "Eric Davidson", [])) == 2


def test_dedupe_merges_openalex_fields_into_kept_europepmc():
    """When EPMC wins, OpenAlex structured fields are merged onto the kept record."""
    epmc = {
        "id": "europepmc:1",
        "doi": "10.1/x",
        "pmid": "",
        "source": "europepmc",
        "title": "Gene regulatory networks",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",  # heuristic: middle author → not first/last
        "tier": 2,
    }
    oa = {
        "id": "openalex:1",
        "doi": "10.1/x",
        "pmid": "",
        "source": "openalex",
        "title": "Gene regulatory networks",
        "abstract": "",
        "authors": "Davidson E, A, B, C, D",
        "openalex_author_position": "first",
        "openalex_is_corresponding": True,
        "is_book": False,
        "tier": 1,
    }
    deduped = sw._dedupe([oa, epmc], "Eric Davidson", ["gene regulatory networks"])
    assert len(deduped) == 1
    kept = deduped[0]
    assert kept["source"] == "europepmc"
    assert kept["openalex_author_position"] == "first"
    assert kept["openalex_is_corresponding"] is True
    # Tier must be recomputed using merged OA fields → now 1 (author from OA + topic)
    assert kept["tier"] == 1


def test_dedupe_merges_structured_fields_when_epmc_arrives_first():
    """Order independent: EPMC first, OA second — merge still happens."""
    epmc = {
        "id": "europepmc:1",
        "doi": "10.1/x",
        "pmid": "",
        "source": "europepmc",
        "title": "Other",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",
        "tier": 3,
    }
    oa = {
        "id": "openalex:1",
        "doi": "10.1/x",
        "pmid": "",
        "source": "openalex",
        "title": "Other",
        "abstract": "",
        "authors": "A, B, Davidson E, C, D",
        "openalex_author_position": "last",
        "openalex_is_corresponding": False,
        "tier": 2,
    }
    deduped = sw._dedupe([epmc, oa], "Eric Davidson", [])
    assert len(deduped) == 1
    kept = deduped[0]
    assert kept["source"] == "europepmc"
    assert kept["openalex_author_position"] == "last"
    assert kept["tier"] == 2  # recomputed using merged OA last-author


# ---- record builders ----


def test_from_europepmc_assigns_tier_via_keyword_and_author():
    hit = {
        "id": "12345",
        "doi": "10.1/x",
        "pmid": "12345",
        "pmcid": "PMC9",
        "pubYear": 2020,
        "title": "Gene regulatory networks in dev",
        "authorString": "Davidson E",
        "abstractText": "...",
        "source": "med",
        "pubType": "research-article",
    }
    rec = sw._from_europepmc(hit, "Eric Davidson", ["gene regulatory networks"])
    assert rec["tier"] == 1  # both author and topic match
    assert rec["pmid"] == "12345"
    assert rec["source"] == "europepmc"
    assert rec["is_first_last"] is True
    assert rec["topic_match"] is True


def test_from_europepmc_extracts_corresponding_author():
    """With resultType=core, EPMC returns authorList with structured per-author fields."""
    hit = {
        "id": "12345",
        "doi": "10.1/x",
        "pmid": "12345",
        "pmcid": "PMC9",
        "pubYear": 2020,
        "title": "Other",
        "authorString": "Smith J, Roe T, Davidson E",
        "abstractText": "",
        "source": "med",
        "pubType": "research-article",
        "authorList": {
            "author": [
                {"lastName": "Smith", "fullName": "Smith J"},
                {"lastName": "Roe", "fullName": "Roe T"},
                {"lastName": "Davidson", "fullName": "Davidson E", "authorIsCorresponding": "Y"},
            ],
        },
    }
    rec = sw._from_europepmc(hit, "Eric Davidson", [])
    assert rec["epmc_author_position"] == "last"
    assert rec["epmc_is_corresponding"] is True
    assert rec["is_first_last"] is True
    assert rec["tier"] == 2  # author only


def test_from_openalex_carries_structured_author_fields():
    hit = {
        "id": "https://openalex.org/W42",
        "doi": "https://doi.org/10.1/x",
        "publication_year": 2020,
        "title": "Other paper",
        "authorships": [
            {"author": {"display_name": "Eric Davidson"}, "author_position": "first", "is_corresponding": True},
            {"author": {"display_name": "B Smith"}, "author_position": "last", "is_corresponding": False},
        ],
        "abstract_inverted_index": {"Cells": [0], "are": [1], "complex": [2]},
        "type": "article",
    }
    rec = sw._from_openalex(hit, "Eric Davidson", [])
    assert rec["abstract"] == "Cells are complex"
    assert rec["openalex_author_position"] == "first"
    assert rec["openalex_is_corresponding"] is True
    assert rec["is_first_last"] is True
    assert rec["tier"] == 2  # author only (no topic match)
    assert rec["doi"] == "10.1/x"


def test_from_openalex_returns_no_position_when_scientist_not_in_authors():
    """When no authorship matches the scientist (false-positive search), the
    structured author position is omitted entirely — the heuristic must run instead."""
    hit = {
        "id": "https://openalex.org/W42",
        "doi": "https://doi.org/10.1/x",
        "publication_year": 2020,
        "title": "Other",
        "authorships": [
            {"author": {"display_name": "Other A"}, "author_position": "first"},
            {"author": {"display_name": "Other B"}, "author_position": "last"},
        ],
        "abstract_inverted_index": {},
        "type": "article",
    }
    rec = sw._from_openalex(hit, "Eric Davidson", [])
    assert "openalex_author_position" not in rec  # absent (None sentinel)
    # Heuristic on the authors string also won't find Davidson → not first_last
    assert rec["is_first_last"] is False


def test_from_openalex_marks_books():
    hit = {
        "id": "https://openalex.org/W99",
        "doi": "",
        "publication_year": 2018,
        "title": "The Book of Why",
        "authorships": [
            {"author": {"display_name": "Judea Pearl"}, "author_position": "first"},
        ],
        "abstract_inverted_index": {},
        "type": "book",
        "ids": {"isbn13": "9780465097609"},
    }
    rec = sw._from_openalex(hit, "Judea Pearl", [])
    assert rec["is_book"] is True
    assert rec["isbn"] == "9780465097609"


def test_from_openalex_non_book_type():
    hit = {
        "id": "https://openalex.org/W1",
        "doi": "",
        "publication_year": 2020,
        "title": "Paper",
        "authorships": [
            {"author": {"display_name": "Eric Davidson"}, "author_position": "first"},
        ],
        "abstract_inverted_index": {},
        "type": "article",
    }
    rec = sw._from_openalex(hit, "Eric Davidson", [])
    assert rec["is_book"] is False
    assert rec["isbn"] == ""
