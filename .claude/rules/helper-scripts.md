---
description: Mandatory rules for running Python and bash commands inside the science_debate conda env — loaded every session
---

# Helper Script Rules

All Python execution and any bash command that needs the project's conda env (`science_debate`) MUST go through the helper scripts. The launchers handle `conda activate` + `activate.d` hooks; call sites stay simple.

## Python Execution

- ALWAYS use `bash scripts/helper_scripts/run_python_cmd.sh` to run Python.
- Default env: `science_debate`. Override with `--env NAME` if needed.

```bash
# Run a script
bash scripts/helper_scripts/run_python_cmd.sh path/to/script.py arg1 arg2

# Inline code
bash scripts/helper_scripts/run_python_cmd.sh -c "import science_debate; print(science_debate.__version__)"
```

See [.claude/skills/run-python/SKILL.md](../../.claude/skills/run-python/SKILL.md) for the full skill spec.

## Any Other Bash Command That Needs the Env

For non-Python commands that need the env (`pytest`, `pip`, `hatch`, `pre-commit`, `gh` if installed in-env, etc.) use the foundation directly:

```bash
bash scripts/helper_scripts/run_conda_bash.sh -- pytest tests/
bash scripts/helper_scripts/run_conda_bash.sh -- pip install -e ".[dev,test]"
bash scripts/helper_scripts/run_conda_bash.sh -- hatch run docs:build
bash scripts/helper_scripts/run_conda_bash.sh --env science_debate -- pre-commit run --all-files
```

The `--` separator is mandatory; everything after it is exec'd verbatim inside the activated env.

## NEVER Do These

- Bare `python3` / `python` — uses whatever's first on PATH (often the system Python, wrong site-packages).
- `conda run -n science_debate python ...` — skips `activate.d` hooks (CUDA/MKL/library-path setup).
- Manual env activation: `~/miniforge3/envs/science_debate/bin/python ...` — same problem; also leaks `~/.local/lib` unless you also set `PYTHONNOUSERSITE`.
- `source $CONDA_PREFIX/etc/profile.d/conda.sh && conda activate ...` inline — the launchers already do this. Don't double-activate.
- Piping Python output through `| grep`, `| head`, etc. — truncates tracebacks and hides errors. Capture the full output, then inspect.
- Long chained commands (`cmd1 && cmd2 ; cmd3 | head`) inside a helper invocation — split into separate calls so each tool result is inspectable on its own.

## Why this matters

`conda activate` runs the env's `etc/conda/activate.d/*.sh` hooks (CUDA paths, MKL threading, env-specific `LD_LIBRARY_PATH`, etc.). Bypassing activation — even by calling the env's python binary directly — skips those hooks and produces subtly wrong runs.
