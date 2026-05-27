"""Tests for debate/scripts/compose_full_event.py — end-of-debate stitched markdown."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import compose_full_event as cfe
import pytest


def _seed_full_event(event_dir: Path, *, with_articles: bool = True, with_audience: bool = True) -> None:
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "inputs.json").write_text(
        json.dumps(
            {
                "topic": "Is causation primitive?",
                "debate": {"total_minutes": 80},
                "scientists": {
                    "A": {"name": "Judea Pearl", "title": "Prof", "affiliation": "UCLA"},
                    "B": {"name": "Donald Rubin", "title": "Prof", "affiliation": "Harvard"},
                    "C": {"name": "Andrew Gelman", "title": "Prof", "affiliation": "Columbia"},
                },
            }
        )
    )
    (event_dir / "team.json").write_text(
        json.dumps(
            {
                "team_name": event_dir.name,
                "A": {"name": "Pearl", "scientist_name": "Judea Pearl"},
                "B": {"name": "Rubin", "scientist_name": "Donald Rubin"},
                "C": {"name": "Gelman", "scientist_name": "Andrew Gelman"},
            }
        )
    )
    (event_dir / "intro_A.md").write_text("Pearl intro body.")
    (event_dir / "intro_B.md").write_text("Rubin intro body.")
    (event_dir / "intro_C.md").write_text("Gelman intro body.")

    # transcript.md after C0c seeding + stage concatenation. Mirrors the format
    # described in run-debate/SKILL.md C1 step 3.4.
    transcript = (
        "# Is causation primitive?\n\n"
        "## Self-introductions\n\n"
        "### Pearl (Presenter A)\nPearl intro body.\n\n"
        "### Rubin (Presenter B)\nRubin intro body.\n\n"
        "### Gelman (Reviewer)\nGelman intro body.\n\n"
        "Moderator: Welcome.\n\n"
        "## The debate\n\n"
        "## Stage 1 — Opening presentation A (Pearl)\nPearl: My talk.\n\n"
        "**Rubin → Pearl (clarifying):** What about confounders?\n\n"
        "Pearl (responding to Rubin): That's what do-calculus handles.\n\n"
        "## Stage 2 — Opening presentation B (Rubin)\nRubin: My talk.\n\n"
        "**Audience:** Could you both define 'causal effect'?\n\n"
        "Pearl (responding to audience): It's a do-operator query.\n\n"
        "Rubin (responding to audience): It's a potential-outcomes contrast.\n\n"
    )
    (event_dir / "transcript.md").write_text(transcript)

    audience_lines: list[str] = []
    if with_audience:
        audience_lines = [
            json.dumps(
                {
                    "after_stage": 2,
                    "text": "Could you both define 'causal effect'?",
                    "forwarded_to": ["A", "B"],
                    "timestamp_iso": "2026-01-01T12:00:00Z",
                }
            ),
        ]
    (event_dir / "audience.log").write_text("\n".join(audience_lines) + ("\n" if audience_lines else ""))

    if with_articles:
        (event_dir / "article_same_field.md").write_text("# Same field\nThe debate centred on...")
        (event_dir / "article_broader_field.md").write_text("# Broader field\nIn related fields...")
        (event_dir / "article_general_stem.md").write_text("# General STEM\nFor a general audience...")


def test_emits_full_debate_md_with_all_top_level_sections(tmp_path: Path) -> None:
    event_dir = tmp_path / "pearl_rubin_2026-01-01_abc123"
    _seed_full_event(event_dir)

    result = cfe.main(event_dir=str(event_dir))

    full_md = (event_dir / "full_debate.md").read_text()
    # H1 title (auto-derived from surnames, alphabetical).
    assert full_md.startswith("# Pearl vs. Rubin — Full debate\n")
    # Topic line.
    assert "**Topic:** Is causation primitive?" in full_md
    # Cast line uses real names + title + affiliation.
    assert "**Cast:**" in full_md
    assert "Judea Pearl (Prof, UCLA)" in full_md
    assert "Donald Rubin (Prof, Harvard)" in full_md
    assert "Andrew Gelman (Prof, Columbia)" in full_md
    # Format table, Contents/TOC, Self-introductions, The debate, Journalist's write-up.
    assert "| # | Stage | Speaker | Words (target) | Audience can ask questions (asked) |" in full_md
    assert "## Contents" in full_md
    assert "## Self-introductions" in full_md
    assert "## The debate" in full_md
    assert "## Journalist's write-up" in full_md
    # Result metadata.
    assert int(result["word_count"]) > 0
    assert result["audience_interjections_total"] == "1"


def test_format_table_uses_real_names_not_slot_letters(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    cfe.main(event_dir=str(event_dir))

    full_md = (event_dir / "full_debate.md").read_text()
    # Find the Format-table block.
    rows = [l for l in full_md.splitlines() if l.startswith("| ") and "|" in l[2:]]
    # Stage 1 row should name Pearl (surname), not "A".
    stage_1_row = [r for r in rows if r.startswith("| 1 |") and "Opening" in r][0]
    assert "Pearl" in stage_1_row
    # The character " A " (slot letter) surrounded by spaces should not appear
    # in a speaker cell — only in role descriptions like "Opening A" / "rejoinder A".
    speaker_cell = stage_1_row.split("|")[3]
    assert re.search(r"\bA\b", speaker_cell) is None, f"slot letter leaked into speaker cell: {speaker_cell!r}"


def test_format_table_renders_dual_substages_8a_8b_10a_10b(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    cfe.main(event_dir=str(event_dir))

    full_md = (event_dir / "full_debate.md").read_text()
    # Substage rows present.
    assert "| 8a |" in full_md
    assert "| 8b |" in full_md
    assert "| 10a |" in full_md
    assert "| 10b |" in full_md
    # 8a has no audience break (—); 8b has the break.
    rows = full_md.splitlines()
    row_8a = next(r for r in rows if r.startswith("| 8a |"))
    row_8b = next(r for r in rows if r.startswith("| 8b |"))
    assert row_8a.endswith("| — |")
    assert "yes (" in row_8b


def test_format_table_audience_counts_match_log(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    # Add another interjection at stage 4.
    extra = json.dumps({"after_stage": 4, "text": "Q2", "forwarded_to": ["A"], "timestamp_iso": "2026-01-01T13:00:00Z"})
    with (event_dir / "audience.log").open("a") as f:
        f.write(extra + "\n")

    cfe.main(event_dir=str(event_dir))
    full_md = (event_dir / "full_debate.md").read_text()
    row_2 = next(r for r in full_md.splitlines() if r.startswith("| 2 |"))
    row_4 = next(r for r in full_md.splitlines() if r.startswith("| 4 |"))
    assert "yes (1)" in row_2  # one interjection after stage 2
    assert "yes (1)" in row_4  # one interjection after stage 4


def test_handles_missing_audience_log_gracefully(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir, with_audience=False)
    (event_dir / "audience.log").unlink()

    result = cfe.main(event_dir=str(event_dir))
    assert result["audience_interjections_total"] == "0"
    full_md = (event_dir / "full_debate.md").read_text()
    # All break-point rows show "yes (0)" rather than crash.
    assert "yes (0)" in full_md


def test_malformed_audience_log_lines_skipped(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir, with_audience=False)
    # Mix of valid + invalid lines.
    (event_dir / "audience.log").write_text(
        json.dumps({"after_stage": 1, "text": "Good Q", "forwarded_to": ["A"], "timestamp_iso": "t"}) + "\n"
        "this is not JSON\n"
        + json.dumps({"after_stage": 2, "text": "Another", "forwarded_to": ["B"], "timestamp_iso": "t"})
        + "\n"
        + json.dumps({"after_stage": "not-an-int", "text": "skipped", "forwarded_to": [], "timestamp_iso": "t"})
        + "\n"
    )
    cfe.main(event_dir=str(event_dir))
    full_md = (event_dir / "full_debate.md").read_text()
    row_1 = next(r for r in full_md.splitlines() if r.startswith("| 1 |"))
    row_2 = next(r for r in full_md.splitlines() if r.startswith("| 2 |"))
    assert "yes (1)" in row_1
    assert "yes (1)" in row_2


def test_audience_counts_helper(tmp_path: Path) -> None:
    """Unit-test _audience_counts directly."""
    log = tmp_path / "audience.log"
    log.write_text(
        json.dumps({"after_stage": 1, "text": "x", "forwarded_to": []})
        + "\n"
        + json.dumps({"after_stage": 1, "text": "y", "forwarded_to": []})
        + "\n"
        + json.dumps({"after_stage": 4, "text": "z", "forwarded_to": []})
        + "\n"
    )
    counts = cfe._audience_counts(log)
    assert counts == Counter({1: 2, 4: 1})

    # Empty file → empty Counter.
    log.write_text("")
    assert cfe._audience_counts(log) == Counter()


def test_missing_articles_dont_crash(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir, with_articles=False)
    cfe.main(event_dir=str(event_dir))

    full_md = (event_dir / "full_debate.md").read_text()
    # All three article placeholders rendered (graceful fallback).
    assert "*(article missing: article_same_field.md)*" in full_md
    assert "*(article missing: article_broader_field.md)*" in full_md
    assert "*(article missing: article_general_stem.md)*" in full_md


def test_stage_h2_demoted_to_h3_under_the_debate(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    cfe.main(event_dir=str(event_dir))

    full_md = (event_dir / "full_debate.md").read_text()
    # Find the index of "## The debate" — every "## Stage" inside should be demoted to "### Stage".
    debate_start = full_md.index("## The debate")
    debate_body = full_md[debate_start:]
    assert "### Stage 1" in debate_body
    assert "### Stage 2" in debate_body
    # No raw line-start `## Stage` (only `### Stage`). Use a line-anchored regex
    # — naive substring check would false-positive because `### Stage` *contains*
    # `## Stage` from offset 1.
    assert re.search(r"^## Stage ", debate_body, re.MULTILINE) is None


def test_word_target_scales_with_total_minutes(tmp_path: Path) -> None:
    """Per FORMAT.md scaling: T=160 should double Stage 1's word target."""
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    # Halve and double.
    inputs = json.loads((event_dir / "inputs.json").read_text())
    inputs["debate"]["total_minutes"] = 160
    (event_dir / "inputs.json").write_text(json.dumps(inputs))

    cfe.main(event_dir=str(event_dir))
    full_md = (event_dir / "full_debate.md").read_text()
    row_1 = next(r for r in full_md.splitlines() if r.startswith("| 1 |"))
    # 1500 * (160/80) = 3000.
    assert "| 3000 |" in row_1


def test_audience_cell_guard_on_non_digit_label() -> None:
    """_audience_cell falls open with — when label has no leading digits."""
    cell = cfe._audience_cell("qweird-label", "yes", Counter())
    assert cell == "—"


def test_toc_disambiguates_duplicate_anchors() -> None:
    """Headings with the same text get -2, -3 suffixed anchors."""
    md = "## Foo\n\n## Foo\n\n## Bar\n"
    toc = cfe._toc(md)
    assert "(#foo)" in toc
    assert "(#foo-2)" in toc
    assert "(#bar)" in toc


def test_user_supplied_title_overrides_auto_h1(tmp_path: Path) -> None:
    event_dir = tmp_path / "evt"
    _seed_full_event(event_dir)
    inputs = json.loads((event_dir / "inputs.json").read_text())
    inputs["title"] = "The Pearl-Rubin Causality Showdown"
    (event_dir / "inputs.json").write_text(json.dumps(inputs))

    cfe.main(event_dir=str(event_dir))
    full_md = (event_dir / "full_debate.md").read_text()
    assert full_md.startswith("# The Pearl-Rubin Causality Showdown\n")


def test_raises_on_nonexistent_event_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not a directory"):
        cfe.main(event_dir=str(tmp_path / "does-not-exist"))
