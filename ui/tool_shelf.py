"""
ZBrush-style Tool Shelf — horizontal icon strip above the taskbar.

Header has three tiny icon buttons:
  ●/○  (top-left)   — pin toggle. Pinned → always visible. Unpinned → auto-hides.
  _    (top-right)  — hide the shelf (re-open from tray menu).
  ✕    (top-right)  — quit the entire program.

When unpinned: 3s after the mouse leaves the shelf, it hides. To bring it
back, the controller polls cursor position and shows the shelf when the
cursor enters a thin "hot zone" along the bottom edge of the screen.

Position + pin state persist in config[tool_shelf_x|y|pinned].
"""

from typing import Callable, Optional

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import config, save_config_full
from ui.hud import _work_area

_ZB_BG     = "#3a3a3a"
_ZB_TEXT   = "#c8c8c8"
_ZB_DIM    = "#888888"
_ZB_HOVER  = "#88aadd"
_ZB_CLOSE  = "#e06060"
_ZB_PIN_ON = "#a6e3a1"   # green when pinned
_TOOL_W    = 42
_TOOL_H    = 46
_FONT_ICON = QFont("Segoe UI", 14)
_FONT_LBL  = QFont("Segoe UI", 7)

_DRAG_THRESHOLD   = 4      # px — distinguishes drag from click
_AUTOHIDE_DELAY   = 3000   # ms — how long to wait before hiding when unpinned
_HOT_ZONE_THICK   = 6      # px — bottom-edge strip that re-shows the shelf
_POLL_INTERVAL    = 200    # ms — how often the controller checks cursor position


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


# ── Tiny icon button (10×10 ish) ──────────────────────────────────────────────

class _IconBtn(QLabel):
    """Clickable single-character icon. Used for pin/hide/quit chrome."""

    def __init__(self, icon: str, color: str, hover_color: str,
                 tooltip: str, on_click: Callable, size: int = 12):
        super().__init__(icon)
        self._on_click      = on_click
        self._default_color = color
        self._hover_color   = hover_color
        self.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)

    def set_icon(self, icon: str, color: str, hover_color: str, tooltip: str):
        self.setText(icon)
        self._default_color = color
        self._hover_color = hover_color
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setToolTip(tooltip)

    def enterEvent(self, _e):
        self.setStyleSheet(f"color: {self._hover_color}; background: transparent;")

    def leaveEvent(self, _e):
        self.setStyleSheet(f"color: {self._default_color}; background: transparent;")

    def mousePressEvent(self, _e):
        self._on_click()


# ── Shelf widget ──────────────────────────────────────────────────────────────

class _ShelfWidget(QWidget):
    def __init__(self, tools: list[tuple], pinned: bool,
                 on_pin_toggle: Callable, on_hide: Callable, on_quit: Callable,
                 on_move: Callable):
        super().__init__()
        self._on_hide     = on_hide
        self._on_move     = on_move
        self._pinned      = pinned
        self._drag_pos: Optional[QPoint] = None
        self._dragging    = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(0)

        # ── Header: pin (L) ………… hide + quit (R) ─────────────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(2, 0, 2, 0)
        hdr.setSpacing(4)

        self._pin_btn = _IconBtn(
            *self._pin_visuals(pinned),
            on_click=on_pin_toggle,
            size=12,
        )
        hdr.addWidget(self._pin_btn)
        hdr.addStretch()

        hdr.addWidget(_IconBtn(
            "_", _ZB_DIM, _ZB_TEXT,
            "Hide  (re-open from tray menu)",
            on_hide, size=12,
        ))
        hdr.addWidget(_IconBtn(
            "✕", _ZB_DIM, _ZB_CLOSE,
            "Quit Universal Translator",
            on_quit, size=12,
        ))
        root.addLayout(hdr)

        # ── Tool row ──────────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(2)
        for icon, label, tooltip, hotkey, cb in tools:
            tip = f"{tooltip}  {hotkey}" if hotkey else tooltip
            btn = _ToolBtn(icon, label, tip, cb)
            row.addWidget(btn)

        # Add timers
        try:
            from ui.timers import TimerWidget90, TimerWidget20
            row.addWidget(TimerWidget90())
            row.addWidget(TimerWidget20())
        except Exception as e:
            import logging
            logging.getLogger("tool_shelf").error("Failed to load timers: %s", e, exc_info=True)

        root.addLayout(row)

        # ── Auto-hide timer (active only when unpinned) ───────────────────────
        self._autohide_timer = QTimer(self)
        self._autohide_timer.setSingleShot(True)
        self._autohide_timer.timeout.connect(self._on_hide_fired)

        self.adjustSize()
        self._place_initial()
        self.show()
        if not pinned:
            self._autohide_timer.start(_AUTOHIDE_DELAY)

    # ── Pin visuals ───────────────────────────────────────────────────────────

    @staticmethod
    def _pin_visuals(pinned: bool):
        if pinned:
            return ("●", _ZB_PIN_ON, _ZB_HOVER,
                    "Pinned — always visible.  Click to unpin (auto-hide).")
        return ("○", _ZB_DIM, _ZB_HOVER,
                "Unpinned — auto-hides.  Click to pin (always visible).")

    def set_pinned(self, pinned: bool):
        self._pinned = pinned
        self._pin_btn.set_icon(*self._pin_visuals(pinned))
        if pinned:
            self._autohide_timer.stop()
        else:
            # If mouse is currently over the widget, leaveEvent will start the
            # timer; otherwise start it now.
            if not self.underMouse():
                self._autohide_timer.start(_AUTOHIDE_DELAY)

    def _on_hide_fired(self):
        if not self._pinned and not self.underMouse():
            self._on_hide()

    # ── Positioning ───────────────────────────────────────────────────────────

    def _place_initial(self):
        wa_l, wa_t, wa_r, wa_b = _work_area()
        saved_x = config.get("tool_shelf_x", -1)
        saved_y = config.get("tool_shelf_y", -1)
        if isinstance(saved_x, int) and isinstance(saved_y, int) and saved_x >= 0 and saved_y >= 0:
            x = max(wa_l, min(saved_x, wa_r - self.width()))
            y = max(wa_t, min(saved_y, wa_b - self.height()))
        else:
            x = (wa_l + wa_r) // 2 - self.width() // 2
            y = wa_b - self.height() - 8
        self.move(x, y)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 4, 4)
        p.fillPath(path, QColor(_ZB_BG))

    # ── Auto-hide ↔ hover ─────────────────────────────────────────────────────

    def enterEvent(self, _e):
        self._autohide_timer.stop()

    def leaveEvent(self, _e):
        if not self._pinned:
            self._autohide_timer.start(_AUTOHIDE_DELAY)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        new_pos = e.globalPosition().toPoint() - self._drag_pos
        delta = (new_pos - self.pos())
        if abs(delta.x()) + abs(delta.y()) > _DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            self.move(new_pos)

    def mouseReleaseEvent(self, _e):
        if self._dragging:
            self._on_move(self.pos().x(), self.pos().y())
        self._drag_pos = None
        self._dragging = False

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._on_hide()


# ── Controller ────────────────────────────────────────────────────────────────

class ToolShelf(QObject):
    """Thread-safe persistent tool shelf controller."""
    _show_sig = Signal()
    _hide_sig = Signal()

    def __init__(self, on_quit: Optional[Callable] = None):
        super().__init__()
        self._widget:  Optional[_ShelfWidget] = None
        self._tools:   list[tuple]            = []
        self._on_quit                          = on_quit or (lambda: None)
        self._pinned                           = bool(config.get("tool_shelf_pinned", True))
        # Cursor-edge poll runs whenever shelf is hidden and unpinned
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL)
        self._poll_timer.timeout.connect(self._check_edge)
        self._last_geom: Optional[QRect] = None
        self._show_sig.connect(self._do_show)
        self._hide_sig.connect(self._do_hide)

    def set_tools(self, tools: list[tuple]):
        self._tools = tools

    def show(self):
        """Show (or bring to front) the shelf. Safe from any thread."""
        self._show_sig.emit()

    def hide(self):
        """Hide the shelf. Safe from any thread."""
        self._hide_sig.emit()

    # ── Slots (Qt main thread) ────────────────────────────────────────────────

    @Slot()
    def _do_show(self):
        if self._widget is not None:
            self._widget.raise_()
            self._widget.show()
            return
        self._widget = _ShelfWidget(
            self._tools,
            pinned=self._pinned,
            on_pin_toggle=self._toggle_pin,
            on_hide=self._do_hide,
            on_quit=self._on_quit,
            on_move=self._save_pos,
        )
        self._widget.destroyed.connect(lambda: setattr(self, "_widget", None))
        self._poll_timer.stop()   # widget visible — no need to poll

    @Slot()
    def _do_hide(self):
        if self._widget is not None:
            self._last_geom = self._widget.geometry()
            try:
                self._widget.destroyed.disconnect()
            except RuntimeError:
                pass
            self._widget.close()
            self._widget = None
        if not self._pinned:
            self._poll_timer.start()   # watch edge to bring it back

    def _toggle_pin(self):
        self._pinned = not self._pinned
        config["tool_shelf_pinned"] = self._pinned
        save_config_full()
        if self._widget is not None:
            self._widget.set_pinned(self._pinned)
        if self._pinned:
            self._poll_timer.stop()
        elif self._widget is None:
            self._poll_timer.start()

    def _save_pos(self, x: int, y: int):
        config["tool_shelf_x"] = int(x)
        config["tool_shelf_y"] = int(y)
        save_config_full()

    def _check_edge(self):
        """Show shelf when cursor enters the bottom-edge hot zone."""
        if self._widget is not None or self._pinned:
            self._poll_timer.stop()
            return
        cursor = QCursor.pos()
        wa_l, wa_t, wa_r, wa_b = _work_area()
        # Hot zone: bottom strip of the work area; if we have last geometry,
        # restrict x range to that region so the shelf doesn't pop up everywhere.
        if self._last_geom:
            x1 = self._last_geom.left()
            x2 = self._last_geom.right()
        else:
            x1, x2 = wa_l, wa_r
        in_x = x1 - 20 <= cursor.x() <= x2 + 20
        in_y = (wa_b - _HOT_ZONE_THICK) <= cursor.y() <= wa_b + _HOT_ZONE_THICK
        if in_x and in_y:
            self._do_show()


# ── Module-level singleton ────────────────────────────────────────────────────

_shelf: Optional[ToolShelf] = None


def get_tool_shelf() -> Optional[ToolShelf]:
    return _shelf


def init_tool_shelf(tools: list[tuple], on_quit: Optional[Callable] = None) -> ToolShelf:
    """Create singleton. Call once after QApplication exists.
    on_quit — called when user clicks the ✕ button (exit the whole app)."""
    global _shelf
    if _shelf is None:
        _shelf = ToolShelf(on_quit=on_quit)
        _shelf.set_tools(tools)
    return _shelf


def show_tool_shelf():
    """Show (or re-open) the shelf. Safe from any thread."""
    if _shelf:
        _shelf.show()
