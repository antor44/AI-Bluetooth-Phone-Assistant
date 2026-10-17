#!/usr/bin/env python3
"""
AI Switchboard Web Interface - Streamlit UI for managing configurations, inbox messages,
contacts/wildcards, audio/VAD parameters, Whisper models, daemon controls, and call logs.

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

import streamlit as st
import sqlite3
import os
import json
import datetime
import time
import re
import shutil
import subprocess
import urllib.request
import urllib.parse
from typing import List, Tuple, Dict, Any
from google import genai
from google.genai import types

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "switchboard.db")
LANG_DIR = os.path.join(BASE_DIR, "languages")
MODELS_DIR = os.path.join(BASE_DIR, "models")
WHISPER_CPP_DIR = os.path.expanduser("~/whisper.cpp")

WHISPER_BASE_MODELS = [
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large-v3-turbo"
]
WHISPER_QUANT_SUFFIXES = ["-q4_0", "-q4_1", "-q5_0", "-q5_1", "-q8_0"]
SUPPORTED_TERMINALS = [
    "xfce4-terminal", "gnome-terminal", "konsole",
    "mate-terminal", "lxterm", "mlterm", "xterm", "background"
]


def find_whisper_bin() -> str:
    """Dynamically searches for the Whisper CLI executable across common build paths."""
    paths_to_check = [
        shutil.which("whisper-cli"),
        shutil.which("main"),
        os.path.join(WHISPER_CPP_DIR, "build", "bin", "whisper-cli"),
        os.path.join(WHISPER_CPP_DIR, "build", "bin", "main"),
        os.path.join(BASE_DIR, "build", "bin", "whisper-cli"),
        os.path.join(BASE_DIR, "build", "bin", "main"),
        os.path.join(BASE_DIR, "whisper-cli")
    ]
    for p in paths_to_check:
        if p and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return ""


def find_quantize_bin() -> str:
    """Dynamically searches for the whisper-quantize executable across common paths."""
    paths_to_check = [
        shutil.which("whisper-quantize"),
        shutil.which("quantize"),
        os.path.join(WHISPER_CPP_DIR, "build", "bin", "whisper-quantize"),
        os.path.join(WHISPER_CPP_DIR, "build", "bin", "quantize"),
        os.path.join(BASE_DIR, "build", "bin", "whisper-quantize"),
        os.path.join(BASE_DIR, "build", "bin", "quantize")
    ]
    for p in paths_to_check:
        if p and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return ""


def normalize_phone_pattern(raw_input: str) -> str:
    """Normalizes a phone number or wildcard pattern while preserving * and ? characters."""
    raw = raw_input.strip()
    cleaned = re.sub(r"[^\d\*\?\+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not any(ch in cleaned for ch in ("*", "?")) and cleaned.startswith("34") and len(cleaned) == 11:
        cleaned = cleaned[2:]
    return cleaned or raw


def format_spam_test_url(url_template: str, raw_number: str) -> str:
    """Formats a SPAM provider URL template using {number}, {national}, and {e164} placeholders."""
    digits = re.sub(r"\D", "", raw_number)
    if digits.startswith("00"):
        digits = digits[2:]
    national = digits[2:] if (digits.startswith("34") and len(digits) == 11) else (digits[-9:] if len(digits) > 9 else digits)
    e164 = f"+{digits}" if not digits.startswith("34") and len(digits) > 9 else (f"+34{national}" if len(national) == 9 else f"+{digits}")

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


def fetch_spam_page_sync(url: str) -> Tuple[int, str]:
    """Fetches a SPAM lookup URL using curl_cffi (Chrome TLS), system curl with browser headers, or urllib."""
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
            resp = curl_requests.get(url, headers=headers, impersonate="chrome", timeout=6)
            if resp.status_code == 200 and resp.text:
                return resp.status_code, resp.text
        except Exception:
            pass

    if shutil.which("curl"):
        try:
            cmd = [
                "curl", "-sL", "--max-time", "6",
                "-w", "\n__HTTP_STATUS__:%{http_code}",
                "-A", headers["User-Agent"],
                "-H", f"Accept: {headers['Accept']}",
                "-H", f"Accept-Language: {headers['Accept-Language']}",
                "-H", f"Referer: {headers['Referer']}",
                url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=7)
            if "__HTTP_STATUS__:" in res.stdout:
                body, status_part = res.stdout.rsplit("__HTTP_STATUS__:", 1)
                status_code = int(status_part.strip() or "0")
                if status_code > 0:
                    return status_code, body
        except Exception:
            pass

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=6) as resp:
        return resp.status, resp.read().decode("utf-8", errors="ignore")


def evaluate_spam_text_with_ai(clean_text: str, raw_number: str, model_name: str, lang_code: str) -> Dict[str, Any]:
    """Evaluates extracted lookup text with Gemini/Gemma and returns {is_spam, risk_score, reason}."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"is_spam": False, "risk_score": 0, "reason": "GEMINI_API_KEY environment variable not set."}

    client = genai.Client(api_key=api_key)
    lang_note = "Spanish" if lang_code.startswith("es") else "English"
    schema = {
        "type": "object",
        "properties": {"is_spam": {"type": "boolean"}, "risk_score": {"type": "integer"}, "reason": {"type": "string"}},
        "required": ["is_spam", "risk_score", "reason"]
    }

    is_gemma = "gemma" in model_name.lower()
    prompt = (
        f"Analyze this text extracted from a phone lookup website for number {raw_number}.\n"
        f"1. Ignore website menus or boilerplate.\n"
        f"2. If there are no negative reports or complaints, set is_spam=false and risk_score=0.\n"
        f"3. If ratings or user comments indicate scam, spam, telemarketing, or harassment, set is_spam=true and risk_score between 75 and 100.\n"
        f"4. Write the 'reason' field briefly in {lang_note}.\n\n"
        f"TEXT:\n{clean_text[:15000]}\n\nJSON:"
    )

    try:
        if is_gemma:
            config = types.GenerateContentConfig(temperature=0.0)
        else:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        response = client.models.generate_content(model=model_name, contents=prompt, config=config)
        raw_out = getattr(response, "text", "") or "{}"
        m = re.search(r"\{.*\}", raw_out, re.DOTALL)
        return json.loads(m.group(0)) if m else {"is_spam": False, "risk_score": 0, "reason": "Could not parse AI response."}
    except Exception as e:
        return {"is_spam": False, "risk_score": 0, "reason": f"AI evaluation error: {e}"}


def parse_model_name(model_name: str) -> Tuple[str, str]:
    """Splits a full Whisper model name into its base model and quantization suffix."""
    suffix = ""
    base_model = model_name
    if model_name in WHISPER_BASE_MODELS:
        base_model = model_name
    else:
        for model in WHISPER_BASE_MODELS:
            for sfx in WHISPER_QUANT_SUFFIXES:
                if f"{model}{sfx}" == model_name:
                    base_model = model
                    suffix = sfx
                    break
            if suffix:
                break
    return base_model, suffix


def find_make_model_processes(base_model: str) -> List[str]:
    """Finds active process IDs running 'make <base_model>' or downloading the model."""
    try:
        result = subprocess.run(["ps", "x"], capture_output=True, text=True)
        process_ids = []
        for line in result.stdout.split("\n"):
            columns = line.split()
            if len(columns) > 4:
                full_command = " ".join(columns[4:])
                if f"make {base_model}" in full_command or f"download-ggml-model.sh {base_model}" in full_command:
                    process_ids.append(columns[0])
        return process_ids
    except Exception:
        return []


def wait_for_process_completion(pids: List[str], process_name: str) -> None:
    """Waits until all specified process IDs finish executing."""
    for pid in pids:
        while True:
            time.sleep(1)
            try:
                check_pid = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command"],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
                if process_name not in check_pid:
                    break
            except subprocess.TimeoutExpired:
                break


def install_whisper_model(model_name: str, terminal: str) -> Tuple[bool, str]:
    """Downloads and optionally quantizes a Whisper model using the selected terminal or background shell."""
    base_model, suffix = parse_model_name(model_name)
    quantize_executable = find_quantize_bin()

    if suffix and not quantize_executable:
        return False, "Quantize executable (whisper-quantize) does not exist."

    os.makedirs(MODELS_DIR, exist_ok=True)
    work_dir = WHISPER_CPP_DIR if os.path.isdir(WHISPER_CPP_DIR) else BASE_DIR
    os.makedirs(os.path.join(work_dir, "models"), exist_ok=True)

    link_cmds = (
        f"ln -sf \"{work_dir}/models/ggml-{base_model}.bin\" \"{MODELS_DIR}/ggml-{base_model}.bin\" 2>/dev/null || true; "
        f"ln -sf \"{work_dir}/models/ggml-{model_name}.bin\" \"{MODELS_DIR}/ggml-{model_name}.bin\" 2>/dev/null || true"
    )

    if suffix:
        core_cmd = (
            f"cd \"{work_dir}\" && "
            f"(make {base_model} || bash ./models/download-ggml-model.sh {base_model}) && "
            f"\"{quantize_executable}\" \"./models/ggml-{base_model}.bin\" \"./models/ggml-{model_name}.bin\" {suffix.lstrip('-')} && "
            f"{link_cmds}"
        )
    else:
        core_cmd = (
            f"cd \"{work_dir}\" && "
            f"(make {model_name} || bash ./models/download-ggml-model.sh {model_name}) && "
            f"{link_cmds}"
        )

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    try:
        if has_display and terminal != "background":
            if terminal == "gnome-terminal" and shutil.which("gnome-terminal") and subprocess.run(["gnome-terminal", "--version"], capture_output=True).returncode == 0:
                subprocess.Popen(["gnome-terminal", "--tab", "--", "/bin/bash", "-c", f"{core_cmd}; exit"])
            elif terminal == "konsole" and shutil.which("konsole") and subprocess.run(["konsole", "--version"], capture_output=True).returncode == 0:
                subprocess.Popen(["konsole", "-e", f"bash -c '{core_cmd}'"])
            elif terminal == "lxterm" and shutil.which("lxterm") and subprocess.run(["lxterm", "-version"], capture_output=True).returncode == 0:
                subprocess.Popen(["lxterm", "-e", "bash", "-c", core_cmd])
            elif terminal == "mate-terminal" and shutil.which("mate-terminal") and subprocess.run(["mate-terminal", "--version"], capture_output=True).returncode == 0:
                subprocess.Popen(["mate-terminal", "-e", f"bash -c '{core_cmd}'"])
            elif terminal == "mlterm" and shutil.which("mlterm"):
                result = subprocess.run(["mlterm", "--version"], capture_output=True, text=True)
                if "mlterm" in result.stdout:
                    subprocess.Popen(["bash", "-c", f"mlterm -e bash -c '{core_cmd}'"])
            elif terminal == "xfce4-terminal" and shutil.which("xfce4-terminal") and subprocess.run(["xfce4-terminal", "--version"], capture_output=True).returncode == 0:
                subprocess.Popen(["xfce4-terminal", "-x", "bash", "-c", core_cmd])
            elif terminal == "xterm" and shutil.which("xterm") and subprocess.run(["xterm", "-version"], capture_output=True).returncode == 0:
                subprocess.Popen(["xterm", "-e", "bash", "-c", core_cmd])
            else:
                subprocess.Popen(["/bin/bash", "-c", core_cmd])
        else:
            subprocess.Popen(["/bin/bash", "-c", core_cmd])

        time.sleep(3)
        process_ids = find_make_model_processes(base_model)
        if process_ids:
            wait_for_process_completion(process_ids, base_model)

        target_file = os.path.join(MODELS_DIR, f"ggml-{model_name}.bin")
        alt_file = os.path.join(work_dir, "models", f"ggml-{model_name}.bin")
        if os.path.exists(alt_file) and not os.path.exists(target_file):
            try:
                os.symlink(alt_file, target_file)
            except Exception:
                pass

        return True, f"Model {model_name} installation completed."
    except OSError as e:
        return False, f"Error executing command: {e}"


def init_db() -> None:
    """Initializes the database schema, runs safe column migrations, and defines global settings."""
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
    c.execute("INSERT OR IGNORE INTO settings VALUES ('language', 'es-ES')")
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

    conn.commit()
    conn.close()


def get_config(key: str, default_value: str) -> str:
    """Retrieves standard or language-localized configuration elements from the database."""
    conn = sqlite3.connect(DB_PATH)
    res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
    current_lang = res_lang[0] if res_lang else "es-ES"

    localized_keys = [
        "boss_name", "assistant_name", "assistant_gender", "owner_type",
        "priority_keywords", "memory_rules", "business_description",
        "expected_calls", "initial_greeting", "extra_prompt", "text_model"
    ]
    if key in localized_keys:
        lang_key = f"{current_lang}_{key}"
        res = conn.execute("SELECT value FROM settings WHERE key=?", (lang_key,)).fetchone()
        if res is not None:
            conn.close()
            return res[0]

    res_global = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return res_global[0] if res_global is not None else default_value


def set_config(key: str, value: Any) -> None:
    """Persists standard or localized settings dynamically to the database."""
    conn = sqlite3.connect(DB_PATH)
    res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
    current_lang = res_lang[0] if res_lang else "es-ES"

    localized_keys = [
        "boss_name", "assistant_name", "assistant_gender", "owner_type",
        "priority_keywords", "memory_rules", "business_description",
        "expected_calls", "initial_greeting", "extra_prompt", "text_model"
    ]
    db_key = f"{current_lang}_{key}" if key in localized_keys else key

    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_key, str(value)))
    conn.commit()
    conn.close()


def import_legacy_messages_from_transcripts() -> int:
    """Scans existing call transcripts for saved message blocks and imports them into the messages table."""
    conn = sqlite3.connect(DB_PATH)
    calls = conn.execute("SELECT id, number, date, transcript FROM calls").fetchall()
    existing = conn.execute("SELECT call_id, time, message_text FROM messages").fetchall()
    existing_set = {(r[0], r[1], r[2]) for r in existing}

    imported_count = 0
    pattern = re.compile(
        r"📝\s*\[(\d{2}:\d{2}:\d{2})\]:\s*\[SYSTEM\]:\s*\*\*\*\s*(?:Message from|Recado de)\s+([^:]+):\s*(.*?)\s*\*\*\*",
        re.IGNORECASE
    )

    for call_id, number, call_date_str, transcript in calls:
        if not transcript:
            continue
        date_only = (call_date_str or "").split(" ")[0] or datetime.datetime.now().strftime("%Y-%m-%d")
        for match in pattern.finditer(transcript):
            msg_time = match.group(1).strip()
            caller_name = match.group(2).strip()
            msg_text = match.group(3).strip()
            if (call_id, msg_time, msg_text) not in existing_set:
                conn.execute(
                    "INSERT INTO messages (call_id, number, date, time, caller_name, message_text, is_read) VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (call_id, number, date_only, msg_time, caller_name, msg_text)
                )
                existing_set.add((call_id, msg_time, msg_text))
                imported_count += 1

    conn.commit()
    conn.close()
    return imported_count


def get_available_languages() -> List[str]:
    if not os.path.exists(LANG_DIR):
        return ["es-ES"]
    return sorted([d for d in os.listdir(LANG_DIR) if os.path.isdir(os.path.join(LANG_DIR, d))])


def load_language_data(lang_code: str, file_name: str = "gui.json") -> Dict[str, Any]:
    path = os.path.join(LANG_DIR, lang_code, file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def apply_language_defaults(lang_code: str) -> None:
    gui_data = load_language_data(lang_code, "gui.json")
    defaults = gui_data.get("defaults", {})
    conn = sqlite3.connect(DB_PATH)
    if defaults:
        for key, val in defaults.items():
            db_key = f"{lang_code}_{key}"
            str_val = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_key, str_val))
    for g_key, g_val in [
        ("wait_seconds", "5"),
        ("caller_gain", "1.5"),
        ("noise_gate_base", "50"),
        ("vad_start_sensitivity", "LOW"),
        ("vad_end_sensitivity", "HIGH"),
        ("vad_prefix_padding_ms", "500"),
        ("vad_silence_duration_ms", "500"),
        ("protect_initial_greeting", "true")
    ]:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (g_key, g_val))
    conn.commit()
    conn.close()


init_db()

available_langs = get_available_languages()
current_lang = get_config("language", "es-ES")
if current_lang not in available_langs and available_langs:
    current_lang = available_langs[0]

trans = load_language_data(current_lang, "gui.json")

if not get_config("assistant_name", ""):
    apply_language_defaults(current_lang)

if not get_config("initial_greeting", ""):
    set_config("initial_greeting", trans.get("default_legal_warning", ""))

current_assistant_name = get_config("assistant_name", "Assistant")

st.set_page_config(
    page_title=f"{trans.get('gui_title', 'AI Switchboard')} - {current_assistant_name}",
    page_icon="📞",
    layout="wide"
)
st.title(f"{trans.get('gui_header', 'AI Switchboard Panel')} ({current_assistant_name}) — v2.0")

st.markdown("""
<style>
    div[data-testid="stExpander"] { margin-bottom: 10px; }
    .cleanup-container { 
        border: 1px solid #444; 
        border-radius: 8px; 
        padding: 15px; 
        margin-bottom: 20px; 
        background-color: rgba(255, 255, 255, 0.05); 
    }
</style>
""", unsafe_allow_html=True)

_live_refresh_html = """
<script>
const runLiveRefresh = () => {
    setTimeout(() => {
        window.parent.document.querySelector('section.main').click();
        runLiveRefresh();
    }, 3000);
};
runLiveRefresh();
</script>
"""

if hasattr(st, "iframe"):
    st.iframe(_live_refresh_html, height=1)
else:
    st.components.v1.html(_live_refresh_html, height=0)

pending_lang = st.session_state.get("pending_lang", None)
target_trans = load_language_data(pending_lang, "gui.json") if pending_lang else trans


@st.dialog(target_trans.get("modal_confirm_lang_title", "Language Change").format(lang=st.session_state.get("pending_lang", "")))
def confirm_language_dialog() -> None:
    st.markdown(target_trans.get("modal_confirm_lang_body", ""))
    c_saved, c_defaults, c_keep, c_cancel = st.columns(4)
    with c_saved:
        if st.button(target_trans.get("modal_btn_saved", "📂 Load Saved"), key="modal_saved_btn"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('language', ?)", (st.session_state.pending_lang,))
            conn.commit()
            conn.close()
            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    with c_defaults:
        if st.button(target_trans.get("modal_btn_defaults", "🔄 Load Defaults"), key="modal_defaults_btn"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('language', ?)", (st.session_state.pending_lang,))
            conn.commit()
            conn.close()
            apply_language_defaults(st.session_state.pending_lang)
            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    with c_keep:
        if st.button(target_trans.get("modal_btn_keep", "📌 Keep Current"), key="modal_keep_btn"):
            old_lang = get_config("language", "es-ES")
            target_lang = st.session_state.pending_lang
            localized_keys = [
                "boss_name", "assistant_name", "assistant_gender", "owner_type",
                "priority_keywords", "memory_rules", "business_description",
                "expected_calls", "initial_greeting", "extra_prompt", "text_model"
            ]

            conn = sqlite3.connect(DB_PATH)
            for key in localized_keys:
                old_key = f"{old_lang}_{key}"
                res = conn.execute("SELECT value FROM settings WHERE key=?", (old_key,)).fetchone()
                if res is None:
                    res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                val = res[0] if res else ""
                target_key = f"{target_lang}_{key}"
                conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (target_key, val))
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('language', ?)", (target_lang,))
            conn.commit()
            conn.close()

            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    with c_cancel:
        if st.button(target_trans.get("modal_btn_cancel", "❌ Cancel"), key="modal_cancel_btn"):
            st.session_state.pending_lang = None
            st.rerun()


col1, col2, col3 = st.columns([1.45, 1.15, 1.25])

# =============================================================================
# COLUMN 1: CALL LOG & RECORDINGS
# =============================================================================
with col1:
    st.subheader(trans.get("call_log_title", "📝 Call Log & Recordings"))
    show_system_msg = st.checkbox(
        trans.get("show_system_msg_label", "Show system messages"),
        value=True,
        key="toggle_sys_msg"
    )

    conn = sqlite3.connect(DB_PATH)
    calls = conn.execute(
        "SELECT id, number, date, spam_score, transcript, audio_path, tag, client_name, company, summary "
        "FROM calls ORDER BY id DESC"
    ).fetchall()
    conn.close()

    if calls:
        for call in calls:
            id_call, number, date, spam_score, transcript, audio_path, tag, client_name, company, summary = call

            in_progress_str = trans.get("ui_in_progress", "IN PROGRESS")
            if tag and tag.strip() == in_progress_str:
                prefix = in_progress_str
            else:
                prefix = "📞"

            caller_display = ""
            if client_name and company:
                caller_display = f" — {client_name} ({company})"
            elif client_name:
                caller_display = f" — {client_name}"
            elif company:
                caller_display = f" — {company}"

            tag_display = tag if tag and tag != in_progress_str else trans.get("ui_general_call", "GENERAL CALL")

            with st.expander(f"{prefix} {number}{caller_display} — {date} | {tag_display} (Risk: {spam_score}/100)"):
                if summary and summary.strip():
                    st.info(f"**📋 {trans.get('ui_call_summary', 'AI Summary:')}** {summary}")

                st.write(f"**{trans.get('ui_transcript', 'Transcript:')}**")

                blocks_raw = [b.strip() for b in (transcript or "").split("\n\n") if b.strip()]
                edit_key = f"edit_phrase_{id_call}"
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = None

                for idx_b, block in enumerate(blocks_raw):
                    if not show_system_msg:
                        if any(marker in block for marker in ["[SYSTEM]", "[Active Hold]", "❌", "⏳", "⏸"]):
                            continue

                    is_user = block.startswith("🗣")
                    is_assistant = block.startswith("📞")

                    m_ts = re.match(r"^[🗣📞]\s*\[(\d{2}:\d{2}:\d{2})\]:\s*(.*)", block, re.DOTALL)
                    if m_ts:
                        ts_str = f"[{m_ts.group(1)}]"
                        pure_text = m_ts.group(2).strip()
                    else:
                        ts_str = ""
                        pure_text = block
                        for pref in ["🗣", "📞"]:
                            pure_text = pure_text.replace(pref, "")
                        pure_text = pure_text.lstrip(": ").strip()

                    if is_user:
                        label_caller = client_name or company or number
                        prefix_md = f"🗣 {ts_str} **[{label_caller}]:**"
                    elif is_assistant:
                        prefix_md = f"📞 {ts_str} **[{current_assistant_name}]:**"
                    else:
                        st.caption(block)
                        continue

                    if st.session_state[edit_key] == idx_b:
                        col_inp, col_ok, col_cancel = st.columns([5, 0.6, 0.8])
                        with col_inp:
                            new_txt = st.text_input(
                                f"Edit {prefix_md}",
                                value=pure_text,
                                key=f"edit_inp_{id_call}_{idx_b}",
                                label_visibility="collapsed"
                            )
                        with col_ok:
                            if st.button("✅", key=f"ok_{id_call}_{idx_b}"):
                                emoji_orig = "🗣" if is_user else "📞"
                                blocks_raw[idx_b] = f"{emoji_orig} {ts_str}: {new_txt}" if ts_str else f"{emoji_orig}: {new_txt}"
                                new_trans = "\n\n".join(blocks_raw)
                                conn2 = sqlite3.connect(DB_PATH)
                                conn2.execute("UPDATE calls SET transcript=? WHERE id=?", (new_trans, id_call))
                                conn2.commit()
                                conn2.close()
                                st.session_state[edit_key] = None
                                st.toast(trans.get("ui_toast_phrase_updated", "Updated"))
                                st.rerun()
                        with col_cancel:
                            if st.button("✖", key=f"cancel_{id_call}_{idx_b}"):
                                st.session_state[edit_key] = None
                                st.rerun()
                    else:
                        col_txt, col_edit, col_del = st.columns([6, 0.55, 0.55])
                        with col_txt:
                            st.markdown(f"{prefix_md} {pure_text}")
                        with col_edit:
                            if st.button("✏️", key=f"edit_btn_{id_call}_{idx_b}"):
                                st.session_state[edit_key] = idx_b
                                st.rerun()
                        with col_del:
                            del_confirm_key = f"del_confirm_{id_call}_{idx_b}"
                            if del_confirm_key not in st.session_state:
                                st.session_state[del_confirm_key] = False

                            if not st.session_state[del_confirm_key]:
                                if st.button("🗑️", key=f"del_phrase_{id_call}_{idx_b}"):
                                    st.session_state[del_confirm_key] = True
                                    st.rerun()
                            else:
                                c_yes, c_no = st.columns(2)
                                with c_yes:
                                    if st.button("✓", key=f"del_yes_{id_call}_{idx_b}"):
                                        blocks_raw.pop(idx_b)
                                        new_trans = "\n\n".join(blocks_raw)
                                        conn2 = sqlite3.connect(DB_PATH)
                                        conn2.execute("UPDATE calls SET transcript=? WHERE id=?", (new_trans, id_call))
                                        conn2.commit()
                                        conn2.close()
                                        st.session_state[del_confirm_key] = False
                                        st.toast(trans.get("ui_toast_phrase_deleted", "Deleted"))
                                        st.rerun()
                                with c_no:
                                    if st.button("X", key=f"del_no_{id_call}_{idx_b}"):
                                        st.session_state[del_confirm_key] = False
                                        st.rerun()

                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f:
                            st.audio(f.read(), format="audio/wav")
                    except Exception:
                        pass

                st.write("---")
                c_edit1, c_edit2 = st.columns([2, 2])
                with c_edit1:
                    tag_options = list(trans.get("tags", ["GENERAL CALL"]))
                    if tag_display and tag_display not in tag_options:
                        tag_options.append(tag_display)
                    tag_current_val = tag_display if tag_display in tag_options else tag_options[-1]

                    new_tag = st.selectbox(
                        trans.get("ui_tag_label", "Classification:"),
                        tag_options,
                        index=tag_options.index(tag_current_val),
                        key=f"tag_{id_call}"
                    )
                    if new_tag != tag_current_val:
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute("UPDATE calls SET tag=? WHERE id=?", (new_tag, id_call))
                        conn_loc.commit()
                        conn_loc.close()
                        st.toast(trans.get("ui_toast_tag_updated", "Tag updated"))
                        st.rerun()

                with c_edit2:
                    corr_name = st.text_input(
                        trans.get("ui_caller_name", "Caller Name:"),
                        value=client_name or "",
                        key=f"name_{id_call}"
                    )
                    corr_company = st.text_input(
                        trans.get("ui_company", "Company:"),
                        value=company or "",
                        key=f"comp_{id_call}"
                    )
                    if corr_name != (client_name or "") or corr_company != (company or ""):
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute(
                            "UPDATE calls SET client_name=?, company=? WHERE id=?",
                            (corr_name, corr_company, id_call)
                        )
                        conn_loc.commit()
                        conn_loc.close()
                        st.toast(trans.get("ui_toast_caller_updated", "Caller data updated"))
                        st.rerun()

                st.write("")
                c_act1, c_act2, c_act3, c_act4 = st.columns(4)
                with c_act1:
                    if audio_path and os.path.exists(audio_path):
                        if st.button(trans.get("ui_btn_delete_audio", "Delete Audio"), key=f"delaud_{id_call}"):
                            try:
                                os.remove(audio_path)
                            except Exception:
                                pass
                            conn_loc = sqlite3.connect(DB_PATH)
                            conn_loc.execute("UPDATE calls SET audio_path='' WHERE id=?", (id_call,))
                            conn_loc.commit()
                            conn_loc.close()
                            st.toast(trans.get("ui_toast_audio_deleted", "Audio deleted"))
                            st.rerun()
                with c_act2:
                    if st.button(trans.get("ui_btn_delete_record", "Delete Record"), key=f"delreg_{id_call}"):
                        if audio_path and os.path.exists(audio_path):
                            try:
                                os.remove(audio_path)
                            except Exception:
                                pass
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute("DELETE FROM calls WHERE id=?", (id_call,))
                        conn_loc.commit()
                        conn_loc.close()
                        st.toast(trans.get("ui_toast_record_deleted", "Record deleted"))
                        st.rerun()
                with c_act3:
                    if st.button(trans.get("ui_btn_whitelist", "Whitelist"), key=f"wht_{id_call}"):
                        norm_num = normalize_phone_pattern(number)
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute(
                            "INSERT OR REPLACE INTO contacts (number, type, prompt_rules, tag, note) VALUES (?, 'whitelist', '', '', '')",
                            (norm_num,)
                        )
                        conn_loc.commit()
                        conn_loc.close()
                        st.toast(trans.get("ui_toast_saved", "Saved successfully"))
                        st.rerun()
                with c_act4:
                    if st.button(trans.get("ui_btn_blacklist", "Blacklist"), key=f"blk_{id_call}"):
                        norm_num = normalize_phone_pattern(number)
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute(
                            "INSERT OR REPLACE INTO contacts (number, type, prompt_rules, tag, note) VALUES (?, 'blacklist', '', '', '')",
                            (norm_num,)
                        )
                        conn_loc.commit()
                        conn_loc.close()
                        st.toast(trans.get("ui_toast_saved", "Saved successfully"))
                        st.rerun()
    else:
        st.info(trans.get("ui_no_calls", "No calls recorded yet."))

# =============================================================================
# COLUMN 2: CALLER MESSAGES INBOX & CONTACT FILTERS / WILDCARDS
# =============================================================================
with col2:
    conn = sqlite3.connect(DB_PATH)
    messages_rows = conn.execute(
        "SELECT id, call_id, number, date, time, caller_name, message_text, is_read "
        "FROM messages ORDER BY id DESC"
    ).fetchall()
    conn.close()

    unread_count = sum(1 for m in messages_rows if m[7] == 0)
    badge_str = f" 🔴 ({unread_count} {trans.get('ui_messages_unread', 'unread')})" if unread_count > 0 else f" ({len(messages_rows)})"
    st.subheader(f"{trans.get('messages_inbox_title', '📬 Caller Messages')}{badge_str}")

    with st.container(border=True):
        c_imp1, c_imp2 = st.columns([2, 1])
        with c_imp1:
            show_unread_only = st.checkbox(
                trans.get("ui_messages_unread_only", "Show unread only"),
                value=False,
                key="chk_unread_msgs"
            )
        with c_imp2:
            if st.button(trans.get("ui_messages_import_btn", "📥 Import Old"), key="btn_import_legacy_msgs", use_container_width=True):
                added = import_legacy_messages_from_transcripts()
                st.toast(trans.get("ui_messages_imported_toast", "Imported messages: {count}").format(count=added))
                st.rerun()

        filtered_msgs = [m for m in messages_rows if (not show_unread_only or m[7] == 0)]
        if filtered_msgs:
            for msg in filtered_msgs:
                msg_id, msg_call_id, msg_num, msg_date, msg_time, msg_caller, msg_text, msg_read = msg
                status_icon = "🟢" if msg_read == 0 else "✅"
                header_label = f"{status_icon} [{msg_date} {msg_time}] {msg_caller or msg_num} ({msg_num})"
                with st.expander(header_label, expanded=(msg_read == 0)):
                    st.markdown(f"**{trans.get('ui_message_date_time', 'Date & Exact Time:')}** `{msg_date} {msg_time}`")
                    st.markdown(f"**{trans.get('ui_caller_name', 'Caller Name:')}** {msg_caller or '-'} | **📞** `{msg_num}`")
                    st.write(msg_text)
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        toggle_label = trans.get("ui_btn_mark_read", "✓ Mark Read") if msg_read == 0 else trans.get("ui_btn_mark_unread", "✉️ Mark Unread")
                        if st.button(toggle_label, key=f"msg_read_{msg_id}", use_container_width=True):
                            new_state = 1 if msg_read == 0 else 0
                            conn_m = sqlite3.connect(DB_PATH)
                            conn_m.execute("UPDATE messages SET is_read=? WHERE id=?", (new_state, msg_id))
                            conn_m.commit()
                            conn_m.close()
                            st.rerun()
                    with mc2:
                        if st.button(trans.get("ui_btn_delete_msg", "🗑️ Delete"), key=f"msg_del_{msg_id}", use_container_width=True):
                            conn_m = sqlite3.connect(DB_PATH)
                            conn_m.execute("DELETE FROM messages WHERE id=?", (msg_id,))
                            conn_m.commit()
                            conn_m.close()
                            st.rerun()
        else:
            st.caption(trans.get("ui_no_messages", "No saved caller messages yet."))

    st.write("---")

    st.subheader(trans.get("filters_title", "🚫 Contact Filters & Wildcards"))
    st.caption(trans.get("ui_wildcard_hint", "Supports exact numbers (614027865) and wildcards (* and ?, e.g. 626288*)."))

    with st.form("new_contact"):
        phone_num = st.text_input(trans.get("ui_form_phone", "Phone Number or Wildcard (e.g. 626288*):"))
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            contact_type = st.selectbox(trans.get("ui_form_category", "Action:"), ["whitelist", "blacklist"])
        with c_f2:
            contact_tag = st.text_input(trans.get("ui_form_tag", "Custom Tag (optional):"), value="")
        contact_note = st.text_input(trans.get("ui_form_note", "Label / Note (e.g. Aunt Mary, Telemarketer):"), value="")
        prompt_rules = st.text_area(trans.get("ui_form_prompt", "Custom Instructions for AI:"))
        submit = st.form_submit_button(trans.get("ui_form_save_rule", "💾 Save Rule"), use_container_width=True)

        if submit and phone_num.strip():
            norm_number = normalize_phone_pattern(phone_num)
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT OR REPLACE INTO contacts (number, type, prompt_rules, tag, note) VALUES (?, ?, ?, ?, ?)",
                (norm_number, contact_type, prompt_rules.strip(), contact_tag.strip(), contact_note.strip())
            )
            conn.commit()
            conn.close()
            st.success(trans.get("ui_toast_saved", "Saved successfully"))
            st.rerun()

    st.write(f"**{trans.get('ui_managed_contacts', 'Managed contacts & wildcard rules:')}**")
    conn = sqlite3.connect(DB_PATH)
    contacts = conn.execute("SELECT number, type, prompt_rules, tag, note FROM contacts ORDER BY number ASC").fetchall()
    conn.close()

    if contacts:
        for idx_c, c_row in enumerate(contacts):
            c_num, c_type, c_prompt, c_tag, c_note = c_row
            badge = "🛡️ WHITELIST" if c_type == "whitelist" else "🚫 BLACKLIST"
            wildcard_badge = " [WILDCARD]" if any(w in c_num for w in ("*", "?")) else ""
            note_str = f" — {c_note}" if c_note else ""
            tag_str = f" | 🏷️ {c_tag}" if c_tag else ""

            with st.expander(f"{c_num}{wildcard_badge} -> [{badge}]{note_str}{tag_str}"):
                edit_num = st.text_input(
                    trans.get("ui_form_phone", "Phone / Pattern:"),
                    value=c_num,
                    key=f"edit_c_num_{idx_c}"
                )
                ec1, ec2 = st.columns(2)
                with ec1:
                    edit_type = st.selectbox(
                        trans.get("ui_form_category", "Action:"),
                        ["whitelist", "blacklist"],
                        index=0 if c_type == "whitelist" else 1,
                        key=f"edit_c_type_{idx_c}"
                    )
                with ec2:
                    edit_tag = st.text_input(
                        trans.get("ui_form_tag", "Custom Tag:"),
                        value=c_tag or "",
                        key=f"edit_c_tag_{idx_c}"
                    )
                edit_note = st.text_input(
                    trans.get("ui_form_note", "Note:"),
                    value=c_note or "",
                    key=f"edit_c_note_{idx_c}"
                )
                edit_prompt = st.text_area(
                    trans.get("ui_form_prompt", "Custom Instructions:"),
                    value=c_prompt or "",
                    key=f"edit_c_prompt_{idx_c}"
                )
                eb1, eb2 = st.columns(2)
                with eb1:
                    if st.button(trans.get("ui_btn_update_contact", "💾 Update"), key=f"btn_upd_c_{idx_c}", use_container_width=True):
                        norm_new_num = normalize_phone_pattern(edit_num)
                        conn_c = sqlite3.connect(DB_PATH)
                        if norm_new_num != c_num:
                            conn_c.execute("DELETE FROM contacts WHERE number=?", (c_num,))
                        conn_c.execute(
                            "INSERT OR REPLACE INTO contacts (number, type, prompt_rules, tag, note) VALUES (?, ?, ?, ?, ?)",
                            (norm_new_num, edit_type, edit_prompt.strip(), edit_tag.strip(), edit_note.strip())
                        )
                        conn_c.commit()
                        conn_c.close()
                        st.toast(trans.get("ui_toast_saved", "Saved successfully"))
                        st.rerun()
                with eb2:
                    if st.button(trans.get("ui_btn_delete_contact", "🗑️ Delete"), key=f"btn_del_c_{idx_c}", use_container_width=True):
                        conn_c = sqlite3.connect(DB_PATH)
                        conn_c.execute("DELETE FROM contacts WHERE number=?", (c_num,))
                        conn_c.commit()
                        conn_c.close()
                        st.toast(trans.get("ui_toast_record_deleted", "Deleted"))
                        st.rerun()
    else:
        st.caption(trans.get("ui_no_contacts", "No contacts or wildcard rules configured yet."))

# =============================================================================
# COLUMN 3: SYSTEM CONTROLS & ASSISTANT SETTINGS
# =============================================================================
with col3:
    st.subheader(trans.get("settings_title", "⚙️ Assistant Settings"))

    if "pending_lang" not in st.session_state:
        st.session_state.pending_lang = None
    selected_lang = st.selectbox(
        trans.get("language_label", "System Language:"),
        available_langs,
        index=available_langs.index(current_lang)
    )

    if selected_lang != current_lang and st.session_state.pending_lang != selected_lang:
        st.session_state.pending_lang = selected_lang
        st.rerun()

    if st.session_state.pending_lang:
        confirm_language_dialog()

    st.write("---")

    # --- DAEMON CONTROLS & FULL LINUX SERVER REBOOT (WITH SUDO PASSWORD INPUT) ---
    st.markdown(f"**🎛️ {trans.get('ui_daemon_control_title', 'Switchboard & Linux Server Control')}**")
    with st.container(border=True):
        daemon_state = get_config("daemon_state", "running")
        try:
            last_hb = float(get_config("daemon_heartbeat", "0"))
        except ValueError:
            last_hb = 0.0
        hb_age = time.time() - last_hb

        if daemon_state == "stopped" or hb_age > 15.0:
            status_badge = trans.get("ui_daemon_status_stopped", "🔴 Stopped / Offline")
        elif daemon_state == "paused":
            status_badge = trans.get("ui_daemon_status_paused", "⏸️ Paused (Calls ring without answering)")
        else:
            status_badge = trans.get("ui_daemon_status_running", "🟢 Active (Listening for calls)")

        st.markdown(f"**{trans.get('ui_daemon_status_label', 'Status:')}** {status_badge}")

        dc1, dc2 = st.columns(2)
        with dc1:
            if daemon_state == "paused":
                if st.button(trans.get("ui_btn_resume_daemon", "▶️ Resume Switchboard"), key="btn_daemon_resume", use_container_width=True):
                    set_config("daemon_state", "running")
                    st.toast(trans.get("ui_toast_daemon_resumed", "Switchboard resumed"))
                    st.rerun()
            else:
                if st.button(trans.get("ui_btn_pause_daemon", "⏸️ Pause Switchboard"), key="btn_daemon_pause", use_container_width=True):
                    set_config("daemon_state", "paused")
                    st.toast(trans.get("ui_toast_daemon_paused", "Switchboard paused"))
                    st.rerun()
        with dc2:
            if st.button(trans.get("ui_btn_stop_daemon", "⏹️ Stop Daemon"), key="btn_daemon_stop", use_container_width=True):
                set_config("daemon_state", "stopped")
                st.toast(trans.get("ui_toast_daemon_stopped", "Stop signal sent to daemon"))
                st.rerun()

        st.write("")
        if "confirm_server_reboot" not in st.session_state:
            st.session_state.confirm_server_reboot = False

        if not st.session_state.confirm_server_reboot:
            if st.button(trans.get("ui_btn_reboot_server", "🔄 Reboot Linux Server"), key="btn_reboot_host", use_container_width=True):
                st.session_state.confirm_server_reboot = True
                st.rerun()
        else:
            st.warning(trans.get("ui_confirm_reboot_warning", "⚠️ Are you sure you want to reboot the entire Linux server?"))
            sudo_pwd = st.text_input(
                trans.get("ui_sudo_password_label", "Sudo password (required to reboot):"),
                type="password",
                key="reboot_sudo_pwd"
            )
            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button(trans.get("ui_btn_confirm_reboot_yes", "✅ Yes, Reboot Now"), key="btn_reboot_yes", use_container_width=True):
                    st.session_state.confirm_server_reboot = False
                    st.toast(trans.get("ui_toast_rebooting", "Rebooting Linux server..."))
                    if sudo_pwd:
                        proc = subprocess.Popen(
                            ["sudo", "-S", "reboot"],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True
                        )
                        try:
                            proc.stdin.write(sudo_pwd + "\n")
                            proc.stdin.flush()
                        except Exception:
                            pass
                    else:
                        subprocess.Popen(["sudo", "-n", "reboot"])
            with rc2:
                if st.button(trans.get("modal_btn_cancel", "❌ Cancel"), key="btn_reboot_no", use_container_width=True):
                    st.session_state.confirm_server_reboot = False
                    st.rerun()

    st.write("---")

    # --- AUTO-CLEANUP DATA ---
    st.markdown(f"**🗑️ {trans.get('ui_cleanup_title', 'Auto-Cleanup Data')}**")
    with st.container(border=True):
        cl1, cl2 = st.columns(2)
        with cl1:
            days_audio = st.number_input(
                trans.get("ui_cleanup_audio_label", "Delete audio older than (days):"),
                min_value=1, max_value=3650, value=30, step=1, key="cleanup_audio_days"
            )
            if st.button(trans.get("ui_cleanup_audio_btn", "🗑️ Delete Audio"), key="btn_cleanup_audio"):
                cutoff_audio = datetime.datetime.now() - datetime.timedelta(days=int(days_audio))
                recs_dir = os.path.join(BASE_DIR, "recordings")
                deleted_audio = 0
                if os.path.exists(recs_dir):
                    for fname in os.listdir(recs_dir):
                        fpath = os.path.join(recs_dir, fname)
                        if os.path.isfile(fpath):
                            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                            if mtime < cutoff_audio:
                                try:
                                    os.remove(fpath)
                                    deleted_audio += 1
                                except Exception:
                                    pass
                conn_cl = sqlite3.connect(DB_PATH)
                all_audio = conn_cl.execute("SELECT id, audio_path, client_audio_path FROM calls").fetchall()
                for row in all_audio:
                    aid, ap, cap = row
                    if ap and not os.path.exists(ap):
                        conn_cl.execute("UPDATE calls SET audio_path='' WHERE id=?", (aid,))
                    if cap and not os.path.exists(cap):
                        conn_cl.execute("UPDATE calls SET client_audio_path='' WHERE id=?", (aid,))
                conn_cl.commit()
                conn_cl.close()
                st.toast(trans.get("ui_cleanup_audio_done", "Recordings deleted: {count}").format(count=deleted_audio))
                st.rerun()

        with cl2:
            days_records = st.number_input(
                trans.get("ui_cleanup_records_label", "Delete records older than (days):"),
                min_value=1, max_value=3650, value=30, step=1, key="cleanup_record_days"
            )
            if st.button(trans.get("ui_cleanup_records_btn", "❌ Delete Records"), key="btn_cleanup_records"):
                cutoff_rec = datetime.datetime.now() - datetime.timedelta(days=int(days_records))
                conn_cl = sqlite3.connect(DB_PATH)
                old_rows = conn_cl.execute(
                    "SELECT id, audio_path, client_audio_path FROM calls WHERE date < ?",
                    (cutoff_rec.strftime("%Y-%m-%d %H:%M:%S"),)
                ).fetchall()
                deleted_recs = 0
                for row in old_rows:
                    rid, ap, cap = row
                    for fpath in [ap, cap]:
                        if fpath and os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
                    conn_cl.execute("DELETE FROM calls WHERE id=?", (rid,))
                    conn_cl.execute("DELETE FROM messages WHERE call_id=?", (rid,))
                    deleted_recs += 1
                conn_cl.commit()
                conn_cl.close()
                st.toast(trans.get("ui_cleanup_records_done", "Records deleted: {count}").format(count=deleted_recs))
                st.rerun()

        st.write("")
        if st.button(trans.get("ui_cleanup_all_btn", "🔥 Delete ALL Records and Recordings"), key="btn_cleanup_all", use_container_width=True):
            recs_dir = os.path.join(BASE_DIR, "recordings")
            deleted_all_audio = 0
            if os.path.exists(recs_dir):
                for fname in os.listdir(recs_dir):
                    fpath = os.path.join(recs_dir, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                            deleted_all_audio += 1
                        except Exception:
                            pass
            conn_cl = sqlite3.connect(DB_PATH)
            all_rows = conn_cl.execute("SELECT id, audio_path, client_audio_path FROM calls").fetchall()
            deleted_all_recs = len(all_rows)
            for row in all_rows:
                _, ap, cap = row
                for fpath in [ap, cap]:
                    if fpath and os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                            deleted_all_audio += 1
                        except Exception:
                            pass
            conn_cl.execute("DELETE FROM calls")
            conn_cl.execute("DELETE FROM messages")
            conn_cl.execute("DELETE FROM sqlite_sequence WHERE name IN ('calls', 'messages')")
            conn_cl.commit()
            conn_cl.close()
            st.toast(trans.get("ui_cleanup_all_done", "All records ({records}) and recordings ({audio}) deleted.").format(records=deleted_all_recs, audio=deleted_all_audio))
            st.rerun()

    st.write("---")
    current_wait = int(get_config("wait_seconds", "5"))
    wait_slider = st.slider(
        trans.get("wait_seconds_label", "Wait before answer:"),
        min_value=0, max_value=15, value=current_wait
    )
    if wait_slider != current_wait:
        set_config("wait_seconds", wait_slider)

    # --- NETWORK SPAM PROTECTION, CACHE & LIVE AI TESTER ---
    st.write("---")
    st.subheader(trans.get("ui_spam_title", "🛡️ Network SPAM Protection"))
    current_spam = get_config("auto_block_spam", "false") == "true"
    block_spam_chk = st.checkbox(trans.get("auto_block_spam_label", "Auto hang up Spam"), value=current_spam)
    if block_spam_chk != current_spam:
        set_config("auto_block_spam", "true" if block_spam_chk else "false")

    sc1, sc2 = st.columns([2, 1])
    with sc1:
        current_cache_days = int(get_config("spam_cache_days", "7"))
        new_cache_days = st.number_input(
            trans.get("ui_spam_cache_days_label", "SPAM Cache expiration (days):"),
            min_value=0, max_value=90, value=current_cache_days, step=1
        )
        if new_cache_days != current_cache_days:
            set_config("spam_cache_days", new_cache_days)
    with sc2:
        st.write("")
        if st.button(trans.get("ui_btn_clear_spam_cache", "🧹 Clear Cache"), key="btn_clr_spam_cache", use_container_width=True):
            conn_sc = sqlite3.connect(DB_PATH)
            conn_sc.execute("DELETE FROM spam_cache")
            conn_sc.commit()
            conn_sc.close()
            st.toast(trans.get("ui_toast_spam_cache_cleared", "SPAM cache cleared"))

    spam_providers_json = get_config("spam_providers", "")
    if not spam_providers_json:
        spam_data = load_language_data(current_lang, "spam.json")
        spam_urls_list = spam_data.get("providers", [])
    else:
        try:
            spam_urls_list = json.loads(spam_providers_json)
        except Exception:
            spam_urls_list = []

    st.caption(trans.get("ui_spam_providers_desc", "Add one URL per line. Placeholders: {number}, {national}, {e164}"))
    current_spam_text = "\n".join(spam_urls_list)
    new_spam_text = st.text_area(
        trans.get("ui_spam_providers_label", "SPAM URLs:"),
        value=current_spam_text,
        label_visibility="collapsed"
    )

    if new_spam_text != current_spam_text:
        new_list = [url.strip() for url in new_spam_text.split("\n") if url.strip()]
        set_config("spam_providers", json.dumps(new_list, ensure_ascii=False))
        spam_urls_list = new_list

    with st.expander(trans.get("ui_spam_test_expander", "🔍 Test Phone Number Against SPAM Providers")):
        test_num_inp = st.text_input(trans.get("ui_spam_test_input", "Phone number to test:"), key="spam_test_num_inp")
        if st.button(trans.get("ui_spam_test_btn", "Run SPAM Test"), key="btn_run_spam_test") and test_num_inp.strip():
            active_text_model = get_config("text_model", "gemini-3-flash-preview")
            for tpl in spam_urls_list:
                formatted_url = format_spam_test_url(tpl, test_num_inp.strip())
                try:
                    status_code, raw_html = fetch_spam_page_sync(formatted_url)
                    if status_code == 200:
                        clean_txt = clean_html_for_spam(raw_html)
                        st.success(f"HTTP {status_code} — {formatted_url} ({len(clean_txt)} chars)")
                        st.caption(clean_txt[:500] + ("..." if len(clean_txt) > 500 else ""))
                        verdict = evaluate_spam_text_with_ai(clean_txt, test_num_inp.strip(), active_text_model, current_lang)
                        v_spam = bool(verdict.get("is_spam"))
                        v_score = int(verdict.get("risk_score", 0))
                        v_reason = verdict.get("reason", "")
                        if v_spam or v_score > 70:
                            st.error(f"🚨 **AI Verdict: SPAM ({v_score}/100)** — {v_reason}")
                        else:
                            st.info(f"✅ **AI Verdict: CLEAN ({v_score}/100)** — {v_reason}")
                    else:
                        st.error(f"HTTP {status_code} — {formatted_url}")
                except Exception as e:
                    st.error(f"Failed: {formatted_url} -> {e}")

    # --- CONFIGURABLE CONTEXT MEMORY & SUMMARIES ---
    st.write("---")
    st.subheader(trans.get("memory_title", "🧠 Call Memory & Category Rules"))

    mem_mode_opts = ["disabled", "per_number", "per_category", "global"]
    mem_mode_labels = trans.get("memory_mode_labels", {
        "disabled": "Disabled (No past call memory)",
        "per_number": "Per Phone Number (Default)",
        "per_category": "Per Category / Contact Tag",
        "global": "Global (All non-SPAM calls)"
    })
    current_mem_mode = get_config("memory_mode", "per_number")
    if current_mem_mode not in mem_mode_opts:
        current_mem_mode = "per_number"

    new_mem_mode = st.selectbox(
        trans.get("memory_mode_select_label", "Memory Scope:"),
        mem_mode_opts,
        format_func=lambda x: mem_mode_labels.get(x, x),
        index=mem_mode_opts.index(current_mem_mode)
    )
    if new_mem_mode != current_mem_mode:
        set_config("memory_mode", new_mem_mode)
        st.rerun()

    if new_mem_mode == "global":
        st.warning(trans.get(
            "memory_global_warning",
            "⚠️ Warning: In Global mode, the AI knows summaries of recent non-SPAM calls from all numbers. An unknown caller could attempt social engineering to ask about other callers."
        ))

    if new_mem_mode != "disabled":
        mm1, mm2, mm3 = st.columns(3)
        with mm1:
            curr_max_calls = int(get_config("memory_max_calls", "1"))
            new_max_calls = st.number_input(
                trans.get("memory_max_calls_label", "Calls to remember:"),
                min_value=1, max_value=20, value=curr_max_calls, step=1
            )
            if new_max_calls != curr_max_calls:
                set_config("memory_max_calls", new_max_calls)
        with mm2:
            curr_max_days = int(get_config("memory_max_days", "30"))
            new_max_days = st.number_input(
                trans.get("memory_max_days_label", "Max age (days):"),
                min_value=1, max_value=365, value=curr_max_days, step=1
            )
            if new_max_days != curr_max_days:
                set_config("memory_max_days", new_max_days)
        with mm3:
            curr_max_chars = int(get_config("memory_max_chars", "2500"))
            new_max_chars = st.number_input(
                trans.get("memory_max_chars_label", "Max characters:"),
                min_value=500, max_value=12000, value=curr_max_chars, step=250
            )
            if new_max_chars != curr_max_chars:
                set_config("memory_max_chars", new_max_chars)

    rules_json = get_config("memory_rules", "[]")
    try:
        rules = json.loads(rules_json)
    except Exception:
        rules = []

    new_cat_name = st.text_input(trans.get("add_category_label", "Add category:"))
    if st.button(trans.get("create_category_btn", "+ Create")) and new_cat_name:
        rules.append({"category": new_cat_name, "keywords": [], "days": 7, "wait_seconds": 120})
        set_config("memory_rules", json.dumps(rules, ensure_ascii=False))
        st.rerun()

    for idx, rule in enumerate(rules):
        widget_suffix = f"{idx}_{current_lang}"
        rule_category = rule.get("category", "Unknown")
        rule_keywords = rule.get("keywords", [])
        rule_days = rule.get("days", 7)
        rule_wait = rule.get("wait_seconds", 120)

        with st.expander(f"📁 {rule_category}"):
            new_cat_title = st.text_input(trans.get("ui_cat_name", "Category Name:"), value=rule_category, key=f"cat_{widget_suffix}")
            keywords_val = st.text_input(trans.get("ui_cat_keywords", "Keywords:"), value=", ".join(rule_keywords), key=f"kw_{widget_suffix}")
            days_val = st.number_input(trans.get("ui_cat_days", "Days:"), min_value=1, value=rule_days, key=f"days_{widget_suffix}")
            wait_val = st.number_input(trans.get("ui_cat_wait", "Wait Seconds:"), min_value=10, value=rule_wait, key=f"wait_{widget_suffix}")

            rules[idx] = {
                "category": new_cat_title,
                "keywords": [p.strip().lower() for p in keywords_val.split(",") if p.strip()],
                "days": days_val,
                "wait_seconds": wait_val
            }

            if st.button("🗑️", key=f"delcat_{widget_suffix}"):
                rules.pop(idx)
                set_config("memory_rules", json.dumps(rules, ensure_ascii=False))
                st.rerun()

    if st.button(trans.get("save_memory_btn", "💾 Save Category Config")):
        set_config("memory_rules", json.dumps(rules, ensure_ascii=False))
        st.success(trans.get("ui_toast_saved", "Saved successfully"))

    st.write("---")
    st.subheader(trans.get("priority_keywords_title", "🚨 Priority Keywords"))
    current_kw = get_config("priority_keywords", "")
    new_kw = st.text_area(trans.get("priority_keywords_desc", "Keywords:"), value=current_kw)
    if new_kw != current_kw:
        set_config("priority_keywords", new_kw)

    # --- TRANSCRIPTION MODE & WHISPER MODEL DOWNLOADER ---
    st.write("---")
    st.subheader(trans.get("transcription_mode_title", "🎙️ Transcription Mode"))
    st.caption(trans.get("gemini_live_trans_note", "ℹ️ Gemini 3.8 Live already transcribes calls natively in real time. Local Whisper.cpp is optional."))

    current_model = get_config("text_model", "gemini-3-flash-preview")
    model_opts = trans.get("text_model_opts", ["gemini-3-flash-preview", "gemma-4-31b-it", "gemma-4-26b-a4b-it"])
    idx_model = model_opts.index(current_model) if current_model in model_opts else 0
    new_model = st.selectbox(trans.get("ui_text_model_label", "Text Model:"), model_opts, index=idx_model)
    if new_model != current_model:
        set_config("text_model", new_model)
        if "gemma" in new_model.lower():
            if get_config("final_transcription_mode", "disabled") == "gemini_final":
                set_config("final_transcription_mode", "disabled")
        st.rerun()

    whisper_bin_path = find_whisper_bin()
    whisper_installed = bool(whisper_bin_path)

    if whisper_installed:
        trans_mode_opts = ["disabled", "realtime", "whisper_final"] if "gemma" in current_model.lower() else ["disabled", "realtime", "whisper_final", "gemini_final"]
    else:
        trans_mode_opts = ["disabled"] if "gemma" in current_model.lower() else ["disabled", "gemini_final"]

    trans_mode_labels = trans.get("trans_mode_opts_labels", {
        "disabled": "Disabled (Gemini Live only)",
        "realtime": "Real-time (Whisper.cpp)",
        "whisper_final": "Whisper.cpp at end of call",
        "gemini_final": "Gemini Flash 3 at end of call"
    })

    current_trans_mode = get_config("final_transcription_mode", "disabled")
    if current_trans_mode not in trans_mode_opts:
        current_trans_mode = "disabled"
        set_config("final_transcription_mode", current_trans_mode)

    selected_mode = st.selectbox(
        trans.get("transcription_mode_label", "Select mode:"),
        trans_mode_opts,
        format_func=lambda x: trans_mode_labels.get(x, x),
        index=trans_mode_opts.index(current_trans_mode)
    )
    if selected_mode != current_trans_mode:
        set_config("final_transcription_mode", selected_mode)
        st.rerun()

    if not whisper_installed:
        st.info(trans.get(
            "whisper_not_installed_info",
            "whisper-cli is not installed. Run './install_system_deps.sh --with-whisper' if you want local Whisper.cpp support."
        ))
    else:
        st.write("---")
        st.subheader(trans.get("whisper_model_label", "Whisper Local Model (GGML)"))
        w_model_opts = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v2", "large-v3", "large-v3-turbo"]
        w_quant_opts = {"": "default (fp16)", "-q4_0": "q4_0", "-q5_0": "q5_0", "-q8_0": "q8_0"}

        col_wm, col_wq = st.columns(2)
        with col_wm:
            current_w_model = get_config("whisper_model", "medium")
            new_w_model = st.selectbox(
                trans.get("ui_whisper_base", "Model Base:"),
                w_model_opts,
                index=w_model_opts.index(current_w_model) if current_w_model in w_model_opts else 6
            )
            if new_w_model != current_w_model:
                set_config("whisper_model", new_w_model)
                st.rerun()

        with col_wq:
            current_w_quant = get_config("whisper_quant", "")
            quant_keys = list(w_quant_opts.keys())
            new_w_quant = st.selectbox(
                trans.get("ui_whisper_quant", "Quantization:"),
                quant_keys,
                format_func=lambda x: w_quant_opts[x],
                index=quant_keys.index(current_w_quant) if current_w_quant in quant_keys else 0
            )
            if new_w_quant != current_w_quant:
                set_config("whisper_quant", new_w_quant)
                st.rerun()

        full_selected_model = f"{new_w_model}{new_w_quant}"
        model_file_path = os.path.join(MODELS_DIR, f"ggml-{full_selected_model}.bin")
        if os.path.exists(model_file_path):
            st.success(f"✅ `models/ggml-{full_selected_model}.bin` {trans.get('ui_model_installed', 'is installed.')}")
        else:
            st.warning(f"⚠️ `models/ggml-{full_selected_model}.bin` {trans.get('ui_model_missing', 'is not downloaded yet.')}")

        wt1, wt2 = st.columns([1.4, 1.6])
        with wt1:
            selected_terminal = st.selectbox(
                trans.get("ui_terminal_select", "Installer Terminal:"),
                SUPPORTED_TERMINALS,
                index=0
            )
        with wt2:
            st.write("")
            if st.button(
                trans.get("ui_btn_install_whisper_model", "⬇️ Download / Quantize Model"),
                key="btn_dl_whisper_model",
                use_container_width=True
            ):
                with st.spinner(trans.get("ui_installing_model_wait", "Installing {model} model. Please wait...").format(model=full_selected_model)):
                    ok_status, status_msg = install_whisper_model(full_selected_model, selected_terminal)
                if ok_status:
                    st.toast(status_msg)
                    st.rerun()
                else:
                    st.error(status_msg)

    # --- PC SPEAKER MONITORING ---
    st.write("---")
    st.subheader(trans.get("monitor_mode_title", "🔊 PC Speaker Monitoring"))
    monitor_mode_opts = ["none", "both", "caller", "assistant"]
    monitor_mode_labels = trans.get("monitor_mode_opts_labels", {
        "none": "None (Total silence on PC)",
        "both": "Both (Caller & Secretary)",
        "caller": "Caller Only",
        "assistant": "Secretary Only"
    })
    current_monitor_mode = get_config("monitor_mode", "none")
    selected_monitor_mode = st.selectbox(
        trans.get("monitor_mode_label", "Select what you want to hear locally:"),
        monitor_mode_opts,
        format_func=lambda x: monitor_mode_labels.get(x, x),
        index=monitor_mode_opts.index(current_monitor_mode) if current_monitor_mode in monitor_mode_opts else 0
    )
    if selected_monitor_mode != current_monitor_mode:
        set_config("monitor_mode", selected_monitor_mode)
        st.rerun()

    st.caption(trans.get("allow_pc_mic_desc", "PC microphone is isolated to prevent leakage and echo."))

    # --- GEMINI 3.8 LIVE AUDIO & VAD TUNING PANEL ---
    st.write("---")
    st.subheader(trans.get("audio_mode_title", "🎚️ Audio, Echo & Gemini 3.8 VAD Tuning"))

    current_echo = get_config("software_echo_suppression", "false") == "true"
    new_echo_chk = st.checkbox(
        trans.get("software_echo_label", "Enable Software Echo Suppression (Half-Duplex)"),
        value=current_echo
    )
    if new_echo_chk != current_echo:
        set_config("software_echo_suppression", "true" if new_echo_chk else "false")
        st.rerun()

    current_prot_greet = get_config("protect_initial_greeting", "true") == "true"
    new_prot_greet = st.checkbox(
        trans.get("protect_greeting_label", "Protect Initial Greeting from Early Line Interruptions"),
        value=current_prot_greet
    )
    if new_prot_greet != current_prot_greet:
        set_config("protect_initial_greeting", "true" if new_prot_greet else "false")
        st.rerun()

    av1, av2 = st.columns(2)
    with av1:
        curr_gain = float(get_config("caller_gain", "1.5"))
        new_gain = st.slider(
            trans.get("caller_gain_label", "Caller Mic Gain (x):"),
            min_value=0.5, max_value=5.0, value=curr_gain, step=0.5
        )
        if new_gain != curr_gain:
            set_config("caller_gain", new_gain)

        vad_sens_opts = ["HIGH", "LOW"]
        curr_vad_start = get_config("vad_start_sensitivity", "LOW")
        if curr_vad_start not in vad_sens_opts:
            curr_vad_start = "LOW"
        new_vad_start = st.selectbox(
            trans.get("vad_start_sens_label", "VAD Start Sensitivity:"),
            vad_sens_opts,
            index=vad_sens_opts.index(curr_vad_start)
        )
        if new_vad_start != curr_vad_start:
            set_config("vad_start_sensitivity", new_vad_start)

        curr_pad_ms = int(get_config("vad_prefix_padding_ms", "500"))
        new_pad_ms = st.slider(
            trans.get("vad_prefix_padding_label", "VAD Prefix Padding (ms):"),
            min_value=50, max_value=1000, value=curr_pad_ms, step=50
        )
        if new_pad_ms != curr_pad_ms:
            set_config("vad_prefix_padding_ms", new_pad_ms)

    with av2:
        curr_gate = int(get_config("noise_gate_base", "50"))
        new_gate = st.slider(
            trans.get("noise_gate_label", "Base Noise Gate (RMS):"),
            min_value=0, max_value=100, value=curr_gate, step=5
        )
        if new_gate != curr_gate:
            set_config("noise_gate_base", new_gate)

        curr_vad_end = get_config("vad_end_sensitivity", "HIGH")
        if curr_vad_end not in vad_sens_opts:
            curr_vad_end = "HIGH"
        new_vad_end = st.selectbox(
            trans.get("vad_end_sens_label", "VAD End Sensitivity:"),
            vad_sens_opts,
            index=vad_sens_opts.index(curr_vad_end)
        )
        if new_vad_end != curr_vad_end:
            set_config("vad_end_sensitivity", new_vad_end)

        curr_sil_ms = int(get_config("vad_silence_duration_ms", "500"))
        new_sil_ms = st.slider(
            trans.get("vad_silence_duration_label", "VAD Silence Duration (ms):"),
            min_value=200, max_value=2000, value=curr_sil_ms, step=100
        )
        if new_sil_ms != curr_sil_ms:
            set_config("vad_silence_duration_ms", new_sil_ms)

    # --- OWNER & IDENTITY CONFIGURATION ---
    st.write("---")
    st.subheader(trans.get("owner_settings_title", "👤 Owner"))
    current_boss_name = get_config("boss_name", "")
    new_boss_name = st.text_input(trans.get("owner_name_label", "Boss Name:"), value=current_boss_name)
    if new_boss_name != current_boss_name:
        set_config("boss_name", new_boss_name.strip())

    current_owner_type = get_config("owner_type", "private")
    owner_type_opts = trans.get("owner_types", ["private", "professional", "business"])
    idx_owner = owner_type_opts.index(current_owner_type) if current_owner_type in owner_type_opts else 0
    new_owner_type = st.selectbox(trans.get("owner_type_label", "Owner Type:"), owner_type_opts, index=idx_owner)

    if new_owner_type != current_owner_type:
        set_config("owner_type", new_owner_type)
        if not get_config("initial_greeting", ""):
            set_config("initial_greeting", trans.get("default_legal_warning", ""))
        st.rerun()

    current_desc = get_config("business_description", "")
    new_desc = st.text_area(trans.get("activity_desc_label", "Activity:"), value=current_desc)
    if new_desc != current_desc:
        set_config("business_description", new_desc.strip())

    current_calls = get_config("expected_calls", "")
    new_calls = st.text_area(trans.get("expected_calls_label", "Expected calls:"), value=current_calls)
    if new_calls != current_calls:
        set_config("expected_calls", new_calls.strip())

    st.write("---")
    st.subheader(trans.get("identity_title", "👤 Identity"))
    assistant_name_val = st.text_input(trans.get("assistant_name_label", "Name:"), value=current_assistant_name)
    if assistant_name_val != current_assistant_name:
        set_config("assistant_name", assistant_name_val.strip())
        st.rerun()

    current_gender = get_config("assistant_gender", "female")
    gender_opts = trans.get("gender_types", ["female", "male"])
    idx_gender = gender_opts.index(current_gender) if current_gender in gender_opts else 0
    new_gender = st.selectbox(trans.get("assistant_gender_label", "Voice:"), gender_opts, index=idx_gender)
    if new_gender != current_gender:
        set_config("assistant_gender", new_gender)
        st.rerun()

    current_greeting = get_config("initial_greeting", "")
    new_greeting = st.text_area(trans.get("ui_initial_greeting", "Exact Initial Greeting:"), value=current_greeting)
    if new_greeting != current_greeting:
        set_config("initial_greeting", new_greeting.strip())

    current_extra = get_config("extra_prompt", "")
    new_extra = st.text_area(trans.get("ui_extra_prompt", "Personality & Extra Instructions:"), value=current_extra)
    if new_extra != current_extra:
        set_config("extra_prompt", new_extra.strip())
