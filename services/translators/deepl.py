"""
DeepL translation engine
"""

import requests
from config import config, deepl_api_base
from utils.language import get_source_lang_upper, get_target_lang_upper

DEEPL_API_PRO = "https://api.deepl.com/v2"
DEEPL_API_FREE = "https://api-free.deepl.com/v2"

class DeepLEngine:
    """DeepL translation engine."""

    def deepl_headers(self):
        return {"Authorization": f"DeepL-Auth-Key {config.get('api_key', '')}"}

    def fetch_usage(self):
        """Fetch usage data from DeepL API."""
        try:
            r = requests.get(f"{deepl_api_base}/usage", headers=self.deepl_headers(), timeout=10)
            r.raise_for_status()
            d = r.json()
            return d.get("character_count", 0), d.get("character_limit", 0)
        except Exception:
            return 0, 0

    def translate(self, text):
        """Translate text using DeepL API."""
        r = requests.post(
            f"{deepl_api_base}/translate",
            headers=self.deepl_headers(),
            data={"text": text, "source_lang": get_source_lang_upper(), "target_lang": "EN"},
            timeout=(4, 20),
        )
        r.raise_for_status()
        translations = r.json().get("translations", [])
        return translations[0]["text"] if translations else "(no translation)"

    def translate_reverse(self, text):
        """Translate English text back to target language."""
        r = requests.post(
            f"{deepl_api_base}/translate",
            headers=self.deepl_headers(),
            data={"text": text, "source_lang": "EN", "target_lang": get_target_lang_upper()},
            timeout=(4, 20),
        )
        r.raise_for_status()
        translations = r.json().get("translations", [])
        return translations[0]["text"] if translations else "(no translation)"

    def translate_to(self, text, target_lang_code: str) -> str:
        """Translate text to any target language; source is auto-detected by DeepL."""
        r = requests.post(
            f"{deepl_api_base}/translate",
            headers=self.deepl_headers(),
            data={"text": text, "target_lang": target_lang_code.upper()},
            timeout=(4, 20),
        )
        r.raise_for_status()
        translations = r.json().get("translations", [])
        return translations[0]["text"] if translations else "(no translation)"

    def get_usage(self):
        """Get usage data."""
        return self.fetch_usage()