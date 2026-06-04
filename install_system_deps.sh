#!/usr/bin/env bash
#
# install_system_deps.sh - System dependency installer for AI Switchboard.
# Installs all system-level packages, auto-detects the best available
# hardware acceleration, compiles whisper-cli from source accordingly,
# downloads Whisper models, and installs Python dependencies for
# phone_assistant.py and gui.py.
#
# Supported distros : Ubuntu/Debian, Fedora/RHEL/CentOS, Arch Linux, openSUSE
# Supported accel.  : CUDA > Vulkan > OpenBLAS > CPU  (auto-detected)
# Models downloaded : base  base.en  medium  medium.en
#
# Author: Antonio R.
# Version: 1.2
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

set -e

# ============================================================
#  Terminal colours
# ============================================================
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_GREEN="\033[1;32m"
C_YELLOW="\033[1;33m"
C_CYAN="\033[1;36m"
C_RED="\033[1;31m"
C_BLUE="\033[1;34m"

info()    { echo -e "${C_CYAN}==>${C_RESET}${C_BOLD} $*${C_RESET}"; }
ok()      { echo -e "    ${C_GREEN}✔${C_RESET}  $*"; }
warn()    { echo -e "    ${C_YELLOW}⚠${C_RESET}  $*"; }
err()     { echo -e "    ${C_RED}✘${C_RESET}  $*"; }
step()    { echo -e "\n${C_BLUE}┌──────────────────────────────────────────────┐${C_RESET}"; \
            echo -e "${C_BLUE}│${C_RESET}  ${C_BOLD}$*${C_RESET}"; \
            echo -e "${C_BLUE}└──────────────────────────────────────────────┘${C_RESET}"; }
progress(){ echo -e "    ${C_CYAN}→${C_RESET}  $*"; }

# ============================================================
#  STEP 0 — Detect Linux distribution
# ============================================================
step "STEP 0/8 — Detecting Linux distribution"

DISTRO=""
PKG_MGR=""

if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${ID_LIKE:-$ID}"
fi

case "$DISTRO" in
    *debian*|*ubuntu*)  PKG_MGR="apt"    ;;
    *fedora*|*rhel*|*centos*) PKG_MGR="dnf" ;;
    *arch*|*manjaro*)   PKG_MGR="pacman" ;;
    *opensuse*|*suse*)  PKG_MGR="zypper" ;;
    *)
        warn "Unrecognised distro: '${DISTRO}'. Falling back to apt."
        PKG_MGR="apt"
        ;;
esac

ok "Distro    : ${PRETTY_NAME:-$DISTRO}"
ok "Pkg mgr   : $PKG_MGR"

# ============================================================
#  Helper: install packages
# ============================================================
pkg_install() {
    case "$PKG_MGR" in
        apt)    sudo apt install -y "$@" ;;
        dnf)    sudo dnf install -y "$@" ;;
        pacman) sudo pacman -S --noconfirm "$@" ;;
        zypper) sudo zypper install -y "$@" ;;
    esac
}

# ============================================================
#  STEP 1 — Update package index
# ============================================================
step "STEP 1/8 — Updating package index"
case "$PKG_MGR" in
    apt)    sudo apt update ;;
    dnf)    sudo dnf check-update || true ;;
    pacman) sudo pacman -Sy ;;
    zypper) sudo zypper refresh ;;
esac
ok "Package index up to date."

# ============================================================
#  STEP 2 — Python base + build tools
# ============================================================
step "STEP 2/8 — Python and build tools"
case "$PKG_MGR" in
    apt)
        pkg_install python3 python3-pip python3-venv \
            build-essential cmake git pkg-config
        ;;
    dnf)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkgconf-pkg-config
        ;;
    pacman)
        pkg_install python python-pip cmake git base-devel pkgconf
        ;;
    zypper)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkg-config
        ;;
esac
ok "Python and build tools installed."

# ============================================================
#  STEP 3 — D-Bus and GLib / GObject introspection
#  Installed via system package manager — pip wheels for
#  dbus-python and PyGObject frequently fail on Linux due to
#  missing system headers. The apt/dnf/pacman packages are
#  the reliable path on all distros.
# ============================================================
step "STEP 3/8 — D-Bus and GLib/GObject bindings"
progress "Installing system-level dbus-python and PyGObject..."
case "$PKG_MGR" in
    apt)
        pkg_install python3-dbus python3-gi python3-gi-cairo \
            gir1.2-glib-2.0 libdbus-1-dev libglib2.0-dev \
            libgirepository1.0-dev
        ;;
    dnf)
        pkg_install python3-dbus python3-gobject \
            gobject-introspection-devel dbus-devel glib2-devel
        ;;
    pacman)
        pkg_install python-dbus python-gobject \
            gobject-introspection dbus glib2
        ;;
    zypper)
        pkg_install python3-dbus-python python3-gobject \
            gobject-introspection-devel dbus-1-devel glib2-devel
        ;;
esac
ok "D-Bus and GLib/GObject bindings installed."
warn "Note: dbus-python / PyGObject are listed in requirements.txt for"
warn "      documentation purposes. On Linux always use the system packages"
warn "      installed above — do NOT reinstall them with pip."

# ============================================================
#  STEP 4 — Bluetooth + oFono  (HFP/HSP SCO for phone calls)
# ============================================================
step "STEP 4/8 — Bluetooth and oFono"
progress "Installing BlueZ and oFono daemon..."
case "$PKG_MGR" in
    apt)    pkg_install bluez bluez-tools ofono ;;
    dnf)    pkg_install bluez bluez-tools ofono ;;
    pacman) pkg_install bluez bluez-utils ofono ;;
    zypper) pkg_install bluez ofono ;;
esac

sudo systemctl enable ofono
sudo systemctl start ofono
ok "BlueZ installed."
ok "oFono daemon enabled and started."

# ============================================================
#  STEP 5 — Audio: PipeWire + WirePlumber + PulseAudio compat.
#  pacat and pactl are called directly by phone_assistant.py
# ============================================================
step "STEP 5/8 — PipeWire / WirePlumber / PulseAudio"
case "$PKG_MGR" in
    apt)
        pkg_install pipewire pipewire-pulse pipewire-audio \
            wireplumber pulseaudio-utils
        ;;
    dnf)
        pkg_install pipewire pipewire-pulseaudio \
            wireplumber pulseaudio-utils
        ;;
    pacman)
        pkg_install pipewire pipewire-pulse wireplumber
        ;;
    zypper)
        pkg_install pipewire pipewire-pulseaudio wireplumber
        ;;
esac

systemctl --user daemon-reload
systemctl --user restart pipewire pipewire-pulse wireplumber || true
ok "PipeWire and WirePlumber installed and restarted."
ok "pacat / pactl available."

# ============================================================
#  STEP 6 — whisper.cpp: auto-detect best acceleration + build
# ============================================================
step "STEP 6/8 — Detecting hardware acceleration"

ACCEL="CPU"
CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF"

# --- CUDA (NVIDIA GPU) ---
if command -v nvidia-smi &>/dev/null || command -v nvcc &>/dev/null; then
    CUDA_ARCH=""
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)
        CUDA_ARCH=$(nvidia-smi --query-gpu=compute_cap \
            --format=csv,noheader 2>/dev/null \
            | head -1 | tr -d '.' || true)
    fi
    CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF -DGGML_CUDA=1"
    if [ -n "$CUDA_ARCH" ]; then
        CMAKE_FLAGS="$CMAKE_FLAGS -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH"
        ACCEL="CUDA  (GPU: ${GPU_NAME:-unknown}  |  sm_${CUDA_ARCH})"
    else
        ACCEL="CUDA"
    fi

# --- Vulkan (AMD / Intel / NVIDIA) ---
elif command -v vulkaninfo &>/dev/null \
     || ldconfig -p 2>/dev/null | grep -q libvulkan; then
    CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF -DGGML_VULKAN=1"
    ACCEL="Vulkan"

# --- OpenBLAS (CPU BLAS) ---
elif ldconfig -p 2>/dev/null | grep -q libopenblas; then
    CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF -DGGML_BLAS=1"
    ACCEL="OpenBLAS"

# --- CPU fallback ---
else
    warn "No GPU acceleration detected. Building for plain CPU."
    ACCEL="CPU (no hardware acceleration)"
fi

ok "Selected acceleration : ${C_GREEN}${ACCEL}${C_RESET}"
ok "cmake flags           : $CMAKE_FLAGS"

# --- Clone / update whisper.cpp ---
WHISPER_DIR="$HOME/whisper.cpp"
progress "Cloning / updating whisper.cpp into $WHISPER_DIR ..."

if [ ! -d "$WHISPER_DIR" ]; then
    git clone https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
    ok "Repository cloned."
else
    cd "$WHISPER_DIR" && git pull && cd -
    ok "Repository already exists — updated to latest."
fi

cd "$WHISPER_DIR"

# --- Build ---
progress "Running cmake configure..."
# shellcheck disable=SC2086
cmake -B build $CMAKE_FLAGS

progress "Compiling whisper-cli using $(nproc) cores — this may take a few minutes..."
cmake --build build --config Release -j"$(nproc)"

# --- Install binary ---
sudo ln -sf "$WHISPER_DIR/build/bin/whisper-cli" /usr/local/bin/whisper-cli
ok "whisper-cli installed at /usr/local/bin/whisper-cli"

cd -

# ============================================================
#  STEP 7 — Download Whisper models
#  Models are saved to $WHISPER_DIR/models/ and then symlinked
#  into ./models/ (next to phone_assistant.py) so the assistant
#  can find them at the expected path ./models/ggml-<name>.bin
# ============================================================
step "STEP 7/8 — Downloading Whisper models"

MODELS_TO_DOWNLOAD=("base" "base.en" "medium" "medium.en")
MODELS_SIZES=("142 MB" "142 MB" "1.42 GB" "1.42 GB")
PROJECT_MODELS_DIR="$(pwd)/models"

progress "Model storage  : $WHISPER_DIR/models/"
progress "Project link   : $PROJECT_MODELS_DIR/"
echo ""

mkdir -p "$PROJECT_MODELS_DIR"

for i in "${!MODELS_TO_DOWNLOAD[@]}"; do
    MODEL="${MODELS_TO_DOWNLOAD[$i]}"
    SIZE="${MODELS_SIZES[$i]}"
    BIN_FILE="$WHISPER_DIR/models/ggml-${MODEL}.bin"
    LINK_FILE="$PROJECT_MODELS_DIR/ggml-${MODEL}.bin"

    echo -e "    ${C_BOLD}[$(( i + 1 ))/${#MODELS_TO_DOWNLOAD[@]}]${C_RESET} Model: ${C_CYAN}${MODEL}${C_RESET}  (${SIZE})"

    if [ -f "$BIN_FILE" ]; then
        ok "Already downloaded — skipping: ggml-${MODEL}.bin"
    else
        progress "Downloading ggml-${MODEL}.bin ..."
        bash "$WHISPER_DIR/models/download-ggml-model.sh" "$MODEL"

        if [ -f "$BIN_FILE" ]; then
            ok "Download complete: ggml-${MODEL}.bin"
        else
            err "Download failed for model '${MODEL}'. Check your connection and retry."
        fi
    fi

    # Symlink into the project ./models/ directory
    if [ -f "$BIN_FILE" ] && [ ! -e "$LINK_FILE" ]; then
        ln -sf "$BIN_FILE" "$LINK_FILE"
        ok "Symlinked into project: models/ggml-${MODEL}.bin"
    elif [ -L "$LINK_FILE" ]; then
        ok "Symlink already exists: models/ggml-${MODEL}.bin"
    fi

    echo ""
done

ok "All models ready in $PROJECT_MODELS_DIR"

# ============================================================
#  STEP 8 — Python pip dependencies
# ============================================================
step "STEP 8/8 — Python pip dependencies"
progress "Installing google-genai, aiohttp, streamlit..."

# Outside a venv, --break-system-packages is required on
# Ubuntu 24.04+ / modern distros with PEP 668 enforcement.
# We try it first and fall back silently for distros that
# don't need or support that flag (e.g. Arch).
pip install --break-system-packages \
    "google-genai" \
    "aiohttp" \
    "streamlit" \
    2>/dev/null \
|| pip install \
    "google-genai" \
    "aiohttp" \
    "streamlit"

ok "google-genai installed."
ok "aiohttp installed."
ok "streamlit installed."

# ============================================================
#  Final summary
# ============================================================
echo ""
echo -e "${C_BLUE}╔══════════════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}${C_GREEN}Installation complete!${C_RESET}"
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  Acceleration : ${C_GREEN}${ACCEL}${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  whisper-cli  : /usr/local/bin/whisper-cli"
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}Models downloaded:${C_RESET}"
for MODEL in "${MODELS_TO_DOWNLOAD[@]}"; do
    BIN="$PROJECT_MODELS_DIR/ggml-${MODEL}.bin"
    if [ -e "$BIN" ]; then
        echo -e "${C_BLUE}║${C_RESET}    ${C_GREEN}✔${C_RESET}  models/ggml-${MODEL}.bin"
    else
        echo -e "${C_BLUE}║${C_RESET}    ${C_RED}✘${C_RESET}  models/ggml-${MODEL}.bin  (download failed)"
    fi
done
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}Next steps:${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  1. Set your Gemini API key:"
echo -e "${C_BLUE}║${C_RESET}       export GEMINI_API_KEY='your_key_here'"
echo -e "${C_BLUE}║${C_RESET}  2. Pair your phone via Bluetooth (HFP profile)"
echo -e "${C_BLUE}║${C_RESET}  3. Launch the assistant:"
echo -e "${C_BLUE}║${C_RESET}       python3 phone_assistant.py"
echo -e "${C_BLUE}║${C_RESET}  4. Launch the Streamlit dashboard (new terminal):"
echo -e "${C_BLUE}║${C_RESET}       streamlit run gui.py"
echo -e "${C_BLUE}╚══════════════════════════════════════════════════════╝${C_RESET}"
