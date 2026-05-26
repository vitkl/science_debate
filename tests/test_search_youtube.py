"""Tests for debate/scripts/search_youtube.py — multi-query, strict speaker filter, tier model."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import search_youtube as syt

# ---- _is_speaker: strict patterns only ----


def test_is_speaker_channel_match_surname():
    assert syt._is_speaker("Eric Davidson", "Some title", "The Davidson Lab", "")


def test_is_speaker_channel_match_full_name():
    assert syt._is_speaker("Eric Davidson", "x", "Eric Davidson Channel", "")


def test_is_speaker_title_starts_with_name():
    assert syt._is_speaker("Judea Pearl", "Judea Pearl on causality", "Some Conf", "")


def test_is_speaker_title_colon_prefix():
    """Catches interview-series titles like 'Lex Fridman #56: Judea Pearl'."""
    assert syt._is_speaker("Judea Pearl", "Lex Fridman Podcast #56: Judea Pearl", "Lex Fridman", "")


def test_is_speaker_title_name_with_verb():
    assert syt._is_speaker("Eric Davidson", "Eric Davidson lecture on GRNs", "MBL", "")
    assert syt._is_speaker("Eric Davidson", "Davidson interview at Caltech", "Caltech", "")


def test_is_speaker_title_preposition_with_name():
    assert syt._is_speaker("Judea Pearl", "Causal inference with Judea Pearl", "Some Chan", "")
    assert syt._is_speaker("Judea Pearl", "Talk by Pearl on counterfactuals", "Some Chan", "")


def test_is_speaker_description_interview_pattern():
    assert syt._is_speaker(
        "Judea Pearl", "Causality 101", "AcademyTV", "An interview with Judea Pearl recorded in 2019."
    )


def test_is_speaker_description_featuring_pattern():
    assert syt._is_speaker("Judea Pearl", "Causality 101", "AcademyTV", "Featuring Judea Pearl on his book.")


def test_is_speaker_rejects_mere_mention_with_speaking_word():
    """The key false-positive case: third-party talk that mentions the scientist + has a speaking word."""
    assert not syt._is_speaker(
        "Judea Pearl",
        "Sara Mostafavi - Inferring gene functional networks",  # title doesn't claim Pearl as speaker
        "UBC Computer Science",  # channel is a university, not Pearl
        "Sara Mostafavi gives a talk on graph networks (references Pearl's causal framework).",
    )


def test_is_speaker_rejects_unrelated_video():
    assert not syt._is_speaker("Eric Davidson", "Random Cat Compilation", "Cat Channel", "Cats being cute.")


def test_is_speaker_rejects_empty_scientist():
    assert not syt._is_speaker("", "anything", "anything", "anything")


# ---- _assign_yt_tier: speaker filter already applied; tier on topic ----


def test_yt_tier_1_when_topic_matches():
    assert syt._assign_yt_tier("Pearl on gene regulatory networks", "", ["gene regulatory networks"]) == 1


def test_yt_tier_2_when_speaker_only_no_topic():
    assert syt._assign_yt_tier("Pearl on causality", "", ["gene regulatory networks"]) == 2


def test_yt_tier_2_when_no_keywords_given():
    assert syt._assign_yt_tier("Anything", "anything", []) == 2


# ---- query builders ----


def test_queries_for_returns_seven_speaker_query_templates():
    queries = syt._queries_for("Eric Davidson")
    assert len(queries) == 7
    assert all("Eric Davidson" in q for q in queries)
    assert any("lecture" in q for q in queries)
    assert any("interview" in q for q in queries)
    assert any("podcast" in q for q in queries)


def test_topic_boost_query_when_primary_terms_present():
    q = syt._topic_boost_query("Eric Davidson", {"primary_terms": ["GRN", "cis-regulatory"]})
    assert q and "Eric Davidson" in q and "GRN" in q


def test_topic_boost_query_none_when_no_primary_terms():
    assert syt._topic_boost_query("Eric Davidson", {"primary_terms": []}) is None


# ---- main(): multi-query dispatch, speaker filter, user_confirmed gate ----


def test_main_runs_multiple_queries_via_ytdlp(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": ["GRN"]}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    # Speaker-passing video — title starts with scientist name
    fake_result = [
        {
            "video_id": "abc",
            "url": "https://youtu.be/abc",
            "title": "Eric Davidson lecture on GRNs",
            "channel": "MBL",
            "published_at": "2024",
            "description_excerpt": "x",
            "description_full": "x",
        }
    ]
    with (
        patch.object(syt, "_search_via_ytdlp", return_value=fake_result) as mock_ydl,
        patch.object(syt, "_search_via_api") as mock_api,
    ):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    # 7 base queries + 1 topic-boost = 8 calls
    assert mock_ydl.call_count == 8
    mock_api.assert_not_called()

    payload = json.loads(out_path.read_text())
    assert payload["backend"] == "ytdlp"
    assert len(payload["results"]) == 1  # deduped to 1 video across 8 queries
    assert payload["results"][0]["user_confirmed"] is False  # Moderator's job to flip


def test_main_uses_api_when_key_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSyDummy")
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": ["GRN"]}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    fake_result = [
        {
            "video_id": "xyz",
            "url": "https://www.youtube.com/watch?v=xyz",
            "title": "Eric Davidson lecture",
            "channel": "Lab",
            "published_at": "2024-01-01",
            "description_excerpt": "x",
            "description_full": "x",
        }
    ]
    with (
        patch.object(syt, "_search_via_api", return_value=fake_result) as mock_api,
        patch.object(syt, "_search_via_ytdlp") as mock_ydl,
    ):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    assert mock_api.call_count == 8
    mock_ydl.assert_not_called()

    payload = json.loads(out_path.read_text())
    assert payload["backend"] == "api"


def test_main_records_failures_per_query(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "X", "primary_terms": []}), encoding="utf-8")
    out_path = tmp_path / "out.json"
    with patch.object(syt, "_search_via_ytdlp", return_value={"failure_reason": "yt-dlp blew up"}):
        syt.main(scientist="Eric Davidson", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    assert payload["results"] == []
    assert len(payload["failures"]) == 7  # every query failed; no topic-boost when no primary_terms
    assert payload["failures"][0]["failure_reason"] == "yt-dlp blew up"


def test_main_filters_out_non_speaker_videos(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": []}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    fake = [
        {
            "video_id": "nope",
            "url": "x",
            "title": "Sara Mostafavi - graph networks",  # Pearl mentioned only in description
            "channel": "UBC CS",
            "published_at": "",
            "description_excerpt": "",
            "description_full": "talks about graph networks; references Pearl's framework",
        }
    ]
    with patch.object(syt, "_search_via_ytdlp", return_value=fake):
        syt.main(scientist="Judea Pearl", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    assert payload["results"] == []  # speaker filter rejected
    assert payload["rejected_count"] >= 1
