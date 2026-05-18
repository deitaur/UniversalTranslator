"""
ZBrush-style Tool Shelf — horizontal icon strip near cursor.

Appears on tray double-click (or programmatically).
Each tool = 36×36 square, letter/symbol 16pt, 7pt label below.
Colors: #c8c8c8 on #3a3a3a. Active/hover = accent blue.
Auto-hides after 4s of inactivity or on click-outside.
"""

import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.hud import _win32_cursor, _screen_w

_ZB_BG     = "#3a3a3a"
_ZB_TEXT   = "#c8c8c8"
_ZB_DIM    = "#888888"
_ZB_HOVER  = "#88aadd"
_ZB_ACTIVE = "#88aadd"
_TOOL_W    = 42
_TOOL_H    = 46
_FONT_ICON = QFont("Segoe UI", 14)
_FONT_LBL  = QFont("Segoe UI", 7)


# ── Single tool button ────────────────────────────────────────────────────────

class _ToolBtn(QWidget):
    def __init__(self, icon: str, label: str, tooltip: str, callback: Callable):
        super().__init__()
        self._cb      = callback
        self._hovered = False
        self.setFixedSize(_TOOL_W, _TOOL_H)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 4, 0, 2)
        lo.setSpacing(0)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFont(_FONT_ICON)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._icon_lbl.setStyleSheet(f"color: {_ZB_TEXT}; background: transparent;")
        lo.addWidget(self._icon_lbl)

        self._sub_lbl = QLabel(label)
        self._sub_lbl.setFont(_FONT_LBL)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._sub_lbl.setStyleSheet(f"color: {_ZB_DIM}; background: transparent;")
        lo.addWidget(self._sub_lbl)

    def enterEvent(self, _e):
        self._hovered = True
        self._icon_lbl.setStyleSheet(f"color: {_ZB_HOVER}; background: transparent;")
        self._sub_lbl.setStyleSheet(f"color: {_ZB_HOVER}; background: transparent;")
        self.update()

    def leaveEvent(self, _e):
        self._hovered = False
        self._icon_lbl.setStyleSheet(f"color: {_ZB_TEXT}; background: transparent;")
        self._sub_lbl.setStyleSheet(f"color: {_ZB_DIM}; background: transparent;")
        self.update()

    def mousePressEvent(self, _e):
        self._cb()

    def paintEvent(self, _e):
        if self._hovered:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(2, 2, _TOOL_W - 4, _TOOL_H - 4), 3, 3)
            p.fillPath(path, QColor("#4a4a4a"))


# ── Shelf widget ──────────────────────────────────────────────────────────────

class _ShelfWidget(QWidget):
    def __init__(self, tools: list[tuple], cx: int, cy: int, on_close: Callable):
        super().__init__()
        self._on_close = on_close
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(6, 4, 6, 4)
        lo.setSpacing(2)

        for icon, label, tooltip, hotkey, cb in tools:
            tip = f"{tooltip}  {hotkey}" if hotkey else tooltip

            def _make_cb(callback, shelf=self):
                def _wrapped():
                    shelf.close()
                    callback()
                return _wrapped

            btn = _ToolBtn(icon, label, tip, _make_cb(cb))
            lo.addWidget(btn)

        self.adjustSize()
        sw = _screen_w()
        x  = min(cx - self.width() // 2, sw - self.width() - 12)
        x  = max(x, 12)
        y  = cy - self.height() - 12
        self.move(x, y)
        self.show()

        # Auto-hide after 4 seconds of no interaction
        self._t_hide = QTimer(self)
        self._t_hide.setSingleShot(True)
        self._t_hide.setInterval(4000)
        self._t_hide.timeout.connect(self.close)
        self._t_hide.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 4, 4)
        p.fillPath(path, QColor(_ZB_BG))

    def enterEvent(self, _e):
        self._t_hide.stop()

    def leaveEvent(self, _e):
        self._t_hide.start()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, e):
        self._on_close()
        super().closeEvent(e)


# ── Controller ────────────────────────────────────────────────────────────────

class ToolShelf(QObject):
    """Thread-safe tool shelf controller."""
    _show_sig = Signal(object, int, int)

    def __init__(self):
        super().__init__()
        self._widget: Optional[_ShelfWidget] = None
        self._tools:  list[tuple]            = []
        self._show_sig.connect(self._do_show)

    def set_tools(self, tools: list[tuple]):
        """
        tools = list of (icon, label, tooltip, hotkey_str, callback)
        Example: ("T", "trnsl", "Translation popup", "Ctrl+Alt+T", fn)
        """
        self._tools = tools

    def show_at_cursor(self):
        """Show shelf near cursor. Safe to call from any thread."""
        cx, cy = _win32_cursor()
        self._show_sig.emit(self._tools, cx, cy)

    @Slot(object, int, int)
    def _do_show(self, tools, cx: int, cy: int):
        if self._widget:
            self._widget.close()
        self._widget = _ShelfWidget(
            tools, cx, cy,
            on_close=lambda: setattr(self, "_widget", None),
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_shelf: Optional[ToolShelf] = None


def get_tool_shelf() -> Optional[ToolShelf]:
    return _shelf


def init_tool_shelf(tools: list[tuple]) -> ToolShelf:
    """Create singleton. Call once after QApplication exists."""
    global _shelf
    if _shelf is None:
        _shelf = ToolShelf()
        _shelf.set_tools(tools)
    return _shelf


def show_tool_shelf():
    """Show the shelf near cursor. Safe from any thread."""
    if _shelf:
        _shelf.show_at_cursor()
