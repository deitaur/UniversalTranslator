"""
Diagnostic script — run this to check for import errors and startup issues.
Usage: python diagnose.py
"""

import sys
import traceback

print("=== Universal Translator Diagnostics ===\n")
print(f"Python: {sys.version}")
print(f"CWD: {__import__('os').getcwd()}\n")

errors = []

# 1. Core imports
modules = [
    ("config", "from config import APP_NAME, CONFIG_DIR, load_config, config, save_config_full"),
    ("globals", "import globals as g"),
    ("win32.clipboard", "from win32.clipboard import get_clipboard_text, set_clipboard_text"),
    ("win32.keyboard", "from win32.keyboard import send_ctrl_c, send_ctrl_v, type_unicode_text, has_caret"),
    ("win32.hotkeys", "from win32.hotkeys import register_hotkey, unregister_hotkey, HOTKEY_POPUP, HOTKEY_REPLACE, HOTKEY_CLIPBOARD, HOTKEY_WHISPER, HOTKEY_NEGOTIATOR, HOTKEY_TEACHER, WM_HOTKEY, DEFAULT_HOTKEYS, parse_hotkey_string, hotkey_mods_vk"),
    ("win32.single_instance", "from win32.single_instance import check_single_instance, release_mutex"),
    ("utils.language", "from utils.language import get_source_lang, get_target_lang, is_english, LANGUAGES"),
    ("services.translators.deepl", "from services.translators.deepl import DeepLEngine"),
    ("services.translators.google", "from services.translators.google import GoogleEngine"),
    ("services.translators.yandex", "from services.translators.yandex import YandexEngine"),
    ("services.ai.ollama", "from services.ai.ollama import chat_ollama, check_ollama"),
    ("services.ai.rag_engine", "from services.ai.rag_engine import search_materials"),
    ("services.ai.whisper", "from services.ai.whisper import on_tray_whisper"),
    ("storage.roles", "from storage.roles import load_roles, get_role"),
    ("storage.history", "from storage.history import load_sessions"),
    ("ui.icon_generator", "from ui.icon_generator import generate_app_icon"),
    ("ui.tray_menu", "from ui.tray_menu import build_tray_image_deepl, update_tray_icon, _build_menu"),
    ("ui.popup_window", "from ui.popup_window import show_translation_popup"),
    ("ui.settings_window", "from ui.settings_window import show_settings_window"),
    ("ui.notifications", "from ui.notifications import show_toast, show_translation_toast"),
    ("ui.chat_window", "from ui.chat_window import show_chat_window"),
    ("ui.role_editor", "from ui.role_editor import show_role_editor"),
]

for name, stmt in modules:
    try:
        exec(stmt)
        print(f"  OK  {name}")
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        errors.append((name, traceback.format_exc()))

# 2. Check config
print()
try:
    from config import load_config, config, CONFIG_FILE
    load_config()
    print(f"Config file: {CONFIG_FILE}")
    print(f"  engine: {config.get('engine', '(not set)')}")
    print(f"  source_lang: {config.get('source_lang', '(not set)')}")
    print(f"  target_lang: {config.get('target_lang', '(not set)')}")
    print(f"  api_key present: {bool(config.get('api_key'))}")
    print(f"  ollama_model: {config.get('ollama_model', '(not set)')}")
    for hk in ["popup", "replace", "clipboard", "whisper", "negotiator", "teacher"]:
        print(f"  hotkey_{hk}: {config.get(f'hotkey_{hk}', '(default)')}")
except Exception as e:
    print(f"  CONFIG ERROR: {e}")
    errors.append(("config", traceback.format_exc()))

# 3. Check hotkey parsing
print()
try:
    from win32.hotkeys import hotkey_mods_vk, DEFAULT_HOTKEYS
    for name in DEFAULT_HOTKEYS:
        mods, vk = hotkey_mods_vk(name)
        status = "OK" if (mods and vk) else "WARN (mods=0x{:x}, vk=0x{:x})".format(mods, vk)
        print(f"  Hotkey '{name}': mods=0x{mods:x}, vk=0x{vk:x} — {status}")
except Exception as e:
    print(f"  HOTKEY PARSE ERROR: {e}")
    errors.append(("hotkey_parse", traceback.format_exc()))

# 4. Check roles
print()
try:
    from storage.roles import load_roles
    roles = load_roles()
    print(f"Roles loaded: {len(roles)}")
    for rid, r in roles.items():
        print(f"  {rid}: {r.get('name', '?')} (tray={r.get('show_in_tray', True)})")
except Exception as e:
    print(f"  ROLES ERROR: {e}")
    errors.append(("roles", traceback.format_exc()))

# 5. Check __init__.py files
print()
from pathlib import Path
base = Path(__file__).parent
for pkg in ["services", "services/translators", "services/ai", "storage", "ui", "win32", "utils"]:
    init = base / pkg / "__init__.py"
    if init.exists():
        print(f"  OK  {pkg}/__init__.py")
    else:
        print(f"  MISSING  {pkg}/__init__.py")
        errors.append((f"{pkg}/__init__.py", "File does not exist"))

# 6. Test translate functions
print()
try:
    from utils.language import is_english
    test_ru = "Привет мир"
    test_en = "Hello world"
    print(f"  is_english('{test_ru}'): {is_english(test_ru)}")
    print(f"  is_english('{test_en}'): {is_english(test_en)}")
except Exception as e:
    print(f"  LANGUAGE DETECTION ERROR: {e}")

# Summary
print("\n" + "=" * 40)
if errors:
    print(f"\nFOUND {len(errors)} ERROR(S):\n")
    for name, tb in errors:
        print(f"--- {name} ---")
        print(tb)
else:
    print("\nAll checks passed! No import errors found.")
    print("\nIf hotkeys still don't work, check:")
    print("  1. Is another instance running? (check Task Manager for pythonw.exe / Universal Translator)")
    print("  2. Check the log file at: %APPDATA%\\DeepLTranslator\\app.log")
    print("  3. Run the app from command line: python main.py")
    print("     (errors will print to console)")
