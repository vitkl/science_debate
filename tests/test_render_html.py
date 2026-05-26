"""Tests for debate/scripts/render_html.py — markdown→HTML rendering with embedded CSS."""

from __future__ import annotations

from pathlib import Path

import render_html as rh


def test_extract_title_picks_h1():
    assert rh._extract_title("# My Article\n\nbody", fallback="x") == "My Article"


def test_extract_title_falls_back_to_filename_when_no_h1():
    assert rh._extract_title("body without heading", fallback="my_article") == "my_article"


def test_render_one_produces_well_formed_html(tmp_path: Path):
    md = tmp_path / "article.md"
    md.write_text("# Title\n\nFirst paragraph.\n\n> A quote.\n\n```python\nprint('x')\n```\n")
    out = rh._render_one(md, css="body { color: red; }", out_dir=tmp_path)
    html = out.read_text(encoding="utf-8")
    assert out.name == "article.html"
    assert html.startswith("<!DOCTYPE html>")
    # toc extension adds id="title" to the heading — match either form
    assert "<h1" in html and ">Title</h1>" in html
    assert "<blockquote>" in html
    assert "<pre>" in html  # code block rendered (codehilite wraps in div + pre)
    assert "<style>body { color: red; }</style>" in html
    assert "<title>Title</title>" in html


def test_render_one_writes_into_out_dir_when_given(tmp_path: Path):
    md = tmp_path / "article.md"
    md.write_text("# T\n\nbody")
    out_dir = tmp_path / "html"
    out = rh._render_one(md, css="", out_dir=out_dir)
    assert out.parent == out_dir
    assert out.exists()


def test_main_renders_multiple_inputs(tmp_path: Path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# Article A\n\nbody")
    b.write_text("# Article B\n\nbody")
    rendered = rh.main(inputs=[str(a), str(b)])
    assert len(rendered) == 2
    assert (tmp_path / "a.html").exists()
    assert (tmp_path / "b.html").exists()


def test_main_warns_on_missing_input(tmp_path: Path, capsys):
    rendered = rh.main(inputs=[str(tmp_path / "missing.md")])
    assert rendered == []
    out = capsys.readouterr().out
    assert "missing" in out.lower()


def test_main_accepts_csv_string(tmp_path: Path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# A\n\nx")
    b.write_text("# B\n\nx")
    rendered = rh.main(inputs=f"{a},{b}")
    assert len(rendered) == 2


def test_main_uses_custom_css_when_provided(tmp_path: Path):
    md = tmp_path / "a.md"
    md.write_text("# T\n\nx")
    css = tmp_path / "custom.css"
    css.write_text("body { font-family: monospace; }")
    rh.main(inputs=str(md), css=str(css))
    html = (tmp_path / "a.html").read_text(encoding="utf-8")
    assert "monospace" in html
