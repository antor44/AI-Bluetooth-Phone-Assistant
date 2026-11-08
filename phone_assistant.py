#!/usr/bin/env python3
"""
AI Switchboard Assistant - Intelligent phone handler utilizing Gemini 3.8 Live and Bluetooth HFP.
Detects incoming calls via D-Bus/oFono, manages audio routing through PipeWire, normalizes
caller numbers & wildcards, caches SPAM lookups, stores structured caller messages and AI
summaries, and interacts in real time.

Author: Antonio R.
Version: 3.1
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
import fcntl
import unicodedata
import difflib
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        import audioop  # C-speed PCM helpers. Removed in Python 3.13: the pure-Python fallbacks below are used then
    except ImportError:
        audioop = None
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
MODEL_TRANSCRIBE_LIVE = "gemini-3.5-transcribe-live"   # Online real-time transcription of the caller (optional mode)
SPAM_SCORE_THRESHOLD = 65           # Risk score from which a call is tagged as SPAM
# Texts saved in the call log that the Web GUI also recognizes (gui.py keeps a copy of both constants: keep them in sync).
BLOCKED_SUMMARY_PREFIX = "Blocked by rule"                          # Summary of a call rejected by a Blacklist rule
UNANSWERED_CALL_MARKER = "Call ended by caller before answering."   # Transcript of a call the caller ended before it was answered
# Fallback prebuilt voices, used only when the language file does not define "voice_names".
DEFAULT_VOICE_FEMALE = "Aoede"
DEFAULT_VOICE_MALE = "Charon"
API_KEY = os.environ.get("GEMINI_API_KEY")

DEFAULT_PW_INPUT  = "bluez_input.00_00_00_00_00_00.0"
DEFAULT_PW_OUTPUT = "bluez_output.00_00_00_00_00_00.1"

APP_VERSION = "3.1"
DEFAULT_LANGUAGE = "en-US"  # Language of a fresh install, until another one is selected in the Web GUI

# Playback drain before hanging up (see PhoneAssistant.is_playback_drained).
PLAYBACK_BYTES_PER_SECOND = 24000 * 2   # Gemini Live output: 24 kHz, 16-bit, mono PCM
HANGUP_AUDIO_TAIL_SECONDS = 1.2         # Extra time after the estimated end of playback (PipeWire + Bluetooth SCO latency)
DEFAULT_CALLER_GAIN = 1.5                 # Default caller microphone gain (x)
DEFAULT_NOISE_GATE_BASE = 55             # Default base noise gate (RMS)
DEFAULT_VAD_PREFIX_PADDING_MS = 450      # Default VAD prefix padding (ms)
DEFAULT_VAD_SILENCE_DURATION_MS = 600    # Default VAD silence (ms) before Gemini Live considers that the caller finished speaking
ASSISTANT_TURN_GAP_SECONDS = 4.0         # Output chunks closer than this belong to the same assistant turn (farewell detection)
HOLD_ACCEPT_WINDOW_SECONDS = 25.0        # An assistant "I'll wait" phrase only starts a hold if the caller asked to wait this recently
HOLD_RESUME_EXCHANGES = 2                # Caller turns dismissed during a hold but answered by the assistant that end the hold
HOLD_RESUME_REPLY_SECONDS = 15.0         # Max delay between a dismissed caller turn and the assistant reply that counts as evidence
HOLD_RESUME_WINDOW_SECONDS = 60.0        # The HOLD_RESUME_EXCHANGES exchanges must happen within this time
HOLD_RESUME_MIN_WORDS = 5                # A reply shorter than this is not considered a real answer
# Languages written in the Latin script: a transcription made mostly of other scripts is a recognition error there
LATIN_SCRIPT_LANGS = {"es", "en", "fr", "it", "pt", "de", "ca", "gl", "eu", "nl", "sv", "da", "no", "nb", "fi", "pl", "cs", "ro"}
ALT_ATTACH_WINDOW_S = 10.0               # An alternative transcription and a Gemini line this close in time belong together
ALT_NEAR_S = 2.0                         # …and when they are this close they are paired even if the words differ a lot
ALT_MIN_RATIO = 0.30                     # Minimum text similarity to pair them when they are not that close
ALT_ORPHAN_AFTER_S = 4.0                 # An alternative text with no Gemini line after this long is written on its own line
ONLINE_LABEL = "Gemini 3.5 Transcribe Live"
FAREWELL_VETO_SECONDS = 20.0             # After the text model says the caller has not closed the call, new goodbyes / hangup requests are ignored this long
SELF_INTERRUPT_WINDOW_SECONDS = 1.5      # An interruption this soon after a text instruction we sent ourselves is not a caller barge-in
HOLD_RENEW_WINDOW_SECONDS = 60.0         # The assistant's waiting phrases only renew a hold within this time of a real wait request
SEMANTIC_VOTE_TIMEOUT = 8.0              # Seconds to wait for the text-model opinion; without an answer there is simply no vote
SEMANTIC_MIN_INTERVAL = 10.0             # Minimum seconds between two semantic checks of the same kind
SEMANTIC_MAX_PER_CALL = 12               # Safety limit of semantic checks per call (cost)
DB_WRITE_MIN_INTERVAL = 0.5              # Live transcript writes to SQLite are merged: at most one write per interval
WHISPER_QUEUE_MAX = 8                    # Pending Whisper jobs per call; beyond this the oldest work is not worth waiting for
HANGUP_STREAM_QUIET_SECONDS = 1.0       # No new audio from the model for this long before cutting the call
HANGUP_MAX_WAIT_SECONDS = 20.0          # Safety limit: never wait longer than this for the audio to finish

# Bluetooth reconnection watchdog (see BluetoothWatchdog).
DB_BUSY_TIMEOUT_SECONDS = 15.0          # How long a SQLite connection waits for the lock held by the other process (daemon / Web GUI)
BT_SLOW_CYCLE_SECONDS = 20.0             # A watchdog cycle slower than this is reported in the console (a blocked D-Bus call)
OFONO_HANDSFREE_INTERFACE = "org.ofono.Handsfree"
BATTERY_LEVEL_STEPS = 5                  # oFono / HFP report the phone battery as 0..5
BATTERY_UNKNOWN = -1                     # Published when the phone does not report its battery
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
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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

    def clear(self) -> None:
        """Drops every chunk that is still waiting to be written to the player."""
        try:
            while True:
                self.chunks.get_nowait()
        except queue.Empty:
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

    conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
                conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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


def migrate_category_prompts() -> None:
    """One-time migration (per language). The courier and workshop rules used to be part of the general
    instructions; they are now editable instructions of their categories. Saved categories get them once:
    a missing default category is added, and a saved one that has no instructions yet receives them.
    Duplicated in gui.py on purpose, so the result is the same whichever of the two starts first."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
        for lang_code in sorted(os.listdir(LANG_DIR)):
            gui_path = os.path.join(LANG_DIR, lang_code, "gui.json")
            if not os.path.isfile(gui_path):
                continue
            flag_key = f"category_prompts_migrated_{lang_code}"
            if conn.execute("SELECT 1 FROM settings WHERE key=?", (flag_key,)).fetchone():
                continue
            row = conn.execute("SELECT value FROM settings WHERE key=?", (f"{lang_code}_memory_rules",)).fetchone()
            if row is not None:
                try:
                    rules = json.loads(row[0])
                    with open(gui_path, "r", encoding="utf-8") as f:
                        default_rules = json.load(f).get("defaults", {}).get("memory_rules", [])
                except Exception:
                    continue   # Unreadable data: try again on the next start, nothing is changed
                if isinstance(rules, list):
                    for default_rule in default_rules:
                        if not isinstance(default_rule, dict) or not default_rule.get("prompt"):
                            continue
                        default_name = str(default_rule.get("category", "")).strip().lower()
                        saved_rule = next((r for r in rules if isinstance(r, dict) and str(r.get("category", "")).strip().lower() == default_name), None)
                        if saved_rule is None:
                            rules.append(dict(default_rule))
                        elif "prompt" not in saved_rule:
                            saved_rule["prompt"] = default_rule["prompt"]
                    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (f"{lang_code}_memory_rules", json.dumps(rules, ensure_ascii=False)))
            # Without saved categories the language defaults (which already carry these instructions) are written on its first run
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, '1')", (flag_key,))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def ensure_database_exists(reset_runtime_state: bool = False) -> None:
    """Ensures that the SQLite database, tables, and v2.0 schema migrations are applied.

    The runtime state (daemon state, heartbeat, Tor status) is reset only when the daemon itself starts
    (reset_runtime_state=True). Any other caller, such as the --test-spam command, must never overwrite the
    state of a daemon that is already running."""
    runtime_insert = "INSERT OR REPLACE" if reset_runtime_state else "INSERT OR IGNORE"
    conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
    conn.execute("PRAGMA journal_mode=WAL")   # Readers (Web GUI) no longer block the daemon writers (heartbeat, traces)
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS calls 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, date TEXT, duration INT, 
                  spam_score INT, transcript TEXT, audio_path TEXT, client_audio_path TEXT, 
                  tag TEXT, client_name TEXT, company TEXT, summary TEXT DEFAULT '',
                  base_tag TEXT, base_client_name TEXT)''')
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
    c.execute('''CREATE TABLE IF NOT EXISTS decision_log 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER, ts TEXT, kind TEXT,
                  gemini_signal TEXT, text_signal TEXT, result TEXT, detail TEXT)''')

    for alter_sql in [
        "ALTER TABLE calls ADD COLUMN summary TEXT DEFAULT ''",
        "ALTER TABLE calls ADD COLUMN base_tag TEXT",
        "ALTER TABLE calls ADD COLUMN base_client_name TEXT",
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
    c.execute("INSERT OR IGNORE INTO settings VALUES ('spam_block_threshold', '70')")
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

    c.execute("INSERT OR IGNORE INTO settings VALUES ('caller_gain', ?)", (str(DEFAULT_CALLER_GAIN),))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('noise_gate_base', ?)", (str(DEFAULT_NOISE_GATE_BASE),))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_start_sensitivity', 'LOW')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_end_sensitivity', 'HIGH')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_prefix_padding_ms', ?)", (str(DEFAULT_VAD_PREFIX_PADDING_MS),))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_silence_duration_ms', ?)", (str(DEFAULT_VAD_SILENCE_DURATION_MS),))
    # One-time migration: the new default replaces the value stored by previous versions (INSERT OR IGNORE never overwrites it)
    c.execute("INSERT OR IGNORE INTO settings VALUES ('vad_silence_default_migrated', '1')")
    if c.rowcount == 1:
        c.execute("UPDATE settings SET value=? WHERE key='vad_silence_duration_ms'", (str(DEFAULT_VAD_SILENCE_DURATION_MS),))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('protect_initial_greeting', 'true')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('farewell_grace_seconds', '2.0')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('farewell_cancel_min_words', '3')")

    c.execute(f"{runtime_insert} INTO settings VALUES ('daemon_state', 'running')")
    c.execute(f"{runtime_insert} INTO settings VALUES ('daemon_heartbeat', ?)", (str(time.time()),))

    # Remote access through a private Tor onion service (off unless the user enables it in the GUI)
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_enabled', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_gui_port', '8501')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('tor_notify_port', '8502')")
    c.execute(f"{runtime_insert} INTO settings VALUES ('tor_status', 'off')")
    c.execute(f"{runtime_insert} INTO settings VALUES ('tor_progress', '0')")
    c.execute(f"{runtime_insert} INTO settings VALUES ('tor_onion', '')")
    c.execute(f"{runtime_insert} INTO settings VALUES ('tor_error', '')")

    conn.commit()
    conn.close()

    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
        res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        current_lang = res_lang[0] if res_lang else DEFAULT_LANGUAGE
        res_asst = conn.execute("SELECT value FROM settings WHERE key=?", (f"{current_lang}_assistant_name",)).fetchone()
        conn.close()
        if res_asst is None:
            apply_language_defaults(current_lang)
    except Exception:
        pass

    migrate_category_prompts()


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
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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


# =============================================================================
# RUNTIME OPTIONS AND DEBUG TRACE
# =============================================================================
DEBUG_DIR = os.path.join(BASE_DIR, "debug")


def knob(name: str, default: str) -> str:
    """Runtime option: environment variable SWITCHBOARD_<NAME> first, then the settings table, then the default.
    Handy to A/B test behaviours from the shell without touching the Web GUI."""
    env = os.environ.get("SWITCHBOARD_" + name.upper())
    if env is not None and env.strip() != "":
        return env.strip()
    return get_config(name, default)


def knob_bool(name: str, default: bool) -> bool:
    return knob(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


def knob_int(name: str, default: int) -> int:
    try:
        return int(float(knob(name, str(default))))
    except ValueError:
        return default


class CallDebugLog:
    """Per-call trace in JSON lines (one event per line) saved in <BASE_DIR>/debug/.

    OFF by default (for advanced users and support). Turn it on with SWITCHBOARD_DEBUG=1, the --debug option or the 'debug_mode' setting = true.
    It writes one .jsonl file per call and, when the playback process reports errors, a *_pw-play.log file next to it.
    It holds what Gemini really sent (raw transcriptions before any cleaning), why each caller turn was kept or
    dropped, every change of a state flag (with the code line that made it) and the Whisper results.
    It contains call content and phone numbers: keep the folder out of version control and out of bug reports.
    Read it with:  python phone_assistant.py --show-debug debug/call_xxx.jsonl"""

    def __init__(self, call_tag: str):
        self.enabled = False
        self.path = ""
        self._fh = None
        self._lock = threading.Lock()
        self._t0 = time.time()
        env_debug = os.environ.get("SWITCHBOARD_DEBUG", "").strip().lower()
        wanted = (env_debug in ("1", "true", "yes", "on")) if env_debug else knob_bool("debug_mode", False)
        if not wanted:
            return
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            safe_tag = re.sub(r"[^0-9A-Za-z+_-]", "_", str(call_tag))[:24] or "unknown"
            self.path = os.path.join(DEBUG_DIR, f"call_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_tag}.jsonl")
            self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
            self.enabled = True
            print(f"{_C_MUTED}[{get_timestamp()}] [Debug] Trace: {self.path}{_R}")
        except Exception as e:
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Debug] Could not open the trace file: {e}{_R}")

    def log(self, event: str, **data: Any) -> None:
        if not self.enabled or self._fh is None:
            return
        rec: Dict[str, Any] = {"t": round(time.time() - self._t0, 3), "clock": get_timestamp(), "ev": event}
        rec.update(data)
        try:
            line = json.dumps(rec, ensure_ascii=False, default=str)
            with self._lock:
                self._fh.write(line + "\n")
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
        self.enabled = False


class _TracedFlag:
    """Data descriptor for a boolean state flag: every change is written to the debug trace together with the
    function and line that made it. Costs nothing when debugging is off (the trace object is then inert)."""

    def __set_name__(self, owner: Any, name: str) -> None:
        self.name = name
        self.attr = "_tf_" + name

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        return obj.__dict__.get(self.attr, False)

    def __set__(self, obj: Any, value: Any) -> None:
        old = obj.__dict__.get(self.attr, None)
        obj.__dict__[self.attr] = value
        if old != value:
            obj.__dict__[self.attr + "_since"] = time.time()
        if old is not None and old != value:
            dbg = obj.__dict__.get("dbg")
            if dbg is not None and dbg.enabled:
                frame = sys._getframe(1)
                dbg.log("state", flag=self.name, old=old, new=value, at=f"{frame.f_code.co_name}:{frame.f_lineno}", snap=obj._state_snapshot())
            if dbg is not None:
                print(f"{_C_MUTED}[{get_timestamp()}] [state] {self.name}: {old} -> {value}  ({sys._getframe(1).f_code.co_name}:{sys._getframe(1).f_lineno}){_R}", flush=True)


def _dbg_short(value: Any, limit: int = 120) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def print_debug_timeline(path: str, only: Optional[str] = None) -> None:
    """Prints a debug trace as a readable timeline plus a count of events (--show-debug)."""
    counts: Counter = Counter()
    try:
        fh = open(path, encoding="utf-8")
    except OSError as e:
        print(f"Cannot open {path}: {e}")
        return
    with fh:
        for raw in fh:
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            t = rec.pop("t", 0.0)
            clock = rec.pop("clock", "")
            ev = rec.pop("ev", "?")
            counts[ev] += 1
            if only and only not in ev:
                continue
            detail = " ".join(f"{k}={_dbg_short(v)}" for k, v in rec.items())
            print(f"{t:8.2f}s {clock} {ev:<18} {detail}")
    print("\n--- Events in this trace ---")
    for ev, n in counts.most_common():
        print(f"{n:6d}  {ev}")


def summarize_bt_audio(objects: Any) -> Dict[str, Any]:
    """Picks the Bluetooth facts out of a pw-dump (codec, profile, sample rate) to learn whether the call runs in
    wide-band (mSBC) or narrow-band (CVSD) audio. Narrow-band audio degrades every transcription."""
    found: Dict[str, Any] = {}
    chunks: List[str] = []
    for obj in objects if isinstance(objects, list) else []:
        if not isinstance(obj, dict):
            continue
        info = obj.get("info") or {}
        props = info.get("props") or {}
        blob = " ".join(str(v) for v in props.values()).lower()
        if "bluez" not in blob and "bluetooth" not in blob and "ofono" not in blob:
            continue
        facts = {k: v for k, v in props.items() if any(w in k.lower() for w in ("codec", "profile", "sco", "hfp", "audio.rate", "audio.format", "audio.channels"))}
        for item in (info.get("params") or {}).get("Profile", []) or []:
            if isinstance(item, dict) and item.get("name"):
                facts["param.Profile"] = item.get("name")
        if facts:
            found[str(props.get("node.name") or props.get("device.name") or obj.get("id"))] = facts
            chunks.append(json.dumps(facts, default=str).lower())
    joined = " ".join(chunks)
    codec = "unknown"
    if "msbc" in joined:
        codec = "mSBC (wide band, 16 kHz)"
    elif "cvsd" in joined:
        codec = "CVSD (narrow band, 8 kHz)"
    elif "lc3" in joined:
        codec = "LC3"
    return {"codec_guess": codec, "objects": found}


_WHISPER_PROMPT_SUPPORT: Optional[bool] = None


def whisper_supports_prompt() -> bool:
    """True when this whisper-cli build accepts --prompt (checked once, from its own help text)."""
    global _WHISPER_PROMPT_SUPPORT
    if _WHISPER_PROMPT_SUPPORT is None:
        try:
            out = subprocess.run([WHISPER_BIN, "-h"], capture_output=True, text=True, timeout=5)
            _WHISPER_PROMPT_SUPPORT = "--prompt" in (out.stdout + out.stderr)
        except Exception:
            _WHISPER_PROMPT_SUPPORT = False
    return _WHISPER_PROMPT_SUPPORT


class OnlineTranscriber:
    """Online real-time transcription of the CALLER with gemini-3.5-transcribe-live, over a Live session of its own.

    It is a second, independent reading of the same voice (a third opinion next to Gemini's own transcription and
    Whisper): it gets a language hint and a custom vocabulary (the assistant's and the owner's names), which the main
    conversation model does not. Only the speech is streamed (the noise gate decides), and the end of each utterance
    is signalled with audio_stream_end so the final text comes back quickly. The service allows 10 minutes per
    session, so the session is renewed before that. Failures never affect the call: the transcriber just stops."""

    BLOCK_BYTES = 3200      # 100 ms of 16 kHz 16-bit mono, the chunk size recommended by the documentation
    MAX_FAILURES = 4

    def __init__(self, owner: Any):
        self.owner = owner
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=400)
        self.task: Optional[asyncio.Task] = None
        self._rx: Optional[asyncio.Task] = None
        self.stopped = False
        self.audio_sent_s = 0.0
        self.finals = 0
        self.out_chars = 0
        self.dropped = 0
        self.sessions = 0
        self.last_voice_time = 0.0
        self.last_interim = ""
        self._buf = bytearray()
        self.backoff_s = 2.0
        self.rotate_s = float(knob_int("online_rotate_seconds", 540))
        self.end_silence_s = knob_int("online_end_silence_ms", 700) / 1000.0
        self.language_codes = self._language_codes()
        self.vocabulary = self._vocabulary()

    def _language_codes(self) -> List[str]:
        configured = knob("online_languages", "").strip()
        if configured.lower() == "auto":
            return []
        if configured:
            return [c.strip() for c in configured.split(",") if c.strip()]
        return [self.owner.current_lang] if self.owner.current_lang else []

    def _vocabulary(self) -> List[str]:
        """Distinct names and terms that help recognition (not everyday words). Up to 100 are used."""
        terms: List[str] = [self.owner.assistant_name, self.owner.boss_name]
        terms += [t.strip() for t in re.split(r"[,\n]", knob("online_vocabulary", "")) if t.strip()]
        seen: set = set()
        out: List[str] = []
        for t in terms:
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out[:100]

    def start(self) -> None:
        self.task = asyncio.create_task(self.run())

    def stop(self) -> None:
        self.stopped = True
        if self.task is not None and not self.task.done():
            self.task.cancel()

    def feed(self, pcm: bytes, voice: bool) -> None:
        """Called for every microphone chunk. Silence is passed as a gap marker: it is not streamed, it only closes utterances."""
        try:
            self.queue.put_nowait((pcm if voice else None, len(pcm) / 32000.0))
        except asyncio.QueueFull:
            self.dropped += 1

    def usage(self) -> Dict[str, Any]:
        return {"audio_sent_s": round(self.audio_sent_s, 1), "finals": self.finals, "sessions": self.sessions, "dropped_chunks": self.dropped}

    def _build_config(self, codes: List[str]) -> Any:
        try:
            tx = types.AudioTranscriptionConfig(language_codes=codes, custom_vocabulary=self.vocabulary or None)
        except Exception:
            tx = types.AudioTranscriptionConfig()      # SDK too old for language hints / vocabulary
        return types.LiveConnectConfig(response_modalities=["TEXT"], input_audio_transcription=tx)

    async def run(self) -> None:
        owner = self.owner
        codes = list(self.language_codes)
        failures = 0
        while not self.stopped and owner.running:
            started = time.time()
            try:
                async with owner.client_live.aio.live.connect(model=MODEL_TRANSCRIBE_LIVE, config=self._build_config(codes)) as session:
                    self.sessions += 1
                    owner.dbg.log("online_connect", model=MODEL_TRANSCRIBE_LIVE, language_codes=codes, vocabulary=self.vocabulary, session=self.sessions)
                    print(f"{_C_MUTED}[{get_timestamp()}] [Online] Transcription session {self.sessions} open (language: {codes or 'auto'}){_R}", flush=True)
                    self._rx = asyncio.create_task(self._receive(session))
                    try:
                        await self._pump(session, started + self.rotate_s)
                    finally:
                        self._rx.cancel()
                        try:
                            await self._rx
                        except BaseException:
                            pass
                if time.time() - started > 5.0:
                    failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                owner.dbg.log("online_error", error=repr(e), failures=failures, language_codes=codes)
                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Online] Transcription session failed ({failures}/{self.MAX_FAILURES}): {e}{_R}", flush=True)
                if codes and failures == 1:
                    codes = []                             # the language hint may be the problem: retry with automatic detection
                    owner.dbg.log("online_language_fallback", to="auto")
                if failures >= self.MAX_FAILURES:
                    owner.dbg.log("online_unavailable")
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Online] Giving up on online transcription for this call. The call itself is not affected.{_R}", flush=True)
                    return
                await asyncio.sleep(min(8.0, self.backoff_s ** failures))

    async def _pump(self, session: Any, deadline: float) -> None:
        gap_s = 0.0
        voice_open = False
        while not self.stopped and self.owner.running and time.time() < deadline:
            if self._rx is not None and self._rx.done():
                self._rx.result()                          # raises the receiver's error, which makes run() reconnect
                raise RuntimeError("transcription receiver ended")
            try:
                pcm, chunk_s = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if pcm is not None:
                self._buf.extend(pcm)
                voice_open = True
                gap_s = 0.0
                self.last_voice_time = time.time()
                while len(self._buf) >= self.BLOCK_BYTES:
                    block = bytes(self._buf[: self.BLOCK_BYTES])
                    del self._buf[: self.BLOCK_BYTES]
                    await session.send_realtime_input(audio=types.Blob(data=block, mime_type="audio/pcm;rate=16000"))
                    self.audio_sent_s += self.BLOCK_BYTES / 32000.0
            else:
                gap_s += chunk_s
                if voice_open and gap_s >= self.end_silence_s:
                    if self._buf:
                        tail = bytes(self._buf)
                        self._buf.clear()
                        await session.send_realtime_input(audio=types.Blob(data=tail, mime_type="audio/pcm;rate=16000"))
                        self.audio_sent_s += len(tail) / 32000.0
                    await session.send_realtime_input(audio_stream_end=True)
                    voice_open = False

    async def _receive(self, session: Any) -> None:
        while not self.stopped:
            got = False
            async for response in session.receive():
                got = True
                sc = getattr(response, "server_content", None)
                if not sc:
                    continue
                interim = getattr(sc, "interim_input_transcription", None)
                if interim is not None and getattr(interim, "text", None):
                    self.last_interim = interim.text
                final = getattr(sc, "input_transcription", None)
                if final is not None and getattr(final, "text", None):
                    self.owner._on_online_final(final.text, self.last_voice_time)
            if not got:
                await asyncio.sleep(0.2)


def normalize_end_of_call_labels(transcript: str, label: str) -> str:
    """The end-of-call correction asks the text model for '[Live]: <text> | [Final ASR]: <corrected>'. Shows the Gemini
    text plainly and names the engine that produced the alternative text."""
    cleaned = re.sub(r"(\[\d{2}:\d{2}:\d{2}\]:)\s*\[Live\]:\s*", r"\1 ", transcript)
    return cleaned.replace("[Final ASR]", f"[{label}]")


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
        self.handsfree_keys_logged = False

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

    @staticmethod
    def battery_level_to_percent(level: Any) -> int:
        """Converts the HFP battery level (0..5) to a percentage in steps of 20; anything else is 'unknown'."""
        try:
            value = int(level)
        except (TypeError, ValueError):
            return BATTERY_UNKNOWN
        if 0 <= value <= BATTERY_LEVEL_STEPS:
            return value * (100 // BATTERY_LEVEL_STEPS)
        return BATTERY_UNKNOWN

    def _read_battery_percent(self, bus: Any, modem_path: str, bluez_interfaces: Any) -> int:
        """Phone battery: exact percentage from BlueZ (Battery1) when the phone gives it, otherwise the HFP level from oFono."""
        battery1 = (bluez_interfaces or {}).get("org.bluez.Battery1")
        if battery1 is not None and "Percentage" in battery1:
            try:
                return max(0, min(100, int(battery1["Percentage"])))
            except (TypeError, ValueError):
                pass
        if not modem_path:
            return BATTERY_UNKNOWN
        try:
            handsfree = dbus.Interface(bus.get_object("org.ofono", modem_path), OFONO_HANDSFREE_INTERFACE)
            properties = handsfree.GetProperties()
        except Exception:
            return BATTERY_UNKNOWN
        if not self.handsfree_keys_logged:
            self.handsfree_keys_logged = True
            print(f"{_C_MUTED}[{get_timestamp()}] [Bluetooth] oFono Handsfree properties: {', '.join(str(k) for k in properties.keys())}{_R}")
        for key, value in properties.items():
            if "battery" in str(key).lower():
                return self.battery_level_to_percent(value)
        return BATTERY_UNKNOWN

    def _publish_state(self, state: str, device_name: str) -> None:
        if (state, device_name) != self.published_state:
            print(f"{_C_SERVER}[{get_timestamp()}] {ICON_CONN}[Bluetooth] State: {self.published_state[0] or 'none'} -> {state} ({device_name}){_R}")
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

    def _ofono_modem_tokens(self, bus: Any) -> Dict[str, str]:
        """Returns {device token: oFono modem path} of the oFono modems, powering on and putting online any that are not."""
        tokens: Dict[str, str] = {}
        try:
            manager = dbus.Interface(bus.get_object("org.ofono", "/"), "org.ofono.Manager")
            modems = manager.GetModems()
        except Exception:
            return tokens
        for modem_path, modem_props in modems:
            tokens[self._mac_token(str(modem_path))] = str(modem_path)
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
        ready_name = ""
        first_name = ""
        battery = BATTERY_UNKNOWN
        for device_path, props in phones:
            name = str(props.get("Alias") or props.get("Name") or device_path)
            first_name = first_name or name
            if self._check_phone(bus, device_path, props, modem_tokens):
                connected_name = connected_name or name
                modem_path = modem_tokens.get(self._mac_token(device_path), "")
                if modem_path and not ready_name:
                    ready_name = name
                    battery = self._read_battery_percent(bus, modem_path, objects.get(dbus.ObjectPath(device_path)) or objects.get(device_path))

        # The call profile (oFono modem) is what carries the calls: BlueZ saying "connected" is not enough.
        if ready_name:
            self._publish_state("connected", ready_name)
        elif connected_name:
            self._publish_state("profile_not_ready", connected_name)
        else:
            self._publish_state("disconnected", first_name)
        set_runtime_setting("bt_battery", str(battery if ready_name else BATTERY_UNKNOWN))


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
                cycle_started = time.time()
                await loop.run_in_executor(None, watchdog.check_once)
                last_error = ""
                cycle_seconds = time.time() - cycle_started
                if cycle_seconds > BT_SLOW_CYCLE_SECONDS:
                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Bluetooth] Watchdog cycle took {cycle_seconds:.0f}s (a D-Bus call was slow).{_R}")
            # The heartbeat stops by itself if a D-Bus call blocks the cycle above; the Web GUI then shows the state as unknown.
            set_runtime_setting("bt_heartbeat", str(time.time()))
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
    data_pcm = data_pcm[: count * 2]
    if audioop is not None:
        try:
            return float(audioop.rms(data_pcm, 2))
        except Exception:
            pass
    shorts = struct.unpack(f"<{count}h", data_pcm)
    return math.sqrt(sum(s * s for s in shorts) / count)


def monitor_volume_gain(volume_pct: int) -> float:
    """Amplitude factor for a monitor volume in percent. The assistant's player is set with pactl, whose percentage follows the
    perceptual (cubic) scale of PulseAudio / PipeWire; the caller's software volume uses the same curve so both sound alike."""
    return max(0.0, min(1.0, volume_pct / 100.0)) ** 3


def apply_gain(data_pcm: bytes, gain: float) -> bytes:
    """Multiplies 16-bit little-endian PCM by gain, clipping instead of wrapping around."""
    count = len(data_pcm) // 2
    if count == 0 or gain == 1.0:
        return data_pcm
    data_pcm = data_pcm[: count * 2]
    if audioop is not None:
        try:
            return audioop.mul(data_pcm, 2, gain)
        except Exception:
            pass
    samples = struct.unpack(f"<{count}h", data_pcm)
    return struct.pack(f"<{count}h", *[max(min(int(v * gain), 32767), -32768) for v in samples])


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


FUZZY_MIN_LEN = 6      # Only words of this length or more may match a close (not identical) spelling
FUZZY_RATIO = 0.86     # Minimum similarity of that close spelling


def fold_text(text: str) -> str:
    """What keyword matching compares: lower case, no accents, no punctuation, single spaces."""
    t = text.replace("\u2019", "'").replace("\u2018", "'").lower()
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _fuzzy_token_eq(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) < FUZZY_MIN_LEN or len(b) < FUZZY_MIN_LEN or a[0] != b[0] or abs(len(a) - len(b)) > 2:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_RATIO


def matches_any_phrase(text: str, phrases: list, fuzzy: bool = False) -> bool:
    """True if any phrase appears in text: multi-word phrases as substrings, single words on word boundaries.

    Case, accents and punctuation are ignored (a recognition error such as 'adios' for 'adiós' must not matter).
    With fuzzy=True a word of FUZZY_MIN_LEN or more letters also matches a close spelling. That is meant for what the
    CALLER says (recognition errors are common there); never use it on the assistant's own text."""
    t = fold_text(text)
    if not t:
        return False
    tokens = None
    for phrase in phrases:
        p = fold_text(phrase)
        if not p:
            continue
        if " " in p:
            if p in t:
                return True
        elif re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", t):
            return True
        if fuzzy:
            ptoks = p.split()
            if not any(len(w) >= FUZZY_MIN_LEN for w in ptoks):
                continue
            if tokens is None:
                tokens = t.split()
            n = len(ptoks)
            for i in range(len(tokens) - n + 1):
                if all(_fuzzy_token_eq(tokens[i + j], ptoks[j]) for j in range(n)):
                    return True
    return False


def non_latin_letter_ratio(text: str) -> float:
    """Share (0..1) of the letters in text that are not Latin-script letters (0.0 when there are no letters)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    non_latin = sum(1 for c in letters if "LATIN" not in unicodedata.name(c, ""))
    return non_latin / len(letters)


def strip_quoted_text(text: str) -> str:
    """Removes quoted fragments: a word between quotes is being mentioned (listed, cited), not said."""
    t = re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d|\u00ab[^\u00bb]*\u00bb', " ", text)
    return re.sub(r"(?<!\w)['\u2018][^'\u2019]{1,60}?['\u2019](?!\w)", " ", t)


def find_farewell(text: str, farewell_words: list, veto_words: list, meta_words: list = (), fuzzy: bool = False) -> bool:
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
        return matches_any_phrase(text, farewell_words, fuzzy)
    for sentence in re.split(r"[.!?¿¡…\n]+", text):
        if not sentence.strip() or (meta_words and matches_any_phrase(sentence, meta_words)):
            continue
        for clause in re.split(r"[,;:]+", sentence):
            clause = clause.strip()
            if clause and matches_any_phrase(clause, farewell_words, fuzzy) and not matches_any_phrase(clause, veto_words):
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
        if any(marker in block for marker in ["[SYSTEM]", "[Active Hold]", "❌", "⏳", "⏸", "[Noise Filtered]", "🔇", "🌐"]):
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

    # State flags whose every change is recorded in the debug trace (see _TracedFlag)
    on_hold = _TracedFlag()
    hanging_up = _TracedFlag()
    hangup_triggered = _TracedFlag()
    farewell_pending = _TracedFlag()
    priority_call = _TracedFlag()
    waiting_definitive_cut = _TracedFlag()

    def __init__(self, dbus_path: str, caller_number: str):
        self.dbus_path = dbus_path
        self.caller_number = caller_number
        self.running = False
        self._post_processed = False
        self.dbg = CallDebugLog(caller_number)

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

        # Hold safeguards (see _hold_acceptance_allowed and _register_hold_exchange)
        self._last_wait_request_time = 0.0
        self._hold_pending_caller_time = 0.0
        self._hold_resume_count = 0
        self._hold_resume_first_time = 0.0
        self._hold_gate_last_note = 0.0

        # Runtime options (environment variable SWITCHBOARD_<NAME> overrides the settings table; see knob())
        self.fuzzy_keywords = knob_bool("fuzzy_keywords", True)                          # Caller-side keyword matching tolerates recognition errors
        self.whisper_signals = knob_bool("whisper_signals", True)                        # Whisper text also feeds hold / farewell / priority detection
        self.flush_on_interrupt = knob_bool("flush_on_interrupt", True)                  # Drop queued model audio when the Live API reports an interruption
        self.explicit_transcription_config = knob_bool("explicit_transcription_config", False)  # Ask the Live API for input/output transcription explicitly (off: the v2.9 session configuration)
        self.send_speech_language_code = knob_bool("send_speech_language_code", True)    # Send speech_language_code from the language file
        self.mic_gate_hangover_chunks = knob_int("mic_gate_hangover_chunks", 8)          # ~16 ms each: keeps the noise gate open after speech
        self.whisper_threads = max(1, knob_int("whisper_threads", min(8, os.cpu_count() or 4)))

        # Agreement between the two "brains" for irreversible / costly decisions
        self.semantic_votes = knob_bool("semantic_votes", True)
        self.whisper_prompt = knob("whisper_prompt", "")
        self._hangup_tool_seen = False          # the model asked to hang up (tool): an intent, not a decision
        self._closing_vote: Optional[bool] = None
        self._pending_hangup_calls: List[Tuple[str, str]] = []   # (id, name) of hangup tool calls the model is still waiting an answer for
        self._live_session: Any = None                           # Live API session of this call, used to answer a cancelled hangup
        self._caller_spoke_since_intent = False   # a caller turn arrived after the goodbye / hangup request
        self._intent_text = ""                    # what the assistant had said when the goodbye / hangup was requested
        self._intent_time = 0.0                   # when the goodbye / hangup was requested
        self._asst_turn_start_time = 0.0
        self._farewell_veto_time = 0.0
        self._self_interrupt_until = 0.0
        self._last_caller_farewell_time = 0.0
        self._last_caller_text_time = 0.0
        self._last_interrupted_time = 0.0
        self._semantic_last: Dict[str, float] = {}
        self._semantic_count = 0
        self._bg_tasks: set = set()
        self.online: Optional[OnlineTranscriber] = None
        self._alt_lines: List[Dict[str, Any]] = []     # recent Gemini caller lines that alternative texts can be attached to
        self._alt_pending: List[Dict[str, Any]] = []   # alternative texts still waiting for their Gemini line
        self._alt_agree = 0                             # alternative texts identical to Gemini's
        self._alt_total = 0
        self.spam_block_threshold = knob_int("spam_block_threshold", 70)

        # Microphone path
        self._mic_carry = b""
        self._gate_hangover_left = 0
        self._mic_stats = self._new_mic_stats(time.time())
        self._playback_proc = None
        self._pb_in_bytes = 0          # model audio received
        self._pb_written_bytes = 0     # model audio written to the player
        self._pb_write_fail = 0
        self._pb_spawns = 0
        self._pb_last_error = ""
        self._pb_last_stats = 0.0
        self._pb_stderr = None

        # Debounced transcript persistence
        self._db_last_write = 0.0
        self._db_dirty = False

        # Whisper (one worker per call, created lazily inside the event loop)
        self._whisper_queue = None
        self._whisper_worker_task = None
        self._whisper_missing_logged = False

        # Priority rules are parsed once per call instead of once per caller turn
        try:
            _rules = json.loads(get_config("memory_rules", "[]"))
            self._memory_rules = _rules if isinstance(_rules, list) else []
        except Exception:
            self._memory_rules = []
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
        self._monitor_gain = monitor_volume_gain(monitor_volume_percent())   # Monitor volume applied in software to the caller's samples (the caller's player stays at 100%)
        self._direct_links_removed: set = set()
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
            self.caller_gain = float(get_config("caller_gain", str(DEFAULT_CALLER_GAIN)))
        except ValueError:
            self.caller_gain = DEFAULT_CALLER_GAIN
        try:
            self.noise_gate_base = int(get_config("noise_gate_base", str(DEFAULT_NOISE_GATE_BASE)))
        except ValueError:
            self.noise_gate_base = DEFAULT_NOISE_GATE_BASE

        self.vad_start_sens = get_config("vad_start_sensitivity", "LOW")
        self.vad_end_sens = get_config("vad_end_sensitivity", "HIGH")
        try:
            self.vad_prefix_padding_ms = int(get_config("vad_prefix_padding_ms", str(DEFAULT_VAD_PREFIX_PADDING_MS)))
        except ValueError:
            self.vad_prefix_padding_ms = DEFAULT_VAD_PREFIX_PADDING_MS
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

        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
                        verdict = self.spam_verdict(bool(is_sp), int(r_score) if r_score else None, self.spam_block_threshold)
                        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_INFO}[SpamCheck] Cache hit for {cache_key}: SPAM={verdict} (Score: {self.network_spam_score}, cut-off: {self.spam_block_threshold}) — {reason}{_R}")
                        return verdict
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

                    raw_score = data.get("risk_score")
                    score = int(raw_score or 0)
                    reason = str(data.get("reason", ""))
                    if score > highest_score:
                        highest_score = score
                        best_reason = reason

                    flagged = self.spam_verdict(bool(data.get("is_spam")), score if raw_score is not None else None, self.spam_block_threshold)
                    if bool(data.get("is_spam")) != flagged and raw_score is not None:
                        self.log_decision("spam", gemini=f"AI says is_spam={bool(data.get('is_spam'))}", text=f"score {score} vs cut-off {self.spam_block_threshold}",
                                          result="blocked" if flagged else "not blocked", detail=reason[:120])
                    if flagged:
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

    @staticmethod
    def spam_verdict(ai_says_spam: bool, score: Optional[int], threshold: int) -> bool:
        """Whether a call counts as SPAM for hanging up: the AI's risk score against the configured cut-off.
        Only when the AI gave no score does its plain yes/no decide."""
        if score is None:
            return bool(ai_says_spam)
        return score >= threshold

    def _save_spam_cache(self, number_key: str, is_spam: bool, risk_score: int, reason: str) -> None:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
                    self.asst_pacat = self._start_assistant_monitor_player()
            else:
                if self.asst_pacat and self.asst_pacat.poll() is None:
                    self.asst_pacat.terminate()
                    self.asst_pacat = None

            if mode in ["both", "caller"]:
                if self.caller_pacat is None or self.caller_pacat.poll() is not None:
                    sink = get_default_sink()
                    cmd = ["pacat", "--format=s16le", "--rate=16000", "--channels=1", "--raw", "--volume=65536"]
                    cmd.append(f"--device={sink}" if sink else "--device=auto_null")
                    self.caller_pacat = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            else:
                if self.caller_pacat and self.caller_pacat.poll() is None:
                    self.caller_pacat.terminate()
                    self.caller_pacat = None

            volume_pct = monitor_volume_percent()
            self._monitor_gain = monitor_volume_gain(volume_pct)
            for player in (self.asst_pacat,):
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
                        caller_player_alive = bool(self.caller_pacat and self.caller_pacat.poll() is None)
                        if "bluez_input" in src_name and (mode not in ["both", "caller"] or caller_player_alive):
                            sink = get_default_sink()
                            # Never touch links to the persistent auto_null sink (clock source on SBCs with disabled onboard audio).
                            # A direct link from the phone to the speakers ignores the monitor volume and doubles the caller's voice (echo):
                            # when the caller is monitored, the monitoring player is the only path to the speakers.
                            if "auto_null" not in dst_name and (("alsa_output" in dst_name) or (sink and sink in dst_name)):
                                await asyncio.create_subprocess_exec("pw-link", "-d", link_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                                if mode in ["both", "caller"] and (src_name, dst_name) not in self._direct_links_removed:
                                    self._direct_links_removed.add((src_name, dst_name))
                                    self.dbg.log("direct_caller_link_removed", source=src_name, destination=dst_name)
                                    print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Routing] Removed direct link {src_name} -> {dst_name} (it bypassed the monitor volume).{_R}")
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
    def _start_assistant_monitor_player() -> subprocess.Popen:
        """Starts the player that sends the assistant's voice to the monitoring speakers."""
        return subprocess.Popen(
            ["pacat", "--format=s16le", "--rate=24000", "--channels=1", "--raw", f"--volume={monitor_volume_percent() * 65536 // 100}"],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

    def _flush_assistant_monitor(self) -> None:
        """Drops the assistant speech that was already sent to the monitoring speakers. The model streams faster than
        real time, so most of a discarded answer is already buffered there when the caller interrupts. The phone
        side is emptied in the same way (queue dropped and player killed), and the monitor must match it."""
        player = self.asst_pacat
        if player is None:
            return
        writer = getattr(player, "monitor_writer", None)
        if writer is not None:
            writer.clear()
        if player.poll() is not None:
            return
        try:
            player.kill()
            player.wait(timeout=1.0)
        except Exception:
            pass
        # A new player is started at once so the beginning of the next answer is not lost while the routing manager notices
        if get_config("monitor_mode", "none") in ("both", "assistant"):
            try:
                self.asst_pacat = self._start_assistant_monitor_player()
            except Exception:
                self.asst_pacat = None

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

    def log_decision(self, kind: str, gemini: str = "", text: str = "", result: str = "", detail: str = "") -> None:
        """Decision log: what each signal said and what was decided. It goes to the console, the debug trace and the
        decision_log table, so the disagreements between Gemini and the text rules can be counted afterwards."""
        ts = get_timestamp()
        self.dbg.log("decision", kind=kind, gemini=gemini, text=text, result=result, detail=detail,
                     state=self._state_snapshot() if self.dbg.enabled else None)
        print(f"\n{_C_WARN}[{ts}] [DECISION] {kind}: Gemini={gemini or '-'} | text={text or '-'} -> {result}{(' (' + detail + ')') if detail else ''}{_R}", flush=True)
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
            conn.execute("INSERT INTO decision_log (call_id, ts, kind, gemini_signal, text_signal, result, detail) VALUES (?,?,?,?,?,?,?)",
                         (getattr(self, "call_id", None), ts, kind, gemini, text, result, detail))
            conn.commit()
        except Exception as e:
            self.dbg.log("db_error", where="decision_log", error=repr(e))
        finally:
            if conn:
                conn.close()

    def _show_filtered_turn(self, raw_text: str, reason: str) -> None:
        """What was heard but not used (noise, TV, echo, words removed by the cleaning) is always shown on the console
        and, when 'show_filtered_in_transcript' is on (default), written to the transcript with a distinct marker."""
        ts = get_timestamp()
        print(f"\n{_C_MUTED}[{ts}] 🔇 FILTERED ({reason}): {raw_text}{_R}", flush=True)
        if knob_bool("show_filtered_in_transcript", True):
            self.accumulated_transcript += f"\n\n🔇 [{ts}]: [FILTERED: {reason}]: {raw_text}"
            self.last_speaker = None
            self.update_transcription_db()

    @staticmethod
    def _new_mic_stats(now: float) -> Dict[str, Any]:
        return {"t": now, "n": 0, "gated": 0, "echo": 0, "greeting": 0, "hangover": 0, "odd": 0, "rms_sum": 0.0, "rms_max": 0.0}

    def _state_snapshot(self) -> Dict[str, Any]:
        """Compact picture of the call state, attached to the decisions written in the debug trace."""
        try:
            return {
                "hold": self.on_hold, "hanging_up": self.hanging_up, "farewell_pending": self.farewell_pending,
                "priority": self.priority_call, "hangup_source": getattr(self, "hangup_source", ""),
                "wait_limit": getattr(self, "category_wait_seconds", None),
                "since_user_s": round(time.time() - self.last_user_spoke_time, 1),
                "playing": self.currently_playing, "audio_q": self.audio_out_queue.qsize(),
            }
        except Exception:
            return {}

    def _check_priority_keywords(self, text: str, source: str = "gemini") -> None:
        """Extended attention mode when a caller sentence contains a keyword of a memory rule."""
        low = text.lower()
        for rule in self._memory_rules:
            if not isinstance(rule, dict):
                continue
            keywords = [str(k).lower() for k in rule.get("keywords", []) if str(k).strip()]
            if any(kw in low for kw in keywords):
                if not self.priority_call:
                    self.category_wait_seconds = float(rule.get("wait_seconds", 120))
                    self.dbg.log("priority", source=source, category=rule.get("category"), text=text)
                    self.log_system_message(f"Priority keyword detected. Activating extended attention mode ({int(self.category_wait_seconds)}s).", "⚠")
                    self.priority_call = True
                break

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
        # The next assistant chunk must open its own line instead of being glued to this system line
        self.last_speaker = None
        self.dbg.log("sys", text=clean_msg)
        self.update_transcription_db()

    def create_call_record_db(self, initial_tag: Optional[str] = None, initial_transcript: Optional[str] = None, audio_path_val: Optional[str] = None,
                              base_tag: Optional[str] = None, base_client_name: Optional[str] = None) -> None:
        """Creates the call row. base_tag / base_client_name are the label and name the call keeps when no contact rule
        overrides them; they stay NULL while the call is in progress and are filled when it ends."""
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
        c = conn.cursor()
        initial = initial_transcript if initial_transcript is not None else f"⚠ [{get_timestamp()}]: [SYSTEM]: Call Connected."
        self.accumulated_transcript = initial
        tag_to_use = initial_tag if initial_tag is not None else self.gui_data.get("ui_in_progress", "IN PROGRESS")
        rec_path = self.recording_path if audio_path_val is None else audio_path_val

        c.execute(
            "INSERT INTO calls (number, date, duration, spam_score, transcript, audio_path, client_audio_path, tag, summary, base_tag, base_client_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)",
            (self.caller_number, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 0, initial, rec_path, "", tag_to_use, base_tag, base_client_name)
        )
        self.call_id = c.lastrowid
        conn.commit()
        conn.close()

    def update_transcription_db(self, force: bool = False) -> None:
        """Persists the live transcript. Writes are merged (at most one per DB_WRITE_MIN_INTERVAL): the transcript
        used to be written to SQLite once per streamed chunk. The receive loop flushes the pending write."""
        if not self.call_id:
            return
        if not force and time.monotonic() - self._db_last_write < DB_WRITE_MIN_INTERVAL:
            self._db_dirty = True
            return
        self._write_transcript_now()

    def _write_transcript_now(self) -> None:
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
            conn.execute("UPDATE calls SET transcript=? WHERE id=?", (self.accumulated_transcript, self.call_id))
            conn.commit()
            self._db_last_write = time.monotonic()
            self._db_dirty = False
        except Exception as e:
            self.dbg.log("db_error", error=repr(e))
        finally:
            if conn:
                conn.close()

    def flush_transcription_db(self) -> None:
        if self._db_dirty and self.call_id:
            self._write_transcript_now()

    def save_to_db(self, name: str, message: str) -> None:
        if self.call_id:
            now_dt = datetime.datetime.now()
            exact_date = now_dt.strftime("%Y-%m-%d")
            exact_time = now_dt.strftime("%H:%M:%S")

            msg_fmt = self.assistant_data.get("ui_saved_message", "Message from {name}: {message}")
            final_msg = msg_fmt.format(name=name, message=message)

            visual_message = f"\n\n📝 [{exact_time}]: [SYSTEM]: *** {final_msg} ***"
            self.accumulated_transcript += visual_message
            self.update_transcription_db(force=True)

            try:
                conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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

    def _notify_mic_loss(self, reason: str) -> None:
        """The caller's audio stream stopped. This is not necessarily the user taking the call on the handset: the Bluetooth
        audio link may also have dropped. Say so, and record what PipeWire and the call know at this moment."""
        self.log_system_message("Caller audio stream lost (the call was routed to the handset or the Bluetooth audio link dropped). AI paused...", "⏸")
        self.dbg.log("mic_lost", reason=reason, mic_node_active=self.mic_node_active, target=self.pw_record_target, state=self._state_snapshot() if self.dbg.enabled else None)
        self._spawn(self._probe_bluetooth_audio())

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
                    self._notify_mic_loss("node_missing")
                    takeover_notified = True
                await asyncio.sleep(1.0)
                continue

            try:
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env)
            except Exception:
                if not takeover_notified:
                    self._notify_mic_loss("spawn_failed")
                    takeover_notified = True
                await asyncio.sleep(1.0)
                continue

            background_energy = 25.0
            consecutive_empty = 0
            valid_chunks = 0
            self._mic_carry = b""
            self._gate_hangover_left = 0

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
                    if self._mic_carry:
                        data = self._mic_carry + data
                        self._mic_carry = b""
                    if len(data) & 1:
                        # The read ended in the middle of a 16-bit sample: keep the odd byte for the next read. Without
                        # this every following sample is misaligned and the audio turns into noise.
                        self._mic_carry = data[-1:]
                        data = data[:-1]
                        self._mic_stats["odd"] += 1
                        if not data:
                            continue
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
                        self._note_self_interrupt()
                        await session.send_realtime_input(text=return_prompt)

                    raw_rms = calculate_rms(data)
                    if raw_rms < 250:
                        background_energy = 0.98 * background_energy + 0.02 * raw_rms

                    adaptive_gate = max(self.noise_gate_base, min(65, int(self.noise_gate_base + (background_energy * 0.35))))
                    noise_gate = min(80, adaptive_gate + 15) if self.on_hold else adaptive_gate

                    amplified_data = apply_gain(data, self.caller_gain)

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

                    self._monitor_write(self.caller_pacat, apply_gain(amplified_data, self._monitor_gain))

                    if self.greeting_in_progress:
                        if (now - self.greeting_started_time > 8.0) or (self.greeting_audio_received and not self.currently_playing and self.audio_out_queue.empty()):
                            self.greeting_in_progress = False

                    is_silence = (raw_rms < noise_gate)
                    used_hangover = False
                    if is_silence:
                        # Hangover: the gate stays open for a few chunks after speech so the soft ends of words are not chopped
                        if self._gate_hangover_left > 0:
                            self._gate_hangover_left -= 1
                            is_silence = False
                            used_hangover = True
                    else:
                        self._gate_hangover_left = self.mic_gate_hangover_chunks
                    is_echo = (self.software_echo_suppression and self.currently_playing)
                    is_protected_greeting = (self.protect_initial_greeting and self.greeting_in_progress)

                    if self.dbg.enabled:
                        st = self._mic_stats
                        st["n"] += 1
                        st["rms_sum"] += raw_rms
                        st["rms_max"] = max(st["rms_max"], raw_rms)
                        st["gated"] += 1 if is_silence else 0
                        st["hangover"] += 1 if used_hangover else 0
                        st["echo"] += 1 if is_echo else 0
                        st["greeting"] += 1 if is_protected_greeting else 0
                        if now - st["t"] >= 5.0:
                            self.dbg.log("mic_stats", chunks=st["n"], gated=st["gated"], hangover=st["hangover"], echo_muted=st["echo"],
                                         greeting_muted=st["greeting"], odd_reads=st["odd"], rms_avg=round(st["rms_sum"] / max(1, st["n"]), 1),
                                         rms_max=round(st["rms_max"], 1), gate=noise_gate, gain=self.caller_gain, hold=self.on_hold)
                            self._mic_stats = self._new_mic_stats(now)

                    if is_silence or is_echo or is_protected_greeting:
                        out_pcm = b"\x00" * len(amplified_data)
                    else:
                        out_pcm = amplified_data
                        self.user_turn_audio.append(amplified_data)

                    if self.online is not None:
                        self.online.feed(amplified_data, not (is_silence or is_echo or is_protected_greeting))

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
                self._notify_mic_loss("stream_ended")
                takeover_notified = True

            await asyncio.sleep(1.0)

    def _spawn(self, coro: Any) -> None:
        """Runs a coroutine in the background, keeping a reference so it is not garbage-collected half-way."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _release_hangup_calls(self, reason: str) -> None:
        """The hangup was cancelled or ignored: the model is still waiting for the answer to its tool call, and without it
        the model stays silent. Answer the call(s) with 'not hung up' and tell it, as text, to keep attending the caller."""
        calls, self._pending_hangup_calls = self._pending_hangup_calls, []
        if not calls or self._live_session is None:
            return
        self._spawn(self._answer_cancelled_hangup(self._live_session, calls, reason))

    async def _answer_cancelled_hangup(self, session: Any, calls: List[Tuple[str, str]], reason: str) -> None:
        message = self.prompts_data.get("hangup_cancelled", "")
        try:
            await session.send_tool_response(function_responses=[
                types.FunctionResponse(id=call_id, name=name, response={"ok": False, "hung_up": False, "note": message}) for call_id, name in calls])
            self.dbg.log("hangup_answer", action="tool_response", reason=reason, calls=len(calls))
        except Exception as e:
            self.dbg.log("hangup_answer", action="tool_response_failed", reason=reason, error=str(e))
        if message:
            try:
                self._note_self_interrupt()
                await session.send_realtime_input(text=message)
                self.dbg.log("hangup_answer", action="text_sent", reason=reason)
            except Exception as e:
                self.dbg.log("hangup_answer", action="text_failed", reason=reason, error=str(e))

    def _request_hangup_from_tool(self) -> None:
        """The model asked to hang up. That is its INTENT, and the goodbye in its own words comes from the same decision,
        so neither is a second opinion. What decides is the caller's side: a real goodbye, or silence once the farewell
        has been played, with no caller turn in between and no 'not finished' verdict of the text model. Everything
        goes through the same waiting logic as a goodbye heard in the assistant's text."""
        self._hangup_tool_seen = True
        if time.time() - self._farewell_veto_time < FAREWELL_VETO_SECONDS:
            self.log_decision("hangup", gemini="tool", text="the text model said the caller has not closed the call", result="ignored")
            self._release_hangup_calls("ignored")
            return
        if self.farewell_pending:
            self.log_decision("hangup", gemini="tool", text="goodbye already pending", result="pending", detail="waiting for the caller's reaction")
            return
        self.farewell_pending = True
        self.farewell_drained_since = 0.0
        self._closing_vote = None
        self._caller_spoke_since_intent = False
        self._intent_text = self._asst_turn_text
        self._intent_time = time.time()
        self.log_decision("hangup", gemini="tool", text="no caller reaction yet", result="pending", detail="waiting for the farewell audio and the caller's reaction")
        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] {self.assistant_name} asked to hang up (tool). Waiting for the audio to finish and the caller's reaction...{_R}")
        self._spawn(self._semantic_resolve_closing())

    def _note_self_interrupt(self) -> None:
        """Call right before sending an instruction as text to the model: it makes the model stop what it was saying,
        which the server reports as an interruption that did not come from the caller."""
        self._self_interrupt_until = time.time() + SELF_INTERRUPT_WINDOW_SECONDS

    def _itx_is_suspect_echo(self, text: str) -> bool:
        """True when a caller transcription most likely is the assistant's own voice coming back through the line.
        The caller really talking over the assistant makes the Live API report an interruption first; long text
        heard while the assistant speaks without one, or text that repeats what she just said, is suspect. Suspect
        text is still shown, but it never starts or ends a hold, nor confirms a farewell."""
        now = time.time()
        if not (self.currently_playing or now < self.playback_end_time + 0.7):
            return False
        if now - self._last_interrupted_time < 4.0:
            return False
        tokens = fold_text(text).split()
        if len(tokens) >= 8:
            return True
        if len(tokens) >= 3:
            heard = set(fold_text(" ".join([self._asst_turn_text] + [p[2] for p in self.recent_asst_phrases])).split())
            unique = set(tokens)
            return sum(1 for w in unique if w in heard) / len(unique) >= 0.7
        return False

    def _recent_dialogue(self, max_chars: int = 900) -> str:
        """The last lines of the call as CALLER / ASSISTANT text, for the semantic checks."""
        names = {"🗣": "CALLER", "📞": "ASSISTANT", "🔇": "CALLER (filtered as noise)"}
        lines = []
        for block in self.accumulated_transcript.split("\n\n"):
            m = re.match(r"^(🗣|📞|🔇)\s*\[[^\]]*\]:\s*(.*)$", block.strip(), re.S)
            if m:
                lines.append(f"{names[m.group(1)]}: {m.group(2).strip()}")
        return "\n".join(lines[-10:])[-max_chars:]

    def _semantic_budget(self, kind: str) -> bool:
        now = time.time()
        if self._semantic_count >= SEMANTIC_MAX_PER_CALL or now - self._semantic_last.get(kind, 0.0) < SEMANTIC_MIN_INTERVAL:
            return False
        self._semantic_last[kind] = now
        self._semantic_count += 1
        return True

    async def _semantic_vote(self, kind: str) -> Optional[bool]:
        """Second opinion from the text model on what the last lines of the call mean. True / False, or None when it
        is unsure or unavailable: a missing answer is never a vote."""
        if not self.semantic_votes:
            return None
        context = self._recent_dialogue()
        if not context:
            return None
        schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no", "unsure"]}, "reason": {"type": "string"}}, "required": ["answer"]}
        header = self.prompts_data.get("semantic_header", "")
        question = self.prompts_data.get("semantic_questions", {}).get(kind, "")
        if not header or not question:
            return None
        prompt = header.format(context=context) + question
        started = time.time()
        try:
            config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema, temperature=0.0,
                                                 thinking_config=types.ThinkingConfig(thinking_budget=0))
            response = None
            for attempt in (1, 2):
                remaining = SEMANTIC_VOTE_TIMEOUT - (time.time() - started)
                if remaining <= 0.5:
                    raise asyncio.TimeoutError()
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(self.client_text.models.generate_content, model=self.model_text, contents=prompt, config=config),
                        timeout=remaining)
                    break
                except asyncio.TimeoutError:
                    raise
                except Exception as transient:
                    if attempt == 2:
                        raise
                    self.dbg.log("semantic_vote_retry", kind=kind, error=repr(transient))
                    await asyncio.sleep(0.6)
            data = json.loads(clean_json_text(extract_response_text(response, default="{}")))
            answer = str(data.get("answer", "")).lower()
            self.dbg.log("semantic_vote", kind=kind, answer=answer, reason=data.get("reason"), ms=int((time.time() - started) * 1000), context=context)
            print(f"{_C_MUTED}[{get_timestamp()}] [Semantic] {kind}: {answer} ({data.get('reason', '')}){_R}", flush=True)
            return True if answer == "yes" else (False if answer == "no" else None)
        except Exception as e:
            self.dbg.log("semantic_vote_error", kind=kind, error=repr(e), ms=int((time.time() - started) * 1000))
            print(f"{_C_MUTED}[{get_timestamp()}] [Semantic] {kind}: no answer ({type(e).__name__}: {e}){_R}", flush=True)
            return None

    async def _semantic_resolve_blocked_hold(self) -> None:
        """The assistant said a waiting phrase but no wait-request keyword was heard from the caller: ask the text model."""
        if not self._semantic_budget("hold_request"):
            return
        if await self._semantic_vote("hold_request") and not self.on_hold and not self.hanging_up:
            self.on_hold = True
            self.current_wait_start = self.last_user_spoke_time = time.time()
            self._last_wait_request_time = time.time()
            self.last_speaker = None
            self.log_decision("hold", gemini="assistant said a waiting phrase", text="no keyword, text model: the caller asked to wait", result="activated", detail="semantic vote")
            self.log_system_message(f"Hold activated (semantic check). Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")

    async def _semantic_resolve_closing(self) -> None:
        """Runs while the farewell is being played: asks the text model whether the caller really closed the call."""
        vote = await self._semantic_vote("caller_closing")
        if self.farewell_pending:
            self._closing_vote = vote

    async def _semantic_resolve_resume(self) -> None:
        """A caller turn was dismissed during a hold: ask the text model whether it was addressed to the assistant."""
        if not self.on_hold or not self._semantic_budget("addressed_to_assistant"):
            return
        if await self._semantic_vote("addressed_to_assistant") and self.on_hold and not self.hanging_up:
            self.on_hold = False
            if self.current_wait_start > 0:
                self.accumulated_wait_time += (time.time() - self.current_wait_start)
            self.current_wait_start = 0.0
            self.log_decision("hold", gemini="-", text="dismissed turns, text model: addressed to the assistant", result="ended", detail="semantic vote")
            self.log_system_message("Return from hold detected (semantic check). Resuming conversation...", "⏳")

    async def _probe_bluetooth_audio(self) -> None:
        """Logs, once per call, what PipeWire reports about the Bluetooth audio link (codec / profile)."""
        summary: Dict[str, Any]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec("pw-dump", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            summary = summarize_bt_audio(json.loads(out.decode("utf-8", errors="ignore") or "[]"))
        except FileNotFoundError:
            summary = {"codec_guess": "unknown", "error": "pw-dump not found"}
        except Exception as e:
            summary = {"codec_guess": "unknown", "error": repr(e)}
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.dbg.log("bt_audio", **summary)
        print(f"{_C_MUTED}[{get_timestamp()}] [Audio] Bluetooth link: {summary['codec_guess']}{(' | ' + summary['error']) if summary.get('error') else ''}{_R}", flush=True)

    @staticmethod
    def _texts_agree(a: str, b: str) -> bool:
        fa, fb = fold_text(a), fold_text(b)
        return bool(fa) and (fa == fb or difflib.SequenceMatcher(None, fa, fb).ratio() >= 0.97)

    def _register_caller_line(self, ts: str, text: str) -> None:
        """Remembers a caller line just written to the transcript, so an alternative transcription can be attached to it."""
        self._alt_lines.append({"t": time.time(), "marker": f"🗣 [{ts}]: {text}", "text": text, "labels": set()})
        del self._alt_lines[:-12]
        self._attach_pending_alternatives()

    @staticmethod
    def _alt_pairing(line_text: str, alt_text: str, dt: float) -> Tuple[float, bool]:
        ratio = difflib.SequenceMatcher(None, fold_text(line_text), fold_text(alt_text)).ratio()
        return ratio, (ratio >= ALT_MIN_RATIO or dt <= ALT_NEAR_S)

    def _attach_alternative(self, line: Dict[str, Any], label: str, text: str) -> bool:
        """Writes ' | [label]: text' right after the Gemini line in the transcript (nothing is added when both agree)."""
        if label in line["labels"]:
            return False
        idx = self.accumulated_transcript.rfind(line["marker"])
        if idx < 0:
            return False
        line["labels"].add(label)
        self._alt_total += 1
        if self._texts_agree(line["text"], text):
            self._alt_agree += 1
            self.dbg.log("alt_agrees", label=label, text=text)
            return True
        addition = f" | [{label}]: {text}"
        end = idx + len(line["marker"])
        self.accumulated_transcript = self.accumulated_transcript[:end] + addition + self.accumulated_transcript[end:]
        line["marker"] += addition
        self.dbg.log("alt_attached", label=label, gemini=line["text"], alternative=text)
        self.update_transcription_db()
        return True

    def add_alternative(self, label: str, text: str, ts: str = "", vocab_only: bool = False) -> None:
        """An alternative transcription (online, Whisper) of what the caller said: it goes right next to Gemini's line,
        or waits a few seconds for that line if it has not been written yet."""
        now = time.time()
        best: Optional[Tuple[float, Dict[str, Any]]] = None
        for line in self._alt_lines:
            dt = now - line["t"]
            if dt > ALT_ATTACH_WINDOW_S or label in line["labels"]:
                continue
            ratio, ok = self._alt_pairing(line["text"], text, dt)
            if ok and (best is None or (ratio, line["t"]) > (best[0], best[1]["t"])):
                best = (ratio, line)
        if best is not None and self._attach_alternative(best[1], label, text):
            return
        self._alt_pending.append({"t": now, "label": label, "text": text, "ts": ts or get_timestamp(), "vocab_only": vocab_only})

    def _attach_pending_alternatives(self) -> None:
        if not self._alt_pending or not self._alt_lines:
            return
        now = time.time()
        line = self._alt_lines[-1]
        remaining = []
        for p in self._alt_pending:
            attached = False
            if now - p["t"] <= ALT_ATTACH_WINDOW_S and p["label"] not in line["labels"]:
                _, ok = self._alt_pairing(line["text"], p["text"], now - p["t"])
                attached = ok and self._attach_alternative(line, p["label"], p["text"])
            if not attached:
                remaining.append(p)
        self._alt_pending = remaining

    def _flush_pending_alternatives(self, force: bool = False) -> None:
        """Alternative texts that found no Gemini line: written on their own line (or filtered when they look invented)."""
        if not self._alt_pending:
            return
        now = time.time()
        keep = []
        for p in self._alt_pending:
            if not force and now - p["t"] < ALT_ORPHAN_AFTER_S:
                keep.append(p)
            elif p["vocab_only"]:
                self._show_filtered_turn(p["text"], f"{p['label']}: only a name from the vocabulary, Gemini heard nothing (possible invention)")
            else:
                self.accumulated_transcript += f"\n\n🌐 [{p['ts']}]: [{p['label']}]: {p['text']}"
                self.last_speaker = None
                self.update_transcription_db()
        self._alt_pending = keep

    def _on_online_final(self, text: str, heard_at: float) -> None:
        """A final text from the online transcriber: shown next to Gemini's line, stored, and used as one more opinion."""
        text = re.sub(r"\s+", " ", text).strip()
        if not text or self._post_processed:
            return
        ts = get_timestamp()
        valid = (self.is_valid_text(text) and not self._has_foreign_language_noise(text)
                 and not self._has_excessive_repetition(text) and not self._is_transcription_noise(text))
        suspect = self._itx_is_suspect_echo(text)
        if suspect and heard_at and self._asst_turn_start_time and heard_at < self._asst_turn_start_time - 0.2:
            suspect = False   # the caller finished speaking before the assistant started this answer: it is a late text, not an echo
        tokens = fold_text(text).split()
        vocab_tokens = {w for term in (self.online.vocabulary if self.online else []) for w in fold_text(term).split()}
        # A vocabulary bias can make the model "hear" a name in noise: a text that is only a name, with no Gemini line near it, is not trusted
        vocab_only = bool(tokens) and len(tokens) <= 2 and all(t in vocab_tokens for t in tokens)
        if self.online is not None:
            self.online.finals += 1
            self.online.out_chars += len(text)
        self.dbg.log("online_final", ts=ts, text=text, valid=valid, suspect=suspect, vocab_only=vocab_only,
                     delay_s=round(time.time() - heard_at, 2) if heard_at else None)
        if not valid:
            self._show_filtered_turn(text, "online transcription filtered")
            return
        color = "\033[36m" if SUPPORTS_COLOR else ""
        print(f"\n{color}· [{ONLINE_LABEL}/{ts}]: {text}{_R}", flush=True)
        self.add_alternative(ONLINE_LABEL, text, ts, vocab_only)
        if not vocab_only:
            self._apply_whisper_signals(text, "", heard_at, suspect, ONLINE_LABEL)

    def _log_playback_stats(self) -> None:
        """Every 5 s: how much model audio arrived and how much reached the player (only with the debug trace on)."""
        now = time.time()
        if not self.dbg.enabled or now - self._pb_last_stats < 5.0:
            return
        self._pb_last_stats = now
        proc = self._playback_proc
        self.dbg.log("playback_stats", received_bytes=self._pb_in_bytes, written_bytes=self._pb_written_bytes, write_failures=self._pb_write_fail,
                     last_error=self._pb_last_error, spawns=self._pb_spawns, player_alive=(proc is not None and proc.poll() is None),
                     player_returncode=(None if proc is None else proc.poll()), queue=self.audio_out_queue.qsize(), playing=self.currently_playing,
                     mic_node_active=getattr(self, "mic_node_active", None), target=self.pw_playback_target)

    def _playback_summary(self) -> None:
        """Console line at the end of the call: did the model audio reach the player?"""
        seconds = self._pb_written_bytes / PLAYBACK_BYTES_PER_SECOND
        line = (f"[Playback] model audio received {self._pb_in_bytes} B, written to the player {self._pb_written_bytes} B (~{seconds:.1f} s), "
                f"write failures {self._pb_write_fail}, player starts {self._pb_spawns}")
        if self._pb_in_bytes > 0 and self._pb_written_bytes == 0:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}{line}. NOTHING reached the player ({self._pb_last_error or 'no error recorded'}){_R}", flush=True)
        elif self._pb_in_bytes == 0:
            print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}{line}. The model sent no audio{_R}", flush=True)
        else:
            print(f"{_C_MUTED}[{get_timestamp()}] {line}{_R}", flush=True)
        self.dbg.log("playback_summary", received_bytes=self._pb_in_bytes, written_bytes=self._pb_written_bytes, write_failures=self._pb_write_fail,
                     last_error=self._pb_last_error, spawns=self._pb_spawns)

    def _on_model_interrupted(self) -> None:
        """The Live API discarded the generation because the caller started speaking. The audio it had already sent
        is still queued here (the model streams faster than real time): it must be dropped and the player stopped,
        otherwise the assistant keeps talking over the caller and that voice comes back through the microphone,
        where it is transcribed as if the caller had said it."""
        dropped = 0
        self_inflicted = time.time() < self._self_interrupt_until
        if not self_inflicted:
            self._last_interrupted_time = time.time()
        if self.flush_on_interrupt and not self_inflicted:
            try:
                while True:
                    self.audio_out_queue.get_nowait()
                    self.audio_out_queue.task_done()
                    dropped += 1
            except queue.Empty:
                pass
            proc = self._playback_proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()  # The playback thread notices the dead player and starts a new one with the next audio
                except Exception:
                    pass
            self._flush_assistant_monitor()
            self.playback_end_time = time.time()
            self._asst_chunk_buffer = ""
            self._asst_turn_text = ""
            self._asst_turn_last_time = 0.0
        self.dbg.log("interrupted", flushed=self.flush_on_interrupt and not self_inflicted, self_inflicted=self_inflicted, dropped_chunks=dropped, state=self._state_snapshot())
        who = "by an instruction sent to the model (audio kept)" if self_inflicted else f"by the caller (queued audio dropped: {dropped})"
        print(f"\n{_C_MUTED}[{get_timestamp()}] [Live] Generation interrupted {who}{_R}", flush=True)

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
                            self.dbg.log("playback_proc_died", returncode=proc.poll(), spawns=self._pb_spawns)
                            try:
                                proc.kill()
                                proc.wait()
                            except Exception:
                                pass
                        if self._pb_stderr is None and self.dbg.enabled:
                            try:
                                self._pb_stderr = open(self.dbg.path.replace(".jsonl", "_pw-play.log"), "ab")
                            except Exception:
                                self._pb_stderr = None
                        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._pb_stderr or subprocess.DEVNULL, env=env)
                        self._playback_proc = proc
                        self._pb_spawns += 1
                        self.dbg.log("playback_proc_started", pid=proc.pid, target=self.pw_playback_target, spawns=self._pb_spawns)

                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                        self._pb_written_bytes += len(chunk)
                        self.last_chunk_audio_time = time.time()
                        self.playback_end_time = max(self.playback_end_time, self.last_chunk_audio_time) + len(chunk) / PLAYBACK_BYTES_PER_SECOND
                    except Exception as e:
                        self._pb_write_fail += 1
                        self._pb_last_error = repr(e)

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

    async def heal_transcription_whisper(self, audio_bytes_list: list, gemini_txt: str, turn_ts: str = "", suspect: bool = False) -> None:
        """Queues the caller audio of one transcription segment for Whisper. One worker runs the jobs one after
        another: launching a whisper-cli per segment in parallel saturates the CPU and delays the whole call."""
        if self._whisper_queue is None:
            self._whisper_queue = asyncio.Queue(maxsize=WHISPER_QUEUE_MAX)
        if self._whisper_worker_task is None or self._whisper_worker_task.done():
            self._whisper_worker_task = asyncio.create_task(self._whisper_worker())
        try:
            self._whisper_queue.put_nowait((audio_bytes_list, gemini_txt, turn_ts, time.time(), suspect))
            self.dbg.log("whisper_queued", ts=turn_ts, gemini=gemini_txt, qsize=self._whisper_queue.qsize(),
                         audio_s=round(sum(len(c) for c in audio_bytes_list) / 32000.0, 2))
        except asyncio.QueueFull:
            self.dbg.log("whisper_dropped", ts=turn_ts, reason="queue_full")

    async def _whisper_worker(self) -> None:
        while True:
            job = await self._whisper_queue.get()
            try:
                await self._whisper_process(*job)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.dbg.log("whisper_error", error=repr(e))
            finally:
                self._whisper_queue.task_done()

    async def _whisper_process(self, audio_bytes_list: list, gemini_txt: str, turn_ts: str, queued_at: float, suspect: bool = False) -> None:
        if self._post_processed:
            return
        model_path = os.path.join(BASE_DIR, "models", f"ggml-{self.whisper_full_model}.bin")
        if not WHISPER_BIN or not os.path.exists(WHISPER_BIN) or not os.path.exists(model_path):
            if not self._whisper_missing_logged:
                self._whisper_missing_logged = True
                print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Whisper] Real-time mode is on but cannot run. "
                      f"whisper-cli: {WHISPER_BIN or 'NOT FOUND'} | model: {model_path} ({'found' if os.path.exists(model_path) else 'NOT FOUND'}){_R}")
                self.dbg.log("whisper_unavailable", bin=WHISPER_BIN or None, model=model_path, model_exists=os.path.exists(model_path))
            return
        tmp_wav = f"/tmp/whisper_turn_{str(uuid.uuid4())[:8]}.wav"
        started = time.time()
        try:
            with wave.open(tmp_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                for chunk in audio_bytes_list:
                    wf.writeframes(chunk)
            lang_arg = self.current_lang.split("-")[0]
            cmd = [WHISPER_BIN, "-l", lang_arg, "-t", str(self.whisper_threads), "-m", model_path, "-f", tmp_wav]
            if self.whisper_prompt and await asyncio.to_thread(whisper_supports_prompt):
                cmd += ["--prompt", self.whisper_prompt]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            run_ms = int((time.time() - started) * 1000)
            if self._post_processed:
                return
            if not stdout:
                self.dbg.log("whisper_empty", ts=turn_ts, run_ms=run_ms, returncode=proc.returncode)
                return
            whisper_txt = clean_whisper_output(stdout.decode("utf-8", errors="ignore"))
            wv = not (not whisper_txt.strip() or self._has_foreign_language_noise(whisper_txt) or self._has_excessive_repetition(whisper_txt) or self._is_transcription_noise(whisper_txt))
            gv = not (not gemini_txt.strip() or self._has_foreign_language_noise(gemini_txt) or self._has_excessive_repetition(gemini_txt) or self._is_transcription_noise(gemini_txt))

            w_label = f"Whisper.cpp {self.whisper_full_model}"
            self._alt_total += 1
            if gv and wv and self._texts_agree(gemini_txt, whisper_txt):
                self._alt_agree += 1
                combined = gemini_txt
            else:
                combined = (
                    f"{gemini_txt} | [{w_label}]: {whisper_txt}" if gv and wv
                    else ("[Noise Filtered]" if not gv and not wv else f"[Noise Filtered] | [{w_label}]: {whisper_txt}" if wv else f"{gemini_txt} | [{w_label}]: [Noise Filtered]")
                )
            pat = f"🗣 [{turn_ts}]: {gemini_txt}"
            if pat in self.accumulated_transcript:
                self.accumulated_transcript = self.accumulated_transcript.replace(pat, f"🗣 [{turn_ts}]: {combined}")

            _C_WHISPER = "\033[33m" if SUPPORTS_COLOR else ""
            whisper_display = whisper_txt if wv else "[Noise Filtered]"
            print(f"\n{_C_WHISPER}· [{w_label}/{turn_ts}]: {whisper_display}{_R}", flush=True)
            self.update_transcription_db()

            if self.dbg.enabled:
                norm = lambda t: re.sub(r"[^\w\s]", "", t.lower()).strip()
                self.dbg.log("whisper_result", ts=turn_ts, whisper=whisper_txt, gemini=gemini_txt, whisper_ok=wv, gemini_ok=gv,
                             similarity=round(difflib.SequenceMatcher(None, norm(gemini_txt), norm(whisper_txt)).ratio(), 2),
                             run_ms=run_ms, wait_ms=int((started - queued_at) * 1000),
                             audio_s=round(sum(len(c) for c in audio_bytes_list) / 32000.0, 2))
            if wv:
                self._apply_whisper_signals(whisper_txt, gemini_txt, queued_at, suspect)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.dbg.log("whisper_error", error=repr(e))
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    def _apply_whisper_signals(self, whisper_txt: str, gemini_txt: str, queued_at: float, suspect: bool = False, source: str = "Whisper") -> None:
        """Whisper is an independent second reading of the same caller audio. Its text feeds the same detectors as
        Gemini's transcription, so a word misheard by one of them can still be caught by the other. Results of
        segments heard before the last change of a state are ignored (they describe the past)."""
        if not self.whisper_signals or self.hanging_up or self._post_processed:
            return
        if suspect:
            self.dbg.log("whisper_signal_skipped", reason="possible echo of the assistant", source=source, whisper=whisper_txt)
            return
        now = time.time()
        hold_since = self.__dict__.get("_tf_on_hold_since", 0.0)
        hold_phrase = self._matches_any_phrase(self._without_ignore_hold_words(whisper_txt), self._caller_hold_phrases(), fuzzy=True)

        if self._is_wait_request(whisper_txt):
            self._last_wait_request_time = max(self._last_wait_request_time, queued_at)

        if queued_at > hold_since:
            if not self.on_hold and hold_phrase:
                self.log_decision("hold", gemini=f"heard: {gemini_txt}" if gemini_txt else "-", text=f"{source}: {whisper_txt}", result="activated", detail=f"{source} keyword")
                self.on_hold = True
                self.current_wait_start = self.last_user_spoke_time = now
                self.last_speaker = None
                self.log_system_message(f"Hold activated by caller (heard by {source}). Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")
            elif self.on_hold and not hold_phrase and self._check_wait_return(whisper_txt):
                self.log_decision("hold", gemini=f"heard: {gemini_txt}" if gemini_txt else "-", text=f"{source}: {whisper_txt}", result="ended", detail=f"{source} return keyword")
                self.log_system_message(f"Return from hold detected (heard by {source}). Resuming conversation...", "⏳")
                self.on_hold = False
                if self.current_wait_start > 0:
                    self.accumulated_wait_time += (now - self.current_wait_start)
                self.current_wait_start = 0.0

        self._check_priority_keywords(whisper_txt, source.lower())

        if self.farewell_pending and queued_at > self.__dict__.get("_tf_farewell_pending_since", 0.0) and self._is_farewell(whisper_txt, fuzzy=True):
            self.log_decision("hangup", gemini=f"heard: {gemini_txt}" if gemini_txt else "-", text=f"{source}: {whisper_txt}", result="caller goodbye", detail=source)
            self._commit_farewell_hangup(f"the caller also said goodbye (heard by {source})")

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
        if self.current_lang.split("-")[0].lower() in LATIN_SCRIPT_LANGS and non_latin_letter_ratio(text) > 0.5:
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

    def _matches_any_phrase(self, text: str, phrases: list, fuzzy: bool = False) -> bool:
        return matches_any_phrase(text, phrases, fuzzy and self.fuzzy_keywords)

    def _is_farewell(self, text: str, fuzzy: bool = False) -> bool:
        """True when the text holds a real farewell (farewell word neither denied nor merely mentioned).
        fuzzy=True tolerates recognition errors and is only for caller speech."""
        return find_farewell(text, self.words_data.get("cut_words", []), self.words_data.get("goodbye_veto_words", []), self.words_data.get("goodbye_meta_words", []), fuzzy and self.fuzzy_keywords)

    def _cancel_pending_farewell(self, reason: str) -> None:
        self.dbg.log("farewell", action="cancel", reason=reason, state=self._state_snapshot())
        self.log_decision("hangup", gemini="assistant text had a goodbye", text=reason, result="cancelled")
        self.farewell_pending = False
        self.farewell_drained_since = 0.0
        self._hangup_tool_seen = False
        self._closing_vote = None
        self._caller_spoke_since_intent = False
        self._asst_chunk_buffer = ""
        print(f"\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Pending farewell cancelled ({reason}).{_R}")
        self._release_hangup_calls(reason)

    def _commit_farewell_hangup(self, reason: str) -> None:
        self.dbg.log("farewell", action="commit", reason=reason, state=self._state_snapshot())
        self.log_decision("hangup", gemini="hangup tool seen" if self._hangup_tool_seen else "no hangup tool call",
                          text="goodbye in the text" if not self._hangup_tool_seen else "goodbye intent", result="hangup", detail=reason)
        self.farewell_pending = False
        self.farewell_drained_since = 0.0
        self.hanging_up = self.hangup_triggered = True
        self.hangup_triggered_time = time.time()
        self.hangup_source = "tool" if self._hangup_tool_seen else "cut_words"
        self._hangup_tool_seen = False
        self._pending_hangup_calls = []
        self._closing_vote = None
        self._caller_spoke_since_intent = False
        self.hangup_reason = "completed"
        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Farewell confirmed ({reason}). Initiating clean call cut...{_R}")

    def _check_wait_return(self, text: str) -> bool:
        triggers = list(self.words_data.get("return_triggers", []))
        triggers.extend([self.assistant_name.lower(), self.boss_name.lower()])
        return self._matches_any_phrase(text, triggers, fuzzy=True)

    def _without_ignore_hold_words(self, text: str) -> str:
        safe = text.lower()
        for iw in self.words_data.get("ignore_hold_words", []):
            safe = safe.replace(iw.lower(), "")
        return safe

    def _is_farewell_ack(self, text: str) -> bool:
        """True when a caller turn is only an acknowledgement that goes with closing a call ('vale, gracias', 'no, nada
        más', 'igualmente'): after the assistant's goodbye it does not mean the caller wants to go on. Anything else
        ('espera, espera', '¿oye?', a question, a new request) does. Languages without farewell_ack_words keep the
        old rule: a turn of farewell_cancel_min_words words or more means the caller goes on."""
        phrases = self.words_data.get("farewell_ack_words")
        if not phrases:
            return len(text.split()) < self.farewell_cancel_min_words
        remainder = " " + fold_text(text) + " "
        for phrase in sorted((fold_text(p) for p in phrases if fold_text(p)), key=len, reverse=True):
            remainder = remainder.replace(" " + phrase + " ", " ")
            remainder = remainder.replace(" " + phrase + " ", " ")
        return not remainder.strip()

    def _caller_hold_phrases(self) -> list:
        """What the CALLER says to ask for a wait. wait_request_words holds clear requests only ('un momento', 'espere un
        momento', 'no cuelgue'...): the bare word 'espera' is left out on purpose, because callers also say it as a noun
        ('el modo de espera', 'estoy a la espera') and that opened false holds. Languages without the list keep hold_words."""
        return self.words_data.get("wait_request_words") or self.words_data.get("hold_words", [])

    def _is_wait_request(self, text: str) -> bool:
        """True when the caller clearly asks (or tells) the assistant to wait."""
        return self._matches_any_phrase(self._without_ignore_hold_words(text), self._caller_hold_phrases(), fuzzy=True)

    def _hold_acceptance_allowed(self, window: float = HOLD_ACCEPT_WINDOW_SECONDS) -> bool:
        """The assistant's own "I'll wait" phrase only starts a hold when the caller has just asked to wait.
        Without it, phrases such as "for a moment" or "I remain waiting for the details" opened false holds.
        Languages without a wait_request_words list keep the previous behaviour."""
        if not self.words_data.get("wait_request_words"):
            return True
        return self._last_wait_request_time > 0.0 and (time.time() - self._last_wait_request_time) <= window

    def _note_hold_phrase_without_request(self) -> None:
        now = time.time()
        if now - self._hold_gate_last_note > 4.0:
            self._hold_gate_last_note = now
            self.log_decision("hold", gemini="assistant said a waiting phrase", text="the caller did not ask to wait", result="not activated")
            self._spawn(self._semantic_resolve_blocked_hold())

    def _hold_note_dismissed_caller_turn(self, text: str) -> None:
        """A caller turn was dismissed during a hold (no return keyword). Remember it: if the assistant then answers it
        with a real reply, the conversation has in fact resumed. A new wait request is not such a turn."""
        if self._is_wait_request(text):
            return
        self._hold_pending_caller_time = time.time()

    def _register_hold_exchange(self) -> None:
        """Second opinion to leave a hold. The return keywords are a closed list, so a caller who comes back without
        using one stayed 'on hold' while the conversation went on. When the assistant gives a real, non-hold reply to
        HOLD_RESUME_EXCHANGES consecutive dismissed caller turns, the hold is considered over."""
        if not self.on_hold:
            self._hold_pending_caller_time = 0.0
            self._hold_resume_count = 0
            return
        if self._hold_pending_caller_time <= 0.0:
            return
        now = time.time()
        if now - self._hold_pending_caller_time > HOLD_RESUME_REPLY_SECONDS:
            self._hold_pending_caller_time = 0.0
            return
        turn = self._asst_turn_text
        if len(turn.split()) < HOLD_RESUME_MIN_WORDS:
            return
        if self._matches_any_phrase(self._without_ignore_hold_words(turn), self.words_data.get("hold_words", [])):
            return
        self._hold_pending_caller_time = 0.0
        if self._hold_resume_count == 0 or now - self._hold_resume_first_time > HOLD_RESUME_WINDOW_SECONDS:
            self._hold_resume_count = 1
            self._hold_resume_first_time = now
        else:
            self._hold_resume_count += 1
        if self._hold_resume_count >= HOLD_RESUME_EXCHANGES:
            self._hold_resume_count = 0
            self.log_system_message("Return from hold inferred: the assistant answered consecutive caller turns. Resuming conversation...", "⏳")
            self.log_decision("hold", gemini="assistant answered the caller", text="no return keyword", result="ended", detail="behaviour evidence")
            self.on_hold = False
            if self.current_wait_start > 0:
                self.accumulated_wait_time += (time.time() - self.current_wait_start)
            self.current_wait_start = 0.0

    async def receive_audio_and_tools(self, session) -> None:
        self._live_session = session
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

        self._note_self_interrupt()

        await session.send_realtime_input(text=greeting)
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_OK}[{self.assistant_name}] Connected. Conversation started.{_R}")

        while self.running:
            if self.farewell_pending and not self.hanging_up:
                if self.is_playback_drained():
                    if self.farewell_drained_since <= 0.0:
                        self.farewell_drained_since = time.time()
                    elif time.time() - self.farewell_drained_since >= self.farewell_grace_seconds:
                        farewell_in_turn = self._is_farewell(self._asst_turn_text)
                        farewell_remembered = self._caller_spoke_since_intent and self._is_farewell(self._intent_text)
                        newer_turn = self._asst_turn_start_time > self._intent_time + 1.0   # a NEW assistant turn, not the goodbye's own
                        if not (self._hangup_tool_seen or farewell_in_turn or farewell_remembered):
                            self._cancel_pending_farewell("the farewell no longer stands in the full turn")
                        elif not farewell_in_turn and (newer_turn or "?" in self._asst_turn_text):
                            # The last thing the assistant said is a question or an answer, not a goodbye: it expects the caller
                            self._cancel_pending_farewell("the conversation went on after the goodbye request")
                        elif self._closing_vote is False:
                            # Silence is not a goodbye when the caller only mentioned / tested a goodbye or still has a request.
                            self._farewell_veto_time = time.time()
                            self._cancel_pending_farewell("the text model says the caller has not closed the conversation")
                        else:
                            self._commit_farewell_hangup("no caller reply after the farewell")
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
                        self._note_self_interrupt()
                        await session.send_realtime_input(text=self.prompts_data.get("silence_grace_end", ""))

                elif self.on_hold and total_hold_time > 900.0 and not self.waiting_definitive_cut:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.log_system_message("Maximum accumulated hold time (15 mins) exceeded. Starting 15s grace warning...", "⚠")
                    self._note_self_interrupt()
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))

                elif time_without_user > silence_threshold and not self.hello_question_sent and not self.waiting_definitive_cut:
                    self.log_system_message(f"{int(silence_threshold)}s without response. Asking if someone is there...", "⏳")
                    self.hello_question_sent = True
                    self.last_user_spoke_time = time.time()
                    self._note_self_interrupt()
                    await session.send_realtime_input(text=self.prompts_data.get("hello_question", ""))

                elif self.hello_question_sent and not self.waiting_definitive_cut and time_without_user > 15.0:
                    self.waiting_definitive_cut = True
                    self.cut_warning_time = time.time()
                    self.last_user_spoke_time = time.time()
                    self.log_system_message("Continued silence. Starting 15s grace period...", "⏳")
                    self._note_self_interrupt()
                    await session.send_realtime_input(text=self.prompts_data.get("silence_grace_start", ""))

            self.flush_transcription_db()
            self._flush_pending_alternatives()
            self._log_playback_stats()
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
                    self.dbg.log("tool_call", name=fc.name, args=dict(fc.args), decision=decision.status, reason=getattr(decision, "reason", ""), state=self._state_snapshot())
                    if decision.status == "allow":
                        if fc.name == "hangup":
                            self._pending_hangup_calls.append((fc.id, fc.name))
                            self._request_hangup_from_tool()
                        elif fc.name == "save_message":
                            self.save_to_db(fc.args.get("caller_name"), fc.args.get("message_text"))
                            function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": True}))
                    else:
                        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[SECURITY POLICY]: Action '{fc.name}' denied. Reason: {decision.reason}{_R}")
                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": False, "error": f"Action denied by security policy: {decision.reason}"}))
                if function_responses:
                    await session.send_tool_response(function_responses=function_responses)

            if getattr(msg, "go_away", None):
                self.dbg.log("go_away", info=str(msg.go_away))

            sc = getattr(msg, "server_content", None)
            if sc:
                if getattr(sc, "interrupted", False):
                    self._on_model_interrupted()
                for _event_flag in ("turn_complete", "generation_complete"):
                    if getattr(sc, _event_flag, False):
                        self.dbg.log(_event_flag)
                itx = getattr(sc, "input_transcription", None)
                if itx and itx.text and self.hanging_up and getattr(self, "hangup_triggered", False):
                    itx = None

                if itx and getattr(itx, "text", None):
                    raw_itx_text = itx.text
                    cleaned_caller_txt = self._strip_assistant_echo_from_input(itx.text)
                    echo_changed = (cleaned_caller_txt != raw_itx_text)
                    cleaned_caller_txt = re.sub(r"<[^<>\n]{1,40}>", "", cleaned_caller_txt or "")
                    cleaned_caller_txt = self._strip_foreign_words(cleaned_caller_txt)
                    drop_reason = ""
                    if not cleaned_caller_txt:
                        drop_reason = "empty_after_cleaning"
                    elif not self.is_valid_text(cleaned_caller_txt):
                        drop_reason = "invalid_text"
                    elif self._is_transcription_noise(cleaned_caller_txt):
                        drop_reason = "transcription_noise"
                    if self.dbg.enabled:
                        self.dbg.log("in_tx", raw=raw_itx_text, clean=cleaned_caller_txt, echo_stripped=echo_changed, dropped=drop_reason or None, state=self._state_snapshot())
                    if drop_reason:
                        self._show_filtered_turn(raw_itx_text, drop_reason)
                        itx = None
                    else:
                        if re.sub(r"\W+", "", raw_itx_text) != re.sub(r"\W+", "", cleaned_caller_txt):
                            self._show_filtered_turn(raw_itx_text, "original text before cleaning")
                        itx.text = cleaned_caller_txt

                if itx and getattr(itx, "text", None):
                    self.last_user_spoke_time = time.time()
                    self.hello_question_sent = self.cutoff_sent = False
                    self._in_angle_tag = False
                    suspect_echo = self._itx_is_suspect_echo(itx.text)
                    if suspect_echo:
                        self.dbg.log("in_tx_suspect_echo", text=itx.text, state=self._state_snapshot())
                        print(f"{_C_MUTED}[{get_timestamp()}] [echo?] Heard while the assistant was speaking and it looks like her own voice: not used for decisions.{_R}", flush=True)
                    else:
                        now_c = time.time()
                        self._last_caller_text_time = now_c
                        if self._is_wait_request(itx.text):
                            self._last_wait_request_time = now_c
                        caller_goodbye = self._is_farewell(itx.text, fuzzy=True)
                        if caller_goodbye:
                            self._last_caller_farewell_time = now_c

                    # The caller's line goes first, so the state messages it causes (hold, goodbye, priority) come after it
                    entering_hold = self.on_hold
                    dismiss_turn = entering_hold and (suspect_echo or not self._check_wait_return(itx.text))
                    if not dismiss_turn:
                        ts = get_timestamp()
                        prefix = "> " if entering_hold else ""
                        print(f"\n\n{_C_MUTED}{prefix}[{ts}]{_R} {_C_AUDIO}{ICON_USER_STR}{itx.text}{_R}")
                        self.accumulated_transcript += f"\n\n🗣 [{ts}]: {itx.text}"
                        self.last_speaker = None
                        self._register_caller_line(ts, itx.text)
                        self.update_transcription_db()

                        if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                            cloned_audio = list(self.user_turn_audio)
                            self.user_turn_audio.clear()
                            asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts, suspect_echo))
                        else:
                            self.user_turn_audio.clear()

                        self._check_priority_keywords(itx.text, "gemini")

                    if self.farewell_pending and not suspect_echo:
                        if self._is_farewell(itx.text, fuzzy=True):
                            self._commit_farewell_hangup("caller also said goodbye")
                        elif not self._is_farewell_ack(itx.text):
                            self._cancel_pending_farewell(f"the caller did not close the conversation: '{itx.text}'")
                        else:
                            # Only an acknowledgement ('vale', 'no, nada'): the goodbye stands, but the silence time starts again
                            self._caller_spoke_since_intent = True
                            self._intent_text = self._asst_turn_text or self._intent_text
                            self.farewell_drained_since = 0.0
                    self._asst_turn_text = ""

                    if self.waiting_definitive_cut:
                        print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_CONN}[SYSTEM]: Interruption during grace period. Cancelling hangup...{_R}")
                        self.waiting_definitive_cut = False

                    just_activated_hold = False

                    if not self.hanging_up and not self.on_hold and not suspect_echo:
                        user_safe_text = itx.text.lower()
                        for iw in self.words_data.get("ignore_hold_words", []):
                            user_safe_text = user_safe_text.replace(iw.lower(), "")

                        if self._matches_any_phrase(user_safe_text, self._caller_hold_phrases(), fuzzy=True):
                            self.on_hold = True
                            just_activated_hold = True
                            self.current_wait_start = self.last_user_spoke_time = time.time()
                            self.last_speaker = None
                            self.log_system_message(f"Hold activated by caller. Silencing inactivity (Limit {int(self.category_wait_seconds)}s).", "⏳")
                            self.log_decision("hold", gemini="-", text=itx.text, result="activated", detail="caller keyword")

                    if self.on_hold:
                        if not just_activated_hold:
                            user_safe_text = itx.text.lower()
                            for iw in self.words_data.get("ignore_hold_words", []):
                                user_safe_text = user_safe_text.replace(iw.lower(), "")

                            if self._matches_any_phrase(user_safe_text, self._caller_hold_phrases(), fuzzy=True):
                                now = time.time()
                                self.last_user_spoke_time = now
                                if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                    self.last_renewal_printed_time = now
                                    self.log_system_message(
                                        self.words_data.get("hold_renewed_caller", "⏳ [SYSTEM]: Wait time renewed by caller request (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)),
                                        "⏳"
                                    )

                            if dismiss_turn:
                                ts = get_timestamp()
                                self._show_filtered_turn(itx.text, "on hold: possible echo of the assistant" if suspect_echo else "on hold: no return keyword")
                                self._hold_note_dismissed_caller_turn(itx.text)
                                if not suspect_echo:
                                    self._spawn(self._semantic_resolve_resume())
                                self.dbg.log("hold_dismissed_turn", text=itx.text)
                                if self.final_transcription_mode == "realtime" and len(self.user_turn_audio) > 0:
                                    cloned_audio = list(self.user_turn_audio)
                                    self.user_turn_audio.clear()
                                    asyncio.create_task(self.heal_transcription_whisper(cloned_audio, itx.text, ts, suspect_echo))
                                else:
                                    self.user_turn_audio.clear()
                                itx = None
                            elif not self._matches_any_phrase(user_safe_text, self._caller_hold_phrases(), fuzzy=True):
                                self.log_system_message("Return from hold detected. Resuming conversation...", "⏳")
                                self.log_decision("hold", gemini="-", text=itx.text, result="ended", detail="return keyword")
                                self.on_hold = False
                                if self.current_wait_start > 0:
                                    self.accumulated_wait_time += (time.time() - self.current_wait_start)
                                self.current_wait_start = 0.0


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
                                self._pb_in_bytes += len(inline_data.data)
                                self._monitor_write(self.asst_pacat, inline_data.data)
                                self.last_chunk_audio_time = time.time()
                                self.cutoff_sent = False
                        except Exception:
                            pass

                otx = getattr(sc, "output_transcription", None)
                if otx and getattr(otx, "text", None):
                    self.user_turn_audio.clear()
                    self.dbg.log("out_tx", raw=otx.text)
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
                                self.dbg.log("out_tx_duplicate", text=clean_otx)
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

                        if (self.on_hold and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", []))
                                and self._hold_acceptance_allowed(HOLD_RENEW_WINDOW_SECONDS)):
                            now = time.time()
                            self.last_user_spoke_time = now
                            if now - getattr(self, "last_renewal_printed_time", 0) > 1.5:
                                self.last_renewal_printed_time = now
                                self.log_system_message(
                                    self.words_data.get("hold_renewed_assistant", "⏳ [SYSTEM]: Wait time renewed by assistant response (Limit: {limit}s).").format(limit=int(self.category_wait_seconds)),
                                    "⏳"
                                )

                        now_turn = time.time()
                        if now_turn - self._asst_turn_last_time < ASSISTANT_TURN_GAP_SECONDS and self._asst_turn_text:
                            self._asst_turn_text += " " + clean_otx
                        else:
                            self._asst_turn_text = clean_otx
                            self._asst_turn_start_time = now_turn
                        self._asst_turn_last_time = now_turn
                        self._register_hold_exchange()

                        # The farewell is judged on the whole assistant turn (not only the latest chunk): the clause that
                        # holds the farewell word can still grow into an explanation or a denial in later chunks.
                        farewell_now = self._is_farewell(self._asst_turn_text)
                        if (farewell_now and not self.hangup_triggered and not self.farewell_pending and not self.waiting_definitive_cut
                                and not self.hello_question_sent and time.time() - self._farewell_veto_time >= FAREWELL_VETO_SECONDS):
                            self.farewell_pending = True
                            self.farewell_drained_since = 0.0
                            self._closing_vote = None
                            self._caller_spoke_since_intent = False
                            self._intent_text = self._asst_turn_text
                            self._intent_time = time.time()
                            self._spawn(self._semantic_resolve_closing())
                            print(f"\n\n{_C_WARN}[{get_timestamp()}] {ICON_INFO}[HANGUP] Goodbye detected in assistant text. Waiting for the audio to finish and the caller's reply...{_R}")
                        elif self.farewell_pending and not self.hanging_up:
                            if not farewell_now and (not self._hangup_tool_seen or self._caller_spoke_since_intent):
                                self._cancel_pending_farewell("farewell word is part of an explanation or was denied" if not self._hangup_tool_seen
                                                              else "the assistant went on with the conversation after the caller reacted")
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

                        assistant_hold_phrase = (not self.hanging_up and not self.on_hold
                                                 and self._matches_any_phrase(safe_eval_text, self.words_data.get("hold_words", [])))
                        if assistant_hold_phrase and not self._hold_acceptance_allowed():
                            self._note_hold_phrase_without_request()
                            assistant_hold_phrase = False
                        if assistant_hold_phrase:
                            self.on_hold = True
                            self.current_wait_start = self.last_user_spoke_time = time.time()
                            self.last_speaker = None
                            self.log_decision("hold", gemini="assistant accepted a wait", text="the caller asked to wait", result="activated", detail="assistant phrase after a caller request")
                            if self.category_wait_seconds < 60.0:
                                self.log_system_message(f"{self.assistant_name} accepted short hold ({int(self.category_wait_seconds)}s). Sending time limit warning...", "⏳")
                                self._note_self_interrupt()
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
            unanswered_base_tag = self.labels_data.get("general", "GENERAL")
            unanswered_trans = f"❌ [{get_timestamp()}]: [SYSTEM]: {UNANSWERED_CALL_MARKER}"
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
            conn.execute(
                "UPDATE calls SET duration=0, tag=?, client_name=?, base_tag=?, base_client_name='', transcript=?, audio_path='', client_audio_path='', summary='' WHERE id=?",
                (final_tag, client_n, unanswered_base_tag, unanswered_trans, self.call_id)
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
                final_trans = normalize_end_of_call_labels(await self.correct_transcript_with_whisper(raw_whisper),
                                                           f"Whisper.cpp {self.whisper_full_model} (end of call)")
        elif self.final_transcription_mode == "gemini_final" and os.path.exists(self.client_recording_path):
            if "gemma" in self.model_text.lower():
                print(f"{_C_WARN}[Post-Processing] Gemma models do not support native audio parsing. Falling back to gemini-3-flash-preview...{_R}")
                final_trans = normalize_end_of_call_labels(
                    await self.correct_transcript_with_gemini_audio(self.client_recording_path, model_override="gemini-3-flash-preview"),
                    "gemini-3-flash-preview (end of call)")
            else:
                print(f"{_C_SERVER}[{get_timestamp()}] {ICON_SERVER}[Post-Processing] Running {self.model_text} Audio alignment...{_R}")
                final_trans = normalize_end_of_call_labels(await self.correct_transcript_with_gemini_audio(self.client_recording_path),
                                                           f"{self.model_text} (end of call)")

        contact_match = match_contact_rule(self.caller_number, self.spam_data)
        custom_contact_tag = (contact_match or {}).get("tag", "").strip()

        # Label chosen by the analysis of the call. It is saved as base_tag: the label the call goes back to when a
        # contact rule with a custom tag is removed or its tag is cleared in the Web GUI.
        if caller_type == "spam" or max_spam_score >= SPAM_SCORE_THRESHOLD or self.last_call_json.get("private_data_requested", False):
            analysis_tag = self.labels_data.get("spam", "SPAM")
        elif self.priority_call:
            analysis_tag = self.labels_data.get("priority", "PRIORITY")
        elif caller_type == "friend_family":
            analysis_tag = self.labels_data.get("personal", "PERSONAL")
        elif caller_type == "work":
            analysis_tag = self.labels_data.get("work", "WORK")
        elif caller_type == "commercial":
            analysis_tag = self.labels_data.get("spam", "SPAM")
        else:
            analysis_tag = self.labels_data.get("general", "GENERAL")
        final_tag = custom_contact_tag or analysis_tag

        client_n = self.last_call_json.get("caller_name", "")
        comp_n = self.last_call_json.get("company", "")
        if client_n.lower() in ["unknown", "null", "none"]:
            client_n = ""
        if comp_n.lower() in ["unknown", "null", "none"]:
            comp_n = ""
        analysis_client_name = client_n   # Name heard by the AI; the contact note only fills in when there is none
        if not client_n and (contact_match or {}).get("note"):
            client_n = contact_match["note"]

        duration_sec = max(0, int(time.time() - self.call_start_time))
        client_rec_val = self.client_recording_path if os.path.exists(self.client_recording_path) else ""
        rec_val = self.recording_path if os.path.exists(self.recording_path) else ""

        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
        conn.execute(
            "UPDATE calls SET duration=?, tag=?, client_name=?, base_tag=?, base_client_name=?, company=?, transcript=?, spam_score=?, audio_path=?, client_audio_path=?, summary=? WHERE id=?",
            (duration_sec, final_tag, client_n, analysis_tag, analysis_client_name, comp_n, final_trans, max_spam_score, rec_val, client_rec_val, call_summary, self.call_id)
        )
        conn.commit()
        conn.close()
        print(f"{_C_SERVER}[{get_timestamp()}] {ICON_OK}[Post-Processing] Complete. Tagged as: {final_tag}{_R}")

    def build_category_rules(self) -> str:
        """Joins the instructions written in the categories (always added, like the rest of the general instructions).
        {boss_name} and {assistant_name} are replaced one by one, so any other braces typed by the user stay untouched."""
        header_template = self.assistant_data.get("category_rule_header", "RULES FOR THE CATEGORY {category} (MANDATORY):")
        blocks = []
        for rule in self._memory_rules:
            if not isinstance(rule, dict):
                continue
            rule_text = str(rule.get("prompt", "") or "").strip()
            if not rule_text:
                continue
            rule_text = rule_text.replace("{boss_name}", self.boss_name).replace("{assistant_name}", self.assistant_name)
            header = header_template.replace("{category}", str(rule.get("category", "")).strip())
            blocks.append(f"{header}\n{rule_text}")
        return "\n\n".join(blocks)

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
            self.create_call_record_db(initial_tag=blocked_tag, initial_transcript=blocked_msg, audio_path_val="",
                                       base_tag=self.labels_data.get("general", "GENERAL"), base_client_name="")
            if contact_match.get("note"):
                conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
                conn.execute("UPDATE calls SET client_name=?, summary=? WHERE id=?", (contact_match["note"], f"{BLOCKED_SUMMARY_PREFIX} {contact_match['pattern']}", self.call_id))
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
        category_rules = self.build_category_rules()
        business_details = self.business_description
        if self.expected_calls.strip():
            expected_calls_header = self.assistant_data.get("expected_calls_header", "EXPECTED TYPES OF CALLS:")
            business_details = f"{business_details}\n\n{expected_calls_header}\n{self.expected_calls.strip()}".strip()
        category_rules_placed = "{category_rules}" in raw_instruction
        try:
            instruction = raw_instruction.format(
                assistant_name=self.assistant_name,
                role_assistant=pick_role_text(self.assistant_data.get("role_mappings", {}), is_female_gender(self.assistant_gender, self.gui_data), "Secretary"),
                owner_desc=pick_owner_text(self.assistant_data.get("owner_type_mappings", {}), self.owner_type, "Private"),
                boss_name=self.boss_name,
                business_details=business_details,
                category_rules=category_rules
            )
        except (KeyError, ValueError):
            instruction = raw_instruction
            category_rules_placed = False
        if category_rules and not category_rules_placed:
            # Language files that do not have the {category_rules} marker still get the category instructions
            instruction += f"\n\n{category_rules}"

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
        if not self.send_speech_language_code:
            speech_lang_code = ""
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
            input_audio_transcription=types.AudioTranscriptionConfig() if self.explicit_transcription_config else None,
            output_audio_transcription=types.AudioTranscriptionConfig() if self.explicit_transcription_config else None,
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=start_sens_enum,
                    end_of_speech_sensitivity=end_sens_enum,
                    prefix_padding_ms=self.vad_prefix_padding_ms,
                    silence_duration_ms=self.vad_silence_duration_ms,
                )
            )
        )

        self.dbg.log(
            "live_config", app_version=APP_VERSION, model=MODEL_LIVE, voice=voice_name, language=self.current_lang,
            speech_language_code_sent=speech_lang_code or None, explicit_transcription=self.explicit_transcription_config,
            vad={"start": self.vad_start_sens, "end": self.vad_end_sens, "prefix_ms": self.vad_prefix_padding_ms, "silence_ms": self.vad_silence_duration_ms},
            caller_gain=self.caller_gain, noise_gate_base=self.noise_gate_base, gate_hangover_chunks=self.mic_gate_hangover_chunks,
            echo_suppression=self.software_echo_suppression, protect_greeting=self.protect_initial_greeting,
            transcription_mode=self.final_transcription_mode, whisper_signals=self.whisper_signals, whisper_bin=WHISPER_BIN or None,
            whisper_model=self.whisper_full_model, whisper_threads=self.whisper_threads, flush_on_interrupt=self.flush_on_interrupt,
            audioop=audioop is not None, instruction_chars=len(instruction),
            pw_record_target=self.pw_record_target, pw_playback_target=self.pw_playback_target,
            monitor_mode=getattr(self, "monitor_mode", None), python=sys.version.split()[0],
        )
        is_whitelisted = bool(contact_match and contact_match.get("type") == "whitelist")
        spam_task = asyncio.create_task(self.check_network_spam(is_whitelisted=is_whitelisted))
        asyncio.create_task(self.monitor_routing_manager())

        try:
            async with self.client_live.aio.live.connect(model=MODEL_LIVE, config=config) as session:
                self.answer_call()
                self.answered_call = True
                self.call_start_time = time.time()
                self._spawn(self._probe_bluetooth_audio())

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
                                    self._note_self_interrupt()
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

                if self.final_transcription_mode == "online_realtime":
                    self.online = OnlineTranscriber(self)
                    self.online.start()
                    self.dbg.log("online_start", language_codes=self.online.language_codes, vocabulary=self.online.vocabulary)

                await asyncio.gather(self.send_mic_audio(session), self.receive_audio_and_tools(session), monitor_spam())

        except Exception as e:
            print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Session] Unexpected error: {e}{_R}")
            if not getattr(self, "answered_call", False):
                print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[AI Engine] Gemini Live is unavailable. Delegating call to native phone handler.{_R}")
        finally:
            self.running = False
            self._flush_pending_alternatives(force=True)
            self.flush_transcription_db()
            self._playback_summary()
            if self._whisper_worker_task is not None:
                self._whisper_worker_task.cancel()
            if self.online is not None:
                self.online.stop()
                usage = self.online.usage()
                self.dbg.log("online_usage", **usage)
                usage["agreed_with_gemini"] = self._alt_agree
                usage["compared"] = self._alt_total
                print(f"{_C_MUTED}[{get_timestamp()}] [Online] {usage['audio_sent_s']} s of audio sent in {usage['sessions']} session(s), "
                      f"{usage['finals']} texts ({self._alt_agree} of {self._alt_total} compared were identical to Gemini's).{_R}", flush=True)
            self.dbg.log("call_end", reason=getattr(self, "hangup_reason", ""), source=getattr(self, "hangup_source", ""), state=self._state_snapshot())
            self.dbg.close()
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
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
NOTIFY_MAX_WAIT_SECONDS = 30        # upper bound for the optional long-poll ("wait") parameter
NOTIFY_WAIT_STEP_SECONDS = 1.0      # how often the database is re-checked while waiting
NOTIFY_SPAM_THRESHOLD = SPAM_SCORE_THRESHOLD   # same threshold used to tag a call as SPAM
_NOTIFY_SERVER: Optional[ThreadingHTTPServer] = None


def build_notify_payload(since_message: Optional[int], since_call: Optional[int]) -> Dict[str, Any]:
    """Returns the newest caller messages and finished calls after the given ids.
    If a cursor is missing (first poll) no items are returned, only the current cursors,
    so enabling notifications never floods the phone with old items."""
    conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
    """Serves GET /api/events?since_message=<id>&since_call=<id>[&wait=<seconds>] as JSON.

    Without "wait" the answer is immediate. With "wait" (only honoured when both cursors are
    given) the request is held open until something new exists or the time runs out, which
    gives near-instant alerts to a client that keeps one request open at all times.
    """

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

        since_message = _int_param("since_message")
        since_call = _int_param("since_call")
        has_cursors = since_message is not None and since_call is not None
        wait_seconds = (_int_param("wait") or 0) if has_cursors else 0
        wait_seconds = max(0, min(wait_seconds, NOTIFY_MAX_WAIT_SECONDS))
        deadline = time.monotonic() + wait_seconds

        try:
            while True:
                payload = build_notify_payload(since_message, since_call)
                if payload["messages"] or payload["calls"] or time.monotonic() >= deadline:
                    break
                time.sleep(NOTIFY_WAIT_STEP_SECONDS)
        except Exception:
            self.send_error(500)
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The client went away while waiting (normal for phones changing networks).
            return

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
        self.state: str = "off"        # What this daemon knows about its own Tor: off, starting, running or error
        self.onion: str = ""

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
        self.state, self.onion = "error", ""
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
        self.state, self.onion = "running", onion
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
        self.state, self.onion = "starting", ""
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
        self.state, self.onion = "off", ""
        _set_runtime_setting("tor_status", "off")
        _set_runtime_setting("tor_error", "")
        _set_runtime_setting("tor_onion", "")
        _set_runtime_setting("tor_progress", "0")

    def _restore_published_state(self) -> None:
        """Self-repair: if the status stored in the database no longer matches this running Tor (something else overwrote it),
        the real state is published again. Without this the Web GUI could show "Starting (0%)" for as long as Tor stays up."""
        if self.state not in ("starting", "running"):
            return
        if get_config("tor_status", "off") == self.state and (self.state != "running" or get_config("tor_onion", "") == self.onion):
            return
        print(f"{_C_WARN}[{get_timestamp()}] {ICON_WARN}[Tor] The published status did not match the running Tor. Publishing it again.{_R}")
        _set_runtime_setting("tor_error", "")
        _set_runtime_setting("tor_onion", self.onion)
        _set_runtime_setting("tor_progress", 100 if self.state == "running" else self.progress)
        _set_runtime_setting("tor_status", self.state)

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
            elif self.proc is not None:
                self._restore_published_state()
        elif self.proc is not None or get_config("tor_status", "off") != "off":
            self.stop()


ONION = OnionService()


async def daemon_heartbeat_loop(main_loop: asyncio.AbstractEventLoop) -> None:
    """Periodically updates the daemon heartbeat in SQLite and checks for pause/stop signals from the GUI."""
    last_logged_state = "running"
    heartbeat_failing = False
    while True:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
        except Exception as heartbeat_error:
            if not heartbeat_failing:
                heartbeat_failing = True
                print(f"{_C_ERR}[{get_timestamp()}] {ICON_ERR}[Heartbeat] Could not update the daemon heartbeat: {heartbeat_error}{_R}")
        else:
            heartbeat_failing = False
        await asyncio.sleep(3.0)


DAEMON_LOCK_WAIT_SECONDS = 10.0     # A daemon that is being replaced (service restart) may still hold the lock for a moment
_DAEMON_LOCK_FILE = None


def acquire_daemon_lock() -> bool:
    """Allows only one daemon at a time. The lock is held on this script file (no extra file is needed) and the system
    releases it by itself when the process ends, even after a crash."""
    global _DAEMON_LOCK_FILE
    lock_file = open(os.path.abspath(__file__), "rb")
    deadline = time.time() + DAEMON_LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _DAEMON_LOCK_FILE = lock_file   # It must stay open for as long as the daemon runs
            return True
        except OSError:
            if time.time() >= deadline:
                lock_file.close()
                return False
            time.sleep(0.5)


async def run_cli_spam_test(test_number: str) -> None:
    """CLI utility to test a phone number against all configured SPAM providers and the LLM."""
    ensure_database_exists()
    dummy = PhoneAssistant(dbus_path="/org/ofono/test", caller_number=test_number)
    print(f"{_C_SERVER}Testing number {test_number} (Normalized: {dummy.national_number}) against SPAM providers...{_R}")
    conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
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
    if len(sys.argv) >= 3 and sys.argv[1] == "--show-debug":
        print_debug_timeline(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        sys.exit(0)
    if "--debug" in sys.argv:
        os.environ["SWITCHBOARD_DEBUG"] = "1"

    if not API_KEY:
        print(f"{_C_ERR}{ICON_ERR}Error: GEMINI_API_KEY environment variable not set.{_R}")
        sys.exit(1)

    if len(sys.argv) >= 3 and sys.argv[1] == "--test-spam":
        asyncio.run(run_cli_spam_test(sys.argv[2]))
        sys.exit(0)

    if not acquire_daemon_lock():
        print(f"{_C_ERR}{ICON_ERR}Another instance of the switchboard daemon is already running. Stop it first (or use ./my_gui.sh --logs to watch it).{_R}")
        sys.exit(1)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    ensure_database_exists(reset_runtime_state=True)
    _truthy = ("1", "true", "yes", "on")
    if os.environ.get("SWITCHBOARD_SKIP_SYSTEM_CONFIG", "").strip().lower() in _truthy:
        print(f"{_C_WARN}{ICON_WARN}SWITCHBOARD_SKIP_SYSTEM_CONFIG: WirePlumber / null-sink / oFono configuration left untouched.{_R}")
    else:
        ensure_system_dependencies()

    initialize_ofono_modems()
    initialize_bluez_devices()

    if os.environ.get("SWITCHBOARD_SKIP_AUDIO_RESTART", "").strip().lower() in _truthy:
        print(f"{_C_WARN}{ICON_WARN}SWITCHBOARD_SKIP_AUDIO_RESTART: PipeWire / WirePlumber were not restarted.{_R}")
    else:
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
