"""Europe-PMC / NCBI PMC OA full-text fetch + JATS XML parsing.

Adapted from the rate-limit + atomic-cache pattern in
``cell2state/cell2state/motif/_pmc_client.py`` (Vitalii Kleshchevnikov);
vendored here so the package is self-contained for claude.ai/code sandboxes
where cell2state isn't importable.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from _common import PAPERS_CACHE, atomic_write_bytes, http_get

ID_CONVERT_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
PMC_OA_URL_TEMPLATE = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/?report=fulltext&format=xml"
EUROPE_PMC_FULL_TEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
EUROPE_PMC_ABSTRACT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def pmid_to_pmcid(pmid: str) -> str | None:
    """Resolve a PubMed ID to a PMC ID via NCBI's ID converter; returns ``None`` on failure or non-OA."""
    try:
        response = http_get(
            ID_CONVERT_URL,
            params={"ids": pmid, "format": "json", "tool": "science_debate", "email": "vitkl@protonmail.com"},
        )
    except Exception:  # noqa: BLE001 — network blip shouldn't crash the whole fetch run
        return None
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return None
    records = payload.get("records", [])
    if not records:
        return None
    return records[0].get("pmcid")


def fetch_pmc_xml(pmcid: str, cache_dir: Path | None = None) -> Path | None:
    """Fetch JATS-format full-text XML for a PMC OA article. Returns the cache path or ``None`` if unavailable."""
    if cache_dir is None:
        cache_dir = PAPERS_CACHE / "fulltext" / "pmc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{pmcid}.xml"
    if cache_path.exists():
        return cache_path
    url = EUROPE_PMC_FULL_TEXT.format(pmcid=pmcid)
    try:
        response = http_get(url)
    except Exception:  # noqa: BLE001 — any HTTP/parse failure means "PMC OA not available"
        return None
    body = response.content
    if not body or b"<article" not in body[:1024]:
        return None
    atomic_write_bytes(cache_path, body)
    return cache_path


def parse_pmc_xml(xml_path: Path) -> dict[str, str]:
    """Parse JATS XML into ``{title, abstract, body_text, pmcid}``."""
    text = xml_path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"title": "", "abstract": "", "body_text": "", "pmcid": xml_path.stem}
    title = _text(root.find(".//article-title"))
    abstract = " ".join(_text(node) for node in root.findall(".//abstract")).strip()
    body_text = " ".join(_text(node) for node in root.findall(".//body")).strip()
    pmcid = xml_path.stem
    return {"title": title, "abstract": abstract, "body_text": body_text, "pmcid": pmcid}


def fetch_abstract(pmid: str) -> dict[str, str] | None:
    """Citation-only abstract via Europe PMC REST. Returns ``{title, abstract, year, authors}`` or ``None``."""
    try:
        response = http_get(
            EUROPE_PMC_ABSTRACT,
            params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json", "resultType": "lite"},
        )
    except Exception:  # noqa: BLE001
        return None
    try:
        hits = response.json().get("resultList", {}).get("result", [])
    except Exception:  # noqa: BLE001
        return None
    if not hits:
        return None
    hit = hits[0]
    return {
        "title": hit.get("title", ""),
        "abstract": hit.get("abstractText", ""),
        "year": str(hit.get("pubYear", "")),
        "authors": hit.get("authorString", ""),
    }


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()
