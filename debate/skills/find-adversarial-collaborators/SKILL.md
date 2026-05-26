---
name: find-adversarial-collaborators
description: Given a scientist's name (and optional topic), suggest 10 people who would make productive adversarial-collaboration or debate partners. Use when the user wants to brainstorm co-authors, debate opponents, or scientist-role candidates for the run-debate skill.
user-invocable: true
---

# Find adversarial collaborators

<section purpose="One-paragraph framing: clarify scope so the skill isn't mistaken for run-debate. This skill is a brainstorming tool — it suggests partners; it does not orchestrate the collaboration.">

## What this skill does

Given one scientist's name, suggest **exactly 10** candidates who would make productive adversarial-collaboration or debate partners. This is a brainstorming tool — it does not run the collaboration itself.

</section>

<section purpose="Define the five-step flow: collect target + topic + recency, then collect seniority criteria for candidates (career stage + quantitative thresholds), then anchor the target's profile, then propose 10 candidates matching the criteria.">

## Flow

### Step 1 — target + topic + recency (one AskUserQuestion, up to 3 questions)

- Target scientist name (required).
- Topic narrowing (optional — if given, candidates are scored for relevance to this topic).
- Years of recent work to anchor on (default 5).

### Step 2 — candidate seniority criteria (AskUserQuestion, multiSelect)

Ask the user *"Which seniority levels are you open to for adversarial collaborators? (Multi-select. Default = any.)"*. Options:

- **Any career stage** (no filter — recommended default; selecting this alone skips the threshold sub-questions)
- **Current PI** (running their own lab, any years as PI)
- **Established PI** (≥ N years as PI — threshold asked in Step 3 if selected)
- **Postdoc or non-PI senior researcher** (research scientist, staff scientist, senior research associate)
- **Current PhD student**
- **Industry researcher** (R&D scientist at a company, no academic appointment)

### Step 3 — quantitative thresholds (AskUserQuestion, only if Step 2 picked specific stages OR user wants thresholds)

For each criterion the user selects in Step 2 that has a numeric threshold, ask:

- If **Established PI** selected: *"Minimum years as PI? (default 5)"*
- If user wants additional filters (a separate AskUserQuestion *"Add quantitative filters?"*):
  - *"Minimum years since first paper? (default `none` — no filter)"*
  - *"Minimum h-index? (default `none` — h-index from Google Scholar is not always programmatically retrievable; treat as a soft preference the LLM applies based on training-data knowledge.)"*
  - *"Minimum number of first/last-author papers in the topic area? (default `none`)"*

All thresholds default to "no filter" so the user can pick *any* of the criteria and still get 10 candidates back. The LLM applies thresholds as **soft preferences** when exact data is unavailable.

### Step 4 — anchor the target's profile

Run:
```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/search_works.py \
  --author "<NAME>" --tier all --years <N> --abstracts-only \
  --out papers_cache/works/<author-slug>.json
```
Read all returned abstracts plus a small amount of full text where freely available. Summarise the target's recent view in 5–10 bullets — this is the *anchor* you compare candidates against.

### Step 5 — propose 10 candidates matching the seniority criteria

Markdown table:

| # | Candidate | Career stage | Years active (since 1st paper) | Their view (1 line) | Why adversarial | Engagement quality | Confidence |
|---|-----------|--------------|--------------------------------|---------------------|-----------------|--------------------|------------|

- **Career stage** is one of: *PI (N years)*, *Postdoc*, *Non-PI senior*, *PhD student*, *Industry*, *unknown*. Use training-data knowledge to fill in; mark `unknown` if you can't determine it.
- **Years active** is approximate (training-data estimate). If you don't know, write `unknown`.
- **Why adversarial** is one of: *complementary tools*, *opposing claims*, *overlap-but-unaligned framing*.
- **Engagement quality** is one of: *constructive*, *unknown*, *dismissive* — default to *unknown* unless high-confidence evidence from public record.
- **Confidence** is `high` / `medium` / `low` — your confidence that this person both exists and holds the view you describe.

If the user selected restrictive seniority criteria (e.g. only "Current PhD student"), candidates should match where possible. If you can't find 10 matching the strict criteria, surface this to the user via a follow-up AskUserQuestion: *"Only N candidates match the strict seniority criteria. Relax to nearest-fit, or accept fewer?"*.

Below the table, list any candidates you considered but dropped, with a one-line reason (e.g. *"too junior for the requested 'established PI' filter"* or *"unable to confirm field overlap"*).

</section>

<section purpose="Lock down the failure modes this skill must avoid (especially fabrication of people) and re-state the scope boundary so the agent doesn't drift into running a debate.">

## Hard rules

- **Never invent a person.** If unsure whether someone exists or holds the view, write `unknown` and mark confidence `low` — or drop the candidate. Suggesting a fabricated researcher is the failure mode this skill must avoid.
- **Exactly 10 candidates** in the main table (unless the seniority filter is strict enough that fewer match — then surface the count and ask the user how to proceed).
- **Seniority data is best-effort.** Career stage / h-index / years active come from LLM training-data knowledge plus the candidate's OpenAlex publication record (`years_active = current_year - earliest_publication_year`). Mark `unknown` when you can't verify; never fabricate years or h-index numbers.
- **Out of scope**: this skill suggests partners — it does not orchestrate the collaboration. For that, see [`run-debate`](../run-debate/SKILL.md).

</section>
