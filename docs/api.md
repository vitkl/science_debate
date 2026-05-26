# API

This package's user-facing surface is not a Python API — it is a set of [Claude Code](https://code.claude.com) agents and skills under [`debate/`](../debate/). Start with [`debate/FORMAT.md`](../debate/FORMAT.md) for the debate-format specification and [`debate/skills/run-debate/SKILL.md`](../debate/skills/run-debate/SKILL.md) for the main workflow.

A Python API may be added later for direct programmatic use of the supporting scripts under [`debate/scripts/`](../debate/scripts/). Until then, invoke those scripts through the helper wrappers (see [`.claude/rules/helper-scripts.md`](../.claude/rules/helper-scripts.md)).
