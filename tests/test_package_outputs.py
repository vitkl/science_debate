"""Tests for debate/scripts/package_outputs.py — highlights + full zip artefacts."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import package_outputs as po


def _seed_event(event_dir: Path) -> None:
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "transcript.md").write_text("# Transcript\n\nbody")
    (event_dir / "audience.log").write_text("Audience: continue")
    (event_dir / "manifest.json").write_text(json.dumps({"slug": event_dir.name}))
    (event_dir / "inputs.json").write_text(json.dumps({"topic": "x"}))
    (event_dir / "usage.json").write_text(json.dumps({"tokens": 1234}))
    (event_dir / "article_same_field.md").write_text("# Same field\n\nbody")
    (event_dir / "article_same_field.html").write_text("<html>same</html>")
    (event_dir / "article_broader_field.md").write_text("# Broader\n\nbody")
    (event_dir / "article_broader_field.html").write_text("<html>broader</html>")
    (event_dir / "article_general_stem.md").write_text("# General\n\nbody")
    (event_dir / "article_general_stem.html").write_text("<html>general</html>")
    # Extra files that should ONLY appear in the full zip:
    (event_dir / "briefing_A.md").write_text("# Briefing A\n\nlong text")
    (event_dir / "intro_A.md").write_text("# Intro A\n\nbody")
    (event_dir / "needs_summary.json").write_text(json.dumps({}))


def test_glob_highlights_picks_curated_set(tmp_path: Path):
    event_dir = tmp_path / "test_slug"
    _seed_event(event_dir)
    highlights = po._glob_highlights(event_dir)
    names = sorted(p.name for p in highlights)
    # The curated set: transcript + audience + manifest + usage + inputs + 3 .md + 3 .html
    assert "transcript.md" in names
    assert "audience.log" in names
    assert "manifest.json" in names
    assert "usage.json" in names
    assert "inputs.json" in names
    assert "article_same_field.md" in names
    assert "article_same_field.html" in names
    assert "article_broader_field.md" in names
    assert "article_general_stem.html" in names
    # Briefings, intros, needs_*.json are NOT in highlights
    assert "briefing_A.md" not in names
    assert "intro_A.md" not in names
    assert "needs_summary.json" not in names


def test_glob_full_includes_everything_except_zips(tmp_path: Path):
    event_dir = tmp_path / "test_slug"
    _seed_event(event_dir)
    # Pre-create a zip — it should NOT be included
    (event_dir / "test_slug_highlights.zip").write_bytes(b"PK\x03\x04")
    full = po._glob_full(event_dir)
    names = sorted(p.name for p in full)
    assert "briefing_A.md" in names
    assert "intro_A.md" in names
    assert "transcript.md" in names
    # Zip itself is excluded
    assert "test_slug_highlights.zip" not in names


def test_main_creates_two_zips_in_event_dir(tmp_path: Path):
    event_dir = tmp_path / "pearl_elowitz_2026-05-26_abc123"
    _seed_event(event_dir)
    result = po.main(event_dir=str(event_dir))
    highlights = Path(result["highlights_zip"])
    full = Path(result["full_zip"])
    assert highlights.exists()
    assert full.exists()
    assert highlights.parent == event_dir
    # Verify highlights zip contains only the curated files
    with zipfile.ZipFile(highlights) as zf:
        members = sorted(zf.namelist())
    assert any(m.endswith("transcript.md") for m in members)
    assert any(m.endswith("article_same_field.md") for m in members)
    assert any(m.endswith("article_same_field.html") for m in members)
    assert not any("briefing_A.md" in m for m in members)
    # Verify full zip contains everything (incl. briefings)
    with zipfile.ZipFile(full) as zf:
        full_members = sorted(zf.namelist())
    assert any("briefing_A.md" in m for m in full_members)
    assert any("transcript.md" in m for m in full_members)
    # Neither zip contains itself
    assert not any(m.endswith(".zip") for m in full_members)


def test_main_raises_on_missing_event_dir(tmp_path: Path):
    import pytest

    with pytest.raises(FileNotFoundError):
        po.main(event_dir=str(tmp_path / "nope"))
