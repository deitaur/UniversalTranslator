"""Bottom-right status widget — recording/transcription/result/saved/error.

Always on top via HWND_TOPMOST; never steals focus.
"""

import ctypes
import os
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import config, save_config_full
from ui.hud._screen import _work_area
from ui.hud._style import (
    _ZB_ACCENT, _ZB_BG, _ZB_DIM, _ZB_ERR, _ZB_FONT,
    _ZB_OK, _ZB_REC, _ZB_SIZE, _ZB_TEXT,
)

_DRAG_THRESHOLD = 4   # px — movement above this counts as drag, not a click


def _os_open(path: str):
    try:
        os.startfile(path)
    except Exception:
        pass


class _PipeWidget(QWidget):
    """
    Fixed-position status notification panel in the bottom-right corner.
    Always on top via HWND_TOPMOST; never steals focus.
    """
    W = 300   # fixed width

    def __init__(self, stop_cb: Callable):
        super().__init__()
        self._stop_cb     = stop_cb
        self._t0          = time.time()
        self._blink_on    = True
        self._blink_color = _ZB_REC
        self._blink_dim   = "#606060"
        self._drag_pos: Optional[QPoint] = None
        self._dragging    = False
        self._user_moved  = False   # once user drags, stop auto-repositioning

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._build_ui()
        self.setFixedWidth(self.W)
        self.adjustSize()
        self._reposition()
        self.show()
        self._force_topmost()

        self._t_blink = QTimer(self); self._t_blink.setInterval(500); self._t_blink.timeout.connect(self._blink)
        self._t_clock = QTimer(self); self._t_clock.setInterval(1000); self._t_clock.timeout.connect(self._tick)
        self._t_blink.start()
        self._t_clock.start()

    # ── Positioning ──

    def _reposition(self):
        self.adjustSize()
        if self._user_moved:
            return   # respect user's drag — only clamp to screen
        # Use saved position if available, otherwise bottom-right corner
        saved_x = config.get("pipe_hud_x", -1)
        saved_y = config.get("pipe_hud_y", -1)
        wa_l, wa_t, wa_r, wa_b = _work_area()
        if isinstance(saved_x, int) and isinstance(saved_y, int) and saved_x >= 0 and saved_y >= 0:
            x = max(wa_l, min(saved_x, wa_r - self.width()))
            y = max(wa_t, min(saved_y, wa_b - self.height()))
        else:
            x = wa_r - self.W - 12
            y = wa_b - self.height() - 12
        self.move(x, y)

    def _force_topmost(self):
        HWND_TOPMOST   = -1
        SWP_NOMOVE     = 0x0002
        SWP_NOSIZE     = 0x0001
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            int(self.winId()), HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    # ── UI ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(3)

        # ── Status row ──
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)

        self._dot = QLabel("●")
        self._dot.setFont(QFont(_ZB_FONT, 8, QFont.Weight.Bold))
        self._dot.setFixedWidth(12)
        self._dot.setStyleSheet(f"color: {_ZB_REC};")
        row.addWidget(self._dot)

        self._status = QLabel("rec")
        self._status.setFont(QFont(_ZB_FONT, _ZB_SIZE))
        self._status.setStyleSheet(f"color: {_ZB_TEXT};")
        self._status.setWordWrap(False)
        row.addWidget(self._status, 1)

        self._timer = QLabel("0s")
        self._timer.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        self._timer.setStyleSheet(f"color: {_ZB_DIM};")
        row.addWidget(self._timer)

        close_lbl = QLabel("✕")
        close_lbl.setFont(QFont(_ZB_FONT, 8))
        close_lbl.setStyleSheet(f"color: {_ZB_DIM};")
        close_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        close_lbl.mousePressEvent = lambda _: self._stop_cb()
        row.addWidget(close_lbl)

        root.addLayout(row)

        # ── Preview (result text / saved path) ──
        self._preview = QLabel()
        self._preview.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        self._preview.setStyleSheet(f"color: {_ZB_DIM};")
        self._preview.setWordWrap(True)
        self._preview.setMaximumWidth(self.W - 20)
        self._preview.hide()
        root.addWidget(self._preview)

        # ── Dictation file buttons ──
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

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        p.fillPath(path, QColor(_ZB_BG))
        p.setPen(QPen(QColor("#505060"), 1))
        p.drawPath(path)

    # ── Timers ──

    def _blink(self):
        self._blink_on = not self._blink_on
        color = self._blink_color if self._blink_on else self._blink_dim
        self._dot.setStyleSheet(f"color: {color};")

    def _tick(self):
        self._timer.setText(f"{int(time.time() - self._t0)}s")

    def _relayout(self):
        self.adjustSize()
        self._reposition()
        self._force_topmost()

    # ── State setters ──

    def set_status(self, text: str, _icon: str = "◌", color: str = _ZB_ACCENT):
        self._blink_color = color
        self._blink_dim   = _ZB_DIM
        self._dot.setText("▸")
        self._status.setText(text)
        self._timer.setText("")
        self._t_clock.stop()
        self._relayout()

    def show_result(self, text: str, label: str = "готово"):
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✓")
        self._dot.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setText(label[:60])
        self._timer.setText("")
        if text:
            self._preview.setText(text[:120] + ("…" if len(text) > 120 else ""))
            self._preview.show()
        self._relayout()

    def show_error(self, text: str):
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✕")
        self._dot.setStyleSheet(f"color: {_ZB_ERR};")
        self._status.setStyleSheet(f"color: {_ZB_ERR};")
        self._status.setText(text[:80])
        self._timer.setText("")
        self._relayout()

    def show_saved(self, filepath: str, filename: str, preview: str):
        self._t_blink.stop()
        self._t_clock.stop()
        self._dot.setText("✓")
        self._dot.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setStyleSheet(f"color: {_ZB_OK};")
        self._status.setText(f"saved  {filename}")
        self._timer.setText("")
        self._preview.setText(preview[:100] + ("…" if len(preview) > 100 else ""))
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
        self._relayout()

    # ── Input  (click = stop, drag = move) ──

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        new_pos = e.globalPosition().toPoint() - self._drag_pos
        delta = new_pos - self.pos()
        if abs(delta.x()) + abs(delta.y()) > _DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            self.move(new_pos)
            self._user_moved = True

    def mouseReleaseEvent(self, _e):
        if self._dragging:
            config["pipe_hud_x"] = self.pos().x()
            config["pipe_hud_y"] = self.pos().y()
            save_config_full()
        elif self._drag_pos is not None:
            # Simple click (no drag) — invoke stop callback
            self._stop_cb()
        self._drag_pos = None
        self._dragging = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._stop_cb()
