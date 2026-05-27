---
name: assess-transcript-faithfulness
description: Critique a text passage for faithfulness to a named scientist's actual views using debate/FAITHFULNESS.md criteria. Invoked BY THE SCIENTIST AGENT on its own draft during run-debate Phase B5 self-iteration, or by the user as a spot-check. MUST NOT be invoked by the Moderator / run-debate orchestration — judgement belongs with the briefing-holder.
user-invocable: true
---

# Assess transcript faithfulness

<section purpose="State the single action this skill performs: score a candidate text against the five faithfulness criteria and return the top three concrete fixes plus a pass/fail verdict against the mirror test.">

**Caller contract.** This skill is called either (a) by a `scientist` agent on its own draft, where "candidate text" is the draft path the scientist just wrote, or (b) by the user as a spot-check. The Moderator / run-debate orchestration must NOT call this skill — doing so contaminates the Moderator with scientist prep content and duplicates judgement that already sits with the briefing-holder. If you are an orchestration agent invoking this skill, stop and re-read run-debate/SKILL.md §B5a.

Read [`debate/FAITHFULNESS.md`](../../FAITHFULNESS.md). Read the source materials at the path the caller gives you (e.g. `debate_events/<slug>/briefing_<scientist>.md`). Score the candidate text on each of the five criteria — **stance**, **reasoning style**, **rhetorical register**, **vocabulary**, **citation behaviour** — using one sentence per criterion. Name the top **three** concrete fixes the author should make in the next iteration. Give a pass/fail verdict against the mirror test.

</section>
