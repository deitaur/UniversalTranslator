"""Hotkey handlers — one per registered global shortcut.

Each `on_hotkey_*` function is invoked from the Win32 message loop in
app.hotkey_loop. Handlers can spawn threads for long-running work but
must not block the listener for more than a few ms.
"""

import logging

import globals as g
from app.translation import grab_selected_text, translate_auto, translate_text
from services.ai.dictation import on_hotkey_dictation
from services.ai.polish import on_hotkey_polish
from services.ai.voice_chat import on_hotkey_voicechat
from services.ai.whisper import on_tray_whisper
from ui.chat_window import show_chat_window
from ui.notifications import show_toast
from ui.popup_window import show_translation_popup
from win32.clipboard import get_clipboard_text, set_clipboard_text
from win32.keyboard import send_ctrl_v

log = logging.getLogger("hotkeys")


def _flash(text: str):
    """Briefly flash the action name in the bottom-right HUD."""
    from ui.hud import get_pipe_hud
    hud = get_pipe_hud()
    if hud:
        hud.flash_action(text)


# ── Translation hotkeys ───────────────────────────────────────────────────────

def on_hotkey_replace():
    log.debug("on_hotkey_replace called")

    # Grab selection BEFORE opening HUD — window creation can steal focus
    text = grab_selected_text()
    if not text.strip():
        log.debug("No text selected, skipping")
        show_toast("Select text first (Ctrl+Alt+R)", 2000)
        return

    log.debug("Text (%d chars): %s...", len(text), text[:50])

    from ui.hud import get_pipe_hud
    hud = get_pipe_hud()
    if hud:
        hud.open_at_cursor()
        hud.set_status("translating…")

    translated, _ = translate_auto(text)
    if not translated:
        log.warning("Translation returned empty")
        if hud:
            hud.show_error("translation failed")
        return

    if hud:
        hud.set_status("pasting…")

    set_clipboard_text(translated)
    log.debug("Translation set to clipboard (%d chars)", len(translated))
    send_ctrl_v(skip_wait=True)

    if hud:
        hud.show_result(translated[:80])
    else:
        show_toast("✓", 800)


def on_hotkey_popup():
    log.debug("on_hotkey_popup called")
    text = grab_selected_text()
    if not text.strip():
        return
    translated, target_lang = translate_auto(text)
    if translated:
        show_translation_popup(text, translated, g.current_engine, target_lang)


def on_hotkey_clipboard():
    log.debug("on_hotkey_clipboard called")
    text = get_clipboard_text()
    if not text.strip():
        return
    translated = translate_text(text)
    if translated:
        set_clipboard_text(translated)
        show_toast("Translated to clipboard")


# ── AI hotkeys ────────────────────────────────────────────────────────────────

def on_hotkey_whisper():
    _flash("voice → text  Ctrl+Alt+W")
    on_tray_whisper()


def on_hotkey_dictation_handler():
    _flash("dictation  Ctrl+Alt+D")
    on_hotkey_dictation()


def on_hotkey_negotiator():
    _flash("negotiator  Ctrl+Alt+N")
    text = grab_selected_text()
    if text and text.strip():
        show_chat_window(
            "Rewrite this to sound more persuasive and professional:\n\n" + text,
            mode="negotiator",
        )
    else:
        show_chat_window(mode="negotiator")


def on_hotkey_websearch():
    _flash("web_search  Ctrl+Alt+S")
    show_chat_window(mode="web_search")


def on_hotkey_voicechat_handler():
    _flash("voice chat  Ctrl+Alt+V")
    on_hotkey_voicechat()


def on_hotkey_polish_handler():
    _flash("voice polish  Ctrl+Alt+F")
    on_hotkey_polish()
