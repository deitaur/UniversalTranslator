"""
Popup review window for translations
"""

import threading
import customtkinter as ctk
from config import APP_NAME, ICON_FILE, C
from utils.language import LANGUAGES, get_source_lang, get_target_lang

# Global popup references
_popup_win = None          # reusable popup window reference
_popup_autoclose_id = None # after() id for auto-close timer

def _close_popup():
    global _popup_win, _popup_autoclose_id
    if _popup_win is not None:
        try:
            _popup_win.destroy()
        except Exception:
            pass
    _popup_win = None
    _popup_autoclose_id = None

def show_translation_popup(original, translated, current_engine, target_lang=None):
    global _popup_win, _popup_autoclose_id

    # If a popup already exists try to reuse it
    if _popup_win is not None:
        try:
            _popup_win.winfo_exists()  # raises if destroyed
            _update_popup(_popup_win, original, translated, current_engine, target_lang)
            _popup_win.deiconify()
            _popup_win.lift()
            _popup_win.focus_force()
            _reset_autoclose(_popup_win)
            return
        except Exception:
            _popup_win = None

    # Create new popup on a background thread (tkinter main loop)
    def _run():
        global _popup_win, _popup_autoclose_id
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        win = ctk.CTk()
        _popup_win = win
        win.title(APP_NAME)
        win.geometry("620x520")
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.configure(fg_color=C["bg"])

        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        # Header
        header = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        engine_name = _engine_display_name(current_engine)
        engine_colors = {"deepl": C["accent"], "google": C["green"], "yandex": C["yellow"]}
        engine_color = engine_colors.get(current_engine, C["accent"])

        ctk.CTkLabel(header, text=APP_NAME, font=("Segoe UI Semibold", 16),
                     text_color=C["text"]).pack(side="left", padx=16)

        win._badge_frame = ctk.CTkFrame(header, fg_color=engine_color, corner_radius=8)
        win._badge_frame.pack(side="right", padx=16, pady=12)
        win._badge_label = ctk.CTkLabel(win._badge_frame, text=engine_name,
                                         font=("Segoe UI Semibold", 11),
                                         text_color=C["bg"], padx=10, pady=2)
        win._badge_label.pack()

        # Content
        content = ctk.CTkFrame(win, fg_color=C["bg"], corner_radius=0)
        content.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        _src_label = LANGUAGES.get(get_source_lang(), get_source_lang()).upper()
        _tgt_code  = target_lang or get_target_lang()
        _tgt_label = LANGUAGES.get(_tgt_code, _tgt_code).upper()
        win._orig_label = ctk.CTkLabel(content, text=f"ORIGINAL  ({_src_label})",
                                        font=("Segoe UI Semibold", 11),
                                        text_color=C["muted"], anchor="w")
        win._orig_label.pack(fill="x", pady=(0, 6))
        win._orig_box = ctk.CTkTextbox(content, height=120, font=("Segoe UI", 13),
                                        fg_color=C["card"], text_color=C["text"],
                                        border_width=1, border_color=C["border"],
                                        corner_radius=10, wrap="word")
        win._orig_box.pack(fill="both", expand=True, pady=(0, 12))
        win._orig_box.insert("1.0", original)
        win._orig_box.configure(state="disabled")

        ctk.CTkLabel(content, text="   >", font=("Segoe UI", 16),
                     text_color=C["accent"]).pack(pady=2)

        win._trans_label = ctk.CTkLabel(content, text=f"TRANSLATION  ({_tgt_label})",
                                         font=("Segoe UI Semibold", 11),
                                         text_color=C["muted"], anchor="w")
        win._trans_label.pack(fill="x", pady=(4, 6))
        win._trans_box = ctk.CTkTextbox(content, height=120, font=("Segoe UI", 13),
                                         fg_color=C["card"], text_color=C["green"],
                                         border_width=1, border_color=C["border"],
                                         corner_radius=10, wrap="word")
        win._trans_box.pack(fill="both", expand=True)
        win._trans_box.insert("1.0", translated)
        win._trans_box.configure(state="disabled")

        # Footer
        footer = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=72)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        win._usage_label = ctk.CTkLabel(footer, text="", font=("Segoe UI", 11),
                                         text_color=C["muted"])
        win._usage_label.pack(side="left", padx=16, pady=12)

        _refresh_usage_label(win, current_engine)

        bf = ctk.CTkFrame(footer, fg_color="transparent")
        bf.pack(side="right", padx=16, pady=12)

        def do_copy():
            _reset_autoclose(win)
            win.clipboard_clear()
            win.clipboard_append(translated)
            win._copy_btn.configure(text="  Copied!  ")
            win.after(1500, lambda: win._copy_btn.configure(text="  Copy  "))

        def do_speak():
            _reset_autoclose(win)
            from services.ai.tts import is_available
            if not is_available():
                return
            tgt = target_lang or get_target_lang()
            _do_speak_updated(win, translated, tgt)

        win._speaking = False
        win._speak_btn = ctk.CTkButton(bf, text="  ▶  ", font=("Segoe UI", 13),
                                        fg_color=C["surface"], text_color=C["accent"],
                                        hover_color=C["card_alt"], corner_radius=10,
                                        width=52, height=36, command=do_speak)
        win._speak_btn.pack(side="left", padx=(0, 8))

        win._copy_btn = ctk.CTkButton(bf, text="  Copy  ", font=("Segoe UI Semibold", 13),
                                       fg_color=C["accent"], text_color=C["bg"],
                                       hover_color="#7ba4e8", corner_radius=10,
                                       width=100, height=36, command=do_copy)
        win._copy_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="  Close  ", font=("Segoe UI", 13),
                       fg_color=C["card_alt"], text_color=C["text"],
                       hover_color=C["border"], corner_radius=10,
                       width=90, height=36, command=_close_popup).pack(side="left")

        win.bind("<Escape>", lambda e: _close_popup())

        # Reset auto-close on any click/key inside the window
        def _on_activity(event=None):
            _reset_autoclose(win)
        win.bind("<Button-1>", _on_activity)
        win.bind("<Key>", _on_activity)

        # Nullify global ref on destroy
        def _on_destroy(event=None):
            global _popup_win, _popup_autoclose_id
            if event.widget is win:
                _popup_win = None
                _popup_autoclose_id = None
        win.bind("<Destroy>", _on_destroy)

        # Start the 10-second auto-close timer
        _reset_autoclose(win)

        win.mainloop()
    threading.Thread(target=_run, daemon=True).start()

def _update_popup(win, original, translated, current_engine, target_lang=None):
    """Refresh the content of an existing popup window."""
    # Update original text
    win._orig_box.configure(state="normal")
    win._orig_box.delete("1.0", "end")
    win._orig_box.insert("1.0", original)
    win._orig_box.configure(state="disabled")
    # Update translation text
    win._trans_box.configure(state="normal")
    win._trans_box.delete("1.0", "end")
    win._trans_box.insert("1.0", translated)
    win._trans_box.configure(state="disabled")
    # Update source language label
    _src_label = LANGUAGES.get(get_source_lang(), get_source_lang()).upper()
    win._orig_label.configure(text=f"ORIGINAL  ({_src_label})")
    # Update translation language label
    _tgt_code  = target_lang or get_target_lang()
    _tgt_label = LANGUAGES.get(_tgt_code, _tgt_code).upper()
    try:
        win._trans_label.configure(text=f"TRANSLATION  ({_tgt_label})")
    except Exception:
        pass
    # Update engine badge
    engine_name = _engine_display_name(current_engine)
    engine_colors = {"deepl": C["accent"], "google": C["green"], "yandex": C["yellow"]}
    win._badge_frame.configure(fg_color=engine_colors.get(current_engine, C["accent"]))
    win._badge_label.configure(text=engine_name)
    # Update usage
    _refresh_usage_label(win, current_engine)
    # Reset copy button
    win._copy_btn.configure(text="  Copy  ",
                             command=lambda: _do_copy_updated(win, translated))
    # Reset speak button
    from services.ai.tts import stop
    stop()
    win._speaking = False
    try:
        tgt = target_lang or get_target_lang()
        win._speak_btn.configure(text="  ▶  ",
                                  command=lambda t=translated, l=tgt: _do_speak_updated(win, t, l))
    except Exception:
        pass

def _do_speak_updated(win, translated, lang_code):
    from services.ai.tts import speak, stop
    if getattr(win, "_speaking", False):
        stop()
        win._speaking = False
        try:
            win._speak_btn.configure(text="  ▶  ")
        except Exception:
            pass
    else:
        win._speaking = True
        try:
            win._speak_btn.configure(text="  ■  ")
        except Exception:
            pass
        speak(translated, lang_code=lang_code)
        def _poll():
            from services.ai.tts import _speak_lock
            if not _speak_lock.locked():
                try:
                    win._speaking = False
                    win._speak_btn.configure(text="  ▶  ")
                except Exception:
                    pass
            else:
                try:
                    win.after(200, _poll)
                except Exception:
                    pass
        try:
            win.after(200, _poll)
        except Exception:
            pass

def _do_copy_updated(win, translated):
    _reset_autoclose(win)
    try:
        win.clipboard_clear()
        win.clipboard_append(translated)
        win._copy_btn.configure(text="  Copied!  ")
        win.after(1500, lambda: win._copy_btn.configure(text="  Copy  "))
    except Exception:
        pass

def _refresh_usage_label(win, current_engine):
    from globals import usage_data
    engine_name = _engine_display_name(current_engine)
    if current_engine == "deepl" and usage_data["character_limit"] > 0:
        rem = usage_data["character_limit"] - usage_data["character_count"]
        pct = rem / usage_data["character_limit"] * 100
        txt = f"{rem:,} / {usage_data['character_limit']:,} chars left  ({pct:.1f}%)"
    elif current_engine == "deepl":
        txt = "DeepL usage data unavailable"
    else:
        txt = f"{engine_name} - free, no limit"
    win._usage_label.configure(text=txt)

def _reset_autoclose(win):
    """(Re)start the 10-second inactivity auto-close timer."""
    global _popup_autoclose_id
    try:
        if _popup_autoclose_id is not None:
            win.after_cancel(_popup_autoclose_id)
        _popup_autoclose_id = win.after(10000, _close_popup)
    except Exception:
        pass

def _engine_display_name(engine):
    return {"deepl": "DeepL", "google": "Google Translate", "yandex": "Yandex Translate"}.get(engine, engine)