"""Toast notifications — PySide6, thread-safe via QObject signal manager."""

import ctypes
import ctypes.wintypes
import logging
from typing import Optional

from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

log = logging.getLogger("notifications")

_SURFACE = "#313244"
_BORDER  = "#585b70"
_ACCENT  = "#89b4fa"
_TEXT    = "#cdd6f4"
_MUTED   = "#6c7086"

_GWL_EXSTYLE      = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080


def _cursor_pos() -> tuple[int, int]:
    class _P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = _P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _screen_wh() -> tuple[int, int]:
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def _noactivate(hwnd: int):
    try:
        u = ctypes.windll.user32
        st = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, _GWL_EXSTYLE, st | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
    except Exception as e:
        log.debug("noactivate failed: %s", e)


class _Toast(QWidget):
    """Frameless notification widget that fades out after duration_ms."""

    def __init__(self, message: str, duration_ms: int, translation: bool = False):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowOpacity(0.95)
        self._translation = translation

        lo = QVBoxLayout(self)
        lo.setContentsMargins(14, 10, 14, 10)
        lo.setSpacing(3)

        sw, sh = _screen_wh()
        max_w = min(460, sw - 40)

        if translation:
            hdr = QLabel("Translation")
            hdr.setFont(QFont("Segoe UI Semibold", 9))
            hdr.setStyleSheet(f"color: {_ACCENT};")
            lo.addWidget(hdr)

        lbl = QLabel(message)
        lbl.setFont(QFont("Segoe UI", 12))
        lbl.setStyleSheet(f"color: {_TEXT};")
        if translation:
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(max_w - 40)
        lo.addWidget(lbl)

        if translation:
            hint = QLabel("copied to clipboard  •  click to close")
            hint.setFont(QFont("Segoe UI", 8))
            hint.setStyleSheet(f"color: {_MUTED};")
            lo.addWidget(hint)

        self.adjustSize()

        cx, cy = _cursor_pos()
        if translation:
            x = min(cx + 20, sw - self.width() - 20)
            y = max(cy - 60, 40)
            if y + self.height() > sh - 40:
                y = sh - self.height() - 40
        else:
            x = cx + 20
            y = max(cy - 40, 10)

        self.move(x, y)
        self.show()
        _noactivate(int(self.winId()))

        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._fade)
        t.start(duration_ms)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect().adjusted(1, 1, -1, -1)), 8, 8)
        p.fillPath(path, QColor(_SURFACE))
        border_color = _ACCENT if self._translation else _BORDER
        p.setPen(QPen(QColor(border_color), 1.5 if self._translation else 1.0))
        p.drawPath(path)

    def mousePressEvent(self, _e):
        if self._translation:
            self.close()

    def _fade(self):
        op = self.windowOpacity() - 0.07
        if op <= 0:
            self.close()
            return
        self.setWindowOpacity(op)
        QTimer.singleShot(30, self._fade)


class _ToastManager(QObject):
    """Lives on the Qt main thread; shows toasts on behalf of background threads."""
    _plain_sig = Signal(str, int)
    _trans_sig = Signal(str, int)

    def __init__(self):
        super().__init__()
        self._plain_sig.connect(self._on_plain)
        self._trans_sig.connect(self._on_trans)

    @Slot(str, int)
    def _on_plain(self, msg: str, ms: int):
        _Toast(msg, ms, translation=False)

    @Slot(str, int)
    def _on_trans(self, msg: str, ms: int):
        _Toast(msg, ms, translation=True)


_manager: Optional[_ToastManager] = None


def setup_notifications() -> _ToastManager:
    """Create the singleton. Must be called from the Qt main thread in main.py."""
    global _manager
    if _manager is None:
        _manager = _ToastManager()
    return _manager


def show_toast(message: str, duration_ms: int = 2000):
    if _manager is not None:
        _manager._plain_sig.emit(message, duration_ms)
    else:
        log.warning("show_toast called before setup_notifications: %s", message)


def show_translation_toast(message: str, duration_ms: int = 5000):
    if _manager is not None:
        _manager._trans_sig.emit(message, duration_ms)
    else:
        log.warning("show_translation_toast before setup_notifications: %s", message)


def play_success_sound():
    """Play a success beep notification."""
    try:
        import winsound
        # 800 Hz for 150 ms
        winsound.Beep(800, 150)
    except Exception as e:
        log.debug("Failed to play beep: %s", e)


def play_timer_alert():
    """Play timer finished alert (like microwave or toaster beep)."""
    try:
        import winsound
        # Triple beep pattern: 3 rapid beeps
        for _ in range(3):
            winsound.Beep(1000, 200)  # 1000 Hz for 200 ms
            import time
            time.sleep(0.1)
    except Exception as e:
        log.debug("Failed to play timer alert: %s", e)
