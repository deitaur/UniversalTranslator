"""Voice Chat Dialog — mic → Whisper STT → Ollama LLM → TTS."""

import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from config import APP_NAME, ICON_FILE, C, config
from ui.chat_window import _Bubble

class _RoleComboBox(QComboBox):
    def __init__(self, refresh_callback):
        super().__init__()
        self._refresh_callback = refresh_callback

    def showPopup(self):
        self._refresh_callback()
        super().showPopup()

# VAD tuning
_SILENCE_RMS = 0.012
_SILENCE_SEC = 1.5
_MAX_SEC     = 60


def _tts_lang() -> str:
    nl = config.get("negotiator_lang", "Same as input")
    if nl == "English":
        return "en"
    if nl == "Russian":
        return "ru"
    from utils.language import get_source_lang
    return get_source_lang()


def _record_vad(stop_evt, on_speech_detected: Optional[Callable] = None):
    """Record with amplitude VAD. Returns np.ndarray or None.
    Calls on_speech_detected() once when the first speech block is found.
    """
    import numpy as np
    import sounddevice as sd

    sr, bms = 16000, 50
    blk = int(sr * bms / 1000)
    chunks: list = []
    has_speech = False
    notified   = False
    silence    = 0
    sil_lim    = int(_SILENCE_SEC * 1000 / bms)
    max_n      = int(_MAX_SEC    * 1000 / bms)

    def cb(indata, frames, t, status):
        chunks.append(indata.copy())

    with sd.InputStream(callback=cb, channels=1, samplerate=sr, blocksize=blk):
        n = 0
        while not stop_evt.is_set() and n < max_n:
            time.sleep(bms / 1000)
            n += 1
            if not chunks:
                continue
            rms = float(np.sqrt(np.mean(chunks[-1].flatten() ** 2)))
            if rms > _SILENCE_RMS:
                if not has_speech:
                    has_speech = True
                    if on_speech_detected and not notified:
                        notified = True
                        try:
                            on_speech_detected()
                        except Exception:
                            pass
                silence = 0
            elif has_speech:
                silence += 1
                if silence >= sil_lim:
                    break

    if not chunks or not has_speech:
        return None
    return np.concatenate(chunks, axis=0).flatten()


class VoiceChatDialog(QWidget):

    _transcript_sig     = Signal(str)
    _mic_state_sig      = Signal(str)   # "idle" | "recording" | "transcribing"
    _speech_detect_sig  = Signal()      # first speech block detected
    _token_sig          = Signal(str)
    _done_sig           = Signal(str)
    _error_sig          = Signal(str)
    _status_sig         = Signal(str, str)  # message, color

    def __init__(self):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._history: list[dict] = []
        self._streaming_bubble: Optional[_Bubble] = None
        self._stop_rec = threading.Event()
        self._is_recording = False

        self.setWindowTitle(f"{APP_NAME} — Voice Chat")
        self.resize(500, 580)
        self.setMinimumSize(380, 400)
        self.setStyleSheet(f"background: {C['bg']}; color: {C['text']};")
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._transcript_sig.connect(self._on_transcript)
        self._mic_state_sig.connect(self._on_mic_state)
        self._speech_detect_sig.connect(self._on_speech_detected)
        self._token_sig.connect(self._on_token)
        self._done_sig.connect(self._on_done)
        self._error_sig.connect(self._on_error)
        self._status_sig.connect(self._on_status)

        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header
        hdr = QFrame()
        hdr.setFixedHeight(42)
        hdr.setStyleSheet(f"background:{C['surface']}; border:none;")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(8, 4, 8, 4)
        hdr_lo.setSpacing(6)

        self._role_combo = _RoleComboBox(self._refresh_roles)
        self._role_combo.setFont(QFont("Segoe UI Semibold", 10))
        self._role_combo.setStyleSheet(
            f"QComboBox {{ background:{C['card_alt']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:5px; padding:1px 6px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ background:{C['card']}; color:{C['text']}; }}"
        )
        self._role_combo.setFixedWidth(170)
        self._refresh_roles()
        hdr_lo.addWidget(self._role_combo)

        edit_role_btn = QPushButton("✎")
        edit_role_btn.setFixedSize(24, 24)
        edit_role_btn.setFont(QFont("Segoe UI", 11))
        edit_role_btn.setStyleSheet(
            f"QPushButton {{ color:{C['text']}; background:{C['card_alt']}; border:1px solid {C['border']}; border-radius:5px; }}"
            f"QPushButton:hover {{ background:{C['border']}; }}"
        )
        def _open_role_editor():
            from ui.role_editor import show_role_editor
            show_role_editor()
        edit_role_btn.clicked.connect(_open_role_editor)
        hdr_lo.addWidget(edit_role_btn)

        from services.ai.ollama import get_ollama_model as _gom
        self._model_lbl = QLabel(_gom())
        self._model_lbl.setFont(QFont("Segoe UI", 8))
        self._model_lbl.setStyleSheet(f"color:{C['muted']}; background:transparent;")
        hdr_lo.addWidget(self._model_lbl)
        hdr_lo.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFont(QFont("Segoe UI Bold", 10))
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(
            f"QPushButton {{ color:{C['red']}; background:{C['card_alt']};"
            f" border:none; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{C['border']}; }}"
        )
        close_btn.clicked.connect(self.close)
        hdr_lo.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Chat scroll
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

        # ── Input bar
        input_bar = QFrame()
        input_bar.setStyleSheet(f"background:{C['surface']}; border:none;")
        in_lo = QVBoxLayout(input_bar)
        in_lo.setContentsMargins(8, 6, 8, 8)
        in_lo.setSpacing(4)

        # Status line
        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet(f"color:{C['muted']}; background:transparent;")
        self._status_lbl.setFixedHeight(14)
        in_lo.addWidget(self._status_lbl)

        row = QHBoxLayout()
        row.setSpacing(5)

        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setFixedSize(38, 38)
        self._mic_btn.setFont(QFont("Segoe UI", 15))
        self._mic_btn.setStyleSheet(self._mic_style_idle())
        self._mic_btn.setToolTip("Click to start/stop voice recording")
        self._mic_btn.clicked.connect(self._toggle_mic)
        row.addWidget(self._mic_btn)

        self._entry = QLineEdit()
        self._entry.setFont(QFont("Segoe UI", 11))
        self._entry.setPlaceholderText("Type or press 🎙 to speak…")
        self._entry.setFixedHeight(38)
        self._entry.setStyleSheet(
            f"QLineEdit {{ background:{C['card']}; color:{C['text']};"
            f" border:1px solid {C['border']}; border-radius:6px; padding:3px 8px; }}"
        )
        self._entry.returnPressed.connect(self._on_send)
        row.addWidget(self._entry, 1)

        self._send_btn = QPushButton("›")
        self._send_btn.setFixedSize(38, 38)
        self._send_btn.setFont(QFont("Segoe UI Bold", 18))
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background:{C['accent']}; color:{C['bg']}; border:none; border-radius:6px; }}"
            f"QPushButton:hover {{ background:#7ba4e8; }}"
            f"QPushButton:disabled {{ background:{C['border']}; color:{C['muted']}; }}"
        )
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._send_btn)

        in_lo.addLayout(row)

        # ── ZBrush-style speed section ─────────────────────────────────────
        _spd_init = float(config.get("tts_speed", 1.0))
        _spd_tick  = round(_spd_init * 10)   # 10 = 1.0×, 14 = 1.4×, 30 = 3.0×

        # Header toggle button
        self._spd_toggle = QPushButton()
        self._spd_toggle.setCheckable(True)
        self._spd_toggle.setChecked(False)
        self._spd_toggle.setFixedHeight(18)
        self._spd_toggle.setFont(QFont("Segoe UI", 8))
        self._spd_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._spd_toggle.setStyleSheet(
            f"QPushButton {{ background:{C['card']}; color:{C['subtext']};"
            f" border:none; border-top:1px solid {C['border']};"
            f" text-align:left; padding-left:6px; }}"
            f"QPushButton:hover {{ color:{C['text']}; }}"
        )
        self._spd_lbl_txt = f"{_spd_init:.1f}×"
        self._spd_toggle.setText(f"  ▸  Voice Speed  {self._spd_lbl_txt}")
        in_lo.addWidget(self._spd_toggle)

        # Body (hidden by default)
        self._spd_body = QWidget()
        self._spd_body.setStyleSheet(f"background:{C['card']}; border:none;")
        self._spd_body.setVisible(False)
        spd_row = QHBoxLayout(self._spd_body)
        spd_row.setContentsMargins(6, 3, 6, 3)
        spd_row.setSpacing(4)

        turtle_btn = QPushButton("🐢")
        turtle_btn.setFixedSize(24, 22)
        turtle_btn.setFont(QFont("Segoe UI", 11))
        turtle_btn.setStyleSheet(
            f"QPushButton {{ background:{C['card_alt']}; border:none; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{C['surface']}; }}"
        )
        spd_row.addWidget(turtle_btn)

        self._spd_slider = QSlider(Qt.Orientation.Horizontal)
        self._spd_slider.setMinimum(10)    # 1.0×
        self._spd_slider.setMaximum(30)    # 3.0×
        self._spd_slider.setSingleStep(2)
        self._spd_slider.setPageStep(2)
        self._spd_slider.setValue(_spd_tick)
        self._spd_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background:{C['border']}; height:4px; border-radius:2px; }}"
            f"QSlider::handle:horizontal {{ background:{C['accent']}; width:12px; height:12px;"
            f" margin:-4px 0; border-radius:6px; }}"
            f"QSlider::sub-page:horizontal {{ background:{C['accent']}; height:4px; border-radius:2px; }}"
        )
        spd_row.addWidget(self._spd_slider, 1)

        leopard_btn = QPushButton("🐆")
        leopard_btn.setFixedSize(24, 22)
        leopard_btn.setFont(QFont("Segoe UI", 11))
        leopard_btn.setStyleSheet(turtle_btn.styleSheet())
        spd_row.addWidget(leopard_btn)

        self._spd_val_lbl = QLabel(self._spd_lbl_txt)
        self._spd_val_lbl.setFont(QFont("Segoe UI Semibold", 9))
        self._spd_val_lbl.setStyleSheet(f"color:{C['accent']}; background:transparent;")
        self._spd_val_lbl.setFixedWidth(34)
        spd_row.addWidget(self._spd_val_lbl)

        in_lo.addWidget(self._spd_body)

        def _spd_update(tick: int):
            tick = max(10, min(30, round(tick / 2) * 2))  # snap to even
            self._spd_slider.setValue(tick)
            spd = tick / 10.0
            label = f"{spd:.1f}×"
            self._spd_val_lbl.setText(label)
            self._spd_toggle.setText(
                f"  {'▾' if self._spd_toggle.isChecked() else '▸'}  Voice Speed  {label}"
            )
            config["tts_speed"] = spd

        def _spd_toggle_body(checked: bool):
            self._spd_body.setVisible(checked)
            spd = self._spd_slider.value() / 10.0
            arrow = "▾" if checked else "▸"
            self._spd_toggle.setText(f"  {arrow}  Voice Speed  {spd:.1f}×")

        self._spd_slider.valueChanged.connect(_spd_update)
        turtle_btn.clicked.connect(lambda: _spd_update(self._spd_slider.value() - 2))
        leopard_btn.clicked.connect(lambda: _spd_update(self._spd_slider.value() + 2))
        self._spd_toggle.toggled.connect(_spd_toggle_body)

        self._immediate_cb = QCheckBox("Send immediately after mic (skip editing)")
        self._immediate_cb.setFont(QFont("Segoe UI", 9))
        self._immediate_cb.setStyleSheet(
            f"QCheckBox {{ color:{C['muted']}; background:transparent; }}"
        )
        self._immediate_cb.setChecked(config.get("voice_chat_immediate", False))
        self._immediate_cb.toggled.connect(
            lambda v: config.__setitem__("voice_chat_immediate", v)
        )
        in_lo.addWidget(self._immediate_cb)

        root.addWidget(input_bar)

    # ── Role / bubble helpers ─────────────────────────────────────────────────

    def _current_role_id(self) -> str:
        return self._role_combo.currentData() or "negotiator"

    def _get_role_info(self):
        from storage.roles import get_role
        rid  = self._current_role_id()
        role = get_role(rid)
        label = role.get("name", rid) if role else rid
        color = role.get("color", C["mauve"]) if role else C["mauve"]
        return label, color

    def _refresh_roles(self):
        from storage.roles import load_roles
        rid_selected = self._current_role_id()
        roles = load_roles()
        self._role_combo.blockSignals(True)
        self._role_combo.clear()
        idx_to_select = 0
        i = 0
        for rid, role_data in roles.items():
            self._role_combo.addItem(role_data.get("name", rid), rid)
            if rid == rid_selected:
                idx_to_select = i
            i += 1
        self._role_combo.setCurrentIndex(idx_to_select)
        self._role_combo.blockSignals(False)

    def _add_bubble(self, role: str, text: str) -> _Bubble:
        label, color = self._get_role_info()
        family = config.get("chat_font_family", "Segoe UI")
        size   = {"Small": 11, "Medium": 13, "Large": 15}.get(
            config.get("chat_font_size", "Medium"), 13)
        bubble = _Bubble(role, text, label, color, family, size)
        self._chat_lo.insertWidget(self._chat_lo.count() - 1, bubble)
        return bubble

    def _scroll_bottom(self):
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Mic state styles ──────────────────────────────────────────────────────

    def _mic_style_idle(self) -> str:
        return (
            f"QPushButton {{ background:{C['card_alt']}; border:1px solid {C['border']};"
            f" border-radius:6px; }}"
            f"QPushButton:hover {{ background:{C['surface']}; }}"
        )

    def _mic_style_recording(self) -> str:
        return (
            f"QPushButton {{ background:{C['red']}; border:none;"
            f" border-radius:6px; color:{C['bg']}; }}"
            f"QPushButton:hover {{ background:#e06080; }}"
        )

    def _mic_style_busy(self) -> str:
        return (
            f"QPushButton {{ background:{C['card_alt']}; border:1px solid {C['border']};"
            f" border-radius:6px; color:{C['muted']}; }}"
        )

    # ── Mic recording ─────────────────────────────────────────────────────────

    def _toggle_mic(self):
        if self._is_recording:
            self._stop_rec.set()
        else:
            self._start_mic()

    def _start_mic(self):
        try:
            import sounddevice  # noqa — verify installed
        except ImportError:
            self._status_sig.emit(
                "sounddevice not installed — pip install sounddevice", C["red"]
            )
            return

        self._stop_rec.clear()
        self._is_recording = True
        self._mic_state_sig.emit("recording")

        def _task():
            audio = _record_vad(
                self._stop_rec,
                on_speech_detected=lambda: self._speech_detect_sig.emit(),
            )

            if audio is None:
                # Nothing recorded — mic may be wrong or silent
                self._mic_state_sig.emit("idle")
                self._status_sig.emit(
                    "⚠  No speech detected — check microphone in Settings", C["yellow"]
                )
                return

            self._mic_state_sig.emit("transcribing")
            try:
                from services.ai.whisper import _load_whisper_model, _fix_russian_spelling
                from utils.language import get_source_lang
                model = _load_whisper_model()
                src   = get_source_lang()
                wlang = None if src == "en" else src
                segs, info = model.transcribe(audio, language=wlang, beam_size=5)
                text = " ".join(s.text for s in segs).strip()
                if getattr(info, "language", src) == "ru":
                    text = _fix_russian_spelling(text)
            except Exception as e:
                self._mic_state_sig.emit("idle")
                self._status_sig.emit(f"⚠  Transcription error: {e}", C["red"])
                return

            self._mic_state_sig.emit("idle")
            if text:
                self._transcript_sig.emit(text)
                self._status_sig.emit("", C["muted"])
            else:
                self._status_sig.emit(
                    "⚠  Nothing recognized — try speaking louder or use a different mic",
                    C["yellow"],
                )

        threading.Thread(target=_task, daemon=True).start()

    @Slot(str)
    def _on_mic_state(self, state: str):
        self._is_recording = (state == "recording")
        if state == "recording":
            self._mic_btn.setText("⏹")
            self._mic_btn.setStyleSheet(self._mic_style_recording())
            self._mic_btn.setEnabled(True)
            self._entry.setPlaceholderText("Recording… say something, then stop talking")
            self._status_sig.emit("🔴  Listening — waiting for speech…", C["muted"])
        elif state == "transcribing":
            self._mic_btn.setText("⌛")
            self._mic_btn.setEnabled(False)
            self._mic_btn.setStyleSheet(self._mic_style_busy())
            self._entry.setPlaceholderText("Transcribing speech…")
            self._status_sig.emit("⏳  Recognizing speech…", C["accent"])
        else:
            self._mic_btn.setText("🎙")
            self._mic_btn.setEnabled(True)
            self._mic_btn.setStyleSheet(self._mic_style_idle())
            self._entry.setPlaceholderText("Type or press 🎙 to speak…")

    @Slot()
    def _on_speech_detected(self):
        """Called as soon as the VAD detects the first voice activity."""
        self._status_sig.emit("🎤  Speech detected — keep talking…", C["green"])

    @Slot(str, str)
    def _on_status(self, message: str, color: str):
        self._status_lbl.setText(message)
        self._status_lbl.setStyleSheet(f"color:{color}; background:transparent;")
        if message:
            # Auto-clear informational messages after 6 seconds
            QTimer.singleShot(6000, lambda: (
                self._status_lbl.setText(""),
            ) if self._status_lbl.text() == message else None)

    @Slot(str)
    def _on_transcript(self, text: str):
        if self._immediate_cb.isChecked():
            self._send(text)
        else:
            self._entry.setText(text)
            self._entry.setFocus()
            self._entry.selectAll()

    # ── Send / AI pipeline ────────────────────────────────────────────────────

    def _on_send(self):
        msg = self._entry.text().strip()
        if not msg:
            return
        self._entry.clear()
        self._send(msg)

    def _send(self, text: str):
        self._add_bubble("user", text)
        self._history.append({"role": "user", "content": text})
        self._scroll_bottom()

        self._entry.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._mic_btn.setEnabled(False)

        self._streaming_bubble = self._add_bubble("assistant", "…")
        self._scroll_bottom()

        def _stream():
            from services.ai.ollama import chat_ollama, check_ollama
            if not check_ollama():
                self._error_sig.emit("Ollama not running — run: ollama serve")
                return
            chunks: list[str] = []

            def on_tok(chunk):
                chunks.append(chunk)
                self._token_sig.emit("".join(chunks))

            def on_status(text: str):
                if text:
                    self._status_sig.emit(text, C["accent"])
                else:
                    self._status_sig.emit("", C["muted"])

            try:
                full = chat_ollama(
                    self._history, on_token=on_tok, on_status=on_status,
                    mode=self._current_role_id()
                )
                self._history.append({"role": "assistant", "content": full})
                if len(self._history) > 30:
                    self._history = self._history[-30:]
                self._done_sig.emit(full)
            except Exception as e:
                self._error_sig.emit(f"Error: {str(e)[:120]}")

        threading.Thread(target=_stream, daemon=True).start()

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
        lang  = _tts_lang()
        speed = float(config.get("tts_speed", 1.0))

        def _speak():
            from services.ai.tts import speak
            speak(text, lang_code=lang, speed=speed)

        threading.Thread(target=_speak, daemon=True).start()

    @Slot(str)
    def _on_error(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_text(f"⚠ {text}")
        self._streaming_bubble = None
        self._re_enable()

    def _re_enable(self):
        self._entry.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._mic_btn.setEnabled(True)
        self._entry.setFocus()

    def closeEvent(self, event):
        self._stop_rec.set()
        super().closeEvent(event)


# ── Module-level singleton ────────────────────────────────────────────────────

_state: dict = {"window": None}


def show_voice_chat_dialog():
    """Open or raise the voice chat dialog. Call from Qt main thread."""
    w = _state["window"]
    if w is not None:
        try:
            w.show()
            w.activateWindow()
            w.raise_()
            return
        except RuntimeError:
            _state["window"] = None

    w = VoiceChatDialog()
    w.destroyed.connect(lambda: _state.update(window=None))
    _state["window"] = w
    w.show()
    w.activateWindow()
