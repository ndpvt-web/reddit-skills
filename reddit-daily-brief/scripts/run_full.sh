#!/bin/bash
# run_full.sh — Detached end-to-end Reddit Daily Brief.
# Runs harvest (RSS, ~25min) → markdown → compose (gateway-first) → PDF → email
# in ONE background process so it survives session/API interruptions.
# Usage: nohup bash scripts/run_full.sh > logs/run_full_<date>.log 2>&1 &
set -u
cd "$(dirname "$0")/.." || exit 1
DATE=$(date -u +%Y-%m-%d)

# Guard: if a harvest is already running, another orchestrator owns this cycle. Exit.
if [ "$(ps aux | grep -c '[h]arvest_24h')" -gt 0 ]; then
  echo "[run_full] harvest already running — skipping duplicate launch $(date -u +%H:%M:%S)"
  exit 0
fi

# Analysis model: sonnet-4.6/opus/sonnet-5 became model_access_denied on this plan
# (2026-08). haiku-4.5 is the only accessible model. Revert this line to
# anthropic/claude-sonnet-4.6 once the plan is upgraded to restore higher-quality analysis.
export REDDIT_BRIEF_MODEL="${REDDIT_BRIEF_MODEL:-anthropic/claude-haiku-4.5}"

echo "[run_full] start $DATE $(date -u +%H:%M:%S) model=$REDDIT_BRIEF_MODEL"

# 1. Back up any existing daily JSONs so 0-post subs don't carry stale data
mkdir -p "outputs/daily/_backup_${DATE}_run"
mv outputs/daily/*.json "outputs/daily/_backup_${DATE}_run/" 2>/dev/null
echo "[run_full] backed up prior daily JSONs"

# 2. Harvest last 24h via RSS
echo "[run_full] harvesting..."
python3 scripts/harvest_24h.py --output outputs/daily
echo "[run_full] harvest done $(date -u +%H:%M:%S)"

# 3. Generate markdown (pipeline skips this under --skip-harvest, so do it explicitly)
python3 scripts/to_markdown.py --input-dir outputs/daily --output-dir outputs/markdown
echo "[run_full] markdown done"

# 4. Compose (gateway-first) + PDF + email; NotebookLM upload stays off (needs a Mac)
python3 scripts/pipeline.py --skip-harvest --skip-upload --date "$DATE"
echo "[run_full] complete $DATE $(date -u +%H:%M:%S)"
