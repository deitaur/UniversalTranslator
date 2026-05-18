"""
Whisper transcription and spell checking.
Status is shown in a Qt HUD overlay (ui.hud.PipeHud).
"""

import ctypes
import ctypes.wintypes
import threading
import time
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
        hud = init_pipe_hud(_stop_recording)
    return hud


def _open_pipe_window():
    """Open the recording status HUD near the cursor."""
    cx, cy = _cursor_pos()
    _get_hud().open(cx, cy)


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
    from ui.hud import get_pipe_hud, init_pipe_hud
    hud = get_pipe_hud()
    if hud is None:
        hud = init_pipe_hud(_stop_recording)
    hud.show_prereq(checks, on_proceed=on_proceed)


def _show_prereq_dialog_legacy(checks: dict, on_proceed):
    """Legacy modal dialog — kept for reference but no longer used."""
    import subprocess
    from PySide6.QtCore import QObject, Qt, Signal, Slot
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    )

    _C = {"bg": "#1e1e2e", "surface": "#313244", "card": "#181825",
          "text": "#cdd6f4", "muted": "#6c7086", "accent": "#89b4fa",
          "green": "#a6e3a1", "yellow": "#f9e2af", "red": "#f38ba8"}

    class _Launcher(QObject):
        _sig = Signal()
        def __init__(self):
            super().__init__()
            self._sig.connect(self._run)
        def launch(self):
            self._sig.emit()
        @Slot()
        def _run(self):
            pkg_missing = []
            for key, c in checks.items():
                if key == "packages" and c["ok"] is False:
                    for part in c["detail"].split("\n"):
                        if "pip install" in part:
                            pkg_missing.extend(part.strip().replace("pip install ", "").split())

            dlg = QDialog()
            dlg.setWindowTitle("Whisper — проверка зависимостей")
            dlg.setWindowFlags(
                dlg.windowFlags() |
                Qt.WindowType.WindowStaysOnTopHint
            )
            dlg.setFixedWidth(560)
            dlg.setStyleSheet(f"background: {_C['bg']}; color: {_C['text']};")

            root = QVBoxLayout(dlg)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            # Header
            hdr = QFrame()
            hdr.setFixedHeight(44)
            hdr.setStyleSheet(f"background: {_C['surface']}; border: none;")
            hdr_lo = QHBoxLayout(hdr)
            hdr_lo.setContentsMargins(14, 0, 14, 0)
            lbl = QLabel("🎙  Whisper — проверка перед запуском")
            lbl.setFont(QFont("Segoe UI Semibold", 12))
            lbl.setStyleSheet(f"color: {_C['text']}; background: transparent;")
            hdr_lo.addWidget(lbl)
            root.addWidget(hdr)

            # Body — check rows
            body = QFrame()
            body.setStyleSheet(f"background: {_C['card']}; border: none;")
            body_lo = QVBoxLayout(body)
            body_lo.setContentsMargins(14, 8, 14, 8)
            body_lo.setSpacing(4)

            for key, c in checks.items():
                ok, optional = c["ok"], c.get("optional", False)
                if ok is True:
                    icon, color = "✓", _C["green"]
                elif ok is False and optional:
                    icon, color = "⚠", _C["yellow"]
                elif ok is False:
                    icon, color = "✗", _C["red"]
                else:
                    icon, color = "·", _C["muted"]

                row = QHBoxLayout()
                row.setSpacing(6)

                ico = QLabel(icon)
                ico.setFont(QFont("Segoe UI Bold", 13))
                ico.setStyleSheet(f"color: {color}; background: transparent;")
                ico.setFixedWidth(18)
                row.addWidget(ico)

                name = QLabel(c["label"])
                name.setFont(QFont("Segoe UI Semibold", 11))
                name.setStyleSheet(f"color: {_C['text']}; background: transparent;")
                name.setFixedWidth(160)
                row.addWidget(name)

                detail_color = _C["muted"] if ok else color
                detail = QLabel(c["detail"])
                detail.setFont(QFont("Segoe UI", 10))
                detail.setStyleSheet(f"color: {detail_color}; background: transparent;")
                detail.setWordWrap(True)
                row.addWidget(detail, 1)

                body_lo.addLayout(row)

            root.addWidget(body)

            # Separator
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background: {_C['surface']};")
            root.addWidget(sep)

            # Footer
            footer = QFrame()
            footer.setFixedHeight(52)
            footer.setStyleSheet(f"background: {_C['surface']}; border: none;")
            foot_lo = QHBoxLayout(footer)
            foot_lo.setContentsMargins(12, 10, 12, 10)
            foot_lo.addStretch()

            _btn = "border-radius: 6px; padding: 3px 12px; font-family: 'Segoe UI'; font-size: 11px;"

            cancel = QPushButton("Отмена")
            cancel.setFixedHeight(32)
            cancel.setStyleSheet(
                f"QPushButton {{ {_btn} background: {_C['surface']}; color: {_C['muted']}; border: 1px solid {_C['card']}; }}"
                f"QPushButton:hover {{ background: {_C['card']}; }}"
            )
            cancel.clicked.connect(dlg.reject)
            foot_lo.addWidget(cancel)

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

                install_btn = QPushButton("Установить пакеты")
                install_btn.setFixedHeight(32)
                install_btn.setStyleSheet(
                    f"QPushButton {{ {_btn} background: {_C['surface']}; color: {_C['yellow']}; border: 1px solid {_C['card']}; }}"
                    f"QPushButton:hover {{ background: {_C['card']}; }}"
                )
                install_btn.clicked.connect(_install)
                foot_lo.addWidget(install_btn)

            ready = _all_required_ok(checks)
            proceed_text = "Начать запись" if ready else "Начать всё равно"
            proceed_color = _C["accent"] if ready else _C["yellow"]
            proceed_hover = "#7ba4e8" if ready else "#e8d59f"

            def _do_proceed():
                dlg.accept()
                on_proceed()

            proceed_btn = QPushButton(proceed_text)
            proceed_btn.setFixedHeight(32)
            proceed_btn.setStyleSheet(
                f"QPushButton {{ {_btn} background: {proceed_color}; color: {_C['bg']}; border: none; }}"
                f"QPushButton:hover {{ background: {proceed_hover}; }}"
            )
            proceed_btn.clicked.connect(_do_proceed)
            foot_lo.addWidget(proceed_btn)

            root.addWidget(footer)

            cx, cy = _cursor_pos()
            dlg.adjustSize()
            dlg.move(max(cx - 200, 20), max(cy - 160, 20))
            dlg.exec()

    launcher = _Launcher()
    launcher.launch()


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
        _show_prereq_dialog(checks,
            on_proceed=lambda: threading.Thread(target=_start_recording, daemon=True).start())
