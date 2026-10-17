#!/usr/bin/env python3
"""
AI Switchboard Assistant - Intelligent phone handler utilizing Gemini 3.8 Live and Bluetooth HFP.
Detects incoming calls via D-Bus/oFono, manages audio routing through PipeWire, normalizes
caller numbers & wildcards, caches SPAM lookups, stores structured caller messages and AI
summaries, and interacts in real time.

Author: Antonio R.
Version: 2.0
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

https://github.com/antor44/AI-Bluetooth-Phone-Assistant
"""

import os
import sys
import json
import asyncio
import re
import fnmatch
import sqlite3
import time
import wave
import struct
import math
import subprocess
import shutil
import urllib.parse
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
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter
from google import genai
from google.genai import types

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "switchboard.db")
LANG_DIR = os.path.join(BASE_DIR, "languages")


def find_whisper_bin() -> str:
    """Dynamically searches for the Whisper executable across common build paths."""
    paths_to_check = [
        shutil.which("whisper-cli"),
        shutil.which("main"),
        os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli"),
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
    except Exception:
        return ""


MODEL_LIVE = "gemini-3.8-live"
API_KEY = os.environ.get("GEMINI_API_KEY")

DEFAULT_PW_INPUT  = "bluez_input.00_00_00_00_00_00.0"
DEFAULT_PW_OUTPUT = "bluez_output.00_00_00_00_00_00.1"

ACTIVE_ASSISTANT = None
ACTIVE_TASKS = set()
GLIB_LOOP = None

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "caller_type":            {"type": "string", "enum": ["friend_family", "work", "spam", "commercial", "unknown"]},
        "risk_score":             {"type": "integer", "minimum": 0, "maximum": 100},
        "insult_detected":        {"type": "boolean"},
        "private_data_requested": {"type": "boolean"},
        "caller_name":            {"type": "string"},
        "company":                {"type": "string"},
        "summary":                {"type": "string"},
        "response_text":          {"type": "string"}
    },
    "required": ["caller_type", "risk_score", "insult_detected", "private_data_requested", "summary", "response_text"]
}


def normalize_phone_candidates(raw_number: str) -> Tuple[str, str, List[str]]:
    """Normalizes an incoming phone number into digits_only, 9-digit national, and matching candidates."""
    digits = re.sub(r"\D", "", raw_number or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("34") and len(digits) == 11:
        national = digits[2:]
    elif len(digits) > 9:
        national = digits[-9:]
    else:
        national = digits

    candidates = []
    for item in [national, digits, (raw_number or "").strip()]:
        if item and item not in candidates:
            candidates.append(item)
    return digits, national, candidates


def normalize_contact_pattern(pattern: str) -> str:
    """Normalizes a stored contact number or wildcard pattern."""
    cleaned = re.sub(r"[^\d\*\?\+]", "", (pattern or "").strip())
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not any(w in cleaned for w in ("*", "?")) and cleaned.startswith("34") and len(cleaned) == 11:
        cleaned = cleaned[2:]
    return cleaned


def match_contact_rule(caller_number: str) -> Optional[Dict[str, str]]:
    """Matches caller_number against contacts (Exact match first, most specific wildcard second)."""
    _, _, caller_candidates = normalize_phone_candidates(caller_number)
    if not caller_candidates:
        return None

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT number, type, prompt_rules, tag, note FROM contacts").fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    exact_matches = []
    wildcard_matches = []

    for row in rows:
        pat_raw, c_type, prompt_rules, tag, note = row
        pat_norm = normalize_contact_pattern(pat_raw)
        if not pat_norm:
            continue

        entry = {
            "pattern": pat_raw,
            "normalized_pattern": pat_norm,
            "type": c_type or "whitelist",
            "prompt_rules": prompt_rules or "",
            "tag": tag or "",
            "note": note or ""
        }

        if any(w in pat_norm for w in ("*", "?")):
            for cand in caller_candidates:
                if fnmatch.fnmatchcase(cand, pat_norm):
                    literal_len = len(re.sub(r"[\*\?]", "", pat_norm))
                    wildcard_matches.append((literal_len, len(pat_norm), entry))
                    break
        else:
            if pat_norm in caller_candidates or pat_raw.strip() in caller_candidates:
                exact_matches.append(entry)

    if exact_matches:
        return exact_matches[0]

    if wildcard_matches:
        wildcard_matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return wildcard_matches[0][2]

    return None


def format_spam_url(url_template: str, raw_number: str) -> str:
    """Formats a SPAM lookup URL supporting {number}, {national}, and {e164} without duplicate prefixes."""
    digits, national, _ = normalize_phone_candidates(raw_number)
    e164 = f"+34{national}" if len(national) == 9 and (digits.startswith("34") or len(digits) == 9) else f"+{digits}"

    url = url_template
    if "%2B34{number}" in url or "+34{number}" in url:
        url = url.replace("{number}", national)
    else:
        url = url.replace("{number}", digits)
    url = url.replace("{national}", national)
    url = url.replace("{e164}", e164)
    return url


def clean_html_for_spam(raw_html: str) -> str:
    """Extracts page title and strips script, style, header, nav, select, footer, and HTML tags."""
    if not raw_html:
        return ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.DOTALL | re.IGNORECASE)
    title_text = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    text = re.sub(r"<!--.*?-->", " ", raw_html, flags=re.DOTALL)
    text = re.sub(
        r"<(script|style|noscript|svg|head|header|nav|footer|select|datalist|aside|form|iframe)\b[^>]*>.*?</\1>",
        " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{title_text} — {text}".strip(" —") if title_text else text


async def fetch_spam_page_async(url: str, http_session: aiohttp.ClientSession) -> Tuple[int, str]:
    """Fetches a SPAM lookup page using curl_cffi (Chrome TLS), aiohttp, or system curl with browser headers."""
    parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else "https://www.google.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": origin,
        "Upgrade-Insecure-Requests": "1"
    }

    if curl_requests is not None:
        try:
            resp = await asyncio.to_thread(
                curl_requests.get, url, headers=headers, impersonate="chrome", timeout=5
            )
            if resp.status_code == 200 and resp.text:
                return resp.status_code, resp.text
        except Exception:
            pass

    if shutil.which("curl"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-sL", "--max-time", "5",
                "-w", "\n__HTTP_STATUS__:%{http_code}",
                "-A", headers["User-Agent"],
                "-H", f"Accept: {headers['Accept']}",
                "-H", f"Accept-Language: {headers['Accept-Language']}",
                "-H", f"Referer: {headers['Referer']}",
                url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            out_str = stdout.decode("utf-8", errors="ignore")
            if "__HTTP_STATUS__:" in out_str:
                body, status_part = out_str.rsplit("__HTTP_STATUS__:", 1)
                status_code = int(status_part.strip() or "0")
                if status_code == 200 and body:
                    return status_code, body
        except Exception:
            pass

    async with http_session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4.5)) as resp:
        return resp.status, await resp.text()


def apply_language_defaults(lang_code: str) -> None:
    """Applies default localized settings to the database if missing."""
    path = os.path.join(LANG_DIR, lang_code, "gui.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                gui_data = json.load(f)
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
                    if default_warning:
                        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_greeting_key, default_warning))
                conn.commit()
                conn.close()
        except Exception:
            pass


def ensure_database_exists() -> None:
    """Ensures that the SQLite database, tables, and v2.0 schema migrations are applied."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS calls 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, date TEXT, duration INT, 
                  spam_score INT, transcript TEXT, audio_path TEXT, client_audio_path TEXT, 
                  tag TEXT, client_name TEXT, company TEXT, summary TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts 
                 (number TEXT PRIMARY KEY, type TEXT, prompt_rules TEXT,
                  tag TEXT DEFAULT '', note TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER, number TEXT,
                  date TEXT, time TEXT, caller_name TEXT, message_text TEXT,
                  is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS spam_cache 
                 (number TEXT PRIMARY KEY, is_spam INTEGER, risk_score INTEGER,
                  reason TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')

    for alter_sql in [
        "ALTER TABLE calls ADD COLUMN summary TEXT DEFAULT ''",
        "ALTER TABLE contacts ADD COLUMN tag TEXT DEFAULT ''",
        "ALTER TABLE contacts ADD COLUMN note TEXT DEFAULT ''"
    ]:
        try:
            c.execute(alter_sql)
        except sqlite3.OperationalError:
            pass

    c.execute("INSERT OR IGNORE INTO settings VALUES ('wait_seconds', '5')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('auto_block_spam', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('spam_cache_days', '7')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_model', 'medium')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_quant', '')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('software_echo_suppression', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('final_transcription_mode', 'disabled')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('monitor_mode', 'none')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('language', 'en-US')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('allow_pc_mic', 'false')")

    c.execute("INSERT OR IGNORE INTO settings VALUES ('memory_mode', 'per_number')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('memory_max_calls', '1')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('memory_max_days', '30')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('memory_max_chars', '2500')")

    c.execute("INSERT OR IGNORE INTO settings VALUES ('daemon_state', 'running')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('daemon_heartbeat', '0')")

    c.execute("INSERT OR IGNORE INTO settings VALUES ('caller_gain', '1.5')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('noise_gate_base', '50')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_start_sensitivity', 'LOW')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_end_sensitivity', 'HIGH')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_prefix_padding_ms', '500')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_silence_duration_ms', '500')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('protect_initial_greeting', 'true')")

    c.execute("INSERT OR REPLACE INTO settings VALUES ('daemon_state', 'running')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('daemon_heartbeat', ?)", (str(time.time()),))

    conn.commit()
    conn.close()

    try:
        conn = sqlite3.connect(DB_PATH)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else "en-US"
        res_asst = conn.execute("SELECT value FROM settings WHERE key=?", (f"{current_lang}_assistant_name",)).fetchone()
        conn.close()
        if res_asst is None:
            apply_language_defaults(current_lang)
    except Exception:
        pass


def ensure_system_dependencies() -> None:
    """Checks and applies necessary WirePlumber and oFono configurations for Bluetooth routing."""
    print(f"{_C_SERVER}{ICON_INFO}Checking system configurations...{_R}")
    home_dir = os.path.expanduser("~")

    wp4_dir = os.path.join(home_dir, ".config", "wireplumber", "bluetooth.lua.d")
    wp4_file = os.path.join(wp4_dir, "50-bluez-config.lua")
    wp4_content = """bluez_monitor.properties = {
  ["with-logind"]             = false,
  ["bluez5.enable-sbc-xq"]    = true,
  ["bluez5.enable-msbc"]      = true,
  ["bluez5.enable-hw-volume"] = true,
  ["bluez5.headset-roles"]    = "[ hsp_hs hsp_ag hfp_hf hfp_ag ]",
  ["bluez5.hfphsp-backend"]   = "ofono"
}"""

    wp5_dir = os.path.join(home_dir, ".config", "wireplumber", "wireplumber.conf.d")
    wp5_file = os.path.join(wp5_dir, "50-bluez-config.conf")
    wp5_content = """wireplumber.profiles = {
  main = {
    monitor.bluez.seat-monitoring = disabled
  }
}

monitor.bluez.properties = {
  bluez5.enable-sbc-xq    = true
  bluez5.enable-msbc      = true
  bluez5.enable-hw-volume = true
  bluez5.roles            = [ a2dp_sink a2dp_source hsp_hs hsp_ag hfp_hf hfp_ag ]
  bluez5.hfphsp-backend   = "ofono"
}"""

    wp_alsa_dir = os.path.join(home_dir, ".config", "wireplumber", "main.lua.d")
    wp_alsa_file = os.path.join(wp_alsa_dir, "51-disable-onboard-alsa.lua")
    wp_alsa_content = """if alsa_monitor and alsa_monitor.rules then
  table.insert(alsa_monitor.rules, {
    matches = {
      {
        { "device.name", "matches", "alsa_card.platform-*" },
      },
    },
    apply_properties = {
      ["device.disabled"] = true,
    },
  })
end"""

    config_changed = False
    for wp_dir, wp_file, content in [
        (wp4_dir, wp4_file, wp4_content),
        (wp5_dir, wp5_file, wp5_content),
        (wp_alsa_dir, wp_alsa_file, wp_alsa_content)
    ]:
        os.makedirs(wp_dir, exist_ok=True)
        needs_write = True
        if os.path.exists(wp_file):
            with open(wp_file, "r") as f:
                needs_write = (f.read().strip() != content.strip())
        if needs_write:
            with open(wp_file, "w") as f:
                f.write(content)
            config_changed = True

    for extra_lua in ["51-no-autolink.lua", "52-headless-fix.lua"]:
        extra_path = os.path.join(wp4_dir, extra_lua)
        if os.path.exists(extra_path):
            os.remove(extra_path)
            config_changed = True

    if config_changed:
        print(f"{_C_SERVER}{ICON_OK}WirePlumber configurations applied.{_R}")

    systemd_dir = os.path.join(home_dir, ".config", "systemd", "user")
    null_sink_file = os.path.join(systemd_dir, "null-sink.service")
    null_sink_content = """[Unit]
Description=PipeWire Null Sink for AI Switchboard
After=pipewire-pulse.service
Requires=pipewire-pulse.service
PartOf=pipewire-pulse.service

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
        with open(null_sink_file, "w") as f:
            f.write(null_sink_content)
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
            subprocess.run(
                ["pactl", "load-module", "module-null-sink", "sink_name=auto_null", "sink_properties=device.description=NullSink"],
                capture_output=True
            )
    except Exception:
        pass


def initialize_ofono_modems(retries: int = 3) -> None:
    """Connects to the oFono D-Bus interface and powers on all available modems (phones)."""
    for attempt in range(retries):
        try:
            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object("org.ofono", "/"), "org.ofono.Manager")
            modems = manager.GetModems()

            if not modems:
                if attempt < retries - 1:
                    time.sleep(3.0)
                    continue
                print(f"{_C_WARN}{ICON_WARN}oFono: no modems found. Ensure your phone is connected via Bluetooth.{_R}")
                return

            all_ready = True
            for path, props in modems:
                modem = dbus.Interface(bus.get_object("org.ofono", path), "org.ofono.Modem")
                try:
                    if not props.get("Powered", False):
                        modem.SetProperty("Powered", dbus.Boolean(True))
                    if not props.get("Online", False):
                        modem.SetProperty("Online", dbus.Boolean(True))
                    print(f"{_C_SERVER}{ICON_OK}oFono modem ready: {path}{_R}")
                except Exception as e:
                    all_ready = False
                    if attempt == retries - 1:
                        print(f"{_C_ERR}{ICON_ERR}oFono error on {path}: {e}{_R}")

            if all_ready:
                return
            if attempt < retries - 1:
                time.sleep(3.0)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3.0)
            else:
                print(f"{_C_ERR}{ICON_ERR}oFono initialization error: {e}{_R}")


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
    except Exception as e:
        print(f"{_C_WARN}{ICON_WARN}BlueZ trust error: {e}{_R}")


def get_timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def get_config(key: str, default_value: str) -> str:
    """Retrieves a configuration value from the SQLite settings table, handling localized keys."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else "en-US"

        localized_keys = [
            "boss_name", "assistant_name", "assistant_gender", "owner_type",
            "priority_keywords", "memory_rules", "business_description",
            "expected_calls", "initial_greeting", "extra_prompt", "text_model"
        ]
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
    path = os.path.join(LANG_DIR, lang_code, file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def calculate_rms(data_pcm: bytes) -> float:
    count = len(data_pcm) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"<{count}h", data_pcm)
    return math.sqrt(sum(s * s for s in shorts) / count)


def upsample_16k_to_24k(data_16k: bytes) -> bytes:
    num_samples = len(data_16k) // 2
    if num_samples < 2:
        return b""
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
    lines = stdout_str.replace("\r", "\n").split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*", "", line)
        line = re.sub(r"\[[^\]]*\]", "", line)
        line = re.sub(r"[<>^*_]", "", line).strip()
        if line:
            cleaned.append(line)
    return " ".join(cleaned)


def clean_ai_text(text: str) -> str:
    t = re.sub(r"start\s*\{.*?\}\s*endcall", "", text, flags=re.IGNORECASE)
    t = re.sub(r"start\s*\{.*?\}", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\{.*?\}", "", t)
    return re.sub(r"\b(call:hangup|hangup|call|endcall|start)\b", "", t, flags=re.IGNORECASE)


def clean_transcript_for_memory(raw_transcript: str) -> str:
    if not raw_transcript:
        return ""
    blocks = [b.strip() for b in raw_transcript.split("\n\n") if b.strip()]
    dialogue_lines = []
    for block in blocks:
        if any(marker in block for marker in ["[SYSTEM]", "[Active Hold]", "❌", "⏳", "⏸", "[Noise Filtered]"]):
            if not block.startswith("📝"):
                continue
        dialogue_lines.append(block)
    return "\n".join(dialogue_lines).strip()


def clean_json_text(raw_text: str) -> str:
    if not raw_text or not str(raw_text).strip():
        return "{}"
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
    return m.group(0).strip() if m else "{}"


def extract_response_text(response, default: str = "{}") -> str:
    try:
        for p in response.candidates[0].content.parts:
            if getattr(p, "text", None) and p.text.strip():
                return p.text.strip()
    except Exception:
        pass
    try:
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception:
        pass
    return default


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
            if call_json.get("private_data_requested"):
                return PolicyDecision("deny", "Attempting to retrieve private data")
            return PolicyDecision("allow", "Message saved safely", args)

        return PolicyDecision("confirm", "Requires user confirmation", args)


class PhoneAssistant:
    """Main class that handles a single active Bluetooth phone call via Gemini 3.8 Live."""
    def __init__(self, dbus_path: str, caller_number: str):
        self.dbus_path = dbus_path
        self.caller_number = caller_number
        self.digits_number, self.national_number, self.caller_candidates = normalize_phone_candidates(caller_number)
        self.running = False
        self._post_processed = False

        self.boss_name = get_config("boss_name", "Boss")
        self.owner_type = get_config("owner_type", "private")
        self.business_description = get_config("business_description", "")
        self.expected_calls = get_config("expected_calls", "")
        self.assistant_name = get_config("assistant_name", "Assistant")
        self.assistant_gender = get_config("assistant_gender", "female")
        self.current_lang = get_config("language", "en-US")

        mac_match = re.search(r"dev_([0-9A-Z_]+)", dbus_path)
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
        self.recent_asst_phrases: List[Tuple[str, float, str]] = []

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

        self.software_echo_suppression = get_config("software_echo_suppression", "false") == "true"
        self.protect_initial_greeting = get_config("protect_initial_greeting", "true") == "true"
        self.greeting_in_progress = False
        self.greeting_started_time = 0.0
        self.greeting_audio_received = False

        try:
            self.caller_gain = float(get_config("caller_gain", "1.5"))
        except ValueError:
            self.caller_gain = 1.5
        try:
            self.noise_gate_base = int(get_config("noise_gate_base", "50"))
        except ValueError:
            self.noise_gate_base = 50

        self.vad_start_sens = get_config("vad_start_sensitivity", "LOW")
        self.vad_end_sens = get_config("vad_end_sensitivity", "HIGH")
        try:
            self.vad_prefix_padding_ms = int(get_config("vad_prefix_padding_ms", "500"))
        except ValueError:
            self.vad_prefix_padding_ms = 500
        try:
            self.vad_silence_duration_ms = int(get_config("vad_silence_duration_ms", "500"))
        except ValueError:
            self.vad_silence_duration_ms = 500

        self.final_transcription_mode = get_config("final_transcription_mode", "disabled")

        w_model = get_config("whisper_model", "medium")
        w_quant = get_config("whisper_quant", "")
        self.whisper_full_model = f"{w_model}{w_quant}"

        self.model_text = get_config("text_model", "gemini-3-flash-preview")

        recordings_dir = os.path.join(BASE_DIR, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_path = os.path.join(recordings_dir, f"call_{self.national_number or caller_number}_{ts_str}.wav")
        self.client_recording_path = os.path.join(recordings_dir, f"call_{self.national_number or caller_number}_{ts_str}_client.wav")

        self.client_text = genai.Client(api_key=API_KEY)
        self.client_live = genai.Client(api_key=API_KEY, http_options={"api_version": "v1alpha"})

        self.last_call_json = {
            "caller_type": "unknown", "risk_score": 0, "insult_detected": False,
            "private_data_requested": False, "caller_name": "", "company": "",
            "summary": "", "response_text": ""
        }

    def build_memory_context(self, contact_match: Optional[Dict[str, str]]) -> str:
        """Builds historical call context according to the selected memory_mode."""
        memory_mode = get_config("memory_mode", "per_number")
        if memory_mode == "disabled":
            return ""

        try:
            max_calls = max(1, int(get_config("memory_max_calls", "1")))
        except ValueError:
            max_calls = 1
        try:
            max_days = max(1, int(get_config("memory_max_days", "30")))
        except ValueError:
            max_days = 30
        try:
            max_chars = max(300, int(get_config("memory_max_chars", "2500")))
        except ValueError:
            max_chars = 2500

        in_progress_lbl = self.gui_data.get("ui_in_progress", "IN PROGRESS")
        spam_lbl = self.labels_data.get("spam", "SPAM")

        conn = sqlite3.connect(DB_PATH)
        rows = []
        try:
            placeholders = ",".join(["?"] * len(self.caller_candidates)) if self.caller_candidates else "'__none__'"

            if memory_mode == "per_number" and self.caller_candidates:
                cutoff_str = (datetime.datetime.now() - datetime.timedelta(days=max_days)).strftime("%Y-%m-%d %H:%M:%S")
                query = (
                    f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                    f"WHERE id != ? AND number IN ({placeholders}) AND date >= ? "
                    f"ORDER BY id DESC LIMIT ?"
                )
                params = [self.call_id or -1] + self.caller_candidates + [cutoff_str, max_calls]
                rows = conn.execute(query, params).fetchall()

            elif memory_mode == "per_category":
                target_tag = (contact_match or {}).get("tag", "").strip()
                if not target_tag and self.caller_candidates:
                    prev_tag_row = conn.execute(
                        f"SELECT tag FROM calls WHERE id != ? AND number IN ({placeholders}) AND tag != ? AND tag != 'IN PROGRESS' ORDER BY id DESC LIMIT 1",
                        [self.call_id or -1] + self.caller_candidates + [in_progress_lbl]
                    ).fetchone()
                    if prev_tag_row and prev_tag_row[0]:
                        target_tag = prev_tag_row[0]

                try:
                    mem_rules = json.loads(get_config("memory_rules", "[]"))
                    for rule in mem_rules:
                        cat_name = rule.get("category", "").lower()
                        if cat_name and (cat_name in target_tag.lower() or any(kw in target_tag.lower() for kw in rule.get("keywords", []))):
                            max_days = int(rule.get("days", max_days))
                            break
                except Exception:
                    pass

                cutoff_str = (datetime.datetime.now() - datetime.timedelta(days=max_days)).strftime("%Y-%m-%d %H:%M:%S")
                if target_tag:
                    rows = conn.execute(
                        "SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                        "WHERE id != ? AND tag = ? AND date >= ? ORDER BY id DESC LIMIT ?",
                        (self.call_id or -1, target_tag, cutoff_str, max_calls)
                    ).fetchall()
                elif self.caller_candidates:
                    query = (
                        f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                        f"WHERE id != ? AND number IN ({placeholders}) AND date >= ? "
                        f"ORDER BY id DESC LIMIT ?"
                    )
                    rows = conn.execute(query, [self.call_id or -1] + self.caller_candidates + [cutoff_str, max_calls]).fetchall()

            elif memory_mode == "global":
                cutoff_str = (datetime.datetime.now() - datetime.timedelta(days=max_days)).strftime("%Y-%m-%d %H:%M:%S")
                rows = conn.execute(
                    "SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                    "WHERE id != ? AND date >= ? AND spam_score < 65 AND tag != ? AND tag NOT LIKE '%SPAM%' "
                    "ORDER BY id DESC LIMIT ?",
                    (self.call_id or -1, cutoff_str, spam_lbl, max_calls)
                ).fetchall()
        except Exception as e:
            print(f"{_C_WARN}[Memory] Query warning: {e}{_R}")
        finally:
            conn.close()

        if not rows:
            return ""

        entries = []
        total_chars = 0
        for idx, r in enumerate(rows):
            c_date, c_num, c_name, c_comp, c_tag, c_sum, c_trans = r
            if not c_trans or in_progress_lbl in c_trans or "IN PROGRESS" in c_trans:
                continue

            cleaned_dialogue = clean_transcript_for_memory(c_trans)
            if idx == 0 and len(cleaned_dialogue) <= 350 and cleaned_dialogue:
                content_body = cleaned_dialogue
            elif c_sum and c_sum.strip():
                content_body = c_sum.strip()
            else:
                content_body = cleaned_dialogue[:450] + ("..." if len(cleaned_dialogue) > 450 else "")

            if not content_body:
                continue

            who_parts = [p for p in [c_name, c_comp, c_num] if p]
            who_str = " / ".join(who_parts) if who_parts else c_num
            entry_text = f"- [{c_date}] ({who_str} | {c_tag}): {content_body}"

            if total_chars + len(entry_text) > max_chars:
                break
            entries.append(entry_text)
            total_chars += len(entry_text)

        if not entries:
            return ""

        joined_entries = "\n".join(entries)
        template = self.assistant_data.get(
            "history_injection",
            "\n[PAST HISTORY — READ ONLY IF CALLER EXPLICITLY REFERS TO IT]:\n{last_transcript}"
        )
        try:
            return template.format(date_str=rows[0][0], last_transcript=joined_entries)
        except Exception:
            return f"\n[PAST CALL MEMORY]:\n{joined_entries}\n"

    async def check_network_spam(self, is_whitelisted: bool = False) -> bool:
        """Asynchronously queries external spam databases with SQLite caching and curl_cffi/curl support."""
        if is_whitelisted:
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[SpamCheck] Caller is whitelisted. Skipping SPAM verification.{_R}")
            return False

        if not self.digits_number:
            return False

        cache_key = self.national_number or self.digits_number
        try:
            cache_days = int(get_config("spam_cache_days", "7"))
        except ValueError:
            cache_days = 7

        if cache_days > 0:
            conn = sqlite3.connect(DB_PATH)
            cached = conn.execute(
                "SELECT is_spam, risk_score, reason, updated_at FROM spam_cache WHERE number=?",
                (cache_key,)
            ).fetchone()
            conn.close()
            if cached:
                is_sp, r_score, reason, upd_at = cached
                try:
                    dt_upd = datetime.datetime.strptime(upd_at, "%Y-%m-%d %H:%M:%S")
                    if (datetime.datetime.now() - dt_upd).days < cache_days:
                        self.network_spam_score = int(r_score or 0)
                        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[SpamCheck] Cache hit for {cache_key}: SPAM={bool(is_sp)} (Score: {self.network_spam_score}) — {reason}{_R}")
                        return bool(is_sp)
                except Exception:
                    pass

        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[SpamCheck] AI evaluating {self.caller_number} (National: {self.national_number}) across databases...{_R}")

        providers_json = get_config("spam_providers", "")
        try:
            providers = json.loads(providers_json) if providers_json else load_language_data(self.current_lang, "spam.json").get("providers", [])
        except Exception:
            providers = []

        schema = {
            "type": "object",
            "properties": {"is_spam": {"type": "boolean"}, "risk_score": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["is_spam", "risk_score"]
        }

        highest_score = 0
        best_reason = "No negative reports found"

        async with aiohttp.ClientSession() as http_session:
            for url_template in providers:
                url = format_spam_url(url_template, self.caller_number)
                try:
                    status_code, html = await fetch_spam_page_async(url, http_session)
                    if status_code != 200:
                        print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[SpamCheck] HTTP {status_code} from {url}{_R}")
                        continue

                    clean_text = clean_html_for_spam(html)[:15000]
                    if len(clean_text) < 50:
                        print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[SpamCheck] Empty/JS-blocked response ({len(clean_text)} chars) from {url}{_R}")
                        continue

                    is_gemma = "gemma" in self.model_text.lower()
                    if is_gemma:
                        prompt = (
                            f"Analyze user comments from a spam-lookup website for number {self.national_number} and output a JSON object.\n\n"
                            f"SCHEMA:\n{{\"is_spam\": boolean, \"risk_score\": integer, \"reason\": string}}\n\n"
                            f"TEXT:\n{clean_text}\n\nJSON:\n"
                        )
                        config = types.GenerateContentConfig(temperature=0.0)
                    else:
                        safety_settings = [
                            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
                        ]
                        prompt = (
                            f"Analyze this raw text extracted from a phone number lookup website for the number {self.national_number}.\n\n"
                            f"EVALUATION RULES:\n"
                            f"1. IGNORE BOILERPLATE: Do not flag based on website navigation text, ads, or generic UI.\n"
                            f"2. NO USER REPORTS = CLEAN: If there are zero complaints or reports about this number, output is_spam=false and risk_score=0.\n"
                            f"3. CONTRADICTORY REPORTS: Require an overwhelming majority (>75%) of negative reports to flag as spam.\n"
                            f"4. LOW VOLUME: If there are only 1 to 3 reports, evaluate their individual severity carefully.\n"
                            f"5. THRESHOLD: Only set is_spam=true if the genuine user-generated risk is clearly high.\n\n"
                            f"RAW TEXT TO ANALYZE:\n{clean_text}\n\n"
                            f"Based strictly on actual user reports for THIS number, return the JSON."
                        )
                        config = types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_json_schema=schema,
                            temperature=0.0,
                            safety_settings=safety_settings,
                            thinking_config=types.ThinkingConfig(thinking_budget=0)
                        )

                    buf = io.StringIO()
                    with contextlib.redirect_stderr(buf):
                        response = await asyncio.to_thread(
                            self.client_text.models.generate_content,
                            model=self.model_text,
                            contents=prompt,
                            config=config
                        )

                    text_part = extract_response_text(response, default="{}")
                    cleaned_text = clean_json_text(text_part)
                    try:
                        data = json.loads(cleaned_text)
                    except (json.JSONDecodeError, TypeError):
                        data = {"is_spam": False, "risk_score": 0}

                    score = int(data.get("risk_score", 0))
                    reason = str(data.get("reason", ""))
                    if score > highest_score:
                        highest_score = score
                        best_reason = reason

                    if data.get("is_spam") or score > 70:
                        self.network_spam_score = score
                        print(f"{_C_WARN}[{get_timestamp()}] [SpamCheck] LLM Flagged as SPAM (Score: {score}): {reason}{_R}")
                        self._save_spam_cache(cache_key, True, score, reason)
                        return True
                    else:
                        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[SpamCheck] Clean on {url} (Score: {score}){_R}")
                except Exception as e:
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[SpamCheck] Provider error ({url}): {e}{_R}")

        self.network_spam_score = highest_score
        self._save_spam_cache(cache_key, False, highest_score, best_reason)
        return False

    def _save_spam_cache(self, number_key: str, is_spam: bool, risk_score: int, reason: str) -> None:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT OR REPLACE INTO spam_cache (number, is_spam, risk_score, reason, updated_at) VALUES (?, ?, ?, ?, ?)",
                (number_key, 1 if is_spam else 0, risk_score, reason, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    async def enforce_bluetooth_call_profile(self) -> None:
        mac_match = re.search(r"dev_([0-9A-Z_]+)", self.dbus_path)
        if not mac_match:
            return
        mac_str = mac_match.group(1).upper()

        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[Bluetooth] Scanning for Bluetooth audio card...{_R}")

        card_name = f"bluez_card.{mac_str}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "list", "cards", "short",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode("utf-8", errors="ignore").splitlines():
                if "bluez_card" in line and mac_str in line:
                    card_name = line.split()[1]
                    break
        except Exception:
            pass

        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[Bluetooth] Forcing HFP profile on {card_name}...{_R}")

        for profile in ["headset-audio-gateway", "headset-head-unit", "hfp-ag", "hfp-hf"]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pactl", "set-card-profile", card_name, profile,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()
                if proc.returncode == 0:
                    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] Audio profile successfully changed to: {profile}{_R}")
                    return
            except Exception:
                pass

        print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Warning: Could not force profile. Relying on auto-switching.{_R}")

    async def wait_for_pw_node(self, node_name: str, timeout: float = 12.0) -> Tuple[bool, str]:
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[PipeWire] Waiting for node: {node_name}...{_R}")
        base_name = re.sub(r"\.\d+$", "", node_name)
        deadline = time.time() + timeout

        while time.time() < deadline and self.running:
            proc_out = await asyncio.create_subprocess_exec("pw-link", "-o", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout_out, _ = await proc_out.communicate()
            proc_in = await asyncio.create_subprocess_exec("pw-link", "-i", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout_in, _ = await proc_in.communicate()
            combined = stdout_out.decode("utf-8", errors="ignore") + "\n" + stdout_in.decode("utf-8", errors="ignore")
            for line in combined.splitlines():
                node_part = line.strip().split(":")[0]
                if base_name in node_part:
                    return True, node_part
            await asyncio.sleep(0.5)
        return False, node_name

    async def monitor_routing_manager(self) -> None:
        while self.running:
            mode = get_config("monitor_mode", "none")
            allow_pc_mic = get_config("allow_pc_mic", "false") == "true"

            if mode in ["both", "assistant"]:
                if self.asst_pacat is None or self.asst_pacat.poll() is not None:
                    self.asst_pacat = subprocess.Popen(
                        ["pacat", "--format=s16le", "--rate=24000", "--channels=1", "--raw"],
                        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
                    )
            else:
                if self.asst_pacat and self.asst_pacat.poll() is None:
                    self.asst_pacat.terminate()
                    self.asst_pacat = None

            if mode in ["both", "caller"]:
                if self.caller_pacat is None or self.caller_pacat.poll() is not None:
                    sink = get_default_sink()
                    cmd = ["pacat", "--format=s16le", "--rate=16000", "--channels=1", "--raw"]
                    cmd.append(f"--device={sink}" if sink else "--device=auto_null")
                    self.caller_pacat = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            else:
                if self.caller_pacat and self.caller_pacat.poll() is None:
                    self.caller_pacat.terminate()
                    self.caller_pacat = None

            try:
                proc = await asyncio.create_subprocess_exec("pw-link", "-l", "--id", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await proc.communicate()
                text = out.decode("utf-8", errors="ignore")
                src_name = ""
                for line in text.splitlines():
                    m_src = re.match(r"^\s{1,4}\d+\s+([\w.\-]+):[\w_]+\s*$", line)
                    if m_src:
                        src_name = m_src.group(1)
                        continue
                    m_dst = re.match(r"^\s+(\d+)\s+\|->\s+\d+\s+([\w.\-]+):[\w_]+\s*$", line)
                    if m_dst and src_name:
                        link_id, dst_name = m_dst.group(1), m_dst.group(2)
                        if not allow_pc_mic and "bluez_output" in dst_name and ("alsa_input" in src_name or "pci" in src_name or "usb" in src_name):
                            await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.DEVNULL)
                        if "bluez_input" in src_name and mode not in ["both", "caller"]:
                            sink = get_default_sink()
                            if ("alsa_output" in dst_name) or (sink and sink in dst_name):
                                await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.DEVNULL)
            except Exception:
                pass

            await asyncio.sleep(2.0)

        for pacat in [self.caller_pacat, self.asst_pacat]:
            if pacat:
                try:
                    if pacat.stdin:
                        pacat.stdin.close()
                    pacat.kill()
                    pacat.wait()
                except Exception:
                    pass

    def log_system_message(self, message_text: str, emoji_prefix: str = "⚠") -> None:
        ts = get_timestamp()
        clean_msg = (
            message_text.replace("⏳", "").replace("⚠", "").replace("❌", "")
            .replace("⏸", "").replace("▶️", "").replace("[SYSTEM]", "").replace(":", "").strip()
        )
        prefix = "> " if getattr(self, "on_hold", False) else ""
        console_tag = f"{prefix}{emoji_prefix} [SYSTEM]" if USE_EMOJI else f"{prefix}[SYSTEM]"

        print(f"\n{_C_WARN}[{ts}] {console_tag}: {clean_msg}{_R}")
        self.accumulated_transcript += f"\n\n{emoji_prefix} [{ts}]: [SYSTEM]: {clean_msg}"
        self.update_transcription_db()

    def create_call_record_db(self, initial_tag: Optional[str] = None, initial_transcript: Optional[str] = None, audio_path_val: Optional[str] = None) -> None:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        initial = initial_transcript if initial_transcript is not None else f"⚠ [{get_timestamp()}]: [SYSTEM]: Call Connected."
        self.accumulated_transcript = initial
        tag_to_use = initial_tag if initial_tag is not None else self.gui_data.get("ui_in_progress", "IN PROGRESS")
        rec_path = self.recording_path if audio_path_val is None else audio_path_val

        c.execute(
            "INSERT INTO calls (number, date, duration, spam_score, transcript, audio_path, client_audio_path, tag, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
            (self.caller_number, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 0, initial, rec_path, "", tag_to_use)
        )
        self.call_id = c.lastrowid
        conn.commit()
        conn.close()

    def update_transcription_db(self) -> None:
        if self.call_id:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE calls SET transcript=? WHERE id=?", (self.accumulated_transcript, self.call_id))
            conn.commit()
            conn.close()

    def save_to_db(self, name: str, message: str) -> None:
        if self.call_id:
            now_dt = datetime.datetime.now()
            exact_date = now_dt.strftime("%Y-%m-%d")
            exact_time = now_dt.strftime("%H:%M:%S")

            msg_fmt = self.assistant_data.get("ui_saved_message", "Message from {name}: {message}")
            final_msg = msg_fmt.format(name=name, message=message)

            visual_message = f"\n\n📝 [{exact_time}]: [SYSTEM]: *** {final_msg} ***"
            self.accumulated_transcript += visual_message
            self.update_transcription_db()

            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "INSERT INTO messages (call_id, number, date, time, caller_name, message_text, is_read) VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (self.call_id, self.caller_number, exact_date, exact_time, str(name or "").strip(), str(message or "").strip())
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"{_C_WARN}[DB] Warning saving to messages table: {e}{_R}")

            print(f"\n{_C_AUDIO}[{exact_time}] {ICON_OK}[DB] {final_msg}{_R}")

    def answer_call(self) -> None:
        try:
            iface = dbus.Interface(dbus.SystemBus().get_object("org.ofono", self.dbus_path), "org.ofono.VoiceCall")
            iface.Answer()
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[D-Bus] Call answered: {self.caller_number}{_R}")
        except Exception as e:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[D-Bus] Answer failed: {e}{_R}")

    def hangup_call(self) -> None:
        try:
            iface = dbus.Interface(dbus.SystemBus().get_object("org.ofono", self.dbus_path), "org.ofono.VoiceCall")
            iface.Hangup()
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[D-Bus] Call terminated.{_R}")
        except Exception:
            pass

    async def send_mic_audio(self, session) -> None:
        print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_AUDIO}[Mic] Active on node: {self.pw_record_target} (Gain: {self.caller_gain}x, Base Gate: {self.noise_gate_base}){_R}")
        cmd = ["pw-record", f"--target={self.pw_record_target}", "-P", '{"node.dont-reconnect": true}', "--format=s16", "--rate=16000", "--channels=1", "-"]
        env = os.environ.copy()
        env["PW_DEBUG"] = "0"

        takeover_notified = False
        base_target = re.sub(r"\.\d+$", "", self.pw_record_target)

        while self.running:
            if self.hanging_up:
                await asyncio.sleep(0.1)
                continue

            check_proc = await asyncio.create_subprocess_exec("pw-link", "-o", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await check_proc.communicate()
            if base_target not in out.decode("utf-8", errors="ignore"):
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

            background_energy = 25.0
            consecutive_empty = 0
            valid_chunks = 0

            try:
                while self.running:
                    if self.hanging_up:
                        await asyncio.sleep(0.1)
                        continue

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

                        return_prompt = self.prompts_data.get(
                            "hold_return_prompt",
                            "[SYSTEM: Bluetooth audio has been restored to the switchboard. Remain silent and attentive until the caller speaks to you.]"
                        )
                        await session.send_realtime_input(text=return_prompt)

                    raw_rms = calculate_rms(data)
                    if raw_rms < 250:
                        background_energy = 0.98 * background_energy + 0.02 * raw_rms

                    adaptive_gate = max(self.noise_gate_base, min(65, int(self.noise_gate_base + (background_energy * 0.35))))
                    noise_gate = min(80, adaptive_gate + 15) if self.on_hold else adaptive_gate

                    count = len(data) // 2
                    if count > 0 and self.caller_gain != 1.0:
                        samples = struct.unpack(f"<{count}h", data)
                        samples = [max(min(int(s * self.caller_gain), 32767), -32768) for s in samples]
                        amplified_data = struct.pack(f"<{count}h", *samples)
                    else:
                        amplified_data = data

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
                    self.caller_recording_buffer.append(amplified_data)

                    if self.caller_pacat and self.caller_pacat.poll() is None:
                        try:
                            self.caller_pacat.stdin.write(amplified_data)
                            self.caller_pacat.stdin.flush()
                        except Exception:
                            pass

                    if self.greeting_in_progress:
                        if (now - self.greeting_started_time > 8.0) or (self.greeting_audio_received and not self.currently_playing and self.audio_out_queue.empty()):
                            self.greeting_in_progress = False

                    is_silence = (raw_rms < noise_gate)
                    is_echo = (self.software_echo_suppression and self.currently_playing)
                    is_protected_greeting = (self.protect_initial_greeting and self.greeting_in_progress)

                    if is_silence or is_echo or is_protected_greeting:
                        out_pcm = b"\x00" * len(amplified_data)
                    else:
                        out_pcm = amplified_data
                        self.user_turn_audio.append(amplified_data)

                    await session.send_realtime_input(audio=types.Blob(data=out_pcm, mime_type="audio/pcm;rate=16000"))

            except Exception:
                pass
            finally:
                self.mic_node_active = False
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass

            if self.running and not takeover_notified and not self.mic_node_active:
                self.log_system_message("Audio routed to handset (Takeover). AI paused...", "⏸")
                takeover_notified = True

            await asyncio.sleep(1.0)

    def sync_playback_loop(self) -> None:
        cmd = ["pw-play", f"--target={self.pw_playback_target}", "-P", '{"node.dont-reconnect": true}', "--format=s16", "--rate=24000", "--channels=1", "-"]
        env = os.environ.copy()
        env["PW_DEBUG"] = "0"
        proc = None

        try:
            while self.running or not self.audio_out_queue.empty():
                if not getattr(self, "mic_node_active", True):
                    try:
                        while True:
                            self.audio_out_queue.get_nowait()
                            self.audio_out_queue.task_done()
                    except queue.Empty:
                        pass
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
                            except Exception:
                                pass
                        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                        self.last_chunk_audio_time = time.time()
                    except Exception:
                        pass

                    self.audio_out_queue.task_done()
                except queue.Empty:
                    self.currently_playing = False
                except Exception:
                    self.currently_playing = False
        finally:
            if proc:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass

    def _strip_assistant_echo_from_input(self, caller_text: str) -> str:
        if not caller_text or not self.recent_asst_phrases:
            return caller_text

        cleaned = caller_text
        now = time.time()
        for norm_p, ts_p, raw_p in list(self.recent_asst_phrases):
            if now - ts_p > 18.0:
                continue
            raw_candidate = raw_p.strip()
            if len(raw_candidate) >= 6:
                pattern = re.compile(re.escape(raw_candidate), re.IGNORECASE)
                cleaned = pattern.sub(" ", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        words_left = [w.strip(".,;:!?¿¡").lower() for w in cleaned.split() if w.strip(".,;:!?¿¡")]
        foreign = set(self.words_data.get("foreign_noise", []))
        if len(words_left) == 1 and words_left[0] in foreign:
            return ""
        return cleaned

    def _calculate_text_similarity(self, a: str, b: str) -> float:
        a, b = a.lower().strip(), b.lower().strip()
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        wa, wb = set(a.split()), set(b.split())
        return (len(wa & wb) / len(wa | wb)) if (wa and wb) else 0.0

    def _has_foreign_language_noise(self, text: str) -> bool:
        words = text.lower().split()
        if not words:
            return False
        foreign = set(self.words_data.get("foreign_noise", []))
        return (sum(1 for w in words if w in foreign) / len(words)) > 0.30

    def _has_excessive_repetition(self, text: str) -> bool:
        words = text.lower().split()
        if len(words) < 5:
            return False
        _, freq = Counter(words).most_common(1)[0]
        return freq > 4 and (freq / len(words)) > 0.40

    def _is_transcription_noise(self, text: str) -> bool:
        t = re.sub(r"[\(\[\{].*?[\)\}\]]", "", text).strip().lower()
        if not t or re.match(r"^[¿¡\s\-,.;.:!?]+$", t):
            return True
        return t in set(self.words_data.get("transcription_noise", []))

    async def heal_transcription_whisper(self, audio_bytes_list: list, gemini_txt: str, turn_ts: str = "") -> None:
        model_path = os.path.join(BASE_DIR, "models", f"ggml-{self.whisper_full_model}.bin")
        if not WHISPER_BIN or not os.path.exists(WHISPER_BIN) or not os.path.exists(model_path):
            return
        tmp_wav = f"/tmp/whisper_turn_{str(uuid.uuid4())[:8]}.wav"
        try:
            with wave.open(tmp_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                for chunk in audio_bytes_list:
                    wf.writeframes(chunk)
            lang_arg = self.current_lang.split("-")[0]
            proc = await asyncio.create_subprocess_exec(
                WHISPER_BIN, "-l", lang_arg, "-t", "4", "-m", model_path, "-f", tmp_wav,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if not stdout:
                return
            whisper_txt = clean_whisper_output(stdout.decode("utf-8", errors="ignore"))
            wv = not (not whisper_txt.strip() or self._has_foreign_language_noise(whisper_txt) or self._has_excessive_repetition(whisper_txt) or self._is_transcription_noise(whisper_txt))
            gv = not (not gemini_txt.strip() or self._has_foreign_language_noise(gemini_txt) or self._has_excessive_repetition(gemini_txt) or self._is_transcription_noise(gemini_txt))

            combined = (
                f"{gemini_txt} | [Whisper]: {whisper_txt}" if gv and wv
                else ("[Noise Filtered]" if not gv and not wv else f"[Noise Filtered] | [Whisper]: {whisper_txt}" if wv else f"{gemini_txt} | [Whisper]: [Noise Filtered]")
            )
            pat = f"🗣 [{turn_ts}]: {gemini_txt}"
            if pat in self.accumulated_transcript:
                self.accumulated_transcript = self.accumulated_transcript.replace(pat, f"🗣 [{turn_ts}]: {combined}")

            _C_WHISPER = "\033[33m" if SUPPORTS_COLOR else ""
            whisper_display = whisper_txt if wv else "[Noise Filtered]"
            print(f"\n{_C_WHISPER}· [Whisper/{turn_ts}]: {whisper_display}{_R}", flush=True)
            self.update_transcription_db()
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    def is_valid_text(self, text: str) -> bool:
        if re.search(r"[\u4e00-\u9fff\uac00-\ud7a3\u3040-\u30ff\u1100-\u11ff]", text):
            return False
        cleaned = text.strip().lower()
        if len(cleaned) <= 1 and cleaned not in ("y", "o", "a", "s", "i", "sí", "si", "no"):
            return False
        return True

    def execute_blocking_generate_content(self, complete_transcript: str) -> None:
        raw_instruction = self.assistant_data.get("output_schema_instruction", "Analyze the transcript and generate a concise summary.")
        try:
            instruction = raw_instruction.format(boss_name=self.boss_name, assistant_name=self.assistant_name)
        except (KeyError, ValueError):
            instruction = raw_instruction

        is_gemma = "gemma" in self.model_text.lower()

        if is_gemma:
            prompt = (
                f"{instruction}\n\n"
                f"OUTPUT MUST BE STRICTLY A JSON OBJECT CONFORMING TO THIS SCHEMA:\n{json.dumps(OUTPUT_SCHEMA, indent=2)}\n\n"
                f"TRANSCRIPT:\n{complete_transcript}\n\nJSON:\n"
            )
            config = types.GenerateContentConfig(temperature=0.0)
        else:
            safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
            ]
            prompt = f"{instruction}\nTRANSCRIPT:\n{complete_transcript}"
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=OUTPUT_SCHEMA,
                temperature=0.0,
                safety_settings=safety_settings,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )

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
            self.last_call_json = {
                "caller_type": "unknown", "risk_score": 0, "insult_detected": False,
                "private_data_requested": False, "caller_name": "", "company": "",
                "summary": "", "response_text": ""
            }

    def _matches_any_phrase(self, text: str, phrases: list) -> bool:
        t = text.lower()
        for phrase in phrases:
            phrase_l = phrase.lower().strip()
            if not phrase_l:
                continue
            if " " in phrase_l:
                if phrase_l in t:
                    return True
            else:
                if re.search(r"(?<![a-záéíóúñüàèìòùâêîôûäëïöüãõ])" + re.escape(phrase_l) + r"(?![a-záéíóúñüàèìòùâêîôûäëïöüãõ])", t):
                    return True
        return False

    def _check_wait_return(self, text: str) -> bool:
        triggers = list(self.words_data.get("return_triggers", []))
        triggers.extend([self.assistant_name.lower(), self.boss_name.lower()])
        return self._matches_any_phrase(text, triggers)

    async def receive_audio_and_tools(self, session) -> None:
        threading.Thread(target=self.sync_playback_loop, daemon=True).start()

        self.last_user_spoke_time = time.time()
        self.last_chunk_audio_time = time.time()
        self.last_asst_text_time = time.time()

        initial_greeting = get_config("initial_greeting", "")
        if initial_greeting:
            greeting = f"[SYSTEM: Start the call by saying EXACTLY this phrase, word by word, without adding anything else: '{initial_greeting}']"
        else:
            greeting = self.prompts_data.get("greeting", "").format(assistant_name=self.assistant_name, boss_name=self.boss_name)

        global ICON_ASST, ICON_USER_STR
        ICON_ASST = "📞 " if USE_EMOJI else f"[{self.assistant_name}]: "
        ICON_USER_STR = "🗣  " if USE_EMOJI else f"[{self.labels_data.get('ui_user_label', 'Caller')}]: "

        print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[{self.assistant_name}] Connecting to Gemini Live websocket...{_R}")
        if self.protect_initial_greeting:
            self.greeting_in_progress = True
            self.greeting_started_time = time.time()
            self.greeting_audio_received = False

        await session.send_realtime_input(text=greeting)
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_OK}[{self.assistant_name}] Connected. Conversation started.{_R}")

        while self.running:
            if self.hanging_up and self.audio_out_queue.empty():
                if time.time() - self.last_chunk_audio_time > 1.0 or time.time() - getattr(self, "hangup_triggered_time", time.time()) > 3.5:
                    print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Final goodbye audio finished playing. Cutting call.{_R}")
                    self.hangup_call()
                    await asyncio.sleep(0.5)
                    self.running = False
                    break

            if self.currently_playing:
                self.last_user_spoke_time = time.time()

            if not self.mic_node_active:
                self.last_user_spoke_time = time.time()
                if self.current_wait_start > 0:
                    self.current_wait_start = time.time()

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

                elif self.on_hold and total_hold_time > 900.0 and not self.waiting_definitive_cut:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.log_system_message("Maximum accumulated hold time (15 mins) exceeded. Starting 15s grace warning...", "⚠")
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))

                elif time_without_user > silence_threshold and not self.hello_question_sent and not self.waiting_definitive_cut:
                    self.log_system_message(f"{int(silence_threshold)}s without response. Asking if someone is there...", "⏳")
                    self.hello_question_sent = True
                    self.last_user_spoke_time = time.time()
                    await session.send_realtime_input(text=self.prompts_data.get("hello_question", ""))

                elif self.hello_question_sent and not self.waiting_definitive_cut and time_without_user > 15.0:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.last_user_spoke_time = time.time()
                    self.log_system_message("Continued silence. Starting 15s grace period...", "⏳")
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))

            try:
                msg = await asyncio.wait_for(session._receive(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

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
                if function_responses:
                    await session.send_tool_response(function_responses=function_responses)

            sc = getattr(msg, "server_content", None)
            if sc:
                itx = getattr(sc, "input_transcription", None)
                if itx and itx.text and self.hanging_up and getattr(self, "hangup_triggered", False):
                    itx = None

                if itx and getattr(itx, "text", None):
                    cleaned_caller_txt = self._strip_assistant_echo_from_input(itx.text)
                    if not cleaned_caller_txt or not self.is_valid_text(cleaned_caller_txt):
                        itx = None
                    else:
                        itx.text = cleaned_caller_txt

                if itx and getattr(itx, "text", None):
                    self.last_user_spoke_time = time.time()
                    self.hello_question_sent = self.cutoff_sent = False

                    if self.waiting_definitive_cut:
                        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Interruption during grace period. Cancelling hangup...{_R}")
                        self.waiting_definitive_cut = False

                    just_activated_hold = False

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
                            user_safe_text = itx.text.lower()
                            for iw in self.words_data.get("ignore_hold_words", []):
                                user_safe_text = user_safe_text.replace(iw.lower(), "")

                            if self._matches_any_phrase(user_safe_text, self.words_data.get("hold_words", [])):
                                now = time.time()
                                self.last_user_spoke_time = now
                                if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                    self.last_renewal_printed_time = now
                                    self.log_system_message(
                                        self.words_data.get("hold_renewed_caller", "⏳ [SYSTEM]: Wait time renewed by caller request (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)),
                                        "⏳"
                                    )

                            if not self._check_wait_return(itx.text):
                                ts = get_timestamp()
                                self.log_system_message(f"Active Hold Ignored background noise / TV '{itx.text}'", "⏸")
                                if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                                    cloned_audio = list(self.user_turn_audio)
                                    self.user_turn_audio.clear()
                                    asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts))
                                else:
                                    self.user_turn_audio.clear()
                                itx = None
                            elif not self._matches_any_phrase(user_safe_text, self.words_data.get("hold_words", [])):
                                self.log_system_message("Return from hold detected. Resuming conversation...", "⏳")
                                self.on_hold = False
                                if self.current_wait_start > 0:
                                    self.accumulated_wait_time += (time.time() - self.current_wait_start)
                                self.current_wait_start = 0.0

                    if itx:
                        ts = get_timestamp()
                        prefix = "> " if self.on_hold else ""
                        print(f"\n\n{_C_MUTED}{prefix}[{ts}]{_R} {_C_AUDIO}{ICON_USER_STR}{itx.text}{_R}")
                        self.accumulated_transcript += f"\n\n🗣 [{ts}]: {itx.text}"
                        self.update_transcription_db()

                        if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                            cloned_audio = list(self.user_turn_audio)
                            self.user_turn_audio.clear()
                            asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts))
                        else:
                            self.user_turn_audio.clear()

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
                                self.greeting_audio_received = True
                                target_byte_idx = int((time.time() - self.call_start_time) * 24000) * 2
                                current_len = len(self.recording_buffer_wav)
                                if current_len < target_byte_idx:
                                    self.recording_buffer_wav.extend(b"\x00" * (target_byte_idx - current_len))
                                self.recording_buffer_wav.extend(inline_data.data)
                                self.audio_out_queue.put(inline_data.data)
                                if self.asst_pacat and self.asst_pacat.poll() is None:
                                    try:
                                        self.asst_pacat.stdin.write(inline_data.data)
                                        self.asst_pacat.stdin.flush()
                                    except Exception:
                                        pass
                                self.last_chunk_audio_time = time.time()
                                self.cutoff_sent = False
                        except Exception:
                            pass

                otx = getattr(sc, "output_transcription", None)
                if otx and getattr(otx, "text", None):
                    self.user_turn_audio.clear()
                    clean_otx = clean_ai_text(otx.text)
                    if clean_otx:
                        clean_norm = re.sub(r"[^\w\s]", "", clean_otx.lower()).strip()
                        now = time.time()
                        self.recent_asst_phrases = [p for p in self.recent_asst_phrases if now - p[1] < 18.0]
                        if len(clean_norm.split()) >= 3:
                            if any(clean_norm == p[0] and (now - p[1] < 4.0) for p in self.recent_asst_phrases):
                                continue
                            self.recent_asst_phrases.append((clean_norm, now, clean_otx))

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

                        now_chunk = time.time()
                        if now_chunk - self._asst_chunk_last_time < 2.5:
                            self._asst_chunk_buffer += " " + clean_otx
                        else:
                            self._asst_chunk_buffer = clean_otx
                        self._asst_chunk_last_time = now_chunk
                        eval_text = self._asst_chunk_buffer.lower()

                        safe_eval_text = eval_text
                        for iw in self.words_data.get("ignore_hold_words", []):
                            safe_eval_text = safe_eval_text.replace(iw.lower(), "")

                        if self.on_hold and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", [])):
                            now = time.time()
                            self.last_user_spoke_time = now
                            if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                self.last_renewal_printed_time = now
                                self.log_system_message(
                                    self.words_data.get("hold_renewed_assistant", "⏳ [SYSTEM]: Wait time renewed by assistant response (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)),
                                    "⏳"
                                )

                        if not self.hangup_triggered and not self.waiting_definitive_cut and not self.hello_question_sent and self._matches_any_phrase(eval_text, self.words_data.get("cut_words", [])):
                            self.hanging_up = self.hangup_triggered = True
                            self.hangup_triggered_time = time.time()
                            self.hangup_source = "cut_words"
                            self.hangup_reason = "completed"
                            print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Goodbye detected in assistant text. Initiating clean call cut...{_R}")

                        if self.hanging_up and self.hangup_source == "cut_words":
                            cancel_phrases = self.words_data.get("cancel_goodbye_phrases", [])
                            has_goodbye = self._matches_any_phrase(eval_text, self.words_data.get("cut_words", []))
                            has_cancel = self._matches_any_phrase(eval_text, cancel_phrases)
                            if has_cancel and not has_goodbye:
                                self.hanging_up = self.hangup_triggered = False
                                self.hangup_triggered_time = 0.0
                                self.hangup_source = ""
                                self._asst_chunk_buffer = ""
                                print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Cancel-goodbye phrase detected without goodbye word. Cancelling hangup...{_R}")

                        if not self.hanging_up and not self.on_hold and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", [])):
                            self.on_hold = True
                            self.current_wait_start = self.last_user_spoke_time = time.time()
                            self.last_speaker = None
                            if self.category_wait_seconds < 60.0:
                                self.log_system_message(f"{self.assistant_name} accepted short hold ({int(self.category_wait_seconds)}s). Sending time limit warning...", "⏳")
                                await session.send_realtime_input(text=self.prompts_data.get("hold_reminder", "").format(wait_seconds=int(self.category_wait_seconds)))
                            else:
                                self.log_system_message(f"{self.assistant_name} accepted hold. Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")

    async def transcribe_file_whisper(self, wav_path: str) -> str:
        model_path = os.path.join(BASE_DIR, "models", f"ggml-{self.whisper_full_model}.bin")
        if not WHISPER_BIN or not os.path.exists(WHISPER_BIN) or not os.path.exists(model_path):
            return ""
        try:
            proc = await asyncio.create_subprocess_exec(
                WHISPER_BIN, "-l", self.current_lang.split("-")[0], "-t", "4", "-m", model_path, "-f", wav_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if stdout:
                return clean_whisper_output(stdout.decode("utf-8", errors="ignore"))
        except Exception:
            pass
        return ""

    async def correct_transcript_with_whisper(self, raw_whisper: str) -> str:
        prompt = (
            f"We have two transcriptions of a call:\n1. LIVE TRANSCRIPT (📞 correct, 🗣 may have noise).\n2. RAW WHISPER (🗣 only).\n"
            f"Task: Align and correct 🗣 parts in LIVE TRANSCRIPT using RAW WHISPER. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
            f"If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\nLIVE TRANSCRIPT:\n{self.accumulated_transcript}\n\nRAW WHISPER:\n{raw_whisper}"
        )
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                resp = await asyncio.to_thread(
                    self.client_text.models.generate_content,
                    model=self.model_text,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1)
                )
            return extract_response_text(resp, default=self.accumulated_transcript)
        except Exception:
            return self.accumulated_transcript

    async def correct_transcript_with_gemini_audio(self, wav_path: str, model_override: Optional[str] = None) -> str:
        try:
            model_to_use = model_override if model_override else self.model_text
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
            prompt = (
                f"Task: Align and correct 🗣 parts in LIVE TRANSCRIPT by listening to audio. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
                f"If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\nLIVE TRANSCRIPT:\n{self.accumulated_transcript}"
            )
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                resp = await asyncio.to_thread(
                    self.client_text.models.generate_content,
                    model=model_to_use,
                    contents=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"), prompt],
                    config=types.GenerateContentConfig(temperature=0.1)
                )
            return extract_response_text(resp, default=self.accumulated_transcript)
        except Exception:
            return self.accumulated_transcript

    async def post_process_call(self) -> None:
        print(f"\n{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Saving recordings, generating summary, and evaluating categories...{_R}")

        caller_pcm_raw = b"".join(self.caller_recording_buffer) if self.caller_recording_buffer else b""
        asst_pcm_raw = bytes(self.recording_buffer_wav)

        if caller_pcm_raw:
            try:
                with wave.open(self.client_recording_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(caller_pcm_raw)
            except Exception:
                pass

        if caller_pcm_raw and asst_pcm_raw:
            try:
                if self.first_mic_time > 0 and self.call_start_time > 0:
                    mic_offset_bytes = int(max(0.0, self.first_mic_time - self.call_start_time) * 16000) * 2
                    if mic_offset_bytes > 0:
                        caller_pcm_raw = (b"\x00" * mic_offset_bytes) + caller_pcm_raw

                caller_pcm = upsample_16k_to_24k(caller_pcm_raw)

                max_len = max(len(caller_pcm), len(asst_pcm_raw))
                if len(caller_pcm) < max_len:
                    caller_pcm += b"\x00" * (max_len - len(caller_pcm))
                if len(asst_pcm_raw) < max_len:
                    asst_pcm_raw += b"\x00" * (max_len - len(asst_pcm_raw))

                num_samples = max_len // 2
                c_samp = struct.unpack(f"<{num_samples}h", caller_pcm)
                a_samp = struct.unpack(f"<{num_samples}h", asst_pcm_raw)

                stereo_data = [val for pair in zip(c_samp, a_samp) for val in pair]
                with wave.open(self.recording_path, "wb") as wf:
                    wf.setnchannels(2)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(struct.pack(f"<{num_samples * 2}h", *stereo_data))
                print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[Audio] Call synchronized stereo recording saved: {self.recording_path}{_R}")
            except Exception as e:
                print(f"{_C_WARN}[{get_timestamp()}] Error mixing stereo audio: {e}{_R}")
        elif asst_pcm_raw:
            try:
                with wave.open(self.recording_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(asst_pcm_raw)
            except Exception:
                pass

        if not getattr(self, "hangup_message_appended", False):
            self.hangup_message_appended = True
            if getattr(self, "hangup_triggered", False):
                lbl = (
                    self.words_data.get("call_spam", "❌ [SYSTEM]: Call automatically hung up due to network SPAM detection.")
                    if getattr(self, "hangup_reason", "completed") == "spam"
                    else self.words_data.get("call_finished", "❌ [SYSTEM]: Call successfully finished and saved.")
                )
            else:
                lbl = self.words_data.get("call_finished", "❌ [SYSTEM]: Call disconnected by caller and saved.")

            clean_lbl = lbl.replace("❌ [SYSTEM]:", "").replace("❌", "").replace("[SYSTEM]:", "").replace("❌ [SISTEMA]:", "").replace("[SISTEMA]:", "").strip()
            self.accumulated_transcript += f"\n\n❌ [{get_timestamp()}]: [SYSTEM]: {clean_lbl}"

        final_trans = re.sub(r"\[SYSTEM\]:\s*.*?-\s*Call Connected\.", "[SYSTEM]: Call Connected.", self.accumulated_transcript)

        try:
            await asyncio.to_thread(self.execute_blocking_generate_content, final_trans)
        except Exception as e:
            print(f"{_C_ERR}[Post-Processing] Final state extraction failed: {e}{_R}")

        caller_type = self.last_call_json.get("caller_type", "unknown")
        max_spam_score = max(self.last_call_json.get("risk_score", 0), self.network_spam_score)
        call_summary = str(self.last_call_json.get("summary", "") or "").strip()

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

        contact_match = match_contact_rule(self.caller_number)
        custom_contact_tag = (contact_match or {}).get("tag", "").strip()

        if custom_contact_tag:
            final_tag = custom_contact_tag
        elif caller_type == "spam" or max_spam_score >= 65 or self.last_call_json.get("private_data_requested", False):
            final_tag = self.labels_data.get("spam", "SPAM")
        elif self.priority_call:
            final_tag = self.labels_data.get("priority", "PRIORITY")
        elif caller_type == "friend_family":
            final_tag = self.labels_data.get("personal", "PERSONAL")
        elif caller_type == "work":
            final_tag = self.labels_data.get("work", "WORK")
        elif caller_type == "commercial":
            final_tag = self.labels_data.get("spam", "SPAM")
        else:
            final_tag = self.labels_data.get("general", "GENERAL")

        client_n = self.last_call_json.get("caller_name", "")
        comp_n = self.last_call_json.get("company", "")
        if client_n.lower() in ["unknown", "null", "none"]:
            client_n = ""
        if comp_n.lower() in ["unknown", "null", "none"]:
            comp_n = ""
        if not client_n and (contact_match or {}).get("note"):
            client_n = contact_match["note"]

        duration_sec = max(0, int(time.time() - self.call_start_time))
        client_rec_val = self.client_recording_path if os.path.exists(self.client_recording_path) else ""
        rec_val = self.recording_path if os.path.exists(self.recording_path) else ""

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE calls SET duration=?, tag=?, client_name=?, company=?, transcript=?, spam_score=?, audio_path=?, client_audio_path=?, summary=? WHERE id=?",
            (duration_sec, final_tag, client_n, comp_n, final_trans, max_spam_score, rec_val, client_rec_val, call_summary, self.call_id)
        )
        conn.commit()
        conn.close()
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Post-Processing] Complete. Tagged as: {final_tag}{_R}")

    async def run(self) -> None:
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[Caller] Raw: '{self.caller_number}' | Normalized National: '{self.national_number}'{_R}")

        contact_match = match_contact_rule(self.caller_number)
        if contact_match:
            print(
                f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[ContactMatch] Matched pattern '{contact_match['pattern']}' "
                f"({contact_match['type'].upper()}) Note: '{contact_match['note']}' Tag: '{contact_match['tag']}'{_R}"
            )

        if contact_match and contact_match["type"] == "blacklist":
            blocked_tag = contact_match["tag"] or self.labels_data.get("blocked", "🚫 BLACKLISTED")
            blocked_msg = f"❌ [{get_timestamp()}]: [SYSTEM]: Call automatically rejected by Blacklist rule ({contact_match['pattern']})."
            self.create_call_record_db(initial_tag=blocked_tag, initial_transcript=blocked_msg, audio_path_val="")
            if contact_match.get("note"):
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE calls SET client_name=?, summary=? WHERE id=?", (contact_match["note"], f"Blocked by rule {contact_match['pattern']}", self.call_id))
                conn.commit()
                conn.close()
            self._post_processed = True
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Blacklist] {self.caller_number} matched '{contact_match['pattern']}'. Logged and rejected.{_R}")
            self.hangup_call()
            return

        self.create_call_record_db()
        self.running = True
        self.answered_call = False
        self.recording_buffer_wav = bytearray()
        self.caller_recording_buffer = []

        delay = int(get_config("wait_seconds", "5"))
        if delay > 0 and self.running:
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Delay] Waiting {delay}s before answering...{_R}")
            for _ in range(delay * 10):
                if not self.running:
                    break
                await asyncio.sleep(0.1)

        if not self.running:
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Delay] Call aborted by caller before answering.{_R}")
            return

        raw_instruction = self.assistant_data.get("system_instruction", "")
        try:
            instruction = raw_instruction.format(
                assistant_name=self.assistant_name,
                role_assistant=self.assistant_data.get("role_mappings", {}).get("female" if "fem" in self.assistant_gender.lower() else "male", "Secretary"),
                owner_desc=self.assistant_data.get("owner_type_mappings", {}).get(self.owner_type, "Private"),
                boss_name=self.boss_name,
                business_details=self.business_description
            )
        except (KeyError, ValueError):
            instruction = raw_instruction

        memory_block = self.build_memory_context(contact_match)
        if memory_block:
            instruction += memory_block

        instruction += self.assistant_data.get("system_date", "\nDATE: {today_str}").format(today_str=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        if contact_match and contact_match.get("prompt_rules"):
            instruction += self.assistant_data.get("custom_contact_rule", "\nRule: {rule}").format(rule=contact_match["prompt_rules"])

        extra_prompt = get_config("extra_prompt", "")
        if extra_prompt:
            instruction += f"\n\nEXTRA INSTRUCTIONS/PERSONALITY:\n{extra_prompt}"

        tools_list = [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="hangup",
                description="Terminates the call immediately if spam or successfully finished.",
                parameters_json_schema={"type": "object", "properties": {"reason": {"type": "string"}}}
            ),
            types.FunctionDeclaration(
                name="save_message",
                description="MANDATORY: Execute this tool to save ANY actionable message, task, delivery notice, or completed appointment details for the owner. Do not say it is noted without invoking this tool.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"caller_name": {"type": "string"}, "message_text": {"type": "string"}},
                    "required": ["caller_name", "message_text"]
                }
            )
        ])]

        start_sens_enum = (
            types.StartSensitivity.START_SENSITIVITY_LOW
            if self.vad_start_sens == "LOW"
            else types.StartSensitivity.START_SENSITIVITY_HIGH
        )
        end_sens_enum = (
            types.EndSensitivity.END_SENSITIVITY_LOW
            if self.vad_end_sens == "LOW"
            else types.EndSensitivity.END_SENSITIVITY_HIGH
        )

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=instruction)]),
            tools=tools_list,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede" if "fem" in self.assistant_gender.lower() else "Puck"
                    )
                )
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=start_sens_enum,
                    end_of_speech_sensitivity=end_sens_enum,
                    prefix_padding_ms=self.vad_prefix_padding_ms,
                    silence_duration_ms=self.vad_silence_duration_ms,
                )
            )
        )

        is_whitelisted = bool(contact_match and contact_match.get("type") == "whitelist")
        spam_task = asyncio.create_task(self.check_network_spam(is_whitelisted=is_whitelisted))
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
                        print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[PipeWire] Channels unmuted.{_R}")
                    except Exception:
                        pass
                    await asyncio.sleep(1.0)
                elif not self.running:
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[PipeWire] Call aborted during initialization.{_R}")
                    return
                else:
                    print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[PipeWire] Timeout waiting for audio nodes. Audio may fail.{_R}")

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
                            except Exception:
                                pass
                            break
                        await asyncio.sleep(0.5)

                await asyncio.gather(self.send_mic_audio(session), self.receive_audio_and_tools(session), monitor_spam())

        except Exception as e:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Session] Unexpected error: {e}{_R}")
            if not getattr(self, "answered_call", False):
                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[AI Engine] Gemini Live is unavailable. Delegating call to native phone handler.{_R}")
        finally:
            self.running = False
            if getattr(self, "answered_call", False):
                self.hangup_call()


async def daemon_heartbeat_loop(main_loop: asyncio.AbstractEventLoop) -> None:
    """Periodically updates the daemon heartbeat in SQLite and checks for pause/stop signals from the GUI."""
    last_logged_state = "running"
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('daemon_heartbeat', ?)", (str(time.time()),))
            row = conn.execute("SELECT value FROM settings WHERE key='daemon_state'").fetchone()
            conn.commit()
            conn.close()

            state = row[0] if row else "running"
            if state != last_logged_state:
                print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[DaemonState] State changed to: {state.upper()}{_R}")
                last_logged_state = state

            if state == "stopped":
                if ACTIVE_ASSISTANT is None or not getattr(ACTIVE_ASSISTANT, "running", False):
                    print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Daemon] Stop requested via Web GUI. Shutting down cleanly...{_R}")
                    if GLIB_LOOP is not None:
                        try:
                            GLIB_LOOP.quit()
                        except Exception:
                            pass
                    main_loop.stop()
                    os._exit(0)
        except Exception:
            pass
        await asyncio.sleep(3.0)


async def run_cli_spam_test(test_number: str) -> None:
    """CLI utility to test a phone number against all configured SPAM providers and the LLM."""
    ensure_database_exists()
    dummy = PhoneAssistant(dbus_path="/org/ofono/test", caller_number=test_number)
    print(f"{_C_SERVER}Testing number {test_number} (National: {dummy.national_number}) against SPAM providers...{_R}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM spam_cache WHERE number=?", (dummy.national_number or dummy.digits_number,))
    conn.commit()
    conn.close()
    is_spam = await dummy.check_network_spam(is_whitelisted=False)
    print(f"{_C_AUDIO}Result: is_spam={is_spam} | risk_score={dummy.network_spam_score}{_R}")


def run_dbus_loop(main_loop: asyncio.AbstractEventLoop) -> None:
    """Listens for CallAdded and CallRemoved events over D-Bus from oFono."""
    global ACTIVE_ASSISTANT, GLIB_LOOP

    def on_call_added(path: str, properties: dict) -> None:
        global ACTIVE_ASSISTANT, ACTIVE_TASKS
        if properties.get("State") != "incoming":
            return
        number = properties.get("LineIdentification", "Unknown")

        daemon_state = get_config("daemon_state", "running")
        if daemon_state == "paused":
            print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Paused] Incoming call from {number} ignored (Switchboard is PAUSED).{_R}")
            return
        if daemon_state == "stopped":
            return

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
            if not getattr(ACTIVE_ASSISTANT, "_post_processed", False):
                ACTIVE_ASSISTANT._post_processed = True
                asyncio.run_coroutine_threadsafe(ACTIVE_ASSISTANT.post_process_call(), main_loop)

    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        bus.add_signal_receiver(on_call_added, dbus_interface="org.ofono.VoiceCallManager", signal_name="CallAdded")
        bus.add_signal_receiver(on_call_removed, dbus_interface="org.ofono.VoiceCallManager", signal_name="CallRemoved")
        GLIB_LOOP = GLib.MainLoop()
        GLIB_LOOP.run()
    except Exception as e:
        print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}Error in D-Bus listener: {e}{_R}")


if __name__ == "__main__":
    if not API_KEY:
        print(f"{_C_ERR}{ICON_ERR}Error: GEMINI_API_KEY environment variable not set.{_R}")
        sys.exit(1)

    if len(sys.argv) >= 3 and sys.argv[1] == "--test-spam":
        asyncio.run(run_cli_spam_test(sys.argv[2]))
        sys.exit(0)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    ensure_database_exists()
    ensure_system_dependencies()

    initialize_ofono_modems()
    initialize_bluez_devices()

    print(f"{_C_SERVER}{ICON_SERVER}Synchronizing audio subsystem with oFono...{_R}")
    try:
        subprocess.run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"], check=True, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        ensure_null_sink()
    except Exception as e:
        print(f"{_C_WARN}{ICON_WARN}Warning: Could not restart audio services: {e}{_R}")

    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)
    main_loop.create_task(daemon_heartbeat_loop(main_loop))

    dbus_thread = threading.Thread(target=run_dbus_loop, args=(main_loop,), daemon=True)
    dbus_thread.start()

    print(f"{_C_SERVER}{ICON_SERVER}--- BLUETOOTH AI SWITCHBOARD v2.0 ---{_R}")
    print("Waiting for incoming calls via oFono...\n")

    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print(f"\n{_C_WARN}{ICON_WARN}Switchboard manually stopped.{_R}")
        os._exit(0)

