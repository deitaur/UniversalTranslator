"""
Yandex Translate engine
"""

import requests
from config import config
from utils.language import get_source_lang, get_target_lang

YANDEX_API_URL = "https://translate.api.cloud.yandex.net/translate/v2/translate"

class YandexEngine:
    """Yandex Translate engine."""

    def translate(self, text):
        """Translate text using Yandex Cloud Translate API."""
        api_key = config.get("yandex_api_key", "")
        if not api_key:
            raise RuntimeError("Yandex API key not set. Go to Settings to add it.")
        folder_id = config.get("yandex_folder_id", "")
        if not folder_id:
            raise RuntimeError("Yandex Folder ID not set. Go to Settings to add it.")
        body = {
            "folderId": folder_id,
            "texts": [text],
            "targetLanguageCode": "en",
            "sourceLanguageCode": get_source_lang(),
        }
        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        r = requests.post(YANDEX_API_URL, json=body, headers=headers, timeout=(4, 20))
        r.raise_for_status()
        data = r.json()
        translations = data.get("translations", [])
        if translations and translations[0].get("text"):
            return translations[0]["text"]
        return "(no translation)"

    def translate_reverse(self, text):
        """Translate English text back to target language."""
        api_key = config.get("yandex_api_key", "")
        if not api_key:
            raise RuntimeError("Yandex API key not set.")
        folder_id = config.get("yandex_folder_id", "")
        if not folder_id:
            raise RuntimeError("Yandex Folder ID not set.")
        body = {
            "folderId": folder_id,
            "texts": [text],
            "targetLanguageCode": get_target_lang(),
            "sourceLanguageCode": "en",
        }
        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        r = requests.post(YANDEX_API_URL, json=body, headers=headers, timeout=(4, 20))
        r.raise_for_status()
        data = r.json()
        translations = data.get("translations", [])
        if translations and translations[0].get("text"):
            return translations[0]["text"]
        return "(no translation)"

    def translate_to(self, text, target_lang_code: str) -> str:
        """Translate text to any target language; source is auto-detected by Yandex."""
        api_key = config.get("yandex_api_key", "")
        if not api_key:
            raise RuntimeError("Yandex API key not set. Go to Settings to add it.")
        folder_id = config.get("yandex_folder_id", "")
        if not folder_id:
            raise RuntimeError("Yandex Folder ID not set. Go to Settings to add it.")
        body = {
            "folderId": folder_id,
            "texts": [text],
            "targetLanguageCode": target_lang_code,
        }
        headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}
        r = requests.post(YANDEX_API_URL, json=body, headers=headers, timeout=(4, 20))
        r.raise_for_status()
        translations = r.json().get("translations", [])
        return translations[0]["text"] if translations and translations[0].get("text") \
            else "(no translation)"

    def get_usage(self):
        """Yandex Translate is free, no usage limits."""
        return 0, 0