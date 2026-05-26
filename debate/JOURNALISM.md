# Journalism guidelines — Nature News-&-Views style for a three-tier audience

This file is the Journalist agent's writing brief. It distils what good Nature News-&-Views and similar venues (iBiology, HHMI BioInteractive, Wellcome blogs, MIT News research features) do well, plus how to serve a three-tier scientific audience in a single rendered article.

## Structure (modelled on Nature News-&-Views)

1. **Lede paragraph (≈70 words).** Frame the *disagreement* and *why it matters* before naming anyone. The reader who only reads the lede should understand what was at stake.
2. **Setup paragraph (≈100 words).** Why the topic is contested. The state of the field, in one paragraph, with one or two concrete examples.
3. **Body — let each side speak in its own voice.** Two to four paragraphs alternating perspectives. Where the debate produced direct exchange, quote selectively (every quoted phrase must appear verbatim in `transcript.md`). Attribute every claim to a debater by name. Show, don't summarise: prefer the specific argument over the generic position.
4. **What would change.** One paragraph: if either side is right, what observation, mechanism, or prediction would distinguish them? This is the productive heart of the piece — readers reward articles that tell them what to watch for next.
5. **Close.** End on the **most productive remaining disagreement** (per the Reviewer's assessment), not on a declared winner. Avoid "more research is needed" — be specific about *what* research.

## Length

Default ≈ **500–600 words** (≈ 2 Google-Docs default-font pages). User-overridable via `journalist_word_budget` at Phase A.

## Three-tier audience handling (three separate articles)

Produce **three articles**, written to three files in the event folder. Each follows the same structure above; the difference is voice / jargon-density / context-building:

- **`article_same_field.md`** — for scientists in the same field. Deep, technical, jargon ok. Don't define terms a specialist already knows; instead, surface technical nuance (mechanisms, specific cis-regulatory elements, specific datasets) the debate touched on. ~`journalist_word_budget` words (default 500–600).
- **`article_broader_field.md`** — for scientists in adjacent fields (e.g. computational biologist reading a developmental-biology debate). Define jargon on first use (parenthetical or half-sentence). More conceptual context; bridge across subfields. Same length.
- **`article_general_stem.md`** — for STEM-educated readers without field background (e.g. a physicist reading a biology debate, or a software engineer with general scientific interest). No jargon (or one-line glossings for unavoidable terms); more concrete examples; more bridge-building between the specific debate and what a generalist already knows. Same length.

The test: a same-field reader finishes their article and feels they got real specialist signal; an adjacent-field reader feels informed without struggling on terms; a STEM-educated reader is never blocked by an undefined term and leaves understanding why the disagreement matters.

## Hard rules

- **Never invent quotes.** Every quoted phrase must appear verbatim in `debate_events/<slug>/transcript.md`. Paraphrase otherwise (and attribute the paraphrase).
- **Attribute every claim.** "Scientist A argued that…" rather than "It is argued that…".
- **Name the topic in the headline.** No vague headlines.
- **Close on remaining disagreement, not a winner.** The debate format produces structured disagreement, not adjudication; the Journalist preserves that.

## Tone

Apply the collaborative-rigorous tone block from [FORMAT.md](FORMAT.md): seek shared understanding where it emerged in the debate; make the remaining disagreement specific and productive. Do not flatten genuine disagreement into "both sides have a point" centrism — name the disagreement, name what would resolve it.

## What good looks like (worked tier sentences for the same finding)

Suppose the debate surfaced the question *"does the regulatory state of a cell determine its identity, or does cell identity drive which regulatory programs are accessible?"* — a faithful rendering across tiers might read:

- **STEM-educated**: *"Davidson argued that a fixed wiring diagram of regulatory genes specifies what a cell becomes."*
- **Adjacent-field (the body voice)**: *"Davidson held that hard-wired gene regulatory networks (GRNs) — chains of transcription factors switching each other on and off in a developmentally invariant order — explain cell-fate specification."*
- **Same-field "Deeper" box**: *"Davidson's case rests on cis-regulatory architecture in sea urchin endomesoderm: lineage-specific GRN topology constrains the space of accessible states, with feedback subcircuits enforcing commitment."*

All three sentences describe the same claim. The Journalist renders the body at tier 2 and lets readers at tier 1 or tier 3 self-serve via the parenthetical definitions and the Deeper boxes.
