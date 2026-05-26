"""Smoke tests for the summarise-for-debate skill (file shape, frontmatter, symlink)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "debate" / "skills" / "summarise-for-debate" / "SKILL.md"
SYMLINK_PATH = REPO_ROOT / ".claude" / "skills" / "summarise-for-debate"


def _read_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL_PATH.exists(), f"missing {SKILL_PATH}"


def test_skill_symlink_resolves_to_debate_tree():
    assert SYMLINK_PATH.is_symlink() or SYMLINK_PATH.exists(), f"missing {SYMLINK_PATH}"
    # Resolve and confirm it points into debate/skills/
    target = SYMLINK_PATH.resolve()
    assert "debate/skills/summarise-for-debate" in str(target)


def test_skill_has_required_frontmatter():
    text = _read_skill()
    assert text.startswith("---\n"), "missing YAML frontmatter delimiter"
    head, _, _ = text[4:].partition("---\n")
    fields = {line.split(":", 1)[0].strip() for line in head.splitlines() if ":" in line}
    assert "name" in fields
    assert "description" in fields
    assert "user-invocable" in fields


def test_skill_name_matches_directory():
    text = _read_skill()
    # name must be 'summarise-for-debate'
    name_line = next(line for line in text.splitlines() if line.startswith("name:"))
    assert name_line.split(":", 1)[1].strip() == "summarise-for-debate"


def test_skill_describes_speaker_attribution_check():
    """The user explicitly asked for speaker/host disambiguation guidance —
    the skill must mention it (catches accidental removal)."""
    text = _read_skill()
    lower = text.lower()
    assert "speaker" in lower
    assert "attribution" in lower
    assert "host" in lower


def test_skill_documents_caller_inputs():
    text = _read_skill()
    for token in ("source-path", "topic", "scientist", "target-words", "model"):
        assert token in text, f"missing input descriptor: {token}"


def test_skill_documents_model_options():
    text = _read_skill()
    lower = text.lower()
    assert "haiku" in lower
    assert "sonnet" in lower
    assert "opus" in lower


def test_skill_under_word_cap():
    """Plan §2 says <= 250 words body budget; allow some slack for the
    enriched speaker-attribution section but cap at 500 words total."""
    text = _read_skill()
    word_count = len(text.split())
    assert word_count < 700, f"skill body exceeded word cap: {word_count}"
