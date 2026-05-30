# 📞 AI Bluetooth Phone Assistant & Switchboard

![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini Live** for conversational AI and **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages, sets context-aware memory for repeat callers, and provides a sleek Web GUI to manage your communications.

> ⚠️ **DISCLAIMER & PRELIMINARY VERSION WARNING**
> This is a **preliminary, experimental version**. I am not responsible for any errors, missed calls, or damages resulting from its use. There are many unhandled edge cases, potential API timeouts, and a remote but possible risk of privacy leaks (see the Privacy section below). Use it at your own risk.

> ⚖️ **LEGAL WARNING REGARDING CALL RECORDING**
> Laws regarding the recording of phone conversations and AI usage vary heavily by country and can be highly controversial. For example, in countries like Spain—despite being a place unfortunately plagued by spammers, scammers, corruption and mafias of all kinds—privacy regulations are extremely strict. If you use this for a business or company, you **must** configure the AI's initial greeting to explicitly warn the caller that the call is being recorded and processed by an AI. Failure to do so can result in massive legal fines. It is your sole responsibility to comply with your local telecommunications and privacy laws.

---

## 📸 Screenshots

### Terminal View (Live Call Processing)
*Real-time processing showing User audio chunks, D-Bus interaction, Gemini AI responses, and Whisper.cpp noise filtering.*
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant1.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant2.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant3.jpg)
![Terminal Output Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/assistant4.jpg)

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
2.  **Two Phones Connected:** Linux (oFono) detects both phones as separate modems. If Phone B rings, the script isolates its D-Bus path and PipeWire nodes (`bluez_input.MAC_PHONE_B`) to answer it. *(Current limitation: If both ring at the exact same millisecond, the global instance variable might be overwritten. It's best to handle calls sequentially).*

---

## 🧠 Tuning & Personality

*   **Language & Accent:** I am not a native English speaker. The prompts and default interactions were originally heavily tuned for **Spanish** and optimized for a personal assistant role handling specific edge cases.
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

## 🔒 Deep Dive: Call Memory & Privacy Risks

The application features a "Call Memory" system that injects the history of previous conversations into the prompt of a returning caller. You must understand how this works and its privacy implications.

**How it works under the hood (lines ~1417):**
```python
last_rec = conn.execute(
    "SELECT transcript, date FROM calls WHERE number=? ORDER BY id DESC LIMIT 1",
    (self.caller_number,)
).fetchone()
```
The query uses `WHERE number=?` filtering strictly by the caller's phone number. It never mixes numbers.
If the last call is completely finished (not "IN PROGRESS"), the system injects the **entire past transcript** into the Gemini Live system prompt.

**Privacy Risks & Unintended Behaviors:**
Even though the JSON prompt includes strict rules like: *"Today's call is new, do not assume they call for the same reason"* and *"Only refer to historical context if explicitly mentioned"*, Gemini does not always respect this nuance.

*   **Scenario A (Same number, repeat caller):** There is no leak to third parties. However, if the caller gave sensitive medical data in Call 1, the AI might spontaneously bring it up in Call 2 without the user evoking it, violating the "clean slate" rule and creating an awkward user experience.
*   **Scenario B (Shared numbers / Fake Caller ID):** If a company number (PBX) is used, and *Person X* calls, followed later by *Person Y* from the same external number, **Person Y's AI context will contain the full transcript of Person X**. This is a real privacy leak, as the AI has access to someone else's business or personal data.

---

## 📝 License
This project is licensed under the GPL v3 License. See the `LICENSE` file for details.
