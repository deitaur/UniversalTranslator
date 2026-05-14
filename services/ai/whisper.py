"""
Whisper transcription and spell checking.
Shows visual recording indicator near cursor.
Click anywhere or press hotkey again to stop recording.
"""

import threading
import time
from win32.clipboard import set_clipboard_text
import globals as g

_whisper_model = None
_spell_model = None
_spell_tokenizer = None
_is_recording = False
_stop_recording = threading.Event()
_rec_indicator = None


def _ensure_whisper_deps():
    try:
        import sounddevice
        import numpy as np
        import faster_whisper
        return True
    except ImportError:
        return False


def _load_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            "deepdml/faster-whisper-large-v3-turbo-ct2",
            device="cpu", compute_type="int8"
        )
    return _whisper_model


def _load_spell_model():
    global _spell_model, _spell_tokenizer
    if _spell_model is None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        _model_name = "ai-forever/sage-fredt5-distilled-95m"
        _spell_tokenizer = AutoTokenizer.from_pretrained(_model_name)
        _spell_model = AutoModelForSeq2SeqLM.from_pretrained(_model_name)
    return _spell_model, _spell_tokenizer


def _fix_russian_spelling(text):
    if not text.strip():
        return text
    try:
        model, tokenizer = _load_spell_model()
        inputs = tokenizer(text, max_length=None, padding="longest",
                           truncation=False, return_tensors="pt")
        max_len = int(inputs["input_ids"].size(1) * 1.5)
        outputs = model.generate(**inputs, max_length=max_len)
        corrected = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return corrected if corrected.strip() else text
    except Exception:
        return text


def _show_recording_indicator():
    """Show a floating 'Recording...' label near cursor that blinks."""
    global _rec_indicator
    import customtkinter as ctk

    def _run():
        global _rec_indicator
        root = ctk.CTk()
        _rec_indicator = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.92)
        root.configure(fg_color="#1e1e2e")

        try:
            cx, cy = root.winfo_pointerx(), root.winfo_pointery()
            root.geometry("+" + str(cx + 20) + "+" + str(cy - 50))
        except Exception:
            root.geometry("+100+100")

        frame = ctk.CTkFrame(root, fg_color="#313244", corner_radius=12,
                              border_width=2, border_color="#f38ba8")
        frame.pack(padx=2, pady=2)

        dot_label = ctk.CTkLabel(frame, text="  REC  ", text_color="#f38ba8",
                                  font=("Segoe UI Bold", 14), padx=6, pady=4)
        dot_label.pack(side="left")

        time_label = ctk.CTkLabel(frame, text="0s", text_color="#cdd6f4",
                                   font=("Segoe UI", 13), padx=8, pady=4)
        time_label.pack(side="left")

        hint_label = ctk.CTkLabel(frame, text="click to stop", text_color="#6c7086",
                                   font=("Segoe UI", 10), padx=8, pady=4)
        hint_label.pack(side="left")

        start_time = time.time()
        blink_state = [True]

        def update_timer():
            if _rec_indicator is None:
                return
            try:
                elapsed = int(time.time() - start_time)
                time_label.configure(text=str(elapsed) + "s")
                # Blink the REC dot
                blink_state[0] = not blink_state[0]
                if blink_state[0]:
                    dot_label.configure(text_color="#f38ba8")
                else:
                    dot_label.configure(text_color="#45475a")
                root.after(500, update_timer)
            except Exception:
                pass

        def on_click(event):
            _stop_recording.set()

        # Bind click on the indicator itself to stop
        root.bind("<Button-1>", on_click)
        frame.bind("<Button-1>", on_click)
        dot_label.bind("<Button-1>", on_click)
        time_label.bind("<Button-1>", on_click)
        hint_label.bind("<Button-1>", on_click)

        root.after(500, update_timer)

        # Poll for stop signal
        def check_stop():
            if _stop_recording.is_set() or _rec_indicator is None:
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            root.after(100, check_stop)

        root.after(100, check_stop)
        root.mainloop()

    threading.Thread(target=_run, daemon=True).start()


def _hide_recording_indicator():
    global _rec_indicator
    if _rec_indicator is not None:
        try:
            _rec_indicator.after(0, _rec_indicator.destroy)
        except Exception:
            pass
        _rec_indicator = None


def _setup_click_hook():
    """Set up a global mouse hook to detect clicks anywhere to stop recording."""
    import ctypes
    import ctypes.wintypes

    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204

    HOOKPROC = ctypes.CFUNCTYPE(
        ctypes.c_long,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM
    )

    user32 = ctypes.windll.user32

    def mouse_callback(nCode, wParam, lParam):
        if nCode >= 0 and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            _stop_recording.set()
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    # Must keep reference alive
    callback_ref = HOOKPROC(mouse_callback)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, callback_ref, None, 0)

    # Pump messages until recording stops
    msg = ctypes.wintypes.MSG()
    while not _stop_recording.is_set():
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    user32.UnhookWindowsHookEx(hook)
    # prevent GC of callback while hook is alive
    del callback_ref


def on_tray_whisper():
    """Toggle voice recording and translation."""
    global _is_recording

    # If already recording, stop it
    if _is_recording:
        _stop_recording.set()
        return

    if not _ensure_whisper_deps():
        from ui.notifications import show_toast
        show_toast("Install AI: pip install faster-whisper sounddevice numpy")
        return

    def _whisper_record_and_translate():
        global _is_recording
        _is_recording = True
        _stop_recording.clear()

        try:
            import sounddevice as sd
            import numpy as np

            sample_rate = 16000
            duration_max = 120
            audio_data = []

            def callback(indata, frames, time_info, status):
                audio_data.append(indata.copy())

            # Show recording indicator
            _show_recording_indicator()

            # Start mouse click hook in separate thread
            hook_thread = threading.Thread(target=_setup_click_hook, daemon=True)
            hook_thread.start()

            # Record until stopped
            with sd.InputStream(callback=callback, channels=1,
                                samplerate=sample_rate, blocksize=1024):
                start_time = time.time()
                while not _stop_recording.is_set():
                    if (time.time() - start_time) >= duration_max:
                        break
                    time.sleep(0.05)

            # Hide indicator
            _hide_recording_indicator()

            if not audio_data:
                from ui.notifications import show_toast
                show_toast("No audio recorded")
                return

            audio = np.concatenate(audio_data, axis=0).flatten()

            # Show processing toast
            from ui.notifications import show_toast
            show_toast("Recognizing...", 5000)

            # Determine transcription language: use source_lang unless it's "en"
            from utils.language import get_source_lang
            src_lang = get_source_lang()
            # Auto-detect if source language is English (user likely speaks
            # their native language, not English, into the mic)
            whisper_lang = None if src_lang == "en" else src_lang
            show_toast(f"Recognizing ({src_lang})...", 3000)

            # Transcribe
            model = _load_whisper_model()
            segments, info = model.transcribe(
                audio, language=whisper_lang, beam_size=5
            )
            detected_lang = getattr(info, "language", src_lang)
            transcription = " ".join([seg.text for seg in segments]).strip()

            if not transcription:
                show_toast("No speech detected")
                return

            # Spell check (only for Russian text)
            if detected_lang == "ru":
                corrected = _fix_russian_spelling(transcription)
            else:
                corrected = transcription

            # Translate
            from services.translators.deepl import DeepLEngine
            from services.translators.google import GoogleEngine
            from services.translators.yandex import YandexEngine
            if g.current_engine == "deepl":
                engine = DeepLEngine()
            elif g.current_engine == "google":
                engine = GoogleEngine()
            else:
                engine = YandexEngine()
            translated = engine.translate(corrected)

            # To clipboard
            set_clipboard_text(translated)
            preview = " ".join(translated.split()[:3])
            if len(translated.split()) > 3:
                preview += "..."
            show_toast(preview, 3000)

        except Exception as e:
            _hide_recording_indicator()
            from ui.notifications import show_toast
            show_toast("Whisper error: " + str(e)[:50])
        finally:
            _is_recording = False
            _stop_recording.clear()

    threading.Thread(target=_whisper_record_and_translate, daemon=True).start()
