#!/usr/bin/env python3
"""Package debate-event outputs into two zips for sharing and archiving.

Used by the Moderator's Phase C4 close-out:

  - ``<slug>_highlights.zip`` — curated, ready to share: 3 audience-tiered
    articles (md + html), transcript, audience log, manifest, inputs, usage.
  - ``<slug>_full.zip`` — the entire event folder for archival re-runs
    (briefings, intros, talks, needs_*.json, everything except the zips
    themselves).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import fire

HIGHLIGHTS_PATTERNS = (
    "transcript.md",
    "audience.log",
    "manifest.json",
    "usage.json",
    "inputs.json",
    "article_*.md",
    "article_*.html",
)


def _glob_highlights(event_dir: Path) -> list[Path]:
    out: list[Path] = []
    for pat in HIGHLIGHTS_PATTERNS:
        out.extend(sorted(event_dir.glob(pat)))
    # Dedupe while preserving order
    seen: set[Path] = set()
    deduped: list[Path] = []
    for p in out:
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


def _glob_full(event_dir: Path) -> list[Path]:
    """All files in the event folder EXCEPT the zip artefacts themselves."""
    out: list[Path] = []
    for p in sorted(event_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix == ".zip":
            continue
        out.append(p)
    return out


def _write_zip(target: Path, files: list[Path], root: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arcname = f.relative_to(root) if f.is_absolute() else f
            zf.write(f, arcname=str(arcname))
    return target


def main(event_dir: str) -> dict[str, str]:
    """Emit ``<slug>_highlights.zip`` and ``<slug>_full.zip`` inside ``event_dir``."""
    event_path = Path(event_dir).resolve()
    if not event_path.is_dir():
        raise FileNotFoundError(f"event_dir does not exist or is not a directory: {event_path}")
    slug = event_path.name

    highlights_files = _glob_highlights(event_path)
    full_files = _glob_full(event_path)

    highlights_zip = event_path / f"{slug}_highlights.zip"
    full_zip = event_path / f"{slug}_full.zip"

    _write_zip(highlights_zip, highlights_files, event_path)
    _write_zip(full_zip, full_files, event_path)

    result = {
        "highlights_zip": str(highlights_zip),
        "highlights_file_count": str(len(highlights_files)),
        "full_zip": str(full_zip),
        "full_file_count": str(len(full_files)),
    }
    print(result)
    return result


if __name__ == "__main__":
    fire.Fire(main)
