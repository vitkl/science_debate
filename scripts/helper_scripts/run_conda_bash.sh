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

# --- Try to activate conda env; fall back to running the command bare if conda
#     isn't available (e.g. claude.ai/code web sandbox, CI containers).
set +u
CONDA_OK=0
if [[ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/miniforge3/etc/profile.d/conda.sh"
    CONDA_OK=1
elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    CONDA_OK=1
fi

if (( CONDA_OK == 1 )) && type conda 2>/dev/null | head -1 | grep -q "function"; then
    if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$ENV_NAME"; then
        export PYTHONNOUSERSITE=TRUE
        conda activate "$ENV_NAME"
        set -u
        exec "$@"
    else
        echo "WARNING: conda env '$ENV_NAME' not found; running command without env activation. Run pip install -e \".[dev,test]\" first if you need the project deps." >&2
    fi
else
    echo "WARNING: conda not found; running command without env activation. Make sure the required Python deps are installed (pip install -e \".[dev,test]\")." >&2
fi
set -u

# --- Fallback: exec the command bare so the same wrapper works everywhere ---
exec "$@"
