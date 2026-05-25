#!/bin/bash
# Local Python launcher. Thin wrapper on top of run_conda_bash.sh that forwards
# `python <script> [args...]` or `python -c <code>` to the foundation layer,
# which activates the science_debate conda env first.
#
# Usage:
#   bash scripts/helper_scripts/run_python_cmd.sh <script.py> [args...]
#   bash scripts/helper_scripts/run_python_cmd.sh -c "<python code>"
#   bash scripts/helper_scripts/run_python_cmd.sh --env <name> <script> [args...]

set -euo pipefail

# --- Parse leading flags ---
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
        *)
            break
            ;;
    esac
done

# --- Build the python invocation ---
if [[ "${1:-}" == "-c" ]]; then
    shift
    CODE="${1:-}"
    if [[ -z "$CODE" ]]; then
        echo "ERROR: -c requires a code string" >&2; exit 2
    fi
    shift || true
    PY_ARGS=(python -c "$CODE" "$@")
elif [[ $# -eq 0 ]]; then
    echo "ERROR: no script or -c command given" >&2
    echo "Usage: bash $0 [--env NAME] <script.py> [args...]" >&2
    echo "       bash $0 [--env NAME] -c \"<code>\"" >&2
    exit 2
else
    PY_ARGS=(python "$@")
fi

# --- Delegate to run_conda_bash.sh ---
DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$DIR/run_conda_bash.sh" --env "$ENV_NAME" -- "${PY_ARGS[@]}"
