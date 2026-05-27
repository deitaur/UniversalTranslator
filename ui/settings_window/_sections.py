"""Section-builder functions for the Settings window.

Each builder takes the SettingsWindow instance `win` (so it can stash
widget references onto it for use by `_save`) and the parent `layout`.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QRadioButton,
)

from config import C, config
from utils.language import LANGUAGES
from win32.hotkeys import DEFAULT_HOTKEYS

from ui.settings_window._widgets import (
    _F_LABEL, _F_MONO, _SS_CHECK, _Section,
    _btn, _combo, _input, _lbl, _row,
)


# ── Translation Engine ────────────────────────────────────────────────────────

def build_engine_section(win, lo):
    s = _Section("Translation Engine", expanded=True)
    lo.addWidget(s)
    win._engine_group = QButtonGroup(win)
    for ev, el, ec in [("deepl", "DeepL", C["accent"]),
                       ("google", "Google (free)", C["green"]),
                       ("yandex", "Yandex (free)", C["yellow"])]:
        rb = QRadioButton(el)
        rb.setFont(_F_LABEL)
        rb.setChecked(ev == win._current_engine)
        rb.setStyleSheet(
            f"QRadioButton {{ color: {C['text']}; background: transparent; }}"
            f"QRadioButton::indicator:checked {{ background: {ec};"
            f" border: 2px solid {ec}; border-radius: 5px; }}"
        )
        rb.toggled.connect(lambda checked, v=ev: checked and win._on_engine(v))
        win._engine_group.addButton(rb)
        s.add(rb)


# ── Languages ─────────────────────────────────────────────────────────────────

def build_languages_section(win, lo):
    _code_to_name = {code: name for code, name in LANGUAGES.items()}
    _name_to_code = {name: code for code, name in LANGUAGES.items()}
    _lang_names   = list(LANGUAGES.values())
    win._name_to_code = _name_to_code

    s = _Section("Languages", expanded=True)
    lo.addWidget(s)
    s.add(_lbl("Source (your language):"))
    win._src_combo = _combo(_lang_names,
                            _code_to_name.get(config.get("source_lang", "ru"), "Russian"))
    s.add(win._src_combo)
    s.add_spacing(2)
    s.add(_lbl("Target (translate to):"))
    _SAME = "(Same as source)"
    win._tgt_combo = _combo([_SAME] + _lang_names)
    tgt_code = config.get("target_lang", "")
    win._tgt_combo.setCurrentText(_code_to_name.get(tgt_code, _SAME) if tgt_code else _SAME)
    s.add(win._tgt_combo)


# ── API Keys ──────────────────────────────────────────────────────────────────

def build_api_keys_section(win, lo):
    s = _Section("API Keys")
    lo.addWidget(s)
    s.add(_lbl("DeepL API Key:"))
    win._deepl_key = _input(config.get("api_key", ""), "Enter DeepL key…", mono=True, pw=True)
    s.add(win._deepl_key)
    s.add(_lbl("Yandex API Key:"))
    win._yandex_key = _input(config.get("yandex_api_key", ""), "Enter Yandex key…", mono=True, pw=True)
    s.add(win._yandex_key)
    s.add(_lbl("Yandex Folder ID:"))
    win._yandex_folder = _input(config.get("yandex_folder_id", ""), "Folder ID…", mono=True)
    s.add(win._yandex_folder)


# ── Mobile Bridge ─────────────────────────────────────────────────────────────

def build_bridge_section(win, lo):
    s = _Section("Mobile Bridge")
    lo.addWidget(s)
    s.add(_lbl("Connect the phone app over WiFi / Tailscale VPN.", color=C["muted"]))
    s.add_spacing(2)

    win._bridge_cb = QCheckBox("Enable Mobile Bridge")
    win._bridge_cb.setFont(_F_LABEL)
    win._bridge_cb.setChecked(config.get("bridge_enabled", False))
    win._bridge_cb.setStyleSheet(_SS_CHECK)
    s.add(win._bridge_cb)

    port_row = QHBoxLayout()
    port_row.setContentsMargins(0, 0, 0, 0)
    port_row.setSpacing(4)
    port_row.addWidget(_lbl("Port:"))
    win._bridge_port = _input(str(config.get("bridge_port", 8082)), mono=True)
    win._bridge_port.setFixedWidth(70)
    port_row.addWidget(win._bridge_port)
    port_row.addStretch()
    s.add_layout(port_row)

    tok_row = QHBoxLayout()
    tok_row.setContentsMargins(0, 0, 0, 0)
    tok_row.setSpacing(4)
    tok_row.addWidget(_lbl("Token:"))
    from services.bridge.auth import get_or_create_token
    tok = get_or_create_token()
    win._bridge_tok_lbl = QLabel(tok[:18] + "…")
    win._bridge_tok_lbl.setFont(_F_MONO)
    win._bridge_tok_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent; border: none;")
    tok_row.addWidget(win._bridge_tok_lbl, 1)
    copy_tok_btn = _btn("Copy", height=20)
    copy_tok_btn.setFixedWidth(46)
    copy_tok_btn.clicked.connect(lambda: win._copy_token(tok))
    tok_row.addWidget(copy_tok_btn)
    s.add_layout(tok_row)

    ip_row = QHBoxLayout()
    ip_row.setContentsMargins(0, 0, 0, 0)
    ip_row.setSpacing(4)
    ip_row.addWidget(_lbl("PC IP:"))
    win._ip_combo = _combo(win._get_all_ips())
    win._ip_combo.setFont(_F_MONO)
    win._ip_combo.currentTextChanged.connect(lambda _: win._refresh_qr())
    ip_row.addWidget(win._ip_combo, 1)
    s.add_layout(ip_row)

    win._qr_lbl = QLabel()
    win._qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win._qr_lbl.setFixedHeight(120)
    win._qr_lbl.setStyleSheet(
        f"background: {C['card_alt']}; border-radius: 4px; color: {C['muted']};"
    )
    s.add(win._qr_lbl)

    qr_btn = _btn("Refresh QR", C["accent"], C["bg"], height=22)
    qr_btn.clicked.connect(win._refresh_qr)
    s.add(qr_btn)

    win._refresh_qr()


# ── AI / Ollama ───────────────────────────────────────────────────────────────

def build_ai_ollama_section(win, lo):
    from services.ai.ollama import _running_models, get_ollama_model, get_polish_model

    s = _Section("AI / Ollama")
    lo.addWidget(s)
    _running = _running_models()
    _running_str = ", ".join(_running) if _running else "none loaded"
    s.add(_lbl(f"Currently in RAM:  {_running_str}", C["muted"]))
    s.add_spacing(4)

    s.add(_lbl("Chat / Voice Chat model:"))
    win._ollama_chat_entry = _input(
        config.get("ollama_model_chat", ""),
        placeholder=f"auto  [{get_ollama_model()}]",
        mono=True,
    )
    win._ollama_chat_entry.setToolTip(
        "Model for chat, voice chat and web search.\n"
        "Leave blank to auto-use whatever is loaded in Ollama RAM.\n"
        "Recommended: qwen2.5:14b  (fast, good tool calling)"
    )
    s.add(win._ollama_chat_entry)
    s.add_spacing(2)

    s.add(_lbl("Polish / Format model:"))
    win._ollama_polish_entry = _input(
        config.get("ollama_model_polish", ""),
        placeholder=f"auto  [{get_polish_model()}]",
        mono=True,
    )
    win._ollama_polish_entry.setToolTip(
        "Model for the voice-dictation editing actions (Ctrl+Alt+W).\n"
        "Used by 'Глубокая редактура' and 'Оформить как список дел'.\n"
        "Leave blank to auto-use whatever is loaded in Ollama RAM.\n"
        "Recommended: gemma4:26b  (best writing quality)"
    )
    s.add(win._ollama_polish_entry)

    # legacy single-model field kept for bridge/diagnose compat
    win._ollama_entry = win._ollama_chat_entry
    s.add(_lbl("Response language:"))
    win._neg_lang_combo = _combo(["Same as input", "English", "Russian"],
                                  config.get("negotiator_lang", "Same as input"))
    s.add(win._neg_lang_combo)
    s.add_spacing(2)
    roles_btn = _btn("Manage Roles…", height=22)
    roles_btn.clicked.connect(win._open_role_editor)
    win._load_btn = _btn("Load into RAM", height=22)
    win._load_btn.clicked.connect(win._on_load_ai)
    s.add_layout(_row(roles_btn, win._load_btn))


# ── Voice & TTS ───────────────────────────────────────────────────────────────

def build_voice_tts_section(win, lo):
    from services.ai.tts import gtts_installed

    s = _Section("Voice & TTS")
    lo.addWidget(s)
    _gtts_ok = gtts_installed()
    _tts_opts = ["Google (gTTS)" if _gtts_ok else "Google (pip install gtts)", "Windows SAPI"]
    win._tts_stored = {
        "Google (gTTS)": "gtts",
        "Google (pip install gtts)": "gtts",
        "Windows SAPI": "sapi",
    }
    _tts_display = {
        "gtts": "Google (gTTS)" if _gtts_ok else "Google (pip install gtts)",
        "sapi": "Windows SAPI",
    }
    tts_row = QHBoxLayout()
    tts_row.setContentsMargins(0, 0, 0, 0)
    tts_row.setSpacing(4)
    tts_row.addWidget(_lbl("Engine:"))
    win._tts_combo = _combo(_tts_opts,
                             _tts_display.get(config.get("tts_engine", "gtts"), "Google (gTTS)"))
    if not _gtts_ok:
        win._tts_combo.setEnabled(False)
    tts_row.addWidget(win._tts_combo, 1)
    win._tts_test_btn = _btn("▶ Test", height=22)
    win._tts_test_btn.setFixedWidth(52)
    win._tts_test_btn.clicked.connect(win._test_tts)
    tts_row.addWidget(win._tts_test_btn)
    s.add_layout(tts_row)


# ── Dictation ─────────────────────────────────────────────────────────────────

def build_dictation_section(win, lo):
    s = _Section("Dictation  (Ctrl+Alt+D)")
    lo.addWidget(s)
    s.add(_lbl("Save folder:"))
    _default = str(Path.home() / "Documents" / "Dictations")
    folder_row = QHBoxLayout()
    folder_row.setContentsMargins(0, 0, 0, 0)
    folder_row.setSpacing(4)
    win._dict_folder = _input(config.get("dictation_folder", _default))
    folder_row.addWidget(win._dict_folder, 1)
    browse_btn = _btn("…", height=22)
    browse_btn.setFixedWidth(26)
    browse_btn.clicked.connect(win._browse_folder)
    folder_row.addWidget(browse_btn)
    s.add_layout(folder_row)

    fmt_row = QHBoxLayout()
    fmt_row.setContentsMargins(0, 0, 0, 0)
    fmt_row.setSpacing(6)
    fmt_row.addWidget(_lbl("Format:"))
    _fmt_display = {"md": "Markdown (.md)", "txt": "Text (.txt)"}
    win._fmt_stored = {"Markdown (.md)": "md", "Text (.txt)": "txt"}
    win._fmt_combo = _combo(["Markdown (.md)", "Text (.txt)"],
                             _fmt_display.get(config.get("dictation_format", "md"), "Markdown (.md)"))
    fmt_row.addWidget(win._fmt_combo)
    win._obsidian_cb = QCheckBox("Obsidian frontmatter")
    win._obsidian_cb.setFont(_F_LABEL)
    win._obsidian_cb.setChecked(config.get("dictation_obsidian", True))
    win._obsidian_cb.setStyleSheet(_SS_CHECK)
    fmt_row.addWidget(win._obsidian_cb)
    fmt_row.addStretch()
    s.add_layout(fmt_row)

    tags_row = QHBoxLayout()
    tags_row.setContentsMargins(0, 0, 0, 0)
    tags_row.setSpacing(6)
    tags_row.addWidget(_lbl("Tags:"))
    win._tags_entry = _input(config.get("dictation_tags", "dictation"), "dictation, notes")
    tags_row.addWidget(win._tags_entry, 1)
    s.add_layout(tags_row)


# ── Voice Polish ──────────────────────────────────────────────────────────────

def build_polish_section(win, lo):
    from services.ai.ollama import get_polish_model

    s = _Section("Voice editing  (Ctrl+Alt+W)")
    lo.addWidget(s)
    win._format_cb = QCheckBox("AI format output  (structure text like a professional editor)")
    win._format_cb.setFont(_F_LABEL)
    win._format_cb.setChecked(config.get("format_output", True))
    win._format_cb.setStyleSheet(_SS_CHECK)
    s.add(win._format_cb)

    _full   = get_polish_model(format_mode=True)
    _light  = get_polish_model(format_mode=False)
    s.add(_lbl(
        f"  ☑ on  →  full reformat   [{_full}]   headings, lists, paragraphs\n"
        f"  ☐ off →  minimal polish  [{_light}]   just filler-word removal + punctuation",
        C["muted"]
    ))


# ── Hotkeys ───────────────────────────────────────────────────────────────────

_HOTKEY_ROWS = [
    ("popup",      "Show Popup"),
    ("replace",    "Replace Text"),
    ("clipboard",  "Translate Clipboard"),
    ("whisper",    "Voice → Text"),
    ("dictation",  "Voice Dictation"),
    ("voicechat",  "Voice AI Chat"),
    ("negotiator", "Negotiator"),
    ("teacher",    "English Teacher"),
]


def build_hotkeys_section(win, lo):
    s = _Section("Hotkeys")
    lo.addWidget(s)
    win._hotkey_entries = {}
    for name, label in _HOTKEY_ROWS:
        hk_row = QHBoxLayout()
        hk_row.setContentsMargins(0, 0, 0, 0)
        hk_row.setSpacing(4)
        lbl_w = QLabel(label)
        lbl_w.setFont(_F_LABEL)
        lbl_w.setFixedWidth(130)
        lbl_w.setStyleSheet(f"color: {C['subtext']}; background: transparent; border: none;")
        hk_row.addWidget(lbl_w)
        entry = _input(config.get(f"hotkey_{name}", DEFAULT_HOTKEYS.get(name, "")),
                       "Ctrl+Alt+…", mono=True)
        hk_row.addWidget(entry, 1)
        s.add_layout(hk_row)
        win._hotkey_entries[name] = entry


# ── System ────────────────────────────────────────────────────────────────────

def build_system_section(win, lo):
    s = _Section("System")
    lo.addWidget(s)
    win._autostart_cb = QCheckBox("Start with Windows")
    win._autostart_cb.setFont(_F_LABEL)
    win._autostart_cb.setChecked(config.get("autostart", False))
    win._autostart_cb.setStyleSheet(_SS_CHECK)
    s.add(win._autostart_cb)

    win._clipboard_cb = QCheckBox("Clipboard-only mode (no text selection)")
    win._clipboard_cb.setFont(_F_LABEL)
    win._clipboard_cb.setChecked(config.get("clipboard_only", False))
    win._clipboard_cb.setStyleSheet(_SS_CHECK)
    s.add(win._clipboard_cb)

    win._direct_cb = QCheckBox("Direct type replacement (no clipboard)")
    win._direct_cb.setFont(_F_LABEL)
    win._direct_cb.setChecked(config.get("direct_type", False))
    win._direct_cb.setStyleSheet(_SS_CHECK)
    s.add(win._direct_cb)

    s.add_spacing(8)
    win._remote_mode_cb = QCheckBox("Remote session mode  (AnyDesk/TeamViewer)")
    win._remote_mode_cb.setFont(_F_LABEL)
    win._remote_mode_cb.setChecked(config.get("remote_session_mode", False))
    win._remote_mode_cb.setStyleSheet(_SS_CHECK)
    s.add(win._remote_mode_cb)
    hint = _lbl("When enabled: results go to clipboard only, no auto-paste via Ctrl+V", C["muted"])
    s.add(hint)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def build_all_sections(win, lo):
    """Call every section builder in display order."""
    build_engine_section(win, lo)
    build_languages_section(win, lo)
    build_api_keys_section(win, lo)
    build_bridge_section(win, lo)
    build_ai_ollama_section(win, lo)
    build_voice_tts_section(win, lo)
    build_dictation_section(win, lo)
    build_polish_section(win, lo)
    build_hotkeys_section(win, lo)
    build_system_section(win, lo)
