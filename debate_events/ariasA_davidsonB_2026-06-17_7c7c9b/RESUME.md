# RESUME — Martinez Arias vs Davidson (Briscoe reviewer)

**Slug:** `ariasA_davidsonB_2026-06-17_7c7c9b`
**Topic:** Is animal development driven primarily by hardwired, deterministic gene
regulatory networks encoded in the genome (Davidson), or by self-organisation and
dynamical-systems processes emerging from cell interactions (Martinez Arias)?

## Cast
- **A — Alfonso Martinez Arias** — ICREA Research Professor, Systems Bioengineering, Universitat Pompeu Fabra, Barcelona
- **B — Eric Davidson** — Norman Chandler Professor of Cell Biology, Caltech, 1937–2015; represented faithfully from his published work
- **C (Reviewer) — James Briscoe** — Associate Research Director and Senior Group Leader, Francis Crick Institute; Editor-in-Chief, *Development*

## Status

### Done (committed to branch `claude/debate-three-participants-7iaj7m`)
- ✅ Phase A inputs collected → `inputs.json` (`complete: true`)
  - 80 min; YouTube + Books on; websearch-during-debate off; presenter tone off
  - ingestion: lighter (n_full_papers_cap=15, n_tier3_sample=10); review_mode=subagent
  - models: all Opus; journalist budget 550
- ✅ B0 event folder; B0.5 cast affiliations (WebSearch-confirmed) merged into `inputs.json`
- ✅ B1 keywords → `keywords.json` (GRN/self-org terms + famous gene names: Shh, Gli, Wnt, Notch, Nodal, BMP, Brachyury, Hox, Sox2, Gata, Otx, Pax6, bicoid)
- ✅ Voice map → `voice_map.json` (A=bm_george, B=am_michael, C=bm_lewis, Moderator=af_heart, Journalist=bf_emma, Audience=am_adam)
- ✅ **Audio fixed**: `render_audio.py` falls back to a GitHub-hosted Kokoro ONNX model when HuggingFace is blocked (warmup passes). Assets cached at `~/.cache/kokoro-onnx/` in the OLD sandbox — a fresh env will re-download them from the GitHub release on first `--warmup` (needs network open).

### NOT done — blocked by network policy
- ⛔ B2 search (papers/blogs/books/youtube), B3 fetch, B4 briefings, B5 prep, Phase C debate.
  The old environment was on "Package managers only" egress; all academic APIs (PubMed,
  OpenAlex, EuropePMC, Crossref, Semantic Scholar, arXiv, bioRxiv) returned 403.

## To resume
1. **Precondition:** environment network egress must be **"All domains"** (Settings → Capabilities → Code execution → Allow network egress, on desktop browser). Verify with a quick reachability probe before searching.
2. Re-invoke `/run-debate` in a fresh conversation; say "resume the Martinez Arias / Davidson / Briscoe debate".
3. Read `inputs.json` (`complete: true`) and skip Phase A. Jump straight to **B2 — search** using the existing `keywords.json`.
4. Run first-run dep install (`pip install -e .`) and audio warmup as usual.
5. Continue B2 → B3 → B4 → B5 → B6 gate → Phase C as normal.
