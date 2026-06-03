#!/usr/bin/env python3
"""
AI Switchboard Assistant - Intelligent phone handler utilizing Gemini Live and Bluetooth HFP.
The application detects incoming calls via D-Bus/oFono, manages audio routing through PipeWire,
transcribes caller intent, applies dynamic security policies, and interacts in real-time.

Author: Antonio R.
Version: 1.2
License: GPL 3.0

Copyright (c) 2026 Antonio R.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import sys
import json
import asyncio
import re
import sqlite3
import time
import wave
import struct
import math
import subprocess
import shutil
import aiohttp
import datetime
import warnings
import logging
import threading
import queue
import uuid
import contextlib
import io
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from collections import Counter
from google import genai
from google.genai import types

# =============================================================================
# TERMINAL STYLE AND EMOJI CONFIGURATION
# =============================================================================
SUPPORTS_COLOR = sys.stdout.isatty()

lang_env = (os.environ.get("LANG") or "").lower()
lc_all_env = (os.environ.get("LC_ALL") or "").lower()
term_env = (os.environ.get("TERM") or "").lower()
has_utf8 = "utf-8" in lang_env or "utf-8" in lc_all_env or "utf8" in lang_env or "utf8" in lc_all_env
is_basic_term = term_env in ["xterm", "linux", "vt100"]
USE_EMOJI = has_utf8 and not is_basic_term

if SUPPORTS_COLOR:
    _R        = "\033[0m"
    _C_SERVER = "\033[96m"
    _C_CONN   = "\033[94m"
    _C_AUDIO  = "\033[92m"
    _C_WARN   = "\033[93m"
    _C_ERR    = "\033[91m"
    _C_MUTED  = "\033[90m"
else:
    _R = _C_SERVER = _C_CONN = _C_AUDIO = _C_WARN = _C_ERR = _C_MUTED = ""

ICON_SERVER   = "🚀 " if USE_EMOJI else "[SERVER] "
ICON_CONN     = "⏳ " if USE_EMOJI else "[SYSTEM] "
ICON_AUDIO    = "🎙  " if USE_EMOJI else "[AUDIO]  "
ICON_WARN     = "⚠  " if USE_EMOJI else "[ALERT]  "
ICON_ERR      = "✖  " if USE_EMOJI else "[ERROR]  "
ICON_OK       = "✔  " if USE_EMOJI else "[OK]     "
ICON_INFO     = "ℹ️  " if USE_EMOJI else "[SYSTEM] "
ICON_USER_STR = ""
ICON_ASST     = ""

warnings.filterwarnings("ignore")
logging.getLogger("google.genai").setLevel(logging.ERROR)

os.environ["DBUS_SYSTEM_BUS_ADDRESS"] = "unix:path=/var/run/dbus/system_bus_socket"

# =============================================================================
# HARDWARE & PATH CONFIGURATION
# =============================================================================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "switchboard.db")
LANG_DIR    = os.path.join(BASE_DIR, "languages")

def find_whisper_bin() -> str:
    """Dynamically searches for the Whisper executable across common build paths."""
    paths_to_check = [
        shutil.which("whisper-cli"),
        shutil.which("main"),
        os.path.join(BASE_DIR, "build", "bin", "whisper-cli"),
        os.path.join(BASE_DIR, "build", "bin", "main"),
        os.path.join(BASE_DIR, "main"),
        os.path.join(BASE_DIR, "whisper-cli")
    ]
    for p in paths_to_check:
        if p and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return ""

WHISPER_BIN = find_whisper_bin()

def get_default_sink() -> str:
    """Retrieves the default PulseAudio/PipeWire sink name."""
    try:
        res = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception: return ""

MODEL_LIVE  = "gemini-3.1-flash-live-preview"
API_KEY = os.environ.get("GEMINI_API_KEY")

DEFAULT_PW_INPUT  = "bluez_input.00_00_00_00_00_00.0"
DEFAULT_PW_OUTPUT = "bluez_output.00_00_00_00_00_00.1"

ACTIVE_ASSISTANT = None
ACTIVE_TASKS = set()

# =============================================================================
# JSON OUTPUT SCHEMA
# =============================================================================
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "caller_type":            {"type": "string", "enum": ["friend_family", "work", "spam", "commercial", "unknown"]},
        "risk_score":             {"type": "integer", "minimum": 0, "maximum": 100},
        "insult_detected":        {"type": "boolean"},
        "private_data_requested": {"type": "boolean"},
        "caller_name":            {"type": "string"},
        "company":                {"type": "string"},
        "response_text":          {"type": "string"}
    },
    "required": ["caller_type", "risk_score", "insult_detected", "private_data_requested", "response_text"]
}

# =============================================================================
# SYSTEM INITIALIZATION & DATABASE
# =============================================================================
def apply_language_defaults(lang_code: str) -> None:
    """Applies default localized settings to the database if missing."""
    path = os.path.join(LANG_DIR, lang_code, "gui.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: gui_data = json.load(f)
            defaults = gui_data.get("defaults", {})
            if defaults:
                conn = sqlite3.connect(DB_PATH)
                for key, val in defaults.items():
                    db_key = f"{lang_code}_{key}"
                    str_val = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
                    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_key, str_val))
                
                db_greeting_key = f"{lang_code}_initial_greeting"
                res = conn.execute("SELECT value FROM settings WHERE key=?", (db_greeting_key,)).fetchone()
                if res is None or not res[0].strip():
                    default_warning = gui_data.get("default_legal_warning", "")
                    if default_warning: conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_greeting_key, default_warning))
                conn.commit(); conn.close()
        except Exception: pass

def ensure_database_exists() -> None:
    """Ensures that the SQLite database and its required tables are created."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS calls 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, date TEXT, duration INT, 
                  spam_score INT, transcript TEXT, audio_path TEXT, client_audio_path TEXT, 
                  tag TEXT, client_name TEXT, company TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts 
                 (number TEXT PRIMARY KEY, type TEXT, prompt_rules TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Insert system defaults
    c.execute("INSERT OR IGNORE INTO settings VALUES ('wait_seconds', '0')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('auto_block_spam', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_model', 'medium')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_quant', '')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('software_echo_suppression', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('final_transcription_mode', 'realtime')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('monitor_mode', 'both')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('language', 'en-US')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('allow_pc_mic', 'false')")
    conn.commit(); conn.close()

    try:
        conn = sqlite3.connect(DB_PATH)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else "en-US"
        res_asst = conn.execute("SELECT value FROM settings WHERE key=?", (f"{current_lang}_assistant_name",)).fetchone()
        conn.close()
        if res_asst is None: apply_language_defaults(current_lang)
    except Exception: pass

def ensure_system_dependencies() -> None:
    """Checks and applies necessary WirePlumber and oFono configurations for Bluetooth routing."""
    print(f"{_C_SERVER}{ICON_INFO}Checking system configurations...{_R}")
    home_dir = os.path.expanduser("~")

    wp4_dir = os.path.join(home_dir, ".config", "wireplumber", "bluetooth.lua.d")
    wp4_file = os.path.join(wp4_dir, "50-bluez-config.lua")
    wp4_content = """bluez_monitor.properties = {
  ["bluez5.enable-sbc-xq"]    = true,
  ["bluez5.enable-msbc"]      = true,
  ["bluez5.enable-hw-volume"] = true,
  ["bluez5.headset-roles"]    = "[ hsp_hs hsp_ag hfp_hf hfp_ag ]",
  ["bluez5.hfphsp-backend"]   = "native"
}"""

    wp5_dir = os.path.join(home_dir, ".config", "wireplumber", "wireplumber.conf.d")
    wp5_file = os.path.join(wp5_dir, "50-bluez-config.conf")
    wp5_content = """monitor.bluez.properties = {
  bluez5.enable-sbc-xq    = true
  bluez5.enable-msbc      = true
  bluez5.enable-hw-volume = true
  bluez5.headset-roles    = [ hsp_hs hsp_ag hfp_hf hfp_ag ]
  bluez5.hfphsp-backend   = "native"
}"""

    config_changed = False
    for wp_dir, wp_file, content in [(wp4_dir, wp4_file, wp4_content), (wp5_dir, wp5_file, wp5_content)]:
        os.makedirs(wp_dir, exist_ok=True)
        needs_write = True
        if os.path.exists(wp_file):
            with open(wp_file, "r") as f:
                needs_write = (f.read().strip() != content.strip())
        if needs_write:
            with open(wp_file, "w") as f: f.write(content)
            config_changed = True

    blocker = os.path.join(wp4_dir, "51-no-autolink.lua")
    if os.path.exists(blocker):
        os.remove(blocker)
        config_changed = True

    if config_changed: print(f"{_C_SERVER}{ICON_OK}WirePlumber configurations applied.{_R}")

    systemd_dir = os.path.join(home_dir, ".config", "systemd", "user")
    null_sink_file = os.path.join(systemd_dir, "null-sink.service")
    null_sink_content = """[Unit]
Description=PipeWire Null Sink for AI Switchboard
After=pipewire-pulse.service
Requires=pipewire-pulse.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/pactl load-module module-null-sink sink_name=auto_null sink_properties=device.description=NullSink
ExecStop=/usr/bin/pactl unload-module module-null-sink

[Install]
WantedBy=default.target"""

    needs_write = True
    if os.path.exists(null_sink_file):
        with open(null_sink_file, "r") as f:
            needs_write = (f.read().strip() != null_sink_content.strip())
            
    if needs_write:
        os.makedirs(systemd_dir, exist_ok=True)
        with open(null_sink_file, "w") as f: f.write(null_sink_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(["systemctl", "--user", "enable", "--now", "null-sink.service"], check=False, stderr=subprocess.DEVNULL)
        print(f"{_C_SERVER}{ICON_OK}Persistent Null Sink service configured.{_R}")

    try:
        ofono_check = subprocess.run(["systemctl", "is-active", "ofono"], capture_output=True, text=True)
        if ofono_check.stdout.strip() != "active":
            print(f"\n{_C_WARN}{ICON_WARN}oFono service is disabled. Administrator privileges required to enable it.{_R}")
            print(f"{_C_WARN}Please enter your sudo password if prompted:{_R}")
            subprocess.run(["sudo", "systemctl", "enable", "--now", "ofono"], check=True)
            print(f"{_C_SERVER}{ICON_INFO}Restarting Bluetooth to bind with oFono...{_R}")
            subprocess.run(["sudo", "systemctl", "restart", "bluetooth"], check=False)
            print(f"{_C_SERVER}{ICON_INFO}Waiting 5 seconds for hardware discovery...{_R}")
            time.sleep(5.0)
            print(f"{_C_SERVER}{ICON_OK}oFono service enabled successfully.{_R}\n")
    except Exception as e:
        print(f"{_C_ERR}{ICON_ERR}Failed to verify/start oFono: {e}{_R}")

def ensure_null_sink() -> None:
    """Creates a temporary null sink if it does not exist, used for audio monitoring isolation."""
    try:
        res = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
        if "auto_null" not in res.stdout:
            subprocess.run(["pactl", "load-module", "module-null-sink", "sink_name=auto_null", "sink_properties=device.description=NullSink"], capture_output=True)
    except Exception: pass

def initialize_ofono_modems(retries: int = 3) -> None:
    """Connects to the oFono D-Bus interface and powers on all available modems (phones)."""
    for attempt in range(retries):
        try:
            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object("org.ofono", "/"), "org.ofono.Manager")
            modems = manager.GetModems()
            
            if not modems:
                if attempt < retries - 1:
                    time.sleep(3.0); continue
                print(f"{_C_WARN}{ICON_WARN}oFono: no modems found. Ensure your phone is connected via Bluetooth.{_R}"); return
            
            all_ready = True
            for path, props in modems:
                modem = dbus.Interface(bus.get_object("org.ofono", path), "org.ofono.Modem")
                try:
                    if not props.get("Powered", False): modem.SetProperty("Powered", dbus.Boolean(True))
                    if not props.get("Online", False): modem.SetProperty("Online", dbus.Boolean(True))
                    print(f"{_C_SERVER}{ICON_OK}oFono modem ready: {path}{_R}")
                except Exception as e:
                    all_ready = False
                    if attempt == retries - 1: print(f"{_C_ERR}{ICON_ERR}oFono error on {path}: {e}{_R}")
            
            if all_ready: return
            if attempt < retries - 1: time.sleep(3.0)
        except Exception as e:
            if attempt < retries - 1: time.sleep(3.0)
            else: print(f"{_C_ERR}{ICON_ERR}oFono initialization error: {e}{_R}")

def initialize_bluez_devices() -> None:
    """Automatically trusts connected BlueZ devices to allow seamless reconnection."""
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
        for path, interfaces in objects.items():
            if "org.bluez.Device1" in interfaces:
                props = interfaces["org.bluez.Device1"]
                if props.get("Paired", False) and not props.get("Trusted", False):
                    dev_props = dbus.Interface(bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
                    dev_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
                    print(f"{_C_SERVER}{ICON_OK}BlueZ device automatically trusted: {path}{_R}")
    except Exception as e: print(f"{_C_WARN}{ICON_WARN}BlueZ trust error: {e}{_R}")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def get_timestamp() -> str:
    """Returns the current system time formatted as HH:MM:SS."""
    return datetime.datetime.now().strftime("%H:%M:%S")

def get_config(key: str, default_value: str) -> str:
    """Retrieves a configuration value from the SQLite settings table, handling localized keys."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else "en-US"

        localized_keys = ["boss_name", "assistant_name", "assistant_gender", "owner_type", "priority_keywords", "memory_rules", "business_description", "expected_calls", "initial_greeting", "extra_prompt", "text_model"]
        if key in localized_keys:
            res = conn.execute("SELECT value FROM settings WHERE key=?", (f"{current_lang}_{key}",)).fetchone()
            if res is not None:
                return res[0]

        res_global = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return res_global[0] if res_global is not None else default_value
    except Exception: 
        return default_value
    finally:
        if conn:
            conn.close()

def load_language_data(lang_code: str, file_name: str = "assistant.json") -> dict:
    """Loads a JSON configuration file from the specified language directory."""
    path = os.path.join(LANG_DIR, lang_code, file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def calculate_rms(data_pcm: bytes) -> float:
    """Calculates the Root Mean Square (RMS) energy level of PCM audio data."""
    count = len(data_pcm) // 2
    if count == 0: return 0.0
    shorts = struct.unpack(f"<{count}h", data_pcm)
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)

def upsample_16k_to_24k(data_16k: bytes) -> bytes:
    """Upsamples 16kHz PCM audio to 24kHz using basic linear interpolation."""
    num_samples = len(data_16k) // 2
    if num_samples < 2: return b""
    samples = struct.unpack(f"<{num_samples}h", data_16k)
    target_len = int(num_samples * 1.5)
    upsampled = []
    for j in range(target_len):
        src_idx = j / 1.5
        low_idx = int(src_idx)
        high_idx = min(low_idx + 1, num_samples - 1)
        weight = src_idx - low_idx
        upsampled.append(int((1.0 - weight) * samples[low_idx] + weight * samples[high_idx]))
    return struct.pack(f"<{len(upsampled)}h", *upsampled)

def clean_whisper_output(stdout_str: str) -> str:
    """Removes timestamps and brackets from Whisper CLI terminal output."""
    lines = stdout_str.replace('\r', '\n').split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line: continue
        line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*', '', line)
        line = re.sub(r'\[[^\]]*\]', '', line)
        line = re.sub(r'[<>^*_]', '', line)
        line = line.strip()
        if line: cleaned.append(line)
    return " ".join(cleaned)

def clean_ai_text(text: str) -> str:
    """Strips internal system commands (like call:hangup) generated by the AI from the final text."""
    t = re.sub(r"start\s*\{.*?\}\s*endcall", "", text, flags=re.IGNORECASE)
    t = re.sub(r"start\s*\{.*?\}", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\{.*?\}", "", t)
    t = re.sub(r"\b(call:hangup|hangup|call|endcall|start)\b", "", t, flags=re.IGNORECASE)
    return t

def clean_json_text(raw_text: str) -> str:
    """Extracts valid JSON syntax from Markdown code blocks returned by the LLM."""
    if not raw_text or not str(raw_text).strip(): return "{}"
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if m: return m.group(0).strip()
    return "{}"

def extract_response_text(response, default: str = "{}") -> str:
    """Robustly extracts text from a Gemini/Gemma GenerateContent response structure."""
    try:
        for p in response.candidates[0].content.parts:
            if getattr(p, "text", None) and p.text.strip():
                return p.text.strip()
    except Exception: pass
    
    try:
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception: pass

    return default

# =============================================================================
# POLICY ENGINE
# =============================================================================
@dataclass
class PolicyDecision:
    status: str
    reason: str
    safe_args: Dict[str, Any] = field(default_factory=dict)

class CallPolicyEngine:
    """Evaluates security rules before allowing the AI to execute tools like hangup or save."""
    def __init__(self, owner_name: str, parent=None):
        self.owner_name = owner_name
        self.parent = parent

    def evaluate(self, tool_call: Dict[str, Any], call_json: Dict[str, Any], cut_words: List[str]) -> PolicyDecision:
        name = tool_call.get("name")
        args = tool_call.get("args", {})

        if name == "hangup":
            if self.parent and (getattr(self.parent, "hanging_up", False) or getattr(self.parent, "forced_goodbye_active", False)):
                return PolicyDecision("allow", "Forced closure sequence active", args)
            if self.parent and getattr(self.parent, "on_hold", False):
                full_history = getattr(self.parent, "accumulated_transcript", "").lower()
                response_text = call_json.get("response_text", "").lower()
                if any(p in full_history[-300:] or p in response_text for p in cut_words):
                    return PolicyDecision("allow", "Legitimate hold interruption with goodbye", args)
                return PolicyDecision("deny", "Cannot hang up while on hold without prior notice.")
            return PolicyDecision("allow", "Call closure requested", args)

        if name == "save_message":
            if call_json.get("private_data_requested"): return PolicyDecision("deny", "Attempting to retrieve private data")
            return PolicyDecision("allow", "Message saved safely", args)

        return PolicyDecision("confirm", "Requires user confirmation", args)


# =============================================================================
# PHONE ASSISTANT
# =============================================================================
class PhoneAssistant:
    """Main class that handles a single active Bluetooth phone call via Gemini Live."""
    def __init__(self, dbus_path: str, caller_number: str):
        self.dbus_path = dbus_path
        self.caller_number = caller_number
        self.running = False
        self._post_processed = False

        self.boss_name = get_config("boss_name", "Boss")
        self.owner_type = get_config("owner_type", "private")
        self.business_description = get_config("business_description", "")
        self.expected_calls = get_config("expected_calls", "")
        self.assistant_name = get_config("assistant_name", "Assistant")
        self.assistant_gender = get_config("assistant_gender", "female")
        self.current_lang = get_config("language", "en-US")

        mac_match = re.search(r'dev_([0-9A-Z_]+)', dbus_path)
        if mac_match:
            mac_str = mac_match.group(1)
            self.pw_record_target = f"bluez_input.{mac_str}.0"
            self.pw_playback_target = f"bluez_output.{mac_str}.1"
        else:
            self.pw_record_target = DEFAULT_PW_INPUT
            self.pw_playback_target = DEFAULT_PW_OUTPUT

        self.assistant_data = load_language_data(self.current_lang, "assistant.json")
        self.gui_data = load_language_data(self.current_lang, "gui.json")
        self.words_data = self.assistant_data.get("words", {})
        self.prompts_data = self.assistant_data.get("inline_prompts", {})
        self.labels_data = self.assistant_data.get("labels", {})

        self.policy_engine = CallPolicyEngine(owner_name=self.boss_name, parent=self)

        self.accumulated_transcript = ""
        self.call_id = None
        self.last_speaker = None
        self.hanging_up = False
        self.forced_goodbye_active = False
        
        self.hangup_source = ""
        
        self._asst_chunk_buffer = ""
        self._asst_chunk_last_time = 0.0
        
        self.hello_question_sent = False
        self.cutoff_sent = False
        self.hangup_triggered = False
        self.hangup_triggered_time = 0.0
        self.hangup_reason = "completed"
        self.hangup_message_appended = False

        self.user_takeover = False
        self.mic_node_active = False

        self.on_hold = False
        self.priority_call = False
        self.priority_list = [p.strip().lower() for p in get_config("priority_keywords", "").split(",") if p.strip()]
        self.category_wait_seconds = 25.0

        self.waiting_definitive_cut = False
        self.cut_warning_time = 0.0
        self.accumulated_wait_time = 0.0
        self.current_wait_start = 0.0

        self.last_user_spoke_time = time.time()
        self.last_chunk_audio_time = time.time()
        self.last_asst_text_time = time.time()
        self.last_renewal_printed_time = 0.0
        self.recent_asst_phrases = []

        self.audio_out_queue = queue.Queue()
        self.user_turn_audio = []
        self.recording_buffer_wav = bytearray()
        self.caller_recording_buffer = []
        self.currently_playing = False
        self.call_start_time = time.time()
        
        self.first_mic_time = 0.0
        self.last_mic_data_time = 0.0
        self._total_mic_silence_injected = 0.0
        
        self.network_spam_score = 0
        self.state_update_lock = asyncio.Lock()
        
        self.caller_pacat = None
        self.asst_pacat = None

        self.software_echo_suppression = get_config("software_echo_suppression", "true") == "true"
        self.final_transcription_mode = get_config("final_transcription_mode", "realtime")
        
        w_model = get_config("whisper_model", "medium")
        w_quant = get_config("whisper_quant", "")
        self.whisper_full_model = f"{w_model}{w_quant}"

        self.model_text = get_config("text_model", "gemini-3-flash-preview")

        recordings_dir = os.path.join(BASE_DIR, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_path = os.path.join(recordings_dir, f"call_{caller_number}_{ts_str}.wav")
        self.client_recording_path = os.path.join(recordings_dir, f"call_{caller_number}_{ts_str}_client.wav")

        self.client_text = genai.Client(api_key=API_KEY)
        self.client_live = genai.Client(api_key=API_KEY, http_options={"api_version": "v1alpha"})

        self.last_call_json = {
            "caller_type": "unknown", "risk_score": 0, "insult_detected": False,
            "private_data_requested": False, "caller_name": "", "company": "", "response_text": ""
        }

    # ==========================================
    # SPAM AI CHECKER
    # ==========================================
    async def check_network_spam(self) -> bool:
        """Asynchronously queries external spam databases to evaluate the caller's phone number."""
        clean_num = re.sub(r"\D", "", self.caller_number)
        if not clean_num: return False
        
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[SpamCheck] AI evaluating {self.caller_number} across databases...{_R}")
        
        providers_json = get_config("spam_providers", "")
        try: providers = json.loads(providers_json) if providers_json else load_language_data(self.current_lang, "spam.json").get("providers", [])
        except Exception: providers = []
            
        headers = {"User-Agent": "Mozilla/5.0"}
        schema = {
            "type": "object",
            "properties": {"is_spam": {"type": "boolean"}, "risk_score": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["is_spam", "risk_score"]
        }

        async with aiohttp.ClientSession() as http_session:
            for url_template in providers:
                url = url_template.replace("{number}", clean_num)
                try:
                    async with http_session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            clean_text = re.sub(r'<[^>]+>', ' ', html)
                            clean_text = re.sub(r'\s+', ' ', clean_text).strip()[:15000] 
                            
                            is_gemma = "gemma" in self.model_text.lower()
                            
                            if is_gemma:
                                prompt = (f"Analyze user comments from a spam-lookup website and output a JSON object.\n\n"
                                          f"SCHEMA:\n{{\"is_spam\": boolean, \"risk_score\": integer, \"reason\": string}}\n\n"
                                          f"TEXT:\n{clean_text}\n\nJSON:\n")
                                config = types.GenerateContentConfig(temperature=0.0)
                            else:
                                safety_settings = [
                                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
                                ]
                                prompt = (
                                    f"Analyze this raw text extracted from a phone number lookup website for the number {clean_num}.\n\n"
                                    f"EVALUATION RULES:\n"
                                    f"1. IGNORE BOILERPLATE: Do not flag based on website navigation text, ads, or generic UI.\n"
                                    f"2. NO USER REPORTS = CLEAN: If there are zero complaints or reports about this number, output is_spam=false and risk_score=0.\n"
                                    f"3. CONTRADICTORY REPORTS: Require an overwhelming majority (>75%) of negative reports to flag as spam.\n"
                                    f"4. LOW VOLUME: If there are only 1 to 3 reports, evaluate their individual severity carefully.\n"
                                    f"5. THRESHOLD: Only set is_spam=true if the genuine user-generated risk is clearly high.\n\n"
                                    f"RAW TEXT TO ANALYZE:\n{clean_text}\n\n"
                                    f"Based strictly on actual user reports for THIS number, return the JSON."
                                )
                                config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema, temperature=0.0, safety_settings=safety_settings, thinking_config=types.ThinkingConfig(thinking_budget=0))
                            
                            buf = io.StringIO()
                            with contextlib.redirect_stderr(buf):
                                response = await asyncio.to_thread(self.client_text.models.generate_content, model=self.model_text, contents=prompt, config=config)
                            
                            text_part = extract_response_text(response, default="{}")
                            cleaned_text = clean_json_text(text_part)
                            try: data = json.loads(cleaned_text)
                            except (json.JSONDecodeError, TypeError): data = {"is_spam": False, "risk_score": 0}
                            
                            if data.get("is_spam") or data.get("risk_score", 0) > 70:
                                self.network_spam_score = data.get("risk_score", 0)
                                print(f"{_C_WARN}[{get_timestamp()}] [SpamCheck] LLM Flagged as SPAM (Score: {data.get('risk_score')}): {data.get('reason')}{_R}")
                                return True
                except Exception: pass
        return False

    # ==========================================
    # PIPEWIRE LINK MANAGEMENT
    # ==========================================
    async def enforce_bluetooth_call_profile(self) -> None:
        """Forces the Bluetooth controller to switch to the Hands-Free Profile (HFP) for calling."""
        mac_match = re.search(r'dev_([0-9A-Z_]+)', self.dbus_path)
        if not mac_match: return
        mac_str = mac_match.group(1).upper()
        
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[Bluetooth] Scanning for Bluetooth audio card...{_R}")
        
        card_name = f"bluez_card.{mac_str}"
        try:
            proc = await asyncio.create_subprocess_exec("pactl", "list", "cards", "short", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            for line in stdout.decode("utf-8", errors="ignore").splitlines():
                if "bluez_card" in line and mac_str in line:
                    card_name = line.split()[1]
                    break
        except Exception: pass

        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[Bluetooth] Forcing HFP profile on {card_name}...{_R}")
        
        profiles_to_try = ["headset-audio-gateway", "headset-head-unit", "hfp-ag", "hfp-hf"]
        for profile in profiles_to_try:
            try:
                proc = await asyncio.create_subprocess_exec("pactl", "set-card-profile", card_name, profile, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await proc.wait()
                if proc.returncode == 0:
                    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] Audio profile successfully changed to: {profile}{_R}")
                    return
            except Exception: pass
                
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Warning: Could not force profile. Relying on auto-switching.{_R}")

    async def wait_for_pw_node(self, node_name: str, timeout: float = 12.0) -> Tuple[bool, str]:
        """Polls PipeWire to ensure the requested audio node is active before proceeding."""
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[PipeWire] Waiting for node: {node_name}...{_R}")
        base_name = re.sub(r'\.\d+$', '', node_name)
        deadline = time.time() + timeout
        
        while time.time() < deadline and self.running:
            proc_out = await asyncio.create_subprocess_exec("pw-link", "-o", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout_out, _ = await proc_out.communicate()
            proc_in = await asyncio.create_subprocess_exec("pw-link", "-i", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout_in, _ = await proc_in.communicate()
            combined = stdout_out.decode("utf-8", errors="ignore") + "\n" + stdout_in.decode("utf-8", errors="ignore")
            for line in combined.splitlines():
                node_part = line.strip().split(':')[0]
                if base_name in node_part: return True, node_part
            await asyncio.sleep(0.5)
        return False, node_name

    # ==========================================
    # DYNAMIC LOCAL MONITOR ROUTER (PC SPEAKERS)
    # ==========================================
    async def monitor_routing_manager(self) -> None:
        """Background daemon that mirrors call audio to PC speakers dynamically based on settings."""
        while self.running:
            mode = get_config("monitor_mode", "both")
            allow_pc_mic = get_config("allow_pc_mic", "false") == "true"
            
            if mode in ["both", "assistant"]:
                if self.asst_pacat is None or self.asst_pacat.poll() is not None:
                    self.asst_pacat = subprocess.Popen(["pacat", "--format=s16le", "--rate=24000", "--channels=1", "--raw"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            else:
                if self.asst_pacat and self.asst_pacat.poll() is None:
                    self.asst_pacat.terminate(); self.asst_pacat = None

            if mode in ["both", "caller"]:
                if self.caller_pacat is None or self.caller_pacat.poll() is not None:
                    sink = get_default_sink()
                    cmd = ["pacat", "--format=s16le", "--rate=16000", "--channels=1", "--raw"]
                    if sink: cmd.append(f"--device={sink}")
                    else: cmd.append("--device=alsa_output.pci-0000_10_00.6.analog-stereo")
                    self.caller_pacat = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            else:
                if self.caller_pacat and self.caller_pacat.poll() is None:
                    self.caller_pacat.terminate(); self.caller_pacat = None

            try:
                proc = await asyncio.create_subprocess_exec("pw-link", "-l", "--id", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await proc.communicate()
                text = out.decode("utf-8", errors="ignore")
                src_name = ""
                for line in text.splitlines():
                    m_src = re.match(r'^\s{1,4}\d+\s+([\w.\-]+):[\w_]+\s*$', line)
                    if m_src:
                        src_name = m_src.group(1)
                        continue
                    m_dst = re.match(r'^\s+(\d+)\s+\|->\s+\d+\s+([\w.\-]+):[\w_]+\s*$', line)
                    if m_dst and src_name:
                        link_id = m_dst.group(1)
                        dst_name = m_dst.group(2)
                        
                        # Disconnect local PC microphone from Bluetooth outputs to prevent audio leaks and echo
                        if not allow_pc_mic and "bluez_output" in dst_name and ("alsa_input" in src_name or "pci" in src_name or "usb" in src_name):
                            await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        # Disconnect Bluetooth input from PC speakers if requested
                        if "bluez_input" in src_name and mode not in ["both", "caller"]:
                            sink = get_default_sink()
                            if ("alsa_output" in dst_name) or (sink and sink in dst_name):
                                await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass
            
            # FIX: Relax polling to 2.0s to prevent aggressive audio probing which causes in-call clicking
            await asyncio.sleep(2.0)

        for pacat in [self.caller_pacat, self.asst_pacat]:
            if pacat:
                try:
                    if pacat.stdin: pacat.stdin.close()
                    pacat.kill(); pacat.wait()
                except Exception: pass

    # ==========================================
    # DB AND D-BUS HANDLERS
    # ==========================================
    def log_system_message(self, message_text: str, emoji_prefix: str = "⚠") -> None:
        """Logs internal system events to the console and appends them to the call transcript."""
        ts = get_timestamp()
        clean_msg = message_text.replace("⏳", "").replace("⚠", "").replace("❌", "").replace("⏸", "").replace("▶️", "").replace("[SYSTEM]", "").replace(":", "").strip()
        
        # Prepend "> " if the system is currently on hold.
        prefix = "> " if getattr(self, "on_hold", False) else ""
        console_tag = f"{prefix}{emoji_prefix} [SYSTEM]" if USE_EMOJI else f"{prefix}[SYSTEM]"
        
        print(f"\n{_C_WARN}[{ts}] {console_tag}: {clean_msg}{_R}")
        self.accumulated_transcript += f"\n\n{emoji_prefix} [{ts}]: [SYSTEM]: {clean_msg}"
        self.update_transcription_db()

    def create_call_record_db(self) -> None:
        """Initializes a new row in the database for the current incoming call."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Use generic system icon to prevent GUI from mapping to AI.
        initial = f"⚠ [{get_timestamp()}]: [SYSTEM]: Call Connected."
        self.accumulated_transcript = initial
        
        in_lbl = self.gui_data.get("ui_in_progress", "IN PROGRESS")
        
        c.execute(
            "INSERT INTO calls (number, date, duration, spam_score, transcript, audio_path, client_audio_path, tag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.caller_number, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0, 0, initial, self.recording_path, "", in_lbl)
        )
        self.call_id = c.lastrowid
        conn.commit(); conn.close()

    def update_transcription_db(self) -> None:
        """Writes the accumulated transcription string into the database."""
        if self.call_id:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE calls SET transcript=? WHERE id=?", (self.accumulated_transcript, self.call_id))
            conn.commit(); conn.close()

    def save_to_db(self, name: str, message: str) -> None:
        """Saves a specific message/appointment (triggered by the AI tool) to the transcript."""
        if self.call_id:
            msg_fmt = self.assistant_data.get("ui_saved_message", "Message from {name}: {message}")
            final_msg = msg_fmt.format(name=name, message=message)
            
            # Add the message to the internal memory with a highlighted format
            recado_visual = f"\n\n📝 [{get_timestamp()}]: [SYSTEM]: *** {final_msg} ***"
            self.accumulated_transcript += recado_visual
            
            # Update the database safely
            self.update_transcription_db()
            
            print(f"\n{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[DB] {final_msg}{_R}")

    def answer_call(self) -> None:
        """Answers the incoming D-Bus oFono call."""
        try:
            iface = dbus.Interface(dbus.SystemBus().get_object("org.ofono", self.dbus_path), "org.ofono.VoiceCall")
            iface.Answer()
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[D-Bus] Call answered: {self.caller_number}{_R}")
        except Exception as e: print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[D-Bus] Answer failed: {e}{_R}")

    def hangup_call(self) -> None:
        """Terminates the current D-Bus oFono call."""
        try:
            iface = dbus.Interface(dbus.SystemBus().get_object("org.ofono", self.dbus_path), "org.ofono.VoiceCall")
            iface.Hangup()
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[D-Bus] Call terminated.{_R}")
        except Exception: pass

    # ==========================================
    # AUDIO SUBPROCESS HANDLING
    # ==========================================
    async def send_mic_audio(self, session) -> None:
        """Continuously reads PCM data from the Bluetooth microphone node and streams it to Gemini."""
        print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_AUDIO}[Mic] Active on node: {self.pw_record_target}{_R}")
        cmd = ["pw-record", f"--target={self.pw_record_target}", "-P", '{"node.dont-reconnect": true}', "--format=s16", "--rate=16000", "--channels=1", "-"]
        env = os.environ.copy()
        env["PW_DEBUG"] = "0"
        
        takeover_notified = False
        base_target = re.sub(r'\.\d+$', '', self.pw_record_target)

        while self.running:
            if self.hanging_up:
                await asyncio.sleep(0.1); continue

            # FIX CLICKS: Check if Bluetooth node exists using native pw-link to prevent audio graph crashes
            check_proc = await asyncio.create_subprocess_exec("pw-link", "-o", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await check_proc.communicate()
            if base_target not in out.decode("utf-8"):
                if not takeover_notified:
                    self.log_system_message("Audio routed to handset (Takeover). AI paused...", "⏸")
                    takeover_notified = True
                await asyncio.sleep(1.0)
                continue

            try: 
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env)
            except Exception: 
                if not takeover_notified:
                    self.log_system_message("Audio routed to handset (Takeover). AI paused...", "⏸")
                    takeover_notified = True
                await asyncio.sleep(1.0)
                continue

            background_energy = 40.0
            consecutive_empty = 0
            valid_chunks = 0

            try:
                while self.running:
                    if self.hanging_up:
                        await asyncio.sleep(0.1); continue
                        
                    try: 
                        data = await asyncio.wait_for(proc.stdout.read(512), timeout=1.0)
                    except asyncio.TimeoutError:
                        break

                    if not data:
                        consecutive_empty += 1
                        if consecutive_empty > 2:
                            break
                        continue
                        
                    consecutive_empty = 0
                    valid_chunks += 1
                    self.mic_node_active = True
                    now = time.time()
                    
                    if takeover_notified and valid_chunks > 15:
                        self.log_system_message("Audio restored to Bluetooth. AI resumed...", "▶️")
                        takeover_notified = False
                        self.last_user_spoke_time = now
                        if self.current_wait_start > 0:
                            self.current_wait_start = now
                        
                        return_prompt = self.prompts_data.get("hold_return_prompt", "[SYSTEM: The caller has returned to the line. Break the silence and respond immediately.]")
                        await session.send_realtime_input(text=return_prompt)

                    count = len(data) // 2
                    if count > 0:
                        samples = struct.unpack(f"<{count}h", data)
                        samples = [max(min(s * 3, 32767), -32768) for s in samples]
                        data = struct.pack(f"<{count}h", *samples)
                    
                    if not self.caller_recording_buffer: 
                        self.first_mic_time = now
                        self.last_mic_data_time = now
                    else:
                        time_gap = now - self.last_mic_data_time
                        if time_gap > 0.5:
                            silence_bytes = int(time_gap * 16000) * 2
                            if silence_bytes > 0:
                                self.caller_recording_buffer.append(b"\x00" * silence_bytes)
                                self._total_mic_silence_injected += time_gap
                                
                    self.last_mic_data_time = now
                    self.caller_recording_buffer.append(data)
                    
                    if self.caller_pacat and self.caller_pacat.poll() is None:
                        try:
                            self.caller_pacat.stdin.write(data)
                            self.caller_pacat.stdin.flush()
                        except Exception: pass

                    rms = calculate_rms(data)
                    if rms < 350: background_energy = 0.98 * background_energy + 0.02 * rms
                    
                    adaptive_gate = max(10, min(45, int(10 + (background_energy * 0.4))))
                    noise_gate = min(60, adaptive_gate + 15) if self.on_hold else adaptive_gate

                    is_silence = (rms < noise_gate)
                    is_echo = (self.software_echo_suppression and self.currently_playing)

                    if is_silence or is_echo:
                        data = b"\x00" * len(data)
                    else:
                        self.user_turn_audio.append(data)

                    await session.send_realtime_input(audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000"))

            except Exception: pass
            finally:
                self.mic_node_active = False
                try: 
                    proc.kill()
                    await proc.wait()
                except Exception: pass
            
            if self.running and not takeover_notified and not self.mic_node_active:
                self.log_system_message("Audio routed to handset (Takeover). AI paused...", "⏸")
                takeover_notified = True
                
            await asyncio.sleep(1.0)

    def sync_playback_loop(self) -> None:
        """Reads audio generated by Gemini from a queue and pipes it to the Bluetooth speaker node."""
        cmd = ["pw-play", f"--target={self.pw_playback_target}", "-P", '{"node.dont-reconnect": true}', "--format=s16", "--rate=24000", "--channels=1", "-"]
        env = os.environ.copy()
        env["PW_DEBUG"] = "0"
        proc = None
        
        try:
            while self.running or not self.audio_out_queue.empty():
                
                # FIX CLICKS: If handset is in Takeover, do not force the player. Flush the queue quietly.
                if not getattr(self, "mic_node_active", True):
                    try:
                        while True:
                            self.audio_out_queue.get_nowait()
                            self.audio_out_queue.task_done()
                    except queue.Empty: pass
                    time.sleep(0.2)
                    continue

                try:
                    chunk = self.audio_out_queue.get(timeout=0.1)
                    self.currently_playing = True
                    
                    if proc is None or proc.poll() is not None:
                        if proc:
                            try:
                                proc.kill()
                                proc.wait()
                            except Exception: pass
                        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                        
                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                        self.last_chunk_audio_time = time.time()
                    except Exception:
                        pass
                    
                    self.audio_out_queue.task_done()
                except queue.Empty: self.currently_playing = False
                except Exception: self.currently_playing = False
        finally:
            if proc:
                try:
                    if proc.stdin: proc.stdin.close()
                    proc.kill()
                    proc.wait()
                except Exception: pass

    # ==========================================
    # HYBRID WHISPER LOGIC & JSON DATA
    # ==========================================
    def _calculate_text_similarity(self, a: str, b: str) -> float:
        """Calculates simple similarity ratio between two strings using sets of words."""
        a, b = a.lower().strip(), b.lower().strip()
        if not a and not b: return 1.0
        if not a or not b: return 0.0
        wa, wb = set(a.split()), set(b.split())
        if not wa or not wb: return 0.0
        return len(wa & wb) / len(wa | wb)

    def _has_foreign_language_noise(self, text: str) -> bool:
        """Detects if transcription contains hallucinated foreign noise words."""
        words = text.lower().split()
        if not words: return False
        foreign = set(self.words_data.get("foreign_noise", []))
        return (sum(1 for w in words if w in foreign) / len(words)) > 0.30

    def _has_excessive_repetition(self, text: str) -> bool:
        """Detects loop hallucinations (e.g. 'hello hello hello')."""
        words = text.lower().split()
        if len(words) < 5: return False
        _, freq = Counter(words).most_common(1)[0]
        return freq > 4 and (freq / len(words)) > 0.40

    def _is_transcription_noise(self, text: str) -> bool:
        """Detects common system-level transcription noise markers."""
        t = re.sub(r'[\(\[\{].*?[\)\}\]]', '', text).strip().lower()
        if not t or re.match(r'^[¿¡\s\-,.;.:!?]+$', t): return True
        return t in set(self.words_data.get("transcription_noise", []))

    async def heal_transcription_whisper(self, audio_bytes_list: list, gemini_txt: str, turn_ts: str = "") -> None:
        """Re-evaluates a short audio snippet using the local Whisper model for higher accuracy."""
        model_path = f"./models/ggml-{self.whisper_full_model}.bin"
        if not WHISPER_BIN or not os.path.exists(WHISPER_BIN) or not os.path.exists(model_path): return
        tmp_wav = f"/tmp/whisper_turn_{str(uuid.uuid4())[:8]}.wav"
        try:
            with wave.open(tmp_wav, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                for chunk in audio_bytes_list: wf.writeframes(chunk)
            lang_arg = self.current_lang.split("-")[0]
            proc = await asyncio.create_subprocess_exec(
                WHISPER_BIN, "-l", lang_arg, "-t", "4", "-m", model_path, "-f", tmp_wav,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if not stdout: return
            whisper_txt = clean_whisper_output(stdout.decode("utf-8", errors="ignore"))
            wv = not (not whisper_txt.strip() or self._has_foreign_language_noise(whisper_txt) or self._has_excessive_repetition(whisper_txt) or self._is_transcription_noise(whisper_txt))
            gv = not (not gemini_txt.strip() or self._has_foreign_language_noise(gemini_txt) or self._has_excessive_repetition(gemini_txt) or self._is_transcription_noise(gemini_txt))
            
            combined = f"{gemini_txt} | [Whisper]: {whisper_txt}" if gv and wv else ("[Noise Filtered]" if not gv and not wv else f"[Noise Filtered] | [Whisper]: {whisper_txt}" if wv else f"{gemini_txt} | [Whisper]: [Noise Filtered]")
            pat = f"🗣 [{turn_ts}]: {gemini_txt}"
            if pat in self.accumulated_transcript:
                self.accumulated_transcript = self.accumulated_transcript.replace(pat, f"🗣 [{turn_ts}]: {combined}")
            
            # Visual update only for console output (does not affect state logic)
            _C_WHISPER = "\033[33m" if SUPPORTS_COLOR else ""
            whisper_display = whisper_txt if wv else "[Noise Filtered]"
            print(f"\n{_C_WHISPER}· [Whisper/{turn_ts}]: {whisper_display}{_R}", flush=True)
            self.update_transcription_db()
        except Exception: pass
        finally:
            if os.path.exists(tmp_wav): os.remove(tmp_wav)

    def is_valid_text(self, text: str) -> bool:
        """Filters out non-Latin character sets and extremely short non-word artifacts."""
        if re.search(r"[\u4e00-\u9fff\uac00-\ud7a3\u3040-\u30ff\u1100-\u11ff]", text): return False
        cleaned = text.strip().lower()
        if len(cleaned) <= 1 and cleaned not in ('y', 'o', 'a', 's', 'i', 'sí', 'si', 'no'): return False
        return True

    async def update_state_json_safe(self, full_transcript: str) -> None:
        """Non-blocking wrapper to periodically extract structured JSON state."""
        if not hasattr(self, "last_state_update_time"): self.last_state_update_time = 0.0
        now = time.time()
        if (now - self.last_state_update_time) < 25.0 or self.state_update_lock.locked(): return
        async with self.state_update_lock:
            self.last_state_update_time = time.time()
            try: await asyncio.to_thread(self.execute_blocking_generate_content, full_transcript)
            except Exception: pass

    def execute_blocking_generate_content(self, complete_transcript: str) -> None:
        """Sends transcript history to LLM model to deduce caller identity and risks (JSON mapping)."""
        raw_instruction = self.assistant_data.get("output_schema_instruction", "Analyze the transcript.")
        try:
            instruction = raw_instruction.format(boss_name=self.boss_name, assistant_name=self.assistant_name)
        except (KeyError, ValueError):
            instruction = raw_instruction

        is_gemma = "gemma" in self.model_text.lower()
        
        if is_gemma:
            prompt = f"{instruction}\n\nOUTPUT MUST BE STRICTLY A JSON OBJECT CONFORMING TO THIS SCHEMA:\n{json.dumps(OUTPUT_SCHEMA, indent=2)}\n\nTRANSCRIPT:\n{complete_transcript}\n\nJSON:\n"
            config = types.GenerateContentConfig(temperature=0.0)
        else:
            safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
            ]
            prompt = f"{instruction}\nTRANSCRIPT:\n{complete_transcript}"
            config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=OUTPUT_SCHEMA, temperature=0.0, safety_settings=safety_settings, thinking_config=types.ThinkingConfig(thinking_budget=0))

        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                response = self.client_text.models.generate_content(model=self.model_text, contents=prompt, config=config)
            
            text_part = extract_response_text(response, default="{}")
            cleaned_text = clean_json_text(text_part)
            parsed = json.loads(cleaned_text)
            
            if "caller_type" in parsed and "risk_score" in parsed:
                self.last_call_json = parsed
        except Exception:
            self.last_call_json = {"caller_type": "unknown", "risk_score": 0, "insult_detected": False, "private_data_requested": False, "caller_name": "", "company": "", "response_text": ""}

    def _matches_any_phrase(self, text: str, phrases: list) -> bool:
        """
        Checks whether any phrase from the list appears in text.
        Single-word entries require a word-boundary match to avoid false positives.
        Multi-word entries are matched as plain substrings.
        """
        t = text.lower()
        for phrase in phrases:
            phrase_l = phrase.lower().strip()
            if not phrase_l:
                continue
            if " " in phrase_l:
                if phrase_l in t:
                    return True
            else:
                if re.search(r'(?<![a-záéíóúñüàèìòùâêîôûäëïöüãõ])' + re.escape(phrase_l) + r'(?![a-záéíóúñüàèìòùâêîôûäëïöüãõ])', t):
                    return True
        return False
    
    def _check_wait_return(self, text: str) -> bool:
        """Checks if the transcription contains words indicating return from hold."""
        triggers = list(self.words_data.get("return_triggers", []))
        triggers.extend([self.assistant_name.lower(), self.boss_name.lower()])
        return self._matches_any_phrase(text, triggers)

    async def receive_audio_and_tools(self, session) -> None:
        """Main interaction loop handling incoming events, audio, and logic rules from Gemini Live."""
        threading.Thread(target=self.sync_playback_loop, daemon=True).start()

        self.last_user_spoke_time = time.time()
        self.last_chunk_audio_time = time.time()
        self.last_asst_text_time = time.time()

        initial_greeting = get_config("initial_greeting", "")
        if initial_greeting: greeting = f"[SYSTEM: Start the call by saying EXACTLY this phrase, word by word, without adding anything else: '{initial_greeting}']"
        else: greeting = self.prompts_data.get("greeting", "").format(assistant_name=self.assistant_name, boss_name=self.boss_name)

        global ICON_ASST, ICON_USER_STR
        ICON_ASST = "📞 " if USE_EMOJI else f"[{self.assistant_name}]: "
        ICON_USER_STR = "🗣  " if USE_EMOJI else f"[{self.labels_data.get('ui_user_label', 'Caller')}]: "

        print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[{self.assistant_name}] Connecting to Gemini Live websocket...{_R}")
        await session.send_realtime_input(text=greeting)
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_OK}[{self.assistant_name}] Connected. Conversation started.{_R}")

        while self.running:
            # Evaluate graceful exit sequences.
            if self.hanging_up and self.audio_out_queue.empty():
                # Cut the call after 3.5 seconds or if AI does not stop speaking
                if time.time() - self.last_chunk_audio_time > 1.0 or time.time() - getattr(self, "hangup_triggered_time", time.time()) > 3.5:
                    
                    print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Final goodbye audio finished playing. Cutting call.{_R}")
                    # Execute network disconnect directly
                    self.hangup_call()
                    await asyncio.sleep(0.5)
                    self.running = False
                    break

            # Maintain active status while assistant speaks.
            if self.currently_playing: 
                self.last_user_spoke_time = time.time()

            # Freeze inactivity timers while owner takes over the call locally
            if not self.mic_node_active:
                self.last_user_spoke_time = time.time()
                if self.current_wait_start > 0:
                    self.current_wait_start = time.time()

            # Dynamic Inactivity Loop Execution
            if not self.hanging_up:
                silence_threshold = self.category_wait_seconds if (self.on_hold or self.priority_call) else 25.0
                time_without_user = time.time() - self.last_user_spoke_time
                total_hold_time = self.accumulated_wait_time + (time.time() - self.current_wait_start if self.on_hold and self.current_wait_start > 0 else 0)

                if self.waiting_definitive_cut:
                    if time.time() - self.cut_warning_time > 20.0:
                        self.hanging_up = self.forced_goodbye_active = self.hangup_triggered = True
                        self.hangup_reason = "completed"
                        self.log_system_message("Grace period exhausted. Forcing hangup...", "❌")
                        await session.send_realtime_input(text=self.prompts_data.get("silence_grace_end", ""))
                
                # Check maximum allowed total hold time (15 minutes / 900 seconds safety net)
                elif self.on_hold and total_hold_time > 900.0 and not self.waiting_definitive_cut:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.log_system_message("Maximum accumulated hold time (15 mins) exceeded. Starting 15s grace warning...", "⚠")
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))
                
                # Initial Silence Timeout -> Ask Hello
                elif time_without_user > silence_threshold and not self.hello_question_sent and not self.waiting_definitive_cut:
                    self.log_system_message(f"{int(silence_threshold)}s without response. Asking if someone is there...", "⏳")
                    self.hello_question_sent = True
                    self.last_user_spoke_time = time.time()  # Reset the inactivity timer to wait exactly 15s from now
                    await session.send_realtime_input(text=self.prompts_data.get("hello_question", ""))
                
                # Extended Silence (15 seconds after Assistant finished asking hello) -> Grace Warning
                elif self.hello_question_sent and not self.waiting_definitive_cut and time_without_user > 15.0:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.last_user_spoke_time = time.time()  # Reset timer to wait another 15s properly
                    self.log_system_message("Continued silence. Starting 15s grace period...", "⏳")
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))

            # Non-blocking web socket receiving event loop.
            try: msg = await asyncio.wait_for(session._receive(), timeout=0.5)
            except asyncio.TimeoutError: continue
            except Exception: break

            if getattr(msg, "tool_call", None):
                function_responses = []
                for fc in msg.tool_call.function_calls:
                    decision = self.policy_engine.evaluate({"name": fc.name, "args": dict(fc.args)}, self.last_call_json, self.words_data.get("cut_words", []))
                    if decision.status == "allow":
                        if fc.name == "hangup":
                            self.hanging_up = self.hangup_triggered = True
                            self.hangup_triggered_time = time.time()
                            self.hangup_reason = "completed"
                            self.hangup_source = "tool"
                            print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] {self.assistant_name} requested hangup via tool. Waiting for audio to finish...{_R}")
                        elif fc.name == "save_message":
                            self.save_to_db(fc.args.get("caller_name"), fc.args.get("message_text"))
                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": True}))
                    else:
                        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[SECURITY POLICY]: Action '{fc.name}' denied. Reason: {decision.reason}{_R}")
                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": False, "error": f"Action denied by security policy: {decision.reason}"}))
                if function_responses: await session.send_tool_response(function_responses=function_responses)

            sc = getattr(msg, "server_content", None)
            if sc:
                itx = getattr(sc, "input_transcription", None)
                if itx and itx.text and self.hanging_up and getattr(self, "hangup_triggered", False): itx = None

                if itx and getattr(itx, "text", None) and self.is_valid_text(itx.text):
                    self.last_user_spoke_time = time.time()
                    self.hello_question_sent = self.cutoff_sent = False
                    
                    if self.waiting_definitive_cut:
                        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Interruption during grace period. Cancelling hangup...{_R}")
                        self.waiting_definitive_cut = False

                    just_activated_hold = False

                    # --- Caller initiates hold manually ---
                    if not self.hanging_up and not self.on_hold:
                        user_safe_text = itx.text.lower()
                        for iw in self.words_data.get("ignore_hold_words", []):
                            user_safe_text = user_safe_text.replace(iw.lower(), "")
                        
                        if self._matches_any_phrase(user_safe_text, self.words_data.get("hold_words", [])):
                            self.on_hold = True
                            just_activated_hold = True
                            self.current_wait_start = self.last_user_spoke_time = time.time()
                            self.last_speaker = None
                            self.log_system_message(f"Hold activated by caller. Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")

                    if self.on_hold:
                        if not just_activated_hold:
                            # --- Caller renews hold time ---
                            user_safe_text = itx.text.lower()
                            for iw in self.words_data.get("ignore_hold_words", []):
                                user_safe_text = user_safe_text.replace(iw.lower(), "")

                            if self._matches_any_phrase(user_safe_text, self.words_data.get("hold_words", [])):
                                now = time.time()
                                self.last_user_spoke_time = now  # Reset the inactivity timer!
                                if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                    self.last_renewal_printed_time = now
                                    self.log_system_message(self.words_data.get("hold_renewed_caller", "⏳ [SYSTEM]: Wait time renewed by caller request (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)), "⏳")

                            # --- Check return from hold ---
                            if not self._check_wait_return(itx.text):
                                ts = get_timestamp()
                                self.log_system_message(f"Active Hold Ignored background noise / TV '{itx.text}'", "⏸")
                                if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                                    cloned_audio = list(self.user_turn_audio); self.user_turn_audio.clear()
                                    asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts))
                                else: self.user_turn_audio.clear()
                                itx = None  
                            elif not self._matches_any_phrase(user_safe_text, self.words_data.get("hold_words", [])):
                                self.log_system_message("Return from hold detected. Resuming conversation...", "⏳")
                                self.on_hold = False
                                if self.current_wait_start > 0: self.accumulated_wait_time += (time.time() - self.current_wait_start)
                                self.current_wait_start = 0.0

                    if itx:
                        ts = get_timestamp()
                        prefix = "> " if self.on_hold else ""
                        print(f"\n\n{_C_MUTED}{prefix}[{ts}]{_R} {_C_AUDIO}{ICON_USER_STR}{itx.text}{_R}")
                        self.accumulated_transcript += f"\n\n🗣 [{ts}]: {itx.text}"
                        self.update_transcription_db()
                        
                        if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                            cloned_audio = list(self.user_turn_audio); self.user_turn_audio.clear()
                            asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts))
                        else: self.user_turn_audio.clear()
                        
                        user_low_text = itx.text.lower()
                        for rule in json.loads(get_config("memory_rules", "[]")):
                            if any(kw in user_low_text for kw in rule.get("keywords", [])):
                                if not self.priority_call:
                                    self.category_wait_seconds = float(rule.get("wait_seconds", 120))
                                    self.log_system_message(f"Priority keyword detected. Activating extended attention mode ({int(self.category_wait_seconds)}s).", "⚠")
                                    self.priority_call = True
                                break

                model_turn = getattr(sc, "model_turn", None)
                if model_turn:
                    for part in model_turn.parts:
                        try:
                            inline_data = getattr(part, "inline_data", None)
                            if inline_data and isinstance(getattr(inline_data, "data", None), bytes):
                                target_byte_idx = int((time.time() - self.call_start_time) * 24000) * 2  
                                current_len = len(self.recording_buffer_wav)
                                if current_len < target_byte_idx: self.recording_buffer_wav.extend(b"\x00" * (target_byte_idx - current_len))
                                self.recording_buffer_wav.extend(inline_data.data)
                                self.audio_out_queue.put(inline_data.data)
                                if self.asst_pacat and self.asst_pacat.poll() is None:
                                    try: self.asst_pacat.stdin.write(inline_data.data); self.asst_pacat.stdin.flush()
                                    except Exception: pass
                                self.last_chunk_audio_time = time.time()
                                self.cutoff_sent = False
                        except Exception: pass

                otx = getattr(sc, "output_transcription", None)
                if otx and getattr(otx, "text", None):
                    self.user_turn_audio.clear()
                    clean_otx = clean_ai_text(otx.text)
                    if clean_otx:
                        clean_norm = re.sub(r'[^\w\s]', '', clean_otx.lower()).strip()
                        if len(clean_norm.split()) >= 3:
                            now = time.time()
                            self.recent_asst_phrases = [p for p in self.recent_asst_phrases if now - p[1] < 4.0]
                            if any(clean_norm == p[0] for p in self.recent_asst_phrases): continue
                            self.recent_asst_phrases.append((clean_norm, now))

                        force_new_timestamp = (time.time() - self.last_asst_text_time > 4.0)
                        self.last_asst_text_time = time.time()

                        prefix = "> " if self.on_hold else ""
                        if self.last_speaker != self.assistant_name.lower() or force_new_timestamp:
                            ts_asst = get_timestamp()
                            print(f"\n\n{_C_MUTED}{prefix}[{ts_asst}]{_R} {_C_CONN}{ICON_ASST}{clean_otx}{_R}", end="", flush=True)
                            self.accumulated_transcript += f"\n\n📞 [{ts_asst}]: {clean_otx}"
                            self.last_speaker = self.assistant_name.lower()
                        else:
                            print(f"{_C_CONN}{clean_otx}{_R}", end="", flush=True)
                            self.accumulated_transcript += clean_otx

                        self.update_transcription_db()

                        # --- Accumulate streaming chunks in a larger time window (2.5 secs) ---
                        # Gemini Live sends the assistant transcription in partial chunks.
                        # We use 2.5s to ensure the sentence is fully completed before evaluating it.
                        now_chunk = time.time()
                        if now_chunk - self._asst_chunk_last_time < 2.5:
                            self._asst_chunk_buffer += " " + clean_otx
                        else:
                            self._asst_chunk_buffer = clean_otx
                        self._asst_chunk_last_time = now_chunk
                        eval_text = self._asst_chunk_buffer.lower()

                        # --- Build safe_eval_text: remove ignore_hold_words before hold detection ---
                        safe_eval_text = eval_text
                        for iw in self.words_data.get("ignore_hold_words", []):
                            safe_eval_text = safe_eval_text.replace(iw.lower(), "")

                        # --- HOLD renewal: assistant speaks while on hold ---
                        if self.on_hold and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", [])):
                            now = time.time()
                            self.last_user_spoke_time = now  # Reset the inactivity timer!
                            if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                self.last_renewal_printed_time = now
                                self.log_system_message(
                                    self.words_data.get("hold_renewed_assistant", "⏳ [SYSTEM]: Wait time renewed by assistant response (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)), "⏳")

                        # --- GOODBYE detection on accumulated eval_text ---
                        if not self.hangup_triggered and not self.waiting_definitive_cut and not self.hello_question_sent and self._matches_any_phrase(eval_text, self.words_data.get("cut_words", [])):
                            self.hanging_up = self.hangup_triggered = True
                            self.hangup_triggered_time = time.time()
                            self.hangup_source = "cut_words"
                            self.hangup_reason = "completed"
                            print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Goodbye detected in assistant text. Initiating clean call cut...{_R}")

                        # --- GOODBYE cancellation: only when the assistant is asking a question ---
                        if self.hanging_up and self.hangup_source == "cut_words":
                            cancel_phrases = self.words_data.get("cancel_goodbye_phrases", [])
                            has_goodbye = self._matches_any_phrase(eval_text, self.words_data.get("cut_words", []))
                            has_cancel  = self._matches_any_phrase(eval_text, cancel_phrases)
                            if has_cancel and not has_goodbye:
                                self.hanging_up = self.hangup_triggered = False
                                self.hangup_triggered_time = 0.0
                                self.hangup_source = ""
                                self._asst_chunk_buffer = ""
                                print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Cancel-goodbye phrase detected without goodbye word. Cancelling hangup...{_R}")

                        # --- HOLD activation: assistant puts call on hold ---
                        if not self.hanging_up and not self.on_hold and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", [])):
                            self.on_hold = True
                            self.current_wait_start = self.last_user_spoke_time = time.time()
                            self.last_speaker = None
                            if self.category_wait_seconds < 60.0:
                                self.log_system_message(
                                    f"{self.assistant_name} accepted short hold ({int(self.category_wait_seconds)}s). Sending time limit warning...", "⏳")
                                await session.send_realtime_input(
                                    text=self.prompts_data.get("hold_reminder", "").format(wait_seconds=int(self.category_wait_seconds)))
                            else:
                                self.log_system_message(
                                    f"{self.assistant_name} accepted hold. Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")

    # ==========================================
    # END OF CALL POST-PROCESSING LOGIC
    # ==========================================
    async def transcribe_file_whisper(self, wav_path: str) -> str:
        """Executes Whisper.cpp completely over the isolated audio file for maximum offline accuracy."""
        model_path = f"./models/ggml-{self.whisper_full_model}.bin"
        if not WHISPER_BIN or not os.path.exists(WHISPER_BIN) or not os.path.exists(model_path): return ""
        try:
            proc = await asyncio.create_subprocess_exec(WHISPER_BIN, "-l", self.current_lang.split("-")[0], "-t", "4", "-m", model_path, "-f", wav_path, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            if stdout: return clean_whisper_output(stdout.decode('utf-8', errors='ignore'))
        except Exception: pass
        return ""

    async def correct_transcript_with_whisper(self, raw_whisper: str) -> str:
        """Aligns the live transcription logs with the highly-accurate batch Whisper transcript."""
        prompt = (f"We have two transcriptions of a call:\n1. LIVE TRANSCRIPT (📞 correct, 🗣 may have noise).\n2. RAW WHISPER (🗣 only).\n"
                  f"Task: Align and correct 🗣 parts in LIVE TRANSCRIPT using RAW WHIPER. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
                  f"If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\nLIVE TRANSCRIPT:\n{self.accumulated_transcript}\n\nRAW WHIPER:\n{raw_whisper}")
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                resp = await asyncio.to_thread(self.client_text.models.generate_content, model=self.model_text, contents=prompt, config=types.GenerateContentConfig(temperature=0.1))
            return extract_response_text(resp, default=self.accumulated_transcript)
        except Exception: return self.accumulated_transcript

    async def correct_transcript_with_gemini_audio(self, wav_path: str, model_override: str = None) -> str:
        """Uploads the actual audio file to Gemini to execute the final transcription alignment."""
        try:
            model_to_use = model_override if model_override else self.model_text
            with open(wav_path, "rb") as f: audio_bytes = f.read()
            prompt = (f"Task: Align and correct 🗣 parts in LIVE TRANSCRIPT by listening to audio. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
                      f"If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\nLIVE TRANSCRIPT:\n{self.accumulated_transcript}")
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                resp = await asyncio.to_thread(self.client_text.models.generate_content, model=model_to_use, contents=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"), prompt], config=types.GenerateContentConfig(temperature=0.1))
            return extract_response_text(resp, default=self.accumulated_transcript)
        except Exception: return self.accumulated_transcript

    async def post_process_call(self) -> None:
        """Final cleanup execution. Merges audio channels, parses labels and tags, outputs result logic."""
        print(f"\n{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Saving recordings and evaluating categories...{_R}")
        
        # Consolida los buffers antes de escribir para evitar corrupciones
        caller_pcm_raw = b"".join(self.caller_recording_buffer) if self.caller_recording_buffer else b""
        asst_pcm_raw = bytes(self.recording_buffer_wav)
        
        if caller_pcm_raw:
            try:
                with wave.open(self.client_recording_path, 'wb') as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                    wf.writeframes(caller_pcm_raw)
            except Exception: pass
            
        if caller_pcm_raw and asst_pcm_raw:
            try:
                # Compensar si la IA tardó en contestar al principio
                if self.first_mic_time > 0 and self.call_start_time > 0:
                    mic_offset_bytes = int(max(0.0, self.first_mic_time - self.call_start_time) * 16000) * 2
                    if mic_offset_bytes > 0: 
                        caller_pcm_raw = (b"\x00" * mic_offset_bytes) + caller_pcm_raw
                
                caller_pcm = upsample_16k_to_24k(caller_pcm_raw)
                
                # Nivelar longitudes para el estéreo
                max_len = max(len(caller_pcm), len(asst_pcm_raw))
                if len(caller_pcm) < max_len: caller_pcm += b"\x00" * (max_len - len(caller_pcm))
                if len(asst_pcm_raw) < max_len: asst_pcm_raw += b"\x00" * (max_len - len(asst_pcm_raw))
                
                num_samples = max_len // 2
                c_samp = struct.unpack(f"<{num_samples}h", caller_pcm)
                a_samp = struct.unpack(f"<{num_samples}h", asst_pcm_raw)
                
                stereo_data = [val for pair in zip(c_samp, a_samp) for val in pair]
                with wave.open(self.recording_path, 'wb') as wf:
                    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(24000)
                    wf.writeframes(struct.pack(f"<{num_samples * 2}h", *stereo_data))
                print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[Audio] Call synchronized stereo recording saved: {self.recording_path}{_R}")
            except Exception as e: print(f"{_C_WARN}[{get_timestamp()}] Error mixing stereo audio: {e}{_R}")
        elif asst_pcm_raw:
            try:
                with wave.open(self.recording_path, 'wb') as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
                    wf.writeframes(asst_pcm_raw)
            except Exception: pass
            
        # Add a clear closing system message if one doesn't exist, correctly stating who hung up.
        if not getattr(self, "hangup_message_appended", False):
            self.hangup_message_appended = True
            if getattr(self, "hangup_triggered", False):
                lbl = self.words_data.get("call_spam", "❌ [SYSTEM]: Call automatically hung up due to network SPAM detection.") if getattr(self, "hangup_reason", "completed") == "spam" else self.words_data.get("call_finished", "❌ [SYSTEM]: Call successfully finished and saved.")
            else:
                lbl = self.words_data.get("call_finished", "❌ [SYSTEM]: Call disconnected by caller and saved.")
                
            clean_lbl = lbl.replace("❌ [SYSTEM]:", "").replace("❌", "").replace("[SYSTEM]:", "").replace("❌ [SISTEMA]:", "").replace("[SISTEMA]:", "").strip()
            self.accumulated_transcript += f"\n\n❌ [{get_timestamp()}]: [SYSTEM]: {clean_lbl}"
        
        final_trans = re.sub(r"\[SYSTEM\]:\s*.*?-\s*Call Connected\.", "[SYSTEM]: Call Connected.", self.accumulated_transcript)
        
        try: await asyncio.to_thread(self.execute_blocking_generate_content, final_trans)
        except Exception as e: print(f"{_C_ERR}[Post-Processing] Final state extraction failed: {e}{_R}")
        
        caller_type = self.last_call_json.get("caller_type", "unknown")
        max_spam_score = max(self.last_call_json.get("risk_score", 0), self.network_spam_score)
        
        if self.final_transcription_mode == "whisper_final" and os.path.exists(self.client_recording_path):
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Running Whisper.cpp on caller audio...{_R}")
            raw_whisper = await self.transcribe_file_whisper(self.client_recording_path)
            if raw_whisper:
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Aligning with {self.model_text}...{_R}")
                final_trans = await self.correct_transcript_with_whisper(raw_whisper)
        elif self.final_transcription_mode == "gemini_final" and os.path.exists(self.client_recording_path):
            if "gemma" in self.model_text.lower():
                print(f"{_C_WARN}[Post-Processing] Gemma models do not support native audio parsing. Falling back to gemini-3-flash-preview...{_R}")
                final_trans = await self.correct_transcript_with_gemini_audio(self.client_recording_path, model_override="gemini-3-flash-preview")
            else:
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Running {self.model_text} Audio alignment...{_R}")
                final_trans = await self.correct_transcript_with_gemini_audio(self.client_recording_path)
            
        if caller_type == "spam" or max_spam_score >= 65 or self.last_call_json.get("private_data_requested", False):
            final_tag = self.labels_data.get("spam", "SPAM")
        elif self.priority_call: final_tag = self.labels_data.get("priority", "PRIORITY")
        elif caller_type == "friend_family": final_tag = self.labels_data.get("personal", "PERSONAL")
        elif caller_type == "work": final_tag = self.labels_data.get("work", "WORK")
        elif caller_type == "commercial": final_tag = self.labels_data.get("spam", "SPAM")
        else: final_tag = self.labels_data.get("general", "GENERAL")
            
        client_n, comp_n = self.last_call_json.get("caller_name", ""), self.last_call_json.get("company", "")
        if client_n.lower() in ["unknown", "null", "none"]: client_n = ""
        if comp_n.lower() in ["unknown", "null", "none"]: comp_n = ""
            
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE calls SET tag=?, client_name=?, company=?, transcript=?, spam_score=? WHERE id=?", (final_tag, client_n, comp_n, final_trans, max_spam_score, self.call_id))
        conn.commit(); conn.close()
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Post-Processing] Complete. Tagged as: {final_tag}{_R}")

    async def run(self) -> None:
        """Entry point. Initializes instructions and triggers the execution loops for the ongoing call."""
        conn = sqlite3.connect(DB_PATH)
        contact = conn.execute("SELECT type, prompt_rules FROM contacts WHERE number=?", (self.caller_number,)).fetchone()
        last_rec = conn.execute("SELECT transcript, date FROM calls WHERE number=? ORDER BY id DESC LIMIT 1", (self.caller_number,)).fetchone()
        conn.close()

        if contact and contact[0] == "blacklist":
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Blacklist] {self.caller_number} blocked. Rejecting.{_R}")
            self.hangup_call(); return

        self.create_call_record_db()
        self.running = True
        self.answered_call = False
        self.recording_buffer_wav = bytearray()
        self.caller_recording_buffer = []

        delay = int(get_config("wait_seconds", "0"))
        if delay > 0 and self.running:
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Delay] Waiting {delay}s before answering...{_R}")
            for _ in range(delay * 10):
                if not self.running: break
                await asyncio.sleep(0.1)

        if not self.running:
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Delay] Call aborted by caller before answering.{_R}"); return

        raw_instruction = self.assistant_data.get("system_instruction", "")
        try:
            instruction = raw_instruction.format(
                assistant_name=self.assistant_name, 
                role_assistant=self.assistant_data.get("role_mappings", {}).get("female" if "fem" in self.assistant_gender.lower() else "male", "Secretary"),
                owner_desc=self.assistant_data.get("owner_type_mappings", {}).get(self.owner_type, "Private"), 
                boss_name=self.boss_name, business_details=self.business_description
            )
        except (KeyError, ValueError):
            instruction = raw_instruction

        if last_rec and self.gui_data.get("ui_in_progress", "IN PROGRESS") not in last_rec[0] and "IN PROGRESS" not in last_rec[0]:
            try: instruction += self.assistant_data.get("history_injection", "").format(date_str=last_rec[1], last_transcript=last_rec[0])
            except Exception: pass

        instruction += self.assistant_data.get("system_date", "\nDATE: {today_str}").format(today_str=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        if contact and contact[1]: instruction += self.assistant_data.get("custom_contact_rule", "\nRule: {rule}").format(rule=contact[1])

        extra_prompt = get_config("extra_prompt", "")
        if extra_prompt: instruction += f"\n\nEXTRA INSTRUCTIONS/PERSONALITY:\n{extra_prompt}"

        tools_list = [types.Tool(function_declarations=[
            types.FunctionDeclaration(name="hangup", description="Terminates the call immediately if spam or successfully finished.", parameters_json_schema={"type": "object", "properties": {"reason": {"type": "string"}}}),
            types.FunctionDeclaration(name="save_message", description="MANDATORY: Execute this tool to save ANY actionable message, task, delivery notice, or completed appointment details for the owner. Do not say it is noted without invoking this tool.", parameters_json_schema={"type": "object", "properties": {"caller_name": {"type": "string"}, "message_text": {"type": "string"}}, "required": ["caller_name", "message_text"]})
        ])]

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"], system_instruction=types.Content(parts=[types.Part(text=instruction)]), tools=tools_list,
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede" if "fem" in self.assistant_gender.lower() else "Puck"))),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    prefix_padding_ms=200,
                    silence_duration_ms=500,
                )
            )
        )

        spam_task = asyncio.create_task(self.check_network_spam())
        asyncio.create_task(self.monitor_routing_manager())

        try:
            async with self.client_live.aio.live.connect(model=MODEL_LIVE, config=config) as session:
                self.answer_call()
                self.answered_call = True
                self.call_start_time = time.time()
                
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Bluetooth] Stabilizing audio channel...{_R}")
                await asyncio.sleep(0.5)
                await self.enforce_bluetooth_call_profile()
                await asyncio.sleep(1.5)

                ready_in, resolved_in = await self.wait_for_pw_node(self.pw_record_target, timeout=12.0)
                ready_out, resolved_out = await self.wait_for_pw_node(self.pw_playback_target, timeout=12.0)
                self.pw_record_target, self.pw_playback_target = resolved_in, resolved_out

                if self.running and ready_in and ready_out:
                    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[PipeWire] Nodes ready. Isolating channels...{_R}")
                    try:
                        await asyncio.create_subprocess_exec("pactl", "set-source-mute", resolved_in, "false", stderr=asyncio.subprocess.DEVNULL)
                        await asyncio.create_subprocess_exec("pactl", "set-source-mute", resolved_out, "false", stderr=asyncio.subprocess.DEVNULL)
                        print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[PipeWire] Channels unmuted.")
                    except Exception: pass
                    await asyncio.sleep(1.0)
                elif not self.running:
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[PipeWire] Call aborted during initialization.{_R}"); return
                else: print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[PipeWire] Timeout waiting for audio nodes. Audio may fail.{_R}")

                async def monitor_spam() -> None:
                    while self.running:
                        if spam_task.done():
                            try:
                                if spam_task.result() and get_config("auto_block_spam", "false") == "true":
                                    print(f"\n{_C_WARN}[{get_timestamp()}] [SpamCheck] SPAM confirmed. Terminating call (Auto-Block ON)...{_R}")
                                    self.hangup_reason = "spam"
                                    self.hangup_triggered = True
                                    self.accumulated_transcript += "\n\n❌ [SYSTEM]: Call hung up — network SPAM detected."
                                    self.update_transcription_db()
                                    await session.send_realtime_input(text=self.prompts_data.get("spam_detected", ""))
                                    await asyncio.sleep(4)
                                    self.hangup_call()
                                    self.running = False
                                    break
                            except Exception: pass
                            break
                        await asyncio.sleep(0.5)

                await asyncio.gather(self.send_mic_audio(session), self.receive_audio_and_tools(session), monitor_spam())
                
        except Exception as e:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Session] Unexpected error: {e}{_R}")
            if not getattr(self, "answered_call", False): print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[AI Engine] Gemini Live is unavailable. Delegating call to native phone handler.{_R}")
        finally:
            self.running = False
            if getattr(self, "answered_call", False):
                self.hangup_call()

def run_dbus_loop(main_loop: asyncio.AbstractEventLoop) -> None:
    """Listens for CallAdded and CallRemoved events over D-Bus from oFono."""
    global ACTIVE_ASSISTANT
    def on_call_added(path: str, properties: dict) -> None:
        global ACTIVE_ASSISTANT, ACTIVE_TASKS
        if properties.get("State") != "incoming": return
        number = properties.get("LineIdentification", "Unknown")
        print(f"\n{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[D-Bus] Incoming call from: {number}{_R}")
        assistant = PhoneAssistant(dbus_path=path, caller_number=number)
        ACTIVE_ASSISTANT = assistant
        future = asyncio.run_coroutine_threadsafe(assistant.run(), main_loop)
        ACTIVE_TASKS.add(future)
        future.add_done_callback(ACTIVE_TASKS.discard)

    def on_call_removed(path: str) -> None:
        global ACTIVE_ASSISTANT
        if ACTIVE_ASSISTANT and ACTIVE_ASSISTANT.dbus_path == path:
            print(f"\n{_C_WARN}[{get_timestamp()}] [D-Bus] Call hung up.{_R}")
            ACTIVE_ASSISTANT.running = False
            # Execute post-processing HERE. Guarantees 100% execution when line drops.
            if not getattr(ACTIVE_ASSISTANT, "_post_processed", False):
                ACTIVE_ASSISTANT._post_processed = True
                asyncio.run_coroutine_threadsafe(ACTIVE_ASSISTANT.post_process_call(), main_loop)

    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        bus.add_signal_receiver(on_call_added, dbus_interface="org.ofono.VoiceCallManager", signal_name="CallAdded")
        bus.add_signal_receiver(on_call_removed, dbus_interface="org.ofono.VoiceCallManager", signal_name="CallRemoved")
        GLib.MainLoop().run()
    except Exception as e: print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}Error in D-Bus listener: {e}{_R}")

if __name__ == "__main__":
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    if not API_KEY:
        print(f"{_C_ERR}{ICON_ERR}Error: GEMINI_API_KEY environment variable not set.{_R}")
        sys.exit(1)

    ensure_database_exists()
    ensure_system_dependencies()

    initialize_ofono_modems()
    initialize_bluez_devices()
    
    print(f"{_C_SERVER}{ICON_SERVER}Synchronizing audio subsystem with oFono...{_R}")
    try:
        subprocess.run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"], check=True, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
    except Exception as e: print(f"{_C_WARN}{ICON_WARN}Warning: Could not restart audio services: {e}{_R}")

    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    dbus_thread = threading.Thread(target=run_dbus_loop, args=(main_loop,), daemon=True)
    dbus_thread.start()

    print(f"{_C_SERVER}{ICON_SERVER}--- BLUETOOTH AI SWITCHBOARD ---{_R}")
    print(f"Waiting for incoming calls via oFono...\n")

    try: 
        main_loop.run_forever()
    except KeyboardInterrupt: 
        print(f"\n{_C_WARN}{ICON_WARN}Switchboard manually stopped.{_R}")
        os._exit(0)
