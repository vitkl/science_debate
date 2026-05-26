---
name: find-adversarial-collaborators
description: Given a scientist's name (and optional empirical question), suggest 10 people who would make either (a) productive debate opponents for run-debate, or (b) true adversarial collaborators in Kahneman's sense (joint pre-registered study, joint authorship). The user picks the mode in Step 1.
user-invocable: true
---

# Find adversarial collaborators

<section purpose="One-paragraph framing: the skill operates in two modes. Debate-partner mode finds suitable opponents for a one-shot run-debate exchange. Adversarial-collaboration mode finds candidates for Kahneman's joint pre-registered study protocol. Different modes apply different filters and table columns.">

## What this skill does

Given one scientist's name, suggest **exactly 10** candidates. You pick the mode:

- **Debate-partner mode** — find people who would make a productive one-shot debate opponent in [`run-debate`](../run-debate/SKILL.md). Filter on whether their public position differs from the target's in an interesting way; engagement quality is the main soft signal.
- **Adversarial-collaboration mode** — find people who would make a true [Kahneman-style adversarial collaborator](https://en.wikipedia.org/wiki/Adversarial_collaboration): two researchers with conflicting predictions on a specific empirical question who agree in advance on a study design, pre-register, run the study once, and jointly author the paper — including the parts where their own predictions failed. Filter on publicly-committed conflicting predictions, pre-registration track record, and willingness to publicly update (concession track record).

This is a brainstorming tool — it does not run either format itself.

</section>

<section purpose="Five-step flow: mode selection + empirical question (if adversarial), seniority criteria, optional quantitative thresholds, anchor the target, then propose 10 candidates matching the criteria.">

## Flow

### Step 1 — mode + target + topic (one or two AskUserQuestion batches)

First batch (≤ 3 questions):
- **Mode**: *"Debate partner (one-shot `run-debate` exchange)"* or *"Adversarial collaborator (joint pre-registered study + joint paper, Kahneman 2009)"*.
- Target scientist name (required).
- Years of recent work to anchor on (default 5).

If the user picked **Adversarial collaborator**, second batch (one question):
- *"What is the specific empirical question you would want to settle jointly? (One sentence; should be operationalisable as a study with a measurable outcome — e.g. 'does X cause Y in human cell line Z under condition W?')"*

Without a concrete empirical question, the LLM cannot evaluate whether candidates have committed to a *conflicting* prediction — required for adversarial mode.

If the user picked **Debate partner**, second batch (one question, optional):
- *"Topic narrowing for the debate? (optional)"*

### Step 2 — candidate seniority criteria (AskUserQuestion, multiSelect)

*"Which seniority levels are you open to for candidates? (Multi-select. Default = any.)"* Options:

- **Any career stage** (no filter — recommended default; selecting this alone skips Step 3)
- **Current PI** (running their own lab, any years as PI)
- **Established PI** (≥ N years as PI — threshold asked in Step 3 if selected)
- **Postdoc or non-PI senior researcher** (research scientist, staff scientist, senior research associate)
- **Current PhD student**
- **Industry researcher** (R&D scientist at a company, no academic appointment)

In adversarial-collaboration mode, surface a note: *"Very junior candidates (PhD students) typically cannot commit lab resources to a multi-year joint pre-registered study — they may be filtered automatically. Confirm if you want them included anyway."*

### Step 3 — quantitative thresholds (AskUserQuestion, only if Step 2 picked specific stages OR user wants thresholds)

- If **Established PI** selected: *"Minimum years as PI? (default 5)"*
- Optional follow-up *"Add quantitative filters?"* with sub-questions:
  - *"Minimum years since first paper? (default `none`)"*
  - *"Minimum h-index? (default `none` — h-index from Google Scholar is not always programmatically retrievable; treat as a soft preference applied from training-data knowledge)"*
  - *"Minimum first/last-author papers in the topic area? (default `none`)"*

Thresholds default to "no filter" — picking *any* of the criteria still returns 10 candidates.

### Step 4 — anchor the target's profile

```bash
bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/search_works.py \
  --author "<NAME>" --tier all --years <N> --abstracts-only \
  --out papers_cache/works/<author-slug>.json
```

Read all returned abstracts plus a small amount of full text where freely available. Summarise the target's recent view in 5–10 bullets — this is the *anchor* you compare candidates against. In adversarial-collaboration mode, also identify whether the target has a public commitment on the empirical question (paper, talk, blog).

### Step 5 — propose 10 candidates matching the mode + criteria

Columns differ by mode.

#### Debate-partner mode

| # | Candidate | Career stage | Years active (since 1st paper) | Their view (1 line) | Why adversarial | Engagement quality | Confidence |
|---|-----------|--------------|--------------------------------|---------------------|-----------------|--------------------|------------|

- **Why adversarial** ∈ {*complementary tools*, *opposing claims*, *overlap-but-unaligned framing*}.
- **Engagement quality** ∈ {*constructive*, *unknown*, *dismissive*}. Default *unknown* unless high-confidence evidence from public record.

#### Adversarial-collaboration mode

| # | Candidate | Career stage | Conflicting prediction (cite) | Publicly committed? | Pre-registration track record | Concession track record | Shared empirical question | Confidence |
|---|-----------|--------------|-------------------------------|---------------------|-------------------------------|-------------------------|---------------------------|------------|

- **Conflicting prediction (cite)** — one sentence stating the candidate's *public* prediction that conflicts with the target's. **Must cite the source (paper / talk / quote) at `medium`+ confidence**; if no public prediction is on record, mark `unknown` and drop the row (do not infer).
- **Publicly committed?** ∈ {*yes (cite)*, *inferred from work*, *unknown*}. Has the candidate publicly staked the conflicting position in print or recorded talk?
- **Pre-registration track record** ∈ {*has pre-registered*, *none on record*, *unknown*}. Soft signal of willingness to bind analysis in advance — strongest available proxy from public record.
- **Concession track record** ∈ {*has publicly updated*, *none on record*, *unknown*}. Has the candidate publicly conceded when data went against them on any topic? Single best predictor of adversarial-collaboration success (per Kahneman & Klein 2009).
- **Shared empirical question** — one line stating the study or question both sides would commit to.
- **Confidence** ∈ {`high`, `medium`, `low`} — your confidence that this person both exists and holds the position described.

If you can't find 10 candidates matching the strict adversarial-collaboration criteria (a common case — publicly-attested conflicting predictions are rarer than they look), surface this via AskUserQuestion: *"Only N candidates match the strict criteria with at least one publicly-attested conflicting prediction. Relax to nearest-fit candidates (mark them as such), or accept fewer?"*.

Below the table, list any candidates you considered but dropped, with a one-line reason.

</section>

<section purpose="Failure modes and out-of-scope boundary. The hard rules prevent fabrication — particularly important in adversarial mode where the LLM is asked to cite specific predictions and is prone to hallucination.">

## Hard rules

- **Never invent a person.** If unsure whether someone exists or holds the view, write `unknown` and mark confidence `low` — or drop the candidate.
- **Never invent a prediction or a quote.** If you cannot point to a paper, blog, talk, or interview where the candidate publicly stated the conflicting position, write `unknown` for the citation column and either drop the row (adversarial mode) or mark *inferred from work* with `low` confidence (debate-partner mode).
- **In adversarial-collaboration mode, never list a candidate without at least one publicly attested conflicting prediction.** "Could plausibly disagree based on their research area" is **not** enough — that is debate-partner mode.
- **Seniority data is best-effort.** Career stage / h-index / years active come from LLM training-data knowledge plus the candidate's OpenAlex publication record (`years_active = current_year - earliest_publication_year`). Mark `unknown` when you can't verify; never fabricate years or h-index numbers.
- **Out of scope**:
  - In debate-partner mode, this skill suggests partners — [`run-debate`](../run-debate/SKILL.md) actually runs the debate.
  - In adversarial-collaboration mode, **the `run-debate` format is the wrong tool**. A true Kahneman-style adversarial collaboration requires offline pre-registration, agreed study design, real data collection, and joint authorship — all outside this package's scope. This skill only helps identify candidates.

</section>
