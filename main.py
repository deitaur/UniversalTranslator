"""
Main entry point for Universal Translator
"""

import sys
import logging
import traceback
import threading
import time
from PySide6.QtWidgets import QApplication
from config import APP_NAME, CONFIG_DIR, load_config, config, save_config_full, STARTUP_LINK

# ── Setup file logging so daemon-thread crashes are visible ──
_LOG_FILE = CONFIG_DIR / "app.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(_LOG_FILE), encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("main")
log.info("=== Universal Translator starting ===")

import globals as g
from globals import stop_event
from services.translators.deepl import DeepLEngine
from services.translators.google import GoogleEngine
from services.translators.yandex import YandexEngine
from win32.clipboard import get_clipboard_text, set_clipboard_text
from win32.keyboard import send_ctrl_c, send_ctrl_v, type_unicode_text, has_caret
from win32.hotkeys import (register_hotkey, unregister_hotkey,
    HOTKEY_POPUP, HOTKEY_REPLACE, HOTKEY_CLIPBOARD,
    HOTKEY_WHISPER, HOTKEY_NEGOTIATOR, HOTKEY_TEACHER, HOTKEY_DICTATION,
    HOTKEY_VOICECHAT, HOTKEY_POLISH, WM_HOTKEY)
from win32.single_instance import check_single_instance, release_mutex
from ui.icon_generator import generate_app_icon
from ui.tray_menu import create_tray_icon, update_tray_icon, rebuild_menu
from ui.popup_window import show_translation_popup
from ui.settings_window import show_settings_window
from ui.notifications import show_toast, show_translation_toast, setup_notifications
from ui.popup_window import setup_popup
from ui.chat_window import setup_chat, show_chat_window
from ui.voice_chat_dialog import show_voice_chat_dialog
from services.ai.whisper import on_tray_whisper
from services.ai.dictation import on_hotkey_dictation
from services.ai.polish import on_hotkey_polish
from services.ai.voice_chat import on_hotkey_voicechat, setup_hud as setup_vc_hud
from utils.language import get_source_lang

log.info("All imports OK")


def _get_engine():
    if g.current_engine == "google":
        return GoogleEngine()
    elif g.current_engine == "yandex":
        return YandexEngine()
    else:
        return DeepLEngine()

def translate_text(text):
    """Translate to the configured target language (always)."""
    from utils.language import get_target_lang
    return _get_engine().translate_to(text, get_target_lang())

def translate_auto(text):
    """
    Auto-detect input language, then choose direction:
      detected == target_lang  →  translate to source_lang (reverse)
      detected != target_lang  →  translate to target_lang
    Returns (translated_text, actual_target_lang_code).
    """
    from utils.language import detect_language, get_target_lang, get_source_lang
    engine = _get_engine()
    try:
        target   = get_target_lang()   # primary output language (e.g. "ru")
        source   = get_source_lang()   # what user usually types (e.g. "ru")
        detected = detect_language(text)
        log.debug("detect=%s  target=%s  source=%s", detected, target, source)

        if detected == target:
            # Text is already in the target language → go the other way
            reverse_to = source if source != target else "en"
            log.debug("Reversing: %s → %s", detected, reverse_to)
            return engine.translate_to(text, reverse_to), reverse_to
        else:
            log.debug("Forward: %s → %s", detected, target)
            return engine.translate_to(text, target), target
    except Exception as e:
        log.error("Translation error: %s\n%s", e, traceback.format_exc())
        show_toast(f"Translation error: {e}")
        return "", None

def _grab_selected_text():
    try:
        original_clipboard = get_clipboard_text()
    except Exception as e:
        log.error("Failed to get clipboard: %s", e)
        original_clipboard = ""
    try:
        set_clipboard_text("")  # Clear clipboard to detect if Ctrl+C works
    except Exception as e:
        log.error("Failed to clear clipboard: %s", e)
    send_ctrl_c()
    time.sleep(0.2)  # slightly longer wait for clipboard to settle
    # Retry clipboard read (sometimes the first read is too early)
    selected_text = ""
    for attempt in range(3):
        try:
            selected_text = get_clipboard_text()
            if selected_text.strip():
                break
        except Exception as e:
            log.error("Clipboard read attempt %d failed: %s", attempt + 1, e)
        time.sleep(0.05)
    if not selected_text.strip():
        # Nothing was copied (e.g. nothing selected), restore original
        log.debug("No text grabbed, restoring original clipboard")
        try:
            set_clipboard_text(original_clipboard)
        except Exception:
            pass
        return ""
    log.debug("Grabbed text: %s...", selected_text[:60])
    return selected_text

def on_hotkey_replace():
    log.debug("on_hotkey_replace called")
    text = _grab_selected_text()
    if not text.strip():
        log.debug("No text selected, skipping")
        show_toast("Select text first (Ctrl+Alt+R)", 2000)
        return

    log.debug("Text (%d chars): %s...", len(text), text[:50])
    translated, _ = translate_auto(text)
    if not translated:
        log.warning("Translation returned empty")
        return

    set_clipboard_text(translated)
    log.debug("Translation set to clipboard (%d chars)", len(translated))
    send_ctrl_v()
    show_toast("✓", 800)

def on_hotkey_popup():
    log.debug("on_hotkey_popup called")
    text = _grab_selected_text()
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

def _flash(text: str):
    from ui.hud import get_pipe_hud
    hud = get_pipe_hud()
    if hud:
        hud.flash_action(text)

def on_hotkey_whisper():
    _flash("voice → text  Ctrl+Alt+W")
    on_tray_whisper()

def on_hotkey_dictation_handler():
    _flash("dictation  Ctrl+Alt+D")
    on_hotkey_dictation()

def on_hotkey_negotiator():
    _flash("negotiator  Ctrl+Alt+N")
    text = _grab_selected_text()
    if text and text.strip():
        show_chat_window("Rewrite this to sound more persuasive and professional:\n\n" + text, mode="negotiator")
    else:
        show_chat_window(mode="negotiator")

def on_hotkey_teacher():
    _flash("teacher  Ctrl+Alt+E")
    show_chat_window(mode="teacher")

def on_hotkey_voicechat_handler():
    _flash("voice chat  Ctrl+Alt+V")
    on_hotkey_voicechat()

def on_hotkey_polish_handler():
    _flash("voice polish  Ctrl+Alt+F")
    on_hotkey_polish()

def _register_hotkeys():
    from win32.hotkeys import hotkey_mods_vk
    for name, hid in [("popup", HOTKEY_POPUP), ("replace", HOTKEY_REPLACE),
                      ("clipboard", HOTKEY_CLIPBOARD), ("whisper", HOTKEY_WHISPER),
                      ("dictation", HOTKEY_DICTATION), ("voicechat", HOTKEY_VOICECHAT),
                      ("negotiator", HOTKEY_NEGOTIATOR), ("teacher", HOTKEY_TEACHER),
                      ("polish", HOTKEY_POLISH)]:
        mods, vk = hotkey_mods_vk(name)
        result = register_hotkey(hid, mods, vk)
        log.info("RegisterHotKey(%s, id=%d, mods=0x%x, vk=0x%x) => %s", name, hid, mods, vk, result)

def _unregister_hotkeys():
    for hid in [HOTKEY_POPUP, HOTKEY_REPLACE, HOTKEY_CLIPBOARD,
                HOTKEY_WHISPER, HOTKEY_DICTATION, HOTKEY_VOICECHAT,
                HOTKEY_NEGOTIATOR, HOTKEY_TEACHER, HOTKEY_POLISH]:
        unregister_hotkey(hid)

def hotkey_listener():
    import ctypes
    user32 = ctypes.windll.user32
    log.info("Hotkey listener thread started")
    try:
        _register_hotkeys()
    except Exception as e:
        log.error("Failed to register hotkeys: %s\n%s", e, traceback.format_exc())
        return
    handlers = {
        HOTKEY_POPUP: ("popup", on_hotkey_popup),
        HOTKEY_REPLACE: ("replace", on_hotkey_replace),
        HOTKEY_CLIPBOARD: ("clipboard", on_hotkey_clipboard),
        HOTKEY_WHISPER: ("whisper", on_hotkey_whisper),
        HOTKEY_DICTATION: ("dictation", on_hotkey_dictation_handler),
        HOTKEY_VOICECHAT: ("voicechat", on_hotkey_voicechat_handler),
        HOTKEY_NEGOTIATOR: ("negotiator", on_hotkey_negotiator),
        HOTKEY_TEACHER: ("teacher", on_hotkey_teacher),
        HOTKEY_POLISH: ("polish", on_hotkey_polish_handler),
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
                        log.error("Hotkey handler '%s' error: %s\n%s", name, e, traceback.format_exc())
                        try:
                            show_toast(f"Error: {e}")
                        except Exception:
                            pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    log.info("Hotkey listener exiting")


def usage_refresh_loop():
    while not stop_event.is_set():
        if g.current_engine == "deepl":
            engine = DeepLEngine()
            count, limit = engine.get_usage()
            g.usage_data["character_count"] = count
            g.usage_data["character_limit"] = limit
            update_tray_icon()
        time.sleep(300)


def on_tray_translate():
    on_hotkey_clipboard()

def on_tray_settings():
    log.info("Opening settings window...")
    try:
        show_settings_window(g.current_engine, update_tray_icon, rebuild_menu)
    except Exception as e:
        log.error("Failed to open settings: %s\n%s", e, traceback.format_exc())

def on_tray_role_chat(role_id):
    show_chat_window(mode=role_id)

def on_tray_quit():
    stop_event.set()
    _unregister_hotkeys()
    QApplication.instance().quit()

def switch_to_google_silently():
    g.current_engine = "google"
    config["engine"] = "google"
    save_config_full()
def manage_autostart_shortcut(is_enabled: bool):
    """Manage the Windows Startup shortcut via tray_menu.set_autostart."""
    try:
        from ui.tray_menu import set_autostart
        set_autostart(is_enabled)
        log.info("Autostart %s", "enabled" if is_enabled else "disabled")
    except Exception as e:
        log.error("Failed to manage autostart shortcut: %s", e)

def main():
    is_first, mutex = check_single_instance(APP_NAME)
    if not is_first:
        log.warning("Another instance is already running. Exiting.")
        sys.exit(0)

    try:
        log.info("Loading config...")
        api_key = load_config()
        g.current_engine = config.get("engine", "deepl")
        log.info("Engine: %s, API key present: %s", g.current_engine, bool(api_key))

        if g.current_engine == "deepl" and not api_key:
            switch_to_google_silently()
            log.info("Switched to Google (no DeepL key)")

        generate_app_icon()
        log.info("App icon generated")

        if g.current_engine == "deepl":
            try:
                engine = DeepLEngine()
                count, limit = engine.get_usage()
                g.usage_data["character_count"] = count
                g.usage_data["character_limit"] = limit
                log.info("DeepL usage: %d / %d", count, limit)
            except Exception as e:
                log.error("DeepL usage fetch failed: %s", e)

        threading.Thread(target=hotkey_listener, daemon=True).start()
        threading.Thread(target=usage_refresh_loop, daemon=True).start()

        if config.get("bridge_enabled", False):
            from services.bridge.server import start_bridge
            threading.Thread(target=start_bridge, daemon=True).start()
            log.info("Mobile bridge thread started")

        log.info("Background threads started")

        # Check and set up Windows Startup shortcut based on configuration
        if config.get("autostart", False):
            manage_autostart_shortcut(True)
        else:
            manage_autostart_shortcut(False)

        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        setup_notifications()   # toast manager must live on the Qt main thread
        setup_popup()           # translation popup controller
        setup_chat()            # chat window controller
        setup_vc_hud()          # voice chat HUD

        # ── Tool shelf (ZBrush-style icon strip) ──
        from ui.tool_shelf import init_tool_shelf, show_tool_shelf
        from services.ai.whisper import on_tray_whisper as _wh
        _shelf_tools = [
            ("T",  "trnsl",  "Translation popup",     "Ctrl+Alt+T", on_hotkey_popup),
            ("R",  "repl",   "Replace in-place",      "Ctrl+Alt+R", on_hotkey_replace),
            ("C",  "clip",   "Translate clipboard",   "Ctrl+Alt+Y", on_hotkey_clipboard),
            ("🎙", "stt",    "Voice → text",           "Ctrl+Alt+W", on_hotkey_whisper),
            ("✨", "polish", "Voice polish → paste",   "Ctrl+Alt+F", on_hotkey_polish_handler),
            ("N",  "nego",   "Negotiator chat",        "Ctrl+Alt+N", on_hotkey_negotiator),
            ("E",  "teach",  "Teacher chat",           "Ctrl+Alt+E", on_hotkey_teacher),
            ("📞", "vc",     "Voice chat dialog",      "Ctrl+Alt+V", on_hotkey_voicechat_handler),
            ("⚙",  "set",    "Settings",               "",           on_tray_settings),
        ]
        init_tool_shelf(_shelf_tools)

        create_tray_icon({
            "translate_clipboard": on_tray_translate,
            "settings":            on_tray_settings,
            "whisper":             on_tray_whisper,
            "role_chat":           on_tray_role_chat,
            "voice_chat_dialog":   show_voice_chat_dialog,
            "tool_shelf":          show_tool_shelf,
            "quit":                on_tray_quit,
        })
        log.info("Tray icon created, entering Qt event loop")
        sys.exit(app.exec())
    except Exception as e:
        log.critical("FATAL ERROR: %s\n%s", e, traceback.format_exc())
        raise
    finally:
        release_mutex(mutex)
        log.info("App shutdown")


if __name__ == "__main__":
    main()
