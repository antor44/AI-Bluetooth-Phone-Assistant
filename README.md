# 📞 AI Bluetooth Phone Assistant & Switchboard

![Version: 2.9](https://img.shields.io/badge/Version-2.9-brightgreen.svg)
![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Linux Only](https://img.shields.io/badge/Platform-Linux-orange.svg)

An advanced, real-time AI telephone secretary designed to handle your mobile calls via Bluetooth. Utilizing **Google Gemini 3.8 Live** for conversational AI and optional **whisper.cpp** for hybrid transcription, this system acts as a fully autonomous switchboard: it answers calls, filters SPAM, takes messages in a dedicated inbox, maintains configurable context-aware memory with AI summaries for repeat callers, and provides a sleek Web GUI to manage your communications and server state.

> ⚠️ **EXPERIMENTAL SOFTWARE — USE AT YOUR OWN RISK**
> This is an experimental project distributed as-is, without warranty. It may contain bugs, missed-call scenarios, transcription errors, or other untested edge cases. Several advanced features — specifically **real-time SPAM database checking, Whitelist/Blacklist/Wildcard filtering, and Contact-Specific Custom Instructions** — are implemented but have not been thoroughly verified in real-world conditions.
>
> The assistant depends on **Google's Gemini 3.8 Live service**, which is outside the author's control. Although uncommon, the connection or the model itself may occasionally fail or slow down to unusable levels. These problems originate on Google's side and are not caused by this software. In the author's experience, a paid API key or account makes no noticeable difference compared with the free tier.
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

Curiously, the flagship Duplex demos were about **outgoing** calls: the AI phoned restaurants and hair salons by itself to book appointments on behalf of the user. In the United States, outgoing AI calls are subject to strict consent rules (the FCC treats AI-generated voices as artificial voices under the TCPA), and in the European Union, the UK and many other countries automated outbound calls generally require the prior consent of the person called. For this reason, this application only supports **incoming** calls, in order to comply with the legislation approved in most countries.

To overcome these commercial barriers (but not, of course, the legal ones), I have developed this Python application that operates as an independent orchestrator from any PC or supported Linux SBC (single-board computer). By connecting to the mobile phone via Bluetooth, the system acts as a supercharged version of Google's solutions that allows answering calls (only answering, to avoid most legal restrictions for normal users) without suffering geographical blocks or depending on specific mobile hardware. This architecture offers complete and unrestricted control to manage bidirectional audio, transcribe conversations, and generate real-time responses using AI. Furthermore, it provides full control over the call history, and at any moment, the user can interrupt the AI to take manual control of the call, among many other improvements that will be added in the future.

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
  <br><b>🔌 An expansion board with two extra USB ports and an audio output is also sold for this SBC. However, the onboard audio output is disabled as well (see SBC Audio Note below), so to monitor call audio locally it is recommended to use a USB sound card or USB speakers.</b>
</div>
<br>
Author: Antonio R. | Version: 2.9 | License: GPL 3.0

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
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy3.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy2.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy4.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy1.jpg)
![GUI Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/browser_guy5.jpg)

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
*   **Localization:** You can easily add new languages. Simply duplicate the `en-US` or `es-ES` folder inside the `languages` directory and translate the values in the `.json` files (`gui.json` and `assistant.json`). **Do not change the variable keys/names**, only translate the text values. For a new language also set `home_country_code` and `home_national_length` in `spam.json`, and adapt the voice and accent profile at the top of the prompt, `speech_language_code`, `voice_names`, and the word lists (`cut_words`, `goodbye_veto_words`, `goodbye_meta_words`, `assistant_placeholder_phrases`). Always copy **all** the keys from the English or Spanish files: missing keys can cause incomplete texts or unexpected behavior.

### Recommended Operating Profile
For a balanced default experience, the recommended profile is:
*   Concise and neutral tone
*   Inbound-call focused
*   Limited to call handling, message capture, hold management, and basic classification
*   Resistant to oversharing personal or schedule details

A more expressive or conversational personality sounds nicer, but may reduce reliability for structural commands during real calls.

For the audio, echo and voice-detection settings (answer speed, hold mode, transcript quality) see the [Audio, Echo & Voice Detection Tuning Guide](#-audio-echo--voice-detection-tuning-guide).

---

## 🔊 Audio, Echo & Voice Detection Tuning Guide

The secretary can only react to what she hears. The **Audio, Echo & VAD Tuning** block of the Web GUI controls how the caller's voice is filtered, amplified and handed to Gemini Live, and how Gemini decides when the caller starts and stops speaking. These settings therefore affect:

* **How fast she answers:** how long she waits before deciding that the caller has finished.
* **Interruptions:** whether noise makes her stop or answer for nothing, and whether she misses a quiet caller.
* **Hold mode:** it is activated, kept and ended by the *words* the caller says (for example "one moment"), so a poor transcript can mean a missed hold or a false wake-up.
* **Transcript quality**, and with it everything decided from the text: hold, goodbye detection, priority keywords, message capture and the text saved in the call history.

Settings are read when a call starts, so a change applies from the **next call**. At the start of each call the terminal prints the gain and base gate in use (`[Mic] Active on node … (Gain: …, Base Gate: …)`).

### How the sound travels
`Caller → mobile network → caller's phone → your phone → Bluetooth → noise gate → gain → echo / greeting protection → Gemini (voice detection + transcription) → answer`

Every step can lose or distort something, and **no setting can restore what never arrived**. The settings below only tune the part on the switchboard and the voice detection of Gemini.

### The settings

| Setting (Web GUI label) | Default | Range | In one sentence |
| :--- | :--- | :--- | :--- |
| **Enable Software Echo Suppression (Half-Duplex)** | Off | On / Off | Mutes the caller's audio while the secretary is speaking. |
| **Protect Initial Greeting from Early Line Interruptions** | On | On / Off | Mutes the caller's audio while the greeting is played. |
| **Caller Mic Gain (x)** | 1.5 | 0.5 – 5.0 | Makes the caller's voice louder or quieter. |
| **Base Noise Gate (RMS)** | 50 | 0 – 100 | Level below which sound is treated as silence. |
| **VAD Start Sensitivity** | LOW | HIGH / LOW | How easily Gemini decides that the caller started speaking. |
| **VAD Prefix Padding (ms)** | 500 | 50 – 1000 | How much speech must be heard before Gemini accepts that the caller started speaking. |
| **VAD End Sensitivity** | HIGH | HIGH / LOW | How easily Gemini decides that the caller stopped speaking. |
| **VAD Silence Duration (ms)** | 700 | 200 – 2000 | How long a silence must last before Gemini decides that the caller finished. |

*VAD = Voice Activity Detection: the part of Gemini Live that decides when somebody is speaking.*

#### Software Echo Suppression (Half-Duplex)
While the secretary is speaking, whatever comes from the caller's line is replaced by silence before Gemini hears it. **Turn it on** if the secretary hears her own voice coming back (echo from a speakerphone, a car kit or a poor line) and gets confused, repeats herself or interrupts herself. **Leave it off** if there is no echo: with it on, the caller **cannot interrupt** her while she talks, and what the caller says during that time is not heard by Gemini and not transcribed. The call recording still keeps it.

#### Protect Initial Greeting
During the greeting (at most about 8 seconds, or until it has finished playing) the caller's audio is muted, so clicks, line noise or a quick "hello?" when the call is answered do not cut the greeting. **Keep it on** for a clean, complete greeting. **Turn it off** if you prefer that she can be interrupted from the very first second; the price is that noise at pick-up can cut the greeting, and with it on, words the caller says at once over the greeting are not heard.

#### Caller Mic Gain
Multiplies the volume of the caller's voice before Gemini hears it. It also changes the volume of the call recording. **Too low:** quiet callers are missed, voice detection fails and transcripts get worse. **Too high:** loud parts distort (clipping) and background noise is amplified, which causes false detections and garbled text. Change it in steps of 0.5. The noise gate below looks at the original level, **before** the gain, so the gain does not change what the gate lets through. Many phones already boost the voice automatically, so avoid stacking a high gain on top of that.

#### Base Noise Gate
Anything quieter than the gate is replaced by silence before Gemini hears it. The gate **adapts by itself**: the switchboard keeps measuring the background noise of the line and raises the gate when the line is noisy (up to about 65), but never below the base value you set. If you set the base above 65, your value is used as it is. While a call is **on hold** the gate is raised by 15 more (up to 80). The gate works on a very low loudness scale (even 80 is about 52 dB below the maximum level), so it removes **line hiss and very quiet noise**; a TV playing at normal volume next to the caller is usually well above it and **cannot be filtered out with this setting** (see [TV or voices behind the caller](#tv-or-voices-behind-the-caller)). **Lower it** (steps of 5) if quiet callers are cut or words are missing at the start or end. **Raise it** if hiss, hum or distant voices reach Gemini and you see nonsense or `[Noise Filtered]` in the transcript. The gate only affects what Gemini hears: the call recording keeps the full caller audio.

#### VAD Start Sensitivity
**LOW (default):** Gemini needs clearer speech to decide that somebody started talking: fewer false triggers from clicks, coughs or noise, but a soft-spoken caller may be noticed late. **HIGH:** quieter and shorter sounds count as speech: faster reaction, but noise can interrupt the secretary or start an empty turn.

#### VAD Prefix Padding
Despite its name, this is the **minimum amount of speech Gemini must hear before it accepts that the caller started talking** (it is not a recording buffer). **Lower values** (50–200 ms): very short words such as "yes", "no" or "hello" are noticed, but short noises also count. **Higher values** (500 ms or more): short noises are ignored, but a very short word may not be recognised and an interruption is noticed a little later.

#### VAD End Sensitivity and VAD Silence Duration
These two work together and are the main controls of the **answer speed**. *End Sensitivity* says how readily a pause counts as the end of the sentence, and *Silence Duration* says how long that pause must last. Each extra 100 ms of silence duration is 100 ms added to every answer, on top of the time Gemini and the Bluetooth link need.
* **Faster answers:** End Sensitivity HIGH and a short silence (200–500 ms). Risk: she answers while the caller is only taking a breath or thinking, and cuts into names, phone numbers or spelled words.
* **More patient:** End Sensitivity LOW and a long silence (1000–2000 ms). Better for slow speakers, older callers and for leaving messages, but answers feel slower and there are awkward silences.

### Hold mode and transcription
The secretary goes on hold when the words the caller says match the **hold phrases** of the language files ("one moment", "wait a second", …). While on hold she stays silent and ignores everything that is not clearly addressed to her: to resume, what she hears must contain a **return phrase** of the language files, or the assistant's name or the owner's name. Anything else is logged as `Active Hold Ignored background noise / TV`. A call can stay on hold for a limited time (15 minutes in total), and the noise gate is higher during hold.

This is why audio quality matters so much for hold:
* If the noise garbles "one moment", **hold is not activated** and she keeps talking or asks if the caller is still there.
* Background voices (a TV, for example) are transcribed during hold too; if their words happen to contain a return phrase, they can **wake her up**, and their noise can make her **react late** to the real caller.
* If the gate is too high or the gain too low, the caller who comes back with a soft voice is **not heard**; she keeps waiting, and the wait limit may end the call.

**What the optional transcription modes (Whisper.cpp / Gemini Flash 3) change:** none of them changes the live decisions. Hold, return from hold, goodbye detection and priority keywords always read Gemini's **live** transcription, because they have to react while the caller is still talking.
* **Real-time (Whisper.cpp):** after each caller turn, Whisper transcribes that turn and its text is added next to Gemini's in the transcript (`Gemini text | [Whisper]: …`). The analysis made at the end of the call (tag, spam score, summary, caller name) reads this transcript with both versions. In this mode Whisper only receives the audio that passed the noise gate and the echo suppression, so it cannot recover what was muted.
* **Whisper.cpp at end of call** and **Gemini Flash 3 at end of call:** once the call is over, the whole recording of the caller (which is not affected by the gate or the echo suppression) is transcribed again and aligned with the live text. The result replaces the **saved** transcript. The tag, spam score and summary were already decided before this step from the live transcript and are not recalculated.

### TV or voices behind the caller
This is the hardest case, because the secretary cannot tell a TV from a person.
* The **Base Noise Gate does not help much here**: it removes line hiss and very quiet noise, not a TV at normal volume.
* Gemini hears the TV as speech. While it keeps talking there is **no silence**, so Gemini needs longer to decide that a turn has ended, and the live transcript mixes the TV with the caller's words. This is why the reaction after a hold can be late and the transcription poor.
* During hold, text that does not contain a return phrase is ignored (`Active Hold Ignored background noise / TV` in the terminal log). So what decides the return is whether the **return phrase is correctly transcribed** among the noise.

What can help:
1. **Tune the return phrases.** In the `assistant.json` file of your language (`languages/<language>/assistant.json`), inside the `"words"` block, the `"return_triggers"` list holds the phrases that bring her back from hold (the assistant's name and the owner's name also count). The matching is **exact**: single words must match as whole words and longer phrases as text, with no fuzzy or phonetic matching. Add the **short phrases your callers really say** and **the way the transcription actually writes them**; the `Active Hold Ignored background noise / TV '…'` lines of the terminal log show what was heard when the caller came back. Only add entries to the list and keep the keys unchanged. It applies from the next call.
2. **Do not raise *VAD Prefix Padding*** for this problem: return phrases are short ("hello?") and a high value can make her miss them.
3. **For faster reactions whenever there are pauses:** *End Sensitivity* HIGH and a *Silence Duration* of 500–600 ms. If the TV never stops, this cannot help.
4. **The caller's side:** a lower TV volume, moving to another room, or a phone with noise suppression / voice isolation for calls makes the biggest difference of all.

### What else changes the result (not adjustable here)
* **The caller's surroundings:** street, car, wind, a TV or several people talking, speakerphone use. These add noise that no gate can separate from the voice.
* **The mobile network and the line:** weak coverage and heavy compression produce distorted or missing syllables. A call from a quiet place with good signal is transcribed far better than any setting can achieve.
* **The phones, on both ends:** many phones apply automatic gain control, noise reduction with several microphones, or AI voice isolation. They can cut the soft ends of words, make background voices appear and disappear, or make the volume pump up and down. If your phone has options such as noise suppression or voice clarity for calls, test with them on and off. The right values for one phone may need a new adjustment after switching phones or after a phone update.
* **The Bluetooth link:** distance, interference and the narrow call-audio profile used for calls; dropouts mean missing syllables (see [Complex Bluetooth Scenarios](#-complex-bluetooth-scenarios)).
* **Language and accent:** accuracy changes with the language, the accent and uncommon names.

### Quick troubleshooting

| What you notice | What to try (one change at a time) |
| :--- | :--- |
| She answers too slowly | Lower *VAD Silence Duration* by 100 ms; keep *End Sensitivity* HIGH. |
| She answers while the caller is still thinking or dictating numbers | Raise *VAD Silence Duration* to 1000–1500 ms and set *End Sensitivity* to LOW. |
| She misses quiet callers or their first words | Raise *Caller Mic Gain* by 0.5 or lower the *Base Noise Gate* by 5; try *Start Sensitivity* HIGH or a lower *Prefix Padding*. |
| She reacts to line hiss or clicks; nonsense or `[Noise Filtered]` in the transcript | Raise the *Base Noise Gate* by 5; keep *Start Sensitivity* LOW and *Prefix Padding* at 500 or more; lower the gain if the voice sounds distorted. For a TV or voices behind the caller see [below](#tv-or-voices-behind-the-caller). |
| She hears her own voice and repeats or interrupts herself | Turn on *Software Echo Suppression*. |
| She asks "are you there?" while the caller speaks softly | The gate is too high, the gain too low, or echo suppression is muting the caller; adjust them in that order. |
| The greeting is cut when the call is answered | Keep *Protect Initial Greeting* on. |
| The first words of a caller who speaks at once are lost | Turn *Protect Initial Greeting* off. |
| Hold is not activated when the caller says "one moment" | Check the live transcript first. Improve the audio (gain, gate) or lower *Prefix Padding* so a short phrase is not lost. |
| Hold ends by itself, or she reacts late when the caller returns, with a TV or voices behind the caller | See [TV or voices behind the caller](#tv-or-voices-behind-the-caller). |

**Tips for tuning:** change **one** setting at a time and in small steps; test with real calls in the conditions you usually have; compare the live transcript in the Web GUI and the terminal log. The defaults are a reasonable starting point for a clean line. Every setting is a compromise (fast vs. patient, sensitive vs. noise-proof), and what works best depends on your phone and on your usual callers. If a model update on Gemini's side changes the behavior, review these values again.

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
The installer always installs the MP3 encoder `lameenc` for call recordings (if it cannot be installed, recordings are saved as WAV instead). It must be run from the installation directory (`~/AI-Bluetooth-Phone-Assistant` by default); it creates and manages the Python virtual environment (`venv`) by itself, so you do not need to activate it.

The switchboard runs its own private Tor instance, so the system-wide `tor` service installed by `--with-tor` is not needed. To disable it: `sudo systemctl disable --now tor`.

After the installer finishes, **reboot your machine once** (`sudo reboot`) so user groups, D-Bus permissions, and Bluetooth kernel rules take effect.

### Updating an Existing Installation
Run these commands on the PC, or on the Orange Pi / SBC over SSH (adjust the path if you cloned the project elsewhere):
```bash
cd ~/AI-Bluetooth-Phone-Assistant
git pull
./install_system_deps.sh
```
Add `--with-tor` and/or `--with-whisper` if you want those optional components (see above). Users coming from a version older than v2.4 also get the `lameenc` MP3 encoder this way. Existing databases are migrated automatically.

* **Local changes:** if you modified any project file (for example `languages/*`), back it up first, because `git pull` may refuse to overwrite it.
* **Custom languages:** copy the new keys from the English or Spanish files and translate them (see *Localization*).
* **Restart:** if you launch it manually, close it and run `./my_gui.sh` again (it can be started from any directory and activates the `venv` automatically). If you use the systemd service: `systemctl --user restart ai-switchboard.service`.

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

#### 🔒 When is the Web GUI exposed to the local network?
The launcher decides who can reach the Web GUI (port 8501) like this:

| How you launch it | Desktop session detected? | Web GUI reachable from |
| :--- | :--- | :--- |
| `./my_gui.sh` | Yes | Only the device itself (`localhost`) |
| `./my_gui.sh` | **No** (for example, over plain SSH) | **Your whole local network** (`0.0.0.0`) |
| `./my_gui.sh --lan` (or `--headless`) | Any | Your whole local network (`0.0.0.0`) |
| `./my_gui.sh --local` | Any | Only the device itself (`localhost`) |

A desktop session is detected when the `DISPLAY` or `WAYLAND_DISPLAY` environment variable has a value. These variables are normally empty when you log in over SSH, so **launching `./my_gui.sh` from an SSH session without any argument opens the Web GUI to your local network automatically** (a connection made with `ssh -X` or `ssh -Y` sets `DISPLAY` and counts as a desktop session).

Because the Web GUI has no login (see the security warning below), you may not want this automatic behavior. Add `--local` to turn it off:

```bash
./my_gui.sh --local
```

With `--local` the Web GUI listens only on `127.0.0.1`, even when no desktop is detected, and nobody else on your network can open it. To use it from another computer, create an SSH tunnel from that computer and then open `http://localhost:8501` in its browser:

```bash
ssh -L 8501:localhost:8501 <user>@<YOUR_DEVICE_IP>
```

`--local` cannot be combined with `--lan` or `--headless`. It only affects the Web GUI: the assistant daemon starts as usual (in a new terminal window if there is a desktop, in the background otherwise).

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

> ⚠️ **Security warning:** the Web GUI has **no login or password** and includes sensitive features (call recordings, transcripts, messages, API settings and remote server reboot). Only use it on networks you trust, and **never expose port 8501 to the Internet** (no router port forwarding). See [Security & Network Exposure](#-security--network-exposure) for a comparison of the access methods and a router checklist. For remote access from outside your LAN, see the next section.

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

1. Install the two packages Tor access needs: run `./install_system_deps.sh --with-tor`, or `sudo apt install tor openssl`. The switchboard uses its own private Tor instance, so you can disable the system-wide service with `sudo systemctl disable --now tor`.
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

> 🔒 This service starts the Web GUI with `--lan`, so it is reachable from your local network. If you prefer to keep it reachable only from the device itself, replace `--lan` with `--local` in the `ExecStart` line (and reach it through an SSH tunnel, see *Manual Launch*).

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

## 🔐 Security & Network Exposure

The Web GUI (port 8501) has **no login or password**. Whoever can open it can listen to call recordings, read transcripts and messages, change the settings (including the API settings) and reboot the device. So its security depends on **who can reach that port**, and that is decided by how you launch it and how you connect to it.

> ⚠️ **Warnings**
> * **Never expose port 8501 to the Internet.** No router port forwarding, no `tailscale funnel`, no DMZ / "exposed host".
> * **LAN mode is plain HTTP.** Nothing is encrypted on your Wi-Fi, and anyone connected to the same network (guests, smart-home gadgets, an infected computer) can open the panel without a password.
> * **Check how it is launched.** The systemd service of this README starts the Web GUI with `--lan`, and `./my_gui.sh` without arguments from a plain SSH session also opens it to your whole network (see [the table above](#-when-is-the-web-gui-exposed-to-the-local-network)). Use `--local` if you do not need that.
> * **Do not forward the SSH port to the Internet** unless SSH itself is hardened (key login, no weak passwords). Otherwise the weak point moves from the panel to SSH.

### How safe is each way of access?

| Way of access | Who can reach the panel | Security for a normal user | Notes |
| :--- | :--- | :--- | :--- |
| **Local only** (`./my_gui.sh --local`, or the default on a desktop session) | Only the device itself | 🟢 **Very high** | Nothing is published on the network. |
| **SSH tunnel** (`--local` + `ssh -L 8501:localhost:8501 <user>@<YOUR_DEVICE_IP>`) | Only whoever can log in to the device by SSH | 🟢 **Very high** | Encrypted. It is as strong as your SSH login: use keys or a strong password. |
| **Private VPN** (Tailscale / WireGuard, see [Option A](#option-a--private-vpn-with-tailscale)) | Only the devices signed in to your VPN | 🟢 **Very high** | Encrypted and works from anywhere. Protect the VPN account (two-factor login if available). |
| **Built-in Tor** (see [Option B](#option-b--built-in-tor-private-onion-service-no-third-parties)) | Only devices that have the onion address **and** the access key | 🟢 **Very high** | Encrypted end to end, no open ports and no accounts: without the key nobody can even see that the service exists. Keep the access key and the pairing link secret: anyone who can open the panel can see them, so prefer `--local` over LAN mode. Slower than a VPN. It also works with `--local`: Tor reaches the panel through `127.0.0.1`, so the panel does not need to be opened to your network. |
| **LAN mode** (`--lan`, systemd service) | Every device on your local network | 🟡 **Lower: depends on your network** | No password and no encryption. Reasonable on a home network you trust, but only if your router does not expose the device (see the checklist below). |
| **LAN mode + router exposing the device** (port forwarding, UPnP, DMZ / exposed host, open IPv6) | **Anyone on the Internet** | 🔴 **Unsafe** | Your recordings, messages and settings would be public. Never do this. |

If you do not need to open the panel from other devices at home, the safest simple setup is `--local` plus an SSH tunnel, a private VPN or the built-in Tor for remote access.

### Router checklist (important in LAN mode)
Opening the panel to your local network is not dangerous by itself: `0.0.0.0` only means "listen on all local interfaces" and does not publish anything to the Internet. It becomes dangerous when the router lets Internet traffic reach the device. Check that:

* There is **no port forwarding / virtual server / NAT rule** from the router to the device's IP address (for port 8501 or any other).
* **UPnP is turned off**, so no program on your network can open ports on the router by itself.
* There is **no DMZ / "exposed host" / "default server"** pointing to the device: it sends *all* incoming traffic to that device.
* If your router gives your devices **public IPv6 addresses**, its IPv6 firewall blocks unsolicited incoming connections (most do by default, but not all).

**Quick test:** with a phone on mobile data (Wi-Fi off), try to open `http://<your public IP address>:8501`. It must **not** load. Your public IP address is shown by any "what is my IP" website. If your Internet provider uses CGNAT (common with mobile and fibre ISPs), incoming connections from the Internet are not possible anyway.

### Optional: firewall on the device (LAN mode)
To let only your own network reach the panel, even if something changes in the router, add a UFW rule. Run this **on the switchboard device** (PC or Orange Pi), replacing `192.168.1.0/24` with your own network (`ip route` shows it):

```bash
sudo ufw allow from 192.168.1.0/24 to any port 22 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 8501 proto tcp
sudo ufw deny 8501/tcp
sudo ufw enable
```

* The first line keeps your SSH access: **without it, enabling UFW can lock you out of an SSH session.**
* The order matters: UFW applies the first rule that matches, so the "allow from your network" rule must come before the `deny`.
* If you use Tailscale, also run `sudo ufw allow in on tailscale0 to any port 8501 proto tcp` **before** the `deny` line, or the VPN devices will be blocked too.

### Optional: a password inside your network
The panel has no login of its own. If you want a password even on your LAN, put a reverse proxy with *Basic Authentication* (for example Caddy or nginx) in front of it and start the panel with `--local`, so the proxy is the only way in. The browser asks for the user and password once and remembers them while the browser stays open. Keep in mind that Basic Authentication over plain HTTP sends the password without encryption, so it only keeps casual visitors out: for real protection use an SSH tunnel or a VPN.

---

## 📱 Android App (AI Switchboard)

A small, free Android app that is the easiest way to reach your switchboard from **anywhere**: it opens the Web GUI through the Tor network built into the app and tells you when a caller leaves a message or a call has finished.

[**⬇️ Download the APK**](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/android/AI-Switchboard.apk) &nbsp;·&nbsp; Android 7.0 or newer &nbsp;·&nbsp; [Build it yourself](android/ANDROID_BUILD.md)

### Verify the download (optional)
The official APK (`android/AI-Switchboard.apk`, version 1.1.2) has this SHA-256: `da2779d5d6421336a1ef2e75288ba29ac39efdf9349669bb1f4cb361efc3ff35`. It is signed with a certificate (`CN=Antonio R.`) whose SHA-256 fingerprint is `d5a4c1db9733d27ade3c4054d771c049a716b86dbde1d2bc603f96297aa9fc42`; every future official version will carry the same certificate. Compare with `sha256sum` and `apksigner verify --print-certs`.

### Why it is worth installing
* 🔒 **Private by design.** The app talks **only to your own switchboard**, through the anonymous Tor network. It never contacts public servers or third-party services of its own: **no analytics, no ads, no trackers, no accounts, no Google or Firebase push service.** The connection is end-to-end encrypted and protected by an access key, and the app refuses to load any address other than your switchboard's.
* 🗄️ **It keeps almost nothing.** The only thing it stores is your pairing key, encrypted with the Android Keystore and excluded from Android backups, plus its own settings. Calls, recordings and messages stay on your switchboard; the panel you see is just a window onto it (like any browser, the phone may cache the pages it shows).
* 🔔 **Notifications without Google.** Because Tor is private, the app cannot receive instant pushes from a server; it *asks* your switchboard instead, and you choose how often in **Settings**: **Power saving** (about every 15 minutes, Android's minimum for background work; lowest battery use, no permanent notification), **Balanced** (every 2, 5 or 10 minutes) or **Instant** (keeps one connection open for near-immediate alerts; highest battery use). Balanced and Instant show a permanent notification, because Android requires it for background services. You can also set a **schedule** with one mode for the day and another for the night (including *Off*). Android can delay the checks in Doze or battery saver. Instant mode works best with the latest switchboard version: with an older one the app notices that the switchboard does not hold requests open and checks about every 15 seconds instead. You are notified of **new caller messages** and **finished calls with their AI summary**. SPAM and blocked calls are not notified, and a call that left a message produces a single notification. On the lock screen only a generic text is shown; the content appears once you unlock. The first time you switch notifications on, old items are not sent.
* 🆓 **Free and open source (GPL v3).** The *About* button shows the version, the license notice and the licenses of the components it uses.

---

## 📸 Screenshots

![Android Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/mobile_app1.jpg)
![Android Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/mobile_app2.jpg)
![Android Screenshot](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/mobile_app3.jpg)

---

### Installation
1. On your phone, open the [APK link](https://github.com/antor44/AI-Bluetooth-Phone-Assistant/raw/main/android/AI-Switchboard.apk) (or download it on a PC and copy it over) and open the downloaded file.
2. Android will ask you to allow installing apps from this source (**"Install unknown apps"** for your browser or file manager). Allow it **only for that app**, then go back and tap **Install**. The app is not distributed through Google Play, so Google Play Protect may warn about an unknown developer: tap *More details → Install anyway*.
3. Open the app. When it asks for permission to show **notifications**, accept (Android 13+).
4. On the switchboard, enable **Remote access (Tor)** and press **Show pairing code** (see [Option B](#option-b--built-in-tor-private-onion-service-no-third-parties)).
5. In the app, **scan the QR code**, or paste the pairing text. The GUI shows the onion address and the access key separately: paste the onion address in the first box and the key in the second, or paste the full pairing link in the first box only.
6. Wait while it says *Connecting through Tor…* (the first connection can take 1–3 minutes; if it seems stuck, press **Refresh**). Then your Web GUI appears. Switch **Notifications** on if you want alerts.

### Using the app
* **↻ Refresh:** reloads the page. If the page is not showing, or the connection is stuck, it cancels the attempt and restarts the Tor connection from scratch.
* **⚙️ Settings:** notifications, how often to check, the day/night schedule, the *Allow background activity* button, *About* and *Unpair*.
* **⏻ Close:** stops the background checks, the permanent notification and Tor, and closes the app completely. Your pairing and settings are kept: when you open the app again, it resumes the checks as you had configured them. After a restart of the phone the background checks also start again by themselves.
* **Unpair:** forgets the pairing, switches the notifications off and closes the app.

### 🔍 About the QR scanner (optional)
Scanning the QR code is optional and uses Google's *code scanner*, a component of Google Play services. Images are processed on your device and the app only receives the resulting text. It requires Google Play services, which may download the scanner module the first time you use it. If you prefer not to use it, simply paste the onion address and key manually: the rest of the app never talks to Google.

### Troubleshooting
| Problem | What to do |
|---|---|
| "App not installed" / the file will not open | Allow *Install unknown apps* for the app you used to open the APK. Android 7–8 has a single "Unknown sources" switch in Security settings. |
| Play Protect warns about an unknown developer | Expected for apps outside Google Play: *More details → Install anyway*. You can compare the file's SHA-256 with the one published in the release. |
| Stuck on *Connecting through Tor…* | The first connection takes 1–3 minutes. If it seems stuck, press **Refresh** (↻) or **Retry**: both cancel the attempt and restart Tor from scratch. Check that the switchboard is on, has Internet, and that its Tor panel says **🟢 Active**. Some networks block Tor: try another Wi-Fi or mobile data. |
| *Cannot reach the switchboard* | The switchboard is off, offline, or remote access is disabled. |
| *The WebView … does not support the required proxy feature* | Update **Android System WebView** (and Chrome) in Google Play, or on devices without Google Play update the WebView component by the vendor's means. |
| *Invalid pairing data* | Paste the onion address (56 characters + `.onion`) and the key (52 characters) in the right boxes, or the full `aiphone://pair?…` link. Do not add spaces or quotes. |
| No notifications | Allow notifications for the app in Android settings; set the app's battery usage to **Unrestricted / Not optimised**; on Xiaomi, Huawei, Oppo, Samsung and similar, allow *autostart* / *background activity* and lock the app in recent apps. In *Power saving* mode checks happen about every 15 minutes, possibly later in Doze or battery saver; choose *Balanced* or *Instant* in the app's Settings for faster alerts. |
| No permanent notification in *Power saving* mode | Intended. Only *Balanced* and *Instant* use a background service, and Android requires a permanent notification for it. *Power saving* uses Android's own scheduler instead, which is why it uses less battery. |
| I want to stop the app completely | Use the **⏻ Close** button on the main screen. Pairing and settings are kept. |
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
