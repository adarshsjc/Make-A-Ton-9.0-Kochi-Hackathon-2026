#!/usr/bin/env bash
set -euo pipefail
if command -v python3.12 >/dev/null 2>&1; then
  python3.12 -m venv .venv
elif command -v uv >/dev/null 2>&1; then
  uv python install 3.12
  uv venv --python 3.12 .venv
else
  echo "Python 3.12 not found. Install python3.12 or install uv first." >&2
  exit 1
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [[ ! -f .env ]]; then cp .env.example .env; fi
echo "Environment installed. Edit .env, then run migrations as described in README.md."
