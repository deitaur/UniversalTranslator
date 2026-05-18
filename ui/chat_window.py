"""Chat popup — PySide6. Role selector, sessions, streaming AI responses."""

import threading
import uuid
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from config import APP_NAME, ICON_FILE, C, config, save_config_full

FONT_FAMILIES = ["Segoe UI", "Verdana", "Cascadia Code"]
FONT_SIZES    = {"Small": 11, "Medium": 13, "Large": 15}


def _btn(text, bg, fg, hover=None, w=None, h=32):
    b = QPushButton(text)
    b.setFont(QFont("Segoe UI Semibold", 10))
    if h:
        b.setFixedHeight(h)
    if w:
        b.setFixedWidth(w)
    hv = hover or bg
    b.setStyleSheet(
        f"QPushButton {{ background:{bg}; color:{fg}; border:none;"
        f" border-radius:6px; padding:2px 8px; }}"
        f"QPushButton:hover {{ background:{hv}; }}"
        f"QPushButton:disabled {{ background:{C['border']}; color:{C['muted']}; }}"
    )
    return b


# ── Bubble widget ─────────────────────────────────────────────────────────────

class _Bubble(QWidget):
    """A single chat message bubble with selectable text and a copy button."""

    def __init__(self, role: str, text: str, role_label: str, role_color: str,
                 font_family: str, font_size: int):
        super().__init__()
        self._role      = role
        self._text      = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        is_user    = (role == "user")
        bubble_bg  = C["card"] if is_user else C["surface"]
        text_color = C["text"] if is_user else C["green"]
        pad_l, pad_r = (60, 10) if is_user else (10, 60)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(pad_l, 2, pad_r, 2)
        outer.setSpacing(2)

        # Role row
        role_row = QHBoxLayout()
        role_row.setSpacing(6)
        rl = QLabel("You" if is_user else role_label)
        rl.setFont(QFont("Segoe UI", 9))
        rl.setStyleSheet(f"color: {C['muted'] if is_user else role_color}; background: transparent;")
        role_row.addWidget(rl)

        copy_btn = QPushButton("[copy]")
        copy_btn.setFont(QFont("Segoe UI", 8))
        copy_btn.setFlat(True)
        copy_btn.setStyleSheet(
            f"QPushButton {{ color:{C['muted']}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ color:{C['text']}; }}"
        )
        copy_btn.clicked.connect(self._copy)
        role_row.addWidget(copy_btn)
        role_row.addStretch()
        outer.addLayout(role_row)

        # Bubble
        bubble = QFrame()
        bubble.setStyleSheet(
            f"QFrame {{ background:{bubble_bg}; border:1px solid {C['border']};"
            f" border-radius:8px; }}"
            f"QTextEdit {{ background:{bubble_bg}; color:{text_color};"
            f" border:none; }}"
        )
        b_lo = QVBoxLayout(bubble)
        b_lo.setContentsMargins(0, 0, 0, 0)

        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont(font_family, font_size))
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(text)
        self._text_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._text_edit.document().contentsChanged.connect(self._adjust_height)
        b_lo.addWidget(self._text_edit)
        outer.addWidget(bubble)

        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self):
        doc_h = int(self._text_edit.document().size().height()) + 12
        self._text_edit.setFixedHeight(max(doc_h, 36))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-measure after Qt has reflowed the document to the new viewport width
        QTimer.singleShot(0, self._adjust_height)

    def set_text(self, text: str):
        self._text = text
        self._text_edit.setPlainText(text)

    def update_font(self, family: str, size: int):
        self._text_edit.setFont(QFont(family, size))
        QTimer.singleShot(0, self._adjust_height)

    def _copy(self):
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(self._text)

    def get_text(self) -> str:
        return self._text


# ── Chat window ───────────────────────────────────────────────────────────────

class ChatWindow(QWidget):
    # Signals for background→main-thread communication
    _token_sig    = Signal(str)   # streaming token (accumulated text)
    _done_sig     = Signal(str)   # full response finished
    _error_sig    = Signal(str)   # error text
    _enable_sig   = Signal()      # re-enable input
    _status_sig   = Signal(str)   # tool status (e.g. "🔍 Searching…")

    def __init__(self, initial_text: str = "", mode: str = "negotiator"):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._mode     = mode
        self._history: list[dict] = []
        self._session_id: Optional[str] = None
        self._streaming_bubble: Optional[_Bubble] = None

        self.setWindowTitle(APP_NAME)
        self.resize(560, 640)
        self.setMinimumSize(440, 400)
        self.setStyleSheet(f"background: {C['bg']}; color: {C['text']};")
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._token_sig.connect(self._on_token)
        self._done_sig.connect(self._on_done)
        self._error_sig.connect(self._on_error)
        self._enable_sig.connect(self._re_enable)
        self._status_sig.connect(self._on_status)

        self._load_session()
        self._build()
        self._update_title()

        if initial_text.strip():
            QTimer.singleShot(200, lambda: self._send(initial_text))

    def _load_session(self):
        from storage.history import load_sessions
        sessions = load_sessions()
        if sessions:
            self._session_id = max(sessions, key=lambda k: sessions[k].get("updated", ""))
            self._history = sessions[self._session_id].get("history", [])
        else:
            self._session_id = str(uuid.uuid4())
            self._history = []

    def _save_session(self):
        from storage.history import save_session
        if self._session_id:
            save_session(self._session_id, self._history)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header
        hdr = QFrame()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background:{C['surface']}; border:none;")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(10, 8, 6, 8)
        hdr_lo.setSpacing(4)

        from storage.roles import load_roles
        roles = load_roles()
        role_ids   = list(roles.keys())
        role_names = {rid: roles[rid].get("name", rid) for rid in role_ids}

        self._role_combo = QComboBox()
        self._role_combo.setFont(QFont("Segoe UI Semibold", 11))
        self._role_combo.setStyleSheet(
            f"QComboBox {{ background:{C['card_alt']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:6px; padding:2px 8px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
        )
        self._role_combo.setFixedWidth(140)
        for rid in role_ids:
            self._role_combo.addItem(role_names[rid], rid)
        # select current mode
        idx = next((i for i in range(self._role_combo.count())
                    if self._role_combo.itemData(i) == self._mode), 0)
        self._role_combo.setCurrentIndex(idx)
        self._role_combo.currentIndexChanged.connect(self._on_role_change)
        hdr_lo.addWidget(self._role_combo)

        model_lbl = QLabel(config.get("ollama_model", "qwen2.5:14b"))
        model_lbl.setFont(QFont("Segoe UI", 9))
        model_lbl.setStyleSheet(f"color:{C['muted']}; background:transparent;")
        hdr_lo.addWidget(model_lbl)

        lang_values = ["Auto", "English", "Russian"]
        _lmap_to = {"Same as input": "Auto", "English": "English", "Russian": "Russian"}
        _lmap_fr = {"Auto": "Same as input", "English": "English", "Russian": "Russian"}
        self._lang_combo = QComboBox()
        self._lang_combo.setFont(QFont("Segoe UI", 10))
        self._lang_combo.setStyleSheet(
            f"QComboBox {{ background:{C['card_alt']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:5px; padding:2px 6px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
        )
        self._lang_combo.setFixedWidth(80)
        self._lang_combo.addItems(lang_values)
        self._lang_combo.setCurrentText(_lmap_to.get(config.get("negotiator_lang", "Same as input"), "Auto"))
        self._lang_combo.currentTextChanged.connect(
            lambda v: (config.__setitem__("negotiator_lang", _lmap_fr.get(v, "Same as input")),
                       save_config_full())
        )
        hdr_lo.addWidget(self._lang_combo)
        hdr_lo.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFont(QFont("Segoe UI Bold", 11))
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ color:{C['red']}; background:{C['card_alt']}; border:none; border-radius:5px; }}"
            f"QPushButton:hover {{ background:{C['border']}; }}"
        )
        close_btn.clicked.connect(self.close)
        hdr_lo.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(34)
        toolbar.setStyleSheet(f"background:{C['surface']}; border:none;")
        tb_lo = QHBoxLayout(toolbar)
        tb_lo.setContentsMargins(8, 3, 8, 3)
        tb_lo.setSpacing(4)

        tb_lo.addWidget(QLabel("Font:"))

        self._font_combo = QComboBox()
        self._font_combo.setFont(QFont("Segoe UI", 9))
        self._font_combo.setFixedWidth(110)
        self._font_combo.setStyleSheet(
            f"QComboBox {{ background:{C['card_alt']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:4px; padding:1px 4px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
        )
        self._font_combo.addItems(FONT_FAMILIES)
        self._font_combo.setCurrentText(config.get("chat_font_family", "Segoe UI"))
        self._font_combo.currentTextChanged.connect(self._on_font_change)
        tb_lo.addWidget(self._font_combo)

        size_combo = QComboBox()
        size_combo.setFont(QFont("Segoe UI", 9))
        size_combo.setFixedWidth(90)
        size_combo.setStyleSheet(self._font_combo.styleSheet())
        size_combo.addItems(list(FONT_SIZES.keys()))
        size_combo.setCurrentText(config.get("chat_font_size", "Medium"))
        size_combo.currentTextChanged.connect(self._on_size_change)
        tb_lo.addWidget(size_combo)

        tb_lo.addStretch()

        # Session controls (right side of toolbar)
        self._compress_btn = _btn("Compress", C["accent"], C["bg"], "#7ba4e8", h=26)
        self._compress_btn.setFont(QFont("Segoe UI", 9))
        self._compress_btn.setFixedWidth(68)
        self._compress_btn.clicked.connect(self._compress_context)
        tb_lo.addWidget(self._compress_btn)

        new_sess = _btn("New", C["green"], C["bg"], "#73daca", h=26)
        new_sess.setFixedWidth(38)
        new_sess.setFont(QFont("Segoe UI", 9))
        new_sess.clicked.connect(self._new_session)
        tb_lo.addWidget(new_sess)

        del_sess = _btn("Del", C["red"], C["bg"], "#e06080", h=26)
        del_sess.setFixedWidth(38)
        del_sess.setFont(QFont("Segoe UI", 9))
        del_sess.clicked.connect(self._del_session)
        tb_lo.addWidget(del_sess)

        self._sess_combo = QComboBox()
        self._sess_combo.setFont(QFont("Segoe UI", 9))
        self._sess_combo.setFixedWidth(130)
        self._sess_combo.setStyleSheet(self._font_combo.styleSheet())
        self._sess_combo.currentTextChanged.connect(self._on_session_select)
        tb_lo.addWidget(self._sess_combo)

        root.addWidget(toolbar)

        # ── Chat scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{C['bg']}; }}")

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet(f"background:{C['bg']};")
        self._chat_lo = QVBoxLayout(self._chat_container)
        self._chat_lo.setContentsMargins(6, 6, 6, 6)
        self._chat_lo.setSpacing(2)
        self._chat_lo.addStretch()

        self._scroll.setWidget(self._chat_container)
        root.addWidget(self._scroll, 1)

        # ── Status bar (tool activity)
        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setFixedHeight(18)
        self._status_lbl.setStyleSheet(
            f"color:{C['accent']}; background:{C['bg']}; padding-left:10px;")
        self._status_lbl.setVisible(False)
        root.addWidget(self._status_lbl)

        # ── Input bar
        input_bar = QFrame()
        input_bar.setFixedHeight(56)
        input_bar.setStyleSheet(f"background:{C['surface']}; border:none;")
        in_lo = QHBoxLayout(input_bar)
        in_lo.setContentsMargins(10, 9, 10, 9)
        in_lo.setSpacing(6)

        paste_btn = _btn("P", C["card_alt"], C["subtext"], C["border"], w=34, h=38)
        paste_btn.setFont(QFont("Segoe UI Bold", 12))
        paste_btn.clicked.connect(self._paste_to_entry)
        in_lo.addWidget(paste_btn)

        self._entry = QLineEdit()
        self._entry.setFont(QFont("Segoe UI", 12))
        self._entry.setPlaceholderText("Type message...")
        self._entry.setStyleSheet(
            f"QLineEdit {{ background:{C['card']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:7px; padding:4px 10px; }}"
        )
        self._entry.returnPressed.connect(self._on_send)
        in_lo.addWidget(self._entry, 1)

        self._send_btn = _btn(">", C["accent"], C["bg"], "#7ba4e8", w=50, h=38)
        self._send_btn.setFont(QFont("Segoe UI Bold", 14))
        self._send_btn.clicked.connect(self._on_send)
        in_lo.addWidget(self._send_btn)

        root.addWidget(input_bar)

        # Populate sessions combo and rebuild history
        self._update_sessions_combo()
        self._rebuild_bubbles()

    # ── Sessions ──────────────────────────────────────────────────────────────

    def _update_sessions_combo(self):
        from storage.history import load_sessions
        sessions = load_sessions()
        self._sess_combo.blockSignals(True)
        self._sess_combo.clear()
        current_name = ""
        for k, v in sorted(sessions.items(), key=lambda i: i[1].get("updated", ""), reverse=True):
            n = v.get("name", "New Chat")
            self._sess_combo.addItem(n, k)
            if k == self._session_id:
                current_name = n
        if current_name:
            self._sess_combo.setCurrentText(current_name)
        self._sess_combo.blockSignals(False)

    def _on_session_select(self, name: str):
        from storage.history import load_sessions
        sessions = load_sessions()
        for k, v in sessions.items():
            if v.get("name") == name:
                self._session_id = k
                self._history = v.get("history", [])
                self._rebuild_bubbles()
                break

    def _new_session(self):
        from storage.history import save_session
        self._session_id = str(uuid.uuid4())
        self._history = []
        save_session(self._session_id, self._history)
        self._clear_bubbles()
        self._update_sessions_combo()

    def _del_session(self):
        from storage.history import load_sessions, save_session, delete_session
        delete_session(self._session_id)
        sessions = load_sessions()
        if sessions:
            self._session_id = max(sessions, key=lambda k: sessions[k].get("updated", ""))
            self._history = sessions[self._session_id].get("history", [])
        else:
            self._session_id = str(uuid.uuid4())
            self._history = []
            save_session(self._session_id, self._history)
        self._rebuild_bubbles()
        self._update_sessions_combo()

    # ── Bubble helpers ────────────────────────────────────────────────────────

    def _get_role_info(self):
        from storage.roles import get_role
        role = get_role(self._mode)
        label = role.get("name", self._mode) if role else self._mode
        color = role.get("color", C["mauve"]) if role else C["mauve"]
        return label, color

    def _get_font(self):
        family = config.get("chat_font_family", "Segoe UI")
        size   = FONT_SIZES.get(config.get("chat_font_size", "Medium"), 13)
        return family, size

    def _add_bubble(self, role: str, text: str) -> _Bubble:
        label, color = self._get_role_info()
        family, size = self._get_font()
        bubble = _Bubble(role, text, label, color, family, size)
        # insert before the trailing stretch
        self._chat_lo.insertWidget(self._chat_lo.count() - 1, bubble)
        return bubble

    def _clear_bubbles(self):
        while self._chat_lo.count() > 1:
            item = self._chat_lo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_bubbles(self):
        self._clear_bubbles()
        for msg in self._history:
            self._add_bubble(msg["role"], msg["content"])
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Font changes ──────────────────────────────────────────────────────────

    def _on_font_change(self, family: str):
        config["chat_font_family"] = family
        save_config_full()
        self._refresh_fonts()

    def _on_size_change(self, size_label: str):
        config["chat_font_size"] = size_label
        save_config_full()
        self._refresh_fonts()

    def _refresh_fonts(self):
        family, size = self._get_font()
        for i in range(self._chat_lo.count()):
            item = self._chat_lo.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _Bubble):
                item.widget().update_font(family, size)

    # ── Role change ───────────────────────────────────────────────────────────

    def _on_role_change(self, idx: int):
        rid = self._role_combo.itemData(idx)
        if rid and rid != self._mode:
            self._mode = rid
            self._update_title()

    def _update_title(self):
        from storage.roles import get_role
        role = get_role(self._mode)
        title = role.get("name", self._mode) if role else self._mode
        self.setWindowTitle(f"{APP_NAME} - {title}")

    # ── Input ─────────────────────────────────────────────────────────────────

    def _paste_to_entry(self):
        from win32.clipboard import get_clipboard_text
        try:
            clip = get_clipboard_text()
            if clip.strip():
                self._entry.insert(clip.strip())
                self._entry.setFocus()
        except Exception:
            pass

    def _on_send(self):
        msg = self._entry.text().strip()
        if not msg:
            return
        self._entry.clear()
        self._send(msg)

    def _send(self, text: str):
        self._add_bubble("user", text)
        self._history.append({"role": "user", "content": text})
        self._save_session()
        self._scroll_bottom()

        self._entry.setEnabled(False)
        self._send_btn.setEnabled(False)

        # Create a placeholder streaming bubble
        self._streaming_bubble = self._add_bubble("assistant", "…")
        self._scroll_bottom()

        def _stream():
            from services.ai.ollama import chat_ollama, check_ollama
            if not check_ollama():
                self._error_sig.emit("Ollama не запущен. Запустите: ollama serve")
                return
            chunks: list[str] = []
            def on_token(chunk):
                chunks.append(chunk)
                self._token_sig.emit("".join(chunks))
            def on_status(text: str):
                self._status_sig.emit(text)
            try:
                full = chat_ollama(self._history, on_token=on_token,
                                   on_status=on_status, mode=self._mode)
                self._history.append({"role": "assistant", "content": full})
                self._save_session()
                self._done_sig.emit(full)
                self._check_auto_compress()
            except Exception as e:
                self._error_sig.emit(f"Error: {str(e)[:100]}")

        threading.Thread(target=_stream, daemon=True).start()

    # ── Streaming slots (main thread) ─────────────────────────────────────────

    @Slot(str)
    def _on_token(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_text(text)
            self._scroll_bottom()

    @Slot(str)
    def _on_done(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_text(text)
        self._streaming_bubble = None
        self._re_enable()

    @Slot(str)
    def _on_error(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_text(text)
        self._streaming_bubble = None
        self._re_enable()

    @Slot(str)
    def _on_status(self, text: str):
        if text:
            self._status_lbl.setText(text)
            self._status_lbl.setVisible(True)
        else:
            self._status_lbl.setVisible(False)

    @Slot()
    def _re_enable(self):
        self._status_lbl.setVisible(False)
        self._entry.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._entry.setFocus()

    # ── Context compression ───────────────────────────────────────────────────

    def _compress_context(self):
        if not self._history:
            return
        self._send_btn.setEnabled(False)
        self._compress_btn.setEnabled(False)

        def _task():
            try:
                from services.ai.ollama import chat_ollama
                compress_prompt = (
                    "You are an expert summarizer. Summarize the following dialogue. "
                    "Capture the core context, conflict/situation, and any decisions made. "
                    "Output ONLY the summary in Russian."
                )
                msgs = [{"role": "system", "content": compress_prompt}] + self._history
                summary = chat_ollama(msgs, mode=self._mode)
                self._history = [{"role": "user",
                                   "content": f"[Сжатый контекст предыдущего диалога]:\n{summary}"}]
                self._save_session()
                # rebuild on main thread
                self._enable_sig.emit()
            except Exception:
                self._enable_sig.emit()

        threading.Thread(target=_task, daemon=True).start()

    def _check_auto_compress(self):
        total = sum(len(m.get("content", "")) for m in self._history)
        if total > 12000:
            self._compress_context()

    @Slot()
    def _re_enable(self):
        self._entry.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._compress_btn.setEnabled(True)
        self._entry.setFocus()
        # rebuild bubbles (needed after compress)
        if self._streaming_bubble is None:
            self._rebuild_bubbles()


# ── Controller (thread-safe show/switch-mode) ─────────────────────────────────

class _ChatController(QObject):
    _show_sig = Signal(str, str)   # initial_text, mode

    def __init__(self):
        super().__init__()
        self._window: Optional[ChatWindow] = None
        self._show_sig.connect(self._do_show)

    def show(self, initial_text: str = "", mode: str = "negotiator"):
        self._show_sig.emit(initial_text, mode)

    @Slot(str, str)
    def _do_show(self, initial_text: str, mode: str):
        if self._window is not None:
            try:
                if mode != self._window._mode:
                    self._window._mode = mode
                    self._window._update_title()
                    idx = next((i for i in range(self._window._role_combo.count())
                                if self._window._role_combo.itemData(i) == mode), -1)
                    if idx >= 0:
                        self._window._role_combo.setCurrentIndex(idx)
                self._window.show()
                self._window.activateWindow()
                self._window.raise_()
                if initial_text.strip():
                    self._window._send(initial_text)
                return
            except RuntimeError:
                self._window = None

        self._window = ChatWindow(initial_text, mode)
        self._window.destroyed.connect(lambda: setattr(self, "_window", None))
        self._window.show()
        self._window.activateWindow()


_controller: Optional[_ChatController] = None


def setup_chat() -> _ChatController:
    """Create the singleton. Call from the Qt main thread in main.py."""
    global _controller
    if _controller is None:
        _controller = _ChatController()
    return _controller


def show_chat_window(initial_text: str = "", mode: str = "negotiator"):
    if _controller is not None:
        _controller.show(initial_text, mode)
    else:
        import logging
        logging.getLogger("chat_window").warning("show_chat_window called before setup_chat")
