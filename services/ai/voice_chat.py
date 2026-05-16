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
MAX_SEC = 45

_VOICE_CHAT_SYSTEM = (
    "You are a helpful voice assistant. Keep responses short and conversational — "
    "2–3 sentences maximum. No markdown, bullet points, or code blocks. "
    "Speak naturally as in a real voice conversation."
)

_is_active     = False
_stop_evt      = threading.Event()
_interrupt_evt = threading.Event()
_vc_win        = None


# ── Window ────────────────────────────────────────────────────────────────────

def _open_vc_window():
    """Open the floating voice chat panel in the top-right corner. Blocks until ready."""
    global _vc_win
    ready = threading.Event()

    def _run():
        global _vc_win
        import customtkinter as ctk
        ctk.set_appearance_mode("dark")
        win = ctk.CTk()
        _vc_win = win
        ready.set()

        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(fg_color="#1e1e2e")

        W, H = 320, 78
        x = win.winfo_screenwidth() - W - 24
        y = 60
        win.geometry(f"{W}x{H}+{x}+{y}")

        outer = ctk.CTkFrame(win, fg_color="#313244", corner_radius=10,
                              border_width=1, border_color="#45475a")
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 0))

        win._icon = ctk.CTkLabel(hdr, text="🎙", font=("Segoe UI", 16), width=22)
        win._icon.pack(side="left")

        win._state = ctk.CTkLabel(hdr, text="Слушаю…", text_color="#a6e3a1",
                                   font=("Segoe UI", 12), anchor="w")
        win._state.pack(side="left", padx=(6, 0), fill="x", expand=True)

        def _do_close():
            global _vc_win
            _stop_evt.set()
            _vc_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win._do_close = _do_close

        ctk.CTkButton(hdr, text="✕", width=22, height=22,
                       font=("Segoe UI", 11), fg_color="transparent",
                       text_color="#6c7086", hover_color="#45475a",
                       corner_radius=4, command=_do_close).pack(side="right")

        win._sub = ctk.CTkLabel(outer, text="", text_color="#6c7086",
                                 font=("Segoe UI", 10), anchor="w",
                                 wraplength=W - 24, justify="left")
        win._sub.pack(fill="x", padx=12, pady=(2, 8))

        # Click anywhere on window interrupts TTS so user can speak sooner
        def _on_click(e=None):
            _interrupt_evt.set()

        for w in (win, outer, hdr, win._icon, win._state, win._sub):
            w.bind("<Button-1>", _on_click)
        win.bind("<Escape>", lambda e: _do_close())

        win.mainloop()
        _vc_win = None

    threading.Thread(target=_run, daemon=True).start()
    ready.wait(timeout=2.0)


def _vc_set_state(state: str, sub: str = ""):
    """Update window from any thread."""
    win = _vc_win
    if not win:
        return
    _ICONS  = {"listening": "🎙", "thinking": "◌", "speaking": "🔊", "error": "✕"}
    _COLORS = {"listening": "#a6e3a1", "thinking": "#89b4fa", "speaking": "#fab387", "error": "#f38ba8"}
    _LABELS = {"listening": "Слушаю…", "thinking": "Думаю…", "speaking": "Говорю…", "error": "Ошибка"}
    icon  = _ICONS.get(state, "◦")
    color = _COLORS.get(state, "#cdd6f4")
    label = _LABELS.get(state, state)

    def _u():
        try:
            win._icon.configure(text=icon)
            win._state.configure(text=label, text_color=color)
            win._sub.configure(text=(sub[:80] if sub else ""))
        except Exception:
            pass

    try:
        win.after(0, _u)
    except Exception:
        pass


# ── VAD recording ─────────────────────────────────────────────────────────────

def _record_with_vad():
    """Record until silence-after-speech or stop event. Returns np.ndarray or None."""
    import numpy as np
    import sounddevice as sd

    sample_rate    = 16000
    block_ms       = 50
    block_size     = int(sample_rate * block_ms / 1000)
    audio_chunks   = []
    silence_count  = 0
    silence_limit  = int(SILENCE_SEC * 1000 / block_ms)
    max_chunks     = int(MAX_SEC * 1000 / block_ms)
    has_speech     = False

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
                has_speech = True
                silence_count = 0
            elif has_speech:
                silence_count += 1
                if silence_count >= silence_limit:
                    break  # silence after speech → end of utterance

    _interrupt_evt.clear()  # reset in case user clicked to interrupt TTS early
    if not audio_chunks or not has_speech:
        return None
    return np.concatenate(audio_chunks, axis=0).flatten()


# ── Ollama call ───────────────────────────────────────────────────────────────

def _call_ollama(history, system_prompt):
    """Streaming Ollama call. Updates window with partial response. Respects _stop_evt."""
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

            # ── 1. Record ──
            audio = _record_with_vad()
            if audio is None:
                if not _stop_evt.is_set():
                    _vc_set_state("listening")
                continue

            # ── 2. STT ──
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

            # ── 3. LLM ──
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
                history = history[-20:]  # keep last 10 exchanges

            # ── 4. TTS ──
            _vc_set_state("speaking", response[:60])
            _interrupt_evt.clear()

            from services.ai import tts as _tts
            speak_lang = detected if detected else src
            _tts.speak(response, lang_code=speak_lang)

            # Wait for TTS to finish, interrupt signal, or stop
            time.sleep(0.15)  # let TTS thread acquire the lock
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
        win = _vc_win
        if win:
            try:
                win.after(0, win._do_close)
            except Exception:
                pass


# ── Public entry point ─────────────────────────────────────────────────────────

def on_hotkey_voicechat():
    """Toggle voice chat session."""
    global _is_active

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
        _open_vc_window()
        threading.Thread(target=_voice_chat_loop, daemon=True).start()

    from services.ai.whisper import _check_prerequisites, _all_required_ok, _show_prereq_dialog
    checks = _check_prerequisites()
    if _all_required_ok(checks):
        _start()
    else:
        _show_prereq_dialog(checks, on_proceed=_start)
