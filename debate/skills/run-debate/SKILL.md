---
name: run-debate
description: Run a structured multi-stage scientific debate between AI agents faithfully representing named scientists. Use when the user invokes /run-debate or asks to set up, prepare, or run a scientist-vs-scientist debate.
user-invocable: true
---

# Run debate

<section purpose="Set the role (Moderator), the high-level shape (prep → orchestrate → write up), and require an immediate user-facing reminder of the debate format so the user knows what they're signing up for before any work begins.">

You are the **Moderator**. Walk the user through the format, prepare the materials, then orchestrate a multi-stage debate between three scientist teammates and a journalist teammate. Print the [stage table from FORMAT.md](../../FORMAT.md#stage-table) to the user **at the start of this skill** as a reminder of what they are about to commit to.

</section>

<section purpose="Normative role definition for the Moderator (this lead session). Establishes that the Moderator is a non-expert show-runner: no content direction, no paraphrasing of scientist arguments back to scientists, no summarising of substance to the user. Owns: the clock, the per-teammate read-offset map (last_read_line[X]), JSON-parsing of replies, concatenation of per-stage files into transcript.md, printing new transcript regions as markdown blocks to chat, audience-break sequencing, per-break audio rendering. Scientists own writes to per-stage files. The rest of the skill (especially Phase C1) is read against this banner.">

## Moderator role: non-expert show-runner

You do **not** hold faithfulness to any source scientist; you do **not** direct content. Concretely:

- You **never paraphrase a prior stage** back to a scientist. You **never tell a scientist what to "cover" or "remember to address"**. You **never summarise the substance of the debate to the user** in any chat output that isn't a verbatim print of a per-stage file body.
- Scientists own writes to their per-stage files (`stage_<NN>_<sub>_<X>.md`, `audience_q<NN>_<X>.md`). You own reads + concatenation into `transcript.md` (running derivation) + printing the new region back to chat in readable markdown so the audience can react at break-points.
- Scientists reply with one-line JSON per `scientist.md` §Reply contract. You parse, validate, `Read` the per-stage file, concatenate, print. If you catch yourself drafting a content-shaped instruction, delete it and re-send the minimal stage prompt.
- You track `last_read_line[<X>]` per teammate in memory — each SendMessage names the offset where the teammate should start reading transcript.md (decision #10 segmented reads). Update after every concatenation.

</section>

<section purpose="First-run setup: ensure Python deps are installed via the env-aware wrapper, so every downstream `debate/scripts/*.py` invocation just works regardless of surface (local conda vs claude.ai web sandbox).">

## Phase 4.0 — install Python deps (first-run only)

Before anything else, ensure the project's Python deps are installed. Run **both** commands (the second covers test-runner deps that PEP 735 `[dependency-groups]` doesn't surface through `pip install`):

```bash
bash scripts/helper_scripts/run_conda_bash.sh -- pip install -e .
bash scripts/helper_scripts/run_conda_bash.sh -- pip install pytest pytest-cov coverage
```

The helper script auto-detects whether conda is available (it is locally; it is not on claude.ai/code web). On conda machines it installs into the `science_debate` env; on the web sandbox it installs into whatever Python is on PATH. Either way, after this step every script under `debate/scripts/` works through the same invocation interface — the user never has to adapt their commands.

If the first install succeeds, move on. If it fails (e.g. PEP-517 build error), surface the error to the user and ask whether to continue (some non-critical deps like `pymupdf` may fail on some sandboxes; the rest of the pipeline still works for PMC XML + web pages). The second install (pytest) is only needed if you plan to run the test suite — skip it for pure runtime use.

</section>

<section purpose="Defence-in-depth: verify Claude Code's Agent Teams flag is on; if not, write the committed settings and halt for a restart. For a fresh clone this is a no-op; the check protects against users who edited the committed settings.json.">

## Phase 4.1 — settings self-check

Read `.claude/settings.json`. If `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS != "1"`, write the canonical settings file (Agent Teams flag, `teammateMode: "in-process"`, the documented permissions allow/deny list — see `debate/skills/run-debate/SETTINGS_TEMPLATE.json` or recreate from the project README), then tell the user *"Agent Teams enabled in `.claude/settings.json`. Please restart Claude Code and re-run /run-debate."* and **halt**. For a fresh clone of this repo the flag is already set; this branch never fires.

</section>

<section purpose="Collect every user-controlled knob for the debate in four small batches (ADHD-friendly). Includes optional YouTube enablement with a full API-key walkthrough and persistence guidance, model picks per role, and the per-scientist ingestion knobs.">

## Phase A — collect inputs (4 batches via AskUserQuestion)

Use small batches; the user may have ADHD — keep each batch ≤ 3 questions. Persist answers to `debate_events/<slug>/inputs.json`.

### Phase A opener — freshness check + `/usage` baseline

Before Batch 1, `/run-debate` performs two pre-flight checks:

1. **Freshness check.** `/run-debate` is expected to start in a **fresh VSCode conversation** — the orchestration accumulates context across Phases A/B/C in one cumulative session. If the current conversation has prior user turns (i.e. this is not the first user message), OR if `ls debate_events/` shows an in-progress event-folder without an `inputs.json` `complete: true` flag AND no explicit `--resume <slug>` argument was passed, `AskUserQuestion`:
   > *"This conversation has prior turns / there's an in-progress event at `<slug>`. `/run-debate` runs best in a fresh conversation. Options: (a) Start a fresh conversation (recommended — stop here, open a new VSCode chat, re-invoke `/run-debate`), (b) Resume `<slug>` from where it left off (only if you crashed mid-debate), (c) Force fresh-start anyway in this conversation (accept that prior context will compete for tokens)."*

   On (a): exit cleanly with a one-line *"Please start a fresh conversation."*. On (b): set `RESUME_SLUG=<slug>`, skip Batch 1–4 (read from `inputs.json`), jump to the unfinished phase. On (c): proceed.

2. **`/usage` baseline.** Run `/usage` in this Moderator session and parse the four named fields per role: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. Write `debate_events/<RESUME_SLUG or tbd-slug>/usage_baseline.json` (deferred until after B0 if slug isn't yet known). The end-of-Phase-C `/usage` re-capture computes the Moderator's debate-only delta = now − baseline.

### Phase A batches

- **Batch 1 — required**: scientist A name; scientist B name; scientist C name (Reviewer); one-sentence debate topic.
- **Batch 2 — debate shape + media toggles**: `total_minutes` (default 80); `give_collaborative_tone_to_presenters?` (default *no*); `journalist_word_budget` (default 500–600); `allow_websearch_during_debate?` (default *no*); `include_youtube?` (default *yes* — works out of the box via yt-dlp); `include_books?` (default *yes* — uses OpenAlex + Google Books + Open Library/IA, all free, no key).
  - <section purpose="YouTube works without setup via yt-dlp (zero-config fallback). If the user has YOUTUBE_API_KEY in their env (e.g. set in ~/.claude/settings.json), the script auto-prefers the API backend. Either way, no user action required in Phase A — the dispatch is automatic in search_youtube.py.">YouTube search works out of the box via yt-dlp; no setup needed. If `YOUTUBE_API_KEY` is set in the env (e.g. in `~/.claude/settings.json`), the script automatically prefers the YouTube Data API v3 backend (faster, more reliable, 10 000 free queries/day) — otherwise it transparently falls back to yt-dlp page-scraping. Either way, no Phase A action required: `search_youtube.py` picks the backend itself and prints which one it used to stderr so the user sees it.</section>
  - **Persist Batch 2 answers via Edit to `debate_events/<slug>/inputs.json::ingestion.include_youtube` and `…include_books`** before starting Phase B — the answers control whether `search_youtube.py` and `search_books.py` run.
- **Batch 3 — ingestion**: per-scientist free-text instruction (default = the tier description below); `n_full_papers_cap` (default 25, the maximum Tier-2a full-text papers); `n_tier3_sample` (default 15, the random-sample size for papers that are neither first/last-author nor topic-matching); `custom_sources` (optional per-scientist list — see schema below; includes `type: url` for one-off URLs).
- **Batch 4 — models per role** (5 roles, one AskUserQuestion per role; lists all 4 model IDs as distinct options with `(recommended)` / `(200k budget)` annotation):

  Available model IDs (harness-accepted forms; use exact strings):
  - `claude-opus-4-7[1m]` — Opus 4.7, **1M-token context**. For roles where total prompt plausibly exceeds 180k tokens.
  - `claude-opus-4-7` — Opus 4.7, **200k-token context**. Default for bounded prompts.
  - `claude-sonnet-4-6` — Sonnet 4.6 (200k). Budget pick for procedural / bounded-input roles.
  - `claude-haiku-4-5-20251001` — Haiku 4.5. Reserved for short formulaic prompts; **never recommend for content roles**.

  Per-role recommendations (default + 200k-budget alternative):

  | Role | Default (1M-friendly) | 200k-budget alternative | Rationale |
  |------|-----------------------|--------------------------|-----------|
  | **Moderator** (lead session) | `claude-opus-4-7[1m]` *(recommended)* | `claude-opus-4-7` *(200k budget — risky; cumulative context from briefings + transcript reads exceeds 200k for a default 80-min debate)* | The Moderator runs Phases A/B5/C in one cumulative session; reads transcript regions and prints stage blocks. No longer purely procedural. |
  | **Scientist A** (Presenter A) | `claude-opus-4-7[1m]` *(recommended)* | `claude-opus-4-7` *(200k budget — only if A-side briefing < 150k tokens after B4 sanity check)* | Receives full A-side briefing (200–400k tokens for exhaustive briefing). |
  | **Scientist B** (Presenter B) | `claude-opus-4-7[1m]` *(recommended)* | `claude-opus-4-7` *(200k budget)* | Symmetric to A. |
  | **Scientist C** (Reviewer) | `claude-opus-4-7` *(recommended)* | `claude-sonnet-4-6` *(200k budget)* | Reviewer briefing typically fits in 200k; post-B4 sanity check upgrades to 1M if not. |
  | **Journalist J** | `claude-opus-4-7` *(recommended)* | `claude-sonnet-4-6` *(200k budget)* | Inputs = finished transcript; fits in 200k easily. |

  Run one `AskUserQuestion` per role with all four model IDs as options. Annotate the default as *"(recommended — 1M for full briefing headroom)"* and the 200k fallback as *"(200k budget — see table)"*. Persist to `inputs.json::models.<role>` (`models.Moderator`, `models.A`, `models.B`, `models.C`, `models.J`).

  **Post-B4 briefing-size sanity check** (per §6 step 6.3): after B4 builds the briefings, compute `briefing_tokens_est = word_count × 1.35` for each of A, B, C. If `est > 180_000` AND the picked model is `claude-opus-4-7` (200k), `AskUserQuestion`: *"<role>'s briefing is ~<est:,> tokens (> 180k headroom). Picked variant is 200k. Upgrade to claude-opus-4-7[1m]?"* — accept yes/no. Persist updated pick into `inputs.json::models.<role>`. Skip J — its input is the finalised transcript, bounded by Phase C output.

- **Batch 4.5 — voice picker** (after model picker, before B0): seeds the per-role Kokoro voice assignment used at audio render time. Moderator prints the proposed voice assignment table (6 roles × Kokoro voice — gender-matched scientists first, distinct voices for Moderator / Audience / Journalist) and `AskUserQuestion`: *"Voice assignment: (a) Accept proposed, (b) Edit (type `<role>=<voice>` lines in Other), (c) Suggest alternative gender-matched assignment, (d) Show full Kokoro voice catalogue."* Persist to `debate_events/<slug>/voice_map.json` (deferred until after B0 if slug isn't yet known). Then `bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_audio.py --warmup` — downloads the ~330 MB Kokoro model on first run; fails fast (with the `pip install kokoro soundfile pydub` / `brew install ffmpeg` advice) if missing.

- **Batch 5 — borderline-candidate review mode** (single AskUserQuestion): how to handle YouTube videos / blog posts / books that pass the cheap heuristics but are borderline (multi-speaker interview, surname-only namesake risk, no topic-keyword in title)? Options:
  - **Moderator reads the short list (default, recommended, no extra cost)** — search scripts mark borderline items with `needs_review: true` in the cache JSON; the Moderator scans them as part of B3a / B2b / B2c and either keeps or drops via `Edit`. Works for all three sources.
  - **Skip review entirely** — keep all candidates that pass the cheap filter. Cheapest, lowest precision.
  - **LLM subagent** — Moderator spawns an `Explore` subagent per scientist that reads the borderline list and returns a verdict list. Protects Moderator context, no SDK dependency.
  - **Direct Anthropic SDK call** — pass `--use-llm-filter` to `search_youtube.py` / `search_blogs.py` / `search_books.py`; each script calls Haiku-4.5 itself per borderline item. Requires `ANTHROPIC_API_KEY`. Verdicts cached per item.

  Persist the choice to `debate_events/<slug>/inputs.json::ingestion.review_mode` (`moderator` | `skip` | `subagent` | `api`). At B3a / B2b / B2c the Moderator branches on this value.

**Default ingestion instruction** (the tier description): *"Read this scientist's work in three tiers and stop when you have enough. **Tier 1** — work directly about the debate topic AND by the scientist (papers, blog posts, book chapters, recorded-talk transcripts where they are the speaker). **Tier 2** — first/last-author papers (any topic; full text up to `n_full_papers_cap` / `n_tier2a_full_max`) OR middle-author papers that match the debate topic (abstract only). **Tier 3** — neither first/last-author nor topic-matching: a random seeded sample of `n_tier3_sample` abstracts (default 15)."*

**`custom_sources` schema** (handles uploaded files on claude.ai/code web, local file paths in VSCode/desktop, full directories of e.g. non-OA PDFs, and inline notes):
```jsonc
"custom_sources": {
  "<scientist_name>": [
    {"type": "file",      "path": "papers_cache/manual/uploads/<file>", "tier": 1, "label": "..."},
    {"type": "directory", "path": "<path>",  "glob": "*.pdf",            "tier": 2, "label": "..."},
    {"type": "url",       "url":  "...",                                 "tier": 1, "label": "..."},
    {"type": "note",      "text": "...",                                 "tier": 1, "label": "..."}
  ]
}
```

</section>

<section purpose="All preparation work — folder creation, keyword generation, search, download, briefing assembly, faithfulness-iterated self-intros and talk drafts, and the explicit GO gate that prevents starting the debate without user approval.">

## Phase B — preparation

Run scripts via `bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/<script>.py …`.

**Task-wording convention.** Every instruction sent to a teammate that produces a persistent artefact must use the form *"Persist `<X>` to `<absolute-path>`"* — not "Draft", "Write", or "Generate". The teammate is expected to use the `Write` tool to commit the artefact to the named path before its reply — the reply is a JSON confirmation (per `scientist.md` §Reply contract), not the artefact itself. If a reply contains prose where the file should be, treat it as off-contract: re-send with *"You did not persist to `<path>`. Use the Write tool now."* (cap at 2 retries, then escalate via `AskUserQuestion`).

<section purpose="Create the per-debate working directory with a slug derived from scientists + date + session-id hash; merge Phase A answers into the skeleton inputs.json.">

### B0 — event folder

`new_debate_event.py --scientist_a "<A>" --scientist_b "<B>" --scientist_c "<C>" --topic "<topic>"` creates `debate_events/<A-last>_<B-last>_<YYYY-MM-DD>_<6hash>/` with an `inputs.json` skeleton. Merge Phase A answers into it.

</section>

<section purpose="Source cast affiliations (title, affiliation, notes) via WebSearch with user confirmation, before any briefing fetching begins. Also infer a rough voice-gender guess per scientist (one-shot heuristic; not user-confirmed separately — the user-facing voice decision happens via the voice picker in Phase A). Persists into inputs.json::scientists.<X>.{title, affiliation, notes, voice_gender_guess, sourced} so downstream rendering (§4 compose_full_event.py cast line; §4 voice_map seeding) has structured data instead of ad-hoc prose.">

### B0.5 — cast affiliations + voice-gender guess (WebSearch-confirmed)

After B0 writes the `inputs.json` skeleton and Batch 1 names are merged, and **before** any briefing fetching begins, source each scientist's current affiliation and a rough voice-gender guess. Runs only if WebSearch is enabled (default); otherwise fall back to user-supplied affiliations with `sourced: "user_only"`.

For each scientist in {A, B, C}:

1. `WebSearch` *"<full name> affiliation title current OR most recent"*. Prefer institutional pages over Wikipedia. For deceased scientists, capture dates + the framing *"represented faithfully from his/her published work"*. In the same WebSearch round, also infer a rough **voice-gender guess** — one of `female`, `male`, `nonbinary`, `unknown` — i.e. what would the listener expect them to sound like (transgender accommodation: self-identified gender wins). This is NOT user-confirmed separately; the user-facing decision is the role→voice assignment via the voice picker in Phase A (§4 voice picker — populates `voice_map.json`).

2. Draft a `{title, affiliation, notes, voice_gender_guess}` dict. Surface via `AskUserQuestion`:
   > *"Affiliation for `<name>` — confirm: `<title>, <affiliation>` (notes: `<notes>`). Voice-gender guess: `<guess>`. Options: (a) confirm as-is, (b) edit inline, (c) re-search."*

3. On (c), loop back to step 1 with the user's refinement (ORCID, institution, paper title, etc.).

4. `Edit` `inputs.json::scientists.<X>` to add `{title, affiliation, notes, voice_gender_guess, sourced}`. `sourced` is `"websearch"` if WebSearch ran; `"user_only"` if WebSearch was disabled or returned nothing useful and the user entered by hand.

**Hard rules:**
- Load-bearing structure for `affiliation`: title prefix + department/programme + institution and city. For deceased scientists, `notes` carries dates + faithfulness disclaimer. Examples:
  - Alfonso Martinez Arias — *"ICREA Research Professor, Systems Bioengineering, Universitat Pompeu Fabra, Barcelona"*
  - Eric Davidson — *"Norman Chandler Professor of Cell Biology, Caltech, 1937–2015; represented faithfully from his published work"*
  - James Briscoe — *"Principal Group Leader, Francis Crick Institute; Editor-in-Chief, Development"*
- WebSearch runs by default; the only way to skip is if the user explicitly disabled the WebSearch toggle in Phase A.
- Re-runs on the same slug short-circuit if all three scientists already have non-null `title`+`affiliation` and `sourced != null`. Print *"Cast affiliations already sourced; skipping WebSearch."*

</section>

<section purpose="Convert the topic into a structured search-keyword set (primary, synonyms, opposing, publication types). The Moderator drafts (LLM domain knowledge), the user confirms, the script persists — a single source of truth for what was searched.">

### B1 — keywords

Before calling `generate_search_keywords.py`, **you** (the Moderator) think out loud and generate the keyword set: `primary_terms`, `synonyms`, `opposing_terms`, plus `publication_types: ["editorial", "letter", "commentary", "opinion", "review", "news"]`. Then ask the user (one `AskUserQuestion`) to confirm or amend. Persist the final set by invoking `generate_search_keywords.py --topic "<topic>" --out debate_events/<slug>/keywords.json --primary "<csv>" --synonyms "<csv>" --opposing "<csv>"`.

</section>

<section purpose="Parallel per-source metadata searches: papers via PMC + OpenAlex, blogs via WebSearch + AskUserQuestion + registry, books via OpenAlex + Google Books (if include_books), YouTube only if include_youtube. All searches mirror the tier model: Tier 1 = author AND topic.">

### B2 — search

For each scientist run **in parallel where possible**. **Pass `{author}` / `{scientist}` literally in the `--out` path** — the scripts auto-substitute the canonical slug (lowercase, dash-separated). Do NOT pre-compute a slug yourself; the script's substitution is the source of truth that `build_briefing.py` later reads from.

**B2a — papers** (always runs):
- `search_works.py --author "<NAME>" --keywords debate_events/<slug>/keywords.json --tier all --out 'papers_cache/works/{author}.json'`

**B2b — blogs** (Moderator-driven discovery + AskUserQuestion confirmation):
1. For each scientist, WebSearch: `"<scientist>" blog OR substack OR wordpress OR personal-site`.
2. Also consult `debate/blog_registry.yaml` for already-known blogs by this scientist.
3. Present the union of candidate URLs via `AskUserQuestion` (multiSelect): *"Which blog URLs to crawl for `<scientist>`? (Select multiple, or skip.)"*.
4. For each confirmed URL, invoke:
   ```
   search_blogs.py --scientist "<NAME>" --urls "u1,u2,..." \
     --keywords debate_events/<slug>/keywords.json \
     --out 'papers_cache/blogs/{scientist}.json'
   ```
5. If the user skipped all candidates, write an empty result file so build_briefing can proceed:
   ```
   search_blogs.py --scientist "<NAME>" --urls "" --keywords ... --out '...'
   ```

**B2c — books** (only if `inputs.json::ingestion.include_books == true`):
```
search_books.py --scientist "<NAME>" \
  --keywords debate_events/<slug>/keywords.json \
  --works 'papers_cache/works/{author}.json' \
  --out 'papers_cache/books/{scientist}.json'
```
Merges OpenAlex book records (already pulled in B2a) with Google Books metadata; emits per-book records tagged with tier and access metadata.

**B2d — YouTube** (only if `inputs.json::ingestion.include_youtube == true`):
```
search_youtube.py --scientist "<NAME>" \
  --keywords debate_events/<slug>/keywords.json \
  --out 'papers_cache/youtube_search/{scientist}.json'
```
Auto-picks backend (API v3 if `YOUTUBE_API_KEY` set, yt-dlp otherwise) and prints the chosen backend to stderr — surface it in the conversation. The strict speaker filter (channel/title/description) drops third-party talks that merely mention the scientist's name.

</section>

<section purpose="Per-scientist Moderator-driven video confirmation: present strict-filter results, user multi-selects which transcripts to fetch, flip user_confirmed=true on the JSON, THEN invoke fetch_fulltext for transcript download. Without this step every transcript is skipped (fetch_fulltext gates on user_confirmed).">

### B3a — video confirmation (only if `include_youtube == true`)

After `search_youtube.py` writes `papers_cache/youtube_search/<slug>.json`:
1. Read the file and group results by scientist.
2. For each scientist, present candidate videos to the user via `AskUserQuestion` (multiSelect; batch in groups of 4 if more than 4 candidates):
   *"Which YouTube videos for `<scientist>` to fetch transcripts for?
    Each entry: `<title> | <channel> | tier <T> | <url>`.
    Picking 'none' skips all transcripts for this scientist."*
3. For each user-confirmed video, mutate `papers_cache/youtube_search/<slug>.json` via Edit: set `"user_confirmed": true` on the matching records.
4. Only then proceed to B3 fetch (the gate at `fetch_fulltext.py` skips records where `user_confirmed=False`).

</section>

<section purpose="Cache-aware full-text download dispatcher: PMC XML, bioRxiv PDF, web pages, YouTube transcripts (user-confirmed only), books (Open Library/IA, fall back to Google Books snippets), plus custom_sources. Custom sources of type=url are read from inputs.json directly.">

### B3 — fetch full text

```
fetch_fulltext.py \
  --works 'papers_cache/works/{author}.json' \
  --blogs 'papers_cache/blogs/{scientist}.json' \
  --youtube 'papers_cache/youtube_search/{scientist}.json' \
  --books 'papers_cache/books/{scientist}.json' \
  --inputs debate_events/<slug>/inputs.json \
  --out-dir papers_cache/
```

The `--inputs` flag is how `custom_sources` is read (the script consumes `inputs.json::ingestion.custom_sources`); there is no separate `--custom-sources` flag. URLs to pre-fetch outside `custom_sources` are not supported in this version — add them as `custom_sources: type: url` entries instead.

Already-cached items skip silently. For custom-source `type: url` entries pointing at new domains, `AskUserQuestion` once per new domain before fetching.

</section>

<section purpose="Per-scientist briefing assembly under user caps. Two-round interactive budget gate: Round 1 surfaces tier-2a overflow (n_full_papers_cap exceeded); Round 2 surfaces global-cap overflow. Each round offers summarise / reduce / drop with explicit cost and coverage trade-offs.">

### B4 — briefings (interactive budget gate)

Run `build_briefing.py --inputs debate_events/<slug>/inputs.json --out debate_events/<slug>/` once. It produces `briefing_<scientist>.md` × 3 + `manifest.json`. Then inspect the side-effect output files:

**Round 1 — Tier-2a overflow** (only if `needs_summary.json` appears):

Semantics: `needs_summary.json` lists tier-2a (first/last-author) full texts beyond `n_full_papers_cap` / `n_tier2a_full_max`. AskUserQuestion:
*"Tier-2a (first/last-author) for `<scientist>` has N sources beyond `n_full_papers_cap`. Pick:
  A) Summarise the N over-cap sources via /summarise-for-debate (paid LLM calls)
  B) Drop the over-cap sources (keep their abstracts only — cheapest)
  C) Raise `n_full_papers_cap` (currently 25)"*

- If A: invoke `/summarise-for-debate` once per path in `needs_summary.json` (`--model haiku` default; user can pick Sonnet/Opus, see Round 2 model picker). Re-run `build_briefing.py`.
- If B: append the over-cap source IDs (from `needs_summary.json`) to `inputs.json::ingestion.dropped_source_ids[scientist]` via Edit. Re-run `build_briefing.py`.
- If C: Edit `inputs.json::ingestion.n_full_papers_cap`. Re-run.

**Round 2 — Global cap overflow** (only if `needs_user_decision.json` appears after Round 1):

Semantics: `needs_user_decision.json` lists scientists whose briefing still exceeds `global_briefing_word_cap` (default 80 000 words). AskUserQuestion:
*"Briefing for `<scientist>` is N words over the global cap (default 80k). Pick:
  A) Summarise over-budget sources via /summarise-for-debate
  B) Reduce tier sizes (cheaper, less coverage — per-tier knobs prompted next)
  C) Drop specific sources by ID (multi-select from the worst offenders)"*

- If A: AskUserQuestion *"Model for summarisation? Haiku (fast, cheap; recommended for mechanical summaries) / Sonnet (balanced) / Opus (highest quality)"*. For each source in `needs_summary.json` (or top-N by word-count if `needs_user_decision.json` doesn't enumerate sources, pick the longest tier-2 / tier-3 entries from the briefing first), invoke `/summarise-for-debate --model <chosen> --source-path <path> --topic "<topic>" --scientist "<name>" --target-words 500`. Re-run `build_briefing.py`.
- If B: three AskUserQuestion (one per tier):
  - *"Tier 1 max papers? (default `null` = unlimited. **Warning: dropping Tier 1 drops topic-direct sources — your scientist agent loses the most-relevant material.**)"*
  - *"Tier 2a max full-text papers? (default 25)"*
  - *"Tier 3 random sample size? (default 15)"*
  - Edit `inputs.json::ingestion.{n_tier1_max, n_tier2a_full_max, n_tier3_sample}`. Re-run `build_briefing.py`.
- If C: present the top-N over-budget sources (by word count, from the briefing) via AskUserQuestion (multiSelect). Append selected source IDs to `inputs.json::ingestion.dropped_source_ids[scientist]`. Re-run.

**Loop Round 2 up to 3 times.** If briefing still exceeds the cap after 3 rounds, surface the absolute word count and AskUserQuestion *"Your scientist agent's context will be tight (Opus is 200k tokens ≈ 150k words). Proceed anyway?"*. **Tier 1 is never dropped automatically — only via explicit user setting of `n_tier1_max` (option B) or option C.**

</section>

<section purpose="Post-B4 briefing-size sanity check. If any scientist's briefing exceeds the 180k-token headroom AND the user picked the 200k-context model variant in Batch 4, prompt to upgrade to the 1M variant. Catches model/briefing-size mismatches before they crash the debate.">

### B4.5 — briefing-size sanity check vs picked model

After B4 completes (all three briefings exist on disk), compute per-scientist briefing-token estimate `briefing_tokens_est = word_count × 1.35` (whitespace-split word count across all briefing artefacts a teammate will receive at spawn). Write to `debate_events/<slug>/briefing_size_check.json`:

```jsonc
{"A": {"words": 142000, "tokens_est": 191700, "model_picked": "claude-opus-4-7", "needs_upgrade": true},
 "B": {"words": 88000,  "tokens_est": 118800, "model_picked": "claude-opus-4-7[1m]", "needs_upgrade": false},
 "C": {"words": 32000,  "tokens_est": 43200,  "model_picked": "claude-opus-4-7", "needs_upgrade": false}}
```

`needs_upgrade = (tokens_est > 180_000) AND (model_picked == "claude-opus-4-7")`. The 180k threshold leaves ~20k headroom for skill text + scratch space + tool-result inflation.

For each role where `needs_upgrade == true`: `AskUserQuestion` *"`<role>`'s briefing is ~`<est:,>` tokens (> 180k headroom). Picked variant is 200k (`claude-opus-4-7`). Upgrade to `claude-opus-4-7[1m]` (1M)?"* — yes / no / drop sources further.

On yes: `Edit` `inputs.json::models.<role>` to `claude-opus-4-7[1m]`. On no: warn user that the teammate may truncate context silently. On drop-further: jump back to B4 Round 2 with `dropped_source_ids` editing.

Journalist `J` excluded — its input is the finalised transcript, bounded by Phase C output.

</section>

<section purpose="Single team-creation point. Spawn the three scientist teammates ONCE for the entire debate. The same teammate objects persist through B5a, B5b, and every stage of Phase C. Handshake-verify identity, then write team.json as the single source of truth for slot ↔ surname ↔ briefing.">

### B5_pre — spawn scientist team (single creation point)

After B4 completes (briefings exist on disk), create the three scientist teammates **once** for the entire debate. The same teammate objects persist through B5a (self-intro), B5b (talk prep), and every stage of Phase C.

Use ONE natural-language create-team instruction to the Agent Teams layer. The teammate `name` field is the scientist's **surname** (so `SendMessage({to: "Martinez Arias", ...})` is the routing call); the `team_name` is the event slug (same identifier as `debate_events/<slug>/` folder name — one identifier, no separate construction). Render the pairings on separate lines so they cannot scramble:

> *"Create an agent team named `<slug>` (the event-folder slug, e.g. `ariasA_davidsonB_2026-05-26_c7893c`). Spawn three scientist teammates (`scientist` agent type). Do NOT inherit my model. Use these exact pairings — each row is one teammate:*
>
> *- name: `<surname of A>` ⟶ slot A, model `<model_for_A from inputs.json>`, briefing `debate_events/<slug>/briefing_A.md`*
> *- name: `<surname of B>` ⟶ slot B, model `<model_for_B>`, briefing `debate_events/<slug>/briefing_B.md`*
> *- name: `<surname of C>` ⟶ slot C, model `<model_for_C>`, briefing `debate_events/<slug>/briefing_C.md`*
>
> *The `name` field is the surname (one or two words, no titles, no first names) — stable for the entire debate, no phase suffix. File naming inside `debate_events/<slug>/` continues to use the slot letter (`briefing_A.md`, `intro_A.md`, `talk_A.md`, `stage_03_A.md`) — only the routing handle uses the surname. WebSearch is `{enabled|disabled}` for this debate."*

Then send each teammate a one-shot handshake message:

> *"Handshake. Reply with exactly this JSON on a single line, nothing else:*
> *`{"name":"<your name>","slot":"<your slot letter>","scientist_name":"<the real name you understand yourself to represent>","briefing_path":"<the path you were given>"}`"*

Parse each reply. **Verify** that `name` matches the surname you assigned, `slot` ∈ {A, B, C}, `scientist_name` matches `inputs.json::scientists.<slot>.name`, and `briefing_path` matches `debate_events/<slug>/briefing_<slot>.md`. If any mismatch: surface to user, ask Agent Teams layer to clean up the team, re-spawn from the top of B5_pre.

On all-confirm, write `debate_events/<slug>/team.json`:

```jsonc
{
  "team_name": "<slug>",
  "A": {
    "name": "<surname>",
    "scientist_name": "<full name from inputs.json>",
    "briefing_path": "debate_events/<slug>/briefing_A.md",
    "identity_confirmed": true,
    "model": "<model id, populated from inputs.json:models[A]>",
    "voice": "<kokoro voice id from voice_map.json — populated by §4 voice picker>"
  },
  "B": { /* same shape, slot B */ },
  "C": { /* same shape, slot C */ }
}
```

`team.json` is the single source of truth for every subsequent stage that addresses a teammate by surname. Do NOT pass `briefing_path` again in later prompts — the teammate already has it and already confirmed it.

</section>

<section purpose="Each scientist (A, B, C) writes a self-introduction grounded in their briefing; the assess-transcript-faithfulness skill critiques each draft; 3 iterations or pass-early. Goal: catch generic-LLM voice before the debate starts.">

### B5a — self-intros (scientist self-iterates, 3 iterations or pass-early)

For each of A, B, C: address the scientist teammate spawned in B5_pre by their **surname** (`SendMessage({to: "<surname>", ...})`; mapping from slot letter → surname lives in `debate_events/<slug>/team.json`). Send a single instruction:

> *"Briefing at `debate_events/<slug>/briefing_<X>.md`. Write a 300–1000 word self-introduction covering (a) who you are and how you got here, (b) your view on the debate topic. Per `scientist.md` §Self-assessment + self-persistence, iterate up to 3 times: each iteration save `intro_<X>_draft<N>.md`, self-invoke `/assess-transcript-faithfulness`, revise. When you pass or reach draft 3, also save to `intro_<X>.md`. Reply with JSON only per `scientist.md` §Reply contract."*

Parse the JSON reply (single-line; keys `stage_id`, `file_path`, `word_count`, `faithfulness`, `iteration`, optional `top_issues`). Verify the canonical file exists by `Read`-ing the `file_path` from the JSON. Do NOT read the draft files. Do NOT invoke `/assess-transcript-faithfulness` yourself — the skill description forbids Moderator invocation.

If the reply has `faithfulness: "fail_after_3"`, record the `top_issues` in Moderator memory and surface a warning at the B6 review gate so the user can choose to re-iterate manually or proceed.

</section>

<section purpose="Talk preparation for A and B only (C doesn't present): three-iteration length-reduction shape from 2× target down to target, with faithfulness pass at each step. Stage 1 / 2 in Phase C then deliver this prepared text near-verbatim.">

### B5b — talk preparation (scientist self-iterates, A and B only)

Compute `talk_target = stage-1/2 word budget` (1500 at default `total_minutes=80`; scales as `1500 × total_minutes / 80`). For each of A, B, address the teammate by surname and send a single instruction:

> *"Briefing at `debate_events/<slug>/briefing_<X>.md`. Prepare your stage-1/2 talk in three iterations, per `scientist.md` §Self-assessment:
> - Draft 1 (~2× target, ~{2 × talk_target} words): expansive — cover all arguments and evidence. Save as `talk_<X>_draft1.md`, self-assess, revise.
> - Draft 2 (≈ {talk_target} words): cut to target, keep most-essential argument. Save as `talk_<X>_draft2.md`, self-assess, revise.
> - Draft 3 (target ±10%): final polish. Save as `talk_<X>_draft3.md`, self-assess.
>
> When draft 3 passes (or after the third self-assessment regardless), also save the final text to `talk_<X>.md`. Reply with JSON only per `scientist.md` §Reply contract."*

Verify `talk_<X>.md` exists for both A and B by `Read`-ing the `file_path` from each JSON reply. Do NOT read its content. Stages 1 and 2 in Phase C deliver this text near-verbatim (the scientist re-reads its own file then).

If a reply has `faithfulness: "fail_after_3"`, surface a warning at the B6 review gate alongside the B5a flag.

</section>

<section purpose="Hard sync point. Show the user what was prepared (per-tier counts incl. 2a/2b split and books/transcripts, sample titles, intros, talks) and wait for an explicit GO. Cheap insurance against a 60-minute debate launched on bad inputs.">

### B6 — review gate

Read `debate_events/<slug>/manifest.json` for the actual counts (don't fabricate them). For each scientist, display:

```
<Scientist real name>
  Tier 1 (topic-direct): X papers (Y with full text), B1 blogs, V1 transcripts, K1 books
  Tier 2a (first/last-author, any topic): X full-text kept (of Z eligible) / N flagged for summary
  Tier 2b (middle-author, topic-relevant abstracts): X papers
  Tier 3 (random sample): X of Z total
  Books: tier1=K1, tier2=K2 (with-text=W)
  Custom sources: N
  Briefing word count: W
```

Then show 5 sample titles per tier per scientist, the final intros, the final talks. `AskUserQuestion` *"Confirm to start the debate, or amend?"*. **Wait for an explicit "GO"** — do not start stages without it.

</section>

</section>

<section purpose="The live debate: team spawn with per-role model overrides, the 10-stage sequence with audience break-points, the journalist write-up, and end-of-debate cost accounting before clean-up.">

## Phase C — orchestrate the debate

**Task-wording convention (Phase C).** Same as Phase B: every per-teammate instruction that produces a persistent artefact uses *"Persist `<X>` to `<absolute-path>`"* — naming the exact per-stage file path. The teammate writes the file via the `Write` tool and replies with the JSON contract from `scientist.md` §Reply contract. If the reply violates the contract (prose where the file should be, missing JSON, malformed JSON, or `word_count` not an int): re-prompt up to 2× with original instruction prepended by *"Your previous reply did not match the JSON contract — reply per `scientist.md` §Reply contract"*; after 2 retries, `AskUserQuestion` surfacing the bad reply verbatim.

<section purpose="Spawn the agent team in one natural-language instruction; lock per-role model picks (teammates do not inherit lead model); materialise the stage table as TODOs so the user sees progress.">

### C0 — spawn journalist + stage TODOs

Once the user says GO:

1. Materialise the [FORMAT.md stage table](../../FORMAT.md#stage-table) as TODOs so progress is visible. **Include the 4 clarifying-question rounds (after stages 1, 2, 3, 5) as intra-stage sub-TODOs** per FORMAT.md §Clarifying-question rounds — these are not separate stages but intra-stage micro-steps.

2. Confirm `debate_events/<slug>/team.json` exists with A/B/C entries (created in B5_pre) and `team_name = <slug>`. If absent, halt and surface a Moderator-bug error — B5_pre should have written it.

3. Spawn the journalist teammate **into the same team** (`team_name: <slug>`). Give it `name: "Journalist"` (literal surname-slot string), model from inputs.json Batch 4 (`models.J`). Do NOT respawn A/B/C — they already exist and carry the intro + talk context built up in B5a/B5b.

4. Handshake the journalist:

   > *"Handshake. Reply with exactly this JSON on a single line:*
   > *`{"name":"Journalist","slot":"J","role":"journalist"}`"*

5. On confirm, `Edit` `debate_events/<slug>/team.json` to append the `J` entry (slot-letter key `J`, `name: "Journalist"`, `scientist_name: null`, `briefing_path: null`, `identity_confirmed: true`, `model: <id>`, `voice: <kokoro voice from voice_map.json>`). On mismatch: respawn `J` only — do not touch the scientist teammates.

</section>

<section purpose="Seed transcript.md from intros + team.json. Initialise audience.log as empty. compose_transcript.py builds the structure compose_full_event.py later expects, so the live transcript is consistent from the first stage concatenation.">

### C0c — seed transcript.md and audience.log

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/compose_transcript.py \
  --event-dir "debate_events/<slug>/"
```

The script reads `inputs.json` (topic, scientists), `team.json` (slot → surname mapping), `intro_<A>.md`, `intro_<B>.md`, `intro_<C>.md`, and writes:

- `debate_events/<slug>/transcript.md` seeded with: H1 `# <topic>`, `## Self-introductions` with three `### <surname> (Presenter A|B|Reviewer)` subsections (body verbatim from each `intro_<X>.md`), Moderator welcome line, empty `## The debate` heading (ready for Phase C1 concatenations).
- `debate_events/<slug>/audience.log` as an empty file (so `compose_full_event.py` at C4 never faces a missing-file edge case).

Defaults to skip-if-exists; pass `--force` to clobber (rare — used when re-seeding after a mid-debate restart).

After this step, initialise the Moderator's in-memory `last_read_line[<X>]` map: for each of A, B, C, set `last_read_line[<X>] = wc -l debate_events/<slug>/transcript.md` (the line count after seed). Each scientist's first SendMessage in Phase C1 will name `last_read_line[<X>] + 1` as the offset.

</section>

<section purpose="The 10 debate stages. Stages 1 and 2 deliver prepared talks (per-stage main files). Stages 3–10 are live exchanges, with intra-stage clarifying-question rounds after 1, 2, 3, 5 (per FORMAT.md §Clarifying-question rounds), and dual-speaker sub-stages 8a/8b + 10a/10b (per FORMAT.md). Each utterance writes its own per-stage file; Moderator concatenates into transcript.md and prints to chat; audience breaks fire after FORMAT.md break-point stages; per-break audio segments rendered to clickable mp3 paths.">

### C1 — stages 1–10 (per-stage files, JSON contract, segmented reads, clarifying rounds, dual sub-stages, per-break audio)

**Mandatory per-stage sequence** (no reordering). For each main stage (and each clarifying sub-step and audience-response):

1. **SendMessage** to the relevant teammate by surname, per template below (segmented offset + per-stage file path + JSON contract).
2. **Parse JSON reply** (single-line, `{stage_id, file_path, word_count}` per `scientist.md` §Reply contract). On parse failure / missing file / `word_count` not int: re-prompt up to 2× with original instruction prepended by *"Your previous reply did not match the JSON contract — reply per `scientist.md` §Reply contract"*; after 2 retries, `AskUserQuestion` surfacing the bad reply.
3. **Read the per-stage file** at `file_path`. This is the Moderator's first sight of the content.
4. **Concatenate into `transcript.md`** (Moderator-owned write):
   - Main stage: append `## Stage <NN> — <FORMAT.md title> (<speaker surname>)\n<speaker surname>: <body>\n\n` (use `### Stage 8a/8b/10a/10b — …` for dual sub-stages).
   - Clarifying Q: append `**<asker surname> → <speaker surname> (clarifying):** <body>\n\n`.
   - Clarifying A: append `<speaker surname> (responding to <asker surname>): <body>\n\n`.
   - Audience-response: append `<target surname> (responding to audience): <body>\n\n`.
5. **Print the new transcript region to chat** as formatted markdown — H2/H3 heading + body — directly readable by the user. Never re-print earlier stages.
6. **Update `last_read_line[<X>]`** for every teammate whose transcript region just grew → current EOF (Moderator memory only, not persisted).
7. **At audience break-points** (after stages 1, 2, 4, 6, 7, 8, 9, 10 per FORMAT.md): render the per-break audio segment immediately:

   ```bash
   bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_audio.py \
     --event-dir "debate_events/<slug>/" --segment <NN>
   ```

   Print the resulting clickable path to chat: `**Audio:** [audio_break_<NN>.mp3](debate_events/<slug>/audio_break_<NN>.mp3) (click to play)`. THEN proceed to C2 audience break.

**Per-stage SendMessage templates** (omit the surrounding `*"..."*` quotes in the actual SendMessage body; they're just formatting markers here):

*Stages 1 and 2 (deliver prepared talk — main):*

> *"Stage `<1|2>` (main). Deliver your prepared opening at `debate_events/<slug>/talk_<X>.md` (re-read it now; minor adjustments allowed). Word target `<target>` (truthful — overruns OK, we don't truncate). Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<X>]+1>` to EOF first. Persist your stage to `debate_events/<slug>/stage_<NN>_<X>.md` via the `Write` tool. Reply JSON per `scientist.md` §Reply contract."*

*Stages 3, 4, 5, 6, 7, 9 (single-speaker, live exchange):*

> *"Stage `<N>` as `<Presenter|Opponent|Reviewer>`. Word target `<target>` (scaled by `total_minutes / 80`, per FORMAT.md). Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<X>]+1>` to EOF. Persist your stage to `debate_events/<slug>/stage_<NN>_<X>.md`. Reply JSON."*

*Stages 8a, 8b, 10a, 10b (dual-speaker sub-stages per FORMAT.md):*

> *"Stage `<NNa|NNb>` (final rejoinder, sub-stage). Word target 400 (scaled). Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<X>]+1>` to EOF. Persist to `debate_events/<slug>/stage_<NNsub>_<X>.md` (e.g. `stage_08a_A.md`). Reply JSON."*

For the pair (e.g. 8a then 8b): run sub-stage 8a fully (steps 1–6), then sub-stage 8b. 8b's scientist's `last_read_line[B]+1` is computed AFTER the Moderator concatenated 8a, so B reads A's rejoinder before composing — real-room order. The single audience break fires only after the pair (per FORMAT.md break-point list `1, 2, 4, 6, 7, 8, 9, 10` — break is after `8`, i.e. after 8b, not between 8a and 8b).

**Clarifying-question rounds (after stages 1, 2, 3, 5, per FORMAT.md §Clarifying-question rounds).** These are intra-stage; no audience break inside.

Identify the round's speaker — whoever just wrote the main stage:
- Stage 1: speaker A (delivered the talk).
- Stage 2: speaker B.
- Stage 3: speaker B (Opponent who just critiqued A).
- Stage 5: speaker A (Opponent who just critiqued B).

Identify the two non-speakers (askers), in alphabetical slot order:
- Speaker A → askers B then C.
- Speaker B → askers A then C.

Run four micro-utterances sequentially: **q1** (first asker → speaker) → **a1** (speaker → first asker) → **q2** (second asker → speaker) → **a2** (speaker → second asker). Each one is a full per-stage sequence (steps 1–6 above; no audio render between micros).

*Clarifying-Q template (asker):*

> *"Clarifying Q (≤30 words) to `<speaker surname>` about Stage `<NN>` — what would you ask if you were in the room? Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<asker>]+1>` to EOF. Persist to `debate_events/<slug>/stage_<NN>_q<n>_<asker>.md`. Reply JSON."*

*Clarifying-A template (speaker):*

> *"Answer `<asker surname>`'s clarifying Q (≤50 words) — the question is the last block in the transcript. Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<speaker>]+1>` to EOF. Persist to `debate_events/<slug>/stage_<NN>_a<n>_<speaker>.md`. Reply JSON."*

After all four micros complete: proceed to the audience break-point IF the stage has one (stages 1, 2 do; stages 3, 5 do not, per FORMAT.md).

**Word-target leniency reminder (decision #22).** The Moderator does NOT truncate overruns. If a scientist returns 67 words instead of 50 for a clarifying answer, accept it. The slack is implicit and Moderator-side; scientists see only the target.

</section>

<section purpose="Audience interjection points between resolved exchanges (never mid-pair). User can ask, comment, or 'continue'; non-continue messages are logged and forwarded to the relevant teammate(s) before proceeding.">

### C2 — audience break-points

After stages **1, 2, 4, 6, 7, 8, 9, 10** (per FORMAT.md), and AFTER the Moderator has printed the new transcript region to chat AND rendered + linked the per-break audio segment (`audio_break_<NN>.mp3` — see §C1), fire `AskUserQuestion` *"Audience question, comment, or 'continue'?"*. Default audience time = ~3 min = ~300 words.

If the reply is `continue` (or empty): proceed to next stage.

If the reply is non-`continue`, run the audience round (double-write + multi-target forward):

1. `AskUserQuestion` follow-up: *"Forward to: A only / B only / C only / all"* — captures `forwarded_to` as a list of slot letters (one or more of `A`/`B`/`C`).

2. **Double-write the audience text** (decision #20):
   - **(a)** Append one JSONL line to `debate_events/<slug>/audience.log` capturing the question metadata:
     ```bash
     bash scripts/helper_scripts/run_conda_bash.sh -- bash -c "printf '%s\n' \"\$(jq -c -n \
       --argjson after_stage \"$STAGE_NUM\" \
       --arg text \"$USER_TEXT\" \
       --argjson forwarded_to \"$FORWARDED_JSON\" \
       --arg timestamp_iso \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\" \
       '{after_stage: \$after_stage, text: \$text, forwarded_to: \$forwarded_to, timestamp_iso: \$timestamp_iso}')\" >> debate_events/<slug>/audience.log"
     ```
     (Fall back to a Python one-liner via `run_python_cmd.sh` if `jq` unavailable.)
   - **(b)** Concatenate `**Audience:** <verbatim>\n\n` into `transcript.md` at the current clock stage (Moderator-owned write; scientists never touch transcript.md per §3 contract).

3. **Sequential multi-target forwarding** (decision #15) — for each target in `forwarded_to`, in alphabetical slot order (A → B → C):
   - Look up the target's surname in `team.json`.
   - SendMessage to that teammate:
     > *"Audience question after Stage `<N>`: `<verbatim>`. Read `debate_events/<slug>/transcript.md` from line `<last_read_line[<target>]+1>` to EOF (you'll see the audience question and any prior targets' responses). Persist your response to `debate_events/<slug>/audience_q<NN>_<target>.md`. Word budget: ≤500. Reply JSON per `scientist.md` §Reply contract."*
   - Parse the JSON reply, `Read` the per-stage file, concatenate `<target surname> (responding to audience): <body>\n\n` into `transcript.md`, update `last_read_line[<target>]` = current EOF, print to chat.
   - The next target in `forwarded_to` then reads transcript.md including the prior target's just-concatenated response — real-room order.

4. **Re-render the audio segment** to include the audience round (overwrite `audio_break_<NN>.mp3`): `bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_audio.py --event-dir debate_events/<slug>/ --segment <NN>`. Print the updated clickable path.

5. Proceed to the next stage.

`audience.log` is initialised empty at C0c (alongside `transcript.md` seeding by `compose_transcript.py`) so downstream readers (`compose_full_event.py`) never face a missing-file edge case — zero interjections is just an empty file.

</section>

<section purpose="Journalist writes three audience-tiered Nature-News-and-Views-style summaries from the full transcript. Output is the user-visible artefact (three .md files).">

### C3 — journalist (three articles)

After stage 10, send the Journalist a single instruction that produces all three articles in one go:

```
Read `debate_events/<slug>/transcript.md` and `debate/JOURNALISM.md`.
Produce three articles targeting different audiences:
  1. `article_same_field.md`     — for scientists in the same field
  2. `article_broader_field.md`  — for scientists in adjacent fields
  3. `article_general_stem.md`   — for STEM-educated readers without field background
Word budget per article: {journalist_word_budget}. Apply Nature News-and-Views
structure (lede / setup / body alternating perspectives / what would change /
close on most-productive remaining disagreement). Never invent quotes — every
quoted phrase must appear verbatim in `transcript.md`. Watch for the
`⚠ MULTI-SPEAKER SOURCE` marker on briefing entries the debate drew on:
paraphrase rather than quote when you can't confidently attribute.
After writing all three files, append a `Journalist: wrote 3 articles to ...`
summary line to `transcript.md` so downstream tooling can find them.
```

</section>

<section purpose="End-of-debate close-out: token accounting via /usage baseline/delta (Moderator) + summed task-notification blocks (teammates), per-role named-field schema; compose full debate markdown + HTML; concatenate audio segments into final recording; package zips; cleanup.">

### C4 — close-out (token accounting + final artifacts + cleanup)

**Step 1 — token accounting (`/usage` delta + per-teammate summation, per §6).**

1a. Run `/usage` in the Moderator session. Parse the four named fields: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. Compute the Moderator's debate-only delta = now − `usage_baseline.json` (captured at start of Phase A per the freshness-check step).

1b. For each teammate (A, B, C, J): the Moderator has been accumulating per-notification `usage` blocks in memory throughout the debate (one update per scientist response since B5_pre, one for J's response in C3). The four named fields are summed per teammate. Do NOT collapse into a bare `total`.

1c. Write `debate_events/<slug>/usage.json` with this exact schema (no `total_tokens` / `tokens_cumulative` / bare `tokens` fields):

```jsonc
{
  "Moderator": {
    "input_tokens": <int>,
    "output_tokens": <int>,
    "cache_read_input_tokens": <int>,
    "cache_creation_input_tokens": <int>,
    "model": "<id from inputs.json::models.Moderator>",
    "source": "lead session /usage before-after delta"
  },
  "A": {
    "input_tokens": <int>,
    "output_tokens": <int>,
    "cache_read_input_tokens": <int>,
    "cache_creation_input_tokens": <int>,
    "model": "<id>",
    "scientist_name": "<surname from team.json>",
    "source": "task-notification stream sum"
  },
  "B": { /* same shape as A */ },
  "C": { /* same shape as A */ },
  "J": { /* same shape as A, scientist_name: null */ }
}
```

Lint after write: `grep -E 'total_tokens|tokens_cumulative|^[[:space:]]*"tokens"' debate_events/<slug>/usage.json` MUST match nothing. If it matches, abort close-out and surface a Moderator-bug error.

**Step 2 — compose full debate markdown.**

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/compose_full_event.py \
  --event-dir "debate_events/<slug>/"
```

Produces `debate_events/<slug>/full_debate.md` — H1 title + topic + cast line + narrative Format paragraph + Format table + Contents/TOC + Self-introductions + The debate (10 stages as H3) + Journalist's write-up.

**Step 3 — render HTML.**

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_html.py \
  --inputs "debate_events/<slug>/article_same_field.md,debate_events/<slug>/article_broader_field.md,debate_events/<slug>/article_general_stem.md,debate_events/<slug>/transcript.md,debate_events/<slug>/full_debate.md"
```

Produces 5 HTMLs in the event folder.

**Step 4 — finalise audio.**

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/render_audio.py \
  --event-dir "debate_events/<slug>/" --final
```

Concatenates `audio_break_<NN>.mp3` segments (rendered incrementally during C1/C2 per decision #16) with the spoken disclaimer + filled methodology template + journalist articles audio → `debate_events/<slug>/recording.mp3` (96 kbps mp3 ≈ 57 MB for an 80-min debate). Also updates `recording.timings.json`. ~30–60 s with the per-segment files already on disk.

**Step 5 — package zips.**

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/package_outputs.py \
  --event-dir "debate_events/<slug>/"
```

Two zips land in the event folder: `<slug>_highlights.zip` (small, ready to share — articles + transcript + full_debate + audience log + manifest + usage + recording) and `<slug>_full.zip` (entire event folder for archival).

**Step 6 — print cost summary to chat (per §6 step 6.9).**

Print a table where every numeric column is labelled with its kind. Acceptable column labels: `input`, `output`, `cache-read`, `cache-creation`. Unacceptable: `tokens`, `total`, `cumulative`. Include the `model` column per row.

| Role | model | input | output | cache-read | cache-creation |
|------|-------|-------|--------|------------|-----------------|
| Moderator | claude-opus-4-7[1m] | … | … | … | … |
| A (`<surname>`) | claude-opus-4-7[1m] | … | … | … | … |
| B (`<surname>`) | claude-opus-4-7[1m] | … | … | … | … |
| C (`<surname>`) | claude-opus-4-7 | … | … | … | … |
| J (Journalist) | claude-opus-4-7 | … | … | … | … |

**Step 7 — surface outputs to user.**

`AskUserQuestion`: *"Outputs ready in `debate_events/<slug>/`. What would you like? A) preview articles in browser (open the three .html files), B) preview full_debate.html (combined event), C) play recording.mp3, D) download the highlights zip, E) download the full event zip, F) all of the above."* Surface absolute paths so the file explorer / browser open works on local Claude Code; on claude.ai/code (web) the user must download before the sandbox expires.

**Step 8 — cleanup.**

Clean up the team per the [Agent Teams docs](https://code.claude.com/docs/en/agent-teams#clean-up-the-team). `team.json` stays on disk for archival — it's part of the post-mortem record.

</section>

</section>

<section purpose="Inventory of files produced into the event folder, and the contents of the final user-visible summary message (paths, article text, word count, models per role, cost/usage breakdown).">

## Output artefacts

When you're done, the event folder contains: `inputs.json`, `keywords.json`, `briefing_<X>.md` × 3, `manifest.json`, `intro_<X>.md` × 3, `talk_<X>.md` × 2, `transcript.md`, `audience.log`, `article.md`, `usage.json`.

Print a final summary to the user containing:

1. The path to `debate_events/<slug>/article.md`.
2. The full text of the journalist's article (paste from `article.md`).
3. The total transcript word count.
4. **Models used per role** — Moderator (your model), Scientist A, Scientist B, Reviewer C, Journalist — as picked at Phase A Batch 4.
5. **Cost / usage** — the contents of `usage.json` in human-readable form. For subscribers, that's per-session end-of-debate context-window tokens + plan-usage-bar delta. For API users, that's per-session `Total cost (USD)` and `Total duration (API)`, plus a grand total.
6. **A SAVE-NOW reminder** for users on claude.ai/code (web): *"⚠️ This sandbox is ephemeral. To keep the outputs, run `/export` now to download the full conversation (article + transcript), or scroll up and copy-paste the article into a document. See [GETTING_STARTED.md](../../../GETTING_STARTED.md) for details."* Show this reminder regardless of surface — it's a no-op on local installs but critical on web.

</section>
