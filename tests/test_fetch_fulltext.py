"""Tests for debate/scripts/fetch_fulltext.py — custom-sources ingestion + dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

import fetch_fulltext as ff


def test_ingest_custom_note_writes_to_manual_notes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path)
    item = {"type": "note", "text": "Davidson said this once.", "tier": 1, "label": "Memorable quote"}
    result = ff._ingest_custom_note(item)
    assert result["source"] == "custom_note"
    assert result["tier"] == 1
    assert Path(result["path"]).exists()
    assert "Davidson said this once" in Path(result["path"]).read_text()


def test_ingest_custom_file_copies_text_file_verbatim(tmp_path: Path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_text("Hello world", encoding="utf-8")
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    result = ff._ingest_custom_file({"type": "file", "path": str(src), "tier": 1})
    assert result is not None
    assert result["source"] == "custom_file"
    assert Path(result["path"]).read_text() == "Hello world"


def test_ingest_custom_file_warns_on_missing_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    result = ff._ingest_custom_file({"type": "file", "path": str(tmp_path / "nope.txt"), "tier": 1})
    assert result is not None
    assert "warning" in result


def test_ingest_custom_directory_recurses_with_glob(tmp_path: Path, monkeypatch):
    src = tmp_path / "papers"
    src.mkdir()
    (src / "a.txt").write_text("paper A")
    (src / "b.txt").write_text("paper B")
    (src / "skip.pdf").write_bytes(b"not really a pdf")
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    results = ff._ingest_custom_directory({"type": "directory", "path": str(src), "glob": "*.txt", "tier": 2})
    # Two txt files ingested
    txt_results = [r for r in results if r and r.get("source") == "custom_file"]
    assert len(txt_results) == 2


def test_ingest_custom_url_rejects_linkedin(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    result = ff._ingest_custom_url({"type": "url", "url": "https://www.linkedin.com/posts/eric_grn"})
    assert result is not None
    assert "linkedin" in result.get("warning", "").lower()


def test_main_dispatches_custom_sources_via_inputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    note_text = "A user-supplied note."
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps(
            {
                "ingestion": {"custom_sources": {"Eric Davidson": [{"type": "note", "text": note_text, "tier": 1}]}},
            }
        ),
        encoding="utf-8",
    )
    summary = ff.main(inputs=str(inputs))
    assert any(item.get("source") == "custom_note" for item in summary["custom"])
