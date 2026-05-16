"""
Language detection and mapping utilities
"""

import locale

# Source languages (code -> display name)
LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "ar": "Arabic",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "cs": "Czech",
}

# Windows locale ID -> language code (most common)
_WIN_LOCALE_MAP = {
    "en": "en", "ru": "ru", "es": "es", "fr": "fr", "de": "de", "zh": "zh",
    "ja": "ja", "ko": "ko", "pt": "pt", "it": "it", "ar": "ar",
    "nl": "nl", "pl": "pl", "tr": "tr", "uk": "uk", "cs": "cs",
}

def detect_system_language():
    """Detect the user's Windows UI language and return a language code."""
    try:
        # locale.getdefaultlocale() deprecated in 3.11, removed in 3.15
        try:
            lang = locale.getlocale()[0]
        except Exception:
            lang = locale.getdefaultlocale()[0]
        if lang:
            short = lang.split("_")[0].lower()
            if short in _WIN_LOCALE_MAP:
                return _WIN_LOCALE_MAP[short]
    except Exception:
        pass
    return "ru"  # fallback

def get_source_lang():
    """Return the configured source language code."""
    from config import config
    return config.get("source_lang", "ru")

def get_source_lang_upper():
    """Return source language code in uppercase (for DeepL API)."""
    return get_source_lang().upper()

def get_target_lang():
    """Return the target language for reverse translation (EN -> ???).
    Uses config 'target_lang', falls back to source_lang, then system language."""
    from config import config
    tl = config.get("target_lang", "")
    if tl:
        return tl
    return get_source_lang()

def get_target_lang_upper():
    """Return target language code in uppercase (for DeepL API)."""
    return get_target_lang().upper()

def is_english(text):
    """Detect if text is primarily English by character analysis."""
    if not text.strip():
        return False
    ascii_letters = 0
    non_ascii_letters = 0
    for ch in text:
        if ch.isalpha():
            if ord(ch) < 128:
                ascii_letters += 1
            else:
                non_ascii_letters += 1
    total = ascii_letters + non_ascii_letters
    if total == 0:
        return False
    return (ascii_letters / total) > 0.7


def detect_language(text: str) -> str:
    """
    Detect the language of *text* using Google Translate's free auto-detect.
    Returns a BCP-47 language code (e.g. 'ru', 'en', 'de').
    Falls back to source_lang config value on any error.
    """
    if not text.strip():
        return get_source_lang()
    try:
        import requests
        # Use max 300 chars — enough for reliable detection, fast request
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": "en",
                    "dt": "t", "q": text[:300]},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        # data[2] = detected source language code ("ru", "en", "de", …)
        if isinstance(data, list) and len(data) > 2 and isinstance(data[2], str):
            return data[2]
    except Exception:
        pass
    # Offline fallback: character-ratio heuristic
    return "en" if is_english(text) else get_source_lang()