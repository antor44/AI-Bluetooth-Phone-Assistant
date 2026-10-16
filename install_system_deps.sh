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
# Version: 1.6
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
        apt)    sudo apt install -y --install-recommends "$@" ;;
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
            build-essential cmake git pkg-config rfkill curl wget
        ;;
    dnf)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkgconf-pkg-config rfkill curl wget
        ;;
    pacman)
        pkg_install python python-pip cmake git base-devel pkgconf rfkill curl wget
        ;;
    zypper)
        pkg_install python3 python3-pip python3-virtualenv \
            gcc gcc-c++ make cmake git pkg-config rfkill curl wget
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
            libgirepository1.0-dev dbus-user-session
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

# Install full USB Bluetooth firmware package on Armbian SBCs if available
if [ -f /etc/armbian-release ] && [ "$PKG_MGR" = "apt" ]; then
    progress "Armbian detected: installing armbian-firmware-full for external USB Bluetooth support..."
    sudo apt install -y armbian-firmware-full || true
fi

# Blacklist broken onboard Spreadtrum UART Bluetooth driver on Allwinner H616/H618 SBCs
if lsmod | grep -q "sprdbt_tty" || modinfo sprdbt_tty &>/dev/null; then
    progress "Disabling onboard UART Bluetooth module (sprdbt_tty) in favor of external USB Bluetooth..."
    sudo tee /etc/modprobe.d/blacklist-onboard-bt.conf > /dev/null << 'EOF'
blacklist sprdbt_tty
install sprdbt_tty /bin/false
EOF
fi

# Configure D-Bus permissions for non-root oFono control
sudo tee /etc/dbus-1/system.d/ofono-user.conf > /dev/null << 'EOF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy group="bluetooth">
    <allow send_destination="org.ofono"/>
  </policy>
  <policy group="sudo">
    <allow send_destination="org.ofono"/>
  </policy>
</busconfig>
EOF

# Configure Polkit permissions for remote desktop / headless management
if [ -d /etc/polkit-1/rules.d ]; then
    sudo tee /etc/polkit-1/rules.d/50-remotebluetooth.rules > /dev/null << 'EOF'
polkit.addRule(function(action, subject) {
    if ((action.id.indexOf("org.blueman.") == 0 ||
         action.id.indexOf("org.bluez.") == 0 ||
         action.id.indexOf("org.freedesktop.NetworkManager.") == 0 ||
         action.id.indexOf("org.freedesktop.policykit.exec") == 0 ||
         action.id.indexOf("com.ubuntu.pkexec.") == 0) &&
        subject.isInGroup("sudo")) {
        return polkit.Result.YES;
    }
});
EOF
fi

# Add current user to required hardware groups
sudo usermod -aG bluetooth,audio,video,netdev,plugdev,dialout,sudo "$USER" 2>/dev/null || true

# Force unblock bluetooth
if command -v rfkill &>/dev/null; then
    sudo rfkill unblock bluetooth || true
elif [ -f /usr/sbin/rfkill ]; then
    sudo /usr/sbin/rfkill unblock bluetooth || true
fi

sudo systemctl reload dbus || true
sudo systemctl enable ofono
sudo systemctl start ofono
ok "BlueZ and oFono daemon configured and started."

# ============================================================
#  STEP 5 — Audio: PipeWire + WirePlumber + PulseAudio compat.
# ============================================================
step "STEP 5/8 — PipeWire / WirePlumber / PulseAudio"
case "$PKG_MGR" in
    apt)
        pkg_install pipewire pipewire-pulse pipewire-audio pipewire-alsa \
            wireplumber pulseaudio-utils libspa-0.2-bluetooth libspa-0.2-modules rtkit
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

# Enable systemd user session persistence for headless operation
sudo loginctl enable-linger "$USER" 2>/dev/null || true
grep -q "XDG_RUNTIME_DIR" "$HOME/.bashrc" || echo 'export XDG_RUNTIME_DIR="/run/user/$(id -u)"' >> "$HOME/.bashrc"
grep -q "DBUS_SESSION_BUS_ADDRESS" "$HOME/.bashrc" || echo 'export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"' >> "$HOME/.bashrc"

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

# --- RAM limits to prevent compiler freezes on SBCs ---
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

if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    MODELS_TO_DOWNLOAD=("base" "base.en")
    MODELS_SIZES=("142 MB" "142 MB")
else
    MODELS_TO_DOWNLOAD=("base" "base.en" "medium" "medium.en")
    MODELS_SIZES=("142 MB" "142 MB" "1.42 GB" "1.42 GB")
fi

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

if [ ! -d "venv" ]; then
    progress "Creating a Python virtual environment with system package access (venv)..."
    python3 -m venv --system-site-packages venv
fi

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
echo -e "${C_BLUE}║${C_RESET}  1. Reboot your system once to apply group & BT rules:"
echo -e "${C_BLUE}║${C_RESET}       sudo reboot"
echo -e "${C_BLUE}║${C_RESET}  2. Set your Gemini API key:"
echo -e "${C_BLUE}║${C_RESET}       export GEMINI_API_KEY='your_key_here'"
echo -e "${C_BLUE}║${C_RESET}  3. Pair your phone via bluetoothctl (HFP profile)"
echo -e "${C_BLUE}║${C_RESET}  4. Launch the switchboard:"
echo -e "${C_BLUE}║${C_RESET}       ./my_gui.sh"
echo -e "${C_BLUE}╚══════════════════════════════════════════════════════╝${C_RESET}"
