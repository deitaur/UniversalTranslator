"""
Configuration management for Universal Translator
"""

import json
import os
from pathlib import Path

# Constants
APP_NAME = "Universal Translator"
APP_VERSION = "3.3"
BUILD_DATE = "2026-05-15"
CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "DeepLTranslator"
CONFIG_FILE = CONFIG_DIR / "config.json"
ICON_FILE = CONFIG_DIR / "app_icon.ico"

STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_LINK = STARTUP_DIR / "Universal Translator.lnk"
deepl_api_base = "https://api-free.deepl.com/v2"

# Catppuccin Mocha color theme
C = {
    "bg":       "#1e1e2e",
    "surface":  "#313244",
    "card":     "#181825",
    "card_alt": "#45475a",
    "text":     "#cdd6f4",
    "subtext":  "#a6adc8",
    "muted":    "#6c7086",
    "accent":   "#89b4fa",
    "border":   "#45475a",
    "green":    "#a6e3a1",
    "yellow":   "#f9e2af",
    "red":      "#f38ba8",
    "mauve":    "#cba6f7",
}

# Global config
config = {}

def load_config():
    """Load configuration from file."""
    global config
    if CONFIG_FILE.exists():
        config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    else:
        config.update({})
    return config.get("api_key", "")

def save_config_full():
    """Save entire config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure 'autostart' key exists and is saved, defaulting to False if not present
    if "autostart" not in config:
        config["autostart"] = False
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")