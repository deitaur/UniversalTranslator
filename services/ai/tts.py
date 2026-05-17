"""
Text-to-speech — two engines selectable in Settings:
  sapi  — Windows SAPI (built-in, offline, robotic)
  gtts  — Google Translate TTS (natural "Google woman" voice, needs internet + pip install gtts)
"""

import ctypes
import os
import tempfile
import threading
import time
import logging

log = logging.getLogger("tts")

_speak_lock  = threading.Lock()
_stop_event  = threading.Event()
_mci         = ctypes.windll.winmm   # Windows MCI — plays MP3 natively, no extra deps


# ── Engine helpers ────────────────────────────────────────────────────────────

def _current_engine() -> str:
    from config import config
    return config.get("tts_engine", "gtts")


# ── MCI MP3 player (Windows built-in, works with gTTS output) ────────────────

def _mci_play(path: str, speed: float = 1.0):
    """Play an MP3 via Windows MCI. Blocks until done or _stop_event is set."""
    alias = "_tts_play_"
    _mci.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    if abs(speed - 1.0) > 0.05:
        _mci.mciSendStringW(f'set {alias} speed {int(speed * 1000)}', None, 0, None)
    _mci.mciSendStringW(f'play {alias}', None, 0, None)
    buf = ctypes.create_unicode_buffer(128)
    try:
        while not _stop_event.is_set():
            _mci.mciSendStringW(f'status {alias} mode', buf, 128, None)
            if buf.value in ("stopped", ""):
                break
            time.sleep(0.08)
    finally:
        _mci.mciSendStringW(f'stop {alias}', None, 0, None)
        _mci.mciSendStringW(f'close {alias}', None, 0, None)


# ── Google TTS engine ─────────────────────────────────────────────────────────

def _speak_gtts(text: str, lang_code: str, speed: float = 1.0):
    try:
        from gtts import gTTS
    except ImportError:
        log.warning("gTTS not installed — falling back to SAPI. Run: pip install gtts")
        _speak_sapi(text, lang_code, speed)
        return

    _GTTS_LANG_MAP = {"zh": "zh-CN", "pt": "pt-BR"}
    gtts_lang = _GTTS_LANG_MAP.get(lang_code[:2], lang_code[:2])

    try:
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tts.save(tmp.name)
        _mci_play(tmp.name, speed)
    except Exception as e:
        log.warning("gTTS speak failed: %s — falling back to SAPI", e)
        _speak_sapi(text, lang_code, speed)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ── Windows SAPI engine ───────────────────────────────────────────────────────

def _best_sapi_voice(sapi_voices, lang_code: str):
    _HINTS = {
        "ru": ["russian"], "en": ["english"], "de": ["german", "deutsch"],
        "fr": ["french"],  "es": ["spanish"], "zh": ["chinese"],
        "ja": ["japanese"],"ko": ["korean"],  "pl": ["polish"],
        "uk": ["ukrainian"],"it": ["italian"],"pt": ["portuguese"],
        "nl": ["dutch"],   "tr": ["turkish"], "ar": ["arabic"],
        "cs": ["czech"],
    }
    hints = _HINTS.get(lang_code[:2], [lang_code[:2]])
    for voice in sapi_voices:
        if any(h in voice.GetDescription().lower() for h in hints):
            return voice
    return None


def _speak_sapi(text: str, lang_code: str, speed: float = 1.0):
    try:
        import comtypes.client
        sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        sapi.Volume = 100
        # SAPI Rate: -10 (slowest) to 10 (fastest). Map 1.0×→0, 2.0×→5, 3.0×→10
        sapi.Rate   = max(-10, min(10, round((speed - 1.0) * 5)))
        voice = _best_sapi_voice(sapi.GetVoices(), lang_code)
        if voice:
            sapi.Voice = voice
        SVSFlagsAsync = 1
        sapi.Speak(text, SVSFlagsAsync)
        while not _stop_event.is_set():
            if sapi.Status.RunningState == 1:   # SRSEDone
                break
            time.sleep(0.1)
        if _stop_event.is_set():
            sapi.Skip("Sentence", 100)
    except Exception as e:
        log.error("SAPI TTS failed: %s", e)


# ── Public API ────────────────────────────────────────────────────────────────

def speak(text: str, lang_code: str = "en", speed: float = 1.0):
    """Speak *text* asynchronously at *speed* (1.0 = normal, 2.0 = double). Cancels any ongoing speech first."""
    if not text.strip():
        return
    stop()
    _stop_event.clear()

    engine = _current_engine()

    def _run():
        with _speak_lock:
            if _stop_event.is_set():
                return
            if engine == "gtts":
                _speak_gtts(text, lang_code, speed)
            else:
                _speak_sapi(text, lang_code, speed)

    threading.Thread(target=_run, daemon=True).start()


def stop():
    """Cancel ongoing speech immediately."""
    _stop_event.set()
    # Also force-stop MCI in case it's mid-playback
    try:
        _mci.mciSendStringW("stop _tts_play_", None, 0, None)
        _mci.mciSendStringW("close _tts_play_", None, 0, None)
    except Exception:
        pass


def is_available() -> bool:
    return True   # SAPI is always available on Windows; gTTS falls back to SAPI


def gtts_installed() -> bool:
    try:
        import gtts  # noqa: F401
        return True
    except ImportError:
        return False


def speak_to_bytes(text: str, lang_code: str = "en") -> bytes:
    """Convert text to MP3 bytes via gTTS. Returns empty bytes if unavailable."""
    import io
    try:
        from gtts import gTTS
    except ImportError:
        log.warning("gTTS not installed — speak_to_bytes unavailable")
        return b""

    _GTTS_LANG_MAP = {"zh": "zh-CN", "pt": "pt-BR"}
    gtts_lang = _GTTS_LANG_MAP.get(lang_code[:2], lang_code[:2])
    try:
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()
    except Exception as e:
        log.error("speak_to_bytes error: %s", e)
        return b""
