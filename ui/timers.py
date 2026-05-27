"""
Minimal timers for tool shelf — 90 min (with controls) and 20 min (simple).
"""

import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_FONT_TIME = QFont("Courier New", 9)
_FONT_SMALL = QFont("Segoe UI", 7)

class TimerWidget90(QWidget):
    """90-minute timer with start/pause/stop buttons."""

    def __init__(self):
        super().__init__()
        self._total_seconds = 90 * 60  # 90 minutes
        self._remaining = self._total_seconds
        self._running = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)

        self.setFixedSize(80, 60)
        self.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")

        lo = QVBoxLayout(self)
        lo.setContentsMargins(4, 4, 4, 4)
        lo.setSpacing(2)

        # Time display
        self._time_lbl = QLabel("90:00")
        self._time_lbl.setFont(_FONT_TIME)
        self._time_lbl.setStyleSheet("color: #89b4fa; background: transparent;")
        self._time_lbl.setAlignment(0x0004 | 0x0020)  # AlignHCenter | AlignVCenter
        lo.addWidget(self._time_lbl)

        # Control buttons
        btn_lo = QHBoxLayout()
        btn_lo.setContentsMargins(0, 0, 0, 0)
        btn_lo.setSpacing(2)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(20, 16)
        self._play_btn.setFont(_FONT_SMALL)
        self._play_btn.setStyleSheet(
            "QPushButton { background: #44475a; color: #89b4fa; border: none; border-radius: 2px; }"
            "QPushButton:hover { background: #565970; }"
        )
        self._play_btn.clicked.connect(self._toggle_play)
        btn_lo.addWidget(self._play_btn)

        self._reset_btn = QPushButton("⊘")
        self._reset_btn.setFixedSize(20, 16)
        self._reset_btn.setFont(_FONT_SMALL)
        self._reset_btn.setStyleSheet(
            "QPushButton { background: #44475a; color: #f38ba8; border: none; border-radius: 2px; }"
            "QPushButton:hover { background: #565970; }"
        )
        self._reset_btn.clicked.connect(self._reset)
        btn_lo.addWidget(self._reset_btn)

        lo.addLayout(btn_lo)

    def _on_tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self._update_display()
            if self._remaining == 0:
                self._timer.stop()
                self._running = False
                self._play_btn.setText("▶")

    def _update_display(self):
        mins, secs = divmod(self._remaining, 60)
        self._time_lbl.setText(f"{mins}:{secs:02d}")

    def _toggle_play(self):
        if self._running:
            self._timer.stop()
            self._play_btn.setText("▶")
            self._running = False
        else:
            if self._remaining > 0:
                self._timer.start(1000)  # 1 second tick
                self._play_btn.setText("⏸")
                self._running = True

    def _reset(self):
        self._timer.stop()
        self._running = False
        self._remaining = self._total_seconds
        self._update_display()
        self._play_btn.setText("▶")


class TimerWidget20(QWidget):
    """20-minute simple countdown timer."""

    def __init__(self):
        super().__init__()
        self._total_seconds = 20 * 60  # 20 minutes
        self._remaining = self._total_seconds
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)

        self.setFixedSize(60, 50)
        self.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")
        self.setCursor(1)  # PointingHandCursor

        lo = QVBoxLayout(self)
        lo.setContentsMargins(4, 6, 4, 6)
        lo.setSpacing(0)

        # Time display (clickable to toggle)
        self._time_lbl = QLabel("20:00")
        self._time_lbl.setFont(_FONT_TIME)
        self._time_lbl.setStyleSheet("color: #a6e3a1; background: transparent;")
        self._time_lbl.setAlignment(0x0004 | 0x0020)
        lo.addWidget(self._time_lbl)

        self.mousePressEvent = self._on_click

    def _on_tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self._update_display()
            if self._remaining == 0:
                self._timer.stop()

    def _update_display(self):
        mins, secs = divmod(self._remaining, 60)
        color = "#ff6b6b" if self._remaining < 60 else "#a6e3a1"  # Red if < 1 min
        self._time_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._time_lbl.setText(f"{mins}:{secs:02d}")

    def _on_click(self, _e):
        if self._timer.isActive():
            self._timer.stop()
        else:
            if self._remaining > 0:
                self._timer.start(1000)
            else:
                self._remaining = self._total_seconds
                self._update_display()
                self._timer.start(1000)
