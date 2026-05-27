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

# Core imports needed immediately
from app.hotkey_loop import hotkey_listener
from app.tray_actions import (
    manage_autostart_shortcut, on_tray_quit, on_tray_role_chat,
    on_tray_settings, on_tray_translate, switch_to_google_silently,
)
from app.hotkey_handlers import (
    on_hotkey_clipboard, on_hotkey_popup,
    on_hotkey_replace, on_hotkey_negotiator,
    on_hotkey_websearch,
)
from ui.chat_window import setup_chat
from ui.notifications import setup_notifications
from ui.popup_window import setup_popup

# Lazy imports — loaded on-demand:
# - on_hotkey_whisper: loaded when whisper module needed
# - on_tray_whisper: loaded when tray whisper needed
# - setup_vc_hud: loaded when voice chat needed
# - show_voice_chat_dialog: loaded when voice chat dialog needed
# - setup_voice_actions_dialog: loaded when voice actions needed
# - on_hotkey_voicechat_handler: loaded when voicechat hotkey needed
# - on_hotkey_dictation_handler: loaded when dictation hotkey needed
# - usage_refresh_loop: loaded only if using DeepL

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
                from services.translators.deepl import DeepLEngine
                engine = DeepLEngine()
                count, limit = engine.get_usage()
                g.usage_data["character_count"] = count
                g.usage_data["character_limit"] = limit
                log.info("DeepL usage: %d / %d", count, limit)
            except Exception as e:
                log.error("DeepL usage fetch failed: %s", e)

        # Start hotkey listener (always needed)
        threading.Thread(target=hotkey_listener, daemon=True).start()

        # Only start usage refresh if using DeepL (lazy load the module)
        if g.current_engine == "deepl":
            from app.tray_actions import usage_refresh_loop
            threading.Thread(target=usage_refresh_loop, daemon=True).start()
            log.info("DeepL usage refresh thread started")

        # Only start bridge if explicitly enabled
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

        # Pipe HUD — init here so Ctrl+Alt+R works even without prior whisper use
        from ui.hud import init_pipe_hud
        try:
            from services.ai.recorder import stop_active as _stop_active
            init_pipe_hud(_stop_active)
        except Exception as e:
            log.warning("Failed to init pipe HUD: %s", e)
            init_pipe_hud(None)

        # Voice chat and voice actions are lazy-loaded when first needed
        # (in on_hotkey_voicechat_handler and on_hotkey_whisper)

        # ── Tool shelf (ZBrush-style icon strip) ──
        from ui.tool_shelf import init_tool_shelf, show_tool_shelf
        _shelf_tools = [
            ("🎙", "stt",    "Voice → text (диктофон)",  "Ctrl+Alt+W", on_hotkey_whisper),
            ("⚙",  "set",    "Settings",                  "",           on_tray_settings),
        ]
        shelf_ctrl = init_tool_shelf(_shelf_tools, on_quit=on_tray_quit)
        show_tool_shelf()   # appear at startup above taskbar; ✕ quits, _ hides, ● pins

        # Create lazy-loaded callbacks for heavy features
        def _on_tray_whisper_lazy():
            from services.ai.whisper import on_tray_whisper
            on_tray_whisper()

        def _on_voice_chat_lazy():
            from ui.voice_chat_dialog import show_voice_chat_dialog
            show_voice_chat_dialog()

        # Proper cleanup on app exit
        def _on_app_quit():
            log.info("App quit: cleaning up resources...")
            # Signal all threads to stop (hotkey listener, usage refresh, bridge, etc.)
            from globals import stop_event
            stop_event.set()
            # Save critical state
            shelf_ctrl.save_timers()
            from app.hotkey_loop import unregister_all_hotkeys
            unregister_all_hotkeys()
            # Brief pause for threads to exit gracefully
            import time
            time.sleep(0.1)
            log.info("Cleanup complete")

        app.aboutToQuit.connect(_on_app_quit)

        create_tray_icon({
            "translate_clipboard": on_tray_translate,
            "settings":            on_tray_settings,
            "whisper":             _on_tray_whisper_lazy,
            "role_chat":           on_tray_role_chat,
            "voice_chat_dialog":   _on_voice_chat_lazy,
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
