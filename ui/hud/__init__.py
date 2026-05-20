"""Floating HUD overlays — PySide6 package.

Two controllers, each a QObject living on the Qt main thread:
  PipeHud       — recording/transcription/dictation status (bottom-right)
  VoiceChatHud  — persistent voice chat panel (top-right corner)

Background threads call the public methods (open/set_status/…); internally
these emit signals that Qt delivers on the main thread, so all QWidget
operations happen where they should.
"""

from ui.hud._screen      import _screen_w, _win32_cursor, _work_area
from ui.hud.pipe_hud      import PipeHud, get_pipe_hud, init_pipe_hud
from ui.hud.voice_chat_hud import VoiceChatHud, get_vc_hud, init_vc_hud

__all__ = [
    "PipeHud", "init_pipe_hud", "get_pipe_hud",
    "VoiceChatHud", "init_vc_hud", "get_vc_hud",
    # Re-exported for ui.tool_shelf (and other widgets that need screen geometry)
    "_win32_cursor", "_screen_w", "_work_area",
]
