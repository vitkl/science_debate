#!/usr/bin/env python3
"""Stitch the end-of-debate combined ``full_debate.md`` artefact.

Reads ``inputs.json``, ``team.json``, ``intro_<X>.md`` (3), ``transcript.md``,
``article_*.md`` (3), and ``audience.log`` (JSONL) from an event folder, and
emits a single ``full_debate.md`` with the structure proven out in the
reference event (slug ariasA_davidsonB_2026-05-26_c7893c):

    # <Title>                              ← H1 (auto or inputs.title)
    **Topic:** ...                         ← topic verbatim
    **Cast:** Presenter A — ... · ...      ← roles + real names + affiliations

    A 10-stage structured debate at ...    ← narrative Format paragraph

    | # | Stage | Speaker | Words | Audience can ask questions (asked) |
    | ... |                                ← Format table (real names)

    ## Contents                            ← TOC w/ anchor links
    - ...

    ## Self-introductions                  ← intros from intro_<X>.md
    ### <Real name> (Presenter A)
    ...

    ## The debate                          ← from transcript.md
    ### Stage 1 — Opening A (Presenter A)  ← H2→H3 demotion during stitch
    ...

    ## Journalist's write-up — three audience-tiered articles
    ### For scientists in the same field
    ...
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fire
from _common import atomic_write_text

# Per FORMAT.md stage table (targets at total_minutes=80, scale by T/80).
BREAK_POINTS = {1, 2, 4, 6, 7, 8, 9, 10}

# Format-table rows. Each entry: (label, role_descr, default_words_at_80m,
# speaker_slot_for_render, audience_break_after_this_stage_or_substage).
FORMAT_TABLE_ROWS = [
    ("1", "Opening presentation A", 1500, "A", "yes"),
    ("1q", "Clarifying-question round after Stage 1 (B and C ask A)", 0, None, "—"),
    ("2", "Opening presentation B", 1500, "B", "yes"),
    ("2q", "Clarifying-question round after Stage 2 (A and C ask B)", 0, None, "—"),
    ("3", "B critiques A (Opponent B)", 700, "B", "—"),
    ("3q", "Clarifying-question round after Stage 3 (A and C ask B)", 0, None, "—"),
    ("4", "A responds (Presenter A)", 500, "A", "yes"),
    ("5", "A critiques B (Opponent A)", 700, "A", "—"),
    ("5q", "Clarifying-question round after Stage 5 (B and C ask A)", 0, None, "—"),
    ("6", "B responds (Presenter B)", 500, "B", "yes"),
    ("7", "Reviewer assessment round 1 (Reviewer C)", 400, "C", "yes"),
    ("8a", "Final rejoinder A — round 1 (Presenter)", 400, "A", "—"),
    ("8b", "Final rejoinder B — round 1 (Presenter)", 400, "B", "yes"),
    ("9", "Reviewer assessment round 2 (Reviewer C)", 400, "C", "yes"),
    ("10a", "Final rejoinder A — round 2 (Presenter)", 400, "A", "—"),
    ("10b", "Final rejoinder B — round 2 (Presenter)", 400, "B", "yes"),
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _surname(team: dict, slot: str) -> str:
    return team[slot]["name"]


def _scientist_full_name(inputs: dict, slot: str) -> str:
    return inputs["scientists"][slot].get("name", f"Scientist {slot}")


def _cast_block(inputs: dict, team: dict) -> str:
    """Build the Cast line from inputs.json::scientists.<X> metadata.

    Uses `{title, affiliation, notes}` populated by §5's B0.5 WebSearch step
    when present; falls back to name-only if any field is missing.
    """
    role_labels = {
        "A": "Presenter A",
        "B": "Presenter B",
        "C": "Reviewer",
    }
    parts = []
    for slot in ("A", "B", "C"):
        sci = inputs.get("scientists", {}).get(slot, {})
        name = sci.get("name") or f"Scientist {slot}"
        title = sci.get("title")
        affiliation = sci.get("affiliation")
        notes = sci.get("notes")
        bits = [name]
        descr = []
        if title:
            descr.append(title)
        if affiliation:
            descr.append(affiliation)
        if descr:
            bits.append(f"({', '.join(descr)})")
        if notes:
            bits.append(f"— {notes}")
        parts.append(f"{role_labels[slot]} — {' '.join(bits)}")
    parts.append("Moderator (lead)")
    parts.append("Journalist (post-debate articles)")
    return "**Cast:** " + " · ".join(parts) + "."


def _scale_words(default_words: int, total_minutes: int) -> int:
    if default_words == 0:
        return 0
    return int(round(default_words * total_minutes / 80))


def _format_paragraph(total_minutes: int) -> str:
    return (
        f"A 10-stage structured debate at a default budget of {total_minutes} minutes "
        f"(≈100 words per spoken minute). Each presenter prepares a self-introduction "
        f"and an opening talk in advance, iterating against a faithfulness self-assessment "
        f"loop. The live debate then opens with the two prepared talks (Stages 1–2), "
        f"proceeds through two cross-examination pairs in which each opponent critiques "
        f"the other and the presenter responds (Stages 3–4, 5–6), and closes with two "
        f"reviewer-and-rejoinder rounds: the Reviewer assesses the exchange and identifies "
        f"the most productive remaining disagreement, after which each presenter delivers "
        f"a short final rejoinder (Stages 7–8, then 9–10). Stages 3–10 are improvised "
        f"after being presented with the prior transcript — each stage sees the transcript "
        f"before it. Stages 1, 2, 3, and 5 each have a brief intra-stage clarifying-question "
        f"round (≤30-word Q, ≤50-word A). Stages 8 and 10 execute as sub-stages 8a/8b and "
        f"10a/10b (sequential A then B; B reads transcript including A's just-appended block)."
    )


def _audience_counts(audience_log: Path) -> Counter:
    """Count audience interjections per `after_stage` from the JSONL log.

    Tolerates missing file (returns empty Counter).
    """
    counts: Counter = Counter()
    if not audience_log.exists() or audience_log.stat().st_size == 0:
        return counts
    for line in audience_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        stage = entry.get("after_stage")
        if isinstance(stage, int):
            counts[stage] += 1
    return counts


def _audience_cell(label: str, break_marker: str, audience_counts: Counter) -> str:
    """Resolve the Audience-column cell value for a Format-table row."""
    if break_marker == "—":
        return "—"
    # Map sub-stage label (e.g. '8b') back to the integer stage that fires the
    # break. If the label doesn't start with digits, fail open with "—" rather
    # than crashing — defensive in case FORMAT_TABLE_ROWS grows a non-digit row.
    m = re.match(r"^\d+", label)
    if not m:
        return "—"
    stage_int = int(m.group(0))
    n = audience_counts.get(stage_int, 0)
    return f"yes ({n})"


def _slugify_anchor(text: str, seen: dict[str, int] | None = None) -> str:
    """Match python-markdown toc extension's anchor slug rules.

    Disambiguates duplicate slugs with a `-2`, `-3` suffix (so two identical
    headings get distinct anchors), using `seen` as a counter dict the caller
    threads.
    """
    s = text.lower()
    s = re.sub(r"[^a-z0-9 \-]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = s or "section"
    if seen is None:
        return s
    count = seen.get(s, 0)
    seen[s] = count + 1
    if count == 0:
        return s
    return f"{s}-{count + 1}"


def _format_table(team: dict, inputs: dict, audience_counts: Counter) -> str:
    total_minutes = inputs.get("debate", {}).get("total_minutes", 80)
    surnames = {slot: _surname(team, slot) for slot in ("A", "B", "C")}
    header = "| # | Stage | Speaker | Words (target) | Audience can ask questions (asked) |\n|---|---|---|---|---|"
    lines = [header]
    for label, stage_descr, default_w, speaker_slot, break_marker in FORMAT_TABLE_ROWS:
        speaker = surnames.get(speaker_slot, "—") if speaker_slot else "—"
        if default_w == 0:
            words_cell = "≤30 / ≤50 per micro"
        else:
            words_cell = str(_scale_words(default_w, total_minutes))
        audience_cell = _audience_cell(label, break_marker, audience_counts)
        lines.append(f"| {label} | {stage_descr} | {speaker} | {words_cell} | {audience_cell} |")
    return "\n".join(lines) + "\n"


def _read_intros(event_dir: Path, team: dict) -> str:
    """Emit ## Self-introductions section with H3 per scientist (real name + role)."""
    role_labels = {
        "A": "Presenter A",
        "B": "Presenter B",
        "C": "Reviewer",
    }
    parts = ["## Self-introductions\n"]
    for slot in ("A", "B", "C"):
        intro_path = event_dir / f"intro_{slot}.md"
        if not intro_path.exists():
            parts.append(f"### {team[slot]['name']} ({role_labels[slot]})\n\n*(intro missing)*\n\n")
            continue
        body = intro_path.read_text(encoding="utf-8").rstrip()
        parts.append(f"### {team[slot]['name']} ({role_labels[slot]})\n\n{body}\n\n")
    return "".join(parts)


def _read_debate(event_dir: Path) -> str:
    """Emit ## The debate section from transcript.md, demoting H2 stages to H3.

    compose_transcript.py guarantees the `## The debate` marker is seeded; if
    it's missing here, something has tampered with transcript.md — strip up to
    the first post-self-introductions H2 rather than re-emit the whole file
    (which would
    duplicate H1 + intros).
    """
    transcript = (event_dir / "transcript.md").read_text(encoding="utf-8")
    marker = "\n## The debate\n"
    idx = transcript.find(marker)
    if idx != -1:
        body = transcript[idx + len(marker) :]
    else:
        # Fallback: drop everything up to and including the first H2 that
        # isn't `## Self-introductions`, so we don't re-emit H1+intros.
        lines = transcript.splitlines(keepends=True)
        body_lines: list[str] = []
        in_body = False
        for line in lines:
            if not in_body and line.startswith("## ") and "Self-introductions" not in line:
                in_body = True
                continue
            if in_body:
                body_lines.append(line)
        body = "".join(body_lines) if body_lines else transcript
    body = re.sub(r"^## (Stage )", r"### \1", body, flags=re.MULTILINE)
    return "## The debate\n\n" + body.lstrip()


def _read_articles(event_dir: Path) -> str:
    """Emit ## Journalist's write-up section with three H3 articles."""
    parts = ["## Journalist's write-up — three audience-tiered articles\n\n"]
    tier_labels = [
        ("article_same_field.md", "For scientists in the same field"),
        ("article_broader_field.md", "For scientists in adjacent fields"),
        ("article_general_stem.md", "For STEM-educated readers without field background"),
    ]
    for fname, label in tier_labels:
        path = event_dir / fname
        if not path.exists():
            parts.append(f"### {label}\n\n*(article missing: {fname})*\n\n")
            continue
        body = path.read_text(encoding="utf-8").rstrip()
        parts.append(f"### {label}\n\n{body}\n\n")
    return "".join(parts)


def _toc(full_debate_md: str) -> str:
    """Build a TOC of all H2 and H3 headings in the assembled document.

    Threads a `seen` counter through _slugify_anchor so duplicate headings get
    `-2`, `-3` suffixes — mirrors python-markdown's toc extension behaviour.
    """
    seen: dict[str, int] = {}
    lines = []
    for raw in full_debate_md.splitlines():
        m = re.match(r"^(#{2,3}) +(.+?)\s*$", raw)
        if not m:
            continue
        level = len(m.group(1))
        text = m.group(2)
        anchor = _slugify_anchor(text, seen=seen)
        indent = "  " * (level - 2)
        lines.append(f"{indent}- [{text}](#{anchor})")
    return "## Contents\n\n" + "\n".join(lines) + "\n"


def _title(inputs: dict, team: dict) -> str:
    user_title = inputs.get("title")
    if user_title:
        return user_title.strip()
    surnames = sorted([_surname(team, "A"), _surname(team, "B")])
    return f"{surnames[0]} vs. {surnames[1]} — Full debate"


def main(*, event_dir: str) -> dict[str, str]:
    """Stitch full_debate.md for the named event folder."""
    event_path = Path(event_dir).resolve()
    if not event_path.is_dir():
        raise FileNotFoundError(f"event_dir not a directory: {event_path}")

    inputs = _load_json(event_path / "inputs.json")
    team = _load_json(event_path / "team.json")
    total_minutes = inputs.get("debate", {}).get("total_minutes", 80)
    audience_counts = _audience_counts(event_path / "audience.log")

    title = _title(inputs, team)
    topic = inputs.get("topic", "Untitled debate")

    # Build the body first (without TOC), then prepend TOC after computing anchors.
    body_parts: list[str] = []
    body_parts.append(f"# {title}\n\n")
    body_parts.append(f"**Topic:** {topic}\n\n")
    body_parts.append(_cast_block(inputs, team) + "\n\n")
    body_parts.append(_format_paragraph(total_minutes) + "\n\n")
    body_parts.append(_format_table(team, inputs, audience_counts) + "\n")
    intros_block = _read_intros(event_path, team)
    debate_block = _read_debate(event_path)
    articles_block = _read_articles(event_path)
    # Compose with a placeholder for TOC so its anchors can scan the assembled doc.
    placeholder = "<!--TOC-->\n\n"
    pre_toc = "".join(body_parts)
    post_toc = intros_block + "\n" + debate_block + "\n" + articles_block
    assembled = pre_toc + placeholder + post_toc
    toc_text = _toc(assembled)
    full_debate_md = assembled.replace(placeholder, toc_text + "\n")

    out_path = event_path / "full_debate.md"
    atomic_write_text(out_path, full_debate_md)

    audience_total = sum(audience_counts.values())
    result = {
        "full_debate_md": str(out_path),
        "word_count": str(len(full_debate_md.split())),
        "audience_interjections_total": str(audience_total),
        "audience_counts": json.dumps(dict(audience_counts)),
    }
    print(result)
    return result


if __name__ == "__main__":
    fire.Fire(main)
