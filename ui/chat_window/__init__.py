"""Chat popup — role selector, sessions, streaming AI responses (PySide6)."""

from ui.chat_window._bubble     import _Bubble
from ui.chat_window._controller import setup_chat, show_chat_window
from ui.chat_window._window     import ChatWindow, FONT_FAMILIES, FONT_SIZES

__all__ = [
    "setup_chat", "show_chat_window",
    "ChatWindow", "FONT_FAMILIES", "FONT_SIZES",
    "_Bubble",   # used by ui.voice_chat_dialog
]
