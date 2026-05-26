"""Tests for debate/scripts/_pmc_client.py — JATS XML parse, PMID→PMCID, abstract fetch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import _pmc_client as pmc

_SAMPLE_JATS = """<?xml version="1.0"?>
<article>
  <front>
    <article-meta>
      <title-group><article-title>Test article on GRNs</article-title></title-group>
      <abstract><p>Hard-wired networks specify cell fate.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><p>Body paragraph one.</p></sec>
    <sec><p>Body paragraph two.</p></sec>
  </body>
</article>
"""


def test_parse_pmc_xml_extracts_title_abstract_body(tmp_path: Path):
    path = tmp_path / "PMC123.xml"
    path.write_text(_SAMPLE_JATS, encoding="utf-8")
    parsed = pmc.parse_pmc_xml(path)
    assert "Test article on GRNs" in parsed["title"]
    assert "Hard-wired networks" in parsed["abstract"]
    assert "Body paragraph one" in parsed["body_text"]
    assert "Body paragraph two" in parsed["body_text"]
    assert parsed["pmcid"] == "PMC123"


def test_parse_pmc_xml_handles_malformed_input(tmp_path: Path):
    path = tmp_path / "PMC999.xml"
    path.write_text("not valid xml at all <broken", encoding="utf-8")
    parsed = pmc.parse_pmc_xml(path)
    assert parsed == {"title": "", "abstract": "", "body_text": "", "pmcid": "PMC999"}


def test_pmid_to_pmcid_returns_pmcid_when_present():
    response = MagicMock()
    response.json = MagicMock(return_value={"records": [{"pmid": "12345", "pmcid": "PMC42"}]})
    with patch.object(pmc, "http_get", return_value=response):
        assert pmc.pmid_to_pmcid("12345") == "PMC42"


def test_pmid_to_pmcid_returns_none_when_unavailable():
    response = MagicMock()
    response.json = MagicMock(return_value={"records": []})
    with patch.object(pmc, "http_get", return_value=response):
        assert pmc.pmid_to_pmcid("99999") is None


def test_fetch_abstract_parses_europepmc_response():
    response = MagicMock()
    response.json = MagicMock(
        return_value={
            "resultList": {"result": [{"title": "T", "abstractText": "A", "pubYear": 2024, "authorString": "Foo, Bar"}]}
        }
    )
    with patch.object(pmc, "http_get", return_value=response):
        result = pmc.fetch_abstract("12345")
    assert result == {"title": "T", "abstract": "A", "year": "2024", "authors": "Foo, Bar"}


def test_fetch_abstract_returns_none_for_no_hits():
    response = MagicMock()
    response.json = MagicMock(return_value={"resultList": {"result": []}})
    with patch.object(pmc, "http_get", return_value=response):
        assert pmc.fetch_abstract("99999") is None


def test_fetch_pmc_xml_caches_and_writes(tmp_path: Path):
    response = MagicMock()
    response.content = _SAMPLE_JATS.encode("utf-8")
    with patch.object(pmc, "http_get", return_value=response):
        path = pmc.fetch_pmc_xml("PMC9999", cache_dir=tmp_path)
    assert path is not None
    assert path.exists()
    assert path.name == "PMC9999.xml"
    # Second call reads from cache without invoking http
    with patch.object(pmc, "http_get") as mock_get:
        cached = pmc.fetch_pmc_xml("PMC9999", cache_dir=tmp_path)
        mock_get.assert_not_called()
    assert cached == path


def test_fetch_pmc_xml_returns_none_when_body_invalid(tmp_path: Path):
    response = MagicMock()
    response.content = b"<html>not jats</html>"
    with patch.object(pmc, "http_get", return_value=response):
        assert pmc.fetch_pmc_xml("PMC8888", cache_dir=tmp_path) is None
