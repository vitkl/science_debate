"""Tests for debate/scripts/compose_transcript.py — Phase C0c transcript seed."""

from __future__ import annotations

import json
from pathlib import Path

import compose_transcript as ct
import pytest


def _seed_inputs(event_dir: Path) -> None:
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "inputs.json").write_text(
        json.dumps(
            {
                "topic": "Is causation a primitive or a derived concept?",
                "scientists": {
                    "A": {"name": "Judea Pearl"},
                    "B": {"name": "Donald Rubin"},
                    "C": {"name": "Andrew Gelman"},
                },
            }
        )
    )
    (event_dir / "team.json").write_text(
        json.dumps(
            {
                "team_name": event_dir.name,
                "A": {"name": "Pearl", "scientist_name": "Judea Pearl", "briefing_path": ""},
                "B": {"name": "Rubin", "scientist_name": "Donald Rubin", "briefing_path": ""},
                "C": {"name": "Gelman", "scientist_name": "Andrew Gelman", "briefing_path": ""},
            }
        )
    )
    (event_dir / "intro_A.md").write_text("# Pearl intro\n\nI am Judea Pearl, and I work on causality.")
    (event_dir / "intro_B.md").write_text(
        "# Rubin intro\n\nI'm Donald Rubin. Potential outcomes is the right framework."
    )
    (event_dir / "intro_C.md").write_text("# Gelman intro\n\nI'm Andrew Gelman. I'll review.")


def test_seeds_transcript_with_all_required_sections(tmp_path: Path) -> None:
    event_dir = tmp_path / "pearl_rubin_2026-01-01_abc123"
    _seed_inputs(event_dir)

    result = ct.main(event_dir=str(event_dir))

    assert result["status"] == "seeded"
    transcript = (event_dir / "transcript.md").read_text()

    # H1 is the topic.
    assert transcript.startswith("# Is causation a primitive or a derived concept?\n")

    # Self-introductions section with one ### per surname + role label.
    assert "## Self-introductions" in transcript
    assert "### Pearl (Presenter A)" in transcript
    assert "### Rubin (Presenter B)" in transcript
    assert "### Gelman (Reviewer)" in transcript

    # Intro bodies present verbatim.
    assert "I am Judea Pearl, and I work on causality." in transcript
    assert "I'm Donald Rubin." in transcript
    assert "I'm Andrew Gelman." in transcript

    # Moderator welcome line + empty The debate placeholder.
    assert "Moderator:" in transcript
    assert "## The debate" in transcript


def test_initialises_empty_audience_log(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt_001"
    _seed_inputs(event_dir)

    result = ct.main(event_dir=str(event_dir))

    audience_log = Path(result["audience_log"])
    assert audience_log.exists()
    assert audience_log.read_text() == ""


def test_skip_if_exists_default(tmp_path: Path) -> None:
    """Default behaviour: existing transcript.md is preserved (skip-if-exists)."""
    event_dir = tmp_path / "evt_002"
    _seed_inputs(event_dir)
    (event_dir / "transcript.md").write_text("# Pre-existing content\nhand-edited.")

    result = ct.main(event_dir=str(event_dir))

    assert result["status"] == "skipped-exists"
    assert (event_dir / "transcript.md").read_text() == "# Pre-existing content\nhand-edited."


def test_skip_creates_missing_audience_log(tmp_path: Path) -> None:
    """Skip path still creates audience.log if it's absent — downstream readers
    must never face a missing file."""
    event_dir = tmp_path / "evt_003"
    _seed_inputs(event_dir)
    (event_dir / "transcript.md").write_text("# existing")

    ct.main(event_dir=str(event_dir))

    assert (event_dir / "audience.log").exists()
    assert (event_dir / "audience.log").read_text() == ""


def test_force_clobbers_existing(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt_004"
    _seed_inputs(event_dir)
    (event_dir / "transcript.md").write_text("# old content")

    result = ct.main(event_dir=str(event_dir), force=True)

    assert result["status"] == "seeded"
    transcript = (event_dir / "transcript.md").read_text()
    assert "# Is causation a primitive or a derived concept?" in transcript
    assert "# old content" not in transcript


def test_raises_on_missing_intro(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt_005"
    _seed_inputs(event_dir)
    (event_dir / "intro_B.md").unlink()  # remove one intro

    with pytest.raises(FileNotFoundError, match="intro_B.md"):
        ct.main(event_dir=str(event_dir))


def test_raises_on_missing_team_slot(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt_006"
    _seed_inputs(event_dir)
    # Drop slot C from team.json.
    team = json.loads((event_dir / "team.json").read_text())
    del team["C"]
    (event_dir / "team.json").write_text(json.dumps(team))

    with pytest.raises(RuntimeError, match="team.json missing slot C"):
        ct.main(event_dir=str(event_dir))


def test_raises_on_nonexistent_event_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not a directory"):
        ct.main(event_dir=str(tmp_path / "does-not-exist"))


def test_default_topic_when_inputs_topic_missing(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt_007"
    _seed_inputs(event_dir)
    # Strip topic from inputs.json.
    inputs = json.loads((event_dir / "inputs.json").read_text())
    del inputs["topic"]
    (event_dir / "inputs.json").write_text(json.dumps(inputs))

    ct.main(event_dir=str(event_dir))

    transcript = (event_dir / "transcript.md").read_text()
    assert transcript.startswith("# Untitled debate\n")
