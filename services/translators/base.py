"""
Base class for translation engines
"""

class TranslationEngine:
    """Abstract base class for translation engines."""

    def translate(self, text):
        """Translate text to English. Must be implemented by subclasses."""
        raise NotImplementedError

    def translate_to(self, text, target_lang_code: str):
        """Translate text to the given language code; source is auto-detected."""
        raise NotImplementedError

    def get_usage(self):
        """Get usage data if available. Returns (count, limit)."""
        return 0, 0