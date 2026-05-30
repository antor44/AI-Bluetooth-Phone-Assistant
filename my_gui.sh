#!/bin/bash
# AI Switchboard - Web GUI Launcher
# This script automates the virtual environment activation and starts the Streamlit Control Panel.

# Exit immediately if a command exits with a non-zero status
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if the virtual environment directory exists
if [ -d "venv" ]; then
    echo "[INFO] Activating Python virtual environment..."
    source venv/bin/activate
else
    echo "[WARNING] 'venv' directory not found. Attempting to run with system Python..."
fi

# Check if streamlit is installed in the active environment
if ! python3 -c "import streamlit" &> /dev/null; then
    echo "[ERROR] Streamlit is not installed in the active Python environment."
    echo "[INFO] Please run: pip install -r requirements.txt"
    exit 1
fi

# Launch the Streamlit application
echo "[INFO] Starting AI Switchboard Web Interface..."
streamlit run gui.py
