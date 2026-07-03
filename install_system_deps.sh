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
# Version: 1.5
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
            build-essential cmake git pkg-config rfkill
        ;;
    dnf)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkgconf-pkg-config rfkill
        ;;
    pacman)
        pkg_install python python-pip cmake git base-devel pkgconf rfkill
        ;;
    zypper)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkg-config rfkill
        ;;
esac
ok "Python, rfkill, and build tools installed."

# ============================================================
#  STEP 3 — D-Bus and GLib / GObject introspection
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

# ============================================================
#  STEP 4 — Bluetooth + oFono (HFP/HSP SCO for phone calls)
# ============================================================
step "STEP 4/8 — Bluetooth and oFono"
progress "Installing BlueZ and oFono daemon..."
case "$PKG_MGR" in
    apt)    pkg_install bluez bluez-tools ofono ;;
    dnf)    pkg_install bluez bluez-tools ofono ;;
    pacman) pkg_install bluez bluez-utils ofono ;;
    zypper) pkg_install bluez ofono ;;
esac

# Force unblock bluetooth in minimal OS
if command -v rfkill &>/dev/null; then
    sudo rfkill unblock bluetooth || true
elif [ -f /usr/sbin/rfkill ]; then
    sudo /usr/sbin/rfkill unblock bluetooth || true
fi

sudo systemctl enable ofono
sudo systemctl start ofono
ok "BlueZ installed."
ok "oFono daemon enabled and started."

# ============================================================
#  STEP 5 — Audio: PipeWire + WirePlumber + PulseAudio compat.
# ============================================================
step "STEP 5/8 — PipeWire / WirePlumber / PulseAudio"
case "$PKG_MGR" in
    apt)
        pkg_install pipewire pipewire-pulse pipewire-audio \
            wireplumber pulseaudio-utils libspa-0.2-bluetooth rtkit
        ;;
    dnf)
        pkg_install pipewire pipewire-pulseaudio \
            wireplumber pulseaudio-utils rtkit
        ;;
    pacman)
        pkg_install pipewire pipewire-pulse wireplumber rtkit
        ;;
    zypper)
        pkg_install pipewire pipewire-pulseaudio wireplumber rtkit
        ;;
esac

systemctl --user daemon-reload || true
systemctl --user restart pipewire pipewire-pulse wireplumber || true
ok "PipeWire, WirePlumber, and Bluetooth plugins installed."

# ============================================================
#  STEP 6 — whisper.cpp: RAM-aware build & compile
# ============================================================
step "STEP 6/8 — Detecting hardware acceleration"

ACCEL="CPU"
CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF"
ARCH=$(uname -m)

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
elif (command -v vulkaninfo &>/dev/null || ldconfig -p 2>/dev/null | grep -q libvulkan) && [ "$ARCH" != "aarch64" ]; then
    CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF -DGGML_VULKAN=1"
    ACCEL="Vulkan"

# --- OpenBLAS (CPU BLAS) ---
elif ldconfig -p 2>/dev/null | grep -q libopenblas; then
    CMAKE_FLAGS="-DWHISPER_BUILD_TESTS=OFF -DGGML_BLAS=1"
    ACCEL="OpenBLAS"

# --- CPU / ARM NEON fallback ---
else
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        ACCEL="ARM NEON (Optimized ARM64 CPU)"
    else
        warn "No GPU acceleration detected. Building for plain CPU."
        ACCEL="CPU (no hardware acceleration)"
    fi
fi

ok "Selected acceleration : ${C_GREEN}${ACCEL}${C_RESET}"
ok "cmake flags           : $CMAKE_FLAGS"

# --- Defensive Coding: RAM limits to prevent compiler freezes on SBCs ---
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [ "$TOTAL_RAM_KB" -lt 1500000 ]; then
    JOBS=1
    warn "Low RAM detected ($((TOTAL_RAM_KB / 1024)) MB). Limiting compiler to $JOBS core to prevent system freeze."
elif [ "$TOTAL_RAM_KB" -lt 2500000 ]; then
    JOBS=2
    warn "Moderate RAM detected ($((TOTAL_RAM_KB / 1024)) MB). Limiting compiler to $JOBS cores to prevent system freeze."
else
    JOBS=$(nproc)
fi

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

progress "Running cmake configure..."
# shellcheck disable=SC2086
cmake -B build $CMAKE_FLAGS

progress "Compiling whisper-cli and quantize tools using $JOBS cores..."
cmake --build build --config Release -j"$JOBS"

# --- Install binaries ---
sudo ln -sf "$WHISPER_DIR/build/bin/whisper-cli" /usr/local/bin/whisper-cli
ok "whisper-cli installed at /usr/local/bin/whisper-cli"

# Also symlink the quantization binary
if [ -f "$WHISPER_DIR/build/bin/whisper-quantize" ]; then
    sudo ln -sf "$WHISPER_DIR/build/bin/whisper-quantize" /usr/local/bin/whisper-quantize
    ok "whisper-quantize installed at /usr/local/bin/whisper-quantize"
elif [ -f "$WHISPER_DIR/build/bin/quantize" ]; then
    sudo ln -sf "$WHISPER_DIR/build/bin/quantize" /usr/local/bin/whisper-quantize
    ok "whisper-quantize installed at /usr/local/bin/whisper-quantize"
fi

cd -

# ============================================================
#  STEP 7 — Download Whisper models
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
        # Only download large medium models if RAM is sufficient
        if { [ "$MODEL" = "medium" ] || [ "$MODEL" = "medium.en" ]; } && [ "$TOTAL_RAM_KB" -lt 1500000 ]; then
            warn "System has low RAM ($((TOTAL_RAM_KB / 1024)) MB). Skipping heavy medium model."
            continue
        fi

        progress "Downloading ggml-${MODEL}.bin ..."
        bash "$WHISPER_DIR/models/download-ggml-model.sh" "$MODEL"

        if [ -f "$BIN_FILE" ]; then
            ok "Download complete: ggml-${MODEL}.bin"
        else
            err "Download failed for model '${MODEL}'. Check your connection and retry."
        fi
    fi

    # Ensure link is established
    if [ -f "$BIN_FILE" ] && [ ! -f "$LINK_FILE" ]; then
        ln -s "$BIN_FILE" "$LINK_FILE"
    fi
done

# ============================================================
#  STEP 8 — Python pip dependencies (Using --system-site-packages)
# ============================================================
step "STEP 8/8 — Python pip dependencies"

PIP_PACKAGES=(
    "google-genai"
    "aiohttp"
    "streamlit"
    "protobuf>=5.26.1,<7.0.0"
)

# MANDATORY: We use --system-site-packages so the venv can inherit the pre-compiled 
# dbus-python and PyGObject modules installed via APT in Step 3.
if [ ! -d "venv" ]; then
    progress "Creating a Python virtual environment with system package access (venv)..."
    python3 -m venv --system-site-packages venv
fi

# Activate environment and install dependencies
# shellcheck disable=SC1091
source venv/bin/activate

progress "Updating pip..."
pip3 install --upgrade pip --quiet

progress "Installing packages into virtual environment..."
if pip3 install "${PIP_PACKAGES[@]}"; then
    ok "Python pip dependencies successfully installed inside venv."
else
    err "pip installation failed."
fi

# ============================================================
#  Final summary
# ============================================================
echo ""
echo -e "${C_BLUE}╔══════════════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}${C_GREEN}Installation complete!${C_RESET}"
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  Acceleration : ${C_GREEN}${ACCEL}${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  whisper-cli  : /usr/local/bin/whisper-cli"
echo -e "${C_BLUE}║${C_RESET}  quantize     : /usr/local/bin/whisper-quantize"
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}Models downloaded:${C_RESET}"
for MODEL in "${MODELS_TO_DOWNLOAD[@]}"; do
    BIN="$PROJECT_MODELS_DIR/ggml-${MODEL}.bin"
    if [ -e "$BIN" ]; then
        echo -e "${C_BLUE}║${C_RESET}    ${C_GREEN}✔${C_RESET}  models/ggml-${MODEL}.bin"
    fi
done
echo -e "${C_BLUE}╠══════════════════════════════════════════════════════╣${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  ${C_BOLD}Next steps:${C_RESET}"
echo -e "${C_BLUE}║${C_RESET}  1. Activate your virtual environment:"
echo -e "${C_BLUE}║${C_RESET}       source venv/bin/activate"
echo -e "${C_BLUE}║${C_RESET}  2. Set your Gemini API key:"
echo -e "${C_BLUE}║${C_RESET}       export GEMINI_API_KEY='your_key_here'"
echo -e "${C_BLUE}║${C_RESET}  3. Pair your phone via Bluetooth (HFP profile)"
echo -e "${C_BLUE}║${C_RESET}  4. Launch the assistant:"
echo -e "${C_BLUE}║${C_RESET}       python3 phone_assistant.py"
echo -e "${C_BLUE}║${C_RESET}  5. Launch the Streamlit dashboard (new terminal):"
echo -e "${C_BLUE}║${C_RESET}       streamlit run gui.py"
echo -e "${C_BLUE}╚══════════════════════════════════════════════════════╝${C_RESET}"
