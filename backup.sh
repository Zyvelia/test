#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Run bash setup.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m vivi.backup "$@"
