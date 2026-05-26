"""Tests for debate/scripts/search_works.py — n-aware author check, tier semantics, dedup, OpenAlex structured fields."""

from __future__ import annotations

import search_works as sw

# ---- _is_first_or_last_author (n-aware) ----


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


# ---- _scientist_in_authors (OpenAlex false-positive guard) ----


def test_scientist_in_authors_true_at_any_position():
    assert sw._scientist_in_authors("Eric Davidson", "Smith J, Davidson E, Roe T")


def test_scientist_in_authors_false_when_absent():
    assert not sw._scientist_in_authors("Eric Davidson", "Smith J, Other E, Roe T")


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


# ---- _assign_tier prefers OpenAlex structured fields ----


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


# ---- dedupe ----


def test_dedupe_prefers_europepmc_over_openalex():
    epmc = {"id": "europepmc:1", "doi": "10.1/x", "pmid": "", "source": "europepmc"}
    oa = {"id": "openalex:1", "doi": "10.1/x", "pmid": "", "source": "openalex"}
    deduped = sw._dedupe([oa, epmc])
    assert len(deduped) == 1
    assert deduped[0]["source"] == "europepmc"


def test_dedupe_keeps_distinct_dois():
    records = [
        {"id": "a", "doi": "10.1/a", "pmid": "", "source": "europepmc"},
        {"id": "b", "doi": "10.1/b", "pmid": "", "source": "europepmc"},
    ]
    assert len(sw._dedupe(records)) == 2


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
