#!/usr/bin/env python3
"""Persist a structured search-keyword set for a debate topic.

The Moderator does the keyword generation in-context (it knows the field
better than a deterministic Python script can) and passes the result
in via CLI flags. This script just structures + writes the JSON so the
debate-event folder has a single source of truth for what was searched.
"""

from __future__ import annotations

from pathlib import Path

import fire
from _common import atomic_write_json


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [term.strip() for term in value.split(",") if term.strip()]


def main(
    topic: str,
    out: str,
    *,
    primary: str = "",
    synonyms: str = "",
    opposing: str = "",
    publication_types: str = "editorial,letter,commentary,opinion,review,news",
) -> Path:
    """Write ``keywords.json`` describing the search strategy for this debate."""
    payload = {
        "topic": topic,
        "primary_terms": _split_csv(primary),
        "synonyms": _split_csv(synonyms),
        "opposing_terms": _split_csv(opposing),
        "publication_types": _split_csv(publication_types),
    }
    out_path = Path(out)
    atomic_write_json(out_path, payload)
    print(str(out_path))
    return out_path


if __name__ == "__main__":
    fire.Fire(main)
