#!/usr/bin/env bash
# my_gui.sh v. 2.8 - AI Switchboard Web GUI & Daemon Launcher
# Automates virtual environment activation, launches the main phone assistant 
# daemon, and starts the Streamlit Control Panel (Optimized for Headless/LAN).
#
# Author: Antonio R.
# Version: 2.8
# License: GPL 3.0
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

# Usage:
#   ./my_gui.sh            Desktop session detected: Web GUI is local only.
#                          No desktop session detected: Web GUI is opened to the LAN.
#   ./my_gui.sh --lan      Always open the Web GUI to the LAN (alias: --headless).
#   ./my_gui.sh --local    Never open the Web GUI to the LAN, even without a desktop session.
#   ./my_gui.sh --logs     Follow the live log of the daemon.

# Exit on error
set -e

# SAFETY TRAP
trap 'echo ""; echo "[FATAL ERROR] The launcher terminated unexpectedly."; echo "Press Enter to close this window..."; read' ERR

# Ensure PipeWire and D-Bus user session variables are exported in SSH/headless sessions
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# User Configurable List: Standard Linux terminals with proper Emoji/UTF-8 support.
PREFERRED_TERMINALS=("xfce4-terminal" "gnome-terminal" "mate-terminal")

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Live console log settings
SERVICE_NAME="ai-switchboard.service"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/daemon.log"
LOG_MAX_BYTES=5242880

# Live log viewer (./my_gui.sh --logs). Ctrl+C closes the viewer only; the service keeps running.
show_logs() {
    trap - ERR
    trap 'echo ""; echo "[INFO] Log view closed. The service keeps running."; exit 0' INT
    if systemctl --user is-active --quiet "$SERVICE_NAME" 2> /dev/null; then
        echo "[INFO] Following the journal of $SERVICE_NAME (press Ctrl+C to leave without stopping the service)..."
        if [ -n "$(journalctl --user -u "$SERVICE_NAME" -n 1 -q -o cat 2>/dev/null)" ]; then
            journalctl --user -u "$SERVICE_NAME" -f -n 100 -a -o cat
        else
            # Some systems keep user services in the system journal (no per-user journal files).
            echo "[INFO] No per-user journal found; reading the system journal instead (the user must belong to the 'systemd-journal' or 'adm' group)."
            journalctl "_SYSTEMD_USER_UNIT=$SERVICE_NAME" -f -n 100 -a -o cat
        fi
    elif [ -f "$LOG_FILE" ]; then
        echo "[INFO] Following $LOG_FILE (press Ctrl+C to leave without stopping the service)..."
        tail -n 100 -F "$LOG_FILE"
    else
        echo "[ERROR] No logs found: the systemd service $SERVICE_NAME does not exist and $LOG_FILE has not been created yet."
        exit 1
    fi
    exit 0
}

# ---------------------------------------------------------------------------
# ARGUMENT PARSING
# ---------------------------------------------------------------------------
FORCE_HEADLESS=0
FORCE_LOCAL=0
for arg in "$@"; do
    if [ "$arg" == "--headless" ] || [ "$arg" == "--lan" ]; then
        FORCE_HEADLESS=1
        echo "[INFO] Manual argument detected: Forcing Headless/LAN mode."
    elif [ "$arg" == "--local" ]; then
        FORCE_LOCAL=1
        echo "[INFO] Manual argument detected: Web GUI will only listen on this device (no LAN exposure)."
    elif [ "$arg" == "--logs" ]; then
        show_logs
    fi
done

if [ "$FORCE_HEADLESS" = "1" ] && [ "$FORCE_LOCAL" = "1" ]; then
    echo "[ERROR] --local cannot be combined with --lan or --headless."
    exit 1
fi

# ---------------------------------------------------------------------------
# API KEY EXTRACTION (Bypassing non-interactive shell limitations)
# ---------------------------------------------------------------------------
if [ -z "$GEMINI_API_KEY" ]; then
    echo "[INFO] Searching for GEMINI_API_KEY in user profile files..."
    for file in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.zshrc"; do
        if [ -f "$file" ]; then
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
ACTIVATION_CMD="true"

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

# Options passed to every Streamlit launch. runner.postScriptGC=false skips the full garbage collection that Streamlit
# forces after every script run: on slow ARM boards (e.g. Orange Pi Zero 3) it added several seconds to each page load.
STREAMLIT_COMMON_OPTS="--runner.postScriptGC=false"

# Search for the first available terminal from the preferred list
SELECTED_TERMINAL=""
for term in "${PREFERRED_TERMINALS[@]}"; do
    if command -v "$term" &> /dev/null; then
        SELECTED_TERMINAL="$term"
        break
    fi
done

# Command to execute inside the chosen terminal
DAEMON_CMD="export GEMINI_API_KEY=\"$GEMINI_API_KEY\"; export XDG_RUNTIME_DIR=\"$XDG_RUNTIME_DIR\"; export DBUS_SESSION_BUS_ADDRESS=\"$DBUS_SESSION_BUS_ADDRESS\"; cd \"$SCRIPT_DIR\"; $ACTIVATION_CMD; python3 phone_assistant.py; echo \"\"; echo \"[Process Stopped] Press Enter to exit...\"; read"

# Launch the daemon
if [ -n "$SELECTED_TERMINAL" ] && [ -n "$DISPLAY" ] && [ "$FORCE_HEADLESS" = "0" ]; then
    echo "[INFO] Found emoji-supported terminal: $SELECTED_TERMINAL"
    echo "[INFO] Starting AI Phone Assistant daemon in a new window..."

    case "$SELECTED_TERMINAL" in
        "xfce4-terminal")
            xfce4-terminal --title="AI Phone Assistant Daemon v2.8" --command="bash -c '$DAEMON_CMD'" &
            ;;
        "gnome-terminal")
            gnome-terminal --title="AI Phone Assistant Daemon v2.8" -- bash -c "$DAEMON_CMD" &
            ;;
        "mate-terminal")
            mate-terminal --title="AI Phone Assistant Daemon v2.8" --command="bash -c '$DAEMON_CMD'" &
            ;;
        *)
            "$SELECTED_TERMINAL" -e bash -c "$DAEMON_CMD" &
            ;;
    esac
else
    if [ "$FORCE_HEADLESS" = "1" ]; then
        echo "[INFO] Headless mode forced. Skipping GUI terminal launch."
    else
        echo "[WARNING] No desktop environment or preferred terminal found (Headless Mode)."
    fi
    echo "[INFO] Launching the AI Phone Assistant daemon in the background..."

    export GEMINI_API_KEY="$GEMINI_API_KEY"
    mkdir -p "$LOG_DIR"
    if [ -f "$LOG_FILE" ] && [ "$(stat -c %s "$LOG_FILE")" -gt "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1"
    fi
    # Unbuffered output, mirrored to the terminal and to the log file (view it live with: ./my_gui.sh --logs)
    python3 -u phone_assistant.py > >(tee -a "$LOG_FILE") 2>&1 &
    DAEMON_PID=$!

    trap "echo '[INFO] Stopping background daemon...'; kill $DAEMON_PID 2>/dev/null" EXIT
fi

# Launch the Streamlit application in the current terminal
echo "[INFO] Starting AI Switchboard Web Interface v2.8..."

if [ "$FORCE_LOCAL" = "1" ]; then
    # Local-only mode: the Web GUI never listens on the network, even without a desktop session.
    echo "[INFO] Local-only mode: the Web GUI listens on 127.0.0.1:8501 and is not reachable from the LAN."
    if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
        streamlit run gui.py $STREAMLIT_COMMON_OPTS --server.headless=true --server.address=127.0.0.1
    else
        streamlit run gui.py $STREAMLIT_COMMON_OPTS --server.address=127.0.0.1
    fi
elif [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ] || [ "$FORCE_HEADLESS" = "1" ]; then
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP="YOUR_DEVICE_IP"
    fi
    echo "[INFO] Headless/LAN server mode enabled. Streamlit configured for Remote LAN access."
    echo "[INFO] ===================================================================="
    echo "[INFO] Open your PC browser and go to:  http://$LOCAL_IP:8501"
    echo "[INFO] ===================================================================="
    streamlit run gui.py $STREAMLIT_COMMON_OPTS --server.headless=true --server.address=0.0.0.0
else
    streamlit run gui.py $STREAMLIT_COMMON_OPTS
fi
