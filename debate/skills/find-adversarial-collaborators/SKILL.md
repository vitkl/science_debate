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

<section purpose="Define the four-step flow from input collection through anchored profile to the ranked candidate table, including the exact search-script invocation.">

## Flow

1. Ask the user (one `AskUserQuestion` with up to 3 questions):
   - Target scientist name (required).
   - Topic narrowing (optional — if given, candidates are scored for relevance to this topic).
   - Years of recent work to anchor on (default 5).
2. Anchor the target scientist's recent profile by running:
   ```bash
   bash scripts/helper_scripts/run_python_cmd.sh debate/scripts/search_works.py \
     --author "<NAME>" --tier all --years <N> --abstracts-only \
     --out papers_cache/works/<author-slug>.json
   ```
   Read all returned abstracts plus a small amount of full text where freely available. Summarise the target's recent view in 5–10 bullets — this is the *anchor* you compare candidates against.
3. Propose **exactly 10** candidates in a markdown table:

   | # | Candidate | Their view (1 line) | Why adversarial | Engagement quality | Confidence |
   |---|-----------|---------------------|-----------------|--------------------|------------|

   - **Why adversarial** is one of: *complementary tools*, *opposing claims*, *overlap-but-unaligned framing*.
   - **Engagement quality** is one of: *constructive*, *unknown*, *dismissive* — default to *unknown* unless you have high-confidence evidence from public record (recorded conversations, replies to criticism, joint publications).
   - **Confidence** is `high` / `medium` / `low` — your confidence that this person both exists and holds the view you describe.

4. Below the table, list any candidates you considered but dropped, with a one-line reason.

</section>

<section purpose="Lock down the failure modes this skill must avoid (especially fabrication of people) and re-state the scope boundary so the agent doesn't drift into running a debate.">

## Hard rules

- **Never invent a person.** If unsure whether someone exists or holds the view, write `unknown` and mark confidence `low` — or drop the candidate. Suggesting a fabricated researcher is the failure mode this skill must avoid.
- **Exactly 10 candidates** in the main table. Not 5, not 12. Drop the weakest if you have too many; surface a related-field candidate if you have too few.
- **Out of scope**: this skill suggests partners — it does not orchestrate the collaboration. For that, see [`run-debate`](../run-debate/SKILL.md).

</section>
