"""Top-right voice-chat panel — click to interrupt TTS."""

from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.hud._screen import _screen_w


class _VoiceChatWidget(QWidget):
    """Fixed panel in the top-right corner. Click = interrupt TTS."""
    W, H = 320, 78

    _ICONS  = {"listening": "🎙", "thinking": "◌", "speaking": "🔊", "error": "✕"}
    _COLORS = {"listening": "#a6e3a1", "thinking": "#89b4fa", "speaking": "#fab387", "error": "#f38ba8"}
    _LABELS = {"listening": "Слушаю…", "thinking": "Думаю…", "speaking": "Говорю…", "error": "Ошибка"}

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
