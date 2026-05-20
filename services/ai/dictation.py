"""
Voice dictation → save to .txt / .md (Obsidian-ready).
Hotkey: Ctrl+Alt+D  (configurable in Settings)
Reuses the Whisper model cache and status-window from whisper.py.
"""

import datetime
import threading
from pathlib import Path

from config import config
from services.ai.whisper import (
    _open_pipe_window, _pipe_set_status, _pipe_show_error,
    _load_whisper_model, _fix_russian_spelling,
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
    """Show save-confirmation in the HUD overlay."""
    from ui.hud import get_pipe_hud
    hud = get_pipe_hud()
    if hud is None:
        return
    preview = text[:120].rstrip() + ("…" if len(text) > 120 else "")
    hud.show_saved(str(filepath), filepath.name, preview)


# ── Main recording pipeline ───────────────────────────────────────────────────

def _start_dictation():
    global _is_dictating
    from services.ai.recorder import AudioSession, start_click_hook

    session = AudioSession(max_seconds=300)   # max 5 min for dictation
    try:
        session.__enter__()
    except RuntimeError:
        _pipe_show_error("Другой модуль уже записывает звук")
        return

    _is_dictating = True
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
        session.__exit__(None, None, None)


# ── Public entry point ────────────────────────────────────────────────────────

def on_hotkey_dictation():
    """Toggle dictation recording."""
    from services.ai.recorder import is_recording, stop_active
    if is_recording():
        stop_active()
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
