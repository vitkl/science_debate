# HANDOFF — full-event combined HTML for /run-debate Phase C4

- **PATH_TO_PLAN**: `/Users/kleshcv/.claude/plans/wild-plotting-finch.md`
- **PATH_TO_CONVERSATION**: `/Users/kleshcv/.claude/projects/-Users-kleshcv-Desktop-my-packages-science-debate/35ab7dec-f16e-440b-bbc0-9b016b38d875.jsonl`

## Goal

The `wild-plotting-finch.md` plan already specifies adding `transcript.html` to Phase C4's HTML exports (item 10, "transcript.md is incomplete" sub-issue). This handoff extends that with a **further, user-validated artifact**: a single combined **`full_debate.html`** covering the entire event — self-intros, all 10 debate stages, and the three journalist articles — with a narrative format description, a stage table, and a table of contents at the top.

The current Phase C4 produces three article HTMLs only. During the live debate session this conversation ran, the user iteratively shaped a new `full_debate.html` artifact by hand. **Fold these requirements into the workflow** so future debates get this artifact automatically — alongside, not replacing, `transcript.html` and the three articles.

## Current Progress

In the running session for slug `ariasA_davidsonB_2026-05-26_c7893c` (Martinez Arias vs Davidson, Briscoe reviewer), I produced two new files by hand:

- [`debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.md`](../../../debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.md) — 12.4k-word combined source markdown.
- [`debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.html`](../../../debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.html) — rendered via existing `debate/scripts/render_html.py`. The render script handled it without modification.

The `.md` was composed one-off via an inline Python helper in a Bash heredoc — not committed as a reusable script. The plan needs to formalise this as a script.

## Final HTML Structure (after seven iterations of user feedback)

1. **H1 title:** "Davidson vs. Martinez Arias — Full debate"
2. **Topic line** (one-sentence framing).
3. **Cast line** with full titles and affiliations:
   - Martinez Arias — *ICREA Research Professor, Systems Bioengineering, Universitat Pompeu Fabra, Barcelona*
   - Davidson — *Norman Chandler Professor of Cell Biology, Caltech, 1937–2015; represented faithfully from his published work*
   - Briscoe — *Principal Group Leader, Francis Crick Institute; Editor-in-Chief, Development*
   - Plus Moderator (lead) and Journalist (post-debate articles).
4. **Format paragraph** — narrative description (≈3 sentences) of the stage arc: prepared self-intros and opening talks; live opens with the two prepared talks (Stages 1–2); two cross-examination pairs (opponent critiques, presenter responds: 3–4, 5–6); two reviewer-and-rejoinder rounds (Reviewer assesses + identifies most-productive remaining disagreement, then short final rejoinders: 7–8, 9–10). Closes with: *"Stages 3–10 are improvised after being presented with the prior transcript — each stage sees the transcript before it."*
5. **Format table** with columns `# | Stage | Speaker | Words | Audience can ask questions (asked)`. **Speaker column uses real names** (Martinez Arias, Davidson, Briscoe), **never slot letters A/B/C**. Last column shows `yes (N)` where N is the actual count from `audience.log` (em-dash for non-break-point stages and prep rows). For this run, N=0 at all eight break-points; a caption note states *"no audience questions were asked (0 across all eight break-points)"*.
6. **Contents section** — table-of-contents block with anchor links to every section and every stage subsection. The python-markdown `toc` extension auto-generates compatible slugs from H2/H3 headings.
7. **`## Self-introductions`** with `### <real name>` subsections, bodies verbatim from `intro_<X>.md`.
8. **`## The debate`** containing the Moderator welcome line + all 10 stage sections verbatim from `transcript.md` (with `transcript.md`'s own header stripped so it doesn't double-up). **Structural note:** stage section headings in `transcript.md` are H2 (`## Stage N — …`), so they end up at the same H2 level as parent `## The debate`. The compose script should demote them to H3 to preserve hierarchy and TOC nesting.
9. **`## Journalist's write-up — three audience-tiered articles`** with `### For developmental biologists and stem-cell biologists (same field)`, `### For scientists in adjacent fields (broader field)`, `### For STEM-educated readers without field background (general STEM)`. Bodies verbatim from `article_same_field.md`, `article_broader_field.md`, `article_general_stem.md`.

## What Worked

- **Composing the combined MD as a single file** and rendering with existing `render_html.py` (which already accepts any markdown). No render-script change needed for layout — only CSS spot-check, which passed at 12k words.
- **Real names in user-facing output everywhere** (cast, table, headings) — slot letters A/B/C are an internal harness construct only.
- **WebSearch verification of affiliations**. The initial cast line had "Universitat Pompeu Fabra" only; user pushed back ("This is not his affiliation"). A WebSearch on the ICREA profile / CV confirmed "ICREA Research Professor, Systems Bioengineering, Universitat Pompeu Fabra, Barcelona" — ICREA is the actual employer, UPF hosts. Same pattern (full title + affiliation) was then applied to the other two scientists.
- **Narrative + table** in the Format section. User initially saw a one-line format note, asked for "a description of what the stages are", got a stage table — then asked again for a narrative paragraph "perhaps taken from the script" describing the arc, on top of the table. Both together is the right shape.
- **Counting audience questions from `audience.log`** rather than hardcoding "break-point: yes/no". Even when zero, surfacing the count tells the reader the debate ran without audience interjections.

## What Didn't Work / Pitfalls

- **First-pass affiliation was incomplete.** Defaulting to short "Universitat Pompeu Fabra" dropped the load-bearing "ICREA" employer. **Lesson for the skill: cast affiliations must be sourced (e.g. WebSearch confirmed) before they go in the HTML — not best-guessed from briefing context.** Add a WebSearch / sourcing step at briefing time, persist titles + affiliations to `inputs.json` or `team.json`, and use those verbatim downstream.
- **Format paragraph drifted three times.** Initial "Format: 10 stages with audience break-points after 1, 2, 4, 6, 7, 8, 9, 10" was too procedural. User wanted (a) what the stages are, (b) the narrative arc (cross-examination pairs, reviewer-rejoinder rounds), (c) the transcript-visibility mechanism stated explicitly. The final paragraph nails all three and should be the template.
- **"Audience break" column was ambiguous.** "yes / no" without counts hid whether the audience actually engaged. The new column "Audience can ask questions (asked)" with `yes (N)` is unambiguous.
- **`audience.log` is currently free-form text** (`# Audience interjections\n` header + ad-hoc lines). Parsing per-break-point counts requires a schema. Without it, the compose script can only count the total or rely on the Moderator to also tag entries by `after_stage`.
- **H2/H3 nesting in the rendered HTML** has stage headings at the same level as their parent `## The debate` because `transcript.md` writes stage headings as H2. The compose script must demote during composition.

## User Verbatim Requests — preserved for spec traceability

In order, these are the user's edits that shaped the artifact. Each maps to a requirement the workflow plan should encode:

- **(A)** *"I need another HTML: like this plan wild-plotting-finch.md suggests - render the full transcript from introductions to talks to all discussion with nice description section headers and ending with 3 articles."* → produce a single combined HTML covering intros → talks/discussion → 3 articles.
- **(B)** *"This is not his affiliation 'Alfonso Martinez Arias (Universitat Pompeu Fabra)'"* and *"Hm, do a search to confirm."* → cast affiliations must be sourced (WebSearch-confirmed) and full; ICREA Research Professor at UPF, not bare UPF. Apply the same standard to Davidson and Briscoe — full titles, dates where relevant.
- **(C)** *"The format needs to be a description of what the stages are. We also need table of contents."* → Format section must describe the stages; add a TOC with anchor links to every section and stage.
- **(D)** *"Now replace A and B and C in the format with actual names"* → real names in the Speaker column; slot letters A/B/C never appear in user-facing output.
- **(E)** *"'Audience break' -> audience can ask questions (table shows how many questions were asked)"* → rename column to "Audience can ask questions (asked)"; show actual counts parsed from `audience.log`; caption note summarising the total.
- **(F)** *"'improvised against the prior transcript.' -> are improvised after being presented with the prior transcript. Each stage sees the transcript before it."* → spell out the transcript-visibility mechanism, don't gloss it.
- **(G)** *"Table is useful but I think format needs to describe a bit about the structure - no longer than the current paragraph but a bit more narrative structure about what the stages are in the debate (perhaps taken from the script)."* → final format paragraph narrates the arc (openings → cross-examination pairs → reviewer-rejoinder rounds), in parallel with the table.

## Next Steps

1. **New script `debate/scripts/compose_full_event.py`.** Parallel to `compose_transcript.py` proposed in `wild-plotting-finch.md` item 9. Reads `inputs.json` + `team.json` + `intro_<X>.md` + `transcript.md` + `article_*.md` + `audience.log` and writes `full_debate.md` with the structure above. Demote stage H2s to H3 during composition. Count audience interjections per break-point from `audience.log`.
2. **Cast affiliations sourced at briefing time.** Either (a) add a WebSearch confirmation step in Phase B that persists `{title, affiliation}` per scientist to `inputs.json`, or (b) require the user to confirm them at Phase A Batch 1 alongside the names. The compose script then reads from there. **Never** infer affiliation from briefing content alone — that's how this run got "Universitat Pompeu Fabra" without "ICREA".
3. **Structured `audience.log`.** Switch to one JSON line per interjection (`{after_stage: <N>, text: "...", forwarded_to: ["A"|"B"|"C"]}`) so per-break-point counts are reliable. Update the Phase C1 audience-handling code to write the structured form. Keep human-readable rendering downstream.
4. **Phase C4 wiring.** Add to the C4 sequence in `.claude/skills/run-debate/SKILL.md`:
   ```bash
   bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/compose_full_event.py --event-dir "debate_events/<slug>/"
   ```
   Then add `full_debate.md` to the `render_html.py --inputs` comma-list (next to `transcript.md` per plan item 10).
5. **`package_outputs.py`** — append `full_debate.html` to `HIGHLIGHTS_PATTERNS` so it lands in the highlights zip alongside `transcript.html` (plan item 4).
6. **Format paragraph template.** The final wording in this run is good enough to seed a template:
   > A 10-stage structured debate at a default budget of `{total_minutes}` minutes (≈100 words per spoken minute). Each presenter prepares a self-introduction and an opening talk in advance, iterating against a faithfulness self-assessment loop. The live debate then opens with the two prepared talks (Stages 1–2), proceeds through two cross-examination pairs in which each opponent critiques the other and the presenter responds (Stages 3–4, 5–6), and closes with two reviewer-and-rejoinder rounds: the Reviewer assesses the exchange and identifies the most productive remaining disagreement, after which each presenter delivers a short final rejoinder (Stages 7–8, then 9–10). Stages 3–10 are improvised after being presented with the prior transcript — each stage sees the transcript before it.

   Drop into the compose script with `{total_minutes}` from `inputs.json`.
7. **Heading hierarchy.** When composing, scan transcript.md for `^## Stage` and rewrite to `### Stage` before stitching under `## The debate`. Same for any other transcript-level H2s.
8. **(Optional)** Decide whether `full_debate.html` should also be added to the running-session handoff (`handoff_for_running_moderator.md` from plan item 11). For the current `ariasA_davidsonB_2026-05-26_c7893c` slug, the file was already produced manually in this session — so the handoff is not needed for that slug. For future in-flight sessions when the workflow update lands mid-debate, yes.

## Reference Paths

- New HTML artifact (this session): `/Users/kleshcv/Desktop/my_packages/science_debate/debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.html`
- Source MD: `/Users/kleshcv/Desktop/my_packages/science_debate/debate_events/ariasA_davidsonB_2026-05-26_c7893c/full_debate.md`
- Existing render script (works as-is): `debate/scripts/render_html.py`
- Existing CSS: `debate/scripts/_article_default.css` (rendered 12k words cleanly; no change needed)
- Parent plan: `/Users/kleshcv/.claude/plans/wild-plotting-finch.md`
