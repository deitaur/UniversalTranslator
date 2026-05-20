"""Thread-safe controller for the bottom-right pipeline HUD."""

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ui.hud._pipe_widget import _PipeWidget
from ui.hud._prereq_widget import _PrereqWidget
from ui.hud._screen import _win32_cursor
from ui.hud._style import _ZB_ACCENT


class PipeHud(QObject):
    """
    Thread-safe controller for the recording/transcription HUD.
    All public methods are safe to call from any thread.
    Connect `clicked` to the stop-recording event before first use.
    """
    clicked = Signal()               # emitted when user clicks the HUD

    _open_sig          = Signal()
    _status_sig        = Signal(str, str, str)   # text, icon, color
    _result_sig        = Signal(str, str)        # text, label
    _error_sig         = Signal(str)
    _saved_sig         = Signal(str, str, str)   # filepath, filename, preview
    _close_sig         = Signal()
    _prereq_sig        = Signal(object, object, object)  # checks, on_proceed, on_cancel
    _sched_close_sig   = Signal(int)             # ms — schedules a delayed close on main thread

    def __init__(self):
        super().__init__()
        self._widget: Optional[_PipeWidget] = None
        self._prereq_widget: Optional[_PrereqWidget] = None
        self._close_gen: int = 0   # bumped on every open; guards stale auto-close timers
        self._open_sig.connect(self._do_open)
        self._status_sig.connect(self._do_status)
        self._result_sig.connect(self._do_result)
        self._error_sig.connect(self._do_error)
        self._saved_sig.connect(self._do_saved)
        self._close_sig.connect(self._do_close)
        self._prereq_sig.connect(self._do_prereq)
        self._sched_close_sig.connect(self._do_sched_close)

    # ── Public API (any thread) ──

    def open(self):
        self._open_sig.emit()

    def open_at_cursor(self):
        """Open HUD at the bottom-right corner. Safe to call from any thread."""
        self._open_sig.emit()

    def set_status(self, text: str, icon: str = "◌", color: str = "#89b4fa"):
        self._status_sig.emit(text, icon, color)

    def show_result(self, text: str, label: str = "готово"):
        self._result_sig.emit(text, label)

    def show_error(self, text: str):
        self._error_sig.emit(text)

    def show_saved(self, filepath: str, filename: str, preview: str):
        self._saved_sig.emit(filepath, filename, preview)

    def close(self):
        self._close_sig.emit()

    def flash_action(self, text: str, ms: int = 900):
        """Flash action name in the bottom-right HUD for ms milliseconds."""
        self._open_sig.emit()
        self._status_sig.emit(text, "▸", _ZB_ACCENT)
        self._sched_close_sig.emit(ms)   # safe cross-thread delayed close

    def show_prereq(self, checks: dict, on_proceed, on_cancel=None):
        """Show non-blocking prereq overlay near cursor. Safe to call from any thread."""
        self._prereq_sig.emit(checks, on_proceed, on_cancel)

    # ── Slots (Qt main thread) ──

    @Slot()
    def _do_open(self):
        self._close_gen += 1   # invalidate any pending auto-close timers
        if self._widget:
            try:
                self._widget.destroyed.disconnect()
            except RuntimeError:
                pass
            self._widget.close()
        w = _PipeWidget(stop_cb=self.clicked.emit)
        self._widget = w
        w.destroyed.connect(lambda: self._clear_widget(w))

    def _clear_widget(self, w):
        if self._widget is w:
            self._widget = None

    @Slot(str, str, str)
    def _do_status(self, text: str, icon: str, color: str):
        if self._widget:
            self._widget.set_status(text, icon, color)

    def _sched_close(self, ms: int):
        """Schedule a close that only fires if no new session has opened since."""
        gen = self._close_gen
        QTimer.singleShot(ms, lambda: self._do_close_if(gen))

    def _do_close_if(self, gen: int):
        if self._close_gen == gen:
            self._do_close()

    @Slot(str, str)
    def _do_result(self, text: str, label: str):
        if self._widget:
            self._widget.show_result(text, label)
            self._sched_close(2000)

    @Slot(str)
    def _do_error(self, text: str):
        if self._widget:
            self._widget.show_error(text)
            self._sched_close(4000)

    @Slot(str, str, str)
    def _do_saved(self, filepath: str, filename: str, preview: str):
        if self._widget:
            self._widget.show_saved(filepath, filename, preview)
            self._sched_close(2500)

    @Slot(int)
    def _do_sched_close(self, ms: int):
        QTimer.singleShot(ms, self._do_close)

    @Slot()
    def _do_close(self):
        if self._widget:
            try:
                self._widget.destroyed.disconnect()
            except RuntimeError:
                pass
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


# ── Module-level singleton ────────────────────────────────────────────────────

_pipe_hud: Optional[PipeHud] = None


def init_pipe_hud(stop_cb=None) -> PipeHud:
    """
    Create the PipeHud singleton. Call once after QApplication exists.
    stop_cb — callable invoked when user clicks the HUD (optional; can be
              a threading.Event or a plain function).
    """
    global _pipe_hud
    if _pipe_hud is None:
        _pipe_hud = PipeHud()
        if stop_cb is not None:
            if callable(stop_cb):
                _pipe_hud.clicked.connect(stop_cb)
            else:
                _pipe_hud.clicked.connect(stop_cb.set)
    return _pipe_hud


def get_pipe_hud() -> Optional[PipeHud]:
    return _pipe_hud
