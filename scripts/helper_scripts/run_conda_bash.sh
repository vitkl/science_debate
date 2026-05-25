#!/bin/bash
# Local conda env activator + bash command runner. Activates the science_debate
# conda env on Mac, then exec's an arbitrary bash command inside it.
#
# Usage:
#   bash scripts/helper_scripts/run_conda_bash.sh [--env NAME] -- <bash command...>
#
# Examples:
#   bash scripts/helper_scripts/run_conda_bash.sh -- python --version
#   bash scripts/helper_scripts/run_conda_bash.sh --env science_debate -- pytest tests/
#
# This is the FOUNDATION layer. run_python_cmd.sh is a thin wrapper on top that
# adds `python <script>` / `python -c <code>` argument shaping.

set -euo pipefail

# --- Parse leading flags up to `--` ---
ENV_NAME="science_debate"

while [[ $# -gt 0 ]]; do
    case "${1:-}" in
        --env)
            shift
            ENV_NAME="${1:-}"
            if [[ -z "$ENV_NAME" ]]; then
                echo "ERROR: --env requires a value" >&2; exit 2
            fi
            shift
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "ERROR: unknown flag or missing '--' separator before bash command: $1" >&2
            echo "Usage: bash $0 [--env NAME] -- <bash command...>" >&2
            exit 2
            ;;
    esac
done

if [[ $# -eq 0 ]]; then
    echo "ERROR: no bash command given after --" >&2
    echo "Usage: bash $0 [--env NAME] -- <bash command...>" >&2
    exit 2
fi

# --- Platform check (local-only; Mac for now) ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: this launcher currently supports macOS only. Adapt run_conda_bash.sh if extending to other hosts." >&2
    exit 3
fi

# --- Ensure conda is available as a shell function ---
set +u
if [[ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/miniforge3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
else
    echo "ERROR: conda not found. Install miniforge3 or set up conda on PATH." >&2
    exit 4
fi
set -u

if ! type conda 2>/dev/null | head -1 | grep -q "function"; then
    echo "ERROR: conda is not available as a shell function; cannot run 'conda activate'." >&2
    exit 5
fi

# --- Activate ---
export PYTHONNOUSERSITE=TRUE
conda activate "$ENV_NAME"

# --- Exec the bash command verbatim ---
exec "$@"
