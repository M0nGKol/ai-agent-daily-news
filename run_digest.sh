#!/usr/bin/env bash
# Run the AI engineering news digest on demand, anytime.
#
#   ./run_digest.sh           # collect, curate, summarize, post to Telegram
#
# Forces DIGEST_MODE=digest so it always runs the news pipeline regardless of
# what .env defaults to. Reads secrets/keys from .env.
set -euo pipefail

cd "$(dirname "$0")"

# Activate the local virtualenv if present (created with Python 3.11+).
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

DIGEST_MODE=digest exec python -m app.jobs.run "$@"
