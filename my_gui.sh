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

# Exit on error
set -e

# SAFETY TRAP
trap 'echo ""; echo "[FATAL ERROR] The launcher terminated unexpectedly."; echo "Press Enter to close this window..."; read' ERR

# User Configurable List: Standard Linux terminals with proper Emoji/UTF-8 support.
PREFERRED_TERMINALS=("xfce4-terminal" "gnome-terminal" "mate-terminal")

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# API KEY EXTRACTION (Bypassing non-interactive shell limitations)
# ---------------------------------------------------------------------------
# If the key is not already set, we grep it directly from common config files.
if [ -z "$GEMINI_API_KEY" ]; then
    echo "[INFO] Searching for GEMINI_API_KEY in user profile files..."
    for file in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.zshrc"; do
        if [ -f "$file" ]; then
            # Extract the line containing the key, strip 'export', quotes, and spaces
            EXTRACTED_KEY=$(grep -E "^(export )?GEMINI_API_KEY=" "$file" | tail -n 1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
            if [ -n "$EXTRACTED_KEY" ]; then
                export GEMINI_API_KEY="$EXTRACTED_KEY"
                echo "[INFO] GEMINI_API_KEY successfully extracted from $file"
                break
            fi
        fi
    done
fi

if [ -z "$GEMINI_API_KEY" ]; then
    echo "[WARNING] GEMINI_API_KEY could not be found."
    echo "[WARNING] The Phone Assistant daemon will fail if the key is required."
fi
# ---------------------------------------------------------------------------

# 1. DYNAMIC DETECTION: Search for local virtual environments (venv or virtualenv)
VENV_DIR=""
for dir in "venv" ".venv" "env" "virtualenv"; do
    if [ -d "$dir" ]; then
        VENV_DIR="$dir"
        break
    fi
done

# 2. DYNAMIC DETECTION: Search for Conda/Mamba/Miniforge installations in HOME
CONDA_DIR=""
for dir in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda" "$HOME/anaconda"; do
    if [ -d "$dir" ]; then
        CONDA_DIR="$dir"
        break
    fi
done

# 3. ENVIRONMENT ACTIVATION: Activate the detected environment
ACTIVATION_CMD="true" # Default fallback (do nothing)

if [ -n "$VENV_DIR" ]; then
    echo "[INFO] Activating local Python virtual environment ($VENV_DIR)..."
    source "$VENV_DIR/bin/activate"
    ACTIVATION_CMD="source $VENV_DIR/bin/activate"
elif [ -n "$CONDA_DIR" ]; then
    echo "[INFO] Conda-based installation detected at $CONDA_DIR"
    source "$CONDA_DIR/etc/profile.d/conda.sh"
    echo "[INFO] Activating Conda 'base' environment..."
    conda activate base
    ACTIVATION_CMD="source $CONDA_DIR/etc/profile.d/conda.sh && conda activate base"
else
    echo "[WARNING] No local virtual environment (venv/virtualenv) or Conda-based installation found."
    echo "[INFO] Attempting to run with system Python..."
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
# We explicitly inject the extracted GEMINI_API_KEY into the new terminal's environment
DAEMON_CMD="export GEMINI_API_KEY=\"$GEMINI_API_KEY\"; cd \"$SCRIPT_DIR\"; $ACTIVATION_CMD; python3 phone_assistant.py; echo \"\"; echo \"[Process Stopped] Press Enter to exit...\"; read"

# Launch the daemon
if [ -n "$SELECTED_TERMINAL" ]; then
    echo "[INFO] Found emoji-supported terminal: $SELECTED_TERMINAL"
    echo "[INFO] Starting AI Phone Assistant daemon in a new window..."
    
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
            "$SELECTED_TERMINAL" -e bash -c "$DAEMON_CMD" &
            ;;
    esac
else
    echo "[WARNING] No preferred emoji-supported terminal found."
    echo "[INFO] Launching the AI Phone Assistant daemon in the background of the current terminal..."
    
    # Run in the background of the current terminal
    export GEMINI_API_KEY="$GEMINI_API_KEY"
    python3 phone_assistant.py &
    DAEMON_PID=$!
    
    trap "echo '[INFO] Stopping background daemon...'; kill $DAEMON_PID 2>/dev/null" EXIT
fi

# Launch the Streamlit application in the current terminal
echo "[INFO] Starting AI Switchboard Web Interface..."
streamlit run gui.py
