# 📞 AI Bluetooth Phone Assistant & Switchboard

![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini Live** for conversational AI and **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages, sets context-aware memory for repeat callers, and provides a sleek Web GUI to manage your communications.

> ⚠️ **EXPERIMENTAL SOFTWARE — USE AT YOUR OWN RISK**
> This is an experimental project distributed as-is, without warranty. It may contain bugs, missed-call scenarios, transcription errors, or other untested edge cases. Several advanced features — specifically **real-time SPAM database checking, Whitelist/Blacklist filtering, and Contact-Specific Custom Instructions** — are implemented but have not been thoroughly verified in real-world conditions.
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

To overcome these commercial barriers, I have developed this Python application that operates as an independent orchestrator from any PC or Linux SBC (single-board computer). By connecting to the mobile phone via Bluetooth, the system acts as a supercharged version of Google's solutions that allows answering calls (only answering, to avoid most legal restrictions for normal users) without suffering geographical blocks or depending on specific mobile hardware. This architecture offers complete and unrestricted control to manage bidirectional audio, transcribe conversations, and generate real-time responses using AI. Furthermore, it provides full control over the call history, and at any moment, the user can interrupt the AI to take manual control of the call, among many other improvements that will be added in the future.

<div align="center">
  <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant1.jpg" width="80%">
  <br><b>🏖️ Free time call answered.</b>
</div>

<br>

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant2.jpg" width="100%">
      <br><b>🛠️ Hands-Free & Deep Work</b><br>
      Perfect for mechanics, freelancers, or programmers. Maintain your flow state or keep working with dirty hands while your AI secretary gracefully handles clients and takes detailed messages.
    </td>
    <td width="50%" align="center" valign="top">
      <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant3.jpg" width="100%">
      <br><b>🛡️ The Ultimate SPAM Shield</b><br>
      Enjoy your free time in peace. The AI intercepts unknown callers, verifies their numbers against live SPAM databases, and automatically terminates telemarketing calls before they bother you.
    </td>
  </tr>
</table>

Author: Antonio R. | Version: 1.2 | License: GPL 3.0

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
*   **GUI Personality Changes:** You can radically modify the secretary's personality via the GUI (e.g., changing instructions, strictness, or tone). Note that significant personality changes may affect the reliability of structural commands like hanging up or saving messages.
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values. In some cases you could slightly modify the default prompts — for example, changing "If they suggest leaving it with a neighbour, give permission for this" instead of "If they suggest leaving it with a neighbour, NEVER give permission for this". Depending on your regional slang you can extend or shorten word lists related to a given variable.

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
The `_calculate_text_similarity` helper splits text using Python's `str.split()`, which tokenizes by whitespace. Chinese and Japanese writing systems do not use spaces between words, so this function will always return `0.0` similarity for CJK input, breaking the hallucination-detection and deduplication logic. Adapting the system for CJK languages requires replacing the whitespace tokenizer with a dedicated segmenter.

### 3. Right-to-Left (RTL) Languages (Arabic, Hebrew)
Although SQLite and the Gemini API natively process UTF-8 encoded Arabic and Hebrew text, most standard Linux terminal emulators and Streamlit layout renderers do not natively support complex bidirectional text mixing. Expect visual alignment issues in live terminal logs and Web GUI logs.

### 4. Voice Synthesis (TTS) Restrictions
The Gemini Live connection is hardcoded to use only two voices (Aoede for female, Puck for male). While Gemini Live handles many languages with these voices, quality varies significantly for non-Western languages. For best results, change the `voice_name` in `phone_assistant.py` to a voice optimized for your target language.

### 5. Planned Support & Future Roadmap
Expanding native compatibility for non-Latin scripts, localized voice mapping, and multi-language SPAM filtering is planned for future releases. These updates will be integrated progressively as development resources and API capabilities permit.

---

## 🛠️ Installation & Setup


> ⚠️ **WARNING FOR SBC USERS (Orange Pi Zero 3, Raspberry Pi, etc.):**
> SBCs not tested; for now, they might not be supported due to different system software/hardware.


### 1. Clone the Assistant Repository
First, download this project to your machine and navigate into its folder:
```bash
git clone https://github.com/antor44/AI-Bluetooth-Phone-Assistant.git
cd AI-Bluetooth-Phone-Assistant
```

### 2. System Dependencies

**For standard Desktop Linux (Ubuntu 24.04):**
You need PipeWire, WirePlumber, oFono, and BlueZ working together.
```bash
sudo apt update
sudo apt install ofono ofono-scripts bluez pipewire wireplumber libportaudio2 libasound2-dev pulseaudio-utils sqlite3 python3.12-venv build-essential cmake
```

**Crucial Permissions Step (Mandatory for non-root/Headless users):**
```bash
sudo usermod -aG bluetooth,audio $USER
sudo reboot
```

### 3. Python Environment
Requires Python 3.10+. On modern Debian/Ubuntu systems (PEP 668), use a virtual environment giving it access to system-site-packages so `dbus-python` functions properly:
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install google-genai aiohttp streamlit
```

### 4. Installing `whisper.cpp` (Hybrid Transcription)
This app uses a hybrid approach: Gemini Live for conversational speed, and a local `whisper.cpp` executable for post-call audio alignment and noise filtering.

To compile and optimize `whisper.cpp` for your hardware, follow these steps:

1. **Clone the repository:**
   ```bash
   cd ~
   git clone https://github.com/ggerganov/whisper.cpp.git
   cd whisper.cpp
   ```

2. **Compile the executables:**
   Choose the option that matches your system architecture:

   * **Option A: CPU-only Mode (Recommended for SBCs/Standard CPU)**
     ```bash
     cmake -B build
     cmake --build build -j --config Release
     ```
     Or using standard Make: `make -j`

   * **Option B: NVIDIA GPU Acceleration (CUDA)**
      - **Requirements**: Install CUDA toolkit (https://developer.nvidia.com/cuda-downloads).  
      - **Compilation**:  
      ```bash
      cmake -B build -DGGML_CUDA=1
      cmake --build build -j --config Release
      ```
        - For newer GPUs (e.g., RTX 5000+ series):  
      ```bash
      cmake -B build -DGGML_CUDA=1 -DCMAKE_CUDA_ARCHITECTURES="86"
      cmake --build build -j --config Release
     
     ```bash
     cmake -B build -DGGML_CUDA=1
     cmake --build build -j --config Release
     ```

3. **Move the binaries to the Assistant root folder:**
   ```bash
   # Go to your AI-Bluetooth-Phone-Assistant folder
   cd ~/AI-Bluetooth-Phone-Assistant

   # Copy the main whisper executable
   cp ~/whisper.cpp/build/bin/whisper-cli ./whisper-cli 2>/dev/null || cp ~/whisper.cpp/main ./whisper-cli

   # Copy the quantization executable (required to run quantized .bin models like Q8_0)
   cp ~/whisper.cpp/build/bin/whisper-quantize ./whisper-quantize 2>/dev/null || cp ~/whisper.cpp/quantize ./whisper-quantize
   ```

4. **Download and prepare Model Files:**
   Create a `models/` directory in the root of the assistant app, download a GGML model, and (optionally) quantize it to save RAM:
   ```bash
   mkdir -p ~/AI-Bluetooth-Phone-Assistant/models
   sh ~/whisper.cpp/models/download-ggml-model.sh medium
   mv ~/whisper.cpp/models/ggml-medium.bin ~/AI-Bluetooth-Phone-Assistant/models/

   # (Optional) Quantize to Q8_0 to drastically reduce VRAM/RAM consumption
   cd ~/AI-Bluetooth-Phone-Assistant
   ./whisper-quantize models/ggml-medium.bin models/ggml-medium-q8_0.bin q8_0
   ```

### 5. Bluetooth Mobile Pairing (Crucial!)
Establishing an active, unencrypted bidirectional Hand-Free profile between Linux and your smartphone requires explicit "agent authentication".

*Desktop environments (GNOME/Ubuntu) typically fail to handle the secure PIN confirmation automatically. However, if relying on the terminal, ** you MUST explicitly approve the PIN **.*

1. **Launch `bluetoothctl` terminal tool:**
   ```bash
   bluetoothctl
   ```
2. **Execute pairing sequence securely:**
   ```text
   power on
   agent on
   default-agent
   scan on
   ```
   Wait for your phone to appear. Then run:
   ```text
   pair XX:XX:XX:XX:XX:XX
   ```
   **CRUCIAL STEP:** In the terminal, it will ask `[agent] Confirm passkey XXXXXX (yes/no):`. **You MUST type `yes`** on the PC console *and immediately press Confirm/Accept on your Smartphone's screen at the same time!* Failing to validate the agent breaks the SCO voice sub-channel.

3. **Establish final trust:**
   ```text
   trust XX:XX:XX:XX:XX:XX
   connect XX:XX:XX:XX:XX:XX
   quit
   ```

> **WirePlumber config mismatch notice:** This script edits your routing config dynamically. If running older OS setups (Ubuntu 24.04), WirePlumber <0.5 configs reside in `.lua`. For bleeding-edge distros (Trixie/Ubuntu 24.10) using WirePlumber 0.5+, configs exist as `.conf`. This script modifies files transparently behind the scenes, mapping `backend="ofono"` to handle voice hardware effectively over Pulse/PipeWire constraints.

---

## 🔑 API Key Setup, Pricing & Privacy

This application relies on the **Google Gemini API** to function. It uses `gemini-3.1-flash-live-preview` for real-time, low-latency bidirectional voice communication, and secondary text models (like `gemini-3-flash-preview` or the `gemma-4` family) for offline tasks like SPAM evaluation and post-call JSON transcript structuring.

### 1. How to Obtain and Set Your API Key
1. Go to **[Google AI Studio](https://aistudio.google.com/)**.
2. Sign in with your Google account.
3. Click on **"Get API key"** and then **"Create API key"**.
4. Copy the generated key immediately.
5. Export the key as an environment variable in your terminal before running the script:
   ```bash
   export GEMINI_API_KEY="YOUR_API_KEY_HERE"
   ```
   *(Tip: Add this line to your `~/.bashrc` or `~/.profile` so it loads automatically).*

### 2. Free Tier vs. Paid Tier — Privacy Considerations
Google AI Studio offers a generous Free Tier, but it comes with a privacy trade-off:
*   **Free Tier:** Google may use conversation data (anonymously) to improve their AI models. If you are handling sensitive personal or business phone calls, consider using the Paid Tier instead.
*   **Paid Tier (Pay-As-You-Go):** Your data is strictly private — Google explicitly states that Paid API data is *not* used to train their models.

**For a privacy-focused deployment, the Paid Tier is recommended.**

### 3. Approximate Pricing (Pay-As-You-Go)
The Paid API operates strictly on a pay-per-use basis: if you don't receive calls, you pay nothing. For normal personal or small-business use, the cost is exceptionally low (typically just a few cents per day).

*   **Real-Time Voice Calls (`gemini-3.1-flash-live-preview`):**
    *   *Audio Input:* ~$0.005 per minute of caller audio.
    *   *Audio Output:* ~$0.018 per minute of assistant speech.
    *   *(A typical 2-minute phone call will cost around $0.04).*
*   **Text Processing & SPAM (`gemini-3-flash-preview`):**
    *   Used silently in the background for SPAM checking and parsing call transcripts.
    *   *Cost:* ~$0.50 per 1 Million input tokens and ~$3.00 per 1 Million output tokens. This equates to fractions of a cent per call.

### 4. Offline Text Processing & Final Transcription Selection
The GUI provides flexibility in how post-call tasks are handled:

*   **Text Processing Models (`gemini` vs `gemma-4`):**
    *   **`gemini-3-flash-preview`:** The default and most stable choice for text processing.
    *   **`gemma-4` Family (`gemma-4-31b-it` / `gemma-4-26b-a4b-it`):** Open-weight alternatives. The 31B version is slightly more comprehensive; the 26B provides faster response times. *(Note: online API endpoints for the Gemma-4 family currently exhibit lower stability compared to native Gemini endpoints).*
*   **Final Audio Transcription (Whisper vs Online AI):**
    By default, the app uses a local `whisper.cpp` executable for the final cleanup and alignment of the call transcript. You can change this in the GUI to use the online API instead (selecting *"Gemini at end"*), which uploads the isolated caller audio to `gemini-3-flash-preview` for final processing.

### 5. Free Tier Limits in Real-World Calls
If you choose to test on the Free Tier, the limits are more than sufficient for a standard personal switchboard. Human speech is slow in terms of token generation:

*   **Voice Limits (Gemini 3.1 Flash Live):** Google converts audio at ~25 tokens per second (1,500 tokens/minute). The Free Tier limit is 150,000 TPM — you would need **100 active simultaneous calls** to hit this limit.
*   **Text Limits (Gemma 4 / Gemini 3 Flash):** SPAM checks and transcript summaries require 1–2 HTTP requests per call. Even the strictest model limit (Gemma 4 at 30 RPM) means you would need more than **15 incoming calls within a single 60-second window** before the API temporarily throttles the request.

---

## 📂 Project Directory Structure

```text
/AI-Bluetooth-Phone-Assistant
├── phone_assistant.py          # Main daemon (handles HFP, D-Bus, and Gemini Live)
├── my_gui.sh                   # Main GUI Launcher Script (Network and Env aware)
├── gui.py                      # Web Control Panel (Streamlit GUI interface)
├── switchboard.db              # SQLite Database (Auto-generated on first launch)
├── requirements.txt            # Python package dependencies
├── whisper-cli                 # Compiled whisper.cpp executable (or symlink in root)
├── whisper-quantize            # Compiled quantize executable (for .bin models)
│
├── /models                     # Whisper.cpp Model Folder
│   ├── ggml-medium.bin         # Multilingual model (ideal for Spanish/bilingual setups)
│   └── ggml-medium-q8_0.bin    # Optimized low-RAM English model 
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
│   ├── call_1234_client.wav    # Isolated caller audio (16kHz mono, used for offline Whisper)
│   └── call_1234.wav           # Mixed synchronized call recording (24kHz stereo: Left=Caller, Right=AI)
```

**Key notes:**
*   **`switchboard.db`:** Auto-created at runtime. Holds call history, whitelist/blacklist rules, and persistent GUI configuration settings.
*   **`/models`:** For English-only installations, specialized English-only models (e.g., `ggml-medium.en.bin`) provide significantly better performance and accuracy than their multilingual counterparts.
*   **`/languages`:** Adding a new language is as simple as creating a folder, copying the JSON files, and translating the text values while preserving the original JSON parameter keys.
*   **`/recordings`:** Generates a clean mono caller track (for post-call Whisper transcription) and a synchronized stereo master with both speaker channels separated. Manage these files according to your privacy preferences.

---

## ⚙️ Configuration & GUI Options

Run the combined script inside your directory:
```bash
./my_gui.sh
```
*Note: In headless (Server Mode/SBC), it natively outputs your Local Network URL (ex: `http://192.168.1.100:8501`) directly through `my_gui.sh --lan` / 0.0.0.0 detection so you can administer calls out of network boundaries properly.*

### GUI Highlights:
*   **Call Log & Transcripts:** View full stereo recordings and transcripts. You can edit or delete specific phrases if the AI hallucinated.
*   **SPAM Protection:** Configure external URLs to check phone numbers against SPAM databases in real-time. The AI analyzes the HTML of the provider using a text model to decide if it should hang up automatically.
*   **Category Memory:** Define keywords (e.g., "doctor", "lawyer") and set specific wait times (hold limits) before the AI hangs up.
*   **Audio Mode:** Toggle software echo suppression if your Bluetooth setup causes audio feedback (which uses internal backend `both` default commands copying mic lines). Change settings per GUI layout if interference occurs across speakers!

### Suggested Greeting Pattern
A safe and clear default greeting for most jurisdictions:

> "Hello. You are speaking with an AI assistant. This call may be recorded and transcribed to handle your request. Please do not share unnecessary sensitive information."

---

## 🔒 Dynamic Call Memory & Context Isolation

The application features a "Call Memory" system that maintains continuity by referencing the last conversation when a caller calls back.

### Data Isolation & Sandbox Scope
*   **Zero System Integration:** Neither the AI nor the application has access to your personal files, emails, calendar, contacts, or any other private operating system data.
*   **Explicit Context Only:** The assistant's entire knowledge base is strictly sandboxed. It only knows what you explicitly configure in the Web GUI (such as the boss's name, expected calls, and business description) and the SQLite call logs database.

### Default Guarded Behavior (Concise & Neutral)
By default, the assistant is configured with a **highly professional, guarded, and straight-to-the-point personality**.
*   It does not volunteer or reveal any information about the owner (such as last names, current location, or schedule).
*   It focuses strictly on taking messages or managing hold requests, keeping interactions brief and direct.

### Shared Number Edge Case
The system retrieves the last conversation based strictly on the caller's phone number (`SELECT transcript FROM calls WHERE number=?`). If multiple people call from the exact same corporate switchboard or shared office number, the background context of the second call will contain the transcript of the first. This is an expected technical limitation for shared lines.

---

## 🏗️ Architecture & Design Philosophy

At first glance, the main `phone_assistant.py` daemon is a dense, monolithic script containing numerous hardcoded rules, timeouts, and state trackers. A common question when working with advanced models like Gemini Live is: *Why build such complex logic around the AI? Shouldn't a sufficiently prompted LLM handle edge cases naturally?*

The answer is a definitive **no**. Relying purely on the LLM to manage a physical, real-time telephony environment is unreliable. This application was built using a **Monolithic State Machine** approach functioning as a robust Telephony Middleware. Here is why:

### 1. LLMs Have No Perception of Time (The Silence Problem)
Gemini Live generates text and audio based on input, but it has no internal clock. If a caller goes silent, the LLM simply waits indefinitely. The state machine actively tracks seconds of inactivity (`time_without_user`) and artificially forces the AI to prompt the user (e.g., *"Are you still there?"*) or initiating a grace-period termination.

### 2. Deterministic Guardrails vs. Probabilistic AI
LLMs are probabilistic. If you instruct an AI via system prompt to *"Never hang up while the user is on hold"*, it will obey 90% of the time. But if background noise occurs, the AI might hallucinate a goodbye and hang up.
This project implements a `CallPolicyEngine` (Deterministic Guardrails). When the AI attempts to use a tool (like `hangup`), the engine intercepts the request and verifies the hardcoded system state. If `self.on_hold == True`, the code explicitly denies the AI's request. **Business rules must be hardcoded; they cannot be left purely to neural network probability.**

### 3. The Fragmentation of Streaming APIs
Real-time streaming APIs deliver text in fragmented chunks. The AI might send `"Good"`, and 500ms later send `"bye"`. If the code evaluated chunks individually to detect call-termination triggers, it would fail. The script employs an accumulator buffer (`_asst_chunk_buffer`) with a 2.5-second sliding window to properly reconstruct and evaluate semantic intent before triggering physical hardware actions.

### 4. Hardware Actuation & Hallucination Curation
Gemini Live cannot physically hang up a Linux modem; the Python code must translate semantic AI intent into `oFono` D-Bus signals. Furthermore, live audio over Bluetooth HFP is prone to noise, causing Gemini to hallucinate bizarre foreign words. The integration of local `whisper.cpp` acts as an asynchronous post-processor to clean the database logs, ensuring transcripts are usable for future memory injection.

In summary, this codebase bridges the gap between a "disembodied AI brain" and the physical realities of Bluetooth radio, acoustic noise, and strict telephony protocols.

---

## 📝 License
This project is licensed under the GPL v3 License. See the `LICENSE` file for details.
