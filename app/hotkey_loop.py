"""Win32 hotkey registration + the message-pump thread that dispatches them."""

import ctypes
import ctypes.wintypes
import logging
import time
import traceback

from globals import stop_event
from ui.notifications import show_toast
from win32.hotkeys import (
    HOTKEY_CLIPBOARD, HOTKEY_DICTATION, HOTKEY_NEGOTIATOR, HOTKEY_POLISH,
    HOTKEY_POPUP, HOTKEY_REPLACE, HOTKEY_WEBSEARCH, HOTKEY_VOICECHAT,
    HOTKEY_WHISPER, WM_HOTKEY, hotkey_mods_vk, register_hotkey, unregister_hotkey,
)

from app.hotkey_handlers import (
    on_hotkey_clipboard, on_hotkey_dictation_handler, on_hotkey_negotiator,
    on_hotkey_polish_handler, on_hotkey_popup, on_hotkey_replace,
    on_hotkey_websearch, on_hotkey_voicechat_handler, on_hotkey_whisper,
)

log = logging.getLogger("hotkey_loop")

_HOTKEY_IDS = [
    HOTKEY_POPUP, HOTKEY_REPLACE, HOTKEY_CLIPBOARD,
    HOTKEY_WHISPER, HOTKEY_DICTATION, HOTKEY_VOICECHAT,
    HOTKEY_NEGOTIATOR, HOTKEY_WEBSEARCH, HOTKEY_POLISH,
]

_HOTKEY_PAIRS = [
    ("popup",      HOTKEY_POPUP),
    ("replace",    HOTKEY_REPLACE),
    ("clipboard",  HOTKEY_CLIPBOARD),
    ("whisper",    HOTKEY_WHISPER),
    ("dictation",  HOTKEY_DICTATION),
    ("voicechat",  HOTKEY_VOICECHAT),
    ("negotiator", HOTKEY_NEGOTIATOR),
    ("web_search", HOTKEY_WEBSEARCH),
    ("polish",     HOTKEY_POLISH),
]


def _register_hotkeys():
    # Unregister first — clears stale registrations from a previous crashed instance
    for _, hid in _HOTKEY_PAIRS:
        unregister_hotkey(hid)
    failed = []
    for name, hid in _HOTKEY_PAIRS:
        mods, vk = hotkey_mods_vk(name)
        result = register_hotkey(hid, mods, vk)
        log.info("RegisterHotKey(%s, id=%d, mods=0x%x, vk=0x%x) => %s",
                 name, hid, mods, vk, result)
        if not result:
            err = ctypes.get_last_error()
            log.warning("  !! FAILED: %s  WinError=%d", name, err)
            failed.append(name)
    if failed:
        show_toast(f"Hotkey registration failed: {', '.join(failed)}\nCheck app.log", 5000)


def unregister_all_hotkeys():
    for hid in _HOTKEY_IDS:
        unregister_hotkey(hid)


def hotkey_listener():
    user32 = ctypes.windll.user32
    log.info("Hotkey listener thread started")
    try:
        _register_hotkeys()
    except Exception as e:
        log.error("Failed to register hotkeys: %s\n%s", e, traceback.format_exc())
        return
    handlers = {
        HOTKEY_POPUP:       ("popup",      on_hotkey_popup),
        HOTKEY_REPLACE:     ("replace",    on_hotkey_replace),
        HOTKEY_CLIPBOARD:   ("clipboard",  on_hotkey_clipboard),
        HOTKEY_WHISPER:     ("whisper",    on_hotkey_whisper),
        HOTKEY_DICTATION:   ("dictation",  on_hotkey_dictation_handler),
        HOTKEY_VOICECHAT:   ("voicechat",  on_hotkey_voicechat_handler),
        HOTKEY_NEGOTIATOR:  ("negotiator", on_hotkey_negotiator),
        HOTKEY_WEBSEARCH:   ("web_search", on_hotkey_websearch),
        HOTKEY_POLISH:      ("polish",     on_hotkey_polish_handler),
    }
    log.info("Hotkey listener entering message loop")
    while not stop_event.is_set():
        msg = ctypes.wintypes.MSG()
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == WM_HOTKEY:
                entry = handlers.get(msg.wParam)
                if entry:
                    name, handler = entry
                    log.debug("Hotkey pressed: %s", name)
                    try:
                        handler()
                    except Exception as e:
                        log.error("Hotkey handler '%s' error: %s\n%s",
                                  name, e, traceback.format_exc())
                        try:
                            show_toast(f"Error: {e}")
                        except Exception:
                            pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    log.info("Hotkey listener exiting")
