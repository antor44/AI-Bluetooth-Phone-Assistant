#!/usr/bin/env python3
"""
AI Switchboard Web Interface - Streamlit UI for managing configurations and logs.
Displays transcripts, handles settings configuration, and manages category logic.

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

import streamlit as st
import sqlite3
import os
import json
import datetime
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "switchboard.db")
LANG_DIR = os.path.join(BASE_DIR, "languages")

def init_db():
    """Initializes the database schema and defines fundamental global settings."""
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
    
    c.execute("INSERT OR IGNORE INTO settings VALUES ('wait_seconds', '0')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('auto_block_spam', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_model', 'medium')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('whisper_quant', '')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('software_echo_suppression', 'false')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('final_transcription_mode', 'realtime')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('monitor_mode', 'both')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('language', 'es-ES')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('allow_pc_mic', 'false')")
    
    conn.commit()
    conn.close()

def get_config(key, default_value):
    """Retrieves standard or language-localized configuration elements from the database."""
    conn = sqlite3.connect(DB_PATH)
    res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
    current_lang = res_lang[0] if res_lang else "es-ES"
    
    localized_keys = ["boss_name", "assistant_name", "assistant_gender", "owner_type", "priority_keywords", "memory_rules", "business_description", "expected_calls", "initial_greeting", "extra_prompt", "text_model"]
    if key in localized_keys:
        lang_key = f"{current_lang}_{key}"
        res = conn.execute("SELECT value FROM settings WHERE key=?", (lang_key,)).fetchone()
        if res is not None:
            conn.close()
            return res[0]
            
    res_global = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return res_global[0] if res_global is not None else default_value

def set_config(key, value):
    """Persists standard or localized settings dynamically to the database."""
    conn = sqlite3.connect(DB_PATH)
    res_lang = conn.execute("SELECT value FROM settings WHERE key='language'").fetchone()
    current_lang = res_lang[0] if res_lang else "es-ES"
    
    localized_keys = ["boss_name", "assistant_name", "assistant_gender", "owner_type", "priority_keywords", "memory_rules", "business_description", "expected_calls", "initial_greeting", "extra_prompt", "text_model"]
    db_key = f"{current_lang}_{key}" if key in localized_keys else key
    
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_key, str(value)))
    conn.commit()
    conn.close()

def get_available_languages():
    if not os.path.exists(LANG_DIR): return ["es-ES"]
    return [d for d in os.listdir(LANG_DIR) if os.path.isdir(os.path.join(LANG_DIR, d))]

def load_language_data(lang_code, file_name="gui.json"):
    path = os.path.join(LANG_DIR, lang_code, file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def apply_language_defaults(lang_code):
    gui_data = load_language_data(lang_code, "gui.json")
    defaults = gui_data.get("defaults", {})
    if defaults:
        conn = sqlite3.connect(DB_PATH)
        for key, val in defaults.items():
            db_key = f"{lang_code}_{key}"
            str_val = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (db_key, str_val))
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

st.set_page_config(page_title=f"{trans.get('gui_title', 'AI Switchboard')} - {current_assistant_name}", page_icon="📞", layout="wide")
st.title(f"{trans.get('gui_header', 'AI Switchboard Panel')} ({current_assistant_name})")

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

st.components.v1.html(
    """
    <script>
    const runLiveRefresh = () => {
        setTimeout(() => {
            window.parent.document.querySelector('section.main').click();
            runLiveRefresh();
        }, 3000);
    };
    runLiveRefresh();
    </script>
    """,
    height=0
)

pending_lang = st.session_state.get("pending_lang", None)
target_trans = load_language_data(pending_lang, "gui.json") if pending_lang else trans

@st.dialog(target_trans.get("modal_confirm_lang_title", "Language Change").format(lang=st.session_state.get("pending_lang", "")))
def confirm_language_dialog():
    st.markdown(target_trans.get("modal_confirm_lang_body", ""))
    c_saved, c_defaults, c_keep, c_cancel = st.columns(4)
    with c_saved:
        if st.button(target_trans.get("modal_btn_saved", "📂 Load Saved"), key="modal_saved_btn"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('language', ?)", (st.session_state.pending_lang,))
            conn.commit(); conn.close()
            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
    with c_defaults:
        if st.button(target_trans.get("modal_btn_defaults", "🔄 Load Defaults"), key="modal_defaults_btn"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('language', ?)", (st.session_state.pending_lang,))
            conn.commit(); conn.close()
            apply_language_defaults(st.session_state.pending_lang)
            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
    with c_keep:
        if st.button(target_trans.get("modal_btn_keep", "📌 Keep Current"), key="modal_keep_btn"):
            old_lang = get_config("language", "es-ES")
            target_lang = st.session_state.pending_lang
            localized_keys = ["boss_name", "assistant_name", "assistant_gender", "owner_type", "priority_keywords", "memory_rules", "business_description", "expected_calls", "initial_greeting", "extra_prompt", "text_model"]
            
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
            conn.commit(); conn.close()
            
            st.session_state.pending_lang = None
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
    with c_cancel:
        if st.button(target_trans.get("modal_btn_cancel", "❌ Cancel"), key="modal_cancel_btn"):
            st.session_state.pending_lang = None
            st.rerun()

col1, col2, col3 = st.columns([1.5, 1.1, 1.2])

with col1:
    st.subheader(trans.get("call_log_title", "Call Log & Recordings"))
    show_system_msg = st.checkbox(trans.get("show_system_msg_label", "Show system messages"), value=True, key="toggle_sys_msg")

    conn = sqlite3.connect(DB_PATH)
    calls = conn.execute("SELECT id, number, date, spam_score, transcript, audio_path, tag, client_name, company FROM calls ORDER BY id DESC").fetchall()
    conn.close()
    
    if calls:
        for call in calls:
            id_call, number, date, spam_score, transcript, audio_path, tag, client_name, company = call

            in_progress_str = trans.get("ui_in_progress", "IN PROGRESS")
            # The "in progress" badge reflects the call's real status stored in the tag column.
            if tag and tag.strip() == in_progress_str:
                prefix = in_progress_str
            else:
                prefix = "📞"
            
            caller_display = ""
            if client_name and company: caller_display = f" — {client_name} ({company})"
            elif client_name: caller_display = f" — {client_name}"
            elif company: caller_display = f" — {company}"
                
            tag_display = tag if tag and tag != in_progress_str else trans.get("ui_general_call", "GENERAL CALL")
            
            with st.expander(f"{prefix} {number}{caller_display} — {date} | {tag_display} (Risk: {spam_score}/100)"):
                st.write(f"**{trans.get('ui_transcript', 'Transcript:')}**")
                
                blocks_raw = [b.strip() for b in transcript.split("\n\n") if b.strip()]
                edit_key = f"edit_phrase_{id_call}"
                if edit_key not in st.session_state: st.session_state[edit_key] = None  

                for idx_b, block in enumerate(blocks_raw):
                    if not show_system_msg:
                        if any(marker in block for marker in ["[SYSTEM]", "[Active Hold]", "❌", "⏳", "⏸"]):
                            continue

                    is_user = block.startswith("🗣")
                    is_assistant = block.startswith("📞")

                    m_ts = re.match(r'^[🗣📞]\s*\[(\d{2}:\d{2}:\d{2})\]:\s*(.*)', block, re.DOTALL)
                    if m_ts:
                        ts_str = f"[{m_ts.group(1)}]"
                        pure_text = m_ts.group(2).strip()
                    else:
                        ts_str = ""
                        pure_text = block
                        for pref in ["🗣", "📞"]: pure_text = pure_text.replace(pref, "")
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
                            new_txt = st.text_input(f"Edit {prefix_md}", value=pure_text, key=f"edit_inp_{id_call}_{idx_b}", label_visibility="collapsed")
                        with col_ok:
                            if st.button("✅", key=f"ok_{id_call}_{idx_b}"):
                                emoji_orig = "🗣" if is_user else "📞"
                                blocks_raw[idx_b] = f"{emoji_orig} {ts_str}: {new_txt}" if ts_str else f"{emoji_orig}: {new_txt}"
                                new_trans = "\n\n".join(blocks_raw)
                                conn2 = sqlite3.connect(DB_PATH)
                                conn2.execute("UPDATE calls SET transcript=? WHERE id=?", (new_trans, id_call))
                                conn2.commit(); conn2.close()
                                st.session_state[edit_key] = None
                                st.toast(trans.get("ui_toast_phrase_updated", "Updated"))
                                st.rerun()
                        with col_cancel:
                            if st.button("✖", key=f"cancel_{id_call}_{idx_b}"):
                                st.session_state[edit_key] = None; st.rerun()
                    else:
                        col_txt, col_edit, col_del = st.columns([6, 0.55, 0.55])
                        with col_txt: st.markdown(f"{prefix_md} {pure_text}")
                        with col_edit:
                            if st.button("✏️", key=f"edit_btn_{id_call}_{idx_b}"):
                                st.session_state[edit_key] = idx_b; st.rerun()
                        with col_del:
                            del_confirm_key = f"del_confirm_{id_call}_{idx_b}"
                            if del_confirm_key not in st.session_state: st.session_state[del_confirm_key] = False
                            
                            if not st.session_state[del_confirm_key]:
                                if st.button("🗑️", key=f"del_phrase_{id_call}_{idx_b}"):
                                    st.session_state[del_confirm_key] = True; st.rerun()
                            else:
                                c_si, c_no = st.columns(2)
                                with c_si:
                                    if st.button("✓", key=f"del_yes_{id_call}_{idx_b}"):
                                        blocks_raw.pop(idx_b)
                                        new_trans = "\n\n".join(blocks_raw)
                                        conn2 = sqlite3.connect(DB_PATH)
                                        conn2.execute("UPDATE calls SET transcript=? WHERE id=?", (new_trans, id_call))
                                        conn2.commit(); conn2.close()
                                        st.session_state[del_confirm_key] = False
                                        st.toast(trans.get("ui_toast_phrase_deleted", "Deleted"))
                                        st.rerun()
                                with c_no:
                                    if st.button("X", key=f"del_no_{id_call}_{idx_b}"):
                                        st.session_state[del_confirm_key] = False; st.rerun()

                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f:
                            st.audio(f.read(), format="audio/wav")
                    except Exception:
                        pass
                
                st.write("---")
                c_edit1, c_edit2 = st.columns([2, 2])
                with c_edit1:
                    tag_options = trans.get("tags", ["GENERAL CALL"])
                    tag_current_val = tag_display if tag_display in tag_options else tag_options[-1]
                    
                    new_tag = st.selectbox(trans.get("ui_tag_label", "Classification:"), tag_options, index=tag_options.index(tag_current_val), key=f"tag_{id_call}")
                    if new_tag != tag_current_val:
                        set_config_local = sqlite3.connect(DB_PATH)
                        set_config_local.execute("UPDATE calls SET tag=? WHERE id=?", (new_tag, id_call))
                        set_config_local.commit(); set_config_local.close()
                        st.toast(trans.get("ui_toast_tag_updated", "Tag updated"))
                        st.rerun()
                        
                with c_edit2:
                    corr_name = st.text_input(trans.get("ui_caller_name", "Caller Name:"), value=client_name or "", key=f"name_{id_call}")
                    corr_company = st.text_input(trans.get("ui_company", "Company:"), value=company or "", key=f"comp_{id_call}")
                    if corr_name != (client_name or "") or corr_company != (company or ""):
                        set_config_local = sqlite3.connect(DB_PATH)
                        set_config_local.execute("UPDATE calls SET client_name=?, company=? WHERE id=?", (corr_name, corr_company, id_call))
                        set_config_local.commit(); set_config_local.close()
                        st.toast(trans.get("ui_toast_caller_updated", "Caller data updated"))
                        st.rerun()
                
                st.write("") 
                c_act1, c_act2, c_act3, c_act4 = st.columns(4)
                with c_act1:
                    if audio_path and os.path.exists(audio_path):
                        if st.button(trans.get("ui_btn_delete_audio", "Delete Audio"), key=f"delaud_{id_call}"):
                            try: os.remove(audio_path)
                            except: pass
                            conn_loc = sqlite3.connect(DB_PATH)
                            conn_loc.execute("UPDATE calls SET audio_path='' WHERE id=?", (id_call,))
                            conn_loc.commit(); conn_loc.close()
                            st.toast(trans.get("ui_toast_audio_deleted", "Audio deleted"))
                            st.rerun()
                with c_act2:
                    if st.button(trans.get("ui_btn_delete_record", "Delete Record"), key=f"delreg_{id_call}"):
                        if audio_path and os.path.exists(audio_path):
                            try: os.remove(audio_path)
                            except: pass
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute("DELETE FROM calls WHERE id=?", (id_call,))
                        conn_loc.commit(); conn_loc.close()
                        st.toast(trans.get("ui_toast_record_deleted", "Record deleted"))
                        st.rerun()
                with c_act3:
                    if st.button(trans.get("ui_btn_whitelist", "Whitelist"), key=f"wht_{id_call}"):
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute("INSERT OR REPLACE INTO contacts VALUES (?, 'whitelist', '')", (number,))
                        conn_loc.commit(); conn_loc.close()
                        st.toast(trans.get("ui_toast_saved", "Saved successfully"))
                        st.rerun()
                with c_act4:
                    if st.button(trans.get("ui_btn_blacklist", "Blacklist"), key=f"blk_{id_call}"):
                        conn_loc = sqlite3.connect(DB_PATH)
                        conn_loc.execute("INSERT OR REPLACE INTO contacts VALUES (?, 'blacklist', '')", (number,))
                        conn_loc.commit(); conn_loc.close()
                        st.toast(trans.get("ui_toast_saved", "Saved successfully"))
                        st.rerun()
    else:
        st.info(trans.get("ui_no_calls", "No calls recorded yet."))

with col2:
    st.subheader(trans.get("filters_title", "Filters & Prompts"))
    with st.form("new_contact"):
        phone_num = st.text_input(trans.get("ui_form_phone", "Phone Number:"))
        contact_type = st.selectbox(trans.get("ui_form_category", "Category:"), ["whitelist", "blacklist"])
        prompt_rules = st.text_area(trans.get("ui_form_prompt", "Custom Instructions:"))
        submit = st.form_submit_button(trans.get("ui_form_save_rule", "Save Rule"))
        
        if submit and phone_num:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO contacts VALUES (?, ?, ?)", (phone_num, contact_type, prompt_rules))
            conn.commit(); conn.close()
            st.success(trans.get("ui_toast_saved", "Saved successfully"))
            st.rerun()

    st.write(f"**{trans.get('ui_managed_contacts', 'Managed contacts:')}**")
    conn = sqlite3.connect(DB_PATH)
    contacts = conn.execute("SELECT number, type, prompt_rules FROM contacts").fetchall()
    conn.close()
    for c in contacts:
        prompt_preview = f" ('{c[2][:20]}...')" if c[2] else ""
        st.text(f"• {c[0]} -> [{c[1].upper()}]{prompt_preview}")

with col3:
    st.subheader(trans.get("settings_title", "Settings"))
    
    if "pending_lang" not in st.session_state: st.session_state.pending_lang = None
    selected_lang = st.selectbox(trans.get("language_label", "System Language:"), available_langs, index=available_langs.index(current_lang))
    
    if selected_lang != current_lang and st.session_state.pending_lang != selected_lang:
        st.session_state.pending_lang = selected_lang
        st.rerun()

    if st.session_state.pending_lang:
        confirm_language_dialog()

    st.write("---")
    
    # Auto-Cleanup logic properly styled and isolated in the settings column
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
                                try: os.remove(fpath); deleted_audio += 1
                                except Exception: pass
                # Also clear audio_path in DB for removed files
                conn_cl = sqlite3.connect(DB_PATH)
                all_audio = conn_cl.execute("SELECT id, audio_path, client_audio_path FROM calls").fetchall()
                for row in all_audio:
                    aid, ap, cap = row
                    if ap and not os.path.exists(ap):
                        conn_cl.execute("UPDATE calls SET audio_path='' WHERE id=?", (aid,))
                    if cap and not os.path.exists(cap):
                        conn_cl.execute("UPDATE calls SET client_audio_path='' WHERE id=?", (aid,))
                conn_cl.commit(); conn_cl.close()
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
                    (cutoff_rec.strftime('%Y-%m-%d %H:%M:%S'),)
                ).fetchall()
                deleted_recs = 0
                for row in old_rows:
                    rid, ap, cap = row
                    for fpath in [ap, cap]:
                        if fpath and os.path.exists(fpath):
                            try: os.remove(fpath)
                            except Exception: pass
                    conn_cl.execute("DELETE FROM calls WHERE id=?", (rid,))
                    deleted_recs += 1
                conn_cl.commit(); conn_cl.close()
                st.toast(trans.get("ui_cleanup_records_done", "Records deleted: {count}").format(count=deleted_recs))
                st.rerun()

    st.write("---")
    current_wait = int(get_config("wait_seconds", "0"))
    wait_slider = st.slider(trans.get("wait_seconds_label", "Wait before answer:"), min_value=0, max_value=15, value=current_wait)
    if wait_slider != current_wait: set_config("wait_seconds", wait_slider)

    st.write("---")
    st.subheader(trans.get("ui_spam_title", "Network SPAM Protection"))
    current_spam = get_config("auto_block_spam", "true") == "true"
    block_spam_chk = st.checkbox(trans.get("auto_block_spam_label", "Auto hang up Spam"), value=current_spam)
    if block_spam_chk != current_spam: set_config("auto_block_spam", "true" if block_spam_chk else "false")
    
    spam_providers_json = get_config("spam_providers", "")
    if not spam_providers_json:
        spam_data = load_language_data(current_lang, "spam.json")
        spam_urls_list = spam_data.get("providers", [])
    else:
        try:
            spam_urls_list = json.loads(spam_providers_json)
        except:
            spam_urls_list = []
    
    st.caption(trans.get("ui_spam_providers_desc", "Add one URL per line. Use {number} where the phone goes."))
    current_spam_text = "\n".join(spam_urls_list)
    new_spam_text = st.text_area(trans.get("ui_spam_providers_label", "SPAM URLs:"), value=current_spam_text, label_visibility="collapsed")
    
    if new_spam_text != current_spam_text:
        new_list = [url.strip() for url in new_spam_text.split("\n") if url.strip()]
        set_config("spam_providers", json.dumps(new_list, ensure_ascii=False))

    st.write("---")
    st.subheader(trans.get("priority_keywords_title", "Priority Keywords"))
    current_kw = get_config("priority_keywords", "")
    new_kw = st.text_area(trans.get("priority_keywords_desc", "Keywords:"), value=current_kw)
    if new_kw != current_kw: set_config("priority_keywords", new_kw)

    st.write("---")
    st.subheader(trans.get("transcription_mode_title", "Transcription Mode"))
    
    current_model = get_config("text_model", "gemini-3-flash-preview")
    model_opts = trans.get("text_model_opts", ["gemini-3-flash-preview", "gemma-4-31b-it", "gemma-4-26b-a4b-it"])
    idx_model = model_opts.index(current_model) if current_model in model_opts else 0
    new_model = st.selectbox(trans.get("ui_text_model_label", "Text Model:"), model_opts, index=idx_model)
    if new_model != current_model:
        set_config("text_model", new_model)
        if "gemma" in new_model.lower():
            if get_config("final_transcription_mode", "realtime") == "gemini_final":
                set_config("final_transcription_mode", "realtime")
        st.rerun()

    trans_mode_opts_all = ["realtime", "disabled", "whisper_final", "gemini_final"]
    if "gemma" in current_model.lower():
        trans_mode_opts = ["realtime", "disabled", "whisper_final"]
    else:
        trans_mode_opts = trans_mode_opts_all
        
    trans_mode_labels = trans.get("trans_mode_opts_labels", {
        "realtime": "Real-time", "disabled": "Disabled", "whisper_final": "Whisper at end", "gemini_final": "Gemini at end"
    })
    
    current_trans_mode = get_config("final_transcription_mode", "realtime")
    if current_trans_mode not in trans_mode_opts:
        current_trans_mode = "realtime"
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

    st.write("---")
    st.subheader(trans.get("monitor_mode_title", "PC Speaker Monitoring"))
    monitor_mode_opts = ["both", "none", "caller", "assistant"]
    monitor_mode_labels = trans.get("monitor_mode_opts_labels", {
        "both": "Both", "none": "None", "caller": "Caller", "assistant": "Assistant"
    })
    current_monitor_mode = get_config("monitor_mode", "both")
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

    st.write("---")
    st.subheader(trans.get("whisper_model_label", "Whisper Local Model (GGML)"))
    w_model_opts = ["base", "base.en", "small", "small.en", "medium", "medium.en", "large-v2", "large-v3", "large-v3-turbo"]
    w_quant_opts = {"": "default (fp16)", "-q4_0": "q4_0", "-q8_0": "q8_0"}
    
    col_wm, col_wq = st.columns(2)
    with col_wm:
        current_w_model = get_config("whisper_model", "medium")
        new_w_model = st.selectbox(trans.get("ui_whisper_base", "Model Base:"), w_model_opts, index=w_model_opts.index(current_w_model) if current_w_model in w_model_opts else 4)
        if new_w_model != current_w_model: set_config("whisper_model", new_w_model); st.rerun()
            
    with col_wq:
        current_w_quant = get_config("whisper_quant", "")
        quant_keys = list(w_quant_opts.keys())
        new_w_quant = st.selectbox(trans.get("ui_whisper_quant", "Quantization:"), quant_keys, format_func=lambda x: w_quant_opts[x], index=quant_keys.index(current_w_quant) if current_w_quant in quant_keys else 0)
        if new_w_quant != current_w_quant: set_config("whisper_quant", new_w_quant); st.rerun()

    st.write("---")
    st.subheader(trans.get("audio_mode_title", "🔊 Audio Mode (Full Duplex / Half Duplex)"))
    current_echo = get_config("software_echo_suppression", "true") == "true"
    new_echo_chk = st.checkbox(trans.get("software_echo_label", "Enable Software Echo Suppression (Recommended if feedback occurs)"), value=current_echo)
    if new_echo_chk != current_echo: 
        set_config("software_echo_suppression", "true" if new_echo_chk else "false")
        st.rerun()

    st.write("---")
    st.subheader(trans.get("owner_settings_title", "Owner"))
    current_boss_name = get_config("boss_name", "")
    new_boss_name = st.text_input(trans.get("owner_name_label", "Boss Name:"), value=current_boss_name)
    if new_boss_name != current_boss_name: set_config("boss_name", new_boss_name.strip())
        
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
    if new_desc != current_desc: set_config("business_description", new_desc.strip())
        
    current_calls = get_config("expected_calls", "")
    new_calls = st.text_area(trans.get("expected_calls_label", "Expected calls:"), value=current_calls)
    if new_calls != current_calls: set_config("expected_calls", new_calls.strip())

    st.write("---")
    st.subheader(trans.get("identity_title", "Identity"))
    assistant_name_val = st.text_input(trans.get("assistant_name_label", "Name:"), value=current_assistant_name)
    if assistant_name_val != current_assistant_name: set_config("assistant_name", assistant_name_val.strip()); st.rerun()
        
    current_gender = get_config("assistant_gender", "female")
    gender_opts = trans.get("gender_types", ["female", "male"])
    idx_gender = gender_opts.index(current_gender) if current_gender in gender_opts else 0
    new_gender = st.selectbox(trans.get("assistant_gender_label", "Voice:"), gender_opts, index=idx_gender)
    if new_gender != current_gender: set_config("assistant_gender", new_gender); st.rerun()
    
    current_greeting = get_config("initial_greeting", "")
    new_greeting = st.text_area(trans.get("ui_initial_greeting", "Exact Initial Greeting:"), value=current_greeting)
    if new_greeting != current_greeting: set_config("initial_greeting", new_greeting.strip())

    current_extra = get_config("extra_prompt", "")
    new_extra = st.text_area(trans.get("ui_extra_prompt", "Personality & Extra Instructions:"), value=current_extra)
    if new_extra != current_extra: set_config("extra_prompt", new_extra.strip())

    st.write("---")
    st.subheader(trans.get("memory_title", "Category Memory"))
    rules_json = get_config("memory_rules", "[]")
    try:
        rules = json.loads(rules_json)
    except:
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

    if st.button(trans.get("save_memory_btn", "Save Config")):
        set_config("memory_rules", json.dumps(rules, ensure_ascii=False))
        st.success(trans.get("ui_toast_saved", "Saved successfully"))
