"""Floating HUD overlays — PySide6.

Two controllers, each a QObject living on the Qt main thread:
  PipeHud       — recording/transcription/dictation status (follows cursor)
  VoiceChatHud  — persistent voice chat panel (top-right corner)

Background threads call the public methods (open/set_status/…); internally
these emit signals that Qt delivers on the main thread, so all QWidget
operations happen where they should.
"""

import ctypes
import ctypes.wintypes
import os
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


# ── Win32 helpers ─────────────────────────────────────────────────────────────

def _win32_cursor() -> tuple[int, int]:
    """Cursor position via Win32 — safe from any thread."""
    class _P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = _P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def _screen_w() -> int:
    return ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN


# ── Base widget ───────────────────────────────────────────────────────────────

class _Rounded(QWidget):
    """Frameless, translucent, always-on-top widget. Rounded rect is painted."""
    _BG     = QColor("#313244")
    _BORDER = QColor("#45475a")

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect().adjusted(1, 1, -1, -1)), 10, 10)
        p.fillPath(path, self._BG)
        p.setPen(QPen(self._BORDER, 1.0))
        p.drawPath(path)


# ── Recording/transcription HUD widget ───────────────────────────────────────

class _PipeWidget(_Rounded):
    """
    Follows the cursor while recording (blink + timer).
    Stops following and shows result/error/saved once recording ends.
    """
    W = 310

    def __init__(self, cx: int, cy: int, stop_cb: Callable):
        super().__init__()
        self._stop_cb   = stop_cb
        self._recording = True
        self._blink_on  = True
        self._t0        = time.time()

        self._build_ui()
        self._reposition(cx, cy)
        self.show()

        self._t_blink = QTimer(self)
        self._t_blink.setInterval(500)
        self._t_blink.timeout.connect(self._blink)

        self._t_cursor = QTimer(self)
        self._t_cursor.setInterval(80)
        self._t_cursor.timeout.connect(self._track_cursor)

        self._t_clock = QTimer(self)
        self._t_clock.setInterval(1000)
        self._t_clock.timeout.connect(self._tick)

        self._t_blink.start()
        self._t_cursor.start()
        self._t_clock.start()

    def _build_ui(self):
        self.setFixedWidth(self.W)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(0)

        # Row 1: icon | status | timer
        r1 = QHBoxLayout()
        r1.setSpacing(0)

        self._icon = QLabel("●")
        self._icon.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._icon.setFixedWidth(18)
        self._icon.setStyleSheet("color: #f38ba8;")
        r1.addWidget(self._icon)

        self._status = QLabel("Запись…  (клик — стоп)")
        self._status.setFont(QFont("Segoe UI", 10))
        self._status.setStyleSheet("color: #cdd6f4; padding-left: 7px;")
        r1.addWidget(self._status, 1)

        self._timer = QLabel("0s")
        self._timer.setFont(QFont("Segoe UI", 9))
        self._timer.setStyleSheet("color: #6c7086;")
        r1.addWidget(self._timer)

        root.addLayout(r1)

        # Row 2: result preview (hidden initially)
        self._result = QLabel()
        self._result.setFont(QFont("Segoe UI", 9))
        self._result.setStyleSheet("color: #a6e3a1; padding-top: 4px;")
        self._result.setWordWrap(True)
        self._result.hide()
        root.addWidget(self._result)

        # Row 3: open-file / open-folder buttons (hidden initially; shown for dictation saves)
        self._btn_row = QWidget()
        bl = QHBoxLayout(self._btn_row)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.setSpacing(6)
        _btn_style = (
            "QPushButton { background:#45475a; color:#89b4fa; border:none;"
            " border-radius:5px; padding:3px 10px; }"
            "QPushButton:hover { background:#585b70; }"
        )
        self._btn_file   = QPushButton("Открыть файл")
        self._btn_folder = QPushButton("Открыть папку")
        for b in (self._btn_file, self._btn_folder):
            b.setFont(QFont("Segoe UI", 9))
            b.setStyleSheet(_btn_style)
        bl.addWidget(self._btn_file)
        bl.addWidget(self._btn_folder)
        self._btn_row.hide()
        root.addWidget(self._btn_row)

        self.adjustSize()

    # ── Positioning ──

    def _reposition(self, cx: int, cy: int):
        sw = _screen_w()
        x  = min(cx + 18, sw - self.W - 20)
        y  = max(cy - 72 - 10, 40)
        self.move(x, y)

    # ── Timer callbacks ──

    def _blink(self):
        if not self._recording:
            self._t_blink.stop()
            return
        self._blink_on = not self._blink_on
        self._icon.setStyleSheet(f"color: {'#f38ba8' if self._blink_on else '#45475a'};")

    def _track_cursor(self):
        if not self._recording:
            self._t_cursor.stop()
            return
        self._reposition(*_win32_cursor())

    def _tick(self):
        if not self._recording:
            self._t_clock.stop()
            return
        self._timer.setText(f"{int(time.time() - self._t0)}s")

    def _stop_timers(self):
        self._recording = False
        self._t_blink.stop()
        self._t_cursor.stop()
        self._t_clock.stop()

    # ── State setters (called from Qt main thread via PipeHud slots) ──

    def set_status(self, text: str, icon: str = "◌", color: str = "#89b4fa"):
        self._stop_timers()
        self._icon.setText(icon)
        self._icon.setStyleSheet(f"color: {color};")
        self._status.setText(text)
        self._status.setStyleSheet("color: #cdd6f4; padding-left: 7px;")
        self._timer.setText("")

    def show_result(self, text: str):
        self._stop_timers()
        self._icon.setText("✓")
        self._icon.setStyleSheet("color: #a6e3a1;")
        self._status.setText("Скопировано в буфер")
        self._status.setStyleSheet("color: #a6e3a1; padding-left: 7px;")
        self._timer.setText("")
        preview = text[:130].rstrip() + ("…" if len(text) > 130 else "")
        self._result.setText(preview)
        self._result.show()
        self.adjustSize()

    def show_error(self, text: str):
        self._stop_timers()
        self._icon.setText("✗")
        self._icon.setStyleSheet("color: #f38ba8;")
        self._status.setText(text[:80])
        self._status.setStyleSheet("color: #f38ba8; padding-left: 7px;")
        self._timer.setText("")

    def show_saved(self, filepath: str, filename: str, preview: str):
        """Used by dictation: show save confirmation with open buttons."""
        self._stop_timers()
        self._icon.setText("✓")
        self._icon.setStyleSheet("color: #a6e3a1;")
        self._status.setText(f"Сохранено: {filename}")
        self._status.setStyleSheet("color: #a6e3a1; padding-left: 7px;")
        self._timer.setText("")
        self._result.setText(preview[:120].rstrip() + ("…" if len(preview) > 120 else ""))
        self._result.show()
        # wire buttons (disconnect first to avoid double-triggers if reused)
        for btn in (self._btn_file, self._btn_folder):
            try:
                btn.clicked.disconnect()
            except RuntimeError:
                pass
        fp = Path(filepath)
        self._btn_file.clicked.connect(lambda: _os_open(str(fp)))
        self._btn_folder.clicked.connect(lambda: _os_open(str(fp.parent)))
        self._btn_row.show()
        self.adjustSize()

    # ── Mouse / keyboard ──

    def mousePressEvent(self, _e):
        self._stop_cb()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._stop_cb()


def _os_open(path: str):
    try:
        os.startfile(path)
    except Exception:
        pass


# ── Voice-chat panel widget ───────────────────────────────────────────────────

class _VoiceChatWidget(_Rounded):
    """Fixed panel in the top-right corner. Click = interrupt TTS."""
    W, H = 320, 78

    _ICONS   = {"listening": "🎙", "thinking": "◌", "speaking": "🔊", "error": "✕"}
    _COLORS  = {"listening": "#a6e3a1", "thinking": "#89b4fa", "speaking": "#fab387", "error": "#f38ba8"}
    _LABELS  = {"listening": "Слушаю…", "thinking": "Думаю…", "speaking": "Говорю…", "error": "Ошибка"}

    def __init__(self, stop_cb: Callable, interrupt_cb: Callable):
        super().__init__()
        self._stop_cb      = stop_cb
        self._interrupt_cb = interrupt_cb
        self._build_ui()
        self.setFixedSize(self.W, self.H)
        self.move(_screen_w() - self.W - 24, 60)
        self.show()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(0)

        hdr = QHBoxLayout()
        hdr.setSpacing(0)

        self._icon = QLabel("🎙")
        self._icon.setFont(QFont("Segoe UI", 14))
        self._icon.setFixedWidth(24)
        hdr.addWidget(self._icon)

        self._state_lbl = QLabel("Слушаю…")
        self._state_lbl.setFont(QFont("Segoe UI", 10))
        self._state_lbl.setStyleSheet("color: #a6e3a1; padding-left: 6px;")
        hdr.addWidget(self._state_lbl, 1)

        close = QLabel("✕")
        close.setFont(QFont("Segoe UI", 10))
        close.setStyleSheet("color: #6c7086; padding: 2px 4px;")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.mousePressEvent = lambda _: self._stop_cb()
        hdr.addWidget(close)

        root.addLayout(hdr)

        self._sub = QLabel()
        self._sub.setFont(QFont("Segoe UI", 8))
        self._sub.setStyleSheet("color: #6c7086; padding-top: 2px;")
        self._sub.setWordWrap(True)
        root.addWidget(self._sub)

    def set_state(self, state: str, sub: str = ""):
        self._icon.setText(self._ICONS.get(state, "◦"))
        color = self._COLORS.get(state, "#cdd6f4")
        self._state_lbl.setStyleSheet(f"color: {color}; padding-left: 6px;")
        self._state_lbl.setText(self._LABELS.get(state, state))
        self._sub.setText(sub[:80] if sub else "")

    def mousePressEvent(self, _e):
        self._interrupt_cb()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._stop_cb()


# ── Controllers ───────────────────────────────────────────────────────────────

class PipeHud(QObject):
    """
    Thread-safe controller for the recording/transcription HUD.
    All public methods are safe to call from any thread.
    Connect `clicked` to the stop-recording event before first use.
    """
    clicked = Signal()               # emitted when user clicks the HUD

    _open_sig   = Signal(int, int)
    _status_sig = Signal(str, str, str)   # text, icon, color
    _result_sig = Signal(str)
    _error_sig  = Signal(str)
    _saved_sig  = Signal(str, str, str)   # filepath, filename, preview
    _close_sig  = Signal()

    def __init__(self):
        super().__init__()
        self._widget: Optional[_PipeWidget] = None
        self._open_sig.connect(self._do_open)
        self._status_sig.connect(self._do_status)
        self._result_sig.connect(self._do_result)
        self._error_sig.connect(self._do_error)
        self._saved_sig.connect(self._do_saved)
        self._close_sig.connect(self._do_close)

    # ── Public API (any thread) ──

    def open(self, cx: int, cy: int):
        self._open_sig.emit(cx, cy)

    def set_status(self, text: str, icon: str = "◌", color: str = "#89b4fa"):
        self._status_sig.emit(text, icon, color)

    def show_result(self, text: str):
        self._result_sig.emit(text)

    def show_error(self, text: str):
        self._error_sig.emit(text)

    def show_saved(self, filepath: str, filename: str, preview: str):
        self._saved_sig.emit(filepath, filename, preview)

    def close(self):
        self._close_sig.emit()

    # ── Slots (Qt main thread) ──

    @Slot(int, int)
    def _do_open(self, cx: int, cy: int):
        if self._widget:
            self._widget.close()
        self._widget = _PipeWidget(cx, cy, stop_cb=self.clicked.emit)
        self._widget.destroyed.connect(lambda: setattr(self, "_widget", None))

    @Slot(str, str, str)
    def _do_status(self, text: str, icon: str, color: str):
        if self._widget:
            self._widget.set_status(text, icon, color)

    @Slot(str)
    def _do_result(self, text: str):
        if self._widget:
            self._widget.show_result(text)
            QTimer.singleShot(1500, self._do_close)

    @Slot(str)
    def _do_error(self, text: str):
        if self._widget:
            self._widget.show_error(text)
            QTimer.singleShot(4000, self._do_close)

    @Slot(str, str, str)
    def _do_saved(self, filepath: str, filename: str, preview: str):
        if self._widget:
            self._widget.show_saved(filepath, filename, preview)
            QTimer.singleShot(2500, self._do_close)

    @Slot()
    def _do_close(self):
        if self._widget:
            self._widget.close()
            self._widget = None


class VoiceChatHud(QObject):
    """
    Thread-safe controller for the voice chat panel.
    Emit `clicked` to interrupt TTS, `closed` when the user shuts the panel.
    Connect these signals to your stop/interrupt events before calling open().
    """
    clicked = Signal()   # user clicked window body → interrupt TTS
    closed  = Signal()   # user pressed ✕ or Escape → stop session

    _open_sig  = Signal()
    _state_sig = Signal(str, str)   # state, sub_text
    _close_sig = Signal()

    def __init__(self):
        super().__init__()
        self._widget: Optional[_VoiceChatWidget] = None
        self._open_sig.connect(self._do_open)
        self._state_sig.connect(self._do_state)
        self._close_sig.connect(self._do_close)

    # ── Public API (any thread) ──

    def open(self):
        self._open_sig.emit()

    def set_state(self, state: str, sub: str = ""):
        self._state_sig.emit(state, sub)

    def close(self):
        self._close_sig.emit()

    # ── Slots (Qt main thread) ──

    @Slot()
    def _do_open(self):
        if self._widget:
            self._widget.close()
        self._widget = _VoiceChatWidget(
            stop_cb=self.closed.emit,
            interrupt_cb=self.clicked.emit,
        )
        self._widget.destroyed.connect(lambda: setattr(self, "_widget", None))

    @Slot(str, str)
    def _do_state(self, state: str, sub: str):
        if self._widget:
            self._widget.set_state(state, sub)

    @Slot()
    def _do_close(self):
        if self._widget:
            self._widget.close()
            self._widget = None


# ── Module-level singletons ───────────────────────────────────────────────────

_pipe_hud: Optional[PipeHud]       = None
_vc_hud:   Optional[VoiceChatHud]  = None


def init_pipe_hud(stop_event) -> PipeHud:
    """Create the PipeHud singleton. Call once after QApplication exists."""
    global _pipe_hud
    if _pipe_hud is None:
        _pipe_hud = PipeHud()
        _pipe_hud.clicked.connect(stop_event.set)
    return _pipe_hud


def get_pipe_hud() -> Optional[PipeHud]:
    return _pipe_hud


def init_vc_hud() -> VoiceChatHud:
    """Create the VoiceChatHud singleton. Must be called from the Qt main thread."""
    global _vc_hud
    if _vc_hud is None:
        _vc_hud = VoiceChatHud()
    return _vc_hud


def get_vc_hud() -> Optional[VoiceChatHud]:
    return _vc_hud
