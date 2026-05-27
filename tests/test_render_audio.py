"""Tests for debate/scripts/render_audio.py — Kokoro TTS pipeline.

Unit-tests the pure-Python parser / slicer / preamble helpers. Does NOT exercise
Kokoro / soundfile / pydub end-to-end (those require ~330 MB of model weights
and an ffmpeg binary, which we don't pin in CI). The lazy-import design lets
us test most of the script without those optional deps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import render_audio as ra

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def team_dict() -> dict:
    """A canonical 4-slot team.json structure (A/B/C/J)."""
    return {
        "team_name": "evt_001",
        "A": {"name": "Pearl", "scientist_name": "Judea Pearl"},
        "B": {"name": "Rubin", "scientist_name": "Donald Rubin"},
        "C": {"name": "Gelman", "scientist_name": "Andrew Gelman"},
        "J": {"name": "Journalist", "scientist_name": None},
    }


@pytest.fixture
def voice_map_dict() -> dict:
    return {
        "A": "af_bella",
        "B": "am_adam",
        "C": "bm_george",
        "Moderator": "am_michael",
        "Audience": "bf_emma",
        "Journalist": "af_sarah",
    }


# ---------------------------------------------------------------------------
# _slot_to_speaker_key
# ---------------------------------------------------------------------------


def test_slot_to_speaker_key_maps_surnames_to_slot_letters(team_dict: dict) -> None:
    assert ra._slot_to_speaker_key(team_dict, "Pearl") == "A"
    assert ra._slot_to_speaker_key(team_dict, "Rubin") == "B"
    assert ra._slot_to_speaker_key(team_dict, "Gelman") == "C"


def test_slot_to_speaker_key_passes_through_fixed_roles(team_dict: dict) -> None:
    assert ra._slot_to_speaker_key(team_dict, "Moderator") == "Moderator"
    assert ra._slot_to_speaker_key(team_dict, "Journalist") == "Journalist"
    assert ra._slot_to_speaker_key(team_dict, "Audience") == "Audience"


def test_slot_to_speaker_key_returns_none_for_unknown(team_dict: dict) -> None:
    assert ra._slot_to_speaker_key(team_dict, "Heckman") is None


# ---------------------------------------------------------------------------
# _voice_for
# ---------------------------------------------------------------------------


def test_voice_for_returns_mapped_voice(voice_map_dict: dict) -> None:
    assert ra._voice_for("A", voice_map_dict) == "af_bella"
    assert ra._voice_for("Audience", voice_map_dict) == "bf_emma"


def test_voice_for_raises_on_missing_key(voice_map_dict: dict) -> None:
    with pytest.raises(KeyError, match="missing entry for speaker key 'Z'"):
        ra._voice_for("Z", voice_map_dict)


# ---------------------------------------------------------------------------
# _parse_utterances — speaker attribution
# ---------------------------------------------------------------------------


def _parse(text: str, team: dict) -> list[ra.Utterance]:
    """Convenience: parse + return list of (speaker, text) tuples."""
    return ra._parse_utterances(text, team)


def test_parse_main_stage_speaker_prefix(team_dict: dict) -> None:
    text = "## Stage 1 — Opening presentation A (Pearl)\nPearl: I argue causality is primitive.\n"
    utts = _parse(text, team_dict)
    assert len(utts) == 1
    assert utts[0].speaker == "A"
    assert utts[0].text == "I argue causality is primitive."


def test_parse_audience_block(team_dict: dict) -> None:
    text = "**Audience:** Could you define 'causal effect'?\n"
    utts = _parse(text, team_dict)
    assert len(utts) == 1
    assert utts[0].speaker == "Audience"
    assert utts[0].text == "Could you define 'causal effect'?"


def test_parse_clarifying_block(team_dict: dict) -> None:
    text = "**Rubin → Pearl (clarifying):** What about confounders?\n"
    utts = _parse(text, team_dict)
    assert len(utts) == 1
    # Asker (Rubin → slot B) voices the question.
    assert utts[0].speaker == "B"
    assert "What about confounders?" in utts[0].text


def test_parse_responding_to_clarification(team_dict: dict) -> None:
    """Regression test for the SPEAKER_RESPONSE bug surfaced in verify-implementation:
    `Pearl (responding to Rubin): ...` must be voiced by Pearl, NOT by the prior
    `current_speaker` (which would be Rubin / Audience after a preceding block)."""
    text = (
        "**Rubin → Pearl (clarifying):** What about confounders?\n"
        "Pearl (responding to Rubin): That's exactly what do-calculus handles.\n"
    )
    utts = _parse(text, team_dict)
    assert len(utts) == 2
    # First utterance: Rubin asking (slot B).
    assert utts[0].speaker == "B"
    # Second utterance: Pearl responding (slot A) — NOT Rubin, NOT Audience.
    assert utts[1].speaker == "A"
    assert utts[1].text == "That's exactly what do-calculus handles."


def test_parse_responding_to_audience(team_dict: dict) -> None:
    """Audience-response line: `Pearl (responding to audience): ...` must be
    voiced by Pearl. Most subtle bug: after `**Audience:**` block, naive parse
    would attribute the response to Audience."""
    text = (
        "**Audience:** Define causal effect.\n"
        "Pearl (responding to audience): It's a do-operator query.\n"
        "Rubin (responding to audience): It's a potential-outcomes contrast.\n"
    )
    utts = _parse(text, team_dict)
    assert len(utts) == 3
    assert utts[0].speaker == "Audience"
    assert utts[1].speaker == "A"  # Pearl
    assert utts[1].text == "It's a do-operator query."
    assert utts[2].speaker == "B"  # Rubin
    assert utts[2].text == "It's a potential-outcomes contrast."


def test_parse_drops_headings_but_tracks_section_speaker(team_dict: dict) -> None:
    """### <Surname> (Presenter A) sets current_speaker for the next plain
    paragraph (so intro bodies don't need a `<Surname>:` prefix)."""
    text = "### Pearl (Presenter A)\nI am Judea Pearl, and I work on causality.\n"
    utts = _parse(text, team_dict)
    assert len(utts) == 1
    assert utts[0].speaker == "A"  # Pearl's section
    assert "Judea Pearl" in utts[0].text


def test_parse_handles_surname_with_internal_space(team_dict: dict) -> None:
    """A surname containing a space (e.g. 'Martinez Arias') is one identifier,
    not two — verify the regex tolerates internal whitespace."""
    team_with_space = {
        **team_dict,
        "A": {"name": "Martinez Arias", "scientist_name": "Alfonso Martinez Arias"},
    }
    text = "Martinez Arias: Self-organisation is the right framing.\n"
    utts = _parse(text, team_with_space)
    assert len(utts) == 1
    assert utts[0].speaker == "A"


def test_parse_unknown_surname_voices_body_under_current_speaker(team_dict: dict) -> None:
    """When a SPEAKER_PREFIX matches but the surname isn't in team.json, the
    body is voiced under current_speaker without the prefix (instead of being
    attributed silently or kept literally). Verifies the fix to the silent-drop
    bug surfaced in verify-implementation."""
    text = (
        "### Pearl (Presenter A)\n"
        "Pearl: First my view.\n"
        "Heckman: Selection bias dominates.\n"  # Heckman not in team.json
    )
    utts = _parse(text, team_dict)
    # Pearl's two text blocks should both be attributed to A.
    # Heckman: line falls through; body (without prefix) is buffered under current_speaker (A).
    assert all(u.speaker == "A" for u in utts), [u.speaker for u in utts]


def test_parse_treats_blank_lines_as_paragraph_breaks(team_dict: dict) -> None:
    """Blank line between two `Pearl:` lines → two separate utterances."""
    text = "Pearl: First sentence.\n\nPearl: Second sentence.\n"
    utts = _parse(text, team_dict)
    assert len(utts) == 2


# ---------------------------------------------------------------------------
# STAGE_HEADING regex
# ---------------------------------------------------------------------------


def test_stage_heading_matches_em_dash() -> None:
    assert ra.STAGE_HEADING.match("## Stage 1 — title") is not None


def test_stage_heading_matches_en_dash() -> None:
    assert ra.STAGE_HEADING.match("## Stage 1 – title") is not None


def test_stage_heading_matches_plain_hyphen() -> None:
    """Regression test: original regex required em-dash only, breaking on
    agents/compose scripts that emit plain hyphens."""
    assert ra.STAGE_HEADING.match("## Stage 1 - title") is not None


def test_stage_heading_extracts_substage_label() -> None:
    m = ra.STAGE_HEADING.match("### Stage 8a — Final rejoinder A")
    assert m is not None
    assert m.group(1) == "8a"
    m = ra.STAGE_HEADING.match("### Stage 10b — Final rejoinder B")
    assert m is not None
    assert m.group(1) == "10b"


# ---------------------------------------------------------------------------
# _segment_slice
# ---------------------------------------------------------------------------


def _multi_stage_transcript() -> str:
    """Synthesise a transcript with stages 1, 2, 3, 4, 5, 6, 7, 8a, 8b."""
    parts = []
    for stage in ["1", "2", "3", "4", "5", "6", "7", "8a", "8b"]:
        parts.append(f"## Stage {stage} — title-for-{stage}\n")
        parts.append(f"Pearl: Stage {stage} body line.\n\n")
    return "".join(parts)


def test_segment_slice_for_break_after_1() -> None:
    sliced = ra._segment_slice(_multi_stage_transcript(), 1)
    assert "Stage 1" in sliced
    assert "Stage 2" not in sliced


def test_segment_slice_for_break_after_2_excludes_stage_1() -> None:
    """Segment 2 covers only stage 2 (stage 1 is owned by the prior segment)."""
    sliced = ra._segment_slice(_multi_stage_transcript(), 2)
    assert "Stage 2" in sliced
    assert "Stage 1" not in sliced
    assert "Stage 3" not in sliced


def test_segment_slice_for_break_after_4_includes_stage_3_and_4() -> None:
    """Stages 3 has no break, so segment 4 covers stages 3 and 4."""
    sliced = ra._segment_slice(_multi_stage_transcript(), 4)
    assert "Stage 3" in sliced
    assert "Stage 4" in sliced
    assert "Stage 2" not in sliced
    assert "Stage 5" not in sliced


def test_segment_slice_for_break_after_8_includes_8a_and_8b() -> None:
    """Dual sub-stages 8a + 8b belong to segment 8."""
    sliced = ra._segment_slice(_multi_stage_transcript(), 8)
    assert "Stage 8a" in sliced
    assert "Stage 8b" in sliced
    assert "Stage 7" not in sliced  # owned by segment 7


def test_segment_slice_rejects_non_break_point() -> None:
    with pytest.raises(ValueError, match="not a break-point"):
        ra._segment_slice(_multi_stage_transcript(), 3)
    with pytest.raises(ValueError, match="not a break-point"):
        ra._segment_slice(_multi_stage_transcript(), 5)


# ---------------------------------------------------------------------------
# _strip_skip_blocks
# ---------------------------------------------------------------------------


def test_strip_skip_blocks_removes_contents() -> None:
    md = "# Title\n\n## Contents\n\n- [a](#a)\n- [b](#b)\n\n## Self-introductions\n\nbody\n"
    out = ra._strip_skip_blocks(md)
    assert "## Contents" not in out
    assert "## Self-introductions" in out
    assert "body" in out


def test_strip_skip_blocks_removes_format_table() -> None:
    md = (
        "# Title\n\n"
        "Some narrative.\n\n"
        "| # | Stage | Speaker | Words | Audience can ask questions (asked) |\n"
        "|---|---|---|---|---|\n"
        "| 1 | Talk A | Pearl | 1500 | yes (0) |\n"
        "| 2 | Talk B | Rubin | 1500 | yes (0) |\n"
        "\n"
        "## Next section\n\n"
        "body\n"
    )
    out = ra._strip_skip_blocks(md)
    assert "| # | Stage |" not in out
    assert "| 1 | Talk A" not in out
    assert "## Next section" in out


# ---------------------------------------------------------------------------
# _load_team / _load_voice_map error messages
# ---------------------------------------------------------------------------


def test_load_team_raises_actionable_error_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="B5_pre should have written it"):
        ra._load_team(tmp_path)


def test_load_voice_map_raises_actionable_error_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Batch 4.5 voice picker should have written it"):
        ra._load_voice_map(tmp_path)


def test_load_team_round_trip(tmp_path: Path, team_dict: dict) -> None:
    (tmp_path / "team.json").write_text(json.dumps(team_dict))
    assert ra._load_team(tmp_path) == team_dict


def test_load_voice_map_round_trip(tmp_path: Path, voice_map_dict: dict) -> None:
    (tmp_path / "voice_map.json").write_text(json.dumps(voice_map_dict))
    assert ra._load_voice_map(tmp_path) == voice_map_dict


# ---------------------------------------------------------------------------
# Preamble helpers
# ---------------------------------------------------------------------------


def test_methodology_text_substitutes_placeholders(tmp_path: Path, team_dict: dict) -> None:
    inputs = {"debate": {"total_minutes": 60}, "topic": "Whether causation is primitive"}
    text = ra._methodology_text(tmp_path, inputs, team_dict)
    assert "60 minutes" in text
    assert "Whether causation is primitive" in text
    assert "Pearl" in text
    assert "Rubin" in text
    assert "Gelman" in text


def test_methodology_text_defaults_when_inputs_missing_fields(tmp_path: Path, team_dict: dict) -> None:
    text = ra._methodology_text(tmp_path, {}, team_dict)
    # str.format_map with no default would raise KeyError on missing placeholders;
    # we use a fallback approach (.get(...)) so missing keys substitute defaults.
    assert "80 minutes" in text  # default total_minutes
    assert "the debate topic" in text  # default topic


def test_disclaimer_text_non_empty() -> None:
    text = ra._disclaimer_text()
    assert "Disclaimer" in text
    assert "AI" in text or "ai" in text.lower()
    # Roughly bounded — should be the ~30s spoken intro, not a whole essay.
    assert 30 < len(text.split()) < 120


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


def test_main_rejects_f5tts_backend() -> None:
    with pytest.raises(NotImplementedError, match="Phase 2"):
        ra.main(backend="f5tts")


def test_main_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        ra.main(backend="garbage-engine")
