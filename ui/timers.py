"""
Minimal clickable timers for tool shelf.
Single click = start/stop, double click = reset.
"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

log = logging.getLogger("timers")

_FONT_TIME = QFont("Courier New", 10, QFont.Weight.Bold)


class _TimerBase(QWidget):
    """Base class for clickable timers."""

    def __init__(self, total_minutes: int):
        super().__init__()
        self._total_seconds = total_minutes * 60
        self._remaining = self._total_seconds
        self._running = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)
        self._color_normal = "#89b4fa"
        self._color_warn = "#f38ba8"

        self.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 8, 6, 8)
        lo.setSpacing(0)

        self._time_lbl = QLabel(self._format_time())
        self._time_lbl.setFont(_FONT_TIME)
        self._time_lbl.setStyleSheet(f"color: {self._color_normal}; background: transparent;")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self._time_lbl)

    def _format_time(self) -> str:
        """Format remaining time based on duration."""
        if self._total_seconds >= 3600:  # 4h timer
            hours = self._remaining // 3600
            mins = (self._remaining % 3600) // 60
            secs = self._remaining % 60
            return f"{hours}:{mins:02d}:{secs:02d}"
        else:  # 20m, 90m timers
            mins = self._remaining // 60
            secs = self._remaining % 60
            return f"{mins}:{secs:02d}"

    def _on_tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self._update_display()
            if self._remaining == 0:
                self._timer.stop()
                self._running = False
                self._play_alert()

    def _update_display(self):
        """Update display and color (red when < 1 min or < 5 min for 4h)."""
        text = self._format_time()
        warn_threshold = 300 if self._total_seconds >= 3600 else 60
        color = self._color_warn if self._remaining <= warn_threshold else self._color_normal
        self._time_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._time_lbl.setText(text)

    def mousePressEvent(self, e):
        """Single click = toggle."""
        log.debug(f"Mouse press on {self.__class__.__name__}")
        if e.button() == Qt.MouseButton.LeftButton:
            self._toggle()
            e.accept()

    def mouseDoubleClickEvent(self, e):
        """Double click = reset."""
        log.debug(f"Double click on {self.__class__.__name__}")
        if e.button() == Qt.MouseButton.LeftButton:
            self._reset()
            e.accept()

    def _toggle(self):
        """Toggle running state."""
        if self._running:
            self._timer.stop()
            self._running = False
            log.debug(f"{self.__class__.__name__} stopped")
        else:
            if self._remaining > 0:
                self._timer.start(1000)
                self._running = True
                log.debug(f"{self.__class__.__name__} started")

    def _reset(self):
        """Reset timer and stop."""
        self._timer.stop()
        self._running = False
        self._remaining = self._total_seconds
        self._update_display()
        log.debug(f"{self.__class__.__name__} reset to {self._total_seconds}s")

    def _play_alert(self):
        """Play timer finished alert (in background thread to avoid blocking UI)."""
        def _alert():
            try:
                from ui.notifications import play_timer_alert
                play_timer_alert()
            except Exception as e:
                log.warning(f"Failed to play alert: {e}")

        threading.Thread(target=_alert, daemon=True).start()


class TimerWidget20(_TimerBase):
    """20-minute clickable timer."""

    def __init__(self):
        super().__init__(20)
        self.setFixedSize(65, 50)


class TimerWidget90(_TimerBase):
    """90-minute clickable timer with deep work logging."""

    def __init__(self):
        super().__init__(90)
        self.setFixedSize(75, 50)

    def _play_alert(self):
        """Play alert and log deep work session."""
        super()._play_alert()
        self._log_session()

    def _log_session(self):
        """Log completed 90-min deep work session to markdown file."""
        def _write_log():
            try:
                from config import CONFIG_DIR
                log_file = CONFIG_DIR / "deep_work.md"

                # Create file with header if it doesn't exist
                if not log_file.exists():
                    log_file.write_text("# Deep Work Sessions\n\n")

                # Get current time and format
                now = datetime.now()
                end_time = now.strftime("%H:%M")
                date = now.strftime("%Y-%m-%d")

                # Append new entry
                entry = f"- {date} | {end_time} | 90 min\n"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(entry)

                log.info(f"Deep work session logged: {date} {end_time}")
            except Exception as e:
                log.warning(f"Failed to log deep work session: {e}")

        threading.Thread(target=_write_log, daemon=True).start()


class TimerWidget240(_TimerBase):
    """4-hour (240-minute) clickable timer."""

    def __init__(self):
        super().__init__(240)
        self._color_normal = "#a6e3a1"  # Green for long timer
        self.setFixedSize(85, 50)
