"""Translation engine routing + clipboard text grabbing for hotkey actions."""

import logging
import time
import traceback

import globals as g
from services.translators.deepl import DeepLEngine
from services.translators.google import GoogleEngine
from services.translators.yandex import YandexEngine
from ui.notifications import show_toast
from win32.clipboard import get_clipboard_text, set_clipboard_text
from win32.keyboard import send_ctrl_c

log = logging.getLogger("translation")


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
    from utils.language import detect_language, get_source_lang, get_target_lang
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


def grab_selected_text() -> str:
    """Copy currently selected text to clipboard via Ctrl+C, then read it back.
    Restores the previous clipboard if nothing was selected."""
    try:
        original_clipboard = get_clipboard_text()
    except Exception as e:
        log.error("Failed to get clipboard: %s", e)
        original_clipboard = ""
    try:
        set_clipboard_text("")   # clear so we can detect whether Ctrl+C actually copied
    except Exception as e:
        log.error("Failed to clear clipboard: %s", e)
    send_ctrl_c()
    time.sleep(0.2)
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
        log.debug("No text grabbed, restoring original clipboard")
        try:
            set_clipboard_text(original_clipboard)
        except Exception:
            pass
        return ""
    log.debug("Grabbed text: %s...", selected_text[:60])
    return selected_text
