#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Run bash setup.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m vivi.updater "$@"
