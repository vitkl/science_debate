---
name: summarise-for-debate
description: Summarise a single source (paper, blog post, transcript, book chapter) through the lens of a specific debate topic. Extract the parts most relevant to the debate, not a generic summary. Use when run-debate Phase B4 needs to compress an over-budget source.
user-invocable: true
---

# Summarise for debate

<section purpose="One-paragraph framing: this skill produces a topic-aware compression of one source, written in the named scientist's voice. Caller picks the model (Haiku default for cost; Sonnet/Opus when quality matters more than spend).">

## What this skill does

Given one source file plus a debate topic + scientist name, produce a topic-aware summary that extracts the parts of the source most useful for an agent representing that scientist in a debate. **Not** a generic abstract — the goal is to compress while preserving the scientist's stance, reasoning, characteristic vocabulary, and quotable phrases for the specified topic.

</section>

<section purpose="Caller-supplied inputs. The model is passed in by the caller (Moderator in run-debate Phase B4); default is haiku for mechanical summaries.">

## Inputs

Caller must provide:
- `source-path`: path to the source file (PMC text, PDF text, web extract, transcript, custom note).
- `topic`: the debate topic (one sentence).
- `scientist`: the named scientist whose source this is.
- `target-words`: target summary length (default 500).
- `out-path`: where to write the summary (default `<source-path>.summary.md`).
- `model`: caller's choice — `haiku` (default; mechanical), `sonnet` (balanced), `opus` (highest quality).

</section>

<section purpose="The summarisation procedure. Step 3 is the critical guard against speaker confusion in multi-speaker transcripts (interviews, podcasts) — without it the agent could defend positions the host or another guest took.">

## Procedure

1. Read the source.
2. Read `debate/FAITHFULNESS.md` to know what 'faithful to the scientist' means in this project.
3. **Speaker attribution check (CRITICAL for interview/podcast transcripts).** Many sources have multiple speakers: interviewer + scientist, panel of scientists, Q&A audience. YouTube transcripts do **not** include speaker labels. Before extracting any view, identify who is speaking using context cues:
   - **Question format**: interviewers ask, scientists answer.
   - **Vocabulary**: the named scientist's characteristic terms vs. the host's.
   - **References**: the named scientist's own papers / collaborators / known positions.
   - **Host signatures**: Sam Harris's free-will framing, Lex Fridman's "love" closings, Joe Rogan's catchphrases, etc.

   If you cannot confidently attribute a passage to the named scientist, **drop it**. Prefer over-conservative attribution to mis-attribution. Misattributed quotes are the failure mode this skill must avoid.
4. Identify the parts of the source most relevant to `<topic>`:
   - The scientist's **stance** on the topic — explicitly stated *by them*, not by host or co-guest.
   - The scientist's **reasoning style**: characteristic analogies, mechanisms they invoke, evidence they cite, objections they raise to received views.
   - **Quotable passages** the scientist might re-use verbatim in a debate (≤ 30 words each, with attribution preserved).
   - **Specific predictions or mechanisms** the scientist names — anything that would distinguish their view from a competing position.
5. **Skip** parts unrelated to `<topic>`: methods sections, generic background, acknowledgements, host monologues, off-topic tangents.
6. Write the summary to `<out-path>`:
   - **First line** — `Source: <title>; relevance to <topic>: <one-line>`.
   - For interview / podcast sources, **add a second line**: `Speaker-attribution confidence: <high|medium|low>; <N> passages dropped due to ambiguous attribution.`
   - Body in the scientist's vocabulary where possible.
   - Preserve quotable phrases with quote characters; never quote host or other-guest text.
   - Keep under `target-words`; if you can't, end with `[summary truncated at target-words]`.

</section>

<section purpose="Hard rules the skill must follow — including the absolute prohibition on attributing host/audience text to the scientist.">

## Hard rules

- **Never attribute** the host's or another guest's words to the named scientist. When in doubt, drop the passage.
- **Never invent** quotes. Every quoted phrase must appear verbatim in the source.
- **Stay within `target-words` ± 10%.**
- **Single source per invocation.** Caller iterates over multiple sources by calling this skill multiple times.

</section>
