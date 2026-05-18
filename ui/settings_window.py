"""Settings window — ZBrush-style compact collapsible layout."""

import datetime as _dt
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from config import APP_NAME, APP_VERSION, ICON_FILE, C, config, save_config_full
from utils.language import LANGUAGES
from win32.hotkeys import DEFAULT_HOTKEYS, parse_hotkey_string


# ── Style constants ────────────────────────────────────────────────────────────

_F_LABEL  = QFont("Segoe UI", 9)
_F_INPUT  = QFont("Consolas", 9)
_F_HDR    = QFont("Segoe UI Semibold", 9)
_F_MONO   = QFont("Consolas", 8)

_SS_INPUT = (
    f"QLineEdit {{ background: {C['card_alt']}; color: {C['text']};"
    f" border: 1px solid {C['border']}; border-radius: 3px;"
    f" padding: 1px 5px; min-height: 20px; }}"
)
_SS_COMBO = (
    f"QComboBox {{ background: {C['card_alt']}; color: {C['text']};"
    f" border: 1px solid {C['border']}; border-radius: 3px;"
    f" padding: 1px 5px; min-height: 20px; }}"
    f"QComboBox::drop-down {{ border: none; }}"
    f"QComboBox QAbstractItemView {{ background: {C['card']}; color: {C['text']}; }}"
)
_SS_CHECK = (
    f"QCheckBox {{ color: {C['text']}; background: transparent; font-size: 9px; }}"
)
_SS_RADIO = (
    f"QRadioButton {{ color: {C['text']}; background: transparent; font-size: 9px; }}"
)


# ── Collapsible Section ────────────────────────────────────────────────────────

class _Section(QWidget):
    """ZBrush-style collapsible section with ▸/▾ header button."""

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header button
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setFixedHeight(22)
        self._btn.setFont(_F_HDR)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {C['surface']}; color: {C['text']};"
            f" border: none; border-top: 1px solid {C['border']};"
            f" text-align: left; padding-left: 8px; }}"
            f"QPushButton:hover {{ background: {C['card']}; }}"
        )
        self._set_title(title, expanded)
        self._btn.toggled.connect(self._toggle)
        outer.addWidget(self._btn)

        # Body
        self._body = QWidget()
        self._body.setStyleSheet(
            f"background: {C['bg']};"
            f"QLabel {{ background: transparent; border: none; color: {C['text']}; }}"
        )
        self._body_lo = QVBoxLayout(self._body)
        self._body_lo.setContentsMargins(10, 4, 8, 6)
        self._body_lo.setSpacing(3)
        self._body.setVisible(expanded)
        outer.addWidget(self._body)

        self._title = title

    def _set_title(self, title: str, expanded: bool):
        arrow = "▾" if expanded else "▸"
        self._btn.setText(f"  {arrow}  {title}")

    def _toggle(self, checked: bool):
        self._body.setVisible(checked)
        self._set_title(self._title, checked)

    def add(self, widget: QWidget):
        self._body_lo.addWidget(widget)

    def add_layout(self, lo):
        self._body_lo.addLayout(lo)

    def add_spacing(self, n: int = 4):
        self._body_lo.addSpacing(n)


# ── Tiny helpers ───────────────────────────────────────────────────────────────

def _lbl(text: str, color: str = None, bold: bool = False) -> QLabel:
    w = QLabel(text)
    f = QFont("Segoe UI Semibold" if bold else "Segoe UI", 9)
    w.setFont(f)
    w.setStyleSheet(f"color: {color or C['subtext']}; background: transparent; border: none;")
    return w


def _input(text: str = "", placeholder: str = "", mono: bool = False, pw: bool = False) -> QLineEdit:
    w = QLineEdit(text)
    w.setFont(_F_INPUT if mono else _F_LABEL)
    if placeholder:
        w.setPlaceholderText(placeholder)
    if pw:
        w.setEchoMode(QLineEdit.EchoMode.Password)
    w.setStyleSheet(_SS_INPUT)
    w.setFixedHeight(22)
    return w


def _combo(items: list[str], current: str = "") -> QComboBox:
    w = QComboBox()
    w.setFont(_F_LABEL)
    w.addItems(items)
    if current:
        w.setCurrentText(current)
    w.setStyleSheet(_SS_COMBO)
    w.setFixedHeight(22)
    return w


def _btn(text: str, bg: str = None, fg: str = None, height: int = 22) -> QPushButton:
    b = QPushButton(text)
    b.setFont(_F_LABEL)
    b.setFixedHeight(height)
    _bg = bg or C["card_alt"]
    _fg = fg or C["text"]
    b.setStyleSheet(
        f"QPushButton {{ background: {_bg}; color: {_fg}; border: 1px solid {C['border']};"
        f" border-radius: 3px; padding: 0 8px; }}"
        f"QPushButton:hover {{ background: {C['surface']}; }}"
        f"QPushButton:disabled {{ color: {C['muted']}; }}"
    )
    return b


def _row(*widgets, stretch: bool = True) -> QHBoxLayout:
    lo = QHBoxLayout()
    lo.setContentsMargins(0, 0, 0, 0)
    lo.setSpacing(4)
    for w in widgets:
        if isinstance(w, int):
            lo.addSpacing(w)
        elif isinstance(w, QWidget):
            lo.addWidget(w)
        else:
            lo.addLayout(w)
    if stretch:
        lo.addStretch()
    return lo


# ── Main window ────────────────────────────────────────────────────────────────

class SettingsWindow(QWidget):

    _ai_load_sig = Signal(bool)

    def __init__(self, current_engine: str, update_tray_icon, rebuild_menu):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._current_engine = current_engine
        self._update_tray    = update_tray_icon
        self._rebuild_menu   = rebuild_menu

        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.resize(460, 580)
        self.setMinimumSize(380, 420)
        self.setStyleSheet(
            f"QWidget {{ background: {C['bg']}; color: {C['text']}; }}"
            f"QScrollArea {{ border: none; }}"
        )
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._ai_load_sig.connect(self._on_ai_load_result)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Mini header
        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(f"background: {C['surface']}; border-bottom: 1px solid {C['border']};")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(10, 0, 10, 0)
        title_lbl = QLabel("Settings")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        title_lbl.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        hdr_lo.addWidget(title_lbl)
        hdr_lo.addStretch()
        try:
            src = sys.argv[0] if getattr(sys, "frozen", False) else __file__
            ts = _dt.datetime.fromtimestamp(os.path.getmtime(src)).strftime("%d %b %Y")
        except Exception:
            ts = ""
        ver_lbl = QLabel(f"v{APP_VERSION}" + (f"  {ts}" if ts else ""))
        ver_lbl.setFont(QFont("Segoe UI", 8))
        ver_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent; border: none;")
        hdr_lo.addWidget(ver_lbl)
        root.addWidget(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet(f"background: {C['bg']};")
        inner_lo = QVBoxLayout(inner)
        inner_lo.setContentsMargins(0, 0, 0, 0)
        inner_lo.setSpacing(0)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setFont(QFont("Segoe UI Semibold", 10))
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {C['accent']}; color: {C['bg']}; border: none; }}"
            f"QPushButton:hover {{ background: #7ba4e8; }}"
        )
        self._save_btn.clicked.connect(self._save)
        root.addWidget(self._save_btn)

        self._build_sections(inner_lo)
        inner_lo.addStretch()

    def _build_sections(self, lo: QVBoxLayout):
        _code_to_name = {code: name for code, name in LANGUAGES.items()}
        _name_to_code = {name: code for code, name in LANGUAGES.items()}
        _lang_names   = list(LANGUAGES.values())
        self._name_to_code = _name_to_code

        # ── Translation Engine ─────────────────────────────────────────────
        s = _Section("Translation Engine", expanded=True)
        lo.addWidget(s)
        self._engine_group = QButtonGroup(self)
        for ev, el, ec in [("deepl", "DeepL", C["accent"]),
                            ("google", "Google (free)", C["green"]),
                            ("yandex", "Yandex (free)", C["yellow"])]:
            rb = QRadioButton(el)
            rb.setFont(_F_LABEL)
            rb.setChecked(ev == self._current_engine)
            rb.setStyleSheet(
                f"QRadioButton {{ color: {C['text']}; background: transparent; }}"
                f"QRadioButton::indicator:checked {{ background: {ec};"
                f" border: 2px solid {ec}; border-radius: 5px; }}"
            )
            rb.toggled.connect(lambda checked, v=ev: checked and self._on_engine(v))
            self._engine_group.addButton(rb)
            s.add(rb)

        # ── Languages ─────────────────────────────────────────────────────
        s = _Section("Languages", expanded=True)
        lo.addWidget(s)
        s.add(_lbl("Source (your language):"))
        self._src_combo = _combo(_lang_names, _code_to_name.get(config.get("source_lang", "ru"), "Russian"))
        s.add(self._src_combo)
        s.add_spacing(2)
        s.add(_lbl("Target (translate to):"))
        _SAME = "(Same as source)"
        self._tgt_combo = _combo([_SAME] + _lang_names)
        tgt_code = config.get("target_lang", "")
        self._tgt_combo.setCurrentText(_code_to_name.get(tgt_code, _SAME) if tgt_code else _SAME)
        s.add(self._tgt_combo)

        # ── API Keys ───────────────────────────────────────────────────────
        s = _Section("API Keys")
        lo.addWidget(s)
        s.add(_lbl("DeepL API Key:"))
        self._deepl_key = _input(config.get("api_key", ""), "Enter DeepL key…", mono=True, pw=True)
        s.add(self._deepl_key)
        s.add(_lbl("Yandex API Key:"))
        self._yandex_key = _input(config.get("yandex_api_key", ""), "Enter Yandex key…", mono=True, pw=True)
        s.add(self._yandex_key)
        s.add(_lbl("Yandex Folder ID:"))
        self._yandex_folder = _input(config.get("yandex_folder_id", ""), "Folder ID…", mono=True)
        s.add(self._yandex_folder)

        # ── Mobile Bridge ─────────────────────────────────────────────────
        s = _Section("Mobile Bridge")
        lo.addWidget(s)
        s.add(_lbl("Connect the phone app over WiFi / Tailscale VPN.", color=C["muted"]))
        s.add_spacing(2)

        self._bridge_cb = QCheckBox("Enable Mobile Bridge")
        self._bridge_cb.setFont(_F_LABEL)
        self._bridge_cb.setChecked(config.get("bridge_enabled", False))
        self._bridge_cb.setStyleSheet(_SS_CHECK)
        s.add(self._bridge_cb)

        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.setSpacing(4)
        port_row.addWidget(_lbl("Port:"))
        self._bridge_port = _input(str(config.get("bridge_port", 8082)), mono=True)
        self._bridge_port.setFixedWidth(70)
        port_row.addWidget(self._bridge_port)
        port_row.addStretch()
        s.add_layout(port_row)

        tok_row = QHBoxLayout()
        tok_row.setContentsMargins(0, 0, 0, 0)
        tok_row.setSpacing(4)
        tok_row.addWidget(_lbl("Token:"))
        from services.bridge.auth import get_or_create_token
        tok = get_or_create_token()
        self._bridge_tok_lbl = QLabel(tok[:18] + "…")
        self._bridge_tok_lbl.setFont(_F_MONO)
        self._bridge_tok_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent; border: none;")
        tok_row.addWidget(self._bridge_tok_lbl, 1)
        copy_tok_btn = _btn("Copy", height=20)
        copy_tok_btn.setFixedWidth(46)
        copy_tok_btn.clicked.connect(lambda: self._copy_token(tok))
        tok_row.addWidget(copy_tok_btn)
        s.add_layout(tok_row)

        ip_row = QHBoxLayout()
        ip_row.setContentsMargins(0, 0, 0, 0)
        ip_row.setSpacing(4)
        ip_row.addWidget(_lbl("PC IP:"))
        self._ip_combo = _combo(self._get_all_ips())
        self._ip_combo.setFont(_F_MONO)
        self._ip_combo.currentTextChanged.connect(lambda _: self._refresh_qr())
        ip_row.addWidget(self._ip_combo, 1)
        s.add_layout(ip_row)

        self._qr_lbl = QLabel()
        self._qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_lbl.setFixedHeight(120)
        self._qr_lbl.setStyleSheet(
            f"background: {C['card_alt']}; border-radius: 4px; color: {C['muted']};"
        )
        s.add(self._qr_lbl)

        qr_btn = _btn("Refresh QR", C["accent"], C["bg"], height=22)
        qr_btn.clicked.connect(self._refresh_qr)
        s.add(qr_btn)

        self._refresh_qr()

        # ── AI / Ollama ────────────────────────────────────────────────────
        s = _Section("AI / Ollama")
        lo.addWidget(s)
        from services.ai.ollama import get_ollama_model, get_polish_model, _running_models
        _running = _running_models()
        _running_str = ", ".join(_running) if _running else "none loaded"
        s.add(_lbl(f"Currently in RAM:  {_running_str}", C["muted"]))
        s.add_spacing(4)

        s.add(_lbl("Chat / Voice Chat model:"))
        self._ollama_chat_entry = _input(
            config.get("ollama_model_chat", ""),
            placeholder=f"auto  [{get_ollama_model()}]",
            mono=True,
        )
        self._ollama_chat_entry.setToolTip(
            "Model for chat, voice chat and web search.\n"
            "Leave blank to auto-use whatever is loaded in Ollama RAM.\n"
            "Recommended: qwen2.5:14b  (fast, good tool calling)"
        )
        s.add(self._ollama_chat_entry)
        s.add_spacing(2)

        s.add(_lbl("Polish / Format model:"))
        self._ollama_polish_entry = _input(
            config.get("ollama_model_polish", ""),
            placeholder=f"auto  [{get_polish_model()}]",
            mono=True,
        )
        self._ollama_polish_entry.setToolTip(
            "Model for voice-polish (Ctrl+Alt+F) text editing.\n"
            "Leave blank to auto-use whatever is loaded in Ollama RAM.\n"
            "Recommended: gemma4:26b  (best writing quality)"
        )
        s.add(self._ollama_polish_entry)

        # legacy single-model field kept for bridge/diagnose compat
        self._ollama_entry = self._ollama_chat_entry
        s.add(_lbl("Response language:"))
        self._neg_lang_combo = _combo(["Same as input", "English", "Russian"],
                                      config.get("negotiator_lang", "Same as input"))
        s.add(self._neg_lang_combo)
        s.add_spacing(2)
        roles_btn = _btn("Manage Roles…", height=22)
        roles_btn.clicked.connect(self._open_role_editor)
        self._load_btn = _btn("Load into RAM", height=22)
        self._load_btn.clicked.connect(self._on_load_ai)
        s.add_layout(_row(roles_btn, self._load_btn))

        # ── Voice & TTS ────────────────────────────────────────────────────
        s = _Section("Voice & TTS")
        lo.addWidget(s)
        from services.ai.tts import gtts_installed
        _gtts_ok = gtts_installed()
        _tts_opts = ["Google (gTTS)" if _gtts_ok else "Google (pip install gtts)", "Windows SAPI"]
        self._tts_stored = {
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
        self._tts_combo = _combo(_tts_opts, _tts_display.get(config.get("tts_engine", "gtts"), "Google (gTTS)"))
        if not _gtts_ok:
            self._tts_combo.setEnabled(False)
        tts_row.addWidget(self._tts_combo, 1)
        self._tts_test_btn = _btn("▶ Test", height=22)
        self._tts_test_btn.setFixedWidth(52)
        self._tts_test_btn.clicked.connect(self._test_tts)
        tts_row.addWidget(self._tts_test_btn)
        s.add_layout(tts_row)

        # ── Dictation ─────────────────────────────────────────────────────
        s = _Section("Dictation  (Ctrl+Alt+D)")
        lo.addWidget(s)
        s.add(_lbl("Save folder:"))
        _default = str(Path.home() / "Documents" / "Dictations")
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(4)
        self._dict_folder = _input(config.get("dictation_folder", _default))
        folder_row.addWidget(self._dict_folder, 1)
        browse_btn = _btn("…", height=22)
        browse_btn.setFixedWidth(26)
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        s.add_layout(folder_row)

        fmt_row = QHBoxLayout()
        fmt_row.setContentsMargins(0, 0, 0, 0)
        fmt_row.setSpacing(6)
        fmt_row.addWidget(_lbl("Format:"))
        _fmt_display = {"md": "Markdown (.md)", "txt": "Text (.txt)"}
        self._fmt_stored = {"Markdown (.md)": "md", "Text (.txt)": "txt"}
        self._fmt_combo = _combo(["Markdown (.md)", "Text (.txt)"],
                                  _fmt_display.get(config.get("dictation_format", "md"), "Markdown (.md)"))
        fmt_row.addWidget(self._fmt_combo)
        self._obsidian_cb = QCheckBox("Obsidian frontmatter")
        self._obsidian_cb.setFont(_F_LABEL)
        self._obsidian_cb.setChecked(config.get("dictation_obsidian", True))
        self._obsidian_cb.setStyleSheet(_SS_CHECK)
        fmt_row.addWidget(self._obsidian_cb)
        fmt_row.addStretch()
        s.add_layout(fmt_row)

        tags_row = QHBoxLayout()
        tags_row.setContentsMargins(0, 0, 0, 0)
        tags_row.setSpacing(6)
        tags_row.addWidget(_lbl("Tags:"))
        self._tags_entry = _input(config.get("dictation_tags", "dictation"), "dictation, notes")
        tags_row.addWidget(self._tags_entry, 1)
        s.add_layout(tags_row)

        # ── Voice Polish ──────────────────────────────────────────────────
        s = _Section("Voice Polish  (Ctrl+Alt+F)")
        lo.addWidget(s)
        self._format_cb = QCheckBox("AI format output  (structure text like a professional editor)")
        self._format_cb.setFont(_F_LABEL)
        self._format_cb.setChecked(config.get("format_output", True))
        self._format_cb.setStyleSheet(_SS_CHECK)
        s.add(self._format_cb)
        s.add(_lbl("When enabled: after transcription, AI adds headings, bullet points,\n"
                   "numbered lists and clean paragraphs before pasting.", C["muted"]))

        # ── Hotkeys ────────────────────────────────────────────────────────
        s = _Section("Hotkeys")
        lo.addWidget(s)
        self._hotkey_entries = {}
        for name, label in [
            ("popup",      "Show Popup"),
            ("replace",    "Replace Text"),
            ("clipboard",  "Translate Clipboard"),
            ("whisper",    "Voice → Text"),
            ("dictation",  "Voice Dictation"),
            ("voicechat",  "Voice AI Chat"),
            ("negotiator", "Negotiator"),
            ("teacher",    "English Teacher"),
        ]:
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
            self._hotkey_entries[name] = entry

        # ── System ────────────────────────────────────────────────────────
        s = _Section("System")
        lo.addWidget(s)
        self._autostart_cb = QCheckBox("Start with Windows")
        self._autostart_cb.setFont(_F_LABEL)
        self._autostart_cb.setChecked(config.get("autostart", False))
        self._autostart_cb.setStyleSheet(_SS_CHECK)
        s.add(self._autostart_cb)

        self._clipboard_cb = QCheckBox("Clipboard-only mode (no text selection)")
        self._clipboard_cb.setFont(_F_LABEL)
        self._clipboard_cb.setChecked(config.get("clipboard_only", False))
        self._clipboard_cb.setStyleSheet(_SS_CHECK)
        s.add(self._clipboard_cb)

        self._direct_cb = QCheckBox("Direct type replacement (no clipboard)")
        self._direct_cb.setFont(_F_LABEL)
        self._direct_cb.setChecked(config.get("direct_type", False))
        self._direct_cb.setStyleSheet(_SS_CHECK)
        s.add(self._direct_cb)

    # ── IP helpers ────────────────────────────────────────────────────────────

    def _get_all_ips(self) -> list[str]:
        import socket
        ips = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    ips.append(ip)
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            default_ip = s.getsockname()[0]
            s.close()
            if default_ip not in ips:
                ips.insert(0, default_ip)
        except Exception:
            pass
        return ips or ["127.0.0.1"]

    def _get_local_ip(self) -> str:
        return self._get_all_ips()[0]

    # ── Slots / callbacks ─────────────────────────────────────────────────────

    def _copy_token(self, tok: str):
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(tok)
        from ui.notifications import show_toast
        show_toast("Token copied", 1500)

    def _refresh_qr(self):
        try:
            import qrcode
            from PySide6.QtGui import QImage, QPixmap
        except ImportError:
            self._qr_lbl.setText("pip install qrcode[pil]")
            return

        from services.bridge.auth import get_or_create_token
        ip   = self._ip_combo.currentText() if hasattr(self, "_ip_combo") else self._get_local_ip()
        port = self._bridge_port.text().strip() or "8082"
        tok  = get_or_create_token()
        url  = f"ws://{ip}:{port}/?token={tok}"

        try:
            qr = qrcode.QRCode(box_size=3, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="white", back_color="#181825")
            img_rgb = img.convert("RGB")
            w, h = img_rgb.size
            data = img_rgb.tobytes("raw", "RGB")
            qimage = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimage).scaled(
                110, 110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._qr_lbl.setPixmap(pix)
            self._qr_lbl.setToolTip(url)
        except Exception as e:
            self._qr_lbl.setText(f"QR error: {e}")

    def _on_engine(self, val: str):
        if val == "deepl" and not config.get("api_key"):
            self._deepl_key.setFocus()
        if val == "yandex" and not config.get("yandex_api_key"):
            self._yandex_key.setFocus()
        self._current_engine = val
        import globals as g
        g.current_engine = val
        config["engine"] = val
        save_config_full()
        if val == "deepl":
            try:
                from services.translators.deepl import DeepLEngine
                engine = DeepLEngine()
                count, limit = engine.get_usage()
                from globals import usage_data
                usage_data["character_count"] = count
                usage_data["character_limit"] = limit
            except Exception:
                pass
        self._update_tray()
        self._rebuild_menu()

    def _test_tts(self):
        from services.ai.tts import speak
        self._tts_test_btn.setText("…")
        self._tts_test_btn.setEnabled(False)
        config["tts_engine"] = self._tts_stored.get(self._tts_combo.currentText(), "gtts")
        speak("Проверка голоса", lang_code="ru")
        QTimer.singleShot(3000, lambda: (
            self._tts_test_btn.setText("▶ Test"),
            self._tts_test_btn.setEnabled(True),
        ))

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Папка для диктовок", self._dict_folder.text() or str(Path.home())
        )
        if folder:
            self._dict_folder.setText(folder)

    def _open_role_editor(self):
        from ui.role_editor import show_role_editor
        show_role_editor()

    def _on_load_ai(self):
        self._load_btn.setText("Loading…")
        self._load_btn.setEnabled(False)
        def _task():
            from services.ai.ollama import preload_model
            self._ai_load_sig.emit(preload_model())
        threading.Thread(target=_task, daemon=True).start()

    @Slot(bool)
    def _on_ai_load_result(self, success: bool):
        self._load_btn.setText("Loaded!" if success else "Error")
        self._load_btn.setEnabled(True)
        QTimer.singleShot(3000, lambda: self._load_btn.setText("Load into RAM"))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        _n2c = self._name_to_code

        config["api_key"]          = self._deepl_key.text().strip()
        config["yandex_api_key"]   = self._yandex_key.text().strip()
        config["yandex_folder_id"] = self._yandex_folder.text().strip()

        config["ollama_model_chat"]   = self._ollama_chat_entry.text().strip()
        config["ollama_model_polish"] = self._ollama_polish_entry.text().strip()
        # invalidate the running-models cache so next call re-detects
        from services.ai import ollama as _ol
        _ol._ps_cache = []
        _ol._ps_cache_ts = 0.0

        config["negotiator_lang"] = self._neg_lang_combo.currentText()
        config["autostart"]       = self._autostart_cb.isChecked()
        config["clipboard_only"]  = self._clipboard_cb.isChecked()
        config["direct_type"]     = self._direct_cb.isChecked()
        config["tts_engine"]      = self._tts_stored.get(self._tts_combo.currentText(), "gtts")

        config["bridge_enabled"] = self._bridge_cb.isChecked()
        try:
            config["bridge_port"] = int(self._bridge_port.text().strip())
        except ValueError:
            pass

        config["dictation_folder"]   = self._dict_folder.text().strip()
        config["dictation_format"]   = self._fmt_stored.get(self._fmt_combo.currentText(), "md")
        config["dictation_obsidian"] = self._obsidian_cb.isChecked()
        config["dictation_tags"]     = self._tags_entry.text().strip()
        config["format_output"]      = self._format_cb.isChecked()

        src_name = self._src_combo.currentText()
        config["source_lang"] = _n2c.get(src_name, src_name)

        tgt_name = self._tgt_combo.currentText()
        _SAME = "(Same as source)"
        config["target_lang"] = "" if tgt_name == _SAME else _n2c.get(tgt_name, tgt_name)

        for name, entry in self._hotkey_entries.items():
            hk = entry.text().strip()
            if hk:
                try:
                    parse_hotkey_string(hk)
                    config[f"hotkey_{name}"] = hk
                except Exception:
                    pass

        save_config_full()
        self.close()

        def _post():
            from ui.tray_menu import set_autostart
            set_autostart(config["autostart"])
            self._update_tray()
            self._rebuild_menu()
        threading.Thread(target=_post, daemon=True).start()


# ── Public entry point ────────────────────────────────────────────────────────

def show_settings_window(current_engine: str, update_tray_icon, rebuild_menu):
    import logging
    log = logging.getLogger("settings")
    try:
        win = SettingsWindow(current_engine, update_tray_icon, rebuild_menu)
        win.show()
    except Exception as e:
        import traceback
        log.error("Settings window failed: %s\n%s", e, traceback.format_exc())
