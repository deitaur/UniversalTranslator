"""Tray menu callbacks + background loops (usage refresh, autostart shortcut)."""

import logging
import time
import traceback

from PySide6.QtWidgets import QApplication

import globals as g
from config import config, save_config_full
from globals import stop_event
from services.translators.deepl import DeepLEngine
from ui.chat_window import show_chat_window
from ui.settings_window import show_settings_window
from ui.tray_menu import rebuild_menu, update_tray_icon

from app.hotkey_handlers import on_hotkey_clipboard
from app.hotkey_loop import unregister_all_hotkeys

log = logging.getLogger("tray")


# ── Background loops ──────────────────────────────────────────────────────────

def usage_refresh_loop():
    while not stop_event.is_set():
        if g.current_engine == "deepl":
            engine = DeepLEngine()
            count, limit = engine.get_usage()
            g.usage_data["character_count"] = count
            g.usage_data["character_limit"] = limit
            update_tray_icon()
        time.sleep(300)


# ── Tray actions ──────────────────────────────────────────────────────────────

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
    unregister_all_hotkeys()
    QApplication.instance().quit()


# ── Engine + autostart helpers ────────────────────────────────────────────────

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
