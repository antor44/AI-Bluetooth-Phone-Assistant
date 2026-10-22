# 📞 AI Bluetooth Phone Assistant & Switchboard

![Version: 2.6](https://img.shields.io/badge/Version-2.6-brightgreen.svg)
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
<div align="center">
  <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/mobile1.jpg" width="80%">
  <br><b>🔌 An expansion board with two extra USB ports and an audio output is also sold for this SBC. However, the onboard audio output is disabled as well (see *SBC Audio Note* below), so to monitor call audio locally it is recommended to use a **USB sound card or USB speakers**.</b>
</div>
<br>
Author: Antonio R. | Version: 2.6 | License: GPL 3.0

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

## 🚀 Main Features

* **🗣️ Real-Time Voice AI (`gemini-3.8-live`):** Low-latency bidirectional conversation with configurable voice, accent profile, and VAD/audio tuning from the Web GUI.
* **📶 Hardware-Agnostic Bluetooth HFP & Auto-Reconnect:** Works with any smartphone via `BlueZ`, `oFono`, and `PipeWire`. Includes an automatic Bluetooth reconnection watchdog and link counters.
* **📱 Live Handset Takeover:** Pick up your phone or switch audio away from Bluetooth mid-call to pause the AI (`⏸ Takeover`), and switch back to Bluetooth to resume.
* **⏳ Smart Hold, Silence & Priority Handling:** Detects hold requests (`on_hold`), extends wait times when priority keywords (*doctor, hospital, lawyer, court...*) are heard, and gives a polite warning before hanging up on dead air.
* **🛡️ Live SPAM Protection & Contact Rules:** Queries online SPAM databases (`curl_cffi`) with SQLite caching, supports exact and wildcard (`626288*`) Whitelist/Blacklist rules, and allows custom AI instructions per contact.
* **🔒 Deterministic Security Guardrails (`CallPolicyEngine`):** Prevents premature hangups during holds, protects private owner data (such as surnames), and enforces a 2-attempt caller identification rule.
* **📬 Dedicated Caller Messages Inbox:** Stores messages captured via `save_message` with exact date/time, caller name, phone number, and Read/Unread filters.
* **🧠 Tiered Call Memory & AI Summaries:** Generates post-call summaries and classifies calls (`PERSONAL`, `WORK`, `PRIORITY`, `SPAM`, `GENERAL`) with a priority memory system (number rule > category rule > default).
* **🎙️ Stereo MP3 Call Recording & Local Monitoring:** Saves synchronized stereo MP3 recordings (Left = Caller, Right = AI) and isolated caller tracks via `lameenc` (WAV fallback). Supports local speaker monitoring with independent volume control while keeping the PC microphone isolated.
* **🌍 Remote Access (Tor) & Android App:** Optional built-in private Tor onion service with QR pairing and a free Android companion app that polls for new message and call notifications without Google/Firebase push servers.


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

*   **Language & Accent:** The author is not a native English speaker. The prompts and default interactions were originally heavily tuned for **Spanish** and optimized for a personal assistant role handling specific edge cases. Since v2.6 each language file starts with a **voice and accent profile** and can set an explicit `speech_language_code` (BCP-47, e.g. `es-ES`); see *Voice Synthesis (TTS) Restrictions* below. Accent drift cannot be fully eliminated with Gemini 3.8 Live; if it persists, try other voices in `voice_names`.
*   **GUI Personality Changes:** You can radically modify the secretary's personality via the GUI (e.g., changing instructions, strictness, or tone). Note that significant personality changes may affect the reliability of structural commands like hanging up or saving messages.
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values. For a new language also set `home_country_code` and `home_national_length` in `spam.json`, and adapt the voice and accent profile at the top of the prompt, `speech_language_code`, `voice_names`, and the word lists (`cut_words`, `goodbye_veto_words`, `goodbye_meta_words`, `assistant_placeholder_phrases`). Missing keys fall back to built-in defaults or, for the word lists, simply disable that protection.

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

### 4. Voice & Language Configuration
The assistant's voice and speech language are configured in each language's `assistant.json` file:
* **`voice_names`:** sets the female and male voices used by Gemini Live (by default `Aoede` for female and `Charon` for male). You can change them to any prebuilt Gemini voice name.
* **`speech_language_code`:** sets the spoken language code (such as `es-ES` or `en-US`). Leave it empty (`""`) if you want Gemini to detect the language automatically.
* **Known Gemini 3.8 Live voice limitation:** the accent and pitch/tone of the voice may occasionally drift during a call. This is a known limitation of the **Gemini 3.8 Live** model itself and is especially noticeable with the **female voice in Spanish**.

---

## 🛠️ Installation & Setup

### Automated Installation (Recommended for Xubuntu 24.04 PC & Orange Pi Zero 3 Armbian 24.04 XFCE)
Clone the repository and run the automated dependency installer:

```bash
git clone https://github.com/antor44/AI-Bluetooth-Phone-Assistant.git
cd AI-Bluetooth-Phone-Assistant
chmod +x install_system_deps.sh my_gui.sh
```
```bash
# Standard installation (uses Gemini 3.8 Live native transcription, skips whisper.cpp compilation):
./install_system_deps.sh
```
```bash
# Optional (Desktop PCs): Pass --with-whisper to also compile whisper.cpp and download GGML models:
./install_system_deps.sh --with-whisper
```
```bash
# Optional: Pass --with-tor to also install tor and openssl (only needed for Remote Access over Tor).
# The flags can be combined, e.g. ./install_system_deps.sh --with-tor --with-whisper
./install_system_deps.sh --with-tor
```
The installer always installs the MP3 encoder `lameenc` for call recordings (if it cannot be installed, recordings are saved as WAV instead).

After the installer finishes, **reboot your machine once** (`sudo reboot`) so user groups, D-Bus permissions, and Bluetooth kernel rules take effect.

---

### Manual Installation Steps (Reference)

#### 1. System Dependencies (Ubuntu 24.04 LTS)
```bash
sudo apt update
sudo apt install --install-recommends ofono bluez bluez-tools pipewire pipewire-pulse pipewire-audio pipewire-alsa wireplumber libspa-0.2-bluetooth libspa-0.2-modules pulseaudio-utils dbus-user-session rtkit sqlite3 python3-venv python3-dbus python3-gi python3-gi-cairo gir1.2-glib-2.0 build-essential cmake git pkg-config rfkill curl wget
```
*(On Armbian SBCs, also install `sudo apt install armbian-firmware-full` so external USB Bluetooth adapters load their required firmware).*

*(Optional, only for Remote Access over Tor:)* `sudo apt install tor openssl`

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
pip install lameenc   # optional: MP3 call recordings (without it recordings are saved as WAV)
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
├── /logs                       # daemon.log (headless mode, rotated at 5 MB) — auto-created
├── /onion_data                 # Private Tor instance & onion service keys (Remote Access) — auto-created
├── /android                    # Android app: full Gradle project, ANDROID_BUILD.md and the ready-to-install AI-Switchboard.apk
│
├── /models                     # Whisper.cpp Model Folder (Optional)
│   ├── ggml-medium.bin         # Multilingual model (for PC setups)
│   └── ggml-base.bin           # Lightweight model (for low-RAM PC setups)
│
├── /languages                  # Localization JSON files
│   ├── /en-US                  # English Default Locale
│   │   ├── assistant.json      # Core AI prompts, hold rules, and logic variables
│   │   ├── gui.json            # Web Control Panel translations & defaults
│   │   └── spam.json           # Default SPAM lookup URL templates + home numbering plan (country code and national number length)
│   │
│   ├── /es-ES                  # Spanish Default Locale
│   │   ├── assistant.json
│   │   ├── gui.json
│   │   └── spam.json
│
├── /recordings                 # Call audio logs directory (Auto-created)
│   ├── call_1234_client.mp3    # Isolated caller audio (32 kbps; WAV if lameenc is missing)
│   └── call_1234.mp3           # Mixed synchronized call recording (64 kbps stereo: Left=Caller, Right=AI)
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

#### 📱 Accessing the Web GUI from a Smartphone (Same LAN or Tethering)
The Web GUI is a regular web page, so you can manage the switchboard directly from the **browser of the phone used for the calls**, or from **any other smartphone or tablet**, as long as the device running the assistant and the phone are on the **same local network** (home Wi-Fi/router) or connected through **tethering** (the phone's Wi-Fi hotspot, or USB tethering).

1. Start the GUI in LAN mode with `./my_gui.sh --lan` (or use the systemd service below, which already does this).
2. Note the LAN IP address printed in the terminal (`[INFO] Open your PC browser and go to: ...`), or find it with `hostname -I`.
3. On the phone, open the browser and enter:
   ```
   http://<ip_lan>:8501
   ```
   For example: `http://192.168.1.50:8501`

> **Tethering note:** when the assistant's device is connected to a phone's hotspot, its IP address is assigned by that phone (usually in a range like `192.168.43.x` or `172.20.10.x`), so check it again with `hostname -I` every time you change network.

> ⚠️ **Security warning:** the Web GUI has **no login or password** and includes sensitive features (call recordings, transcripts, messages, API settings and remote server reboot). Only use it on networks you trust, and **never expose port 8501 to the Internet** (no router port forwarding). For remote access from outside your LAN, see the next section.

#### 🌍 Remote Access from Anywhere (Outside Your LAN)
To manage the switchboard while away from home (mobile data, work, travel) **never expose the GUI to the Internet** (no router port forwarding, no `tailscale funnel`): it has no password. There are two safe ways, pick the one that suits you:

| | **Option A — Private VPN (Tailscale / WireGuard)** | **Option B — Built-in Tor (quick alternative)** |
|---|---|---|
| Setup | Install the VPN on the switchboard and on each phone/PC | Switch it on in the Web GUI; install the Android app on the phone |
| Accounts / third parties | Tailscale account (or your own WireGuard server) | None — no account, no router configuration, no third-party service |
| Speed & reliability | Fast and stable | **Can be slow, and may occasionally fail** (Tor circuits take time to build) |
| Works with | Any browser, Android and iPhone | The Android app, or Tor Browser on a PC (see below) |

##### Option A — Private VPN with Tailscale
[Tailscale](https://tailscale.com) is the easiest VPN: free for personal use, no router configuration or port forwarding, and it works even behind CGNAT (common with mobile and fibre ISPs).

**On the switchboard device (PC / Orange Pi):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # opens a login link: sign in once with your account
tailscale ip -4            # shows the private IP, e.g. 100.101.102.103
```

**On your phone (Android or iPhone):**
1. Install the **Tailscale** app and sign in with the **same account**.
2. Turn the VPN switch on.
3. Open the phone browser and go to:
   ```
   http://<tailscale_ip>:8501
   ```
   (or use the device's MagicDNS name, e.g. `http://orangepi:8501`).

**Tips:**
* Use the browser's **"Add to Home screen"** to get an app-like icon that opens the GUI directly.
* Optional HTTPS inside your private network: `sudo tailscale serve --bg 8501` publishes the GUI only to your own devices at `https://<device>.<tailnet>.ts.net`.
* Alternatives: a self-hosted **WireGuard** server on your router, or any other VPN that gives your phone a private route to the switchboard device.

##### Option B — Built-in Tor (private onion service, no third parties)
The switchboard can publish its Web GUI as a **private Tor onion service protected by an access key** (Tor "client authorization"): without the key nobody can even see that the service exists. It needs no account, no open ports and no router configuration, and it works behind CGNAT. The trade-off is speed: pages load slower than on a VPN, and a connection can occasionally fail and need a retry.

1. Install the two packages Tor access needs: run `./install_system_deps.sh --with-tor`, or `sudo apt install tor openssl`
2. Open the Web GUI and find the **Remote access (Tor)** panel. Press **▶️ Enable remote access** and wait until the status says **🟢 Active** (the first start can take a minute or two).
3. The onion address is shown with a **copy button**. Press **🔑 Show pairing code** to see the access key (also with a copy button), the full pairing link that joins both, and a QR code. **Keep them secret**: whoever has them can reach your panel.
4. Connect a device:
   * **Android phone → the [AI Switchboard app](#-android-app-ai-switchboard)** (recommended): scan the QR code, or paste the onion address and the access key in the two boxes, or paste the full pairing link in the first box.
   * **PC → Tor Browser (desktop)**: open the onion address; Tor Browser asks for the access key. *(Tor Browser for Android and other mobile Tor browsers may not support access-key protected onion services — according to the Tor Project's issue tracker, Tor Browser for Android did not support them when this was written — so on Android use the app.)*
   * **iPhone:** there is no app for iOS. Use Option A (Tailscale has an iOS app) or your home network.
5. To cut remote access at any time, press **⏹️ Disable remote access** in the same panel.

> The switchboard also pushes nothing to any server: the Android app *polls* it through Tor (see below), so no Google/Firebase service is involved.

---
**🛡️ Optional CLI SPAM Test**

You can also test any phone number against your configured SPAM providers from the terminal.
Run it from the project directory (also when connected via SSH):
```bash
cd ~/AI-Bluetooth-Phone-Assistant
source venv/bin/activate        # use your own environment name if different (.venv, conda...)
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
  ./my_gui.sh --logs
  # or directly:
  journalctl --user -u ai-switchboard.service -f -n 100 -a -o cat
  ```
  > The `-a -o cat` options matter: without them `journalctl` hides lines that contain colours/emojis. If your system keeps user services in the system journal, add yourself to the journal group once (`sudo usermod -aG systemd-journal $USER`, then log out and in); `./my_gui.sh --logs` handles that case automatically.
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
alias switchboard-log='journalctl --user -u ai-switchboard.service -f -n 100 -a -o cat'
alias switchboard-status='systemctl --user status ai-switchboard.service'
EOF
source ~/.bashrc
```

---

## 📱 Android App (AI Switchboard)

A small, free Android app that is the easiest way to reach your switchboard from **anywhere**: it opens the Web GUI through the Tor network built into the app and tells you when a caller leaves a message or a call has finished.

[**⬇️ Download the APK**](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/android/AI-Switchboard.apk) &nbsp;·&nbsp; Android 7.0 or newer &nbsp;·&nbsp; [Build it yourself](android/ANDROID_BUILD.md)

### Why it is worth installing
* 🔒 **Private by design.** The app talks **only to your own switchboard**, through the anonymous Tor network. It never contacts public servers or third-party services of its own: **no analytics, no ads, no trackers, no accounts, no Google or Firebase push service.** The connection is end-to-end encrypted and protected by an access key, and the app refuses to load any address other than your switchboard's.
* 🗄️ **It keeps almost nothing.** The only thing it stores is your pairing key, encrypted with the Android Keystore and excluded from Android backups, plus its own settings. Calls, recordings and messages stay on your switchboard; the panel you see is just a window onto it (like any browser, the phone may cache the pages it shows).
* 🔔 **Notifications without Google.** Because Tor is private, the app cannot receive instant pushes; instead it *checks your switchboard about every 15 minutes* (Android's minimum for background work; it can be later in battery-saver mode) and notifies you of **new caller messages** and **finished calls with their AI summary**. SPAM and blocked calls are not notified, and a call that left a message produces a single notification. On the lock screen only a generic text is shown; the content appears once you unlock. The first time you switch notifications on, old items are not sent.
* 🆓 **Free and open source (GPL v3).** The *About* button shows the version, the license notice and the licenses of the components it uses.

### Verify the download (optional)
The official APK (`android/AI-Switchboard.apk`, version 1.0.0) has this SHA-256: `6a2ebb0383f4b3ba00d301252c8b506acc9e61bfe44964cdb3cca8312e9e8d7d`. It is signed with a certificate (`CN=Antonio R.`) whose SHA-256 fingerprint is `d5a4c1db9733d27ade3c4054d771c049a716b86dbde1d2bc603f96297aa9fc42`; every future official version will carry the same certificate. Compare with `sha256sum` and `apksigner verify --print-certs`.

### Installation
1. On your phone, open the [APK link](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/android/AI-Switchboard.apk) (or download it on a PC and copy it over) and open the downloaded file.
2. Android will ask you to allow installing apps from this source (**"Install unknown apps"** for your browser or file manager). Allow it **only for that app**, then go back and tap **Install**. The app is not distributed through Google Play, so Google Play Protect may warn about an unknown developer: tap *More details → Install anyway*.
3. Open the app. When it asks for permission to show **notifications**, accept (Android 13+).
4. On the switchboard, enable **Remote access (Tor)** and press **Show pairing code** (see [Option B](#option-b--built-in-tor-private-onion-service-no-third-parties)).
5. In the app, **scan the QR code**, or paste the pairing text. The GUI shows the onion address and the access key separately: paste the onion address in the first box and the key in the second, or paste the full pairing link in the first box only.
6. Wait while it says *Connecting through Tor…* (the first connection can take 1–3 minutes). Then your Web GUI appears. Switch **Notifications** on if you want alerts.

### 🔍 About the QR scanner (for the very meticulous)
Scanning the QR code is optional and uses Google’s code scanner, a component of Google Play services. Images are processed on your device and the app only receives the resulting text. It requires Google Play services, which may download the scanner module the first time you use it. If you prefer not to use it, simply paste the onion address and key manually.

### Troubleshooting
| Problem | What to do |
|---|---|
| "App not installed" / the file will not open | Allow *Install unknown apps* for the app you used to open the APK. Android 7–8 has a single "Unknown sources" switch in Security settings. |
| Play Protect warns about an unknown developer | Expected for apps outside Google Play: *More details → Install anyway*. You can compare the file's SHA-256 with the one published in the release. |
| Stuck on *Connecting through Tor…* | The first connection takes 1–3 minutes. Press **Retry**. Check that the switchboard is on, has Internet, and that its Tor panel says **🟢 Active**. Some networks block Tor: try another Wi-Fi or mobile data. |
| *Cannot reach the switchboard* | The switchboard is off, offline, or remote access is disabled. |
| *The WebView … does not support the required proxy feature* | Update **Android System WebView** (and Chrome) in Google Play, or on devices without Google Play update the WebView component by the vendor's means. |
| *Invalid pairing data* | Paste the onion address (56 characters + `.onion`) and the key (52 characters) in the right boxes, or the full `aiphone://pair?…` link. Do not add spaces or quotes. |
| No notifications | Allow notifications for the app in Android settings; set the app's battery usage to **Unrestricted / Not optimised**; on Xiaomi, Huawei, Oppo, Samsung and similar, allow *autostart* / *background activity* and lock the app in recent apps. Checks happen about every 15 minutes, not instantly, and possibly later in Doze or battery saver. |
| Notifications appear with a generic text | That is intended on the lock screen; unlock the phone to read them. |
| The panel is slow | Normal with Tor. For a faster connection use Option A (VPN). |
| After reinstalling or changing phone | Pair again: the key is deliberately not backed up. |

---

## 🏗️ Architecture & Design Philosophy

This application is built as a **Monolithic State Machine** functioning as a deterministic Telephony Middleware around the LLM:

1. **Active Silence & Hold Tracking:** Tracks seconds of inactivity (`time_without_user`) to prompt silent callers or execute grace-period disconnections, while extending timeouts dynamically when a call is placed on hold (`self.on_hold`) or matches priority keywords.
2. **Deterministic Guardrails (`CallPolicyEngine`):** Intercepts AI tool calls (`hangup`, `save_message`) and validates them against the real-time state machine to prevent premature disconnections during active holds and store structured messages in the inbox.
3. **Streaming Chunk Reconstruction & Echo Stripping:** Accumulates fragmented streaming text chunks in a 2.5-second sliding window (`_asst_chunk_buffer`) to reliably evaluate goodbye and hold triggers while stripping assistant phrase bleed from incoming transcriptions.
4. **Hardware Actuation & Post-Call Curation:** Translates AI intent into `oFono` D-Bus calls, isolates PipeWire audio channels, records synchronized stereo call recordings (MP3, or WAV as fallback), and generates concise AI call summaries for future context memory.

---

## 📝 License
This project (switchboard and Android app) is licensed under the **GNU General Public License v3.0 or later**. See the `LICENSE` file for details.

The Android app also contains third-party components under their own licenses (all compatible with the GPL v3): Tor (`tor-android`, `jtorctl`; BSD 3-Clause), AndroidX / Kotlin / Kotlinx Coroutines (Apache 2.0) and the Noto Emoji artwork of the icon (Apache 2.0, © Google). Their notices are shown inside the app under *About → Licenses*. The optional QR scan relies on the Google Play services code scanner, which is not part of this repository.
