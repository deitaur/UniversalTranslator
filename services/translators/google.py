"""
Google Translate engine
"""

import requests
from utils.language import get_source_lang, get_target_lang

GOOGLE_TL_URL = "https://translate.googleapis.com/translate_a/single"

class GoogleEngine:
    """Google Translate engine."""

    def translate(self, text):
        """Translate text using Google Translate."""
        params = {"client": "gtx", "sl": get_source_lang(), "tl": "en", "dt": "t", "q": text}
        r = requests.get(GOOGLE_TL_URL, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        parts = []
        if isinstance(data, list) and data and isinstance(data[0], list):
            for seg in data[0]:
                if isinstance(seg, list) and seg:
                    parts.append(str(seg[0]))
        return "".join(parts) if parts else "(no translation)"

    def translate_reverse(self, text):
        """Translate English text back to target language."""
        params = {"client": "gtx", "sl": "en", "tl": get_target_lang(), "dt": "t", "q": text}
        r = requests.get(GOOGLE_TL_URL, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        parts = []
        if isinstance(data, list) and data and isinstance(data[0], list):
            for seg in data[0]:
                if isinstance(seg, list) and seg:
                    parts.append(str(seg[0]))
        return "".join(parts) if parts else "(no translation)"

    def translate_to(self, text, target_lang_code: str) -> str:
        """Translate text to any target language; source is auto-detected."""
        params = {"client": "gtx", "sl": "auto", "tl": target_lang_code,
                  "dt": "t", "q": text}
        r = requests.get(GOOGLE_TL_URL, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        parts = []
        if isinstance(data, list) and data and isinstance(data[0], list):
            for seg in data[0]:
                if isinstance(seg, list) and seg:
                    parts.append(str(seg[0]))
        return "".join(parts) if parts else "(no translation)"

    def get_usage(self):
        """Google Translate is free, no usage limits."""
        return 0, 0