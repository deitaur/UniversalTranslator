"""
Whisper transcription and spell checking.
A single status window near the cursor shows live progress and the final result.
"""

import ctypes
import ctypes.wintypes
import threading
import time
from pathlib import Path
from win32.clipboard import set_clipboard_text
import globals as g

_is_recording  = False
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
        "label": "Python-пакеты",
        "detail": ("OK" if not pkg_missing
                   else "Не установлены: " + ", ".join(pkg_missing)
                        + "\n  pip install " + " ".join(pkg_missing)),
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


# ── Pipeline window (progress + result near cursor) ────────────────────────────
#
# One small CTkFrame that:
#   • shows a blinking REC indicator while recording
#   • updates status text at each pipeline stage
#   • reveals the translated result inline
#   • auto-closes after 5 s once result is shown
#
_pipe_win = None   # CTk root, written from window thread, read from pipeline thread


def _cursor_pos():
    """Return current cursor (x, y) using Win32 — safe to call from any thread."""
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _open_pipe_window():
    """
    Open the status window near the cursor and store it in _pipe_win.
    Blocks until the window is ready (max 2 s).
    """
    global _pipe_win
    cx, cy = _cursor_pos()
    ready  = threading.Event()

    def _run():
        global _pipe_win
        import customtkinter as ctk

        ctk.set_appearance_mode("dark")
        win = ctk.CTk()
        _pipe_win = win
        ready.set()

        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(fg_color="#1e1e2e")

        # Position: right of cursor, above it
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        W = 310
        x = min(cx + 18, sw - W - 20)
        y = max(cy - 72, 40)
        win.geometry(f"{W}x72+{x}+{y}")
        win._base_x, win._base_y, win._base_w = x, y, W

        outer = ctk.CTkFrame(win, fg_color="#313244", corner_radius=10,
                              border_width=1, border_color="#45475a")
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Row 1: icon  |  status text  |  timer ──
        row1 = ctk.CTkFrame(outer, fg_color="transparent", height=38)
        row1.pack(fill="x", padx=10, pady=(7, 0))
        row1.pack_propagate(False)

        win._icon   = ctk.CTkLabel(row1, text="●", text_color="#f38ba8",
                                    font=("Segoe UI Bold", 15), width=18)
        win._icon.pack(side="left")

        win._status = ctk.CTkLabel(row1, text="Запись…  (клик — стоп)",
                                    text_color="#cdd6f4",
                                    font=("Segoe UI", 12), anchor="w")
        win._status.pack(side="left", padx=(7, 0), fill="x", expand=True)

        win._timer  = ctk.CTkLabel(row1, text="0s", text_color="#6c7086",
                                    font=("Segoe UI", 11))
        win._timer.pack(side="right")

        # ── Row 2: result text (hidden until translation is done) ──
        win._result = ctk.CTkLabel(outer, text="", text_color="#a6e3a1",
                                    font=("Segoe UI", 11), anchor="w",
                                    wraplength=W - 30, justify="left")
        # (not packed yet)

        # ── Blink while recording ──
        win._blink_on     = True
        win._blink_active = True

        def _blink():
            if not win._blink_active:
                return
            try:
                win._blink_on = not win._blink_on
                win._icon.configure(
                    text_color="#f38ba8" if win._blink_on else "#45475a")
                win.after(500, _blink)
            except Exception:
                pass
        win.after(500, _blink)

        # ── Elapsed timer while recording ──
        _t0 = [time.time()]
        win._timer_active = True

        def _tick():
            if not win._timer_active:
                return
            try:
                win._timer.configure(text=f"{int(time.time() - _t0[0])}s")
                win.after(1000, _tick)
            except Exception:
                pass
        win.after(1000, _tick)

        # ── Click anywhere on the window → stop recording ──
        def _stop(e=None):
            _stop_recording.set()

        for w in (win, outer, row1, win._icon, win._status, win._timer):
            w.bind("<Button-1>", _stop)

        win.bind("<Escape>", lambda e: _do_close())

        # ── Watchdog: destroy if pipeline clears _pipe_win ──
        def _watchdog():
            global _pipe_win
            if _pipe_win is None:
                try:
                    win.destroy()
                except Exception:
                    pass
                return
            try:
                win.after(200, _watchdog)
            except Exception:
                pass
        win.after(200, _watchdog)

        def _do_close():
            global _pipe_win
            _pipe_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win._do_close = _do_close
        win.mainloop()
        _pipe_win = None

    threading.Thread(target=_run, daemon=True).start()
    ready.wait(timeout=2.0)


def _pipe_set_status(text: str, icon: str = "◌", icon_color: str = "#89b4fa"):
    """Update status text from any thread."""
    win = _pipe_win
    if not win:
        return
    def _u():
        try:
            win._blink_active = False
            win._timer_active = False
            win._icon.configure(text=icon, text_color=icon_color)
            win._status.configure(text=text, text_color="#cdd6f4")
            win._timer.configure(text="")
        except Exception:
            pass
    try:
        win.after(0, _u)
    except Exception:
        pass


def _pipe_show_result(translated: str):
    """Show the final result inline and schedule auto-close."""
    win = _pipe_win
    if not win:
        return
    preview = translated[:130].rstrip() + ("…" if len(translated) > 130 else "")

    def _u():
        try:
            win._blink_active = False
            win._timer_active = False
            win._icon.configure(text="✓", text_color="#a6e3a1")
            win._status.configure(text="Скопировано в буфер", text_color="#a6e3a1")
            win._timer.configure(text="")
            win._result.configure(text=preview)
            win._result.pack(fill="x", padx=10, pady=(2, 8))
            win.update_idletasks()
            new_h = max(72, win.winfo_reqheight() + 4)
            win.geometry(f"{win._base_w}x{new_h}+{win._base_x}+{win._base_y}")
            win.after(5000, win._do_close)
        except Exception:
            pass
    try:
        win.after(0, _u)
    except Exception:
        pass


def _pipe_show_error(text: str):
    """Show error in the window and close after 4 s."""
    win = _pipe_win
    if not win:
        return
    def _u():
        try:
            win._blink_active = False
            win._timer_active = False
            win._icon.configure(text="✗", text_color="#f38ba8")
            win._status.configure(text=text[:80], text_color="#f38ba8")
            win._timer.configure(text="")
            win.after(4000, win._do_close)
        except Exception:
            pass
    try:
        win.after(0, _u)
    except Exception:
        pass


def _close_pipe_window():
    global _pipe_win
    win = _pipe_win
    _pipe_win = None
    if win:
        try:
            win.after(0, win._do_close)
        except Exception:
            pass


# ── Prereq dialog ──────────────────────────────────────────────────────────────

def _show_prereq_dialog(checks: dict, on_proceed):
    import customtkinter as ctk
    import subprocess

    C = {"bg": "#1e1e2e", "surface": "#313244", "card": "#181825",
         "text": "#cdd6f4", "muted": "#6c7086", "accent": "#89b4fa",
         "green": "#a6e3a1", "yellow": "#f9e2af", "red": "#f38ba8"}

    def _run():
        ctk.set_appearance_mode("dark")
        win = ctk.CTk()
        win.title("Whisper — проверка зависимостей")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(fg_color=C["bg"])
        cx, cy = _cursor_pos()
        win.geometry(f"+{max(cx - 200, 20)}+{max(cy - 160, 20)}")

        hdr = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🎙  Whisper — проверка перед запуском",
                     font=("Segoe UI Semibold", 13), text_color=C["text"]
                     ).pack(side="left", padx=14, pady=10)

        body = ctk.CTkFrame(win, fg_color=C["card"], corner_radius=0)
        body.pack(fill="both")

        pkg_missing = []
        keys = list(checks.keys())
        for i, (key, c) in enumerate(checks.items()):
            ok, optional = c["ok"], c.get("optional", False)
            if ok is True:
                icon, color = "✓", C["green"]
            elif ok is False and optional:
                icon, color = "⚠", C["yellow"]
            elif ok is False:
                icon, color = "✗", C["red"]
            else:
                icon, color = "·", C["muted"]

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(8 if i == 0 else 2, 2))
            ctk.CTkLabel(row, text=icon, font=("Segoe UI Bold", 15),
                         text_color=color, width=20).pack(side="left")
            ctk.CTkLabel(row, text=c["label"], font=("Segoe UI Semibold", 12),
                         text_color=C["text"], width=150, anchor="w"
                         ).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row, text=c["detail"], font=("Segoe UI", 11),
                         text_color=C["muted"] if ok else color,
                         anchor="w", wraplength=280, justify="left"
                         ).pack(side="left", padx=(8, 0))

            if key == "packages" and ok is False:
                for part in c["detail"].split("\n"):
                    if "pip install" in part:
                        pkg_missing.extend(part.strip().replace("pip install ", "").split())

        ctk.CTkFrame(win, fg_color=C["surface"], height=1).pack(fill="x", pady=(10, 0))

        footer = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=52)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        bf = ctk.CTkFrame(footer, fg_color="transparent")
        bf.pack(side="right", padx=12, pady=10)

        ctk.CTkButton(bf, text="Отмена", width=80, height=32,
                      font=("Segoe UI", 12), fg_color=C["surface"],
                      text_color=C["muted"], hover_color=C["card"],
                      command=win.destroy).pack(side="left", padx=(0, 6))

        if pkg_missing:
            def _install():
                try:
                    subprocess.Popen(
                        ["cmd", "/k", "pip", "install"] + pkg_missing,
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                except Exception as e:
                    from ui.notifications import show_toast
                    show_toast(f"Ошибка: {e}")

            ctk.CTkButton(bf, text="Установить пакеты", width=150, height=32,
                          font=("Segoe UI Semibold", 12), fg_color=C["surface"],
                          text_color=C["yellow"], hover_color=C["card"],
                          command=_install).pack(side="left", padx=(0, 6))

        ready = _all_required_ok(checks)

        def _proceed():
            win.destroy()
            on_proceed()

        ctk.CTkButton(bf,
                      text="Начать запись" if ready else "Начать всё равно",
                      width=140, height=32,
                      font=("Segoe UI Semibold", 12),
                      fg_color=C["accent"] if ready else C["yellow"],
                      text_color=C["bg"],
                      hover_color="#7ba4e8" if ready else "#e8d59f",
                      command=_proceed).pack(side="left")

        win.bind("<Escape>", lambda e: win.destroy())
        win.mainloop()

    threading.Thread(target=_run, daemon=True).start()


# ── Model loading ──────────────────────────────────────────────────────────────

def _load_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(WHISPER_MODEL_ID, device="cpu", compute_type="int8")
    return _whisper_model


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


# ── Click-hook (stop on any mouse click) ──────────────────────────────────────

def _setup_click_hook():
    WH_MOUSE_LL    = 14
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204

    HOOKPROC = ctypes.CFUNCTYPE(
        ctypes.c_long, ctypes.c_int,
        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    )
    user32 = ctypes.windll.user32

    def _cb(nCode, wParam, lParam):
        if nCode >= 0 and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            _stop_recording.set()
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    ref  = HOOKPROC(_cb)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ref, None, 0)
    msg  = ctypes.wintypes.MSG()
    while not _stop_recording.is_set():
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    user32.UnhookWindowsHookEx(hook)
    del ref


# ── Main recording pipeline ────────────────────────────────────────────────────

def _start_recording():
    global _is_recording
    _is_recording = True
    _stop_recording.clear()

    # Open the status window next to the cursor
    _open_pipe_window()

    try:
        import sounddevice as sd
        import numpy as np

        sample_rate  = 16000
        duration_max = 120
        audio_data   = []

        def _audio_cb(indata, frames, t, status):
            audio_data.append(indata.copy())

        threading.Thread(target=_setup_click_hook, daemon=True).start()

        with sd.InputStream(callback=_audio_cb, channels=1,
                            samplerate=sample_rate, blocksize=1024):
            t0 = time.time()
            while not _stop_recording.is_set():
                if (time.time() - t0) >= duration_max:
                    break
                time.sleep(0.05)

        if not audio_data:
            _pipe_show_error("Нет аудио — ничего не записано")
            return

        audio = np.concatenate(audio_data, axis=0).flatten()

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
        _stop_recording.clear()


# ── Public entry point ─────────────────────────────────────────────────────────

def on_tray_whisper():
    """Toggle voice recording. Shows prereq dialog if something is missing."""
    global _is_recording

    if _is_recording:
        _stop_recording.set()
        return

    checks = _check_prerequisites()

    if _all_required_ok(checks):
        threading.Thread(target=_start_recording, daemon=True).start()
    else:
        _show_prereq_dialog(
            checks,
            on_proceed=lambda: threading.Thread(target=_start_recording, daemon=True).start(),
        )
