"""
Voice Polish — Ctrl+Alt+F
Record speech → Whisper STT → Ollama (format/polish) → clipboard → Ctrl+V.
Progress shown in the bottom-right HUD.
"""

import threading
import time
import logging

log = logging.getLogger("polish")

# ── Whisper hallucination filter ──────────────────────────────────────────────

_HALLUCINATIONS = {
    "продолжение следует", "спасибо за просмотр", "подпишитесь на канал",
    "до свидания", "thank you for watching", "thanks for watching",
    "please subscribe", "to be continued", "subscribe",
    "[музыка]", "[music]", "[аплодисменты]", "[applause]",
}


def _is_hallucination(text: str) -> bool:
    cleaned = text.strip().lower().rstrip(".!?,…").strip()
    return cleaned in _HALLUCINATIONS or len(cleaned) < 3


# ── Prompts ───────────────────────────────────────────────────────────────────

# Prompts are used as the SYSTEM message — raw text goes separately as USER message.

# ── Quick polish: punctuation + light cleanup (gemma-friendly: short & direct) ─
_POLISH_SYSTEM = """\
Edit this voice-to-text. Remove filler words (um, uh, like, ну, вот, э-э, как бы, типа, значит). Fix punctuation. Keep the original language. Output ONLY the corrected text — no introduction, no explanation."""

# ── Full editorial reformat ───────────────────────────────────────────────────
_FORMAT_SYSTEM = """\
You are a professional text editor. The user sends a raw voice-to-text transcript. Your job: clean and restructure it. Output only the final result.

CLEAN: Delete filler words (do not replace, just remove).
  Russian: ну, вот, ну вот, э-э, ммм, как бы, в общем, собственно, типа, значит, это самое, короче, понимаешь, то есть, так сказать, на самом деле
  English: um, uh, like, you know, so, right, basically, actually, I mean, kind of, well, anyway
Delete repetitions, false starts, self-corrections. Fix grammar and spelling.

STRUCTURE: Choose the right format for the content.
  One or two ideas → clean paragraph.
  List of items → bullet list, each item on its own line starting with "- ".
  Steps or sequence → numbered list: 1. 2. 3.
  Tasks or to-do → checklist lines starting with "[ ] ".
  Multiple separate topics → topic name in CAPITALS + colon on its own line, then content below.
  Mixed content → combine formats, blank line between blocks.
  Plain text only — no markdown symbols (#, *, **, ~~).

OUTPUT: Start directly with the content. Do not write "Here is", "Sure", "Вот текст", or any preamble. Keep the original language, do not translate."""



# ── HUD helpers (thin wrappers so _start_polish doesn't import whisper at top) ─

def _hud_open():
    from services.ai.whisper import _open_pipe_window
    _open_pipe_window()


def _hud_status(text, icon="◌", color="#89b4fa"):
    from services.ai.whisper import _pipe_set_status
    _pipe_set_status(text, icon, color)


def _hud_error(text):
    from services.ai.whisper import _pipe_show_error
    _pipe_show_error(text)


def _hud_result(text, label="готово"):
    from ui.hud import get_pipe_hud
    hud = get_pipe_hud()
    if hud:
        hud.show_result(text, label)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _start_polish():
    from services.ai.recorder import AudioSession, start_click_hook, load_whisper_model
    from utils.language import get_source_lang

    session = AudioSession(max_seconds=120)
    try:
        session.__enter__()
    except RuntimeError:
        _hud_error("Запись уже идёт — нажмите Ctrl+Alt+F ещё раз чтобы остановить")
        return

    _hud_open()

    try:
        start_click_hook(session.stop_event)

        # ── Stage 1: record ───────────────────────────────────────────────────
        audio = session.record()
        if audio is None:
            _hud_error("Нет аудио — проверьте микрофон")
            return

        err = session.validate(audio)
        if err:
            _hud_error(err)
            return

        # ── Stage 2: transcribe ───────────────────────────────────────────────
        _hud_status("Загрузка Whisper…", "⏳", "#89b4fa")
        try:
            model = load_whisper_model()
        except Exception as e:
            _hud_error(f"Ошибка загрузки модели: {str(e)[:55]}")
            return

        src_lang     = get_source_lang()
        whisper_lang = None if src_lang == "en" else src_lang
        _hud_status(f"Распознаю речь ({src_lang.upper()})…", "◌", "#89b4fa")
        try:
            # beam_size=1 — быстрее; LLM всё равно исправит ошибки транскрипции
            segments, _info = model.transcribe(audio, language=whisper_lang, beam_size=1)
            raw_text = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            _hud_error(f"Ошибка распознавания: {str(e)[:55]}")
            return

        log.debug("Whisper raw: %r", raw_text[:100])
        if not raw_text or _is_hallucination(raw_text):
            _hud_error("Речь не распознана — говорите чётче или выберите другой микрофон")
            return

        # ── Stage 3: Ollama polish (streaming) ────────────────────────────────
        from config import config
        from services.ai.ollama import check_ollama, get_polish_model
        import requests
        import json as _json

        format_mode = config.get("format_output", True)
        system_msg  = _FORMAT_SYSTEM if format_mode else _POLISH_SYSTEM
        model_name  = get_polish_model(format_mode)
        preview_in = raw_text[:30] + ("…" if len(raw_text) > 30 else "")
        _hud_status(f"[{model_name.split(':')[0]}] редактирую…  «{preview_in}»", "✨", "#cba6f7")

        polished = raw_text
        ai_ok    = False

        if not check_ollama():
            log.warning("Ollama unavailable — pasting raw text")
            _hud_status("Ollama недоступна — вставляю без редактуры", "⚠", "#f9e2af")
            time.sleep(1.5)
        else:
            ollama_url = "http://localhost:11434/api/chat"
            # Gemma игнорирует system-роль — инструкцию кладём в user-сообщение.
            # Qwen/Llama → нормальный system+user split.
            if "gemma" in model_name.lower():
                messages = [
                    {"role": "user",
                     "content": f"{system_msg}\n\n---\n{raw_text}"},
                ]
            else:
                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": raw_text},
                ]
            # num_ctx=8192 — явно задаём окно, чтобы промпт + ответ не упирались
            # в дефолтные 2048 токенов Ollama
            options = {"num_predict": 2048, "num_ctx": 8192}
            log.debug("system=%d chars  user=%d chars  model=%s",
                      len(system_msg), len(raw_text), model_name)

            # ── Pass 1: streaming ─────────────────────────────────────────────
            t0     = time.time()
            result = ""
            try:
                body = {"model": model_name, "messages": messages,
                        "stream": True, "options": options}
                with requests.post(ollama_url, json=body,
                                   timeout=300, stream=True) as r:
                    r.raise_for_status()
                    chunks = []
                    for line in r.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            data = _json.loads(line)
                        except Exception:
                            log.debug("Unparseable line: %r", line[:80])
                            continue
                        token = data.get("message", {}).get("content", "")
                        if token:
                            chunks.append(token)
                        if chunks and len(chunks) % 20 == 0:
                            partial = "".join(chunks)[-28:]
                            _hud_status(
                                f"[{model_name.split(':')[0]}] {int(time.time()-t0)}s  …{partial}",
                                "✨", "#cba6f7",
                            )
                        if data.get("done"):
                            log.debug("Ollama done reason=%r tokens=%d",
                                      data.get("done_reason"), len(chunks))
                            break
                result = "".join(chunks).strip()
                log.debug("Streaming result: %d chars", len(result))
            except requests.exceptions.Timeout:
                log.warning("Polish streaming timeout")
            except Exception as e:
                log.warning("Ollama streaming error: %s", e)

            # ── Pass 2: non-streaming retry if streaming returned empty ───────
            if not result:
                log.warning("Streaming returned empty — retrying non-streaming")
                _hud_status(f"[{model_name.split(':')[0]}] повтор (no-stream)…",
                            "◌", "#cba6f7")
                try:
                    body2 = {"model": model_name, "messages": messages,
                             "stream": False, "options": options}
                    r2 = requests.post(ollama_url, json=body2, timeout=300)
                    r2.raise_for_status()
                    result = (r2.json()
                              .get("message", {})
                              .get("content", "")
                              .strip())
                    log.debug("Non-streaming result: %d chars", len(result))
                except Exception as e:
                    log.warning("Non-streaming retry failed: %s", e)

            if result:
                polished = result
                ai_ok    = True
                log.debug("Polish OK %ds %d chars", int(time.time()-t0), len(polished))
            else:
                log.warning("Both passes returned empty")
                _hud_status("Модель не ответила — вставляю как есть", "⚠", "#f9e2af")
                time.sleep(2.0)

        log.debug("Polished (ai=%s): %r", ai_ok, polished[:120])

        # ── Stage 4: clipboard + paste ────────────────────────────────────────
        _hud_status("Вставляю в поле…", "📋", "#a6e3a1")
        try:
            from win32.clipboard import set_clipboard_text
            from win32.keyboard import send_ctrl_v
            set_clipboard_text(polished)
            time.sleep(0.15)
            send_ctrl_v()
        except Exception as e:
            _hud_error(f"Ошибка вставки: {str(e)[:55]}")
            return

        # HUD result: clearly show whether AI actually edited or fell back
        if ai_ok:
            label   = "✨ отредактировано"
            preview = polished[:100] + ("…" if len(polished) > 100 else "")
        else:
            label   = "⚠ вставлено без редактуры  (сырой текст)"
            # Show the raw transcription so user can see what was pasted
            preview = raw_text[:100] + ("…" if len(raw_text) > 100 else "")
        _hud_result(preview, label)

    except Exception as e:
        log.error("polish error: %s", e, exc_info=True)
        _hud_error(f"Ошибка: {str(e)[:60]}")
    finally:
        session.__exit__(None, None, None)


# ── Public entry point ────────────────────────────────────────────────────────

def on_hotkey_polish():
    """Toggle voice-polish (Ctrl+Alt+F). Second press cancels an active session."""
    from services.ai.recorder import stop_active, is_recording

    if is_recording():
        stop_active()
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
