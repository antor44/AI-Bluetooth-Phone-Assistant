#!/usr/bin/env python3
"""
AI Switchboard Assistant - Intelligent phone handler utilizing Gemini 3.8 Live and Bluetooth HFP.
Detects incoming calls via D-Bus/oFono, manages audio routing through PipeWire, normalizes
caller numbers & wildcards, caches SPAM lookups, stores structured caller messages and AI
summaries, and interacts in real time.

Author: Antonio R.
Version: 2.8
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
import base64
import re
import fnmatch
import sqlite3
import time
import wave
import struct
import array
import math
import subprocess
import shutil
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

try:
    import lameenc
except ImportError:
    lameenc = None

# Line-buffered output keeps the console and the systemd journal in real time when stdout is a pipe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True)
    except Exception:
        pass

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
# Fallback prebuilt voices, used only when the language file does not define "voice_names".
DEFAULT_VOICE_FEMALE = "Aoede"
DEFAULT_VOICE_MALE = "Charon"
API_KEY = os.environ.get("GEMINI_API_KEY")

DEFAULT_PW_INPUT  = "bluez_input.00_00_00_00_00_00.0"
DEFAULT_PW_OUTPUT = "bluez_output.00_00_00_00_00_00.1"

APP_VERSION = "2.8"
DEFAULT_LANGUAGE = "en-US"  # Language of a fresh install, until another one is selected in the Web GUI

# Playback drain before hanging up (see PhoneAssistant.is_playback_drained).
PLAYBACK_BYTES_PER_SECOND = 24000 * 2   # Gemini Live output: 24 kHz, 16-bit, mono PCM
HANGUP_AUDIO_TAIL_SECONDS = 1.2         # Extra time after the estimated end of playback (PipeWire + Bluetooth SCO latency)
DEFAULT_VAD_SILENCE_DURATION_MS = 700    # Default VAD silence (ms) before Gemini Live considers that the caller finished speaking
ASSISTANT_TURN_GAP_SECONDS = 4.0         # Output chunks closer than this belong to the same assistant turn (farewell detection)
HANGUP_STREAM_QUIET_SECONDS = 1.0       # No new audio from the model for this long before cutting the call
HANGUP_MAX_WAIT_SECONDS = 20.0          # Safety limit: never wait longer than this for the audio to finish

# Bluetooth reconnection watchdog (see BluetoothWatchdog).
BT_HFP_AG_UUID = "0000111f-0000-1000-8000-00805f9b34fb"  # Hands-Free Audio Gateway profile (the phone side)
BT_WATCHDOG_INTERVAL_SECONDS = 10.0
BT_RECONNECT_BACKOFF_MIN_SECONDS = 10.0
BT_RECONNECT_BACKOFF_MAX_SECONDS = 120.0
BT_CONNECT_TIMEOUT_SECONDS = 30
BT_MODEM_MISSING_CYCLES = 3             # Connected phone without an oFono modem for this many cycles -> reconnect the profile

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


def get_home_numbering(lang_code: str = "") -> Dict[str, Any]:
    """Loads the home country numbering plan (home_country_code, home_national_length) from the active language's spam.json."""
    active_lang = lang_code
    if not active_lang:
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
            active_lang = row[0] if row and row[0] else DEFAULT_LANGUAGE
        except Exception:
            active_lang = DEFAULT_LANGUAGE
        finally:
            if conn:
                conn.close()
    path = os.path.join(LANG_DIR, active_lang, "spam.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def build_e164(raw_number: str, numbering: Optional[Dict[str, Any]] = None) -> str:
    """Builds an E.164 number (with a leading "+") from a caller ID string.

    A "+" or "00" prefix is trusted as is. For numbers without an international marker, the home numbering plan
    of the active language (spam.json: "home_country_code" and "home_national_length") decides whether the
    country code must be added. Without that information the digits are assumed to be complete."""
    if numbering is None:
        numbering = get_home_numbering()
    raw = (raw_number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"
    if digits.startswith("00"):
        return f"+{digits[2:]}"
    country_code = re.sub(r"\D", "", str(numbering.get("home_country_code", "")))
    try:
        national_length = int(numbering.get("home_national_length", 0))
    except (TypeError, ValueError):
        national_length = 0
    if not country_code or national_length <= 0:
        return f"+{digits}"
    significant = digits[1:] if (digits.startswith("0") and len(digits) - 1 == national_length) else digits
    if len(significant) == national_length:
        return f"+{country_code}{significant}"
    return f"+{digits}"


def normalize_phone_candidates(raw_number: str, numbering: Optional[Dict[str, Any]] = None) -> Tuple[str, str, List[str]]:
    """Normalizes an incoming phone number into (digits_only, national_or_full_digits, matching_candidates) using the active numbering plan."""
    if numbering is None:
        numbering = get_home_numbering()
    raw = (raw_number or "").strip()
    raw_digits = re.sub(r"\D", "", raw)
    has_intl_prefix = raw.startswith("+") or raw_digits.startswith("00")
    digits = raw_digits[2:] if raw_digits.startswith("00") else raw_digits

    country_code = re.sub(r"\D", "", str(numbering.get("home_country_code", "")))
    try:
        national_length = int(numbering.get("home_national_length", 0))
    except (TypeError, ValueError):
        national_length = 0

    if country_code and national_length > 0:
        if digits.startswith(country_code) and len(digits) == len(country_code) + national_length:
            national = digits[len(country_code):]
        elif digits.startswith(country_code + "0") and len(digits) == len(country_code) + 1 + national_length:
            national = digits[len(country_code) + 1:]
        elif not has_intl_prefix and digits.startswith("0") and len(digits) - 1 == national_length:
            national = digits[1:]
        else:
            national = digits
    else:
        national = digits

    e164 = build_e164(raw_number, numbering)
    e164_digits = e164.lstrip("+")

    candidates = []
    for item in [national, digits, e164_digits, e164, raw]:
        if item and item not in candidates:
            candidates.append(item)
    return digits, national, candidates


def normalize_contact_pattern(pattern: str, numbering: Optional[Dict[str, Any]] = None) -> str:
    """Normalizes a stored contact number or wildcard pattern while preserving * and ? characters."""
    if numbering is None:
        numbering = get_home_numbering()
    raw = (pattern or "").strip()
    cleaned = re.sub(r"[^\d\*\?\+]", "", raw)
    has_intl_prefix = cleaned.startswith("+") or cleaned.startswith("00")
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]

    if not any(w in cleaned for w in ("*", "?")):
        country_code = re.sub(r"\D", "", str(numbering.get("home_country_code", "")))
        try:
            national_length = int(numbering.get("home_national_length", 0))
        except (TypeError, ValueError):
            national_length = 0
        if country_code and national_length > 0:
            if cleaned.startswith(country_code) and len(cleaned) == len(country_code) + national_length:
                cleaned = cleaned[len(country_code):]
            elif cleaned.startswith(country_code + "0") and len(cleaned) == len(country_code) + 1 + national_length:
                cleaned = cleaned[len(country_code) + 1:]
            elif not has_intl_prefix and cleaned.startswith("0") and len(cleaned) - 1 == national_length:
                cleaned = cleaned[1:]
    return cleaned


def monitor_volume_percent() -> int:
    """Monitoring volume (0-100) configured in the control panel."""
    try:
        return max(0, min(100, int(float(get_config("monitor_volume", "100")))))
    except ValueError:
        return 100


def find_sink_input_ids(pactl_listing: str, process_id: int) -> List[str]:
    """Returns the sink-input ids that belong to a process, parsed from `pactl list sink-inputs`."""
    ids = []
    for block in pactl_listing.split("Sink Input #")[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        if re.search(rf'application\.process\.id\s*=\s*"{process_id}"', block):
            ids.append(lines[0].strip())
    return ids


class MonitorWriter:
    """Feeds a monitoring player (pacat) from a bounded queue and a worker thread.

    Writing to a pipe from the asyncio loop blocks the whole call loop whenever the player is slower than
    the incoming audio, which delays microphone reads and recording timestamps. Monitoring is best-effort,
    so chunks are dropped when the queue is full instead of waiting.
    """

    def __init__(self, proc, max_chunks: int = 400):
        self.proc = proc
        self.chunks = queue.Queue(maxsize=max_chunks)
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def write(self, data: bytes) -> None:
        try:
            self.chunks.put_nowait(data)
        except queue.Full:
            try:
                self.chunks.get_nowait()
                self.chunks.put_nowait(data)
            except (queue.Empty, queue.Full):
                pass

    def _run(self) -> None:
        while True:
            try:
                chunk = self.chunks.get(timeout=1.0)
            except queue.Empty:
                if self.proc.poll() is not None:
                    return
                continue
            try:
                self.proc.stdin.write(chunk)
                self.proc.stdin.flush()
            except Exception:
                return


# Call recordings are stored as MP3 when the optional "lameenc" encoder is installed (WAV otherwise).
AUDIO_EXT = ".mp3" if lameenc is not None else ".wav"
MP3_BITRATE_MONO_KBPS = 32
MP3_BITRATE_STEREO_KBPS = 64
MP3_QUALITY = 5
MP3_CHUNK_BYTES = 1 << 20

MEMORY_MODES = ("priority", "disabled", "only_categories", "only_numbers", "only_global")
MEMORY_MODE_ALIASES = {"per_number": "only_numbers", "per_category": "only_categories", "global": "only_global"}


def normalize_memory_mode(value: str) -> str:
    """Maps legacy memory modes to the current ones and falls back to the priority system."""
    mode = MEMORY_MODE_ALIASES.get(value, value)
    return mode if mode in MEMORY_MODES else "priority"


def encode_pcm_to_mp3(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    """Encodes 16-bit little-endian PCM into an MP3 byte string using LAME."""
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BITRATE_STEREO_KBPS if channels == 2 else MP3_BITRATE_MONO_KBPS)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_out_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(MP3_QUALITY)
    frame_bytes = 2 * channels
    pcm = pcm[:len(pcm) - (len(pcm) % frame_bytes)]
    chunk = MP3_CHUNK_BYTES - (MP3_CHUNK_BYTES % frame_bytes)
    out = bytearray()
    for start in range(0, len(pcm), chunk):
        out += encoder.encode(pcm[start:start + chunk])
    out += encoder.flush()
    return bytes(out)


def save_pcm_recording(path: str, pcm: bytes, sample_rate: int, channels: int) -> None:
    """Saves 16-bit PCM as MP3 when the path ends with .mp3 (and the encoder is available), otherwise as WAV."""
    if path.lower().endswith(".mp3") and lameenc is not None:
        tmp_path = path + ".part"
        with open(tmp_path, "wb") as f:
            f.write(encode_pcm_to_mp3(pcm, sample_rate, channels))
        os.replace(tmp_path, path)
        return
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def interleave_to_stereo(left_pcm: bytes, right_pcm: bytes) -> bytes:
    """Interleaves two mono 16-bit PCM tracks into one stereo track (left, right)."""
    frames = min(len(left_pcm), len(right_pcm)) // 2
    left = array.array("h")
    left.frombytes(left_pcm[:frames * 2])
    right = array.array("h")
    right.frombytes(right_pcm[:frames * 2])
    stereo = array.array("h", bytes(frames * 4))
    stereo[0::2] = left
    stereo[1::2] = right
    if sys.byteorder == "big":
        stereo.byteswap()
    return stereo.tobytes()


def match_contact_rule(caller_number: str, numbering: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    """Matches caller_number against contacts (Exact match first, most specific wildcard second)."""
    if numbering is None:
        numbering = get_home_numbering()
    _, _, caller_candidates = normalize_phone_candidates(caller_number, numbering)
    if not caller_candidates:
        return None

    conn = sqlite3.connect(DB_PATH)
    try:
        try:
            rows = conn.execute("SELECT number, type, prompt_rules, tag, note, mem_mode, mem_calls, mem_days FROM contacts").fetchall()
        except sqlite3.OperationalError:
            rows = [tuple(r) + ("", None, None) for r in conn.execute("SELECT number, type, prompt_rules, tag, note FROM contacts").fetchall()]
    except Exception:
        rows = []
    finally:
        conn.close()

    exact_matches = []
    wildcard_matches = []

    for row in rows:
        pat_raw, c_type, prompt_rules, tag, note, mem_mode, mem_calls, mem_days = row
        pat_norm = normalize_contact_pattern(pat_raw, numbering)
        if not pat_norm:
            continue

        entry = {
            "pattern": pat_raw,
            "normalized_pattern": pat_norm,
            "type": c_type or "whitelist",
            "prompt_rules": prompt_rules or "",
            "tag": tag or "",
            "note": note or "",
            "mem_mode": mem_mode or "",
            "mem_calls": mem_calls,
            "mem_days": mem_days
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


def format_spam_url(url_template: str, raw_number: str, numbering: Optional[Dict[str, Any]] = None) -> str:
    """Formats a SPAM lookup URL supporting {number}, {national}, and {e164} (URL-encoded, "+" becomes %2B)."""
    if numbering is None:
        numbering = get_home_numbering()
    digits, national, _ = normalize_phone_candidates(raw_number, numbering)
    e164 = build_e164(raw_number, numbering)

    url = url_template
    # A template that already carries a country code before {number} (e.g. "/num/%2B34{number}") needs the national part only.
    embedded = re.search(r"(?:%2B|\+)(\d{1,3})\{number\}", url)
    number_value = digits
    if embedded and digits.startswith(embedded.group(1)):
        number_value = digits[len(embedded.group(1)):]
    url = url.replace("{number}", number_value)
    url = url.replace("{national}", national)
    url = url.replace("{e164}", urllib.parse.quote(e164, safe=""))
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


def build_accept_language(lang_code: str) -> str:
    """Builds the Accept-Language header from the active language (e.g. "es-ES" -> "es-ES,es;q=0.9,en;q=0.8")."""
    active = lang_code or DEFAULT_LANGUAGE
    primary = active.split("-")[0]
    fallback = DEFAULT_LANGUAGE.split("-")[0]
    header = f"{active},{primary};q=0.9"
    if primary != fallback:
        header += f",{fallback};q=0.8"
    return header


async def fetch_spam_page_async(url: str, http_session: aiohttp.ClientSession, lang_code: str = DEFAULT_LANGUAGE) -> Tuple[int, str]:
    """Fetches a SPAM lookup page using curl_cffi (Chrome TLS), aiohttp, or system curl with browser headers."""
    parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else "https://www.google.com/"
    accept_lang = build_accept_language(lang_code)

    if curl_requests is not None:
        try:
            # Do not override User-Agent when impersonating Chrome: curl_cffi sets matching Chrome headers and TLS fingerprint
            chrome_headers = {
                "Accept-Language": accept_lang,
                "Referer": origin
            }
            resp = await asyncio.to_thread(
                curl_requests.get, url, headers=chrome_headers, impersonate="chrome", timeout=5
            )
            if resp.status_code == 200 and resp.text:
                return resp.status_code, resp.text
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_lang,
        "Referer": origin,
        "Upgrade-Insecure-Requests": "1"
    }

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
    spam_path = os.path.join(LANG_DIR, lang_code, "spam.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                gui_data = json.load(f)
            spam_data = {}
            if os.path.exists(spam_path):
                with open(spam_path, "r", encoding="utf-8") as sf:
                    spam_data = json.load(sf)
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

                default_providers = spam_data.get("providers", [])
                conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (f"{lang_code}_spam_providers", json.dumps(default_providers, ensure_ascii=False)))
                conn.execute("DELETE FROM settings WHERE key='spam_providers'")
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
                  tag TEXT DEFAULT '', note TEXT DEFAULT '',
                  mem_mode TEXT DEFAULT '', mem_calls INTEGER, mem_days INTEGER)''')
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
        "ALTER TABLE contacts ADD COLUMN note TEXT DEFAULT ''",
        "ALTER TABLE contacts ADD COLUMN mem_mode TEXT DEFAULT ''",
        "ALTER TABLE contacts ADD COLUMN mem_calls INTEGER",
        "ALTER TABLE contacts ADD COLUMN mem_days INTEGER"
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
    c.execute("INSERT OR IGNORE INTO settings VALUES ('language', ?)", (DEFAULT_LANGUAGE,))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('allow_pc_mic', 'false')")

    c.execute("INSERT OR IGNORE INTO settings VALUES ('memory_mode', 'priority')")
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
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_silence_duration_ms', ?)", (str(DEFAULT_VAD_SILENCE_DURATION_MS),))
    # One-time migration: the new default replaces the value stored by previous versions (INSERT OR IGNORE never overwrites it)
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_silence_default_migrated', '1')")
    if c.rowcount == 1:
        c.execute("UPDATE settings SET value=? WHERE key='vad_silence_duration_ms'", (str(DEFAULT_VAD_SILENCE_DURATION_MS),))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('protect_initial_greeting', 'true')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('farewell_grace_seconds', '2.0')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('farewell_cancel_min_words', '3')")

    c.execute("INSERT OR REPLACE INTO settings VALUES ('daemon_state', 'running')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('daemon_heartbeat', ?)", (str(time.time()),))

    # Remote access through a private Tor onion service (off unless the user enables it in the GUI)
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_enabled', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_gui_port', '8501')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_notify_port', '8502')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('tor_status', 'off')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('tor_progress', '0')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('tor_onion', '')")
    c.execute("INSERT OR REPLACE INTO settings VALUES ('tor_error', '')")

    conn.commit()
    conn.close()

    try:
        conn = sqlite3.connect(DB_PATH)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else DEFAULT_LANGUAGE
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
        current_lang = res_lang[0] if res_lang else DEFAULT_LANGUAGE

        localized_keys = [
            "boss_name", "assistant_name", "assistant_gender", "owner_type",
            "priority_keywords", "memory_rules", "business_description",
            "expected_calls", "initial_greeting", "extra_prompt", "text_model",
            "spam_providers"
        ]
        if key in localized_keys:
            res = conn.execute("SELECT value FROM settings WHERE key=?", (f"{current_lang}_{key}",)).fetchone()
            if res is not None:
                return res[0]
            if key == "spam_providers":
                return default_value

        res_global = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return res_global[0] if res_global is not None else default_value
    except Exception:
        return default_value
    finally:
        if conn:
            conn.close()


def set_runtime_setting(key: str, value: Any) -> None:
    """Writes a runtime value (status, counters) to the shared SQLite settings table."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def increment_runtime_counter(key: str) -> int:
    """Increments an integer counter stored in the settings table and returns the new value."""
    try:
        current = int(float(get_config(key, "0")))
    except ValueError:
        current = 0
    set_runtime_setting(key, current + 1)
    return current + 1


class BluetoothWatchdog:
    """Keeps the Bluetooth link with the paired phone alive without restarting the switchboard.

    Every cycle it looks at the paired phones that offer the Hands-Free Audio Gateway profile:
      * a phone that is not connected is reconnected with BlueZ (exponential back-off while it is out of range);
      * a phone that is connected but has no oFono modem gets its HFP profile reconnected;
      * oFono modems are powered on and put online again after a reconnection;
      * the Bluetooth adapter is powered on if it was switched off.
    Status and error counters are written to the settings table so the Web GUI can show them."""

    def __init__(self) -> None:
        self.link_state: Dict[str, bool] = {}
        self.backoff_seconds: Dict[str, float] = {}
        self.next_attempt_time: Dict[str, float] = {}
        self.modem_missing_cycles: Dict[str, int] = {}
        self.published_state: Tuple[str, str] = ("", "")

    @staticmethod
    def _mac_token(object_path: str) -> str:
        """Returns the 'AA_BB_CC_DD_EE_FF' part of a BlueZ device path or an oFono modem path."""
        match = re.search(r"dev_([0-9A-Fa-f_]+)", object_path)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _is_paired_phone(props: Any) -> bool:
        if not props.get("Paired", False):
            return False
        return any(str(uuid).lower() == BT_HFP_AG_UUID for uuid in props.get("UUIDs", []))

    @staticmethod
    def _record_event(code: str, detail: str = "") -> None:
        """Stores the last event as 'code|HH:MM:SS|detail'; the Web GUI translates the code."""
        set_runtime_setting("bt_last_event", f"{code}|{get_timestamp()}|{detail}")

    def _publish_state(self, state: str, device_name: str) -> None:
        if (state, device_name) != self.published_state:
            self.published_state = (state, device_name)
            set_runtime_setting("bt_state", state)
            set_runtime_setting("bt_device_name", device_name)

    def _ensure_adapters_powered(self, bus: Any, objects: Any) -> None:
        for path, interfaces in objects.items():
            adapter = interfaces.get("org.bluez.Adapter1")
            if adapter is not None and not adapter.get("Powered", False):
                try:
                    props_iface = dbus.Interface(bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
                    props_iface.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Adapter {path} was powered off. Powered on again.{_R}")
                except Exception as e:
                    print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Bluetooth] Could not power on adapter {path}: {e}{_R}")

    def _ofono_modem_tokens(self, bus: Any) -> set:
        """Returns the device tokens of the oFono modems, powering on and putting online any that are not."""
        tokens = set()
        try:
            manager = dbus.Interface(bus.get_object("org.ofono", "/"), "org.ofono.Manager")
            modems = manager.GetModems()
        except Exception:
            return tokens
        for modem_path, modem_props in modems:
            tokens.add(self._mac_token(str(modem_path)))
            try:
                modem = dbus.Interface(bus.get_object("org.ofono", modem_path), "org.ofono.Modem")
                if not modem_props.get("Powered", False):
                    modem.SetProperty("Powered", dbus.Boolean(True))
                    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] oFono modem powered on: {modem_path}{_R}")
                if not modem_props.get("Online", False):
                    modem.SetProperty("Online", dbus.Boolean(True))
                    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] oFono modem set online: {modem_path}{_R}")
            except Exception:
                pass
        return tokens

    def _connect_phone(self, bus: Any, device_path: str, device_name: str) -> None:
        """Asks BlueZ to connect the HFP profile of the phone and updates the back-off and the counters."""
        now = time.time()
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_CONN}[Bluetooth] Trying to reconnect {device_name}...{_R}")
        try:
            device = dbus.Interface(bus.get_object("org.bluez", device_path), "org.bluez.Device1")
            try:
                device.ConnectProfile(BT_HFP_AG_UUID, timeout=BT_CONNECT_TIMEOUT_SECONDS)
            except dbus.exceptions.DBusException as e:
                if e.get_dbus_name() in ("org.bluez.Error.NotAvailable", "org.bluez.Error.NotSupported"):
                    device.Connect(timeout=BT_CONNECT_TIMEOUT_SECONDS)
                else:
                    raise
            self.backoff_seconds.pop(device_path, None)
            self.next_attempt_time[device_path] = now + BT_WATCHDOG_INTERVAL_SECONDS
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] Reconnection request accepted for {device_name}.{_R}")
        except Exception as e:
            error_name = e.get_dbus_name() if hasattr(e, "get_dbus_name") else ""
            error_text = e.get_dbus_message() if hasattr(e, "get_dbus_message") else str(e)
            if error_name == "org.bluez.Error.AlreadyConnected":
                return
            backoff = min(
                BT_RECONNECT_BACKOFF_MAX_SECONDS,
                max(BT_RECONNECT_BACKOFF_MIN_SECONDS, self.backoff_seconds.get(device_path, BT_RECONNECT_BACKOFF_MIN_SECONDS / 2) * 2)
            )
            self.backoff_seconds[device_path] = backoff
            self.next_attempt_time[device_path] = now + backoff
            if error_name != "org.bluez.Error.InProgress":
                total = increment_runtime_counter("bt_failed_attempts_count")
                self._record_event("failed", error_text)
                print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Bluetooth] Reconnection of {device_name} failed ({error_text}). "
                      f"Failed attempts: {total}. Next attempt in {int(backoff)}s.{_R}")

    def _check_phone(self, bus: Any, device_path: str, props: Any, modem_tokens: set) -> bool:
        """Checks one paired phone and returns True if it is connected."""
        device_name = str(props.get("Alias") or props.get("Name") or device_path)
        connected = bool(props.get("Connected", False))
        previous = self.link_state.get(device_path)
        self.link_state[device_path] = connected
        now = time.time()

        if not props.get("Trusted", False):
            try:
                props_iface = dbus.Interface(bus.get_object("org.bluez", device_path), "org.freedesktop.DBus.Properties")
                props_iface.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
            except Exception:
                pass

        if connected:
            if previous is False:
                total = increment_runtime_counter("bt_restored_count")
                self._record_event("restored", device_name)
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Bluetooth] {device_name} is connected again. Restored connections: {total}.{_R}")
            self.backoff_seconds.pop(device_path, None)

            if self._mac_token(device_path) in modem_tokens:
                self.modem_missing_cycles[device_path] = 0
            else:
                cycles = self.modem_missing_cycles.get(device_path, 0) + 1
                self.modem_missing_cycles[device_path] = cycles
                if cycles >= BT_MODEM_MISSING_CYCLES and now >= self.next_attempt_time.get(device_path, 0.0):
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] {device_name} is connected but has no oFono modem. Reconnecting its HFP profile.{_R}")
                    self._connect_phone(bus, device_path, device_name)
            return True

        if previous is True:
            total = increment_runtime_counter("bt_lost_count")
            self._record_event("lost", device_name)
            self.next_attempt_time[device_path] = 0.0
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Connection with {device_name} lost. Lost connections: {total}.{_R}")

        self.modem_missing_cycles[device_path] = 0
        if now >= self.next_attempt_time.get(device_path, 0.0):
            self._connect_phone(bus, device_path, device_name)
        return False

    def check_once(self) -> None:
        """Runs one watchdog cycle. It is blocking (D-Bus), so the caller runs it in a worker thread."""
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
        self._ensure_adapters_powered(bus, objects)

        phones = [
            (str(path), interfaces["org.bluez.Device1"])
            for path, interfaces in objects.items()
            if "org.bluez.Device1" in interfaces and self._is_paired_phone(interfaces["org.bluez.Device1"])
        ]
        if not phones:
            self._publish_state("no_device", "")
            return

        modem_tokens = self._ofono_modem_tokens(bus)
        connected_name = ""
        first_name = ""
        for device_path, props in phones:
            name = str(props.get("Alias") or props.get("Name") or device_path)
            first_name = first_name or name
            if self._check_phone(bus, device_path, props, modem_tokens) and not connected_name:
                connected_name = name

        if connected_name:
            self._publish_state("connected", connected_name)
        else:
            self._publish_state("disconnected", first_name)


async def bluetooth_watchdog_loop() -> None:
    """Runs the Bluetooth watchdog while the daemon is alive (also when the switchboard is paused).
    It stays idle during a call so it never interferes with the audio link."""
    watchdog = BluetoothWatchdog()
    loop = asyncio.get_running_loop()
    last_error = ""
    while True:
        try:
            state = get_config("daemon_state", "running")
            call_active = ACTIVE_ASSISTANT is not None and getattr(ACTIVE_ASSISTANT, "running", False)
            if state != "stopped" and not call_active:
                await loop.run_in_executor(None, watchdog.check_once)
                last_error = ""
        except Exception as e:
            if str(e) != last_error:
                last_error = str(e)
                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Watchdog error: {e}{_R}")
        await asyncio.sleep(BT_WATCHDOG_INTERVAL_SECONDS)


def load_language_data(lang_code: str, file_name: str = "assistant.json") -> dict:
    path = os.path.join(LANG_DIR, lang_code, file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def is_female_gender(gender_value: str, gui_data: dict) -> bool:
    """Language-neutral gender check: the first entry of "gender_types" in gui.json is the female option."""
    gender_types = gui_data.get("gender_types", []) if gui_data else []
    if gender_value in gender_types:
        return gender_types.index(gender_value) == 0
    return str(gender_value).lower().startswith(("fem", "fém"))


def pick_role_text(role_map: dict, is_female: bool, default: str) -> str:
    """Language-neutral lookup of the role text: tolerates localized keys (e.g. 'femenino'/'masculino')."""
    if not role_map:
        return default
    canonical = "female" if is_female else "male"
    if canonical in role_map:
        return role_map[canonical]
    keys = list(role_map.keys())
    fem_key = next((k for k in keys if k.lower().startswith(("fem", "fém"))), None)
    if is_female:
        return role_map.get(fem_key, default) if fem_key else default
    male_key = next((k for k in keys if k != fem_key), None)
    return role_map.get(male_key, default) if male_key else default


def pick_owner_text(owner_map: dict, owner_type: str, default: str) -> str:
    """Language-neutral lookup of the owner description: exact key first, then by canonical position."""
    if not owner_map:
        return default
    if owner_type in owner_map:
        return owner_map[owner_type]
    canonical_order = ["private", "professional", "business"]
    values = list(owner_map.values())
    if owner_type in canonical_order:
        idx = canonical_order.index(owner_type)
        if idx < len(values):
            return values[idx]
    return default


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


def matches_any_phrase(text: str, phrases: list) -> bool:
    """True if any phrase appears in text: multi-word phrases as substrings, single words on word boundaries."""
    t = text.replace("\u2019", "'").replace("\u2018", "'").lower()
    for phrase in phrases:
        phrase_l = phrase.replace("\u2019", "'").lower().strip()
        if not phrase_l:
            continue
        if " " in phrase_l:
            if phrase_l in t:
                return True
        else:
            if re.search(r"(?<![a-záéíóúñüàèìòùâêîôûäëïöüãõ])" + re.escape(phrase_l) + r"(?![a-záéíóúñüàèìòùâêîôûäëïöüãõ])", t):
                return True
    return False


def strip_quoted_text(text: str) -> str:
    """Removes quoted fragments: a word between quotes is being mentioned (listed, cited), not said."""
    t = re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d|\u00ab[^\u00bb]*\u00bb', " ", text)
    return re.sub(r"(?<!\w)['\u2018][^'\u2019]{1,60}?['\u2019](?!\w)", " ", t)


def find_farewell(text: str, farewell_words: list, veto_words: list, meta_words: list = ()) -> bool:
    """True when the text holds a real farewell: a farewell word that is neither quoted, nor in a sentence that
    talks about words/commands/examples (meta words, whole sentence), nor in a clause with a negation or
    conditional (veto words, same clause only). Without veto and meta words it is a plain farewell match.

    Examples of what is NOT a farewell: 'I will not hang up', 'if you say goodbye as part of a test',
    'examples include phrases like goodbye, or have a good day', 'words like "bye" or "see you"'.
    """
    if not farewell_words:
        return False
    text = strip_quoted_text(text)
    if not veto_words and not meta_words:
        return matches_any_phrase(text, farewell_words)
    for sentence in re.split(r"[.!?¿¡…\n]+", text):
        if not sentence.strip() or (meta_words and matches_any_phrase(sentence, meta_words)):
            continue
        for clause in re.split(r"[,;:]+", sentence):
            clause = clause.strip()
            if clause and matches_any_phrase(clause, farewell_words) and not matches_any_phrase(clause, veto_words):
                return True
    return False


def clean_ai_text(text: str) -> str:
    """Removes command artifacts leaked into the model transcription (tool-call tokens and <no speech> markers).

    Ordinary words such as "call" or "start" are kept; they are only removed when part of a command token.
    """
    t = re.sub(r"start\s*\{.*?\}\s*endcall", "", text, flags=re.IGNORECASE)
    t = re.sub(r"start\s*\{.*?\}", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\{.*?\}", "", t)
    t = re.sub(r"<[^<>\n]{1,40}>", "", t)
    t = re.sub(r"<?\s*\b(?:no\s+speech(?:\s+detected)?|noise\s+detected|speech\s+detected)\b\s*>?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[<>]", "", t)
    t = re.sub(r"\bcall\s*:\s*\w+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:call|start)\s*(?=[{(])", "", t, flags=re.IGNORECASE)
    return re.sub(r"\b(hangup|endcall)\b", "", t, flags=re.IGNORECASE)


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
        self.running = False
        self._post_processed = False

        self.boss_name = get_config("boss_name", "Boss")
        self.owner_type = get_config("owner_type", "private")
        self.business_description = get_config("business_description", "")
        self.expected_calls = get_config("expected_calls", "")
        self.assistant_name = get_config("assistant_name", "Assistant")
        self.assistant_gender = get_config("assistant_gender", "female")
        self.current_lang = get_config("language", DEFAULT_LANGUAGE)

        self.assistant_data = load_language_data(self.current_lang, "assistant.json")
        self.gui_data = load_language_data(self.current_lang, "gui.json")
        self.spam_data = load_language_data(self.current_lang, "spam.json")
        self.words_data = self.assistant_data.get("words", {})
        self.prompts_data = self.assistant_data.get("inline_prompts", {})
        self.labels_data = self.assistant_data.get("labels", {})

        self.digits_number, self.national_number, self.caller_candidates = normalize_phone_candidates(caller_number, self.spam_data)

        mac_match = re.search(r"dev_([0-9A-Z_]+)", dbus_path)
        if mac_match:
            mac_str = mac_match.group(1)
            self.pw_record_target = f"bluez_input.{mac_str}.0"
            self.pw_playback_target = f"bluez_output.{mac_str}.1"
        else:
            self.pw_record_target = DEFAULT_PW_INPUT
            self.pw_playback_target = DEFAULT_PW_OUTPUT

        self.policy_engine = CallPolicyEngine(owner_name=self.boss_name, parent=self)

        self.accumulated_transcript = ""
        self.call_id = None
        self.last_speaker = None
        self.hanging_up = False
        self.forced_goodbye_active = False
        self.hangup_source = ""

        self._asst_chunk_buffer = ""
        self._asst_chunk_last_time = 0.0
        self._in_angle_tag = False

        self.hello_question_sent = False
        self.cutoff_sent = False
        self.hangup_triggered = False
        self.hangup_triggered_time = 0.0
        self.hangup_reason = "completed"
        self.hangup_message_appended = False

        # Pending farewell: a farewell word was detected in the assistant's current turn. The call is only cut once
        # the audio has finished, the farewell still stands in the full turn text and the caller had a grace time.
        self.farewell_pending = False
        self.farewell_drained_since = 0.0
        self._asst_turn_text = ""
        self._asst_turn_last_time = 0.0
        try:
            self.farewell_grace_seconds = float(get_config("farewell_grace_seconds", "2.0"))
        except ValueError:
            self.farewell_grace_seconds = 2.0
        try:
            self.farewell_cancel_min_words = int(get_config("farewell_cancel_min_words", "3"))
        except ValueError:
            self.farewell_cancel_min_words = 3

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
        self.playback_end_time = 0.0  # Estimated moment when everything written to the speaker path has been played
        self._routing_diag_logged = False
        self._removed_loop_links = set()
        self._monitor_volume_applied = {}
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
            self.vad_silence_duration_ms = int(get_config("vad_silence_duration_ms", str(DEFAULT_VAD_SILENCE_DURATION_MS)))
        except ValueError:
            self.vad_silence_duration_ms = DEFAULT_VAD_SILENCE_DURATION_MS

        self.final_transcription_mode = get_config("final_transcription_mode", "disabled")

        w_model = get_config("whisper_model", "medium")
        w_quant = get_config("whisper_quant", "")
        self.whisper_full_model = f"{w_model}{w_quant}"

        self.model_text = get_config("text_model", "gemini-3-flash-preview")

        recordings_dir = os.path.join(BASE_DIR, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_path = os.path.join(recordings_dir, f"call_{self.national_number or caller_number}_{ts_str}{AUDIO_EXT}")
        self.client_recording_path = os.path.join(recordings_dir, f"call_{self.national_number or caller_number}_{ts_str}_client{AUDIO_EXT}")

        self.client_text = genai.Client(api_key=API_KEY)
        self.client_live = genai.Client(api_key=API_KEY, http_options={"api_version": "v1alpha"})

        self.last_call_json = {
            "caller_type": "unknown", "risk_score": 0, "insult_detected": False,
            "private_data_requested": False, "caller_name": "", "company": "",
            "summary": "", "response_text": ""
        }

    @staticmethod
    def _find_memory_category(target_tag: str) -> Optional[Dict[str, Any]]:
        """Returns the first category rule whose name or keywords match the given tag."""
        if not target_tag:
            return None
        try:
            mem_rules = json.loads(get_config("memory_rules", "[]"))
        except Exception:
            return None
        tag_low = target_tag.lower()
        for rule in mem_rules:
            cat_name = rule.get("category", "").lower()
            if cat_name and (cat_name in tag_low or any(kw in tag_low for kw in rule.get("keywords", []))):
                return rule
        return None

    def build_memory_context(self, contact_match: Optional[Dict[str, str]]) -> str:
        """Builds historical call context. Priority system: number rule > category rule > default (this number)."""
        memory_mode = normalize_memory_mode(get_config("memory_mode", "priority"))
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

        # Level 1: rule attached to the number (exact contact or wildcard)
        number_rule_custom = False
        if memory_mode in ("priority", "only_numbers") and contact_match:
            number_rule_mode = (contact_match.get("mem_mode") or "").strip()
            if number_rule_mode == "none":
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[Memory] Disabled by the rule of this number.{_R}")
                return ""
            if number_rule_mode == "custom":
                number_rule_custom = True
                try:
                    if contact_match.get("mem_calls"):
                        max_calls = max(1, int(contact_match["mem_calls"]))
                    if contact_match.get("mem_days"):
                        max_days = max(1, int(contact_match["mem_days"]))
                except (TypeError, ValueError):
                    pass

        if memory_mode == "only_global":
            scope = "global"
        elif memory_mode == "only_categories":
            scope = "category"
        elif memory_mode == "priority" and not number_rule_custom:
            scope = "auto"
        else:
            scope = "number"

        in_progress_lbl = self.gui_data.get("ui_in_progress", "IN PROGRESS")
        spam_lbl = self.labels_data.get("spam", "SPAM")

        conn = sqlite3.connect(DB_PATH)
        rows = []
        try:
            placeholders = ",".join(["?"] * len(self.caller_candidates)) if self.caller_candidates else "'__none__'"
            valid_filter = "AND COALESCE(transcript, '') != '' AND COALESCE(tag, '') != ? AND COALESCE(tag, '') != 'IN PROGRESS' AND COALESCE(summary, '') NOT LIKE 'Blocked by rule%'"

            # Level 2: category rule (tag of the contact rule or tag of the previous call of this number)
            target_tag = ""
            if scope in ("auto", "category"):
                target_tag = (contact_match or {}).get("tag", "").strip()
                if not target_tag and self.caller_candidates:
                    prev_tag_row = conn.execute(
                        f"SELECT tag FROM calls WHERE id != ? AND number IN ({placeholders}) {valid_filter} ORDER BY id DESC LIMIT 1",
                        [self.call_id or -1] + self.caller_candidates + [in_progress_lbl]
                    ).fetchone()
                    if prev_tag_row and prev_tag_row[0]:
                        target_tag = prev_tag_row[0]

                category_rule = self._find_memory_category(target_tag)
                if category_rule:
                    try:
                        max_days = max(1, int(category_rule.get("days", max_days)))
                        if category_rule.get("calls"):
                            max_calls = max(1, int(category_rule["calls"]))
                        if category_rule.get("chars"):
                            max_chars = max(300, int(category_rule["chars"]))
                    except (TypeError, ValueError):
                        pass
                if scope == "auto":
                    scope = "category" if category_rule else "number"

            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[Memory] Mode={memory_mode} Scope={scope} Calls={max_calls} Days={max_days} Chars={max_chars}{_R}")

            cutoff_str = (datetime.datetime.now() - datetime.timedelta(days=max_days)).strftime("%Y-%m-%d %H:%M:%S")

            # Level 3 (default) and number scope: history of this phone number
            if scope == "number" and self.caller_candidates:
                query = (
                    f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                    f"WHERE id != ? AND number IN ({placeholders}) AND date >= ? {valid_filter} "
                    f"ORDER BY id DESC LIMIT ?"
                )
                params = [self.call_id or -1] + self.caller_candidates + [cutoff_str, in_progress_lbl, max_calls]
                rows = conn.execute(query, params).fetchall()

            elif scope == "category":
                if target_tag:
                    rows = conn.execute(
                        f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                        f"WHERE id != ? AND tag = ? AND date >= ? {valid_filter} ORDER BY id DESC LIMIT ?",
                        (self.call_id or -1, target_tag, cutoff_str, in_progress_lbl, max_calls)
                    ).fetchall()
                elif self.caller_candidates:
                    query = (
                        f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                        f"WHERE id != ? AND number IN ({placeholders}) AND date >= ? {valid_filter} "
                        f"ORDER BY id DESC LIMIT ?"
                    )
                    rows = conn.execute(query, [self.call_id or -1] + self.caller_candidates + [cutoff_str, in_progress_lbl, max_calls]).fetchall()

            elif scope == "global":
                rows = conn.execute(
                    f"SELECT date, number, client_name, company, tag, summary, transcript FROM calls "
                    f"WHERE id != ? AND date >= ? AND spam_score < 65 AND tag != ? AND tag NOT LIKE '%SPAM%' {valid_filter} "
                    f"ORDER BY id DESC LIMIT ?",
                    (self.call_id or -1, cutoff_str, spam_lbl, in_progress_lbl, max_calls)
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

        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[SpamCheck] AI evaluating {self.caller_number} (Normalized: {self.national_number}) across databases...{_R}")

        providers_json = get_config("spam_providers", "")
        providers = []
        if providers_json:
            try:
                providers = json.loads(providers_json)
            except Exception:
                providers = []
        if not providers:
            providers = self.spam_data.get("providers", [])

        schema = {
            "type": "object",
            "properties": {"is_spam": {"type": "boolean"}, "risk_score": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["is_spam", "risk_score"]
        }

        highest_score = 0
        best_reason = "No negative reports found"

        async with aiohttp.ClientSession() as http_session:
            for url_template in providers:
                url = format_spam_url(url_template, self.caller_number, self.spam_data)
                try:
                    status_code, html = await fetch_spam_page_async(url, http_session, self.current_lang)
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
                        ["pacat", "--format=s16le", "--rate=24000", "--channels=1", "--raw", f"--volume={monitor_volume_percent() * 65536 // 100}"],
                        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
                    )
            else:
                if self.asst_pacat and self.asst_pacat.poll() is None:
                    self.asst_pacat.terminate()
                    self.asst_pacat = None

            if mode in ["both", "caller"]:
                if self.caller_pacat is None or self.caller_pacat.poll() is not None:
                    sink = get_default_sink()
                    cmd = ["pacat", "--format=s16le", "--rate=16000", "--channels=1", "--raw", f"--volume={monitor_volume_percent() * 65536 // 100}"]
                    cmd.append(f"--device={sink}" if sink else "--device=auto_null")
                    self.caller_pacat = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            else:
                if self.caller_pacat and self.caller_pacat.poll() is None:
                    self.caller_pacat.terminate()
                    self.caller_pacat = None

            volume_pct = monitor_volume_percent()
            for player in (self.asst_pacat, self.caller_pacat):
                if player and player.poll() is None and self._monitor_volume_applied.get(player.pid) != volume_pct:
                    if await self._apply_player_volume(player.pid, volume_pct):
                        self._monitor_volume_applied[player.pid] = volume_pct

            removed_link = False
            phone_output_base = re.sub(r"\.\d+$", "", self.pw_playback_target)
            try:
                proc = await asyncio.create_subprocess_exec("pw-link", "-l", "--id", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await proc.communicate()
                text = out.decode("utf-8", errors="ignore")
                if not self._routing_diag_logged:
                    bluez_lines = [ln.rstrip() for ln in text.splitlines() if "bluez" in ln]
                    if bluez_lines:
                        self._routing_diag_logged = True
                        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[Routing] Bluetooth links at call start:{_R}")
                        for ln in bluez_lines:
                            print(f"{_C_MUTED}    {ln}{_R}")
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
                            await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        if dst_name.startswith(phone_output_base) and (src_name.startswith("auto_null") or "bluez_input" in src_name):
                            # The caller's audio must never return to the phone's output node, either directly or through the
                            # monitor of the null sink (bluez_input -> auto_null -> auto_null:monitor -> phone output).
                            # Other Bluetooth outputs (for example monitoring speakers) are left untouched.
                            removed_link = True
                            await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                            if link_id not in self._removed_loop_links:
                                self._removed_loop_links.add(link_id)
                                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Routing] Removed echo loop link {src_name} -> {dst_name}{_R}")
                            continue
                        if "bluez_input" in src_name and mode not in ["both", "caller"]:
                            sink = get_default_sink()
                            # Never touch links to the persistent auto_null sink (clock source on SBCs with disabled onboard audio)
                            if "auto_null" not in dst_name and (("alsa_output" in dst_name) or (sink and sink in dst_name)):
                                await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            except Exception:
                pass

            # Re-check quickly after removing a link in case the session manager recreates it; relaxed polling otherwise.
            await asyncio.sleep(0.5 if removed_link else 2.0)

        for pacat in [self.caller_pacat, self.asst_pacat]:
            if pacat:
                try:
                    if pacat.stdin:
                        pacat.stdin.close()
                    pacat.kill()
                    pacat.wait()
                except Exception:
                    pass

    @staticmethod
    async def _apply_player_volume(process_id: int, volume_pct: int) -> bool:
        """Sets the volume of the monitoring stream that belongs to a pacat process (other audio is untouched)."""
        try:
            proc = await asyncio.create_subprocess_exec("pactl", "list", "sink-inputs", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await proc.communicate()
            stream_ids = find_sink_input_ids(out.decode("utf-8", errors="ignore"), process_id)
            for stream_id in stream_ids:
                setter = await asyncio.create_subprocess_exec("pactl", "set-sink-input-volume", stream_id, f"{volume_pct}%", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await setter.wait()
            return bool(stream_ids)
        except Exception:
            return False

    @staticmethod
    def _monitor_write(player, data: bytes) -> None:
        """Queues audio for a monitoring player without ever blocking the call loop."""
        if not player or player.poll() is not None:
            return
        writer = getattr(player, "monitor_writer", None)
        if writer is None:
            writer = MonitorWriter(player)
            player.monitor_writer = writer
        writer.write(data)

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

                    self._monitor_write(self.caller_pacat, amplified_data)

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

    def is_playback_drained(self) -> bool:
        """True when the model's audio has really finished playing. The audio queue is empty long before that:
        the model streams faster than real time and PipeWire / the Bluetooth link buffer the rest, so the
        end of playback is estimated from the amount of audio written, plus a tail for the Bluetooth latency."""
        now = time.time()
        return (
            self.audio_out_queue.empty()
            and now - self.last_chunk_audio_time > HANGUP_STREAM_QUIET_SECONDS
            and now >= self.playback_end_time + HANGUP_AUDIO_TAIL_SECONDS
        )

    async def wait_for_playback_drain(self, max_wait: float = HANGUP_MAX_WAIT_SECONDS) -> None:
        """Waits (bounded) until the audio that is still being played has finished."""
        deadline = time.time() + max_wait
        while time.time() < deadline and not self.is_playback_drained():
            await asyncio.sleep(0.1)

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
                        self.playback_end_time = max(self.playback_end_time, self.last_chunk_audio_time) + len(chunk) / PLAYBACK_BYTES_PER_SECOND
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

    def _strip_foreign_words(self, text: str) -> str:
        """Removes words listed as foreign noise for the current language; returns "" if nothing is left."""
        foreign = set(self.words_data.get("foreign_noise", []))
        if not foreign:
            return text
        kept = [w for w in text.split() if w.strip(".,;:!?¿¡\"'()[]").lower() not in foreign]
        return " ".join(kept).strip()

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

    def _strip_streamed_angle_tags(self, text: str) -> str:
        """Strips <...> tags from streamed output chunks even when a tag is split across two or more chunks."""
        out = []
        i = 0
        n = len(text)
        while i < n:
            if self._in_angle_tag:
                close_idx = text.find(">", i)
                if close_idx == -1:
                    return "".join(out)
                self._in_angle_tag = False
                i = close_idx + 1
            else:
                open_idx = text.find("<", i)
                if open_idx == -1:
                    out.append(text[i:])
                    break
                if open_idx > i:
                    out.append(text[i:open_idx])
                close_idx = text.find(">", open_idx + 1)
                if close_idx == -1:
                    self._in_angle_tag = True
                    break
                i = close_idx + 1
        return "".join(out)

    def _is_assistant_placeholder(self, text: str) -> bool:
        """True when assistant output has no real words (dots, ellipsis, <no speech detected>) or is only a configured placeholder phrase."""
        normalized = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).strip().lower()
        if not normalized or normalized in ("no speech", "no speech detected", "detected", "noise detected", "speech detected"):
            return True
        return normalized in set(self.words_data.get("assistant_placeholder_phrases", []))

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
        return matches_any_phrase(text, phrases)

    def _is_farewell(self, text: str) -> bool:
        """True when the text holds a real farewell (farewell word neither denied nor merely mentioned)."""
        return find_farewell(text, self.words_data.get("cut_words", []), self.words_data.get("goodbye_veto_words", []), self.words_data.get("goodbye_meta_words", []))

    def _cancel_pending_farewell(self, reason: str) -> None:
        self.farewell_pending = False
        self.farewell_drained_since = 0.0
        self._asst_chunk_buffer = ""
        print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Pending farewell cancelled ({reason}).{_R}")

    def _commit_farewell_hangup(self, reason: str) -> None:
        self.farewell_pending = False
        self.farewell_drained_since = 0.0
        self.hanging_up = self.hangup_triggered = True
        self.hangup_triggered_time = time.time()
        self.hangup_source = "cut_words"
        self.hangup_reason = "completed"
        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Farewell confirmed ({reason}). Initiating clean call cut...{_R}")

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
            exact_template = self.prompts_data.get(
                "greeting_exact",
                "[SYSTEM: Start the call by saying EXACTLY this phrase, word by word, without adding anything else: '{phrase}']"
            )
            try:
                greeting = exact_template.format(phrase=initial_greeting)
            except (KeyError, ValueError, IndexError):
                greeting = exact_template.replace("{phrase}", initial_greeting)
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
            if self.farewell_pending and not self.hanging_up:
                if self.is_playback_drained():
                    if self.farewell_drained_since <= 0.0:
                        self.farewell_drained_since = time.time()
                    elif time.time() - self.farewell_drained_since >= self.farewell_grace_seconds:
                        if self._is_farewell(self._asst_turn_text):
                            self._commit_farewell_hangup("no caller reply after the farewell")
                        else:
                            self._cancel_pending_farewell("the farewell no longer stands in the full turn")
                else:
                    self.farewell_drained_since = 0.0

            if self.hanging_up:
                if self.hangup_triggered_time <= 0.0:
                    self.hangup_triggered_time = time.time()
                if self.is_playback_drained() or time.time() - self.hangup_triggered_time > HANGUP_MAX_WAIT_SECONDS:
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
                    cleaned_caller_txt = re.sub(r"<[^<>\n]{1,40}>", "", cleaned_caller_txt or "")
                    cleaned_caller_txt = self._strip_foreign_words(cleaned_caller_txt)
                    if not cleaned_caller_txt or not self.is_valid_text(cleaned_caller_txt) or self._is_transcription_noise(cleaned_caller_txt):
                        itx = None
                    else:
                        itx.text = cleaned_caller_txt

                if itx and getattr(itx, "text", None):
                    self.last_user_spoke_time = time.time()
                    self.hello_question_sent = self.cutoff_sent = False
                    self._in_angle_tag = False

                    if self.farewell_pending:
                        if self._is_farewell(itx.text):
                            self._commit_farewell_hangup("caller also said goodbye")
                        elif len(itx.text.split()) >= self.farewell_cancel_min_words:
                            self._cancel_pending_farewell("caller kept talking")
                    self._asst_turn_text = ""

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
                        self.last_speaker = None
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
                                self._monitor_write(self.asst_pacat, inline_data.data)
                                self.last_chunk_audio_time = time.time()
                                self.cutoff_sent = False
                        except Exception:
                            pass

                otx = getattr(sc, "output_transcription", None)
                if otx and getattr(otx, "text", None):
                    self.user_turn_audio.clear()
                    tag_stripped = self._strip_streamed_angle_tags(otx.text)
                    clean_otx = clean_ai_text(tag_stripped) if tag_stripped else ""
                    if clean_otx and self._is_assistant_placeholder(clean_otx):
                        # Placeholder utterance (e.g. "..." or "Nothing" or "<no speech detected>"): keep it out of the transcript and the memory
                        clean_otx = ""
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

                        now_turn = time.time()
                        if now_turn - self._asst_turn_last_time < ASSISTANT_TURN_GAP_SECONDS:
                            self._asst_turn_text += " " + clean_otx
                        else:
                            self._asst_turn_text = clean_otx
                        self._asst_turn_last_time = now_turn

                        # The farewell is judged on the whole assistant turn (not only the latest chunk): the clause that
                        # holds the farewell word can still grow into an explanation or a denial in later chunks.
                        farewell_now = self._is_farewell(self._asst_turn_text)
                        if farewell_now and not self.hangup_triggered and not self.farewell_pending and not self.waiting_definitive_cut and not self.hello_question_sent:
                            self.farewell_pending = True
                            self.farewell_drained_since = 0.0
                            print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Goodbye detected in assistant text. Waiting for the audio to finish and the caller's reply...{_R}")
                        elif self.farewell_pending and not self.hanging_up:
                            if not farewell_now:
                                self._cancel_pending_farewell("farewell word is part of an explanation or was denied")
                            elif self._matches_any_phrase(eval_text, self.words_data.get("cancel_goodbye_phrases", [])) and not self._is_farewell(eval_text):
                                self._cancel_pending_farewell("assistant asked if there is anything else")

                        if self.hanging_up and self.hangup_source == "cut_words":
                            cancel_phrases = self.words_data.get("cancel_goodbye_phrases", [])
                            has_goodbye = self._is_farewell(eval_text)
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
        template = self.assistant_data.get("transcript_fix_whisper_prompt") or (
            "We have two transcriptions of a call held in the language with code {lang}:\n1. LIVE TRANSCRIPT (📞 correct, 🗣 may have noise).\n2. RAW WHISPER (🗣 only).\n"
            "Task: Align and correct 🗣 parts in LIVE TRANSCRIPT using RAW WHISPER. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
            "Write everything in the call language and treat words in any other language as noise. If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\n"
            "LIVE TRANSCRIPT:\n{live_transcript}\n\nRAW WHISPER:\n{raw_whisper}"
        )
        prompt = template.replace("{lang}", self.current_lang).replace("{live_transcript}", self.accumulated_transcript).replace("{raw_whisper}", raw_whisper)
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
            audio_mime = "audio/mp3" if wav_path.lower().endswith(".mp3") else "audio/wav"
            template = self.assistant_data.get("transcript_fix_audio_prompt") or (
                "Task: the call is held in the language with code {lang}. Align and correct 🗣 parts in LIVE TRANSCRIPT by listening to audio. Format: 🗣 [HH:MM:SS]: [Live]: <text> | [Final ASR]: <corrected>\n"
                "Write everything in the call language and treat words in any other language as noise. If noise, write [Noise Filtered]. Output ONLY formatted dialogue.\nLIVE TRANSCRIPT:\n{live_transcript}"
            )
            prompt = template.replace("{lang}", self.current_lang).replace("{live_transcript}", self.accumulated_transcript)
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                resp = await asyncio.to_thread(
                    self.client_text.models.generate_content,
                    model=model_to_use,
                    contents=[types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime), prompt],
                    config=types.GenerateContentConfig(temperature=0.1)
                )
            return extract_response_text(resp, default=self.accumulated_transcript)
        except Exception:
            return self.accumulated_transcript

    async def post_process_call(self) -> None:
        if not getattr(self, "answered_call", False):
            contact_match = match_contact_rule(self.caller_number, self.spam_data)
            final_tag = (contact_match or {}).get("tag", "").strip() or self.labels_data.get("general", "GENERAL")
            client_n = (contact_match or {}).get("note", "").strip()
            unanswered_trans = f"❌ [{get_timestamp()}]: [SYSTEM]: Call ended by caller before answering."
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE calls SET duration=0, tag=?, client_name=?, transcript=?, audio_path='', client_audio_path='', summary='' WHERE id=?",
                (final_tag, client_n, unanswered_trans, self.call_id)
            )
            conn.commit()
            conn.close()
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Post-Processing] Unanswered call recorded.{_R}")
            return

        print(f"\n{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Saving recordings, generating summary, and evaluating categories...{_R}")

        caller_pcm_raw = b"".join(self.caller_recording_buffer) if self.caller_recording_buffer else b""
        asst_pcm_raw = bytes(self.recording_buffer_wav)

        client_pcm_snapshot = caller_pcm_raw
        if self._total_mic_silence_injected > 0:
            print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_INFO}[Audio] Silence inserted into the caller track: {self._total_mic_silence_injected:.1f}s{_R}")

        if caller_pcm_raw:
            try:
                await asyncio.to_thread(save_pcm_recording, self.client_recording_path, caller_pcm_raw, 16000, 1)
            except Exception as e:
                print(f"{_C_WARN}[{get_timestamp()}] Error saving caller audio: {e}{_R}")

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

                stereo_pcm = interleave_to_stereo(caller_pcm, asst_pcm_raw)
                await asyncio.to_thread(save_pcm_recording, self.recording_path, stereo_pcm, 24000, 2)
                print(f"{_C_AUDIO}[{get_timestamp()}] {ICON_OK}[Audio] Call synchronized stereo recording saved: {self.recording_path}{_R}")
            except Exception as e:
                print(f"{_C_WARN}[{get_timestamp()}] Error mixing stereo audio: {e}{_R}")
        elif asst_pcm_raw:
            try:
                await asyncio.to_thread(save_pcm_recording, self.recording_path, asst_pcm_raw, 24000, 1)
            except Exception as e:
                print(f"{_C_WARN}[{get_timestamp()}] Error saving assistant audio: {e}{_R}")

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
            tmp_whisper_wav = f"/tmp/whisper_final_{str(uuid.uuid4())[:8]}.wav"
            try:
                await asyncio.to_thread(save_pcm_recording, tmp_whisper_wav, client_pcm_snapshot, 16000, 1)
                raw_whisper = await self.transcribe_file_whisper(tmp_whisper_wav)
            finally:
                if os.path.exists(tmp_whisper_wav):
                    os.remove(tmp_whisper_wav)
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

        contact_match = match_contact_rule(self.caller_number, self.spam_data)
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
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[Caller] Raw: '{self.caller_number}' | Normalized: '{self.national_number}'{_R}")

        contact_match = match_contact_rule(self.caller_number, self.spam_data)
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
                role_assistant=pick_role_text(self.assistant_data.get("role_mappings", {}), is_female_gender(self.assistant_gender, self.gui_data), "Secretary"),
                owner_desc=pick_owner_text(self.assistant_data.get("owner_type_mappings", {}), self.owner_type, "Private"),
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
            extra_header = self.assistant_data.get("extra_prompt_header", "EXTRA INSTRUCTIONS/PERSONALITY:")
            instruction += f"\n\n{extra_header}\n{extra_prompt}"

        tool_texts = self.assistant_data.get("tool_descriptions", {})
        tools_list = [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="hangup",
                description=tool_texts.get("hangup", "Terminates the call immediately if spam or successfully finished."),
                parameters_json_schema={"type": "object", "properties": {"reason": {"type": "string"}}}
            ),
            types.FunctionDeclaration(
                name="save_message",
                description=tool_texts.get("save_message", "MANDATORY: Execute this tool to save ANY actionable message, task, delivery notice, or completed appointment details for the owner. Do not say it is noted without invoking this tool."),
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

        is_female_voice = is_female_gender(self.assistant_gender, self.gui_data)
        voice_names = self.assistant_data.get("voice_names", {})
        voice_name = voice_names.get("female" if is_female_voice else "male") or (
            DEFAULT_VOICE_FEMALE if is_female_voice else DEFAULT_VOICE_MALE
        )
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
        )
        # Optional explicit speech language (BCP-47) from the language file; empty disables it.
        speech_lang_code = str(self.assistant_data.get("speech_language_code", "")).strip()
        speech_config = None
        if speech_lang_code:
            try:
                speech_config = types.SpeechConfig(voice_config=voice_config, language_code=speech_lang_code)
            except Exception as e:
                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Voice] language_code not supported by this SDK, ignoring it: {e}{_R}")
        if speech_config is None:
            speech_config = types.SpeechConfig(voice_config=voice_config)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=instruction)]),
            tools=tools_list,
            speech_config=speech_config,
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
                                    await self.wait_for_playback_drain()
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


# =============================================================================
# PRIVATE TOR ONION SERVICE (optional remote access to the Web GUI)
# =============================================================================
# Switched on/off from the Web GUI through the 'tor_enabled' setting. The daemon owns the
# Tor process: it starts and stops it and publishes its state in SQLite ('tor_status',
# 'tor_progress', 'tor_onion', 'tor_error') so the GUI can display it. These values are
# language-neutral codes; the GUI translates them through gui.json.
# Keys and the onion address live in <BASE_DIR>/onion_data (same layout as onion_poc.py,
# so an address and devices created earlier with that script keep working).

ONION_DIR = os.path.join(BASE_DIR, "onion_data")
ONION_CLIENT_NAME = "phone1"
ONION_RETRY_SECONDS = 30.0


def _set_runtime_setting(key: str, value: Any) -> None:
    """Writes a runtime value (status, progress...) into the SQLite settings table."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def _torrc_quote(path: str) -> str:
    """Quotes a path for torrc so folders containing spaces work."""
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


# -----------------------------------------------------------------------------
# PUSH-STYLE NOTIFICATIONS FOR THE ANDROID APP (polled through Tor)
# -----------------------------------------------------------------------------
# A tiny read-only JSON endpoint bound to 127.0.0.1 only. It is published as a second port of the
# same onion service, so it is protected by the same client authorization as the Web GUI.
# The Android app polls it periodically and shows a local notification for each new item.

NOTIFY_MAX_ITEMS = 20
NOTIFY_SPAM_THRESHOLD = 65          # same threshold used to tag a call as SPAM
_NOTIFY_SERVER: Optional[ThreadingHTTPServer] = None


def build_notify_payload(since_message: Optional[int], since_call: Optional[int]) -> Dict[str, Any]:
    """Returns the newest caller messages and finished calls after the given ids.
    If a cursor is missing (first poll) no items are returned, only the current cursors,
    so enabling notifications never floods the phone with old items."""
    conn = sqlite3.connect(DB_PATH)
    try:
        max_message = conn.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0]
        # Only finished calls have a summary; calls are processed one at a time, so ids grow in finish order.
        max_call = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM calls WHERE summary IS NOT NULL AND summary != ''"
        ).fetchone()[0]

        messages: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []

        if since_message is not None:
            rows = conn.execute(
                "SELECT id, caller_name, message_text, date, time FROM messages "
                "WHERE id > ? ORDER BY id ASC LIMIT ?", (since_message, NOTIFY_MAX_ITEMS)
            ).fetchall()
            messages = [
                {"id": r[0], "caller": r[1] or "", "text": r[2] or "", "date": r[3] or "", "time": r[4] or ""}
                for r in rows
            ]

        if since_call is not None:
            # Calls that already left a message are skipped: the message notification covers them.
            rows = conn.execute(
                "SELECT id, client_name, company, summary, date FROM calls "
                "WHERE id > ? AND summary IS NOT NULL AND summary != '' "
                "AND summary NOT LIKE 'Blocked by rule%' "
                "AND COALESCE(spam_score, 0) < ? AND COALESCE(tag, '') NOT LIKE '%SPAM%' "
                "AND id NOT IN (SELECT call_id FROM messages WHERE call_id IS NOT NULL) "
                "ORDER BY id ASC LIMIT ?", (since_call, NOTIFY_SPAM_THRESHOLD, NOTIFY_MAX_ITEMS)
            ).fetchall()
            calls = [
                {"id": r[0], "caller": r[1] or "", "company": r[2] or "", "summary": r[3] or "", "date": r[4] or ""}
                for r in rows
            ]

        return {"max_message_id": max_message, "max_call_id": max_call, "messages": messages, "calls": calls}
    finally:
        conn.close()


class _NotifyHandler(BaseHTTPRequestHandler):
    """Serves GET /api/events?since_message=<id>&since_call=<id> as JSON."""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/events":
            self.send_error(404)
            return
        query = urllib.parse.parse_qs(parsed.query)

        def _int_param(name: str) -> Optional[int]:
            try:
                return int(query[name][0])
            except (KeyError, IndexError, ValueError):
                return None

        try:
            payload = build_notify_payload(_int_param("since_message"), _int_param("since_call"))
        except Exception:
            self.send_error(500)
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Silences the default per-request console logging."""
        return


def start_notify_server(port: int) -> None:
    """Starts the notification endpoint once (localhost only; Tor forwards the onion port to it)."""
    global _NOTIFY_SERVER
    if _NOTIFY_SERVER is not None:
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _NotifyHandler)
    except OSError as e:
        print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Notify] Could not listen on 127.0.0.1:{port}: {e}{_R}")
        return
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _NOTIFY_SERVER = server
    print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Notify] Notification endpoint ready on 127.0.0.1:{port}{_R}")


class OnionService:
    """Runs a private Tor instance that publishes the Web GUI as a v3 onion service
    protected with client authorization (only paired devices can even find it)."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.last_failure: float = 0.0
        self.progress: int = 0

    # ---- key material (same scheme as onion_poc.py) -------------------------------------

    @staticmethod
    def _b32(raw: bytes) -> str:
        return base64.b32encode(raw).decode().rstrip("=")

    def _generate_client(self, name: str) -> dict:
        priv_der = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "x25519", "-outform", "DER"],
            capture_output=True, check=True).stdout
        pub_der = subprocess.run(
            ["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"],
            input=priv_der, capture_output=True, check=True).stdout
        return {"name": name, "priv": self._b32(priv_der[-32:]), "pub": self._b32(pub_der[-32:])}

    def _load_clients(self) -> list:
        """Returns all authorized devices; creates the first one if there is none yet."""
        clients_dir = os.path.join(ONION_DIR, "clients")
        os.makedirs(clients_dir, exist_ok=True)
        clients = []
        for fname in sorted(os.listdir(clients_dir)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(clients_dir, fname), "r", encoding="utf-8") as f:
                        clients.append(json.load(f))
                except Exception:
                    pass
        if not clients:
            client = self._generate_client(ONION_CLIENT_NAME)
            path = os.path.join(clients_dir, f"{ONION_CLIENT_NAME}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(client, f)
            os.chmod(path, 0o600)
            clients.append(client)
        return clients

    def _write_torrc(self, port: int, clients: list, notify_port: int) -> str:
        hs = os.path.join(ONION_DIR, "hs")
        auth = os.path.join(hs, "authorized_clients")
        data = os.path.join(ONION_DIR, "data")
        for d in (ONION_DIR, hs, auth, data):
            os.makedirs(d, exist_ok=True)
            os.chmod(d, 0o700)
        valid = {f"{c['name']}.auth" for c in clients}
        for fname in os.listdir(auth):                       # revoke devices that no longer exist
            if fname.endswith(".auth") and fname not in valid:
                os.remove(os.path.join(auth, fname))
        for c in clients:
            with open(os.path.join(auth, f"{c['name']}.auth"), "w", encoding="utf-8") as f:
                f.write(f"descriptor:x25519:{c['pub']}\n")
        torrc = os.path.join(ONION_DIR, "torrc")
        with open(torrc, "w", encoding="utf-8") as f:
            f.write(
                f"DataDirectory {_torrc_quote(data)}\n"
                f"HiddenServiceDir {_torrc_quote(hs)}\n"
                f"HiddenServicePort 80 127.0.0.1:{port}\n"
                f"HiddenServicePort {notify_port} 127.0.0.1:{notify_port}\n"
                "SocksPort 0\n"
                "Log notice stdout\n"
            )
        return torrc

    # ---- process control ----------------------------------------------------------------

    def _fail(self, code: str) -> None:
        self.last_failure = time.time()
        _set_runtime_setting("tor_status", "error")
        _set_runtime_setting("tor_error", code)
        _set_runtime_setting("tor_onion", "")
        _set_runtime_setting("tor_progress", "0")

    def _publish_address(self, proc: subprocess.Popen) -> None:
        hostname_file = os.path.join(ONION_DIR, "hs", "hostname")
        onion = ""
        for _ in range(10):
            try:
                with open(hostname_file, "r", encoding="utf-8") as f:
                    onion = f.read().strip()
            except Exception:
                onion = ""
            if onion:
                break
            time.sleep(0.5)
        if not onion:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Tor] Onion hostname file not found.{_R}")
            self._fail("start_failed")
            if proc.poll() is None:
                proc.terminate()
            return
        _set_runtime_setting("tor_onion", onion)
        _set_runtime_setting("tor_error", "")
        _set_runtime_setting("tor_status", "running")
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Tor] Remote access active: http://{onion}{_R}")

    def _read_output(self, proc: subprocess.Popen) -> None:
        """Follows Tor's log: bootstrap progress and warnings."""
        pattern = re.compile(r"Bootstrapped (\d+)%")
        try:
            for line in proc.stdout:
                line = line.rstrip()
                m = pattern.search(line)
                if m:
                    self.progress = int(m.group(1))
                    if proc is self.proc and self.progress < 100:
                        _set_runtime_setting("tor_progress", self.progress)
                    elif proc is self.proc:
                        _set_runtime_setting("tor_progress", 100)
                        self._publish_address(proc)
                elif "[warn]" in line or "[err]" in line:
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Tor] {line}{_R}")
        except Exception:
            pass

    def start(self) -> None:
        if shutil.which("tor") is None:
            self._fail("tor_missing")
            return
        if shutil.which("openssl") is None:
            self._fail("openssl_missing")
            return
        try:
            port = int(get_config("tor_gui_port", "8501"))
            notify_port = int(get_config("tor_notify_port", "8502"))
            start_notify_server(notify_port)
            torrc = self._write_torrc(port, self._load_clients(), notify_port)
            self.progress = 0
            # __OwningControllerProcess makes Tor exit by itself if this daemon dies.
            self.proc = subprocess.Popen(
                ["tor", "-f", torrc, "--__OwningControllerProcess", str(os.getpid())],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Tor] Could not start: {e}{_R}")
            self._fail("start_failed")
            return
        _set_runtime_setting("tor_error", "")
        _set_runtime_setting("tor_onion", "")
        _set_runtime_setting("tor_progress", "0")
        _set_runtime_setting("tor_status", "starting")
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Tor] Starting private Tor instance (first bootstrap can take a minute)...{_R}")
        threading.Thread(target=self._read_output, args=(self.proc,), daemon=True).start()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Tor] Remote access stopped.{_R}")
        _set_runtime_setting("tor_status", "off")
        _set_runtime_setting("tor_error", "")
        _set_runtime_setting("tor_onion", "")
        _set_runtime_setting("tor_progress", "0")

    def sync(self, enabled: bool) -> None:
        """Called every few seconds by the heartbeat loop: makes reality match the GUI switch."""
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            self.proc = None
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Tor] Process ended (exit code {code}).{_R}")
            if get_config("tor_status", "off") != "error":
                self._fail("exited")
        if enabled:
            if self.proc is None and time.time() - self.last_failure >= ONION_RETRY_SECONDS:
                self.start()
        elif self.proc is not None or get_config("tor_status", "off") != "off":
            self.stop()


ONION = OnionService()


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

            try:
                ONION.sync(get_config("tor_enabled", "false").strip().lower() == "true")
            except Exception as tor_err:
                print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Tor] {tor_err}{_R}")

            if state == "stopped":
                if ACTIVE_ASSISTANT is None or not getattr(ACTIVE_ASSISTANT, "running", False):
                    print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Daemon] Stop requested via Web GUI. Shutting down cleanly...{_R}")
                    if GLIB_LOOP is not None:
                        try:
                            GLIB_LOOP.quit()
                        except Exception:
                            pass
                    ONION.stop()
                    main_loop.stop()
                    os._exit(0)
        except Exception:
            pass
        await asyncio.sleep(3.0)


async def run_cli_spam_test(test_number: str) -> None:
    """CLI utility to test a phone number against all configured SPAM providers and the LLM."""
    ensure_database_exists()
    dummy = PhoneAssistant(dbus_path="/org/ofono/test", caller_number=test_number)
    print(f"{_C_SERVER}Testing number {test_number} (Normalized: {dummy.national_number}) against SPAM providers...{_R}")
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
    main_loop.create_task(bluetooth_watchdog_loop())

    dbus_thread = threading.Thread(target=run_dbus_loop, args=(main_loop,), daemon=True)
    dbus_thread.start()

    print(f"{_C_SERVER}{ICON_SERVER}--- BLUETOOTH AI SWITCHBOARD v{APP_VERSION} ---{_R}")
    print("Waiting for incoming calls via oFono...\n")

    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print(f"\n{_C_WARN}{ICON_WARN}Switchboard manually stopped.{_R}")
        ONION.stop()
        os._exit(0)
