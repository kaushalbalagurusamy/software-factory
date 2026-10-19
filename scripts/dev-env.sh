#!/usr/bin/env bash
# Create or refresh the local dev environment (.venv, gitignored). Idempotent.
#   UNITY_REPO   Unity checkout to install editable (default: ~/Projects/unity)
#   PYTHON       interpreter to build the venv with (default: python3)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
UNITY_REPO="${UNITY_REPO:-$HOME/Projects/unity}"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating $VENV with $($PYTHON --version 2>&1)"
  "$PYTHON" -m venv "$VENV"
else
  echo "Reusing $VENV"
fi

"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements.txt"
echo "Installed base requirements from requirements.txt"
"$VENV/bin/python" -m pip install --quiet -e "$ROOT[skills]"
echo "Installed factory CLI and supporting skill schema dependencies"

if [ -d "$UNITY_REPO" ] && [ -f "$UNITY_REPO/pyproject.toml" ]; then
  "$VENV/bin/python" -m pip install --quiet -e "$UNITY_REPO"
  echo "Installed Unity editable from $UNITY_REPO"
else
  echo "Unity NOT installed: no checkout at $UNITY_REPO (set UNITY_REPO)."
  echo "  Semantic audit will report GATE FAILED; tests marked requires_unity will fail."
fi

echo "--- versions ---"
"$VENV/bin/python" --version
"$VENV/bin/python" -c "import z3; print('z3-solver', z3.get_version_string())"
"$VENV/bin/python" -c "import importlib.util as u; print('unity compiler importable:', u.find_spec('compiler') is not None)"
echo "Activate with: source $VENV/bin/activate"
