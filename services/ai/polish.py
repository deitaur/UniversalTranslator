"""
Voice Polish — Ctrl+Alt+F
Record speech → Whisper STT → Ollama (friendly tone + punctuation)
→ clipboard → Ctrl+V into active field.

Progress shown in the mouse-cursor HUD (same as dictation/whisper).
Click HUD or press Ctrl+Alt+F again to stop recording early.
"""

import threading
import time
import logging
import numpy as np

log = logging.getLogger("polish")

_is_running  = False
_MIN_RMS     = 0.008   # minimum audio level — below this = probably silence
_MIN_SECONDS = 0.5     # ignore clips shorter than 0.5 s of real speech

# Whisper hallucinations it generates on silence (multilingual)
_HALLUCINATIONS = {
    "продолжение следует",
    "спасибо за просмотр",
    "подпишитесь на канал",
    "до свидания",
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "to be continued",
    "subscribe",
    "[музыка]",
    "[music]",
    "[аплодисменты]",
    "[applause]",
}

_POLISH_PROMPT = (
    "You receive a raw speech-to-text transcription. Your only task:\n"
    "1. Add correct punctuation (periods, commas, question marks, etc.).\n"
    "2. Fix obvious speech-recognition errors without changing meaning.\n"
    "3. Make the tone warm, friendly, and natural — like a quick message to a colleague.\n"
    "4. Keep the ORIGINAL language of the text (do NOT translate).\n"
    "5. Output ONLY the final polished text — no explanations, no quotes, no comments.\n\n"
    "Transcription:\n"
)


def _is_hallucination(text: str) -> bool:
    """Return True if whisper just made something up (silence artifact)."""
    cleaned = text.strip().lower().rstrip(".!?,…").strip()
    return cleaned in _HALLUCINATIONS or len(cleaned) < 3


def _audio_has_speech(audio: np.ndarray) -> bool:
    """True if the recording contains enough non-silence."""
    rms = float(np.sqrt(np.mean(audio ** 2)))
    log.debug("Audio RMS: %.4f (min=%.4f)", rms, _MIN_RMS)
    return rms >= _MIN_RMS


def _start_polish():
    global _is_running
    _is_running = True

    from services.ai.whisper import (
        _open_pipe_window, _pipe_set_status, _pipe_show_error,
        _load_whisper_model, _stop_recording, _setup_click_hook,
        _pipe_show_result,
    )
    from utils.language import get_source_lang

    _stop_recording.clear()
    _open_pipe_window()

    try:
        import sounddevice as sd

        sample_rate = 16000
        audio_data  = []

        def _cb(indata, frames, t, status):
            audio_data.append(indata.copy())

        threading.Thread(target=_setup_click_hook, daemon=True).start()

        # Recording phase — HUD blinks red while listening
        # (The HUD shows "Запись… (клик — стоп)" by default while blinking)
        # We just wait until click or timeout
        with sd.InputStream(callback=_cb, channels=1,
                            samplerate=sample_rate, blocksize=1024):
            t0 = time.time()
            while not _stop_recording.is_set():
                if (time.time() - t0) >= 120:
                    break
                time.sleep(0.05)

        if not audio_data:
            _pipe_show_error("Нет аудио — проверьте микрофон")
            return

        audio = np.concatenate(audio_data, axis=0).flatten()
        duration = len(audio) / sample_rate
        log.debug("Recorded %.1f s", duration)

        # ── Check volume ─────────────────────────────────────────────────────
        if not _audio_has_speech(audio):
            _pipe_show_error("Ничего не слышно — говорите громче или выберите другой микрофон")
            return

        if duration < _MIN_SECONDS:
            _pipe_show_error("Слишком короткая запись — говорите дольше")
            return

        # ── Stage 1: load model ───────────────────────────────────────────────
        _pipe_set_status("Загрузка Whisper…", "⏳", "#89b4fa")
        try:
            model = _load_whisper_model()
        except Exception as e:
            _pipe_show_error(f"Ошибка загрузки модели: {str(e)[:55]}")
            return

        # ── Stage 2: transcribe ───────────────────────────────────────────────
        src_lang     = get_source_lang()
        whisper_lang = None if src_lang == "en" else src_lang
        _pipe_set_status(f"Распознаю речь ({src_lang.upper()})…", "◌", "#89b4fa")
        try:
            segments, _ = model.transcribe(audio, language=whisper_lang, beam_size=5)
            raw_text    = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            _pipe_show_error(f"Ошибка распознавания: {str(e)[:55]}")
            return

        log.debug("Whisper raw: %r", raw_text[:100])

        if not raw_text or _is_hallucination(raw_text):
            _pipe_show_error("Речь не распознана — говорите чётче или выберите другой микрофон")
            return

        # ── Stage 3: polish via Ollama ────────────────────────────────────────
        preview_in = raw_text[:35] + ("…" if len(raw_text) > 35 else "")
        _pipe_set_status(f"ИИ: «{preview_in}»", "✨", "#cba6f7")
        try:
            from services.ai.ollama import check_ollama, get_ollama_model
            import requests

            if not check_ollama():
                polished = raw_text
                log.warning("Ollama unavailable — using raw transcription")
            else:
                import json
                body = {
                    "model": get_ollama_model(),
                    "messages": [
                        {"role": "user", "content": _POLISH_PROMPT + raw_text}
                    ],
                    "stream": False,
                    "options": {"num_predict": 1024},
                }
                r = requests.post(
                    "http://localhost:11434/api/chat",
                    json=body, timeout=60,
                )
                r.raise_for_status()
                r.encoding = "utf-8"
                polished = r.json().get("message", {}).get("content", "").strip()
                if not polished:
                    polished = raw_text

        except Exception as e:
            log.warning("Polish LLM error: %s — using raw text", e)
            polished = raw_text

        log.debug("Polished: %r", polished[:100])

        # ── Stage 4: clipboard + paste ────────────────────────────────────────
        _pipe_set_status("Вставляю в поле…", "📋", "#a6e3a1")
        try:
            from win32.clipboard import set_clipboard_text
            from win32.keyboard import send_ctrl_v
            set_clipboard_text(polished)
            time.sleep(0.15)
            send_ctrl_v()
        except Exception as e:
            _pipe_show_error(f"Ошибка вставки: {str(e)[:55]}")
            return

        # Show first ~60 chars of result in HUD, then auto-close
        _pipe_show_result(polished[:80] + ("…" if len(polished) > 80 else ""))

    except Exception as e:
        log.error("polish error: %s", e, exc_info=True)
        _pipe_show_error(f"Ошибка: {str(e)[:60]}")
    finally:
        _is_running = False
        _stop_recording.clear()


def on_hotkey_polish():
    """Toggle voice-polish recording (Ctrl+Alt+F)."""
    global _is_running
    if _is_running:
        from services.ai.whisper import _stop_recording
        _stop_recording.set()
        return

    from services.ai.whisper import _check_prerequisites, _all_required_ok, _show_prereq_dialog
    checks = _check_prerequisites()
    if _all_required_ok(checks):
        threading.Thread(target=_start_polish, daemon=True).start()
    else:
        _show_prereq_dialog(
            checks,
            on_proceed=lambda: threading.Thread(target=_start_polish, daemon=True).start(),
        )
