"""
Универсальный переводчик — основная точка входа.

Подключает значок на панели задач, прослушиватель горячих клавиш, цикл событий Qt и наложения HUD.
Фактическая логика горячих клавиш/трея находится в пакете app.
"""

import logging
import sys
import threading
import traceback

from PySide6.QtWidgets import QApplication

import globals as g
from config import APP_NAME, CONFIG_DIR, config, load_config
from services.translators.deepl import DeepLEngine
from ui.icon_generator import generate_app_icon
from ui.tray_menu import create_tray_icon
from win32.single_instance import check_single_instance, release_mutex

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

# Imports that may indirectly pull in heavy modules (PySide6 widgets, Whisper…)
# are kept *after* logging is set up so any import-time crash lands in app.log.
from app.hotkey_loop import hotkey_listener
from app.tray_actions import (
    manage_autostart_shortcut, on_tray_quit, on_tray_role_chat,
    on_tray_settings, on_tray_translate, switch_to_google_silently,
    usage_refresh_loop,
)
from app.hotkey_handlers import (
    on_hotkey_clipboard, on_hotkey_popup,
    on_hotkey_replace, on_hotkey_whisper, on_hotkey_negotiator,
    on_hotkey_websearch, on_hotkey_voicechat_handler,
)
from services.ai.voice_chat import setup_hud as setup_vc_hud
from services.ai.whisper import on_tray_whisper
from ui.chat_window import setup_chat
from ui.notifications import setup_notifications
from ui.popup_window import setup_popup
from ui.voice_actions_dialog import setup_voice_actions_dialog
from ui.voice_chat_dialog import show_voice_chat_dialog

log.info("All imports OK")


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

        # Set up Windows Startup shortcut based on configuration
        manage_autostart_shortcut(bool(config.get("autostart", False)))

        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        setup_notifications()         # toast manager must live on the Qt main thread
        setup_popup()                 # translation popup controller
        setup_chat()                  # chat window controller
        setup_vc_hud()                # voice chat HUD
        setup_voice_actions_dialog()  # post-Whisper action dialog controller

        # Pipe HUD — init here so Ctrl+Alt+R works even without prior whisper use
        from ui.hud import init_pipe_hud
        from services.ai.recorder import stop_active as _stop_active
        init_pipe_hud(_stop_active)

        # ── Tool shelf (ZBrush-style icon strip) ──
        from ui.tool_shelf import init_tool_shelf, show_tool_shelf
        _shelf_tools = [
            ("🎙", "stt",    "Voice → text (диктофон)",  "Ctrl+Alt+W", on_hotkey_whisper),
            ("⚙",  "set",    "Settings",                  "",           on_tray_settings),
        ]
        init_tool_shelf(_shelf_tools, on_quit=on_tray_quit)
        show_tool_shelf()   # appear at startup above taskbar; ✕ quits, _ hides, ● pins

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
