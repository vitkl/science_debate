---
name: run-debate
description: Run a structured multi-stage scientific debate between AI agents faithfully representing named scientists. Use when the user invokes /run-debate or asks to set up, prepare, or run a scientist-vs-scientist debate.
user-invocable: true
---

# Run debate

<section purpose="Set the role (Moderator), the high-level shape (prep → orchestrate → write up), and require an immediate user-facing reminder of the debate format so the user knows what they're signing up for before any work begins.">

You are the **Moderator**. Walk the user through the format, prepare the materials, then orchestrate a multi-stage debate between three scientist teammates and a journalist teammate. Print the [stage table from FORMAT.md](../../FORMAT.md#stage-table) to the user **at the start of this skill** as a reminder of what they are about to commit to.

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

- **Batch 1 — required**: scientist A name; scientist B name; scientist C name (Reviewer); one-sentence debate topic.
- **Batch 2 — debate shape**: `total_minutes` (default 80); `give_collaborative_tone_to_presenters?` (default *no*); `journalist_word_budget` (default 500–600); `allow_websearch_during_debate?` (default *no*); `include_youtube?` (default *yes* — works out of the box via yt-dlp).
  - <section purpose="YouTube works without setup via yt-dlp (zero-config fallback). If the user has YOUTUBE_API_KEY in their env (e.g. set in ~/.claude/settings.json), the script auto-prefers the API backend. Either way, no user action required in Phase A — the dispatch is automatic in search_youtube.py.">YouTube search works out of the box via yt-dlp; no setup needed. If `YOUTUBE_API_KEY` is set in the env (e.g. in `~/.claude/settings.json`), the script automatically prefers the YouTube Data API v3 backend (faster, more reliable, 10 000 free queries/day) — otherwise it transparently falls back to yt-dlp page-scraping. Either way, no Phase A action required: `search_youtube.py` picks the backend itself and prints which one it used to stderr so the user sees it.</section>
- **Batch 3 — ingestion**: per-scientist free-text instruction (default = the tier description below); `n_full_papers_cap` (default 25); `n_abstracts_cap` (default 500); `pre_fetch_urls` (optional list — harness asks per-domain permission); `custom_sources` (optional per-scientist list — see schema below).
- **Batch 4 — models**: model per role for PresenterA, PresenterB, Reviewer-scientist, Journalist (default Opus). Tell the user the Moderator (you) runs Sonnet by default; teammates do **not** inherit lead model — you specify each one explicitly at spawn.

**Default ingestion instruction** (the tier description): *"Read this scientist's work in three tiers and stop when you have enough. **Tier 1** — work directly about the debate topic (papers, blog posts, book chapters, recorded-talk transcripts, social-media posts when available, opinion/commentary pieces from PMC). **Tier 2** — papers where they are first or last author (abstracts always; full text up to `n_full_papers_cap`). **Tier 3** — all other papers (abstracts only up to `n_abstracts_cap`)."*

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

<section purpose="Create the per-debate working directory with a slug derived from scientists + date + session-id hash; merge Phase A answers into the skeleton inputs.json.">

### B0 — event folder

`new_debate_event.py --scientist_a "<A>" --scientist_b "<B>" --scientist_c "<C>" --topic "<topic>"` creates `debate_events/<A-last>_<B-last>_<YYYY-MM-DD>_<6hash>/` with an `inputs.json` skeleton. Merge Phase A answers into it.

</section>

<section purpose="Convert the topic into a structured search-keyword set (primary, synonyms, opposing, publication types). The Moderator drafts (LLM domain knowledge), the user confirms, the script persists — a single source of truth for what was searched.">

### B1 — keywords

Before calling `generate_search_keywords.py`, **you** (the Moderator) think out loud and generate the keyword set: `primary_terms`, `synonyms`, `opposing_terms`, plus `publication_types: ["editorial", "letter", "commentary", "opinion", "review", "news"]`. Then ask the user (one `AskUserQuestion`) to confirm or amend. Persist the final set by invoking `generate_search_keywords.py --topic "<topic>" --out debate_events/<slug>/keywords.json --primary "<csv>" --synonyms "<csv>" --opposing "<csv>"`.

</section>

<section purpose="Parallel per-source metadata searches: papers via PMC + OpenAlex, blogs via the registry, YouTube only if explicitly enabled and the API key is set (degrades gracefully otherwise).">

### B2 — search

For each scientist run, in parallel. **Pass `{author}` / `{scientist}` literally in the `--out` path** — the scripts auto-substitute the canonical slug (lowercase, dash-separated). Do NOT pre-compute a slug yourself; the script's substitution is the source of truth that `build_briefing.py` later reads from.

- `search_works.py --author "<NAME>" --keywords debate_events/<slug>/keywords.json --tier all --out 'papers_cache/works/{author}.json'`
- `search_blogs.py --scientist "<NAME>" --registry debate/blog_registry.yaml --keywords debate_events/<slug>/keywords.json --out 'papers_cache/blogs/{scientist}.json'`
- *If* `include_youtube == true`: `search_youtube.py --scientist "<NAME>" --keywords debate_events/<slug>/keywords.json --out 'papers_cache/youtube_search/{scientist}.json'` (auto-picks backend: YouTube Data API v3 when `YOUTUBE_API_KEY` is set, yt-dlp otherwise; prints the chosen backend to stderr — surface it in the conversation so the user knows which path ran)

</section>

<section purpose="Cache-aware full-text download dispatcher: PMC XML, bioRxiv PDF, generic web pages, YouTube transcripts, plus user-supplied custom sources. Each new outbound domain is gated by per-domain user approval before fetching.">

### B3 — fetch full text

`fetch_fulltext.py --works papers_cache/works/<author>.json --blogs papers_cache/blogs/<scientist>.json --youtube papers_cache/youtube_search/<scientist>.json --custom-sources debate_events/<slug>/inputs.json --pre-fetch-urls debate_events/<slug>/inputs.json`

For each domain in `pre_fetch_urls` and each new domain in custom URLs, **ask the user via `AskUserQuestion`** before fetching. Already-cached items skip silently.

</section>

<section purpose="Per-scientist briefing assembly under user caps. Handles oversize sources via LLM summarisation (Tier-1 sacred, Tier-2 summarisable to ~500 words, Tier-3 batch-summarisable). If even after that the briefing exceeds the global cap, surfaces the over-budget Tier-1 list to the user for triage.">

### B4 — briefings

`build_briefing.py --inputs debate_events/<slug>/inputs.json --out debate_events/<slug>/` produces `briefing_<scientist>.md` × 3 + `manifest.json`. If the script writes `needs_summary.json` (over-budget sources), spawn one `Task` subagent per source with prompt *"Summarise this paper/post to ~500 words preserving the author's argument, claims, and characteristic vocabulary. Source path: <path>. Write result to <path>.summary.md."*, then re-run `build_briefing.py` to merge. If `needs_user_decision.json` appears (briefing still over global cap after Tier-2 summary + Tier-3 batch summary), surface the over-budget Tier-1 list to the user via `AskUserQuestion`.

</section>

<section purpose="Each scientist (A, B, C) writes a self-introduction grounded in their briefing; the assess-transcript-faithfulness skill critiques each draft; 3 iterations or pass-early. Goal: catch generic-LLM voice before the debate starts.">

### B5a — self-intros (3 iterations)

For each of A, B, C: spawn the scientist teammate (`scientist` agent type, model from Batch 4) with name `A`/`B`/`C`. Send *"You are <real name>; read your briefing at debate_events/<slug>/briefing_<X>.md. Write a 300–1000 word self-introduction covering (a) who you are and how you got here, (b) your view on the debate topic. Aim for high faithfulness — see debate/FAITHFULNESS.md."* Invoke `/assess-transcript-faithfulness` on the reply; relay the top 3 fixes back to the scientist. Iterate **3 times** (or stop earlier if the critic returns *pass*). Commit the final intro to `debate_events/<slug>/intro_<X>.md`.

</section>

<section purpose="Talk preparation for A and B only (C doesn't present): three-iteration length-reduction shape from 2× target down to target, with faithfulness pass at each step. Stage 1 / 2 in Phase C then deliver this prepared text near-verbatim.">

### B5b — talk preparation (3 iterations, A and B only)

Compute `talk_target = stage-1/2 word budget` (1500 at default `total_minutes=80`; scales as `1500 × total_minutes / 80`). For each of A, B:
- *"Draft 1: ~2× target (~3000 words at default), expansive — cover all the arguments and evidence you'd raise. Don't worry about length yet."* → faithfulness pass.
- *"Draft 2: cut to target (≈ {talk_target} words), tighten to your most-essential argument."* → faithfulness pass.
- *"Draft 3: final polish, exactly target ±10%, ready to deliver."* → final.

Commit to `debate_events/<slug>/talk_<X>.md`. Stages 1 and 2 in Phase C deliver this text near-verbatim.

</section>

<section purpose="Hard sync point. Show the user what was prepared (counts, sample titles, intros, talks) and wait for an explicit GO. Cheap insurance against a 60-minute debate launched on bad inputs.">

### B6 — review gate

Display per-scientist counts (`Tier 1: X papers (Y full text), N blogs, M transcripts; Tier 2: …; Tier 3: …`), 5 sample titles per tier per scientist, the final intros, the final talks. `AskUserQuestion` *"Confirm to start the debate, or amend?"*. **Wait for an explicit "GO"** — do not start stages without it.

</section>

</section>

<section purpose="The live debate: team spawn with per-role model overrides, the 10-stage sequence with audience break-points, the journalist write-up, and end-of-debate cost accounting before clean-up.">

## Phase C — orchestrate the debate

<section purpose="Spawn the agent team in one natural-language instruction; lock per-role model picks (teammates do not inherit lead model); materialise the stage table as TODOs so the user sees progress.">

### C0 — team setup

Once the user says GO, materialise the [FORMAT.md stage table](../../FORMAT.md#stage-table) as TODOs so progress is visible. Then create the team in natural language: *"Create an agent team for the debate. Spawn three scientist teammates (`scientist` agent type) named A, B, C with their respective briefing paths. Spawn one journalist teammate (`journalist` agent type) named J. Use models: A=<>, B=<>, C=<>, J=<>. Do not inherit my model. WebSearch is {enabled|disabled} for this debate."*

</section>

<section purpose="The 10 debate stages. Stages 1–2 deliver prepared talks (no fresh generation); 3–10 are live exchanges. Append every utterance to transcript.md with speaker-prefixed lines; nudge agents toward conclusion if they near their word target.">

### C1 — stages 1–10

For **stages 1 and 2** (deliver prepared talk): send the scientist teammate *"Stage <1|2>: deliver your prepared opening at `debate_events/<slug>/talk_<X>.md`. Minor adjustments allowed (e.g. a sentence connecting to your self-intro), but stay close to the prepared text — the faithfulness work is already done."*

For **stages 3–10**: send a single message to the relevant teammate with stage number, role, word target (per FORMAT.md, scaled by `total_minutes / 80`), and the path to `transcript.md` so far. Append each reply to `transcript.md` with prefix `<Scientist real name> representative agent: …` (or `Reviewer (<Scientist C real name>):` for stages 7 and 9). Print the same prefixed line in the conversation.

You may send a brief reminder if a reply approaches its word target without a conclusion: *"You're at <current>/<target> words; please wrap up your point."*

</section>

<section purpose="Audience interjection points between resolved exchanges (never mid-pair). User can ask, comment, or 'continue'; non-continue messages are logged and forwarded to the relevant teammate(s) before proceeding.">

### C2 — audience break-points

After stages **1, 2, 4, 6, 7, 8, 9, 10**, `AskUserQuestion` *"Audience question, comment, or 'continue'?"*. Default audience time = ~3 min = ~300 words. Log to `debate_events/<slug>/audience.log` as `Audience: …`. If non-continue, forward the audience message (prefixed `Audience: …`) to the relevant teammate(s) before proceeding.

</section>

<section purpose="Journalist writes the Nature-News-and-Views-style summary from the full transcript and JOURNALISM.md. Output is the user-visible artefact.">

### C3 — journalist

After stage 10, send the Journalist *"Read `debate_events/<slug>/transcript.md` and `debate/JOURNALISM.md`. Write the summary article to `debate_events/<slug>/article.md`, target ≈ {journalist_word_budget} words. Apply Nature News-and-Views structure. Never invent quotes."* Append `Journalist: …` line + the article to `transcript.md`.

</section>

<section purpose="End-of-debate cost accounting tailored to the user's subscription tier. Subscribers get /context end-of-debate token counts per session (the primary signal) plus plan-usage-bar delta as a rough plan-cost proxy. API users get the Session block from /usage. Then clean up the team.">

### C4 — session-cost accounting + cleanup

Per-session token counts are not cleanly exposed via slash commands for Pro / Max / Team / Enterprise subscribers — the *Session block* at the top of `/usage` is intentionally hidden for subscribers (it's there for raw-API users only), and only **plan-usage bars** + activity stats are shown. So we report what's actually available:

1. **Before** sending the journalist message (i.e. at the start of C3), have each teammate run `/context` and reply with the current context-window token count. Capture these as the *baseline* (close to the end-of-debate state, since most generation has happened by then). Lead runs `/context` too.
2. **After** the journalist finishes (start of C4), repeat `/context` for the lead and for the journalist (the only teammate whose context grew during C3). The other teammates' baselines from step 1 are still the right end-state for them.
3. **For Pro / Max / Team / Enterprise subscribers**: also have the lead run `/usage` *once* before the debate and once at the end; note the plan-usage-bar percentages (e.g. "Sonnet: 14% → 21%"). The delta is the rough cost of this debate against the user's plan.
4. **For raw-API users**: run `/usage` at the end on every teammate and capture the Session block's `Total cost` and `Total duration (API)` values.
5. Write everything collected to `debate_events/<slug>/usage.json` with structure:
   ```jsonc
   {
     "subscription_kind": "pro|max|team|enterprise|api",
     "sessions": {
       "Moderator": {"context_tokens_end": N, "context_delta_tokens": N, "session_cost_usd": N_or_null, "api_duration_s": N_or_null},
       "A": {...}, "B": {...}, "C": {...}, "J": {...}
     },
     "plan_usage_delta": {"sonnet": "+7%", "opus": "+12%"},
     "grand_total_context_tokens": N
   }
   ```
6. Then ask the lead (yourself) to clean up the team per the [Agent Teams docs](https://code.claude.com/docs/en/agent-teams#clean-up-the-team).

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
