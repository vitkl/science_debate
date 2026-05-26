"""Tests for debate/scripts/generate_search_keywords.py — CSV split + persistence."""

from __future__ import annotations

import json
from pathlib import Path

import generate_search_keywords as gsk


def test_split_csv_trims_and_drops_empty():
    assert gsk._split_csv(" foo , bar ,, baz, ") == ["foo", "bar", "baz"]
    assert gsk._split_csv("") == []
    assert gsk._split_csv(None) == []


def test_main_writes_expected_schema(tmp_path: Path):
    out = tmp_path / "keywords.json"
    gsk.main(
        topic="gene regulatory networks",
        out=str(out),
        primary="GRN, gene regulatory network",
        synonyms="cis-regulatory, transcription factor network",
        opposing="self-organisation",
    )
    payload = json.loads(out.read_text())
    assert payload["topic"] == "gene regulatory networks"
    assert payload["primary_terms"] == ["GRN", "gene regulatory network"]
    assert payload["synonyms"] == ["cis-regulatory", "transcription factor network"]
    assert payload["opposing_terms"] == ["self-organisation"]
    assert "editorial" in payload["publication_types"]
    assert "review" in payload["publication_types"]


def test_main_publication_types_overridable(tmp_path: Path):
    out = tmp_path / "k.json"
    gsk.main(topic="t", out=str(out), publication_types="editorial,letter")
    payload = json.loads(out.read_text())
    assert payload["publication_types"] == ["editorial", "letter"]
