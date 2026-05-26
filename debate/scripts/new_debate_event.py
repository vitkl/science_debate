#!/usr/bin/env python3
"""Create a new debate-event folder with a skeleton inputs.json.

Folder naming: ``debate_events/<A-last>_<B-last>_<YYYY-MM-DD>_<6char-hash>/``
The 6-character hash is taken from ``CLAUDE_SESSION_ID`` if set, otherwise
generated with ``secrets.token_hex(3)`` so each run is traceable.
"""

from __future__ import annotations

import datetime as _dt
import os
import secrets
from pathlib import Path

import fire
from _common import DEBATE_EVENTS, atomic_write_json, slug


def _hash() -> str:
    session_id = os.environ.get("CLAUDE_SESSION_ID", "").strip()
    if session_id:
        # take the first 6 hex-safe characters from the session id
        cleaned = "".join(c for c in session_id.lower() if c in "0123456789abcdef")[:6]
        if len(cleaned) == 6:
            return cleaned
    return secrets.token_hex(3)


def _last_name(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    return slug(parts[-1]) if parts else "unknown"


def main(
    scientist_a: str,
    scientist_b: str,
    scientist_c: str,
    topic: str,
    *,
    date: str | None = None,
) -> Path:
    """Create the event folder + ``inputs.json`` skeleton; print the resulting path."""
    date_str = date or _dt.date.today().isoformat()
    folder_name = f"{_last_name(scientist_a)}_{_last_name(scientist_b)}_{date_str}_{_hash()}"
    event_dir = DEBATE_EVENTS / folder_name
    event_dir.mkdir(parents=True, exist_ok=True)

    skeleton = {
        "event_slug": folder_name,
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "topic": topic,
        "scientists": {
            "A": {"name": scientist_a, "role": "presenter+opponent"},
            "B": {"name": scientist_b, "role": "presenter+opponent"},
            "C": {"name": scientist_c, "role": "reviewer"},
        },
        "debate": {
            "total_minutes": 80,
            "give_collaborative_tone_to_presenters": False,
            "journalist_word_budget": 550,
            "allow_websearch_during_debate": False,
        },
        "ingestion": {
            "n_full_papers_cap": 25,
            "n_abstracts_cap": 500,
            "global_briefing_word_cap": 80_000,
            "per_scientist_instruction": {scientist_a: "", scientist_b: "", scientist_c: ""},
            "pre_fetch_urls": {scientist_a: [], scientist_b: [], scientist_c: []},
            "custom_sources": {scientist_a: [], scientist_b: [], scientist_c: []},
        },
        "models": {"A": "opus", "B": "opus", "C": "opus", "J": "opus"},
    }
    atomic_write_json(event_dir / "inputs.json", skeleton)
    print(str(event_dir))
    return event_dir


if __name__ == "__main__":
    fire.Fire(main)
