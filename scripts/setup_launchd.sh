#!/bin/bash
# Install the weekday pipeline as a macOS launchd user agent.

set -euo pipefail

LABEL="com.swedish-ai-tutor.daily"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${PROJECT_DIR}/data/logs"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "Error: virtual environment not found. Run ./scripts/setup_macos.sh first."
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "Error: .env is missing. Copy .env.example to .env and add your API keys."
    exit 1
fi

mkdir -p "${LOG_DIR}" "${PLIST_DIR}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>-m</string>
        <string>swedish_ai_tutor</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>7</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>7</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>7</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>7</integer></dict>
        <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>7</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd-error.log</string>
</dict>
</plist>
EOF

plutil -lint "${PLIST_PATH}"
launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"

echo "Installed ${LABEL}; it runs at 07:00 Monday-Friday."
echo "Logs: ${LOG_DIR}/launchd.log and ${LOG_DIR}/launchd-error.log"
echo "Remove: launchctl bootout gui/$(id -u) \"${PLIST_PATH}\""
