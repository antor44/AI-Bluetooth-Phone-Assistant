# 📞 AI Bluetooth Phone Assistant & Switchboard

![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini Live** for conversational AI and **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages, sets context-aware memory for repeat callers, and provides a sleek Web GUI to manage your communications.

> ⚠️ **EXPERIMENTAL SOFTWARE / NO WARRANTY / LEGAL NOTICE**
> This project is an **experimental AI phone assistant** for technically competent users. It is distributed **as-is**, without warranty, and may contain bugs, missed-call scenarios, transcription errors, privacy-impacting failures, or other unsafe edge cases.
>
> If you deploy, repackage, integrate, modify, or operate it in a real environment, **you** are responsible for compliance with local law, including caller notice, recording/transcription rules, retention, access control, and any sector-specific requirements. This repository is a technical project, not legal advice and not a guarantee that any particular deployment is lawful or production-safe.
>
> In practice, the safest profile is usually: **incoming calls only**, clear first-message disclosure, minimal data retention, and a conservative assistant configuration.
>
> 🧪 **EXPERIMENTAL & UNTESTED FEATURES WARNING**
> Please note that several advanced features—specifically **real-time network SPAM database checking, Whitelist/Blacklist filtering, and Contact-Specific Custom Instructions**—are considered **highly experimental and largely untested**. While the code framework is implemented, they have not undergone thorough real-world verification. They may fail to trigger, parse incorrectly, or behave unpredictably under certain conditions.

## 🌟 Why use this? (Use Cases)

<div align="center">
  <img src="https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/Pi_assistant1.jpg" width="80%">
  <br><b>🏖️ Free time call answered</b>
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
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values. In determinated cases you could modify slightly the default prompts, for example, change "If they suggest leaving it with a neighbour, give permission for this" instead of "If they suggest leaving it with a neighbour, NEVER give permission for this". Depending on your regional slang you can extend or shorten the word list related to a variable.

### Recommended Operating Profile
For privacy-sensitive or legally cautious deployments, the safest default profile is generally:
*   concise,
*   neutral,
*   non-chatty,
*   inbound-call focused,
*   resistant to oversharing,
*   and limited to call handling, message capture, hold management, and basic classification.

A more playful, emotionally warm, or highly compliant personality may sound nicer, but it can also increase the risk of over-disclosure, prompt drift, or ambiguous behavior during real calls.

---

## 🌐 Multi-Language Compatibility & Script Limitations

While the application is structurally designed to support translation locales via JSON files, there are technical limitations in the current codebase regarding non-Latin scripts, Asian languages, and Right-to-Left (RTL) languages:

### 1. Hardcoded Character Filtering (CJK Languages)
At the code level, the daemon employs a regex-based noise filter in the is_valid_text function to discard transcription artifacts caused by Bluetooth static. This filter explicitly blocks and discards any text containing character ranges for:

Chinese (Kanji/Hanzi: \u4e00-\u9fff)
Japanese (Hiragana/Katakana: \u3040-\u30ff)
Korean (Hangul: \uac00-\ud7a3 / \u1100-\u11ff)

If a caller speaks in Chinese, Japanese, or Korean, the daemon will classify the input as noise, skip the processing branch entirely, and produce no response to the caller.

### 2. Word Tokenization Failure (CJK Languages)
The _calculate_text_similarity helper splits text using Python's str.split(), which tokenizes by whitespace. Chinese and Japanese writing systems do not use spaces between words, so this function will always return 0.0 similarity for CJK input, breaking the hallucination-detection and deduplication logic that depends on it. Adapting the system for CJK languages requires replacing the whitespace tokenizer with a dedicated segmenter.

### 3. Right-to-Left (RTL) Languages (Arabic, Hebrew)
Although SQLite and the Gemini API natively process UTF-8 encoded Arabic and Hebrew text, most standard Linux terminal emulators and Streamlit layout renderers do not natively support complex bidirectional text mixing. Expect visual alignment glitches, displaced punctuation, and inverted text ordering in live terminal logs and Web GUI logs.

### 4. Voice Synthesis (TTS) Restrictions
The Gemini Live connection is hardcoded to use only two voices (Aoede for female, Puck for male). While Gemini Live does handle many languages with these voices, quality varies significantly for non-Western languages. If you configure the system prompt to operate in languages like Russian, Hindi, or Arabic, the voice synthesizer may sound heavily accented or produce noticeably degraded output. For best results, change the voice_name in phone_assistant.py to a voice optimized for your target language.

### 5. Planned Support & Future Roadmap
Expanding native, out-of-the-box compatibility for non-Latin scripts, localized voice mapping, and multi-language SPAM filtering is planned for future releases. These updates will be integrated progressively as development resources and API capabilities permit.

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

### 4. Bluetooth Mobile Pairing (Crucial for Ubuntu 24.04 / Modern GNOME)
On modern Linux distributions like **Ubuntu 24.04** (and other desktops using modern GNOME or KDE Plasma), pairing your mobile phone using the default desktop Settings GUI often fails to establish the necessary telephony integration. The desktop GUI frequently pairs devices solely as media audio players (A2DP), ignoring or blocking the **Hands-Free Profile (HFP)** required by `oFono` to detect incoming calls.

To ensure your phone is recognized correctly as a telephony gateway, **you must pair, trust, and connect the device via the terminal using direct `bluetoothctl` commands**:

1. **Find your phone's Bluetooth MAC address:**
   Turn on Bluetooth on your phone and make it discoverable. Note your phone's MAC address (which looks like `50:2F:BB:89:0C:BE`).

2. **Execute the pairing sequence directly from your terminal:**
   Replace `XX:XX:XX:XX:XX:XX` with your phone's actual MAC address:

   ```bash
   # 1. Pair the device (accept any numeric confirmation prompts on your phone)
   bluetoothctl pair XX:XX:XX:XX:XX:XX

   # 2. Trust the device so it can reconnect automatically in the future
   bluetoothctl trust XX:XX:XX:XX:XX:XX

   # 3. Establish the connection manually
   bluetoothctl connect XX:XX:XX:XX:XX:XX
   ```

3. **Verification through the Assistant:**
   Once paired, when you run the `phone_assistant.py` script, it will automatically attempt to detect and connect to your phone via oFono. Watch the terminal output for the status:
   *   `[OK] oFono modem ready: /hfp/org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX` (If successful).
   *   `[INFO] oFono: no modems found. Ensure your phone is connected via Bluetooth.` (If it fails).
   *   *Tip:* If your phone is connected but not detected by oFono, restart the Bluetooth service (`sudo systemctl restart bluetooth`) to trigger a clean re-scan.

---

## 🔑 API Key Setup, Pricing & Privacy

This application relies on the **Google Gemini API** to function. It uses the groundbreaking `gemini-3.1-flash-live-preview` model for real-time, low-latency bidirectional voice communication over Bluetooth, and secondary text models (like `gemini-3-flash-preview` or the `gemma-4` family) for offline tasks like SPAM evaluation and post-call JSON transcript structuring.

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

### 2. ⚠️ Privacy Warning: Free Tier vs. Paid Tier
Google AI Studio offers a generous Free Tier, but it comes with a critical privacy trade-off:
*   **Free Tier:** By using the free API, you agree to Google's terms which allow them to collect and use your conversation data (anonymously) to train and improve their AI models. If you are handling sensitive personal or business phone calls, **do not use the Free Tier**.
*   **Paid Tier (Pay-As-You-Go):** When you set up a billing account, **your data is strictly private**. Google explicitly states that Paid API data is *not* used to train their models. 

**For a privacy-focused phone switchboard, enabling the Paid Tier is highly recommended.** 

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
The GUI provides flexibility in how post-call tasks (SPAM checks, JSON state extraction, and final audio alignment) are handled:

*   **Text Processing Models (`gemini` vs `gemma-4`):**
    *   **`gemini-3-flash-preview`:** The default and most stable choice for text processing. It perfectly balances speed, reliability, and low cost.
    *   **`gemma-4` Family (`gemma-4-31b-it` / `gemma-4-26b-a4b-it`):** You can opt for these open-weight models. The 31B version is slightly more comprehensive, while the 26B provides faster response times. *(Warning: online API endpoints for the Gemma-4 family currently exhibit lower stability compared to native Gemini endpoints).*
*   **Final Audio Transcription (Whisper vs Online AI):**
    By default, the app uses a local `whisper.cpp` executable to perform the final cleanup and alignment of the call transcript without relying on the cloud. However, **you can change this in the GUI** to use the online API instead (selecting *"Gemini at end"*). 
    *   If you select the online option, the app uploads the isolated caller audio to `gemini-3-flash-preview` for final processing. 

### 5. Understanding Free Tier Limits in Real-World Calls
If you choose to test the application on the Free Tier, the limits provided by Google are **more than sufficient** for a standard phone switchboard environment. Human speech is slow in terms of token generation:

*   **Voice Limits (Gemini 3.1 Flash Live):** Google converts audio at a rate of 25 tokens per second (1,500 tokens per minute). The Free Tier limit is 150,000 Tokens Per Minute (TPM). You would need **100 active phone calls simultaneously** to hit this limit.
*   **Text Limits (Gemma 4 / Gemini 3 Flash):** SPAM checks and transcript summaries require 1 or 2 HTTP requests per call. Even the strictest model limit (Gemma 4 at 30 Requests Per Minute) means you would need to receive **more than 15 incoming calls in a single 60-second window** before the API temporarily blocks the request.
   
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

### Data Storage & Sensitivity Note
The presence of call audio, transcripts, and per-number history means this directory structure should be treated as sensitive local data. Real deployments should think about file permissions, disk encryption, backup scope, retention limits, and explicit deletion workflows rather than indefinite accumulation.

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

### Deployment Caution
The GUI makes the system highly configurable, but legal or privacy compliance does **not** come from merely having an option available in the interface. In live operation, disclosure, recording rules, retention, and personality constraints should be treated as deployment requirements, not decorative toggles.

### Suggested Greeting Pattern
A safer default greeting for many jurisdictions is something close to:

> “Hello. You are speaking with an AI assistant. This call may be recorded and transcribed to handle your request. Please do not share unnecessary sensitive information.”

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

### 4. Safer Memory Practices
If you plan to deploy this beyond hobby testing, a more cautious approach is usually better:
*   keep only the minimum context required,
*   separate short message memory from general free-form memory,
*   expire old call history automatically where possible,
*   avoid keeping sensitive context unless there is a clear operational reason,
*   and do not assume that caller ID always maps to one real human being.

---

## 🏗️ Architecture & Design Philosophy (Why not just let the LLM do everything?)

At first glance, the main `phone_assistant.py` daemon is a dense, monolithic script containing numerous hardcoded rules, timeouts, and state trackers. A common question when working with advanced models like Gemini Live is: *Why build such complex "spaghetti" logic around the AI? Shouldn't a sufficiently prompted LLM handle edge cases naturally?*

The answer is a definitive **no**. Relying purely on the LLM to manage a physical, real-time telephony environment is unreliable. This application was built using a **Monolithic State Machine** approach functioning as a robust Telephony Middleware. Here is why this architecture was absolutely necessary:

### 1. LLMs Have No Perception of Time (The Silence Problem)
Gemini Live generates text and audio based on input, but it has no internal clock. If a caller goes silent, the LLM simply waits indefinitely. The dense logic loops in this script act as the "nervous system", actively tracking seconds of inactivity (`time_without_user`) and artificially forcing the AI to prompt the user (e.g., *"Are you still there?"*) or initiating a grace-period termination. 

### 2. Deterministic Guardrails vs. Probabilistic AI
LLMs are probabilistic. If you instruct an AI via system prompt to *"Never hang up while the user is on hold"*, it will obey 90% of the time. But if background noise occurs, the AI might hallucinate a goodbye and hang up. 
This project implements a `CallPolicyEngine` (Deterministic Guardrails). When the AI attempts to use a tool (like `hangup`), the engine intercepts the request and verifies the hardcoded system state. If `self.on_hold == True`, the code explicitly denies the AI's request. **Business rules must be hardcoded; they cannot be left purely to neural network probability.**

### 3. The Fragmentation of Streaming APIs
Real-time streaming APIs deliver text in fragmented chunks. The AI might send `"Good"`, and 500ms later send `"bye"`. If the code evaluated chunks individually to detect call-termination triggers, it would fail. The script employs an accumulator buffer (`_asst_chunk_buffer`) with a 2.5-second sliding window to properly reconstruct and evaluate semantic intent before triggering physical hardware actions.

### 4. Hardware Actuation & Hallucination Curation
Gemini Live cannot physically hang up a Linux modem; the Python code must translate semantic AI intent into `oFono` D-Bus signals. Furthermore, live audio over Bluetooth HFP is prone to severe static, causing Gemini to hallucinate bizarre foreign words. The integration of local `whisper.cpp` acts as an asynchronous post-processor to heal the database logs, ensuring the resulting transcripts are clean and usable for future memory injection.

In summary, this codebase bridges the gap between a "disembodied AI brain" and the physical realities of Bluetooth radio, acoustic noise, and strict telephony protocols.

---

## 📝 License
This project is licensed under the GPL v3 License. See the `LICENSE` file for details.
