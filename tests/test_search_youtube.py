"""Tests for debate/scripts/search_youtube.py — backend selection, channel match, query build."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import search_youtube as syt


def test_channel_matches_scientist_surname_match():
    assert syt._channel_matches_scientist("The Davidson Lab", "Eric Davidson")


def test_channel_matches_scientist_full_name_components():
    assert syt._channel_matches_scientist("Eric Davidson talks", "Eric Davidson")


def test_channel_matches_scientist_rejects_unrelated():
    assert not syt._channel_matches_scientist("Random Cat Channel", "Eric Davidson")


def test_query_for_uses_primary_terms():
    keywords = {"primary_terms": ["gene regulatory networks", "GRN"], "topic": "ignored"}
    q = syt._query_for("Eric Davidson", keywords)
    assert "Eric Davidson" in q
    assert "gene regulatory networks" in q
    assert "GRN" in q
    assert " OR " in q


def test_query_for_falls_back_to_topic_when_no_primary():
    keywords = {"primary_terms": [], "topic": "development"}
    q = syt._query_for("Eric Davidson", keywords)
    assert "Eric Davidson" in q and "development" in q


def test_main_uses_ytdlp_when_no_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": ["GRN"]}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    fake_results = [
        {
            "video_id": "abc",
            "url": "https://youtu.be/abc",
            "title": "T",
            "channel": "Davidson Lab",
            "published_at": "2024",
            "description_excerpt": "",
            "scientist_channel_match": True,
        }
    ]
    with (
        patch.object(syt, "_search_via_ytdlp", return_value=fake_results) as mock_ydl,
        patch.object(syt, "_search_via_api") as mock_api,
    ):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    mock_ydl.assert_called_once()
    mock_api.assert_not_called()

    payload = json.loads(out_path.read_text())
    assert payload["backend"] == "ytdlp"
    assert len(payload["results"]) == 1


def test_main_uses_api_when_key_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSyDummy")
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": ["GRN"]}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    fake_results = [
        {
            "video_id": "xyz",
            "url": "https://www.youtube.com/watch?v=xyz",
            "title": "Talk",
            "channel": "Conf",
            "published_at": "2024-01-01",
            "description_excerpt": "",
            "scientist_channel_match": False,
        }
    ]
    with (
        patch.object(syt, "_search_via_api", return_value=fake_results) as mock_api,
        patch.object(syt, "_search_via_ytdlp") as mock_ydl,
    ):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    mock_api.assert_called_once()
    mock_ydl.assert_not_called()

    payload = json.loads(out_path.read_text())
    assert payload["backend"] == "api"


def test_main_writes_failure_reason_on_backend_error(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "X", "primary_terms": []}), encoding="utf-8")
    out_path = tmp_path / "out.json"
    with patch.object(syt, "_search_via_ytdlp", return_value={"failure_reason": "yt-dlp blew up"}):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    assert payload["results"] == []
    assert payload["failure_reason"] == "yt-dlp blew up"


def test_search_via_api_handles_http_error():
    import requests as _req

    err = _req.HTTPError("boom")
    with patch.object(syt, "http_get", side_effect=err):
        result = syt._search_via_api("X", "query", "AIzaKey", 5)
    assert isinstance(result, dict)
    assert "failure_reason" in result
