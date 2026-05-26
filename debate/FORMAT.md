# Debate format — the rules

This file is the single source of truth for the debate format. Every agent definition and the `run-debate` skill references it rather than re-stating the rules.

## Cast (five roles)

- **Moderator** — the lead Claude Code session. Sets up the team, runs the stage clock, prints the stage table when `run-debate` is invoked, materialises stages as TODOs once the debate starts, holds audience questions, and may nudge a scientist to wrap up when they're near their word target with no conclusion in sight. Default model: **Sonnet** (the role is procedural).
- **Presenter** — a scientist agent in "present my case" mode. Faithful to the source scientist's actual views and style.
- **Opponent** — same scientist agent switched to "critique the other's case" mode. Faithfulness still binds.
- **Reviewer** — a third scientist agent who has not presented; evaluates both sides and surfaces the most-productive remaining disagreement. Receives the collaborative-rigorous tone block (below).
- **Journalist** — produces the public-facing summary article in Nature-News-and-Views style (see [JOURNALISM.md](JOURNALISM.md)).

## Stage table

Word counts are *targets at default `total_minutes = 80`*. When the user sets a different `total_minutes = T`, scale each stage's "Default min" by `T / 80` and convert to words at **~100 words per minute** (LLM text is denser than spoken English). Self-intros and the journalist write-up have their own dedicated parameters and do not scale with `total_minutes`.

| # | Stage | Actor | Default min | Default words @100 wpm | Audience break after? |
| --- | --- | --- | --- | --- | --- |
| 0a | Self-introduction prep (3 iterations; faithfulness-driven; no length reduction) | A, B, C separately | n/a | 300–1000 each, final | (Phase B) |
| 0b | Talk preparation (3 iterations; length-reduction + faithfulness) — draft 1 ≈ 2× stage-1/2 target, drafts 2/3 ≈ target | A, B separately | n/a | draft 1 ≈ 3000; drafts 2/3 ≈ 1500 (at default) | (Phase B) |
| 1 | Opening presentation A (deliver prepared talk; minor adjustments allowed) | Presenter A | 15 | 1500 | yes |
| 2 | Opening presentation B (deliver prepared talk; minor adjustments allowed) | Presenter B | 15 | 1500 | yes |
| 3 | B critiques A | Opponent B | 7 | 700 | no |
| 4 | A responds | Presenter A | 5 | 500 | yes |
| 5 | A critiques B | Opponent A | 7 | 700 | no |
| 6 | B responds | Presenter B | 5 | 500 | yes |
| 7 | Reviewer assessment (round 1) | Reviewer C | 4 | 400 | yes |
| 8 | Final rejoinders A → B (round 1) | A, B as Presenter | 4 + 4 | 400 + 400 | yes |
| 9 | Reviewer assessment (round 2) | Reviewer C | 4 | 400 | yes |
| 10 | Final rejoinders A → B (round 2) | A, B as Presenter | 4 + 4 | 400 + 400 | yes |
| — | Journalist write-up | Journalist | n/a | ~500–600 (≈2 GDocs pages), user-tunable | (end) |

## Audience break-points

After stages 1, 2, 4, 6, 7, 8, 9, 10 the Moderator pauses and asks the user (the audience) for a question, comment, or "continue". Default audience-time budget: ~3 minutes (~300 words). Audience text is logged as `Audience: …` in `transcript.md` and forwarded as a labelled message to the next relevant agent before the next stage starts.

## Transcript line format

Every model utterance is appended to `debate_events/<slug>/transcript.md` and printed in the conversation as one of:

- `<Scientist real name> representative agent: …` (scientists in any role)
- `Reviewer (<Scientist C real name>): …` (stages 7 and 9 specifically)
- `Moderator: …` (procedural turns)
- `Journalist: …` (final article)
- `Audience: …` (user interjections at break-points)

## Quotation rule

When an Opponent quotes the other side, the quote is at most **30 words** and is marked with quote characters. Paraphrase otherwise.

## Tone block (gated by audience)

Given verbatim to **Moderator**, **Reviewer**, and **Journalist** only — and to **Presenters/Opponents only if the user explicitly opts in at Phase A**. Default for Presenters/Opponents is no tone block, because faithfulness binds: imposing a collaborative tone on a scientist whose real-world style is combative would reduce faithfulness.

> *The structured format exists to better understand the topic through robust but collaborative exchange. Seek shared understanding where possible; where disagreement remains, make it specific (mechanism, prediction, observation that would distinguish the views).*

## Faithfulness

See [FAITHFULNESS.md](FAITHFULNESS.md). Every scientist agent treats those criteria as binding; `assess-transcript-faithfulness` uses them when critiquing self-intros and talk drafts during Phase B.

## Reminders the Moderator may send

The Moderator may, at its discretion, send a short reminder when a reply approaches its word target without a conclusion. Example:

> *"You're at 1300 / 1500 words; please wrap up your point."*

This is a courtesy, not an interruption — the agent should land the argument promptly, not stop mid-sentence.
