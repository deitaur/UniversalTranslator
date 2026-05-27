"""
Whisper transcription and spell checking.
Status is shown in a Qt HUD overlay (ui.hud.PipeHud).
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from pathlib import Path

from config import config, save_config_full
from win32.clipboard import set_clipboard_text
from win32.keyboard import restore_foreground, send_ctrl_v
import globals as g

log = logging.getLogger("whisper")

_is_recording   = False
_stop_recording = threading.Event()
_whisper_model  = None
_spell_model    = None
_spell_tokenizer = None
_processing_lock = threading.Lock()  # Serialize voice pipeline (record → transcribe → process → paste)

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

def _is_own_window(hwnd: int) -> bool:
    """True if `hwnd` belongs to this Python process (so we shouldn't paste into it)."""
    if not hwnd:
        return True
    pid = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == ctypes.windll.kernel32.GetCurrentProcessId()


def _resolve_actions(raw_text: str) -> "dict | None":
    """Decide which actions to apply. Returns dict {shape, translate} or None on cancel.

    If the user previously checked 'Запомнить выбор', skip the dialog and use
    the saved choice. Otherwise show the dialog and wait."""
    from ui.voice_actions_dialog import ask_voice_actions, SHAPE_NONE

    show_dialog = config.get("voice_show_dialog", True)
    if not show_dialog:
        return {
            "shape":     config.get("voice_action_shape", SHAPE_NONE),
            "translate": bool(config.get("voice_action_translate", False)),
        }
    result = ask_voice_actions(raw_text)
    return result  # may be None on Cancel


def _apply_actions(raw_text: str, detected_lang: str, shape: str, translate: bool) -> str:
    """Run the chosen pipeline. Shape runs first (cleanup/format), translate last."""
    from services.ai.voice_actions import (
        apply_spelling, apply_deep_edit, apply_tasks, apply_translate,
    )
    from ui.voice_actions_dialog import SHAPE_SPELLING, SHAPE_DEEP, SHAPE_TASKS

    text = raw_text
    if shape == SHAPE_SPELLING:
        text = apply_spelling(text, detected_lang, _pipe_set_status)
    elif shape == SHAPE_DEEP:
        text = apply_deep_edit(text, _pipe_set_status)
    elif shape == SHAPE_TASKS:
        text = apply_tasks(text, _pipe_set_status)

    if translate:
        text = apply_translate(text, _pipe_set_status)

    return text


def _paste_into(hwnd: int, text: str) -> bool:
    """Restore foreground to `hwnd` and paste via Ctrl+V. Returns True if pasted."""
    set_clipboard_text(text)
    if _is_own_window(hwnd):
        # Triggered from tray (or no target captured) — leave in clipboard only.
        return False
    restore_foreground(hwnd)
    time.sleep(0.12)
    send_ctrl_v(skip_wait=True)
    return True


def _start_recording(target_hwnd: int = 0):
    global _is_recording
    from services.ai.recorder import AudioSession, start_click_hook
    from services.ai.voice_actions import is_hallucination

    # Acquire lock to serialize the entire pipeline (record → transcribe → process → paste)
    if not _processing_lock.acquire(blocking=False):
        from ui.notifications import show_toast
        show_toast("⏳ Подождите, идет обработка голоса…")
        return

    try:
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

            # ── Stage 1: transcribe ──
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

            if not transcription or is_hallucination(transcription):
                _pipe_show_error("Речь не распознана — говорите чётче или выберите другой микрофон")
                return

            # ── Stage 2: ask user what to do (or use saved choice) ──
            _pipe_set_status("Жду выбор действия…")
            choice = _resolve_actions(transcription)
            if choice is None:
                log.debug("User cancelled voice-actions dialog")
                _pipe_show_error("отменено")
                return

            # ── Stage 3: apply chosen pipeline ──
            try:
                processed = _apply_actions(
                    transcription, detected_lang, choice["shape"], choice["translate"],
                )
            except Exception as e:
                log.error("Action pipeline failed: %s", e, exc_info=True)
                _pipe_show_error(f"Ошибка обработки: {str(e)[:55]}")
                return

            # ── Stage 4: paste & notify ──
            _pipe_set_status("Вставляю…")
            pasted = _paste_into(target_hwnd, processed)

            # Play success sound + show toast for translation
            if choice["translate"]:
                from ui.notifications import play_success_sound, show_translation_toast
                play_success_sound()
                show_translation_toast(processed)

            preview = processed[:100] + ("…" if len(processed) > 100 else "")
            label = "✓ вставлено" if pasted else "✓ в буфере"
            _get_hud().show_result(preview, label)

        except Exception as e:
            log.error("Whisper pipeline error: %s", e, exc_info=True)
            _pipe_show_error(f"Whisper error: {str(e)[:60]}")
        finally:
            _is_recording = False
            session.__exit__(None, None, None)
    finally:
        _processing_lock.release()


# ── Public entry point ─────────────────────────────────────────────────────────

def on_tray_whisper():
    """Toggle voice recording. Shows prereq dialog if something is missing."""
    from services.ai.recorder import is_recording, stop_active

    if is_recording():
        stop_active()
        return

    # Capture target foreground window NOW — by the time the user finishes
    # talking, focus may have moved (HUD, dialog). We paste back into the
    # window that was active when the hotkey was pressed.
    target_hwnd = ctypes.windll.user32.GetForegroundWindow()

    checks = _check_prerequisites()

    def _spawn():
        threading.Thread(target=_start_recording, args=(target_hwnd,), daemon=True).start()

    if _all_required_ok(checks):
        _spawn()
    else:
        _show_prereq_dialog(checks, on_proceed=_spawn)


def reset_voice_dialog_preference():
    """Clear the 'remembered choice' so the dialog shows again next time."""
    config["voice_show_dialog"] = True
    save_config_full()
