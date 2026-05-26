"""Tests for debate/scripts/build_briefing.py — briefing assembly + cap enforcement."""

from __future__ import annotations

import json
from pathlib import Path

import build_briefing as bb


def _seed_works(papers_cache: Path, slug: str, records: list[dict]) -> None:
    (papers_cache / "works").mkdir(parents=True, exist_ok=True)
    (papers_cache / "works" / f"{slug}.json").write_text(json.dumps(records), encoding="utf-8")


def _seed_blogs(papers_cache: Path, slug: str, posts: list[dict]) -> None:
    (papers_cache / "blogs").mkdir(parents=True, exist_ok=True)
    (papers_cache / "blogs" / f"{slug}.json").write_text(json.dumps(posts), encoding="utf-8")


def test_format_work_entry_includes_full_text_when_requested():
    record = {"title": "T", "year": "2024", "authors": "X", "doi": "10.1/x", "abstract": "A"}
    out = bb._format_work_entry(record, text="FULL BODY", include_full=True)
    assert "FULL BODY" in out
    assert "**Abstract.**" not in out


def test_format_work_entry_uses_abstract_when_no_full_text():
    record = {"title": "T", "year": "2024", "authors": "X", "doi": "10.1/x", "abstract": "An abstract."}
    out = bb._format_work_entry(record, text="", include_full=False)
    assert "An abstract" in out
    assert "FULL BODY" not in out


def test_build_for_scientist_groups_into_tiers(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(bb, "PAPERS_CACHE", cache)
    records = [
        {
            "title": "GRN paper",
            "year": "2024",
            "authors": "Davidson E",
            "doi": "10.1/a",
            "abstract": "abc",
            "tier": 1,
            "pmcid": "",
            "pmid": "",
        },
        {
            "title": "First-author 2020",
            "year": "2020",
            "authors": "Davidson E, Foo B",
            "doi": "10.1/b",
            "abstract": "def",
            "tier": 2,
            "pmcid": "",
            "pmid": "",
        },
        {
            "title": "Co-author 2019",
            "year": "2019",
            "authors": "Foo B, Davidson E",
            "doi": "10.1/c",
            "abstract": "ghi",
            "tier": 3,
            "pmcid": "",
            "pmid": "",
        },
    ]
    _seed_works(cache, "eric-davidson", records)
    _seed_blogs(cache, "eric-davidson", [])
    briefing, manifest, needs_summary = bb._build_for_scientist(
        "Eric Davidson",
        custom_sources=[],
        n_full_papers_cap=10,
        n_abstracts_cap=10,
    )
    assert "## Tier 1: topic-direct" in briefing
    assert "## Tier 2: first/last-author" in briefing
    assert "## Tier 3: other" in briefing
    assert "GRN paper" in briefing
    assert "First-author 2020" in briefing
    assert "Co-author 2019" in briefing
    assert manifest["tier1"]["papers_total"] == 1
    assert manifest["tier2"]["papers_total"] == 1
    assert manifest["tier3"]["abstracts_total"] == 1
    assert needs_summary == []


def test_build_for_scientist_truncates_tier3_by_cap(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(bb, "PAPERS_CACHE", cache)
    records = [
        {
            "title": f"P{i}",
            "year": str(2000 + i),
            "authors": "Other",
            "doi": f"10/x{i}",
            "abstract": "...",
            "tier": 3,
            "pmcid": "",
            "pmid": "",
        }
        for i in range(50)
    ]
    _seed_works(cache, "test-author", records)
    _seed_blogs(cache, "test-author", [])
    _, manifest, _ = bb._build_for_scientist(
        "Test Author",
        custom_sources=[],
        n_full_papers_cap=10,
        n_abstracts_cap=5,
    )
    assert manifest["tier3"]["abstracts_total"] == 50
    assert manifest["tier3"]["abstracts_kept"] == 5
    assert manifest["tier3"]["abstracts_dropped"] == 45


def test_build_for_scientist_flags_tier2_overflow_for_summary(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(bb, "PAPERS_CACHE", cache)
    # Tier 2 papers with on-disk full text
    pmc_dir = cache / "fulltext" / "pmc"
    pmc_dir.mkdir(parents=True)
    records = []
    for i in range(3):
        pmcid = f"PMC{i}"
        (pmc_dir / f"{pmcid}.txt").write_text("Full text body " + str(i))
        records.append(
            {
                "title": f"T{i}",
                "year": str(2020 - i),
                "authors": "Davidson E",
                "doi": "",
                "pmcid": pmcid,
                "pmid": "",
                "abstract": "abs",
                "tier": 2,
            }
        )
    _seed_works(cache, "eric-davidson", records)
    _seed_blogs(cache, "eric-davidson", [])
    # Cap of 1 full-text means 2 are flagged for summary
    _, manifest, needs_summary = bb._build_for_scientist(
        "Eric Davidson",
        custom_sources=[],
        n_full_papers_cap=1,
        n_abstracts_cap=50,
    )
    assert manifest["tier2"]["papers_with_fulltext_kept"] == 1
    assert len(needs_summary) == 2


def test_main_writes_manifest_and_briefing_files(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(bb, "PAPERS_CACHE", cache)
    out_dir = tmp_path / "event"
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps(
            {
                "event_slug": "slug",
                "topic": "x",
                "scientists": {
                    "A": {"name": "Eric Davidson"},
                    "B": {"name": "Alfonso Martinez"},
                    "C": {"name": "Marc Kirschner"},
                },
                "ingestion": {"n_full_papers_cap": 25, "n_abstracts_cap": 500, "custom_sources": {}},
            }
        ),
        encoding="utf-8",
    )
    # Seed minimal works
    for slug in ("eric-davidson", "alfonso-martinez", "marc-kirschner"):
        _seed_works(cache, slug, [])
        _seed_blogs(cache, slug, [])
    bb.main(inputs=str(inputs), out=str(out_dir))
    assert (out_dir / "manifest.json").exists()
    for letter in ("A", "B", "C"):
        assert (out_dir / f"briefing_{letter}.md").exists()
