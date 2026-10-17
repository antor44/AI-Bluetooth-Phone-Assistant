# 📞 AI Bluetooth Phone Assistant & Switchboard

![Version: 2.0](https://img.shields.io/badge/Version-2.0-brightgreen.svg)
![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini 3.8 Live** for conversational AI and optional **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages in a dedicated inbox, maintains configurable context-aware memory with AI summaries for repeat callers, and provides a sleek Web GUI to manage your communications and server state.

> ⚠️ **EXPERIMENTAL SOFTWARE — USE AT YOUR OWN RISK**
> This is an experimental project distributed as-is, without warranty. It may contain bugs, missed-call scenarios, transcription errors, or other untested edge cases. Several advanced features — specifically **real-time SPAM database checking, Whitelist/Blacklist/Wildcard filtering, and Contact-Specific Custom Instructions** — are implemented but have not been thoroughly verified in real-world conditions.
>
> Users are responsible for compliance with applicable local laws regarding call recording, transcription, and AI-assisted call handling. The safest default profile is: **incoming calls only**, clear first-message disclosure to the caller, and minimal data retention.

---

## 🌟 Why use this?

<div align="center">
  <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant4.jpg" width="80%">
  <br><b>😲 The demonstration that Google CEO Sundar Pichai gave during the Google I/O 2018 conference.</b>
</div>

<br>

In May 2018, Google introduced its Duplex technology as a revolutionary AI assistant capable of holding natural phone conversations by simulating human speech. Despite its initial impact, the service was deployed with severe limitations, being available in only a few countries and initially restricted to Google Pixel devices. Subsequent solutions like Google Call Screen have carried similar barriers, being limited by regional blocks, carrier restrictions, and predefined functions that do not allow the user to freely customize responses or call handling.

To overcome these commercial barriers, I have developed this Python application that operates as an independent orchestrator from any PC or supported Linux SBC (single-board computer). By connecting to the mobile phone via Bluetooth, the system acts as a supercharged version of Google's solutions that allows answering calls (only answering, to avoid most legal restrictions for normal users) without suffering geographical blocks or depending on specific mobile hardware. This architecture offers complete and unrestricted control to manage bidirectional audio, transcribe conversations, and generate real-time responses using AI. Furthermore, it provides full control over the call history, and at any moment, the user can interrupt the AI to take manual control of the call, among many other improvements that will be added in the future.

<table>
  <tr>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant3.jpg" width="100%">
      <br><b>🛡️ The Ultimate SPAM Shield</b><br>Enjoy your free time in peace. The AI intercepts unknown callers, verifies their numbers against live SPAM databases, and automatically terminates telemarketing calls before they bother you.
    </td>
    <td width="3.5%"></td>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant2.jpg" width="100%">
      <br><b>🛠️ Hands-Free & Deep Work</b><br>Perfect for mechanics, freelancers, or programmers. Maintain your flow state or keep working with dirty hands while your AI secretary gracefully handles clients and takes detailed messages.
    </td>
    <td width="3.5%"></td>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant1.jpg" width="100%">
      <br><b>🎶 Your free time, protected.</b><br>Even a call from Mom during a concert gets answered: the whole setup fits in your pockets, and you decide later whether to call back. Or, if Mom is not one to be trifled with, you can jump in and take over the call in the middle of her conversation with the AI.
    </td>
  </tr>
</table>

> 📶 **No Wi-Fi around? The required Internet connection can come from the phone itself: just turn on its Wi-Fi hotspot (also called tethering or mobile hotspot) and share its mobile data.**

<br><br>

<table>
  <tr>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Orange_Pi_Zero_3_powerbank1.jpg" width="100%">
      <br><b>🔋 Portable SBC example</b><br>An Orange Pi Zero 3 with only 1.5 GB of RAM, connected to the router via Wi-Fi and powered by a power bank.
    </td>
    <td width="3.5%"></td>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Orange_Pi_Zero_3_powerbank2.jpg" width="100%">
      <br><b>🔍 Close-up</b><br>A closer look at the board, showing the details of a simple metal case.
    </td>
    <td width="3.5%"></td>
    <td width="31%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Orange_Pi_Zero_3_powerbank3.jpg" width="100%">
      <br><b>🔵 External USB Bluetooth</b><br>Detail of the USB Bluetooth dongle that replaces the defective onboard chip of the Zero 3.
    </td>
  </tr>
</table>

> 🔌 An expansion board with two extra USB ports and an audio output is also sold for this SBC. However, the onboard audio output is disabled as well (see *SBC Audio Note* below), so to monitor call audio locally it is recommended to use a **USB sound card or USB speakers**.

Author: Antonio R. | Version: 2.0 | License: GPL 3.0

---

## 📸 Screenshots

### Terminal View (Live Call Processing)
*Real-time processing showing User audio chunks, D-Bus interaction, Gemini AI responses, and Whisper.cpp noise filtering.*
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant1.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant2.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant3.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant4.jpg)

---

### Web GUI (Control Panel & Call Log)
*Streamlit-based GUI for managing call transcripts, caller messages inbox, SPAM rules, category memory, audio/VAD parameters, and AI personality settings.*
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy1.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy3.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy2.jpg)

---

## 🚀 Features & Technical Highlights

### ⭐ Core Features & Switchboard Capabilities
* **Real-Time Conversational Voice AI (`gemini-3.8-live`):** Low-latency bidirectional voice interaction with natural intonation, affective dialogue, and built-in resistance to background noise.
* **Hardware-Agnostic Bluetooth HFP Switchboard:** Connects to any smartphone via standard Bluetooth Hands-Free Profile (`BlueZ`, `oFono`, and `PipeWire`), bypassing regional locks, carrier restrictions, or proprietary Google Pixel hardware requirements.
* **Live Handset Takeover (Mid-Call Interruption):** Pick up your smartphone or switch the audio route from Bluetooth to the handset at any point during a call. The daemon automatically detects the PipeWire node disconnect, pauses the AI (`⏸ Takeover`), and seamlessly resumes if you route the call back to Bluetooth.
* **Intelligent Hold & Dynamic Silence Management:** Automatically detects when a caller asks to hold or transfers the line (`on_hold`), silences inactivity prompts while waiting, and executes a polite two-step grace-period warning before disconnecting dead air.
* **Priority Keyword Detection & Category Wait Rules:** Dynamically extends hold and silence timeouts when high-priority keywords (e.g., *hospital, doctor, surgery, dentist, lawyer, court*) are detected in real time.
* **Deterministic Security Guardrails (`CallPolicyEngine`):** Intercepts AI tool executions (`hangup`, `save_message`) to prevent premature disconnections while on hold, block private data disclosure (such as revealing the owner's surname), and enforce a balanced 2-attempt caller identification rule.
* **Synchronized Stereo Call Recording (`.wav`):** Saves every call as a 24kHz stereo WAV file (Left channel = Caller, Right channel = AI Secretary) alongside an isolated 16kHz caller track, with an integrated audio player in the Web GUI.
* **Background LLM Classification & SPAM Scoring:** Uses secondary text models (`gemini-3-flash-preview` or `gemma-4`) to retrospectively classify calls (`PERSONAL`, `WORK`, `PRIORITY`, `SPAM`, `GENERAL`), extract caller name and company, and assign a `0–100` risk score.
* **Multi-Engine Transcription Modes:** Choose between **Disabled (Gemini Live native transcription)**, **Real-time per-turn `whisper.cpp` healing**, **Batch `whisper.cpp` at end of call**, or **Gemini Audio alignment at end of call**.
* **Local Speaker Monitoring & PC Mic Isolation:** Route call audio to local speakers (Both, Caller Only, Secretary Only, or None) while keeping the local PC microphone strictly unlinked from the Bluetooth call to prevent echo and room audio leakage.
* **Interactive Transcript Editor & Data Auto-Cleanup:** Edit or delete individual dialogue turns in the Web GUI, retag calls, purge audio recordings or database logs older than $N$ days, or wipe all records and `.wav` files with a single click.

### 🆕 New in Version 2.0
* **📬 Dedicated Caller Messages Inbox:** Messages captured via the `save_message` tool are stored in a dedicated `messages` table with the **exact date (`YYYY-MM-DD`) and time (`HH:MM:SS`)**, caller name, phone number, unread counter badge, Read/Unread toggles, and a 1-click importer for legacy transcripts.
* **🧠 Configurable Call Memory & Post-Call AI Summaries:** Generates a concise call summary at the end of every call in the same LLM analysis pass (zero extra API calls or pickup latency). Supports **Disabled**, **Per Phone Number** (default), **Per Category**, and **Global** (all non-SPAM calls) modes with configurable call count, max age in days, and max character limits.
* **🔢 Phone Normalization, Wildcards (`626288*`) & Editable Contacts:** Normalizes international prefixes (`+34`, `0034`, national digits), supports `*` and `?` wildcard rules with specificity priority, logs rejected blacklist calls in the Call History with custom tags, and provides a full GUI editor for managed contacts.
* **🛡️ Upgraded SPAM Engine (`curl_cffi`), Cache & Live AI Tester:** Automatically skips SPAM checks for whitelisted contacts, supports `{number}`, `{national}`, and `{e164}` URL placeholders, uses `curl_cffi` TLS browser impersonation (`listaspam.com`, `tellows.es`), strips `<script>`/`<style>`/`<nav>`/`<select>` noise before analysis, caches lookups in SQLite (`spam_cache`), and includes a live SPAM provider + AI verdict tester in the Web GUI and CLI (`--test-spam`).
* **🎚️ Gemini 3.8 Live Audio & VAD Tuning Panel:** Adjust Caller Mic Gain (default `1.5x`), Pre-Gain Base Noise Gate (default `50`), VAD Start/End Sensitivity (`LOW`/`HIGH`), VAD Prefix Padding (`500 ms`), VAD Silence Duration (`500 ms`), Wait Seconds before answering (`5s`), and Initial Greeting Interruption Protection directly from the Web GUI, plus automatic input transcription echo stripping.
* **🎛️ Daemon Controls, Web Whisper Manager & Remote Server Reboot:** Pause, resume, or stop the switchboard daemon from the Web GUI with live heartbeat status, download/quantize Whisper models from the browser, or reboot the entire Linux host server remotely with `sudo` password confirmation.

---

### 🌍 Tested Hardware & OS Compatibility
This codebase interacts at a low level with Linux D-Bus, BlueZ, oFono, PipeWire, and WirePlumber. Because Bluetooth SCO (Synchronous Connection-Oriented) voice routing is sensitive to kernel drivers and audio session managers, **only the following configurations have been verified and are officially supported**:

1. **Standard x86_64 PC:**
   * **OS:** **Xubuntu / Ubuntu 24.04 LTS (Noble Numbat)**.
   * **Audio/BT Stack:** PipeWire 1.0.x, WirePlumber 0.4.x (`.lua` configuration), BlueZ 5.72, and oFono.

2. **ARM Single-Board Computer (SBC) — Orange Pi Zero 3 (Allwinner H618):**
   * **OS (Exact Image Verified):** **`Armbian_25.5.1_Orangepizero3_noble_current_6.12.23_xfce_desktop`** (Ubuntu 24.04 LTS Noble with XFCE Desktop environment, which includes the full user session stack equivalent to Xubuntu 24.04 LTS).
   * **Bluetooth Hardware Requirement:** The onboard Allwinner/Unisoc combo chip (`sprdbt_tty`) has kernel limitations when handling bidirectional SCO voice channels and is automatically blacklisted by the installer. **An external USB Bluetooth adapter (e.g., Realtek RTL8761BU USB 5.1 dongle) is required.**
   * **SBC Audio Note:** The onboard Allwinner platform audio codecs (`alsa_card.platform-*`) exhibit DMA clock multiplier bugs on mainline kernels when running headless and are automatically disabled in WirePlumber in favor of the persistent `auto_null` clock source. To monitor calls locally via speakers on the Orange Pi Zero 3, use an external **USB sound card or USB speaker** (`alsa_card.usb-*`).

> ⚠️ **CRITICAL PERFORMANCE WARNING FOR ARM SBCs (Keep `whisper.cpp` Disabled):**
> Starting in v2.0, **Transcription Mode** defaults to **"Disabled (Gemini Live only)"** and `install_system_deps.sh` skips compiling `whisper.cpp` unless `--with-whisper` is passed. On ARM single-board computers (such as the Orange Pi Zero 3 or other modest SBCs), **keep local `whisper.cpp` transcription disabled**. Running local Whisper inference on low-power ARM CPUs will saturate all cores at 100%, starving the real-time PipeWire audio threads and **causing the board to freeze or hang even when using the smallest (`base`) models**.

> ⚠️ **Note on Other SBCs & Linux Distributions:**
> * **Minimal / Stripped-down OS images (e.g., DietPi, Armbian Minimal):** Not recommended. They run as `root` by default (where PipeWire is blocked by `ConditionUser=!root`) and lack `dbus-user-session` and `libpam-systemd`.
> * **Non-24.04 Distributions (Debian 13 Trixie, Ubuntu 26.04 LTS, Fedora 40+, Arch):** Newer distributions transition to WirePlumber 0.5+ and PipeWire 1.4+, which deprecate `.lua` scripts and alter `oFono` vs `native` HFP socket arbitration. While fallback `.conf` templates are generated by the script, **Ubuntu 24.04 LTS (Xubuntu 24.04 on PC / Armbian 24.04 Noble XFCE on Orange Pi Zero 3)** is strongly recommended for reliable operation.
> * **Other ARM SBCs (Raspberry Pi, Rockchip, etc.):** Untested. If attempting installation on another SBC, use an Ubuntu 24.04 LTS Desktop image, an external USB Bluetooth dongle, and keep local `whisper.cpp` transcription disabled.

### 🎧 Complex Bluetooth Scenarios
1.  **Headsets connected simultaneously:** If you have Bluetooth headphones connected to the PC while the phone rings, the script extracts the specific MAC address of the calling phone. It forces the HFP profile **only** on the phone, leaving your headset alone. *(Note: depending on your BT chip bandwidth, handling A2DP music and HFP bidirectional audio simultaneously may cause slight audio drops).*
2.  **Two Phones Paired:** Linux (`oFono`) registers every paired phone as a separate modem (`HandsfreeAudioCard`). Having more than one phone paired in BlueZ causes `oFono` initialization errors (`org.ofono.Error.Failed`) and breaks call audio routing. **Always keep only one phone paired at a time** (see Section 6 below on how to unpair old phones when switching devices).

---

## 🧠 Tuning & Personality

*   **Language & Accent:** The author is not a native English speaker. The prompts and default interactions were originally heavily tuned for **Spanish** and optimized for a personal assistant role handling specific edge cases.
*   **GUI Personality Changes:** You can radically modify the secretary's personality via the GUI (e.g., changing instructions, strictness, or tone). Note that significant personality changes may affect the reliability of structural commands like hanging up or saving messages.
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values.

### Recommended Operating Profile
For a balanced default experience, the recommended profile is:
*   Concise and neutral tone
*   Inbound-call focused
*   Limited to call handling, message capture, hold management, and basic classification
*   Resistant to oversharing personal or schedule details

A more expressive or conversational personality sounds nicer, but may reduce reliability for structural commands during real calls.

---

## 🌐 Multi-Language Compatibility & Script Limitations

While the application is structurally designed to support translation locales via JSON files, there are technical limitations in the current codebase regarding non-Latin scripts, Asian languages, and Right-to-Left (RTL) languages:

### 1. Hardcoded Character Filtering (CJK Languages)
At the code level, the daemon employs a regex-based noise filter in the `is_valid_text` function to discard transcription artifacts caused by Bluetooth static. This filter explicitly blocks character ranges for:
- Chinese (Kanji/Hanzi: `\u4e00-\u9fff`)
- Japanese (Hiragana/Katakana: `\u3040-\u30ff`)
- Korean (Hangul: `\uac00-\ud7a3` / `\u1100-\u11ff`)

If a caller speaks in Chinese, Japanese, or Korean, the daemon will classify the input as noise and produce no response.

### 2. Word Tokenization Failure (CJK Languages)
The `_calculate_text_similarity` helper splits text using Python's `str.split()`, which tokenizes by whitespace. Chinese and Japanese writing systems do not use spaces between words, so this function will always return `0.0` similarity for CJK input, breaking the hallucination-detection and deduplication logic.

### 3. Right-to-Left (RTL) Languages (Arabic, Hebrew)
Although SQLite and the Gemini API natively process UTF-8 encoded Arabic and Hebrew text, most standard Linux terminal emulators and Streamlit layout renderers do not natively support complex bidirectional text mixing. Expect visual alignment issues in live terminal logs and Web GUI logs.

### 4. Voice Synthesis (TTS) Restrictions
The Gemini Live connection is hardcoded to use two voices (`Aoede` for female, `Puck` for male). For best results in non-Western languages, change `voice_name` in `phone_assistant.py` to a voice optimized for your target language.

---

## 🛠️ Installation & Setup

### Automated Installation (Recommended for Xubuntu 24.04 PC & Orange Pi Zero 3 Armbian 24.04 XFCE)
Clone the repository and run the automated dependency installer:

```bash
git clone https://github.com/antor44/AI-Bluetooth-Phone-Assistant.git
cd AI-Bluetooth-Phone-Assistant
chmod +x install_system_deps.sh my_gui.sh

# Standard installation (uses Gemini 3.8 Live native transcription, skips whisper.cpp compilation):
./install_system_deps.sh

# Optional (Desktop PCs): Pass --with-whisper to also compile whisper.cpp and download GGML models:
./install_system_deps.sh --with-whisper
```

After the installer finishes, **reboot your machine once** (`sudo reboot`) so user groups, D-Bus permissions, and Bluetooth kernel rules take effect.

---

### Manual Installation Steps (Reference)

#### 1. System Dependencies (Ubuntu 24.04 LTS)
```bash
sudo apt update
sudo apt install --install-recommends ofono bluez bluez-tools pipewire pipewire-pulse pipewire-audio pipewire-alsa wireplumber libspa-0.2-bluetooth libspa-0.2-modules pulseaudio-utils dbus-user-session rtkit sqlite3 python3-venv python3-dbus python3-gi python3-gi-cairo gir1.2-glib-2.0 build-essential cmake git pkg-config rfkill curl wget
```
*(On Armbian SBCs, also install `sudo apt install armbian-firmware-full` so external USB Bluetooth adapters load their required firmware).*

#### 2. Crucial Permissions Step
```bash
sudo usermod -aG bluetooth,audio,video,netdev,plugdev,dialout,sudo $USER
sudo loginctl enable-linger $USER
sudo reboot
```

#### 3. Python Environment
Requires Python 3.10+. Use a virtual environment with `--system-site-packages` so `dbus-python` and `PyGObject` are inherited:
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install google-genai aiohttp curl_cffi streamlit "protobuf>=5.26.1,<7.0.0"
```

#### 4. Installing `whisper.cpp` (Optional on SBCs / Hybrid Transcription for PC)
> ⚠️ **Reminder for SBC users:** On ARM SBCs (like the Orange Pi Zero 3), keep local `whisper.cpp` disabled in the Web GUI settings (`Disabled - Gemini Live only`) as even the smallest Whisper models can cause the board to hang during calls.

1. **Clone and compile:**
   ```bash
   cd ~
   git clone https://github.com/ggml-org/whisper.cpp.git
   cd whisper.cpp
   cmake -B build
   cmake --build build -j --config Release
   sudo ln -sf "$HOME/whisper.cpp/build/bin/whisper-cli" /usr/local/bin/whisper-cli
   ```
2. **Download models:**
   ```bash
   bash ~/whisper.cpp/models/download-ggml-model.sh base
   mkdir -p ~/AI-Bluetooth-Phone-Assistant/models
   ln -s ~/whisper.cpp/models/ggml-base.bin ~/AI-Bluetooth-Phone-Assistant/models/ggml-base.bin
   ```

---

### 5. Bluetooth Mobile Pairing (Crucial!)
Establishing an active bidirectional Hands-Free profile between Linux and your smartphone requires explicit agent authentication via `bluetoothctl`.

*Desktop GUI tools typically fail to negotiate the bidirectional HFP voice channel properly. Always pair from the terminal:*

1. **Launch `bluetoothctl`:**
   ```bash
   bluetoothctl
   ```
2. **Execute pairing sequence securely:**
   ```text
   power on
   ```
   ```text
   agent on
   ```
   ```text
   default-agent
   ```
   ```text
   scan on
   ```
   Wait for your phone to appear, then run:
   ```text
   pair XX:XX:XX:XX:XX:XX
   ```
   **CRUCIAL STEP:** In the terminal, it will ask `[agent] Confirm passkey XXXXXX (yes/no):`. **You MUST type `yes`** on the terminal *and immediately press Confirm/Accept on your Smartphone's screen at the same time!*

3. **Establish final trust:**
   ```text
   trust XX:XX:XX:XX:XX:XX
   ```
   ```text
   connect XX:XX:XX:XX:XX:XX
   ```
   ```text
   quit
   ```

---

### 6. Switching Phones / Unpairing Old Devices (Crucial for oFono!)
If you change your smartphone, **you must remove the old phone from BlueZ**. Leaving an old phone paired will cause `oFono` to repeatedly fail (`org.ofono.Error.Failed`) on startup and can result in silent calls (no audio) on the new phone due to conflicting HFP modem cards.

1. **List currently paired devices to find the old phone's MAC address:**
   ```bash
   bluetoothctl devices
   ```
2. **Remove the old phone and reset the audio/telephony services:**
   ```bash
   # Stop the switchboard if running
   systemctl --user stop ai-switchboard.service 2>/dev/null || true

   # Remove the old phone (replace with your old phone's MAC)
   bluetoothctl remove AA:BB:CC:DD:EE:FF

   # Restart Bluetooth, oFono, and PipeWire cleanly
   systemctl --user stop wireplumber pipewire pipewire-pulse
   sudo systemctl restart bluetooth ofono
   sleep 2
   systemctl --user start pipewire pipewire-pulse wireplumber
   ```
3. **Pair your new phone using the `bluetoothctl` terminal procedure in Step 5.**
   *(Tip: When placing your first test call on a newly paired smartphone, turn up the Bluetooth in-call volume on the phone itself and verify that "Phone Calls" / "Call Audio" is enabled in the phone's Bluetooth settings for this device).*

---

## 🔑 API Key Setup, Pricing & Privacy

This application relies on the **Google Gemini API**. It uses **`gemini-3.8-live`** for real-time, low-latency bidirectional voice communication, and secondary text models (`gemini-3-flash-preview` or the `gemma-4` family) for offline tasks like SPAM evaluation, post-call JSON transcript structuring, and call summary generation.

### 1. How to Obtain and Set Your API Key
1. Go to **[Google AI Studio](https://aistudio.google.com/)**.
2. Sign in and click **"Get API key"** -> **"Create API key"**.
3. Export the key in your `~/.bashrc`:
   ```bash
   echo 'export GEMINI_API_KEY="YOUR_API_KEY_HERE"' >> ~/.bashrc
   source ~/.bashrc
   ```

### 2. Free Tier vs. Paid Tier — Privacy Considerations
*   **Free Tier:** Google may use conversation data (anonymously) to improve their AI models.
*   **Paid Tier (Pay-As-You-Go):** Your data is strictly private — Paid API data is *not* used to train Google models. **For a privacy-focused deployment, the Paid Tier is recommended.**

### 3. Approximate Pricing (Pay-As-You-Go)
*   **Real-Time Voice Calls (`gemini-3.8-live`):**
    *   *Audio Input:* $3.00 / 1M tokens (~$0.005 per minute of caller audio).
    *   *Audio Output:* $12.00 / 1M tokens (~$0.018 per minute of assistant speech).
    *   *(A typical 2-minute phone call costs around $0.04).*
*   **Text Processing, Summaries & SPAM (`gemini-3-flash-preview`):**
    *   Used silently in the background for SPAM checking and parsing call transcripts/summaries (fractions of a cent per call).

---

## 📂 Project Directory Structure

```text
/AI-Bluetooth-Phone-Assistant
├── phone_assistant.py          # Main daemon (handles HFP, D-Bus, and Gemini 3.8 Live)
├── my_gui.sh                   # Main GUI Launcher Script (Desktop and Headless/LAN aware)
├── gui.py                      # Web Control Panel (Streamlit GUI interface)
├── install_system_deps.sh      # Automated system & Python dependency installer (--with-whisper optional)
├── switchboard.db              # SQLite Database (Auto-generated & migrated on launch)
├── requirements.txt            # Python package dependencies
│
├── /models                     # Whisper.cpp Model Folder (Optional)
│   ├── ggml-medium.bin         # Multilingual model (for PC setups)
│   └── ggml-base.bin           # Lightweight model (for low-RAM PC setups)
│
├── /languages                  # Localization JSON files
│   ├── /en-US                  # English Default Locale
│   │   ├── assistant.json      # Core AI prompts, hold rules, and logic variables
│   │   ├── gui.json            # Web Control Panel translations & defaults
│   │   └── spam.json           # Default spam verification search URL templates
│   │
│   ├── /es-ES                  # Spanish Default Locale
│   │   ├── assistant.json
│   │   ├── gui.json
│   │   └── spam.json
│
├── /recordings                 # Call audio logs directory (Auto-created)
│   ├── call_1234_client.wav    # Isolated caller audio (16kHz mono, used for offline ASR)
│   └── call_1234.wav           # Mixed synchronized call recording (24kHz stereo: Left=Caller, Right=AI)
```

---

## ⚙️ Running the Switchboard & Auto-Start on Boot

### 1. Manual Launch
On a desktop PC:
```bash
./my_gui.sh
```

On a headless SBC (e.g., Orange Pi Zero 3 via SSH) or to expose the Web GUI over your local network:
```bash
./my_gui.sh --lan
```
Then open `http://<YOUR_DEVICE_IP>:8501` from any browser on your local network.

*(Optional CLI SPAM Test):* You can also test any phone number against your configured SPAM providers from the terminal:
```bash
source venv/bin/activate
python3 phone_assistant.py --test-spam +34600000000
```

---

### 2. Automatic Startup on Boot (Systemd User Service)
To run the AI Switchboard automatically in the background whenever your PC or SBC boots up (without needing to log in via SSH or open a terminal), configure a `systemd` user service:

```bash
mkdir -p ~/.config/systemd/user

cat << 'EOF' > ~/.config/systemd/user/ai-switchboard.service
[Unit]
Description=AI Bluetooth Phone Assistant & Web Switchboard
After=network-online.target pipewire.service pipewire-pulse.service wireplumber.service
Wants=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
Type=simple
WorkingDirectory=%h/AI-Bluetooth-Phone-Assistant
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash %h/AI-Bluetooth-Phone-Assistant/my_gui.sh --lan
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

# Enable user session persistence and start the service
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now ai-switchboard.service
```

#### Controlling the Background Service
You can manage the service at any time from your terminal (as well as pausing/stopping the daemon or rebooting the server from the Web GUI):

* **Stop the switchboard (stops both the AI daemon and Web GUI):**
  ```bash
  systemctl --user stop ai-switchboard.service
  ```
* **Start the switchboard:**
  ```bash
  systemctl --user start ai-switchboard.service
  ```
* **Restart the switchboard:**
  ```bash
  systemctl --user restart ai-switchboard.service
  ```
* **View real-time console logs (press `Ctrl+C` to exit log view without stopping the service):**
  ```bash
  journalctl --user -u ai-switchboard.service -f
  ```
* **Disable automatic startup on boot:**
  ```bash
  systemctl --user disable ai-switchboard.service
  ```

*(Optional) You can add short aliases to your `~/.bashrc` for quick control:*
```bash
cat << 'EOF' >> ~/.bashrc
alias switchboard-stop='systemctl --user stop ai-switchboard.service && echo "Switchboard stopped."'
alias switchboard-start='systemctl --user start ai-switchboard.service && echo "Switchboard started."'
alias switchboard-restart='systemctl --user restart ai-switchboard.service && echo "Switchboard restarted."'
alias switchboard-log='journalctl --user -u ai-switchboard.service -f'
alias switchboard-status='systemctl --user status ai-switchboard.service'
EOF
source ~/.bashrc
```

---

## 🏗️ Architecture & Design Philosophy

This application is built as a **Monolithic State Machine** functioning as a deterministic Telephony Middleware around the LLM:

1. **Active Silence & Hold Tracking:** Tracks seconds of inactivity (`time_without_user`) to prompt silent callers or execute grace-period disconnections, while extending timeouts dynamically when a call is placed on hold (`self.on_hold`) or matches priority keywords.
2. **Deterministic Guardrails (`CallPolicyEngine`):** Intercepts AI tool calls (`hangup`, `save_message`) and validates them against the real-time state machine to prevent premature disconnections during active holds and store structured messages in the inbox.
3. **Streaming Chunk Reconstruction & Echo Stripping:** Accumulates fragmented streaming text chunks in a 2.5-second sliding window (`_asst_chunk_buffer`) to reliably evaluate goodbye and hold triggers while stripping assistant phrase bleed from incoming transcriptions.
4. **Hardware Actuation & Post-Call Curation:** Translates AI intent into `oFono` D-Bus calls, isolates PipeWire audio channels, records synchronized stereo `.wav` logs, and generates concise AI call summaries for future context memory.

---

## 📝 License
This project is licensed under the GPL v3 License. See the `LICENSE` file for details.
