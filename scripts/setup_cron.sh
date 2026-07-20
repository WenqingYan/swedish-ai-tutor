#!/bin/bash
# Setup cron job for the Swedish AI Tutor daily pipeline.
#
# Runs every weekday at 07:00 (configurable below).
# Logs output to ./data/logs/pipeline_YYYY-MM-DD.log
#
# Usage:
#   chmod +x scripts/setup_cron.sh
#   ./scripts/setup_cron.sh

set -euo pipefail

# Configuration
SCHEDULE="0 7 * * 1-5"  # 07:00 Monday-Friday
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${PROJECT_DIR}/data/logs"

# Validate
if [ ! -f "${VENV_PYTHON}" ]; then
    echo "Error: Virtual environment not found at ${PROJECT_DIR}/.venv"
    echo "Run: python3 -m venv .venv && pip install -e '.[dev]'"
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "Error: .env file not found."
    echo "Copy .env.example to .env and fill in your API keys."
    exit 1
fi

# Create log directory
mkdir -p "${LOG_DIR}"

# Build the cron command
CRON_CMD="${SCHEDULE} cd ${PROJECT_DIR} && ${VENV_PYTHON} -m swedish_ai_tutor run >> ${LOG_DIR}/pipeline_\$(date +\%Y-\%m-\%d).log 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -q "swedish_ai_tutor"; then
    echo "Cron job already exists. Removing old entry..."
    crontab -l | grep -v "swedish_ai_tutor" | crontab -
fi

# Install new cron job
(crontab -l 2>/dev/null; echo "${CRON_CMD}") | crontab -

echo "✅ Cron job installed!"
echo ""
echo "Schedule: ${SCHEDULE} (Weekdays at 07:00)"
echo "Command: python -m swedish_ai_tutor run"
echo "Logs: ${LOG_DIR}/pipeline_YYYY-MM-DD.log"
echo ""
echo "To verify: crontab -l"
echo "To remove: crontab -l | grep -v 'swedish_ai_tutor' | crontab -"
