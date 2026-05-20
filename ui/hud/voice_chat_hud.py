"""Thread-safe controller for the top-right voice-chat panel."""

from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from ui.hud._voice_chat_widget import _VoiceChatWidget


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
            try:
                self._widget.destroyed.disconnect()
            except RuntimeError:
                pass
            self._widget.close()
        w = _VoiceChatWidget(
            stop_cb=self.closed.emit,
            interrupt_cb=self.clicked.emit,
        )
        self._widget = w
        w.destroyed.connect(lambda: self._clear_vc_widget(w))

    def _clear_vc_widget(self, w):
        if self._widget is w:
            self._widget = None

    @Slot(str, str)
    def _do_state(self, state: str, sub: str):
        if self._widget:
            self._widget.set_state(state, sub)

    @Slot()
    def _do_close(self):
        if self._widget:
            try:
                self._widget.destroyed.disconnect()
            except RuntimeError:
                pass
            self._widget.close()
            self._widget = None


# ── Module-level singleton ────────────────────────────────────────────────────

_vc_hud: Optional[VoiceChatHud] = None


def init_vc_hud() -> VoiceChatHud:
    """Create the VoiceChatHud singleton. Must be called from the Qt main thread."""
    global _vc_hud
    if _vc_hud is None:
        _vc_hud = VoiceChatHud()
    return _vc_hud


def get_vc_hud() -> Optional[VoiceChatHud]:
    return _vc_hud
