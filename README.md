# science_debate

AI-agent scientific debates between agents that faithfully represent the views of real, named scientists, in a structured multi-stage tournament format. Real scientists can then comment on the output.

The format addresses a real gap: opinionated commentaries and debates between scientists are widely read but nearly impossible to commission — few scientists will stick their necks out. This package gets faithful agents to do it instead.

## Package contents

All agents, skills, scripts, and the format/faithfulness/journalism specs live under [`debate/`](debate/) — top-level and discoverable. The `.claude/` directory contains symlinks that point into `debate/` so Claude Code can find the agents and skills; the real files are in `debate/`.

- [`debate/FORMAT.md`](debate/FORMAT.md) — the debate format: cast, stage table, audience break-points, transcript line format, quotation rule, tone block.
- [`debate/FAITHFULNESS.md`](debate/FAITHFULNESS.md) — operational criteria for "faithful to the named scientist". Bound on every scientist agent.
- [`debate/JOURNALISM.md`](debate/JOURNALISM.md) — Nature News-and-Views-style writing brief for the journalist agent.
- [`debate/agents/`](debate/agents/) — the [`scientist`](debate/agents/scientist.md) and [`journalist`](debate/agents/journalist.md) agent definitions.
- [`debate/skills/`](debate/skills/) — three slash-commands:
  - [`/run-debate`](debate/skills/run-debate/SKILL.md) — the main orchestration skill (inputs → preparation → multi-stage debate → article).
  - [`/find-adversarial-collaborators`](debate/skills/find-adversarial-collaborators/SKILL.md) — suggest 10 candidate debate / co-author partners for a given scientist.
  - [`/assess-transcript-faithfulness`](debate/skills/assess-transcript-faithfulness/SKILL.md) — critique a passage against [`FAITHFULNESS.md`](debate/FAITHFULNESS.md).
- [`debate/scripts/`](debate/scripts/) — Python scripts for paper / blog / YouTube search and full-text fetching (PMC, bioRxiv, web pages, transcripts).
- [`debate/blog_registry.yaml`](debate/blog_registry.yaml) — seeded list of scientist → blog URL(s); extend freely.
- `debate_events/` — generated, gitignored. One folder per debate run, named `<A-last>_<B-last>_<YYYY-MM-DD>_<6char-hash>/`, containing inputs, briefings, intros, talks, transcript, article.
- `papers_cache/` — generated, gitignored. Shared cache of downloaded papers / blogs / transcripts keyed by DOI / URL hash / video ID. Re-used across debates so the same paper isn't downloaded twice.

## Requirements

[Claude Code](https://code.claude.com) **v2.1.32 or later** (`claude --version`). No tmux / iTerm2 needed — we force [in-process teammate mode](https://code.claude.com/docs/en/agent-teams) (split-pane mode is unsupported in the VSCode integrated terminal anyway).

## How to run

[`.claude/settings.json`](.claude/settings.json) is committed and enables the experimental [Agent Teams](https://code.claude.com/docs/en/agent-teams) feature plus a narrow permissions allowlist for `debate/scripts/` and `debate_events/` writes. **Cloning the repo + opening it in Claude Code is the whole setup.** Then invoke `/run-debate` and follow the prompts.

### Easiest for trying it out — claude.ai/code (web)

Open [claude.ai/code](https://claude.ai/code), load this repo, invoke `/run-debate`. No install. The web sandbox is **ephemeral**: `debate_events/` and `papers_cache/` live only for that session and are lost when it ends. Nothing is downloaded to your local machine. **Run `/export` at the end of the debate to download the full conversation (article + transcript) before closing the tab.**

For a step-by-step walkthrough aimed at non-technical readers, see [GETTING_STARTED.md](GETTING_STARTED.md).

### Recommended for serious use — VSCode plugin, Claude desktop app, or terminal

All three are the same Claude Code harness running locally. Files persist on your local filesystem at the repo path, indefinitely. `papers_cache/` is re-used across debates, so the same paper isn't re-fetched.

### Python environment

Scripts under [`debate/scripts/`](debate/scripts/) are invoked through the project's helper wrappers ([`.claude/rules/helper-scripts.md`](.claude/rules/helper-scripts.md)). The wrappers auto-detect whether conda is available: locally they activate the `science_debate` conda env; on claude.ai/code (web) where conda isn't present, they fall back to running the command against whatever Python is on PATH — the invocation interface stays the same either way. **The `/run-debate` skill installs the project's Python deps for you on first run**, so you don't need to do this manually. If you want to install them yourself:

```bash
bash scripts/helper_scripts/run_conda_bash.sh -- pip install -e .
# Add pytest/coverage only if you plan to run the test suite:
bash scripts/helper_scripts/run_conda_bash.sh -- pip install pytest pytest-cov coverage
```

(The project's `pyproject.toml` uses PEP 735 `[dependency-groups]` for test-runner deps, which standard `pip install -e ".[dev,test]"` doesn't pick up — hence the two commands.)

### YouTube transcripts — works out of the box

YouTube search uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) by default — no API key, no setup. Transcripts are downloaded with `youtube-transcript-api` (also keyless). Slightly slower (~1–2 s per search) and occasionally fragile when YouTube changes their pages, but reliable enough for debate prep.

**Optional**: for faster and more reliable search, get a free YouTube Data API v3 key from [console.cloud.google.com](https://console.cloud.google.com/) (10 000 queries/day, no billing required even if you exceed quota — search just stops). Add it to your global `~/.claude/settings.json` env block:

```json
{
  "env": { "YOUTUBE_API_KEY": "AIza…" }
}
```

`search_youtube.py` auto-prefers the API backend whenever the env var is set and falls back to yt-dlp otherwise. It prints which backend it used to stderr so you always know which path ran.

## Acknowledgement

The debate format is loosely adapted from a long-running national high-school biology tournament — a well-tested structure for staged, role-rotating scientific discussion. Original role terms in that tournament: *Доповідач* = Presenter, *Опонент* = Opponent, *Рецензент* = Reviewer.

## Citation

> t.b.a

## Contact

For questions and help requests, reach out in the [scverse discourse](https://discourse.scverse.org/). For bugs, use the [issue tracker](https://github.com/vitkl/science_debate/issues).
