"""
Configuration management for Universal Translator
"""

import json
import os
from pathlib import Path

# Constants
APP_NAME = "Universal Translator"
APP_VERSION = "3.2"
BUILD_DATE = "2026-05-15"
CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "DeepLTranslator"
CONFIG_FILE = CONFIG_DIR / "config.json"
ICON_FILE = CONFIG_DIR / "app_icon.ico"

STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_LINK = STARTUP_DIR / "Universal Translator.lnk"

# Global config
config = {}

def load_config():
    """Load configuration from file."""
    global config
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    # Auto-detect source language on first run
    if "source_lang" not in config:
        from utils.language import detect_system_language
        config["source_lang"] = detect_system_language()
    if "ollama_model" not in config:
        config["ollama_model"] = "qwen2.5:14b"
    return config.get("api_key", "")

def save_config_full():
    """Save entire config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

def save_config(api_key):
    """Save API key to config."""
    global config
    config["api_key"] = api_key
    save_config_full()

# Catppuccin Mocha color theme
C = {
    "bg":        "#1e1e2e",
    "surface":   "#181825",
    "card":      "#313244",
    "card_alt":  "#45475a",
    "border":    "#585b70",
    "text":      "#cdd6f4",
    "subtext":   "#a6adc8",
    "muted":     "#6c7086",
    "accent":    "#89b4fa",
    "green":     "#a6e3a1",
    "red":       "#f38ba8",
    "yellow":    "#f9e2af",
    "mauve":     "#cba6f7",
    "teal":      "#94e2d5",
    "peach":     "#fab387",
}

def deepl_api_base():
    """Get DeepL API base URL based on key type."""
    key = config.get("api_key", "")
    return "https://api.deepl.com/v2" if not key.endswith(":fx") else "https://api-free.deepl.com/v2"