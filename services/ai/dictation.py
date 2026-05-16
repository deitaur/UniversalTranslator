"""
Voice dictation → save to .txt / .md (Obsidian-ready).
Hotkey: Ctrl+Alt+D  (configurable in Settings)
Reuses the Whisper model cache and status-window from whisper.py.
"""

import datetime
import os
import threading
import time
from pathlib import Path

from config import config
# Share model cache, status window, click-hook, and stop event with whisper module
from services.ai.whisper import (
    _open_pipe_window, _pipe_set_status, _pipe_show_error,
    _load_whisper_model, _fix_russian_spelling,
    _setup_click_hook, _stop_recording,
)

_is_dictating = False

# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_folder() -> Path:
    folder = config.get("dictation_folder", "")
    if folder:
        p = Path(folder)
    else:
        p = Path.home() / "Documents" / "Dictations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_filename(ext: str) -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S") + "." + ext


def _build_content(text: str) -> str:
    fmt = config.get("dictation_format", "md")
    if fmt != "md":
        return text

    use_obsidian = config.get("dictation_obsidian", True)
    if not use_obsidian:
        return text

    now = datetime.datetime.now().isoformat(timespec="seconds")
    raw_tags = config.get("dictation_tags", "dictation").strip()
    tags = [t.strip() for t in raw_tags.replace(",", "\n").splitlines() if t.strip()]
    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  - dictation"

    frontmatter = f"---\ndate: {now}\ntags:\n{tag_lines}\n---\n\n"
    return frontmatter + text


def _show_saved_popup(filepath: Path, text: str):
    """Small result window near cursor: filename + preview + Open buttons."""
    import customtkinter as ctk
    from services.ai.whisper import _pipe_win as _pw

    # Re-read module var — may have changed since import
    import services.ai.whisper as _wmod
    win = _wmod._pipe_win
    if win is None:
        return

    preview = text[:120].rstrip() + ("…" if len(text) > 120 else "")

    def _u():
        try:
            win._blink_active = False
            win._timer_active = False
            win._icon.configure(text="✓", text_color="#a6e3a1")
            win._status.configure(text=f"Сохранено: {filepath.name}", text_color="#a6e3a1")
            win._timer.configure(text="")

            win._result.configure(text=preview)
            win._result.pack(fill="x", padx=10, pady=(2, 4))

            # Open-file button
            def _open_file():
                try:
                    os.startfile(str(filepath))
                except Exception:
                    pass

            def _open_folder():
                try:
                    os.startfile(str(filepath.parent))
                except Exception:
                    pass

            btn_frame = ctk.CTkFrame(win._result.master, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))

            ctk.CTkButton(btn_frame, text="Открыть файл", width=110, height=24,
                          font=("Segoe UI", 10), fg_color="#313244",
                          text_color="#89b4fa", hover_color="#45475a",
                          corner_radius=6, command=_open_file
                          ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(btn_frame, text="Открыть папку", width=110, height=24,
                          font=("Segoe UI", 10), fg_color="#313244",
                          text_color="#6c7086", hover_color="#45475a",
                          corner_radius=6, command=_open_folder
                          ).pack(side="left")

            win.update_idletasks()
            new_h = max(72, win.winfo_reqheight() + 4)
            win.geometry(f"{win._base_w}x{new_h}+{win._base_x}+{win._base_y}")
            win.after(2500, win._do_close)
        except Exception:
            pass

    try:
        win.after(0, _u)
    except Exception:
        pass


# ── Main recording pipeline ───────────────────────────────────────────────────

def _start_dictation():
    global _is_dictating
    _is_dictating = True
    _stop_recording.clear()

    _open_pipe_window()

    try:
        import sounddevice as sd
        import numpy as np

        sample_rate  = 16000
        audio_data   = []

        def _audio_cb(indata, frames, t, status):
            audio_data.append(indata.copy())

        threading.Thread(target=_setup_click_hook, daemon=True).start()

        with sd.InputStream(callback=_audio_cb, channels=1,
                            samplerate=sample_rate, blocksize=1024):
            t0 = time.time()
            while not _stop_recording.is_set():
                if (time.time() - t0) >= 300:   # max 5 min for dictation
                    break
                time.sleep(0.05)

        if not audio_data:
            _pipe_show_error("Нет аудио — ничего не записано")
            return

        audio = np.concatenate(audio_data, axis=0).flatten()

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

        if not transcription:
            _pipe_show_error("Речь не обнаружена")
            return

        # ── Stage 2: spell check ──
        if detected_lang == "ru":
            _pipe_set_status("Проверка орфографии…")
            transcription = _fix_russian_spelling(transcription)

        # ── Stage 3: save ──
        _pipe_set_status("Сохранение…")
        try:
            fmt      = config.get("dictation_format", "md")
            folder   = _save_folder()
            filename = _make_filename(fmt)
            filepath = folder / filename
            content  = _build_content(transcription)
            filepath.write_text(content, encoding="utf-8")
        except Exception as e:
            _pipe_show_error(f"Ошибка сохранения: {str(e)[:55]}")
            return

        _show_saved_popup(filepath, transcription)

    except Exception as e:
        _pipe_show_error(f"Dictation error: {str(e)[:60]}")
    finally:
        _is_dictating = False
        _stop_recording.clear()


# ── Public entry point ────────────────────────────────────────────────────────

def on_hotkey_dictation():
    """Toggle dictation recording."""
    global _is_dictating
    if _is_dictating:
        _stop_recording.set()
        return

    from services.ai.whisper import _check_prerequisites, _all_required_ok, _show_prereq_dialog
    checks = _check_prerequisites()

    if _all_required_ok(checks):
        threading.Thread(target=_start_dictation, daemon=True).start()
    else:
        _show_prereq_dialog(
            checks,
            on_proceed=lambda: threading.Thread(target=_start_dictation, daemon=True).start(),
        )
