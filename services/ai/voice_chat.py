"""Voice AI Chat loop — Ctrl+Alt+V
Record (VAD) → Whisper STT → Ollama LLM → TTS → repeat
"""

import json
import threading
import time

from config import config
from services.ai.whisper import _load_whisper_model, _fix_russian_spelling
from services.ai.ollama import OLLAMA_URL, get_ollama_model

SILENCE_RMS = 0.012
SILENCE_SEC = 1.8
MAX_SEC     = 45

_VOICE_CHAT_SYSTEM = (
    "You are a helpful voice assistant. Keep responses short and conversational — "
    "2–3 sentences maximum. No markdown, bullet points, or code blocks. "
    "Speak naturally as in a real voice conversation."
)

_is_active     = False
_stop_evt      = threading.Event()
_interrupt_evt = threading.Event()


# ── HUD helpers ───────────────────────────────────────────────────────────────

def setup_hud():
    """Create the VoiceChatHud singleton on the Qt main thread.
    Called from main.py after QApplication is created, before app.exec()."""
    from ui.hud import init_vc_hud
    hud = init_vc_hud()
    hud.closed.connect(_stop_evt.set)
    hud.clicked.connect(_interrupt_evt.set)


def _hud():
    from ui.hud import get_vc_hud
    return get_vc_hud()


def _vc_set_state(state: str, sub: str = ""):
    h = _hud()
    if h:
        h.set_state(state, sub)


# ── VAD recording ─────────────────────────────────────────────────────────────

def _record_with_vad():
    """Record until silence-after-speech or stop event. Returns np.ndarray or None."""
    import numpy as np
    import sounddevice as sd

    sample_rate   = 16000
    block_ms      = 50
    block_size    = int(sample_rate * block_ms / 1000)
    audio_chunks  = []
    silence_count = 0
    silence_limit = int(SILENCE_SEC * 1000 / block_ms)
    max_chunks    = int(MAX_SEC * 1000 / block_ms)
    has_speech    = False

    _vc_set_state("listening")

    def _cb(indata, frames, t, status):
        audio_chunks.append(indata.copy())

    with sd.InputStream(callback=_cb, channels=1, samplerate=sample_rate,
                        blocksize=block_size):
        count = 0
        while not _stop_evt.is_set() and not _interrupt_evt.is_set():
            time.sleep(block_ms / 1000)
            count += 1
            if count >= max_chunks:
                break
            if not audio_chunks:
                continue
            rms = float(np.sqrt(np.mean(audio_chunks[-1].flatten() ** 2)))
            if rms > SILENCE_RMS:
                has_speech    = True
                silence_count = 0
            elif has_speech:
                silence_count += 1
                if silence_count >= silence_limit:
                    break

    _interrupt_evt.clear()
    if not audio_chunks or not has_speech:
        return None
    import numpy as np
    return np.concatenate(audio_chunks, axis=0).flatten()


# ── Ollama streaming call ─────────────────────────────────────────────────────

def _call_ollama(history, system_prompt):
    """Stream Ollama response, updating the HUD with partial text."""
    import requests
    model    = get_ollama_model()
    messages = [{"role": "system", "content": system_prompt}] + history
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": 4096, "num_predict": 256},
    }
    parts = []
    r = requests.post(OLLAMA_URL, json=body, timeout=120, stream=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    for line in r.iter_lines(decode_unicode=True):
        if _stop_evt.is_set():
            break
        if line:
            data  = json.loads(line)
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                parts.append(chunk)
                _vc_set_state("thinking", "".join(parts)[-60:])
            if data.get("done"):
                break
    return "".join(parts).strip()


# ── Main chat loop ─────────────────────────────────────────────────────────────

def _voice_chat_loop():
    global _is_active
    history       = []
    system_prompt = config.get("voicechat_system_prompt", _VOICE_CHAT_SYSTEM)

    try:
        while not _stop_evt.is_set():

            # 1. Record
            audio = _record_with_vad()
            if audio is None:
                if not _stop_evt.is_set():
                    _vc_set_state("listening")
                continue

            # 2. STT
            _vc_set_state("thinking", "Распознаю речь…")
            try:
                model = _load_whisper_model()
                from utils.language import get_source_lang
                src          = get_source_lang()
                whisper_lang = None if src == "en" else src
                segments, info = model.transcribe(audio, language=whisper_lang, beam_size=5)
                text     = " ".join(seg.text for seg in segments).strip()
                detected = getattr(info, "language", src)
                if detected == "ru":
                    text = _fix_russian_spelling(text)
            except Exception as e:
                _vc_set_state("error", str(e)[:60])
                time.sleep(2)
                _vc_set_state("listening")
                continue

            if not text:
                _vc_set_state("listening")
                continue

            _vc_set_state("thinking", text[:60])

            # 3. LLM
            history.append({"role": "user", "content": text})
            try:
                response = _call_ollama(history, system_prompt)
            except Exception as e:
                _vc_set_state("error", str(e)[:60])
                history.pop()
                time.sleep(2)
                _vc_set_state("listening")
                continue

            if not response or _stop_evt.is_set():
                if not _stop_evt.is_set():
                    _vc_set_state("listening")
                continue

            history.append({"role": "assistant", "content": response})
            if len(history) > 20:
                history = history[-20:]

            # 4. TTS
            _vc_set_state("speaking", response[:60])
            _interrupt_evt.clear()

            from services.ai import tts as _tts
            _tts.speak(response, lang_code=detected if detected else src)

            # Wait for TTS to finish, interrupt, or stop
            time.sleep(0.15)
            while True:
                if _interrupt_evt.is_set() or _stop_evt.is_set():
                    _tts.stop()
                    _interrupt_evt.clear()
                    break
                if not _tts._speak_lock.locked():
                    break
                time.sleep(0.1)

            if not _stop_evt.is_set():
                _vc_set_state("listening")

    except Exception as e:
        import logging
        logging.getLogger("voice_chat").error("Loop error: %s", e)
    finally:
        _is_active = False
        h = _hud()
        if h:
            h.close()


# ── Public entry point ─────────────────────────────────────────────────────────

def on_hotkey_voicechat():
    """Toggle voice chat session."""
    if _is_active:
        _stop_evt.set()
        from services.ai import tts as _tts
        _tts.stop()
        return

    def _start():
        global _is_active
        _stop_evt.clear()
        _interrupt_evt.clear()
        _is_active = True
        h = _hud()
        if h is None:
            _is_active = False
            return
        h.open()
        threading.Thread(target=_voice_chat_loop, daemon=True).start()

    from services.ai.whisper import _check_prerequisites, _all_required_ok, _show_prereq_dialog
    checks = _check_prerequisites()
    if _all_required_ok(checks):
        _start()
    else:
        _show_prereq_dialog(checks, on_proceed=_start)
