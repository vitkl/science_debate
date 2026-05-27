# Debate format — the rules

This file is the single source of truth for the debate format. Every agent definition and the `run-debate` skill references it rather than re-stating the rules.

## Cast (five roles)

- **Moderator** — the lead Claude Code session. Sets up the team, runs the stage clock, prints the stage table when `run-debate` is invoked, materialises stages as TODOs once the debate starts, reads per-stage files and concatenates them into `transcript.md`, prints each new stage as a formatted markdown block to chat, runs the audience-break sequence, renders per-break audio segments, runs the `/usage` baseline/delta, and may nudge a scientist to wrap up when they're near their word target with no conclusion in sight. Default model: **`claude-opus-4-7[1m]`** (1M-context Opus — the role is no longer purely procedural; cumulative context from Phase B briefings + Phase C transcript reads exceeds 200k for an 80-minute debate).
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
| 8 | Final rejoinders A → B (round 1) | A, B as Presenter — runs as **sub-stages 8a then 8b** (sequential; B reads transcript including A's just-appended 8a before composing 8b — real-room order) | 4 + 4 | 400 + 400 | yes (single break after the pair, i.e. after 8b) |
| 9 | Reviewer assessment (round 2) | Reviewer C | 4 | 400 | yes |
| 10 | Final rejoinders A → B (round 2) | A, B as Presenter — runs as **sub-stages 10a then 10b** (same shape as 8a/8b) | 4 + 4 | 400 + 400 | yes (single break after 10b) |
| — | Journalist write-up | Journalist | n/a | ~500–600 (≈2 GDocs pages), user-tunable | (end) |

## Clarifying-question rounds

After stages **1, 2, 3, 5** the Moderator runs an intra-stage clarifying-question round before the audience break (if any). The two non-speakers each ask the stage's speaker one ≤30-word clarifying question; the speaker answers each in ≤50 words. The round is sequential in real-room order: Q from first non-speaker → A from speaker → Q from second non-speaker → A from speaker. Word targets are truthful but unenforced (the Moderator does not truncate overruns).

Speaker per round:

| After stage | Speaker | Askers (in turn order) |
|---|---|---|
| 1 (Presenter A talk) | A | B, then C |
| 2 (Presenter B talk) | B | A, then C |
| 3 (Opponent B critiques A) | B | A, then C |
| 5 (Opponent A critiques B) | A | B, then C |

Each utterance becomes its own per-stage file (`stage_<NN>_q<n>_<asker>.md`, `stage_<NN>_a<n>_<speaker>.md`). The Moderator concatenates each into `transcript.md` as the round progresses. Clarifying rounds do NOT trigger audience breaks — those still fire only after stages listed below.

## Audience break-points

After stages 1, 2, 4, 6, 7, 8, 9, 10 the Moderator pauses and asks the user (the audience) for a question, comment, or "continue". Default audience-time budget: ~3 minutes (~300 words). Audience text is double-written: one JSONL line to `audience.log` (structured audit) and one `**Audience:** <text>` block concatenated into `transcript.md` at the clock stage. Forwarded responses (multi-target sequential, A → B → C in turn order) become per-stage files `audience_q<NN>_<X>.md` that the Moderator concatenates into the transcript as they land — so the next target reads the prior target's response before composing.

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
