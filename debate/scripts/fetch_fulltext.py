#!/usr/bin/env python3
"""Download full-text content for everything surfaced by the search scripts.

Dispatch table:
  - PMC OA articles  → JATS XML via Europe PMC (``_pmc_client.fetch_pmc_xml``)
  - bioRxiv preprints → PDF via constructed URL → text via ``pymupdf``
  - Generic web pages (blogs, lab sites) → ``trafilatura``
  - YouTube transcripts → ``youtube-transcript-api``
  - Custom sources (``inputs.custom_sources``) — file / directory / url / note

All writes go to ``papers_cache/{fulltext,web,transcripts,manual}/`` keyed by
stable IDs (DOI, URL hash, video ID, content hash). Already-cached items are
skipped silently.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fire
from _common import (
    PAPERS_CACHE,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    content_hash,
    ensure_dirs,
    http_get,
    load_json,
    url_hash,
)
from _pmc_client import fetch_pmc_xml, parse_pmc_xml, pmid_to_pmcid


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    import pymupdf  # type: ignore

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _fetch_biorxiv(doi: str) -> dict[str, Any] | None:
    if not doi:
        return None
    out_dir = PAPERS_CACHE / "fulltext" / "biorxiv"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = doi.replace("/", "_")
    pdf_path = out_dir / f"{safe}.pdf"
    text_path = out_dir / f"{safe}.txt"
    if text_path.exists():
        return {"path": str(text_path), "doi": doi, "source": "biorxiv", "cached": True}
    url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
    try:
        response = http_get(url)
    except Exception:  # noqa: BLE001 — any HTTP failure means "bioRxiv PDF not available"
        return None
    body = response.content
    if not body or not body[:5].startswith(b"%PDF"):
        return None
    atomic_write_bytes(pdf_path, body)
    try:
        text = _extract_pdf_text(body)
    except Exception as exc:  # noqa: BLE001
        return {"path": str(pdf_path), "doi": doi, "source": "biorxiv", "warning": f"pdf extract failed: {exc}"}
    atomic_write_text(text_path, text)
    return {"path": str(text_path), "doi": doi, "source": "biorxiv", "cached": False}


def _fetch_pmc(record: dict[str, Any]) -> dict[str, Any] | None:
    pmcid = record.get("pmcid") or ""
    if not pmcid and record.get("pmid"):
        pmcid = pmid_to_pmcid(record["pmid"]) or ""
    if not pmcid:
        return None
    xml_path = fetch_pmc_xml(pmcid)
    if xml_path is None:
        return None
    parsed = parse_pmc_xml(xml_path)
    text_path = xml_path.with_suffix(".txt")
    if not text_path.exists():
        atomic_write_text(text_path, parsed.get("body_text", "") or parsed.get("abstract", ""))
    return {"path": str(text_path), "pmcid": pmcid, "source": "pmc", "cached": text_path.exists()}


def _fetch_web(url: str) -> dict[str, Any] | None:
    import trafilatura  # type: ignore

    out_dir = PAPERS_CACHE / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{url_hash(url)}.txt"
    if text_path.exists():
        return {"path": str(text_path), "url": url, "source": "web", "cached": True}
    html = trafilatura.fetch_url(url)
    if not html:
        return None
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not extracted:
        return None
    atomic_write_text(text_path, extracted)
    return {"path": str(text_path), "url": url, "source": "web", "cached": False}


def _fetch_youtube_transcript(video_id: str) -> dict[str, Any] | None:
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

    out_dir = PAPERS_CACHE / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{video_id}.txt"
    if text_path.exists():
        return {"path": str(text_path), "video_id": video_id, "source": "youtube", "cached": True}
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as exc:  # noqa: BLE001
        return {"video_id": video_id, "source": "youtube", "warning": f"transcript unavailable: {exc}"}
    text = " ".join(seg["text"] for seg in segments)
    atomic_write_text(text_path, text)
    return {"path": str(text_path), "video_id": video_id, "source": "youtube", "cached": False}


def _ingest_custom_file(item: dict[str, Any]) -> dict[str, Any] | None:
    src = Path(item["path"]).expanduser()
    if not src.exists():
        return {"warning": f"custom file missing: {src}", "source": "custom_file"}
    dest_dir = PAPERS_CACHE / "manual" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists():
        shutil.copy2(src, dest)
    out: dict[str, Any] = {
        "path": str(dest),
        "source": "custom_file",
        "tier": item.get("tier"),
        "label": item.get("label"),
    }
    if src.suffix.lower() == ".pdf":
        text_path = dest.with_suffix(".txt")
        if not text_path.exists():
            try:
                text = _extract_pdf_text(dest.read_bytes())
                atomic_write_text(text_path, text)
                out["text_path"] = str(text_path)
            except Exception as exc:  # noqa: BLE001
                out["warning"] = f"pdf extract failed: {exc}"
        else:
            out["text_path"] = str(text_path)
    elif src.suffix.lower() in {".txt", ".md", ".markdown"}:
        out["text_path"] = str(dest)
    else:
        out["warning"] = f"unhandled extension: {src.suffix}; copied verbatim"
    return out


def _ingest_custom_directory(item: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(item["path"]).expanduser()
    if not root.exists() or not root.is_dir():
        return [{"warning": f"custom directory missing: {root}", "source": "custom_directory"}]
    pattern = item.get("glob") or "*"
    out: list[dict[str, Any]] = []
    for child in sorted(root.rglob(pattern)):
        if child.is_file():
            out.append(
                _ingest_custom_file(
                    {"path": str(child), "tier": item.get("tier"), "label": item.get("label") or child.name}
                )
                or {}
            )
    return out


def _ingest_custom_note(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text", "") or ""
    out_dir = PAPERS_CACHE / "manual" / "notes"
    out_dir.mkdir(parents=True, exist_ok=True)
    note_path = out_dir / f"{content_hash(text)}.md"
    if not note_path.exists():
        atomic_write_text(note_path, text)
    return {"path": str(note_path), "source": "custom_note", "tier": item.get("tier"), "label": item.get("label")}


def _ingest_custom_url(item: dict[str, Any]) -> dict[str, Any] | None:
    url = item["url"]
    if "linkedin.com" in (urlparse(url).netloc or ""):
        return {
            "url": url,
            "source": "custom_url",
            "warning": "LinkedIn has no free public API; paste content as a 'note' custom source instead.",
        }
    return _fetch_web(url) or {"url": url, "source": "custom_url", "warning": "web fetch returned no content"}


def main(
    *,
    works: str | None = None,
    blogs: str | None = None,
    youtube: str | None = None,
    inputs: str | None = None,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Fetch all sources surfaced by upstream scripts. Returns a per-source summary."""
    ensure_dirs()
    summary: dict[str, list[dict[str, Any]]] = {"pmc": [], "biorxiv": [], "blogs": [], "youtube": [], "custom": []}

    if works:
        for record in load_json(Path(works)):
            res = _fetch_pmc(record)
            if res:
                summary["pmc"].append(res)
                continue
            doi = (record.get("doi") or "").lower()
            if "biorxiv" in doi or "10.1101/" in doi:
                res = _fetch_biorxiv(doi)
                if res:
                    summary["biorxiv"].append(res)

    if blogs:
        for post in load_json(Path(blogs)):
            url = post.get("url")
            if not url or post.get("_warning") or post.get("_error"):
                continue
            res = _fetch_web(url)
            if res:
                summary["blogs"].append(res)

    if youtube:
        payload = load_json(Path(youtube))
        for video in payload.get("results", []) if isinstance(payload, dict) else []:
            res = _fetch_youtube_transcript(video["video_id"])
            if res:
                summary["youtube"].append(res)

    if inputs:
        inputs_data = load_json(Path(inputs))
        custom_sources = inputs_data.get("ingestion", {}).get("custom_sources", {})
        for _scientist, items in custom_sources.items():
            for item in items:
                kind = item.get("type")
                if kind == "file":
                    res = _ingest_custom_file(item)
                    if res:
                        summary["custom"].append(res)
                elif kind == "directory":
                    summary["custom"].extend(_ingest_custom_directory(item))
                elif kind == "url":
                    res = _ingest_custom_url(item)
                    if res:
                        summary["custom"].append(res)
                elif kind == "note":
                    summary["custom"].append(_ingest_custom_note(item))

    if out_dir:
        atomic_write_json(Path(out_dir) / "fetch_summary.json", summary)
    print({k: len(v) for k, v in summary.items()})
    return summary


if __name__ == "__main__":
    fire.Fire(main)
