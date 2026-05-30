# 📞 AI Bluetooth Phone Assistant & Switchboard

![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini Live** for conversational AI and **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages, sets context-aware memory for repeat callers, and provides a sleek Web GUI to manage your communications.

> ⚠️ **DISCLAIMER & PRELIMINARY VERSION WARNING**
> This is a **preliminary, experimental version**. The author is not responsible for any errors, missed calls, or damages resulting from its use. There are many unhandled edge cases, potential API timeouts, and a remote but possible risk of privacy leaks (see the Privacy section below). Use it at your own risk.

> 🧪 **EXPERIMENTAL & UNTESTED FEATURES WARNING**
> Please note that several advanced features—specifically **real-time network SPAM database checking, Whitelist/Blacklist filtering, and Contact-Specific Custom Instructions**—are considered **highly experimental and largely untested**. While the code framework is implemented, they have not undergone thorough real-world verification. They may fail to trigger, parse incorrectly, or behave unpredictably under certain conditions.

> ⚖️ **LEGAL WARNING REGARDING CALL RECORDING**
> Laws regarding the recording of phone conversations and AI-driven voice processing vary significantly by jurisdiction and can be highly sensitive. For example, in jurisdictions like Spain (under European GDPR and local AEPD regulations), privacy laws are exceptionally strict. If this application is used for business or commercial purposes, you **must** configure the AI's initial greeting to explicitly and immediately inform the caller that the conversation is being recorded and processed by an automated AI system. Failure to provide proper notification can lead to severe legal penalties and substantial financial audits. It is your sole responsibility to ensure full compliance with local telecommunications, data protection, and privacy laws.

Author: Antonio R. | Version: 1.0 | License: GPL 3.0
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
*Streamlit-based GUI for managing call transcripts, SPAM rules, category memory, and AI personality settings.*
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy1.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy3.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy2.jpg)


---

## 🚀 Features & Technical Highlights

### 🌍 Universal Hardware & Bluetooth Compatibility
This code interacts directly with Linux D-Bus and PipeWire, making it a robust standard for audio routing:
*   **Linux Distributions:** Built and tested on Ubuntu 24.04, but designed for the "generational gap". It supports older/stable systems using *WirePlumber 0.4.x* (Lua scripts) and modern systems (Ubuntu 24.10+, Fedora 40+, Arch) using *WirePlumber 0.5.x* (Conf files).
*   **Hardware Resilience:** The code is resistant to hardware failures and network delays. If you turn off your phone's Bluetooth, the script will gracefully wait. Turn it back on, and it will seamlessly reconnect on the next execution.
*   **Mobile Support:** Works with iOS (iPhone), Android, or even a 15-year-old dumbphone, as long as it supports the **HFP (Hands-Free Profile - Audio Gateway)**. Your PC simply acts as a Bluetooth car headset.
*   **Audio Routing:** Creates a virtual `Null Sink` to isolate the AI's audio from local microphones, preventing echo.

### 🎧 Complex Bluetooth Scenarios
1.  **Headsets connected simultaneously:** If you have Bluetooth headphones connected to the PC while the phone rings, the script extracts the specific MAC address of the calling phone. It forces the HFP profile **only** on the phone, leaving your headset alone. *(Note: depending on your motherboard's BT chip bandwidth, handling A2DP music and HFP bidirectional audio simultaneously may cause slight audio drops).*
2.  **Two Phones Connected:** Linux (oFono) detects both phones as separate modems, but currently, the app has not been tested for multi-user/multi-instance use. There may be hardware limitations in handling both phones, so it is advisable to only have one of them paired.

---

## 🧠 Tuning & Personality

*   **Language & Accent:** The author is not a native English speaker. The prompts and default interactions were originally heavily tuned for **Spanish** and optimized for a personal assistant role handling specific edge cases.
*   **GUI Personality Changes:** You can radically modify the secretary's personality via the GUI (e.g., changing instructions, strictness, or tone). However, **be warned**: doing so can trigger unforeseen side effects or cause the AI to ignore structural commands like hanging up or saving messages.
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values.

---

## 🛠️ Installation & Setup

### 1. System Dependencies (Ubuntu 24.04 / Debian)
You need PipeWire, WirePlumber, oFono, and BlueZ working together.
```bash
sudo apt update
sudo apt install ofono ofono-scripts bluez pipewire wireplumber libportaudio2 libasound2-dev pactl sqlite3
```
*Note: Ensure your user is in the `bluetooth` and `audio` groups.*

### 2. Python Environment
Requires Python 3.10+.
```bash
python3 -m venv venv
source venv/bin/activate
pip install google-genai aiohttp streamlit
```

### 3. Installing `whisper.cpp` (Hybrid Transcription)
This app uses a hybrid approach: Gemini Live for conversational speed, and a local `whisper.cpp` executable for post-call audio alignment and noise filtering.

1. Clone the repository:
   ```bash
   git clone https://github.com/ggerganov/whisper.cpp.git
   cd whisper.cpp
   ```
2. **Compile it:**
   *   **CPU only:** `make`
   *   **NVIDIA GPU (CUDA):** `make GGML_CUDA=1`
   *   *(Other accelerations like OpenVINO or Vulkan are supported, check the whisper.cpp documentation).*
3. **Move the executable:**
   Copy the compiled `whisper-cli` (or `main`) executable into the root directory of *this* application, or ensure it's in a `./build/bin/` subfolder.
4. **Download Models:**
   Create a `models/` folder in the root of this app and download the `.bin` models (e.g., `ggml-medium.bin`). The GUI allows you to select which model and quantization to use.

---

## 📂 Project Directory Structure

Below is the directory scheme of the installation, showing where the main daemon, the SQLite database, the Whisper models, translations, and generated recordings are located:

```text
/AI-Bluetooth-Phone-Assistant
├── phone_assistant.py          # Main daemon (handles HFP, D-Bus, and Gemini Live)
├── gui.py                      # Web Control Panel (Streamlit GUI interface)
├── switchboard.db              # SQLite Database (Auto-generated on first launch)
├── requirements.txt            # Python package dependencies
├── whisper-cli                 # Compiled whisper.cpp executable (or symlink in root)
│
├── /models                     # Whisper.cpp Model Folder
│   ├── ggml-medium.bin         # Multilingual model (ideal for Spanish/bilingual setups)
│   └── ggml-medium.en.bin      # Highly optimized English-only model (recommended for English)
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
│   │
│   └── /fr-FR                  # [Example of adding a new language]
│       ├── assistant.json      # Simply translate the text values while
│       ├── gui.json            # keeping the exact same variable keys intact!
│       └── spam.json
│
├── /recordings                 # Call audio logs directory (Auto-created)
│   ├── call_1234_client.wav    # Isolated caller audio (16kHz mono, used for offline Whisper)
│   └── call_1234.wav           # Mixed synchronized call recording (24kHz stereo: Left=Caller, Right=AI)
│
└── /build                      # Optional whisper.cpp compilation tree (if cloned in the same folder)
    └── /bin
        └── whisper-cli         # Original compiled path of the whisper-cli executable

```

### Directory Components Breakdown:
*   **`switchboard.db`:** The SQL database created automatically at runtime. It holds the active calls history, whitelist/blacklist rules, and persistent GUI configuration settings.
*   **`/models`:** This is where you place the offline GGML model binaries downloaded for `whisper.cpp`. 
    *   *Tip:* For English-only installations, using the specialized English-only models (e.g., **`ggml-medium.en.bin`** or **`ggml-base.en.bin`**) provides significantly better performance, lower resource usage, and higher accuracy compared to their standard multilingual counterparts.
*   **`/languages`:** Contains separate directory folders for each translation locale. Adding a new language (like the `/fr-FR` example) is as simple as creating a folder, copying the JSON files, and translating their text values while preserving the original JSON parameter keys.
*   **`/recordings`:** This directory holds the audio files of the processed calls. For every call, it generates a clean mono caller track (used for post-call Whisper transcription) and a high-quality synchronized stereo master containing both speaker channels separated.

---

## ⚙️ Configuration & GUI Options

Run the Control Panel:
```bash
streamlit run gui.py
```

### GUI Highlights:
*   **Call Log & Transcripts:** View full stereo recordings and transcripts. You can edit or delete specific phrases if the AI hallucinated.
*   **SPAM Protection:** Configure external URLs to check phone numbers against SPAM databases in real-time. The AI analyzes the HTML of the provider using a text model to decide if it should hang up automatically.
*   **Category Memory:** Define keywords (e.g., "doctor", "lawyer") and set specific wait times (hold limits) before the AI hangs up.
*   **Audio Mode:** Toggle software echo suppression if your Bluetooth setup causes audio feedback.

To start the actual phone assistant daemon:
```bash
python3 phone_assistant.py
```
*You must provide your Gemini API key via the environment variable `GEMINI_API_KEY`.*

---

## 🔒 Dynamic Call Memory & Context Isolation

The application features a "Call Memory" system that allows the assistant to maintain continuity by referencing the last conversation when a caller calls back. It is important to understand how this is handled technically and its exact scope:

### 1. Data Isolation & Sandbox Scope
*   **Zero System Integration:** Neither the AI nor the application has access to your personal files, emails, calendar, contacts, or any other private operating system data.
*   **Explicit Context Only:** The assistant's entire knowledge base is strictly sandboxed. It only knows what you explicitly configure in the Web GUI (such as the boss's name, expected calls, and business description) and the SQLite call logs database.

### 2. Default Guarded Behavior (Concise & Neutral)
By default, the assistant is configured with a **highly professional, guarded, and straight-to-the-point personality**. 
*   It does not volunteer or reveal any information about the owner (such as last names, current location, or schedule).
*   It focuses strictly on taking messages or managing hold requests, keeping interactions brief and direct.

### 3. Personality Tuning & Behavioral Edge Cases
While the default profile is highly secure, the Web GUI allows you to modify the assistant's personality. If you configure a highly talkative, jovial, or over-compliant personality, certain edge cases can theoretically occur in rare circumstances:
*   **Over-Compliance:** A highly friendly personality might be more prone to becoming talkative if pressed by an inquisitive caller.
*   **Shared Office Numbers (Caller ID Matching):** The system retrieves the last conversation based strictly on the caller's phone number (`SELECT transcript FROM calls WHERE number=?`). If multiple people call your assistant from the exact same corporate switchboard or shared office number, the background context of the second call will contain the transcript of the first call. Under a highly compliant custom personality, the AI could reference past details if the new caller explicitly asks about them.

---

## 📝 License
This project is licensed under the GPL v3 License. See the `LICENSE` file for details.
