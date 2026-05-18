"""
Voice Polish — Ctrl+Alt+F
Record speech → Whisper STT → Ollama rewrite (friendly tone + punctuation)
→ clipboard → Ctrl+V into active field.
Progress shown in the same mouse-cursor HUD as dictation/whisper.
"""

import threading
import time
import logging

log = logging.getLogger("polish")

_is_running = False

_POLISH_PROMPT = (
    "You receive raw speech transcription. Your task:\n"
    "1. Add correct punctuation (periods, commas, question marks, etc.).\n"
    "2. Fix obvious speech-to-text errors.\n"
    "3. Make the tone warm, friendly, and natural — like a message to a colleague.\n"
    "4. Keep the original meaning and language exactly.\n"
    "5. Output ONLY the polished text, nothing else — no explanations, no quotes.\n\n"
    "Raw transcription:\n"
)


def _start_polish():
    global _is_running
    _is_running = True

    from services.ai.whisper import (
        _open_pipe_window, _pipe_set_status, _pipe_show_error,
        _load_whisper_model, _stop_recording, _setup_click_hook,
    )
    from utils.language import get_source_lang

    _stop_recording.clear()
    _open_pipe_window()

    try:
        import sounddevice as sd
        import numpy as np

        sample_rate = 16000
        audio_data  = []

        def _cb(indata, frames, t, status):
            audio_data.append(indata.copy())

        threading.Thread(target=_setup_click_hook, daemon=True).start()

        _pipe_set_status("🎙  Говорите… (клик — стоп)", "🎙", "#f38ba8")

        with sd.InputStream(callback=_cb, channels=1,
                            samplerate=sample_rate, blocksize=1024):
            t0 = time.time()
            while not _stop_recording.is_set():
                if (time.time() - t0) >= 120:
                    break
                time.sleep(0.05)

        if not audio_data:
            _pipe_show_error("Нет аудио — ничего не записано")
            return

        audio = np.concatenate(audio_data, axis=0).flatten()

        # ── Stage 1: transcribe ──────────────────────────────────────────────
        _pipe_set_status("Загрузка модели…", "⏳", "#89b4fa")
        try:
            model = _load_whisper_model()
        except Exception as e:
            _pipe_show_error(f"Ошибка модели: {str(e)[:55]}")
            return

        src_lang     = get_source_lang()
        whisper_lang = None if src_lang == "en" else src_lang

        _pipe_set_status(f"Распознавание ({src_lang.upper()})…", "◌", "#89b4fa")
        try:
            segments, _ = model.transcribe(audio, language=whisper_lang, beam_size=5)
            raw_text    = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            _pipe_show_error(f"Ошибка транскрипции: {str(e)[:55]}")
            return

        if not raw_text:
            _pipe_show_error("Речь не распознана")
            return

        log.debug("Raw transcription: %s", raw_text[:80])

        # ── Stage 2: polish via Ollama ───────────────────────────────────────
        _pipe_set_status("ИИ улучшает текст…", "✨", "#cba6f7")
        try:
            from services.ai.ollama import check_ollama, get_ollama_model
            import requests, json

            if not check_ollama():
                # Fallback: just fix spelling if Ollama is down
                polished = raw_text
                log.warning("Ollama unavailable — skipping polish step")
            else:
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
                polished = r.json().get("message", {}).get("content", raw_text).strip()
                if not polished:
                    polished = raw_text
        except Exception as e:
            log.warning("Polish LLM error: %s — using raw text", e)
            polished = raw_text

        log.debug("Polished: %s", polished[:80])

        # ── Stage 3: clipboard + paste ───────────────────────────────────────
        _pipe_set_status("Вставка…", "📋", "#a6e3a1")
        try:
            from win32.clipboard import set_clipboard_text
            from win32.keyboard import send_ctrl_v
            set_clipboard_text(polished)
            time.sleep(0.15)
            send_ctrl_v()
        except Exception as e:
            _pipe_show_error(f"Ошибка вставки: {str(e)[:55]}")
            return

        # Show preview in HUD
        from services.ai.whisper import _pipe_show_result
        _pipe_show_result(polished[:120] + ("…" if len(polished) > 120 else ""))

    except Exception as e:
        log.error("polish error: %s", e)
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
