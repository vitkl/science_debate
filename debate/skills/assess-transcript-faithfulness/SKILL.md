---
name: assess-transcript-faithfulness
description: Critique a text passage for faithfulness to a named scientist's actual views using debate/FAITHFULNESS.md criteria. Use when run-debate iterates self-intros or talk drafts, or when the user wants to check whether a passage sounds like a named scientist.
user-invocable: true
---

# Assess transcript faithfulness

<section purpose="State the single action this skill performs: score a candidate text against the five faithfulness criteria and return the top three concrete fixes plus a pass/fail verdict against the mirror test.">

Read [`debate/FAITHFULNESS.md`](../../FAITHFULNESS.md). Read the source materials at the path the caller gives you (e.g. `debate_events/<slug>/briefing_<scientist>.md`). Score the candidate text on each of the five criteria — **stance**, **reasoning style**, **rhetorical register**, **vocabulary**, **citation behaviour** — using one sentence per criterion. Name the top **three** concrete fixes the author should make in the next iteration. Give a pass/fail verdict against the mirror test.

</section>
