"""Tests for debate/scripts/search_works.py — tier assignment, author logic, dedupe."""

from __future__ import annotations

import search_works as sw


def test_is_first_or_last_author_matches_first():
    assert sw._is_first_or_last_author("Eric Davidson", "Davidson E, Smith J, Roe T")


def test_is_first_or_last_author_matches_last():
    assert sw._is_first_or_last_author("Eric Davidson", "Smith J, Roe T, Davidson E")


def test_is_first_or_last_author_rejects_middle_only():
    assert not sw._is_first_or_last_author("Eric Davidson", "Smith J, Davidson E, Roe T")


def test_is_first_or_last_author_handles_empty_list():
    assert not sw._is_first_or_last_author("Eric Davidson", "")


def test_assign_tier_primary_keyword_match_wins():
    record = {"title": "Gene regulatory networks in development", "abstract": "x", "authors": ""}
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 1


def test_assign_tier_first_last_author_when_no_keyword_match():
    record = {"title": "Other topic", "abstract": "x", "authors": "Davidson E, Foo B"}
    assert sw._assign_tier(record, "Eric Davidson", ["unrelated"]) == 2


def test_assign_tier_falls_through_to_three():
    record = {"title": "Quantum chromodynamics", "abstract": "particle physics", "authors": "Foo B, Bar C"}
    assert sw._assign_tier(record, "Eric Davidson", ["gene regulatory networks"]) == 3


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


def test_from_europepmc_assigns_tier_via_keyword_match():
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
    assert rec["tier"] == 1
    assert rec["pmid"] == "12345"
    assert rec["source"] == "europepmc"


def test_from_openalex_reconstructs_abstract_from_inverted_index():
    hit = {
        "id": "https://openalex.org/W42",
        "doi": "https://doi.org/10.1/x",
        "publication_year": 2020,
        "title": "Other paper",
        "authorships": [{"author": {"display_name": "Eric Davidson"}}, {"author": {"display_name": "B"}}],
        "abstract_inverted_index": {"Cells": [0], "are": [1], "complex": [2]},
        "type": "article",
    }
    rec = sw._from_openalex(hit, "Eric Davidson", [])
    assert rec["abstract"] == "Cells are complex"
    assert rec["tier"] == 2  # first author
    assert rec["doi"] == "10.1/x"
