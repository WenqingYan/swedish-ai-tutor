#!/bin/bash
# Create a native macOS development environment for Swedish AI Tutor.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

find_python() {
    local candidate
    for candidate in python3.13 python3.12 python3.11; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            command -v "${candidate}"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python || true)"
if [ -z "${PYTHON_BIN}" ]; then
    echo "Error: Python 3.11 or newer is required."
    echo "Install it first, for example: brew install python@3.12"
    exit 1
fi

echo "Using $(${PYTHON_BIN} --version) at ${PYTHON_BIN}"
"${PYTHON_BIN}" -m venv "${PROJECT_DIR}/.venv"
"${PROJECT_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${PROJECT_DIR}/.venv/bin/python" -m pip install -e "${PROJECT_DIR}[dev]"

mkdir -p "${PROJECT_DIR}/data/audio" \
    "${PROJECT_DIR}/data/lessons" \
    "${PROJECT_DIR}/data/logs"

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
    echo "Created .env from .env.example. Add your API keys before running the app."
fi

echo "macOS environment ready."
echo "Activate it with: source \"${PROJECT_DIR}/.venv/bin/activate\""
echo "Then verify with: python -m swedish_ai_tutor --help"
