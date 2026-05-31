#!/bin/bash

# my_gui.sh v. 1.0 - AI Switchboard Web GUI & Daemon Launcher
# Automates virtual environment activation, launches the main phone assistant 
# daemon in an emoji-supported terminal, and starts the Streamlit Control Panel.
#
# Copyright (c) 2026 Antonio R.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# https://github.com/antor44/AI-Bluetooth-Phone-Assistant

# Exit immediately if a command exits with a non-zero status
set -e

# User Configurable List: Standard Linux terminals with proper Emoji/UTF-8 support.
# The script will try to use them in this exact order.
PREFERRED_TERMINALS=("xfce4-terminal" "gnome-terminal" "mate-terminal")

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

# Search for the first available terminal from the preferred list
SELECTED_TERMINAL=""
for term in "${PREFERRED_TERMINALS[@]}"; do
    if command -v "$term" &> /dev/null; then
        SELECTED_TERMINAL="$term"
        break
    fi
done

# Command to execute inside the chosen terminal
DAEMON_CMD="cd \"$SCRIPT_DIR\"; [ -d \"venv\" ] && source venv/bin/activate; python3 phone_assistant.py; echo \"\"; echo \"[Process Stopped] Press Enter to exit...\"; read"

# Launch the daemon
if [ -n "$SELECTED_TERMINAL" ]; then
    echo "[INFO] Found emoji-supported terminal: $SELECTED_TERMINAL"
    echo "[INFO] Starting AI Phone Assistant daemon in a new window..."
    
    # Execute with the correct flag depending on the terminal type
    case "$SELECTED_TERMINAL" in
        "xfce4-terminal")
            xfce4-terminal --title="AI Phone Assistant Daemon" --command="bash -c '$DAEMON_CMD'" &
            ;;
        "gnome-terminal")
            gnome-terminal --title="AI Phone Assistant Daemon" -- bash -c "$DAEMON_CMD" &
            ;;
        "mate-terminal")
            mate-terminal --title="AI Phone Assistant Daemon" --command="bash -c '$DAEMON_CMD'" &
            ;;
        *)
            # Generic fallback
            "$SELECTED_TERMINAL" -e bash -c "$DAEMON_CMD" &
            ;;
    esac
else
    echo "[WARNING] No preferred emoji-supported terminal found."
    echo "[INFO] Launching the AI Phone Assistant daemon in the background of the current terminal..."
    
    # Run in the background of the current terminal
    python3 phone_assistant.py &
    DAEMON_PID=$!
    
    # Ensure the background daemon is killed if the user closes Streamlit (Ctrl+C)
    trap "echo '[INFO] Stopping background daemon...'; kill $DAEMON_PID 2>/dev/null" EXIT
fi

# Launch the Streamlit application in the current terminal
echo "[INFO] Starting AI Switchboard Web Interface..."
streamlit run gui.py
