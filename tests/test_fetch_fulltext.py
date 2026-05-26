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


# ---- YouTube user_confirmed gate ----


def test_main_skips_youtube_transcripts_without_user_confirmed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    yt = tmp_path / "youtube.json"
    yt.write_text(
        json.dumps(
            {
                "scientist": "Judea Pearl",
                "results": [
                    {"video_id": "abc123", "title": "x", "tier": 1, "user_confirmed": False},
                    {"video_id": "def456", "title": "y", "tier": 2},  # user_confirmed missing → also skipped
                ],
            }
        )
    )
    summary = ff.main(youtube=str(yt))
    assert all(item.get("skipped_reason") == "not_user_confirmed" for item in summary["youtube"])
    assert len(summary["youtube"]) == 2


def test_main_attempts_youtube_when_user_confirmed_true(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    yt = tmp_path / "youtube.json"
    yt.write_text(
        json.dumps(
            {
                "scientist": "Judea Pearl",
                "results": [{"video_id": "abc123", "title": "Pearl podcast", "tier": 1, "user_confirmed": True}],
            }
        )
    )
    # Mock the transcript fetcher to return success
    monkeypatch.setattr(
        ff,
        "_fetch_youtube_transcript",
        lambda video_id: {"path": "/tmp/x", "video_id": video_id, "source": "youtube", "cached": False},
    )
    summary = ff.main(youtube=str(yt))
    assert any(item.get("source") == "youtube" and item.get("video_id") == "abc123" for item in summary["youtube"])


# ---- Books ----


def test_fetch_book_uses_description_when_no_text_sources_available(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path)
    # No ISBN → Open Library skipped; no preview link → trafilatura skipped;
    # falls through to description + snippet metadata fallback.
    book = {
        "google_books_id": "gb1",
        "title": "Some Book",
        "isbn": "",
        "description": "A causal-inference primer.",
        "snippet": "Includes worked examples.",
        "preview_link": "",
    }
    result = ff._fetch_book(book)
    assert result is not None
    assert "path" in result
    assert result["text_source"] == "google_books_metadata"
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert "causal-inference" in text or "A causal-inference primer" in text


def test_fetch_book_returns_warning_when_no_text_available(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path)
    book = {
        "google_books_id": "gb2",
        "title": "Empty book",
        "isbn": "",
        "description": "",
        "snippet": "",
        "preview_link": "",
    }
    result = ff._fetch_book(book)
    assert result is not None
    assert result.get("warning") == "no text source available"


def test_fetch_book_caches_after_first_call(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path)
    book = {"google_books_id": "gb-cached", "title": "T", "description": "D", "snippet": "S"}
    first = ff._fetch_book(book)
    assert first is not None
    assert first["cached"] is False
    second = ff._fetch_book(book)
    assert second is not None
    assert second["cached"] is True


def test_main_dispatches_books_when_books_flag_set(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ff, "PAPERS_CACHE", tmp_path / "cache")
    books_path = tmp_path / "books.json"
    books_path.write_text(
        json.dumps(
            {
                "scientist": "Judea Pearl",
                "books": [
                    {
                        "google_books_id": "vol-1",
                        "title": "The Book of Why",
                        "isbn": "",  # forces metadata fallback
                        "description": "The new science of cause and effect.",
                        "snippet": "...",
                        "preview_link": "",
                        "tier": 1,
                    }
                ],
            }
        )
    )
    summary = ff.main(books=str(books_path))
    assert len(summary["books"]) == 1
    entry = summary["books"][0]
    assert entry["title"] == "The Book of Why"
    assert entry["tier"] == 1
