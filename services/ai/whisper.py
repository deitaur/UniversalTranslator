"""
Whisper transcription and spell checking.
Status is shown in a Qt HUD overlay (ui.hud.PipeHud).
"""

import ctypes
import ctypes.wintypes
import threading
from pathlib import Path
from win32.clipboard import set_clipboard_text
import globals as g

_is_recording   = False
_stop_recording = threading.Event()
_whisper_model  = None
_spell_model    = None
_spell_tokenizer = None

WHISPER_MODEL_ID = "deepdml/faster-whisper-large-v3-turbo-ct2"
SPELL_MODEL_ID   = "ai-forever/sage-fredt5-distilled-95m"
HF_CACHE_ROOT    = Path.home() / ".cache" / "huggingface" / "hub"

# ── Prerequisite checks ────────────────────────────────────────────────────────

def _model_cached(model_id: str) -> bool:
    folder = "models--" + model_id.replace("/", "--")
    d = HF_CACHE_ROOT / folder
    return d.exists() and (
        any(d.rglob("*.bin")) or any(d.rglob("*.safetensors")) or any(d.rglob("*.ct2"))
    )


def _check_prerequisites() -> dict:
    checks = {}

    pkg_missing = []
    for mod, pip_name in [("sounddevice", "sounddevice"),
                           ("numpy",       "numpy"),
                           ("faster_whisper", "faster-whisper")]:
        try:
            __import__(mod)
        except ImportError:
            pkg_missing.append(pip_name)

    checks["packages"] = {
        "ok": not pkg_missing,
        "label": "Утилиты ИИ",
        "detail": ("OK" if not pkg_missing
                   else "Для работы функции необходимо докачать модули."),
        "missing_pip": pkg_missing,
    }

    if checks["packages"]["ok"]:
        try:
            import sounddevice as sd
            devs = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
            checks["mic"] = {
                "ok": bool(devs),
                "label": "Микрофон",
                "detail": f"Найдено {len(devs)} устр." if devs else "Нет входных устройств",
            }
        except Exception as e:
            checks["mic"] = {"ok": False, "label": "Микрофон", "detail": str(e)[:80]}
    else:
        checks["mic"] = {"ok": None, "label": "Микрофон", "detail": "Сначала установите пакеты"}

    if checks["packages"]["ok"]:
        cached = _model_cached(WHISPER_MODEL_ID)
        checks["whisper_model"] = {
            "ok": cached,
            "label": "Whisper-модель",
            "detail": "В кэше" if cached else "Не скачана (~1.5 ГБ, загрузится при первом запуске)",
        }
        cached2 = _model_cached(SPELL_MODEL_ID)
        checks["spell_model"] = {
            "ok": cached2, "optional": True,
            "label": "Spell-check модель",
            "detail": "В кэше" if cached2 else "Не скачана (~200 МБ, загрузится при первом запуске)",
        }
    else:
        checks["whisper_model"] = {"ok": None, "label": "Whisper-модель",
                                    "detail": "Сначала установите пакеты"}
        checks["spell_model"]   = {"ok": None, "optional": True,
                                    "label": "Spell-check", "detail": ""}

    return checks


def _all_required_ok(checks: dict) -> bool:
    return all(c["ok"] is not False for c in checks.values() if not c.get("optional"))


# ── HUD overlay (Qt PipeHud) ──────────────────────────────────────────────────

def _cursor_pos():
    """Win32 cursor position — kept for _show_prereq_dialog positioning."""
    class _P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = _P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _get_hud():
    """Return the PipeHud singleton, creating it on first call."""
    from ui.hud import get_pipe_hud, init_pipe_hud
    hud = get_pipe_hud()
    if hud is None:
        from services.ai.recorder import stop_active
        hud = init_pipe_hud(stop_active)
    return hud


def _open_pipe_window():
    """Open the recording status HUD in the bottom-right corner."""
    _get_hud().open()


def _pipe_set_status(text: str, icon: str = "◌", icon_color: str = "#89b4fa"):
    """Update HUD status from any thread."""
    _get_hud().set_status(text, icon, icon_color)


def _pipe_show_result(translated: str):
    """Show translation result in HUD and schedule auto-close."""
    _get_hud().show_result(translated)


def _pipe_show_error(text: str):
    """Show error in HUD and schedule auto-close."""
    _get_hud().show_error(text)


def _close_pipe_window():
    """Close the HUD immediately."""
    _get_hud().close()


# ── Prereq dialog ──────────────────────────────────────────────────────────────

def _show_prereq_dialog(checks: dict, on_proceed):
    """Show ZBrush-style prereq overlay near cursor. Safe to call from any thread."""
    _get_hud().show_prereq(checks, on_proceed=on_proceed)


# ── Model loading ──────────────────────────────────────────────────────────────

def _load_whisper_model():
    """Thread-safe Whisper model loader (delegates to recorder singleton)."""
    from services.ai.recorder import load_whisper_model
    return load_whisper_model()


def _load_spell_model():
    global _spell_model, _spell_tokenizer
    if _spell_model is None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        _spell_tokenizer = AutoTokenizer.from_pretrained(SPELL_MODEL_ID)
        _spell_model = AutoModelForSeq2SeqLM.from_pretrained(SPELL_MODEL_ID)
    return _spell_model, _spell_tokenizer


def _fix_russian_spelling(text: str) -> str:
    if not text.strip():
        return text
    try:
        model, tokenizer = _load_spell_model()
        inputs  = tokenizer(text, max_length=None, padding="longest",
                            truncation=False, return_tensors="pt")
        max_len = int(inputs["input_ids"].size(1) * 1.5)
        outputs = model.generate(**inputs, max_length=max_len)
        corrected = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return corrected if corrected.strip() else text
    except Exception:
        return text


# ── Click-hook (kept for dictation.py backward compat) ────────────────────────

def _setup_click_hook():
    """Deprecated: use recorder.start_click_hook(session.stop_event) instead."""
    from services.ai.recorder import _click_hook_loop
    _click_hook_loop(_stop_recording)


# ── Main recording pipeline ────────────────────────────────────────────────────

def _start_recording():
    global _is_recording
    from services.ai.recorder import AudioSession, start_click_hook

    session = AudioSession(max_seconds=120)
    try:
        session.__enter__()
    except RuntimeError:
        _pipe_show_error("Другой модуль уже записывает звук")
        return

    _is_recording = True
    _open_pipe_window()

    try:
        start_click_hook(session.stop_event)

        audio = session.record()
        if audio is None:
            _pipe_show_error("Нет аудио — ничего не записано")
            return

        err = session.validate(audio)
        if err:
            _pipe_show_error(err)
            return

        # ── Stage 1: load / transcribe ──
        _pipe_set_status("Загрузка модели…")
        try:
            model = _load_whisper_model()
        except Exception as e:
            _pipe_show_error(f"Ошибка загрузки модели: {str(e)[:55]}")
            return

        from utils.language import get_source_lang
        src_lang     = get_source_lang()
        whisper_lang = None if src_lang == "en" else src_lang

        _pipe_set_status(f"Распознавание речи ({src_lang.upper()})…")
        try:
            segments, info = model.transcribe(audio, language=whisper_lang, beam_size=5)
            detected_lang  = getattr(info, "language", src_lang)
            transcription  = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            _pipe_show_error(f"Ошибка транскрипции: {str(e)[:55]}")
            return

        if not transcription:
            _pipe_show_error("Речь не обнаружена")
            return

        # ── Stage 2: spell check ──
        if detected_lang == "ru":
            _pipe_set_status("Проверка орфографии…")
            corrected = _fix_russian_spelling(transcription)
        else:
            corrected = transcription

        # ── Stage 3: translate ──
        _pipe_set_status("Перевод…")
        try:
            if g.current_engine == "google":
                from services.translators.google import GoogleEngine
                engine = GoogleEngine()
            elif g.current_engine == "yandex":
                from services.translators.yandex import YandexEngine
                engine = YandexEngine()
            else:
                from services.translators.deepl import DeepLEngine
                engine = DeepLEngine()
            translated = engine.translate(corrected)
        except Exception as e:
            _pipe_show_error(f"Ошибка перевода: {str(e)[:55]}")
            return

        set_clipboard_text(translated)
        _pipe_show_result(translated)

    except Exception as e:
        _pipe_show_error(f"Whisper error: {str(e)[:60]}")
    finally:
        _is_recording = False
        session.__exit__(None, None, None)


# ── Public entry point ─────────────────────────────────────────────────────────

def on_tray_whisper():
    """Toggle voice recording. Shows prereq dialog if something is missing."""
    from services.ai.recorder import is_recording, stop_active

    if is_recording():
        stop_active()
        return

    checks = _check_prerequisites()

    if _all_required_ok(checks):
        threading.Thread(target=_start_recording, daemon=True).start()
    else:
        _show_prereq_dialog(checks,
            on_proceed=lambda: threading.Thread(target=_start_recording, daemon=True).start())
