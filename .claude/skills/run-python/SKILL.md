---
name: run-python
description: ALWAYS use this when executing Python code/scripts in the science_debate repo. Activates the `science_debate` conda env locally. NEVER use bare python3, conda run, or piped/chained Python (|, &&, &).
user-invocable: false
---

# Run Python

**ALWAYS** use `./scripts/helper_scripts/run_python_cmd.sh` to run any Python code or scripts in this repo. The launcher activates the project's conda env (`science_debate`) before invoking python, so call sites don't need to know about activation.

## Usage

```bash
# Run a script (default science_debate env)
bash ./scripts/helper_scripts/run_python_cmd.sh path/to/script.py arg1 arg2

# Run inline code
bash ./scripts/helper_scripts/run_python_cmd.sh -c "import science_debate; print(science_debate.__version__)"

# Use a different conda env (e.g. for cross-package work)
bash ./scripts/helper_scripts/run_python_cmd.sh --env other_env script.py
```

Internally `run_python_cmd.sh` delegates to `run_conda_bash.sh` (the foundation layer). For non-Python shell commands inside the env, call the foundation directly:

```bash
bash ./scripts/helper_scripts/run_conda_bash.sh -- pytest tests/
bash ./scripts/helper_scripts/run_conda_bash.sh --env science_debate -- pip list
```

## Activation flow

The foundation script:
1. Sources `~/miniforge3/etc/profile.d/conda.sh` (falls back to `conda shell.bash hook` if not found).
2. Sets `PYTHONNOUSERSITE=TRUE` to suppress `~/.local/lib` leakage.
3. Runs `conda activate science_debate` — prepends the env's `bin/` to PATH, sets `CONDA_PREFIX`, and runs per-env `etc/conda/activate.d/*.sh` hooks.
4. Exec's the requested command verbatim.

Why `conda activate` (not direct binary invocation): activation runs the env's `activate.d` hooks (CUDA/MKL setup, library paths) that bare-binary invocations skip.

## NEVER do these

```bash
# BAD: bare python — uses whatever python is first on PATH
python3 -c "..."
python -c "..."

# BAD: manual activation (skips activate.d hooks)
PYTHONNOUSERSITE=TRUE ~/miniforge3/envs/science_debate/bin/python -c "..."

# BAD: conda run (doesn't run activate.d hooks)
conda run -n science_debate python -c "..."

# BAD: source conda.sh in user scripts (the launcher already handles it)
source "$CONDA_PREFIX/etc/profile.d/conda.sh"

# BAD: piping python output through shell tools (truncates errors, hides traceback)
bash run_python_cmd.sh -c "..." | grep pattern | head -5
```
