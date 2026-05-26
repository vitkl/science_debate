"""Tests for debate/scripts/new_debate_event.py — folder naming + skeleton."""

from __future__ import annotations

import json
import re
from pathlib import Path

import new_debate_event as nde


def test_last_name_picks_final_token():
    assert nde._last_name("Eric Davidson") == "davidson"
    assert nde._last_name("Alfonso Martinez Arias") == "arias"
    assert nde._last_name("  ") == "unknown"


def test_hash_uses_session_id_when_set(monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "ab12cd-3456-ef78-9012-3456")
    h = nde._hash()
    assert len(h) == 6
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_falls_back_to_random_when_no_session_id(monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    h = nde._hash()
    assert len(h) == 6
    assert all(c in "0123456789abcdef" for c in h)


def test_main_creates_event_folder_with_expected_structure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(nde, "DEBATE_EVENTS", tmp_path)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "deadbeef00000000")
    event_dir = nde.main(
        scientist_a="Eric Davidson",
        scientist_b="Alfonso Martinez Arias",
        scientist_c="Marc Kirschner",
        topic="gene regulatory networks",
        date="2026-05-26",
    )
    assert event_dir.is_dir()
    # Role-letter suffix (A/B) disambiguates same-surname scientists.
    assert re.fullmatch(r"davidsonA_ariasB_2026-05-26_[0-9a-f]{6}", event_dir.name)

    inputs = json.loads((event_dir / "inputs.json").read_text())
    assert inputs["topic"] == "gene regulatory networks"
    assert inputs["scientists"]["A"]["name"] == "Eric Davidson"
    assert inputs["scientists"]["B"]["name"] == "Alfonso Martinez Arias"
    assert inputs["scientists"]["C"]["name"] == "Marc Kirschner"
    assert inputs["debate"]["total_minutes"] == 80
    # New tier-cap knobs
    assert inputs["ingestion"]["n_tier1_max"] is None  # sacred by default
    assert inputs["ingestion"]["n_tier2a_full_max"] == 25
    assert inputs["ingestion"]["n_tier3_sample"] == 15
    assert inputs["ingestion"]["n_full_papers_cap"] == 25
    # Phase A toggles default to None (Moderator asks at runtime)
    assert inputs["ingestion"]["include_youtube"] is None
    assert inputs["ingestion"]["include_books"] is None
    # B4 "drop" lever
    assert inputs["ingestion"]["dropped_source_ids"] == {
        "Eric Davidson": [],
        "Alfonso Martinez Arias": [],
        "Marc Kirschner": [],
    }
    # Old field name is gone (no back-compat)
    assert "n_abstracts_cap" not in inputs["ingestion"]
    assert "pre_fetch_urls" not in inputs["ingestion"]
    assert set(inputs["models"]) == {"A", "B", "C", "J"}
