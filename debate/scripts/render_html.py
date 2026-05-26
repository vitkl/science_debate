#!/usr/bin/env python3
"""Render markdown files to standalone HTML with an embedded stylesheet.

Used by the Moderator's Phase C4 close-out to render the three audience-tiered
Journalist articles (``article_same_field.md``, ``article_broader_field.md``,
``article_general_stem.md``) to ``.html`` siblings for easy sharing.

The Python ``markdown`` library handles standard markdown plus extras
(extra, codehilite, toc, tables, sane_lists). Stylesheet is bundled at
``debate/scripts/_article_default.css``; user can override via ``--css``.
"""

from __future__ import annotations

import re
from pathlib import Path

import fire
from _common import atomic_write_text

DEFAULT_CSS_PATH = Path(__file__).resolve().parent / "_article_default.css"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body><article>{body}</article></body>
</html>
"""


def _extract_title(md_text: str, fallback: str) -> str:
    """Pull title from first H1 ``# Title`` line if present; fall back to filename stem."""
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _render_one(md_path: Path, css: str, out_dir: Path | None) -> Path:
    import markdown as md_lib  # type: ignore

    text = md_path.read_text(encoding="utf-8")
    body_html = md_lib.markdown(
        text,
        extensions=["extra", "codehilite", "toc", "tables", "sane_lists"],
        output_format="html5",
    )
    title = _extract_title(text, fallback=md_path.stem.replace("_", " "))
    html = _HTML_TEMPLATE.format(
        title=re.sub(r"<[^>]+>", "", title),  # strip any HTML from title
        css=css,
        body=body_html,
    )
    target_dir = out_dir or md_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{md_path.stem}.html"
    atomic_write_text(out_path, html)
    return out_path


def main(
    *,
    inputs: str | list[str],
    css: str | None = None,
    out_dir: str | None = None,
) -> list[Path]:
    """Render one or more markdown files to standalone HTML.

    Pass ``inputs`` as a comma-separated path list (Fire flattens this for us).
    """
    css_path = Path(css) if css else DEFAULT_CSS_PATH
    css_text = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    out_dir_path = Path(out_dir) if out_dir else None

    paths = inputs if isinstance(inputs, list) else [s.strip() for s in str(inputs).split(",") if s.strip()]
    rendered: list[Path] = []
    for raw in paths:
        md_path = Path(raw)
        if not md_path.exists():
            print(f"WARNING: skipping missing input: {md_path}")
            continue
        out = _render_one(md_path, css_text, out_dir_path)
        rendered.append(out)
        print(f"{md_path} -> {out}")
    return rendered


if __name__ == "__main__":
    fire.Fire(main)
