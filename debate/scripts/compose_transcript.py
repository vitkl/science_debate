#!/usr/bin/env python3
"""Seed ``transcript.md`` and ``audience.log`` at Phase C0c (run-debate skill).

Builds the initial structure of ``transcript.md`` that ``compose_full_event.py``
later expects, so the live transcript is consistent from the first per-stage
concatenation in C1. Also initialises ``audience.log`` as an empty file so
downstream readers never face a missing-file edge case.

The script reads ``inputs.json`` (topic, scientists), ``team.json`` (slot →
surname mapping written by Phase B5_pre), and the three ``intro_<X>.md`` files
(written by each scientist during B5a self-iteration). It emits:

  - H1 ``# <topic>``
  - ``## Self-introductions`` with three ``### <surname> (Presenter A|B|Reviewer)``
    subsections, body verbatim from each ``intro_<X>.md``.
  - A Moderator welcome line.
  - An empty ``## The debate`` heading (Phase C1 concatenates per-stage files
    underneath this).

Defaults to skip-if-exists; pass ``--force`` to clobber.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fire
from _common import atomic_write_text

ROLE_LABEL = {"A": "Presenter A", "B": "Presenter B", "C": "Reviewer"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_intro(event_dir: Path, slot: str) -> str:
    intro_path = event_dir / f"intro_{slot}.md"
    if not intro_path.exists():
        raise FileNotFoundError(f"Missing {intro_path} — B5a should have produced it. Run B5a self-intros before C0c.")
    return intro_path.read_text(encoding="utf-8").rstrip() + "\n"


def main(
    *,
    event_dir: str,
    force: bool = False,
) -> dict[str, str]:
    """Seed ``transcript.md`` and ``audience.log`` for the named event folder."""
    event_path = Path(event_dir).resolve()
    if not event_path.is_dir():
        raise FileNotFoundError(f"event_dir not a directory: {event_path}")

    transcript_path = event_path / "transcript.md"
    audience_path = event_path / "audience.log"

    if transcript_path.exists() and not force:
        print(
            f"transcript.md exists at {transcript_path} — skipping seed (pass --force to recreate).",
            file=sys.stderr,
        )
        # Still ensure audience.log exists (empty) so downstream is safe.
        if not audience_path.exists():
            atomic_write_text(audience_path, "")
        return {
            "transcript_md": str(transcript_path),
            "audience_log": str(audience_path),
            "status": "skipped-exists",
        }

    inputs = _load_json(event_path / "inputs.json")
    team = _load_json(event_path / "team.json")

    topic = inputs.get("topic", "Untitled debate")

    parts: list[str] = []
    parts.append(f"# {topic}\n\n")
    parts.append("## Self-introductions\n\n")

    for slot in ("A", "B", "C"):
        slot_entry = team.get(slot)
        if slot_entry is None:
            raise RuntimeError(f"team.json missing slot {slot}. B5_pre should have written all three.")
        surname = slot_entry["name"]
        role_label = ROLE_LABEL[slot]
        intro_body = _read_intro(event_path, slot)
        parts.append(f"### {surname} ({role_label})\n\n")
        parts.append(intro_body)
        if not intro_body.endswith("\n\n"):
            parts.append("\n")

    moderator_welcome = (
        "Moderator: Welcome. The three speakers above have introduced themselves; "
        "the debate proper begins with the prepared opening talks."
    )
    parts.append(moderator_welcome + "\n\n")
    parts.append("## The debate\n\n")

    atomic_write_text(transcript_path, "".join(parts))
    if not audience_path.exists():
        atomic_write_text(audience_path, "")

    result = {
        "transcript_md": str(transcript_path),
        "audience_log": str(audience_path),
        "status": "seeded",
    }
    print(result)
    return result


if __name__ == "__main__":
    fire.Fire(main)
