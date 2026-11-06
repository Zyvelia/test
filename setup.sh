#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -c 'import sys; sys.exit("Python 3.11 or newer is required") if sys.version_info < (3,11) else None'
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
if [[ ! -e .env ]]; then
  (umask 077; cp .env.example .env)
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Music is optional: install FFmpeg (see docs/LINUX.md) before enabling it."
fi
printf '%s\n' 'Vivi setup complete. Edit .env privately, then run bash start.sh.'
