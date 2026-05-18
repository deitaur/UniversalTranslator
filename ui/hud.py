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
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
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


# ── ZBrush-style status bar widget ───────────────────────────────────────────
#
# Thin horizontal bar that follows the cursor at all pipeline stages.
# Colors: dark gray bg, lighter gray text — matches ZBrush's status line.

_ZB_BG      = "#3a3a3a"   # ZBrush dark gray
_ZB_TEXT    = "#c8c8c8"   # light gray — noticeably lighter than bg
_ZB_DIM     = "#888888"   # timer / secondary info
_ZB_REC     = "#e06060"   # recording dot (warm red)
_ZB_OK      = "#80cc80"   # success green
_ZB_ERR     = "#e06060"   # error red
_ZB_ACCENT  = "#88aadd"   # processing blue
_ZB_FONT    = "Segoe UI"
_ZB_SIZE    = 9           # pt — small, like ZBrush


class _PipeWidget(QWidget):
    """
    ZBrush-style status bar that follows the cursor.
    Single line during recording/processing; adds a preview line on result/saved.
    Follows cursor at ALL stages — stops only after final result is shown.
    """
    _MIN_W = 220
    _MAX_W = 480

    def __init__(self, cx: int, cy: int, stop_cb: Callable):
        super().__init__()
        self._stop_cb  = stop_cb
        self._t0       = time.time()
        self._blink_on = True
        self._follow   = True   # keep tracking cursor until done

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_ui()
        self._reposition(cx, cy)
        self.show()

        self._t_blink  = QTimer(self); self._t_blink.setInterval(500);  self._t_blink.timeout.connect(self._blink)
        self._t_cursor = QTimer(self); self._t_cursor.setInterval(60);  self._t_cursor.timeout.connect(self._track)
        self._t_clock  = QTimer(self); self._t_clock.setInterval(1000); self._t_clock.timeout.connect(self._tick)
        self._t_blink.start()
        self._t_cursor.start()
        self._t_clock.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 3, 8, 3)
        root.setSpacing(1)

        # ── Main status row ──
        row = QHBoxLayout()
        row.setSpacing(5)
        row.setContentsMargins(0, 0, 0, 0)

        self._dot = QLabel("●")
        self._dot.setFont(QFont(_ZB_FONT, 7, QFont.Weight.Bold))
        self._dot.setFixedWidth(10)
        self._dot.setStyleSheet(f"color: {_ZB_REC};")
        row.addWidget(self._dot)

        self._status = QLabel("rec  (click to stop)")
        f = QFont(_ZB_FONT, _ZB_SIZE)
        self._status.setFont(f)
        self._status.setStyleSheet(f"color: {_ZB_TEXT};")
        row.addWidget(self._status, 1)

        self._timer = QLabel("0s")
        self._timer.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        self._timer.setStyleSheet(f"color: {_ZB_DIM};")
        row.addWidget(self._timer)

        root.addLayout(row)

        # ── Preview line (result / saved) ──
        self._preview = QLabel()
        self._preview.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        self._preview.setStyleSheet(f"color: {_ZB_DIM};")
        self._preview.setWordWrap(True)
        self._preview.hide()
        root.addWidget(self._preview)

        # ── Dictation buttons (open file / folder) ──
        self._btn_row = QWidget()
        bl = QHBoxLayout(self._btn_row)
        bl.setContentsMargins(0, 2, 0, 0)
        bl.setSpacing(4)
        _bs = (f"QPushButton {{ background:#505050; color:{_ZB_TEXT}; border:none;"
               f" padding:2px 8px; font-size:8pt; }}"
               f"QPushButton:hover {{ background:#686868; }}")
        self._btn_file   = QPushButton("open file")
        self._btn_folder = QPushButton("open folder")
        for b in (self._btn_file, self._btn_folder):
            b.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
            b.setStyleSheet(_bs)
        bl.addWidget(self._btn_file)
        bl.addWidget(self._btn_folder)
        self._btn_row.hide()
        root.addWidget(self._btn_row)

        self._refresh_width()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 2, 2)
        p.fillPath(path, QColor(_ZB_BG))

    # ── Layout helpers ──

    def _refresh_width(self):
        self.adjustSize()
        w = max(self._MIN_W, min(self.sizeHint().width() + 4, self._MAX_W))
        self.setFixedWidth(w)
        self.adjustSize()

    # ── Cursor tracking ──

    def _reposition(self, cx: int, cy: int):
        sw = _screen_w()
        w  = self.width() or self._MIN_W
        x  = min(cx + 16, sw - w - 12)
        y  = cy + 18        # just below cursor arrow
        self.move(x, y)

    def _track(self):
        if self._follow:
            self._reposition(*_win32_cursor())

    # ── Blink / timer ──

    def _blink(self):
        self._blink_on = not self._blink_on
        if self._blink_on:
            self._dot.setStyleSheet(f"color: {_ZB_REC};")
        else:
            self._dot.setStyleSheet(f"color: #606060;")

    def _tick(self):
        self._timer.setText(f"{int(time.time() - self._t0)}s")

    # ── State setters ──

    def set_status(self, text: str, _icon: str = "◌", color: str = _ZB_ACCENT):
        """Processing stage — keep following cursor, swap dot color."""
        self._t_blink.stop()
        self._dot.setStyleSheet(f"color: {color};")
        self._dot.setText("▸")
        self._status.setText(text)
        self._timer.setText("")
        self._t_clock.stop()
        self._refresh_width()

    def show_result(self, text: str):
        self._follow = False
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✓")
        self._dot.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setText("done")
        self._timer.setText("")
        if text:
            self._preview.setStyleSheet(f"color: {_ZB_DIM};")
            self._preview.setText(text[:100] + ("…" if len(text) > 100 else ""))
            self._preview.show()
        self._refresh_width()

    def show_error(self, text: str):
        self._follow = False
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✕")
        self._dot.setStyleSheet(f"color: {_ZB_ERR};")
        self._status.setStyleSheet(f"color: {_ZB_ERR};")
        self._status.setText(text[:90])
        self._timer.setText("")
        self._refresh_width()

    def show_saved(self, filepath: str, filename: str, preview: str):
        self._follow = False
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✓")
        self._dot.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setText(f"saved  {filename}")
        self._timer.setText("")
        self._preview.setStyleSheet(f"color: {_ZB_DIM};")
        self._preview.setText(preview[:90] + ("…" if len(preview) > 90 else ""))
        self._preview.show()
        for btn in (self._btn_file, self._btn_folder):
            try:
                btn.clicked.disconnect()
            except RuntimeError:
                pass
        fp = Path(filepath)
        self._btn_file.clicked.connect(lambda: _os_open(str(fp)))
        self._btn_folder.clicked.connect(lambda: _os_open(str(fp.parent)))
        self._btn_row.show()
        self._refresh_width()

    # ── Input ──

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

class _VoiceChatWidget(QWidget):
    """Fixed panel in the top-right corner. Click = interrupt TTS."""
    W, H = 320, 78

    _ICONS   = {"listening": "🎙", "thinking": "◌", "speaking": "🔊", "error": "✕"}
    _COLORS  = {"listening": "#a6e3a1", "thinking": "#89b4fa", "speaking": "#fab387", "error": "#f38ba8"}
    _LABELS  = {"listening": "Слушаю…", "thinking": "Думаю…", "speaking": "Говорю…", "error": "Ошибка"}

    def __init__(self, stop_cb: Callable, interrupt_cb: Callable):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._stop_cb      = stop_cb
        self._interrupt_cb = interrupt_cb
        self._build_ui()
        self.setFixedSize(self.W, self.H)
        self.move(_screen_w() - self.W - 24, 60)
        self.show()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect().adjusted(1, 1, -1, -1)), 10, 10)
        p.fillPath(path, QColor("#313244"))
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor("#45475a"), 1.0))
        p.drawPath(path)

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


# ── ZBrush-style prerequisite overlay ────────────────────────────────────────

class _PrereqWidget(QWidget):
    """
    Non-blocking prereq check overlay — appears near cursor.
    Rows: [dot] label  [status]  [action-btn?]
    """
    _W = 340

    def __init__(self, cx: int, cy: int, checks: dict, on_proceed, on_cancel):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._on_proceed = on_proceed
        self._on_cancel  = on_cancel
        self._checks     = checks
        self._pkg_missing = []
        for key, c in checks.items():
            if key == "packages" and c["ok"] is False:
                for part in c.get("detail", "").split("\n"):
                    if "pip install" in part:
                        self._pkg_missing.extend(
                            part.strip().replace("pip install ", "").split())

        self._build_ui()
        sw = _screen_w()
        x  = min(cx + 16, sw - self._W - 12)
        y  = cy + 20
        self.move(x, y)
        self.show()

    def _build_ui(self):
        self.setFixedWidth(self._W)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(3)

        _lf = QFont(_ZB_FONT, _ZB_SIZE)
        _bf = QFont(_ZB_FONT, _ZB_SIZE)
        _bf.setBold(True)

        # ── Header row ──
        hdr = QHBoxLayout()
        hdr.setSpacing(5)
        t = QLabel("prerequisites")
        t.setFont(_bf)
        t.setStyleSheet(f"color: {_ZB_TEXT};")
        hdr.addWidget(t)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Check rows ──
        for key, c in self._checks.items():
            ok, optional = c["ok"], c.get("optional", False)
            if ok is True:
                dot, color = "●", _ZB_OK
            elif ok is False and optional:
                dot, color = "●", "#c8a040"
            elif ok is False:
                dot, color = "●", _ZB_ERR
            else:
                dot, color = "◦", _ZB_DIM

            row = QHBoxLayout()
            row.setSpacing(5)

            d = QLabel(dot)
            d.setFont(QFont(_ZB_FONT, 7))
            d.setFixedWidth(9)
            d.setStyleSheet(f"color: {color};")
            row.addWidget(d)

            lbl = QLabel(c["label"])
            lbl.setFont(_lf)
            lbl.setStyleSheet(f"color: {_ZB_TEXT};")
            lbl.setFixedWidth(130)
            row.addWidget(lbl)

            detail = QLabel(c["detail"][:45])
            detail.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
            detail.setStyleSheet(f"color: {color if ok is not True else _ZB_DIM};")
            row.addWidget(detail, 1)

            root.addLayout(row)

        # ── Divider ──
        div = QLabel()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: #505050;")
        root.addWidget(div)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addStretch()

        _bs = (f"QPushButton {{ background:#505050; color:{_ZB_TEXT}; border:none;"
               f" padding:2px 8px; font-size:8pt; }}"
               f"QPushButton:hover {{ background:#686868; }}")

        cancel = QPushButton("cancel")
        cancel.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        cancel.setStyleSheet(_bs)
        cancel.clicked.connect(self._cancel)
        btn_row.addWidget(cancel)

        if self._pkg_missing:
            install = QPushButton("install packages")
            install.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
            install.setStyleSheet(_bs.replace(_ZB_TEXT, "#c8a040"))
            install.clicked.connect(self._install)
            btn_row.addWidget(install)

        ready = all(c["ok"] is not False for c in self._checks.values()
                    if not c.get("optional"))
        proceed_lbl = "proceed" if ready else "proceed anyway"
        proceed_col = _ZB_OK if ready else "#c8a040"
        proceed = QPushButton(proceed_lbl)
        proceed.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        proceed.setStyleSheet(_bs.replace(_ZB_TEXT, proceed_col))
        proceed.clicked.connect(self._proceed)
        btn_row.addWidget(proceed)

        root.addLayout(btn_row)
        self.adjustSize()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 2, 2)
        p.fillPath(path, QColor(_ZB_BG))

    def _proceed(self):
        self.close()
        if self._on_proceed:
            self._on_proceed()

    def _cancel(self):
        self.close()
        if self._on_cancel:
            self._on_cancel()

    def _install(self):
        import subprocess
        try:
            subprocess.Popen(
                ["cmd", "/k", "pip", "install"] + self._pkg_missing,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            from ui.notifications import show_toast
            show_toast(f"Error: {e}")

    def mousePressEvent(self, _e):
        pass   # don't close on click — user needs to read it

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()


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
    _prereq_sig = Signal(object, object, object)  # checks, on_proceed, on_cancel

    def __init__(self):
        super().__init__()
        self._widget: Optional[_PipeWidget] = None
        self._prereq_widget: Optional[_PrereqWidget] = None
        self._open_sig.connect(self._do_open)
        self._status_sig.connect(self._do_status)
        self._result_sig.connect(self._do_result)
        self._error_sig.connect(self._do_error)
        self._saved_sig.connect(self._do_saved)
        self._close_sig.connect(self._do_close)
        self._prereq_sig.connect(self._do_prereq)

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

    def flash_action(self, text: str, ms: int = 900):
        """Show action name near cursor for ms milliseconds (hotkey feedback)."""
        cx, cy = _win32_cursor()
        self._open_sig.emit(cx, cy)
        self._status_sig.emit(text, "▸", _ZB_ACCENT)
        QTimer.singleShot(ms, self._do_close)

    def show_prereq(self, checks: dict, on_proceed, on_cancel=None):
        """Show non-blocking prereq overlay near cursor. Safe to call from any thread."""
        self._prereq_sig.emit(checks, on_proceed, on_cancel)

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

    @Slot(object, object, object)
    def _do_prereq(self, checks, on_proceed, on_cancel):
        if self._prereq_widget:
            self._prereq_widget.close()
        cx, cy = _win32_cursor()
        self._prereq_widget = _PrereqWidget(cx, cy, checks, on_proceed, on_cancel)
        self._prereq_widget.destroyed.connect(
            lambda: setattr(self, "_prereq_widget", None))


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
