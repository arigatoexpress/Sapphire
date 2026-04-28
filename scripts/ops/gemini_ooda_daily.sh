#!/bin/zsh
set -euo pipefail

cd /Users/aribs/Code/Sapphire
export PYTHONPATH="/Users/aribs/Code/Sapphire:${PYTHONPATH:-}"
export SAPPHIRE_GEMINI_LIVE=0

/usr/local/bin/python3 scripts/ops/gemini_ooda_daily.py "$@"
