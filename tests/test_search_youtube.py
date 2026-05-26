"""Tests for debate/scripts/search_youtube.py — multi-query, strict speaker filter, tier model."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import search_youtube as syt
from _registry import YoutubeHints

# ---- _is_speaker: strict patterns only ----


def test_is_speaker_rejects_surname_only_channel():
    """Surname-only channel match is intentionally NOT a signal (rejects 'Davidson Realty')."""
    assert not syt._is_speaker("Eric Davidson", "Some random title", "The Davidson Lab", "")


def test_is_speaker_personal_channel_first_and_last_name():
    """Personal channel exception: BOTH first and last name in channel."""
    assert syt._is_speaker("Eric Davidson", "x", "Eric Davidson Channel", "")


def test_is_speaker_institutional_channel_plus_name_in_title():
    """Institutional allowlist channel + name in title ⇒ passes."""
    hints = YoutubeHints(affiliations=["Caltech"])
    assert syt._is_speaker("Eric Davidson", "Eric Davidson on sea urchin GRNs", "Caltech Biology", "", hints)


def test_is_speaker_institutional_channel_without_name_rejected():
    """Institutional channel alone (no name anywhere) ⇒ rejected."""
    hints = YoutubeHints(affiliations=["Caltech"])
    assert not syt._is_speaker("Eric Davidson", "Some unrelated talk", "Caltech Biology", "", hints)


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
    queries = syt._queries_for("Eric Davidson")  # no hints ⇒ base templates only
    assert len(queries) == 7
    assert all("Eric Davidson" in q for q in queries)
    assert any("lecture" in q for q in queries)
    assert any("interview" in q for q in queries)
    assert any("podcast" in q for q in queries)


def test_queries_for_adds_affiliation_and_variant_queries():
    hints = YoutubeHints(
        affiliations=["Caltech", "MBL"],
        name_variants=["Eric H. Davidson"],
    )
    queries = syt._queries_for("Eric Davidson", hints)
    assert any('"Caltech"' in q for q in queries)
    assert any('"MBL"' in q for q in queries)
    assert any('"Eric H. Davidson"' in q for q in queries)


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

    # Scientist not in registry → no extra hint queries; 7 base + 1 topic-boost = 8.
    fake_result = [
        {
            "video_id": "abc",
            "url": "https://youtu.be/abc",
            "title": "Test Scientist lecture on GRNs",
            "channel": "MBL",  # institutional allowlist
            "published_at": "2024",
            "description_excerpt": "x",
            "description_full": "x",
        }
    ]
    with (
        patch.object(syt, "_search_via_ytdlp", return_value=fake_result) as mock_ydl,
        patch.object(syt, "_search_via_api") as mock_api,
    ):
        syt.main(scientist="Test Scientist", out=str(out_path), keywords=str(keywords_path))
    assert mock_ydl.call_count == 8
    mock_api.assert_not_called()

    payload = json.loads(out_path.read_text())
    assert payload["backend"] == "ytdlp"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["user_confirmed"] is False


def test_main_uses_api_when_key_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSyDummy")
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "GRN", "primary_terms": ["GRN"]}), encoding="utf-8")
    out_path = tmp_path / "out.json"

    fake_result = [
        {
            "video_id": "xyz",
            "url": "https://www.youtube.com/watch?v=xyz",
            "title": "Test Scientist lecture",
            "channel": "MBL",
            "published_at": "2024-01-01",
            "description_excerpt": "x",
            "description_full": "x",
        }
    ]
    with (
        patch.object(syt, "_search_via_api", return_value=fake_result) as mock_api,
        patch.object(syt, "_search_via_ytdlp") as mock_ydl,
        patch.object(syt, "_resolve_channel_handles", return_value={}),
    ):
        syt.main(scientist="Test Scientist", out=str(out_path), keywords=str(keywords_path))
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
        syt.main(scientist="Test Scientist", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    assert payload["results"] == []
    assert len(payload["failures"]) == 7
    assert payload["failures"][0]["failure_reason"] == "yt-dlp blew up"


def test_main_persists_full_rejected_list(tmp_path: Path, monkeypatch):
    """Full ``rejected`` list (not just first 5) must be persisted to the cache JSON."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "x", "primary_terms": []}), encoding="utf-8")
    out_path = tmp_path / "out.json"
    fake = [
        {
            "video_id": f"v{i}",
            "url": f"u{i}",
            "title": f"Random Title {i}",
            "channel": "Some Random Channel",
            "published_at": "",
            "description_excerpt": f"desc {i}",
            "description_full": f"desc {i}",
        }
        for i in range(8)
    ]
    with patch.object(syt, "_search_via_ytdlp", return_value=fake):
        syt.main(scientist="Test Scientist", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    assert payload["rejected_count"] == 8
    assert len(payload["rejected"]) == 8
    assert len(payload["rejected_sample"]) == 5
    assert payload["rejected"][0]["description_excerpt"]  # full record kept


def test_dump_rejected_reads_cache(tmp_path: Path, monkeypatch, capsys):
    """--dump-rejected SLUG prints the persisted rejected list."""
    cache_dir = tmp_path / "youtube_search"
    cache_dir.mkdir(parents=True)
    (cache_dir / "test-slug.json").write_text(
        json.dumps(
            {
                "rejected": [
                    {
                        "video_id": "v1",
                        "title": "Some rejected talk",
                        "channel": "Random Chan",
                        "reason": "not_speaker",
                        "description_excerpt": "blah",
                        "url": "https://youtu.be/v1",
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(syt, "PAPERS_CACHE", tmp_path)
    rc = syt.main(dump_rejected="test-slug")
    out = capsys.readouterr().out
    assert rc == 0
    assert "Some rejected talk" in out
    assert "Random Chan" in out


# ---- PODCAST_CHANNELS + multi_speaker flag ----


def test_podcast_channels_constant_includes_known_hosts():
    handles = {h for _, _, h in syt.PODCAST_CHANNELS}
    assert "@samharrisorg" in handles
    assert "@lexfridman" in handles
    assert "@joerogan" in handles


def test_is_multi_speaker_fires_on_podcast_channel_name():
    assert syt._is_multi_speaker("Lex Fridman Podcast", "Episode #100", {})


def test_is_multi_speaker_fires_on_title_hint():
    assert syt._is_multi_speaker("Random Channel", "An interview with Judea Pearl", {})
    assert syt._is_multi_speaker("Random Channel", "Conversation with Carroll", {})


def test_is_multi_speaker_false_for_solo_lecture():
    assert not syt._is_multi_speaker("MIT OpenCourseWare", "Lecture 7: Causality", {})


def test_main_sets_multi_speaker_flag_on_interview_title(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    keywords_path = tmp_path / "k.json"
    keywords_path.write_text(json.dumps({"topic": "x", "primary_terms": []}), encoding="utf-8")
    out_path = tmp_path / "out.json"
    fake = [
        {
            "video_id": "v1",
            "url": "u1",
            "title": "An interview with Judea Pearl",
            "channel": "Generic Channel",
            "published_at": "",
            "description_excerpt": "",
            "description_full": "",
        },
        {
            "video_id": "v2",
            "url": "u2",
            "title": "Judea Pearl lecture on causality",  # solo lecture — not multi-speaker
            "channel": "MIT",
            "published_at": "",
            "description_excerpt": "",
            "description_full": "",
        },
    ]
    with patch.object(syt, "_search_via_ytdlp", return_value=fake):
        syt.main(scientist="Judea Pearl", out=str(out_path), keywords=str(keywords_path))
    payload = json.loads(out_path.read_text())
    results = {r["video_id"]: r for r in payload["results"]}
    assert results["v1"]["multi_speaker"] is True
    assert results["v2"]["multi_speaker"] is False


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
