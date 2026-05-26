"""Shared Haiku-4.5 classifier for borderline search-result candidates.

Used by ``search_youtube.py``, ``search_blogs.py``, and ``search_books.py``
to drop candidates that pass cheap heuristics but are unlikely to be
relevant scientific work by/about the named scientist on the debate topic.

Papers (search_works.py) deliberately do NOT use this — OpenAlex
author IDs + tier filtering already give high precision there.

Failure modes are *permissive*: if the LLM call or SDK is missing /
errors out, we KEEP the candidate (don't silently delete data); the
reason field captures why. Verdicts are cached per cache_key.
"""

from __future__ import annotations

import os
from typing import Any

MODEL_ID = "claude-haiku-4-5-20251001"


def classify_candidate(
    *,
    cache_key: str,
    scientist: str,
    primary_terms: list[str],
    kind: str,
    item_fields: dict[str, str],
    question_template: str,
    cache: dict[str, dict],
    max_tokens: int = 120,
) -> tuple[bool, str]:
    """Return (keep, reason) for one candidate.

    Parameters
    ----------
    cache_key : stable per-item key (video_id, url, isbn, etc.).
    scientist : the named scientist the search targets.
    primary_terms : debate topic keywords (joined into the prompt as ``{topic}``).
    kind : short label for logging (``youtube_video``, ``blog_post``, ``book``).
    item_fields : ordered dict of ``Label: value`` rendered into the prompt.
    question_template : may include ``{scientist}`` and ``{topic}`` placeholders.
    cache : in-memory verdict cache (caller persists to disk between runs).
    """
    if cache_key and cache_key in cache:
        cached = cache[cache_key]
        return cached["keep"], cached["reason"]
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError:
        return True, f"anthropic-sdk-missing; skipped LLM filter for {kind}"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return True, f"no ANTHROPIC_API_KEY; skipped LLM filter for {kind}"

    client = Anthropic()
    topic = ", ".join(primary_terms[:5]) if primary_terms else "the scientist's research"
    field_block = "\n".join(f"{label}: {value}" for label, value in item_fields.items() if value)
    question = question_template.format(scientist=scientist, topic=topic)
    prompt = (
        f"{field_block}\n\n"
        f"Question: {question} "
        "Answer with YES or NO on the first line, then one short sentence of justification."
    )
    try:
        msg = client.messages.create(
            model=MODEL_ID,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip() if msg.content else ""
    except Exception as exc:  # noqa: BLE001
        return True, f"LLM call failed ({exc}); kept by default"
    first_line = text.splitlines()[0].strip().upper() if text else ""
    keep = first_line.startswith("YES")
    reason = text.replace("\n", " ").strip()[:300]
    if cache_key:
        cache[cache_key] = {"keep": keep, "reason": reason}
    return keep, reason


def load_cache(path: Any) -> dict[str, dict]:
    """Load a verdict cache from JSON; return {} on miss or error."""
    from pathlib import Path

    from _common import load_json

    p = Path(path)
    if not p.exists():
        return {}
    try:
        return load_json(p) or {}
    except Exception:  # noqa: BLE001
        return {}


def save_cache(path: Any, cache: dict[str, dict]) -> None:
    """Persist a verdict cache; swallow IO errors (cache is best-effort)."""
    from pathlib import Path

    from _common import atomic_write_json

    if not cache:
        return
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, cache)
    except Exception:  # noqa: BLE001
        pass
