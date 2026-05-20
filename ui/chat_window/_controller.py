"""Singleton controller — thread-safe show / switch-mode for the chat window."""

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from ui.chat_window._window import ChatWindow


class _ChatController(QObject):
    _show_sig = Signal(str, str)   # initial_text, mode

    def __init__(self):
        super().__init__()
        self._window: Optional[ChatWindow] = None
        self._show_sig.connect(self._do_show)

    def show(self, initial_text: str = "", mode: str = "negotiator"):
        self._show_sig.emit(initial_text, mode)

    @Slot(str, str)
    def _do_show(self, initial_text: str, mode: str):
        if self._window is not None:
            try:
                if mode != self._window._mode:
                    self._window._mode = mode
                    self._window._update_title()
                    idx = next((i for i in range(self._window._role_combo.count())
                                if self._window._role_combo.itemData(i) == mode), -1)
                    if idx >= 0:
                        self._window._role_combo.setCurrentIndex(idx)
                self._window.show()
                self._window.activateWindow()
                self._window.raise_()
                if initial_text.strip():
                    self._window._send(initial_text)
                return
            except RuntimeError:
                self._window = None

        self._window = ChatWindow(initial_text, mode)
        self._window.destroyed.connect(lambda: setattr(self, "_window", None))
        self._window.show()
        self._window.activateWindow()


_controller: Optional[_ChatController] = None


def setup_chat() -> _ChatController:
    """Create the singleton. Call from the Qt main thread in main.py."""
    global _controller
    if _controller is None:
        _controller = _ChatController()
    return _controller


def show_chat_window(initial_text: str = "", mode: str = "negotiator"):
    if _controller is not None:
        _controller.show(initial_text, mode)
    else:
        logging.getLogger("chat_window").warning(
            "show_chat_window called before setup_chat")
