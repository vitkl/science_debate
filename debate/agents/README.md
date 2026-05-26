# Agents

Two agent definitions live here. Both are spawned as Claude Code [Agent Teams](https://code.claude.com/docs/en/agent-teams) teammates by the [`run-debate`](../skills/run-debate/SKILL.md) skill.

- [`scientist.md`](scientist.md) — faithfully represents a real named scientist. Switches between Presenter, Opponent, and Reviewer modes per the [stage table in FORMAT.md](../FORMAT.md). Three instances are spawned per debate (A, B, C). Reads its identity from `debate_events/<slug>/briefing_<self>.md` and treats [`FAITHFULNESS.md`](../FAITHFULNESS.md) as binding.
- [`journalist.md`](journalist.md) — writes the public-facing summary article in Nature News-and-Views style. Reads [`JOURNALISM.md`](../JOURNALISM.md) as its writing brief.

The [`.claude/agents/`](../../.claude/agents/) directory contains symlinks to these files so Claude Code can discover them; the real files live here.
