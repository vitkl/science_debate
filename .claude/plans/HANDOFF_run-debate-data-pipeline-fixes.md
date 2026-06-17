# HANDOFF — `/run-debate` data-pipeline fixes (author pinning + egress + budget)

- **Repo / branch**: `vitkl/science_debate` @ `claude/dev-bio-debate-846pv0`
- **Event slug under test**: `ariasA_davidsonB_2026-06-17_6cec38`
- **Cast**: Alfonso Martinez Arias (A) vs Eric Davidson (B); James Briscoe (C, Reviewer)
- **Topic**: *Are gene regulatory networks the primary causal determinant of animal development, or is development better understood as a self-organising process of cells and tissues?*
- **Context**: A `/run-debate` run reached Phase B4 (briefings built) and surfaced a set of data-quality / environment issues. This document hands those issues to an implementation agent so they can be fixed **before** re-running the (expensive) downstream debate. Phase B0–B4 artefacts already exist in `debate_events/ariasA_davidsonB_2026-06-17_6cec38/` and `papers_cache/`.

---

## Issue summary

| # | Pri | Issue | Status | Root cause |
|---|-----|-------|--------|------------|
| 1 | **P0** | Namesake contamination in author search | **needs fix** | `search_works.py` matches by **name string only**; no author-ID/ORCID pin |
| 2 | P1 | Briefings blow the 80k-word budget (108k / 96k / 151k) | needs fix (mostly downstream of #1) | namesake papers inflate counts; no knob caps Tier-2a *abstract* count |
| 3 | P2 | `fetch_fulltext.py` doesn't expand `{author}`/`{scientist}` templates | needs fix (code or doc) | `main()` loads the literal templated path → `FileNotFoundError` |
| 4 | P2 | Google Books returns 0 (HTTP 429) | mitigated (manual notes) | IP-rate-limited API; no key / backoff / fallback |
| 5 | P3 | Blog + YouTube egress-blocked | worked around (skipped) | env network policy; scripts don't detect/report egress block cleanly |
| 6 | P3 | Audio prereqs (ffmpeg + Kokoro) not pre-installed | fixed manually | not in web-session setup |

---

## Issue 1 — Namesake contamination (P0, the important one)

### Symptom / evidence
`search_works.py` returns many works by **other people with the same name**. Worst for "Eric Davidson" (a very common name):

- Davidson Tier-2a ("any-topic, first/last author") is dominated by namesakes — e.g. `europepmc:41803450` *"A framework for estimating manure nitrogen balance…"*, `europepmc:40799308` *"Omega-3 Polyunsaturated Fatty Acids … Diabetic Peripheral Neuropathy"*, `europepmc:41502794` *"Nitrogen management during decarbonization"*, plus cardiology / methanogenesis / soil-carbon papers. These are **≥3 distinct "Eric Davidson"s** (a soil/environmental scientist, a nutrition researcher, etc.), none the Caltech developmental biologist.
- Briscoe books matched `openalex:W3151214684` *"Linguistic evolution through language acquisition"* by **E. J. (Ted) Briscoe**, a computational linguist (already manually removed in `papers_cache/books/james-briscoe.json`).
- Briscoe Tier-3 includes Burkholderia genomics, IL-12/T-helper immunology — other Briscoes.

### Root cause
In `debate/scripts/search_works.py`:
- `_europepmc()` (lines 29–53) queries `AUTH:"<name>"` — name string, no author identifier.
- `_openalex()` (lines 56–77) queries `search=<name>` — broad name search, no `author.id` filter.
- The only disambiguation is the post-filter at line 364 `scientist_in_authors(author, r["authors"])`, a **surname token match** — every namesake shares the surname, so it passes them all. (It dropped 461/793 for Davidson but kept 332, still heavily contaminated.)

### Recommended fix — pin the author by OpenAlex `author.id` (NOT ORCID)

> **⚠ Do NOT use ORCID (`AUTHORID:"<orcid>"`) as the disambiguation filter — it is lossy.**
> ORCID is annotated on only a fraction of works (most pre-~2013 papers, and the
> majority of Europe PMC records, carry no ORCID). An ORCID/`AUTHORID` filter would
> silently drop large numbers of the real author's papers — especially bad for a
> deceased author like Davidson whose whole corpus predates widespread ORCID use.
> ORCID is at best a *secondary confirmation* signal, never the primary net.

The right backbone is the **OpenAlex `author.id`**, because OpenAlex *clusters* all of an
author's works (ORCID-tagged or not, across Crossref/PMC/etc.) under one ID. That cluster is
the disambiguation; it is not dependent on per-paper ORCID tagging.

Add one primary flag (ORCID optional, confirmation-only):

```python
def main(author, out, *, keywords=None, tier="all", years=25,
         abstracts_only=False, max_results=500,
         openalex_author_id: str | None = None):   # e.g. "A5103567392"  (may be comma-list for split profiles)
```

Architecture (make OpenAlex the source of truth, EPMC an identifier-keyed enrichment):

1. **OpenAlex `author.id` pin = authoritative work list.** In `_openalex`, when
   `openalex_author_id` is set, drop `search=` and use
   `filter=author.id:<id1>|<id2>,from_publication_date:<since>-01-01`
   (the `|` unions split profiles — see Davidson below). This returns the disambiguated
   author's works **including those with no ORCID**, which is the whole point.
2. **Europe PMC = enrichment by identifier, NOT by name.** Replace the contaminated
   `AUTH:"<name>"` net: take the DOIs/PMIDs/PMCIDs from the OpenAlex-pinned set and look
   each up in Europe PMC (`query=DOI:"<doi>" OR EXT_ID:"<pmid>"`) to pull the better EPMC
   abstract / full-text / structured author position. No EPMC name search ⇒ no EPMC
   namesakes, and nothing is dropped for lacking an ORCID.
3. Keep the surname token post-filter as a cheap backstop only.
4. **OpenAlex clustering is imperfect** — verify the pinned cluster (spot-check titles) and
   union known split profiles. Persist the pin(s) used into the output JSON header for audit.

### Disambiguated identifiers (verified via OpenAlex this session)

| Scientist | OpenAlex author ID | ORCID | Notes |
|-----------|--------------------|-------|-------|
| **Eric H. Davidson** (Caltech dev bio) | `A5103567392` | — (none; pre-ORCID) | 510 works, Caltech 1968–2018, concepts: Developmental Biology & Gene Regulation. **Possible split profile** `A5128641113` (8 works, echinoderm/GRN) — consider unioning both IDs. Avoid `A5113616616` (Georgia Tech materials) and the soil/nutrition namesakes. |
| **Alfonso Martinez Arias** | `A5066926440` | `0000-0002-1781-564X` | 339 works, UPF/ICREA + Cambridge 1988–2022. |
| **James Briscoe** (Crick) | `A5019391436` | `0000-0002-1020-5240` | 426 works, Francis Crick Institute, Hedgehog/neural tube. NOT `A5049553875` (Ted/E.J. Briscoe, musicology/linguistics). |

### Where to store the pins
Add a required-ish `openalex_author_id` (and optional `orcid`, confirmation-only) per scientist in `inputs.json::scientists.<slot>` and have the `run-debate` skill (B2a) pass `openalex_author_id` to `search_works.py`. The skill's B0.5 (cast affiliation WebSearch) is the natural place to *also* resolve and persist the OpenAlex ID by querying `api.openalex.org/authors?search=<name>` and confirming the cluster with the user (works_count + last institution + top concepts), exactly as was done manually this session.

### Residual coverage caveat
Making OpenAlex the authoritative work list means a paper that exists in PMC/EPMC but is **absent from OpenAlex** would be missed. In practice OpenAlex ingests Crossref + PMC + MAG so coverage is very high; the contamination cost of the old EPMC name-net far outweighs this small recall risk. Full-text fetch is unaffected — OpenAlex records carry `ids.pmcid`, which `fetch_fulltext.py` already uses for PMC retrieval.

### Test
Re-run for Davidson with the pin and assert zero soil/nitrogen/cardiology titles:
```
search_works.py "Eric Davidson" 'papers_cache/works/{author}.json' \
  --keywords <kw> --openalex_author_id A5103567392
```
Expect works_count ≈ Caltech corpus; Tier-2a should be sea-urchin / GRN / molecular-biology only.

---

## Issue 2 — Briefing budget overflow (P1)

### Symptom
`build_briefing.py` reported all three over the 80k global cap: **Arias 108,267 / Davidson 96,212 / Briscoe 151,197** words (`needs_user_decision.json`, `needs_summary.json` written).

### Root cause / interaction with #1
- Much of the bulk is namesake papers (esp. Davidson/Briscoe) → fixing #1 should cut this substantially. **Re-measure after author pinning before doing anything else here.**
- Structural gap: `build_briefing.py` (`_build_one`, ~lines 283–319) includes **all** Tier-2a (first/last-author) abstracts; `n_tier2a_full_max` only caps how many get *full text*, not the abstract count. So a prolific author can blow the cap on abstracts alone with no knob to trim. Tier-1 is `n_tier1_max` (default unlimited), Tier-3 is `n_tier3_sample`. **There is no `n_tier2a_abstract_max`.**

### Recommended fix
1. Land #1 first, rebuild, re-measure.
2. If still over: add an `n_tier2a_abstract_max` ingestion knob (cap abstract-only Tier-2a entries, newest-first), mirroring `n_tier3_sample`. Wire in `main()` (~lines 415–447) and `_build_one` (~lines 201–319).
3. Leave the existing Round-1/Round-2 budget-gate (summarise / reduce / drop) as the interactive fallback.

---

## Issue 3 — `fetch_fulltext.py` template expansion (P2)

### Symptom
The skill's B3 shows one invocation with `--works 'papers_cache/works/{author}.json'` etc. But `fetch_fulltext.main()` (line ~380) does `load_json(Path(works))` on the literal string → `FileNotFoundError: '.../{author}.json'`. Had to call it **once per scientist** with resolved slugs (and pass `--inputs` only once so custom-source notes aren't ingested 3×).

### Recommended fix (pick one)
- **Code**: in `main()`, if a path contains `{author}`/`{scientist}`, read `inputs.json::scientists` and loop over the three slugs, expanding per scientist (using `author_slug`), and merge summaries. Also de-dupe custom-source ingestion to once.
- **Doc**: if per-scientist invocation is intended, update `SKILL.md` B3 to show the loop and the "pass `--inputs` once" caveat. (Code fix preferred — matches the templated convention used by `search_works.py` line 374.)

---

## Issue 4 — Google Books 429 (P2)

### Symptom
`search_books.py` Google Books backend returns `429 Too Many Requests` for every scientist (also via WebFetch — it's IP-rate-limiting, not egress). Result: 0 books from Google Books; OpenAlex book records sparse/contaminated. Davidson's foundational GRN trilogy and Arias's *The Master Builder* were not retrieved automatically.

### Mitigation already applied
Added the canonical books as Tier-1 `note` custom sources in `inputs.json::ingestion.custom_sources` (Davidson: *The Regulatory Genome* 2006, *Genomic Control Process* 2015, *Genomic Regulatory Systems* 2001; Arias: *The Master Builder* 2023, *Molecular Principles of Animal Development*), grounded in fetched OpenLibrary/publisher descriptions. These are ingested fine (`fetch_fulltext` custom-note path).

### Recommended fix
Add a Google Books API key (env `GOOGLE_BOOKS_API_KEY`) + exponential backoff, and/or fall back to OpenLibrary/publisher descriptions automatically when 429. After #1's author pinning, also dedupe book namesakes.

---

## Issue 5 — Egress-blocked sources (P3)

### Symptom
- **Blogs**: `amapress.upf.edu` (Arias's lab blog) is **DNS-unreachable** from this environment — both the crawler (`NameResolutionError`) and WebFetch (`ECONNREFUSED`). Skipped.
- **YouTube**: yt-dlp scrapes `youtube.com` → blocked (0 results). The YouTube Data API (`googleapis.com`) IS reachable (would fix *search* with an API key), but transcript download (`youtube-transcript-api`) also hits `youtube.com` → still blocked. User chose to skip YouTube.
- Reachable from this env: `api.openalex.org`, `openlibrary.org`, `www.ebi.ac.uk` (Europe PMC), PMC; `www.googleapis.com` resolves but rate-limits.

### Recommended fix
This is an **environment network-policy** limitation, not a code bug. But the scripts should fail *legibly*: have `search_blogs.py` / `search_youtube.py` detect DNS/egress failures and emit a clear `"egress_blocked": true` marker (vs. silent 0 results), and have the skill note that under restrictive egress policies, blog/YouTube ingestion may be unavailable and to prefer papers + book notes. Consider a `--via-webfetch` mode for blog crawling where WebFetch can reach the domain.

---

## Issue 6 — Audio prereqs not pre-installed (P3)

### Symptom
ffmpeg and Kokoro absent in the web sandbox. Naive `pip install kokoro` fails building `docopt` under Debian's patched setuptools (`AttributeError: install_layout`).

### Fix applied this session (reuse for setup hook)
```bash
apt-get update && apt-get install -y ffmpeg
bash scripts/helper_scripts/run_conda_bash.sh -- env SETUPTOOLS_USE_DISTUTILS=stdlib \
  pip install kokoro soundfile pydub
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_audio.py --warmup   # downloads ~330MB model
```
The `SETUPTOOLS_USE_DISTUTILS=stdlib` env var is the key — it sidesteps the Debian distutils patch that breaks `docopt`'s legacy `setup.py`. Recommend adding the above to the project's SessionStart hook / setup script so web sessions get audio out of the box.

---

## Suggested fix order
1. **Issue 1** (author pinning) — unblocks faithfulness AND most of the budget problem. Land first.
2. **Issue 3** (fetch_fulltext templates) — small, removes a sharp edge for the next run.
3. **Issue 2** (re-measure budget post-#1; add `n_tier2a_abstract_max` only if still over).
4. **Issue 4** (Google Books key/backoff) — quality-of-life.
5. **Issues 5 & 6** — environment/setup; document + add to setup hook.

## What is already done (don't redo)
- Phase A inputs captured → `debate_events/ariasA_davidsonB_2026-06-17_6cec38/inputs.json` (cast, affiliations WebSearch-verified, topic, keywords incl. signature genes, models=opus, voice_map, light ingestion, review_mode=subagent, books on, youtube off).
- ffmpeg + Kokoro installed and warmed up (audio renders).
- Book namesake (Ted Briscoe linguistics) removed; canonical book notes added as custom sources.
- Candidate-review files exist (`papers_cache/works/_review_<slug>.json`) — these become **unnecessary once author pinning lands** (they were the manual workaround for #1).
