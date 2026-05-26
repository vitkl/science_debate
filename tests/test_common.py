"""Tests for debate/scripts/_common.py — HTTP, caching, slug, hash helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import _common as common
import pytest
import requests


def test_slug_basic():
    assert common.slug("Eric Davidson") == "eric-davidson"


def test_slug_ascii_folds_accents():
    assert common.slug("Alfonso Martínez-Arias") == "alfonso-martinez-arias"


def test_slug_empty_string_falls_back():
    assert common.slug("") == "unnamed"
    assert common.slug("   ") == "unnamed"


def test_slug_strips_repeated_punctuation():
    assert common.slug("foo!!bar??baz") == "foo-bar-baz"


def test_url_hash_is_deterministic():
    h1 = common.url_hash("https://example.com/x")
    h2 = common.url_hash("https://example.com/x")
    assert h1 == h2
    assert len(h1) == 16


def test_url_hash_differs_per_url():
    assert common.url_hash("https://a.com") != common.url_hash("https://b.com")


def test_content_hash_is_deterministic():
    assert common.content_hash("hello") == common.content_hash("hello")
    assert common.content_hash("hello") != common.content_hash("world")


def test_word_count():
    assert common.word_count("") == 0
    assert common.word_count("one") == 1
    assert common.word_count("one two   three\nfour") == 4


def test_atomic_write_json_round_trip(tmp_path: Path):
    target = tmp_path / "sub" / "out.json"
    payload = {"a": 1, "b": [1, 2, 3], "c": "x"}
    common.atomic_write_json(target, payload)
    assert json.loads(target.read_text()) == payload
    # No leftover .tmp file
    leftovers = list(tmp_path.rglob("*.tmp.*"))
    assert leftovers == []


def test_atomic_write_text_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "nested" / "dirs" / "x.txt"
    common.atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def _ok_response(status: int = 200, body: bytes = b"{}") -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.content = body
    response.text = body.decode("utf-8") if isinstance(body, bytes) else body
    response.headers = {}
    response.json = MagicMock(return_value=json.loads(body or b"{}"))
    response.raise_for_status = MagicMock()
    return response


def test_http_get_success_returns_response():
    with patch.object(common.requests, "get", return_value=_ok_response()) as mock_get:
        response = common.http_get("https://example.com")
    assert response.status_code == 200
    mock_get.assert_called_once()


def test_http_get_retries_on_429_then_succeeds():
    sequence = [_ok_response(status=429), _ok_response(status=429), _ok_response(status=200, body=b'{"ok": true}')]
    with patch.object(common.requests, "get", side_effect=sequence) as mock_get, patch.object(common.time, "sleep"):
        response = common.http_get("https://example.com", backoff=(0.0, 0.0, 0.0))
    assert response.status_code == 200
    assert mock_get.call_count == 3


def test_http_get_raises_after_exhausting_retries():
    failing = [_ok_response(status=429) for _ in range(4)]
    with patch.object(common.requests, "get", side_effect=failing), patch.object(common.time, "sleep"):
        with pytest.raises((requests.HTTPError, RuntimeError)):
            common.http_get("https://example.com", backoff=(0.0, 0.0, 0.0))
