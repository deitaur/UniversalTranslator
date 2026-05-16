"""
Settings window for configuration
"""

import datetime as _dt
import os
import sys
import threading
from pathlib import Path
import customtkinter as ctk
from config import APP_NAME, APP_VERSION, CONFIG_DIR, ICON_FILE, C, config, save_config_full
from utils.language import LANGUAGES
from win32.hotkeys import DEFAULT_HOTKEYS, parse_hotkey_string

def show_settings_window(current_engine, update_tray_icon, rebuild_menu):
    """Display the settings window."""
    import logging, traceback
    _log = logging.getLogger("settings")

    def _run():
      try:
        _log.info("Settings window opening...")
        ctk.set_appearance_mode("dark")
        win = ctk.CTk()
        win.title(f"{APP_NAME} - Settings")
        win.geometry("860x600")
        win.minsize(780, 520)
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.configure(fg_color=C["bg"])

        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        # ---- Header bar ----
        hdr = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Settings", font=("Segoe UI Semibold", 22),
                     text_color=C["text"]).pack(side="left", padx=24, pady=12)
        try:
            _src = sys.argv[0] if getattr(sys, "frozen", False) else __file__
            _ts = _dt.datetime.fromtimestamp(os.path.getmtime(_src)).strftime("%b %d, %Y  %H:%M")
        except Exception:
            _ts = ""
        _vt = f"v{APP_VERSION}"
        if _ts:
            _vt += f"  |  {_ts}"
        ctk.CTkLabel(hdr, text=_vt, font=("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="right", padx=24, pady=12)

        # ---- Scrollable body with two columns ----
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=0)
        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=12, pady=(10, 10))
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # ============== LEFT COLUMN ==============

        # --- Engine ---
        ef = ctk.CTkFrame(left, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        ef.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(ef, text="Translation Engine", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 8), anchor="w")
        engine_var = ctk.StringVar(value=current_engine)

        def on_engine(val):
            nonlocal current_engine
            if val == "deepl" and not config.get("api_key"):
                engine_var.set(current_engine)
                key_entry.focus()
                return
            if val == "yandex" and not config.get("yandex_api_key"):
                engine_var.set(current_engine)
                yandex_key_entry.focus()
                return
            current_engine = val
            import globals as g
            g.current_engine = val
            config["engine"] = val
            save_config_full()
            if val == "deepl":
                from services.translators.deepl import DeepLEngine
                engine = DeepLEngine()
                count, limit = engine.get_usage()
                from globals import usage_data
                usage_data["character_count"] = count
                usage_data["character_limit"] = limit
            update_tray_icon()
            rebuild_menu()

        for ev, el, ec in [("deepl", "DeepL", C["accent"]),
                           ("google", "Google (free)", C["green"]),
                           ("yandex", "Yandex (free)", C["yellow"])]:
            ctk.CTkRadioButton(ef, text=el, variable=engine_var, value=ev,
                                command=lambda v=ev: on_engine(v),
                                font=("Segoe UI", 12), text_color=C["text"],
                                fg_color=ec, hover_color=ec,
                                border_color=C["border"]).pack(padx=14, anchor="w", pady=2)
        ctk.CTkFrame(ef, fg_color="transparent", height=6).pack()

        # Maps: code → display name, display name → code
        _code_to_name = {code: name for code, name in LANGUAGES.items()}
        _name_to_code = {name: code for code, name in LANGUAGES.items()}
        _lang_names   = list(LANGUAGES.values())   # ["Russian", "Spanish", …]

        # --- Source Language ---
        lf = ctk.CTkFrame(left, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        lf.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(lf, text="Ваш язык (исходный)",
                     font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 2), anchor="w")
        ctk.CTkLabel(lf, text="Язык, на котором вы обычно пишете. При авто-определении — направление обратного перевода.",
                     font=("Segoe UI", 10), text_color=C["muted"],
                     wraplength=340, justify="left").pack(padx=14, anchor="w")

        _src_code = config.get("source_lang", "ru")
        lang_var  = ctk.StringVar(value=_code_to_name.get(_src_code, _src_code))
        lang_combo = ctk.CTkComboBox(lf, variable=lang_var,
                                     values=_lang_names,
                                     font=("Segoe UI", 12), text_color=C["text"],
                                     fg_color=C["card"], button_color=C["accent"],
                                     border_color=C["border"], dropdown_fg_color=C["card"],
                                     dropdown_text_color=C["text"], dropdown_hover_color=C["surface"],
                                     command=lambda v: None)   # live update via StringVar
        lang_combo.pack(padx=14, pady=(6, 12), fill="x")

        # --- Target Language ---
        tf = ctk.CTkFrame(left, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        tf.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(tf, text="Переводить на язык",
                     font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 2), anchor="w")
        ctk.CTkLabel(tf, text="Язык перевода по умолчанию. Например, выберите English — и всё будет переводиться в английский.",
                     font=("Segoe UI", 10), text_color=C["muted"],
                     wraplength=340, justify="left").pack(padx=14, anchor="w")

        _SAME = "(Same as source)"
        _tgt_code   = config.get("target_lang", "")
        _tgt_display = _code_to_name.get(_tgt_code, _SAME) if _tgt_code else _SAME
        target_var  = ctk.StringVar(value=_tgt_display)
        target_combo = ctk.CTkComboBox(tf, variable=target_var,
                                       values=[_SAME] + _lang_names,
                                       font=("Segoe UI", 12), text_color=C["text"],
                                       fg_color=C["card"], button_color=C["accent"],
                                       border_color=C["border"], dropdown_fg_color=C["card"],
                                       dropdown_text_color=C["text"], dropdown_hover_color=C["surface"],
                                       command=lambda v: None)  # live update via StringVar
        target_combo.pack(padx=14, pady=(6, 12), fill="x")

        # --- API Keys ---
        kf = ctk.CTkFrame(left, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        kf.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(kf, text="API Keys", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 8), anchor="w")

        # DeepL Key
        ctk.CTkLabel(kf, text="DeepL API Key:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(padx=14, anchor="w")
        key_entry = ctk.CTkEntry(kf, font=("Consolas", 11), text_color=C["text"],
                                 fg_color=C["card"], border_color=C["border"],
                                 show="•", placeholder_text="Enter DeepL API key...")
        key_entry.pack(padx=14, pady=(0, 8), fill="x")
        key_entry.insert(0, config.get("api_key", ""))

        # Yandex Key
        ctk.CTkLabel(kf, text="Yandex API Key:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(padx=14, anchor="w")
        yandex_key_entry = ctk.CTkEntry(kf, font=("Consolas", 11), text_color=C["text"],
                                        fg_color=C["card"], border_color=C["border"],
                                        show="•", placeholder_text="Enter Yandex API key...")
        yandex_key_entry.pack(padx=14, pady=(0, 8), fill="x")
        yandex_key_entry.insert(0, config.get("yandex_api_key", ""))

        # Yandex Folder ID
        ctk.CTkLabel(kf, text="Yandex Folder ID:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(padx=14, anchor="w")
        yandex_folder_entry = ctk.CTkEntry(kf, font=("Consolas", 11), text_color=C["text"],
                                           fg_color=C["card"], border_color=C["border"],
                                           placeholder_text="Enter Yandex Folder ID...")
        yandex_folder_entry.pack(padx=14, pady=(0, 12), fill="x")
        yandex_folder_entry.insert(0, config.get("yandex_folder_id", ""))

        # ============== RIGHT COLUMN ==============

        # --- System Options ---
        sf = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        sf.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(sf, text="System Options", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 8), anchor="w")

        # Autostart
        autostart_var = ctk.BooleanVar(value=config.get("autostart", False))
        ctk.CTkCheckBox(sf, text="Start with Windows", variable=autostart_var,
                        font=("Segoe UI", 12), text_color=C["text"],
                        fg_color=C["accent"], hover_color=C["accent"],
                        border_color=C["border"]).pack(padx=14, anchor="w", pady=2)

        # Clipboard-only
        clipboard_var = ctk.BooleanVar(value=config.get("clipboard_only", False))
        ctk.CTkCheckBox(sf, text="Clipboard-only mode (no text selection)", variable=clipboard_var,
                        font=("Segoe UI", 12), text_color=C["text"],
                        fg_color=C["accent"], hover_color=C["accent"],
                        border_color=C["border"]).pack(padx=14, anchor="w", pady=2)

        # Direct type
        direct_var = ctk.BooleanVar(value=config.get("direct_type", False))
        ctk.CTkCheckBox(sf, text="Direct type replacement (no clipboard)", variable=direct_var,
                        font=("Segoe UI", 12), text_color=C["text"],
                        fg_color=C["accent"], hover_color=C["accent"],
                        border_color=C["border"]).pack(padx=14, anchor="w", pady=2)

        # TTS voice engine
        ctk.CTkFrame(sf, fg_color=C["border"], height=1).pack(fill="x", padx=14, pady=(8, 6))
        tts_row = ctk.CTkFrame(sf, fg_color="transparent")
        tts_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tts_row, text="Голос озвучки:", font=("Segoe UI", 12),
                     text_color=C["text"]).pack(side="left")

        from services.ai.tts import gtts_installed
        _gtts_ok = gtts_installed()
        _tts_options = ["Google (gTTS)" if _gtts_ok else "Google (pip install gtts)", "Windows SAPI"]
        _tts_stored  = {"Google (gTTS)": "gtts", "Google (pip install gtts)": "gtts", "Windows SAPI": "sapi"}
        _tts_display = {"gtts": "Google (gTTS)" if _gtts_ok else "Google (pip install gtts)",
                        "sapi": "Windows SAPI"}
        tts_engine_var = ctk.StringVar(
            value=_tts_display.get(config.get("tts_engine", "gtts"), "Google (gTTS)"))
        tts_combo = ctk.CTkComboBox(tts_row, variable=tts_engine_var,
                                    values=_tts_options, width=180, height=28,
                                    font=("Segoe UI", 12), text_color=C["text"],
                                    fg_color=C["card_alt"], button_color=C["accent"],
                                    border_color=C["border"], dropdown_fg_color=C["card"],
                                    dropdown_text_color=C["text"],
                                    dropdown_hover_color=C["surface"],
                                    state="normal" if _gtts_ok else "readonly",
                                    command=lambda v: None)
        tts_combo.pack(side="left", padx=(10, 0))

        def _test_tts():
            from services.ai.tts import speak
            tts_btn.configure(text="▶ …", state="disabled")
            engine_sel = _tts_stored.get(tts_engine_var.get(), "gtts")
            from config import config as _cfg
            _cfg["tts_engine"] = engine_sel
            speak("Проверка голоса", lang_code="ru")
            win.after(3000, lambda: tts_btn.configure(text="▶ Тест", state="normal"))

        tts_btn = ctk.CTkButton(tts_row, text="▶ Тест", width=70, height=28,
                                font=("Segoe UI", 11), fg_color=C["surface"],
                                text_color=C["accent"], hover_color=C["card_alt"],
                                corner_radius=6, command=_test_tts)
        tts_btn.pack(side="left", padx=(8, 0))
        ctk.CTkFrame(sf, fg_color="transparent", height=8).pack()

        # --- Ollama (Negotiator AI) ---
        of = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        of.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(of, text="Negotiator AI (Ollama)", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 2), anchor="w")
        ctk.CTkLabel(of, text="Local model via ollama serve", font=("Segoe UI", 10),
                     text_color=C["muted"]).pack(padx=14, pady=(0, 8), anchor="w")

        ctk.CTkLabel(of, text="Model name:", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(padx=14, anchor="w")
        ollama_entry = ctk.CTkEntry(of, font=("Consolas", 11), text_color=C["text"],
                                     fg_color=C["card_alt"], border_color=C["border"],
                                     placeholder_text="e.g., qwen2.5:14b, llama3")
        ollama_entry.pack(padx=14, pady=(0, 8), fill="x")
        ollama_entry.insert(0, config.get("ollama_model", "qwen2.5:14b"))

        ctk.CTkLabel(of, text="Response language:", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(padx=14, anchor="w")
        neg_lang_values = ["Same as input", "English", "Russian"]
        neg_lang_var = ctk.StringVar(value=config.get("negotiator_lang", "Same as input"))
        neg_lang_combo = ctk.CTkComboBox(of, variable=neg_lang_var,
                                          values=neg_lang_values,
                                          font=("Segoe UI", 12), text_color=C["text"],
                                          fg_color=C["card_alt"], button_color=C["accent"],
                                          border_color=C["border"], dropdown_fg_color=C["card"],
                                          dropdown_text_color=C["text"],
                                          dropdown_hover_color=C["surface"])
        neg_lang_combo.pack(padx=14, pady=(0, 8), fill="x")

        # AI Buttons Frame
        ai_btn_frame = ctk.CTkFrame(of, fg_color="transparent")
        ai_btn_frame.pack(padx=14, pady=(0, 12), fill="x")

        # Manage Roles button
        ctk.CTkButton(ai_btn_frame, text="Manage AI Roles...", font=("Segoe UI Semibold", 12),
                       fg_color=C["accent"], text_color=C["bg"],
                       hover_color="#7ba4e8", corner_radius=8, height=34,
                       command=lambda: _open_role_editor()
                       ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        def _on_load_ai():
            import threading
            from services.ai.ollama import preload_model
            
            # Disable button immediately on main thread
            load_btn.configure(text="Загрузка...", state="disabled")
            
            def task():
                success = preload_model()
                if success:
                    win.after(0, lambda: load_btn.configure(text="ИИ загружен!", state="normal"))
                    win.after(3000, lambda: load_btn.configure(text="Загрузить ИИ в память"))
                else:
                    win.after(0, lambda: load_btn.configure(text="Ошибка", state="normal"))
                    win.after(3000, lambda: load_btn.configure(text="Загрузить ИИ в память"))
            threading.Thread(target=task, daemon=True).start()

        load_btn = ctk.CTkButton(ai_btn_frame, text="Загрузить ИИ в память", font=("Segoe UI Semibold", 12),
                       fg_color=C["accent"], text_color=C["bg"],
                       hover_color="#7ba4e8", corner_radius=8, height=34,
                       command=_on_load_ai)
        load_btn.pack(side="right", fill="x", expand=True, padx=(6, 0))

        # --- Voice Dictation ---
        df = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        df.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(df, text="Голосовая диктовка  (Ctrl+Alt+D)",
                     font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 2), anchor="w")
        ctk.CTkLabel(df, text="Запись голоса → транскрипция → сохранение в файл",
                     font=("Segoe UI", 10), text_color=C["muted"]).pack(padx=14, anchor="w")

        # Save folder
        ctk.CTkLabel(df, text="Папка сохранения:", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(padx=14, pady=(10, 2), anchor="w")
        folder_row = ctk.CTkFrame(df, fg_color="transparent")
        folder_row.pack(fill="x", padx=14, pady=(0, 6))

        _default_dict_folder = str(Path.home() / "Documents" / "Dictations")
        dict_folder_var = ctk.StringVar(value=config.get("dictation_folder", _default_dict_folder))
        dict_folder_entry = ctk.CTkEntry(folder_row, textvariable=dict_folder_var,
                                          font=("Segoe UI", 11), text_color=C["text"],
                                          fg_color=C["card_alt"], border_color=C["border"],
                                          height=28)
        dict_folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def _browse_dict_folder():
            from tkinter import filedialog
            win.attributes("-topmost", False)
            folder = filedialog.askdirectory(
                title="Папка для сохранения диктовок", parent=win,
                initialdir=dict_folder_var.get() or str(Path.home()))
            win.attributes("-topmost", True)
            win.lift()
            if folder:
                dict_folder_var.set(folder)

        ctk.CTkButton(folder_row, text="…", width=32, height=28,
                       font=("Segoe UI", 12), fg_color=C["card_alt"],
                       text_color=C["text"], hover_color=C["border"],
                       corner_radius=6, command=_browse_dict_folder).pack(side="left")

        # Format + Obsidian options
        fmt_row = ctk.CTkFrame(df, fg_color="transparent")
        fmt_row.pack(fill="x", padx=14, pady=(0, 4))

        ctk.CTkLabel(fmt_row, text="Формат:", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(side="left")
        _fmt_opts = ["Markdown (.md)", "Текст (.txt)"]
        _fmt_stored = {"Markdown (.md)": "md", "Текст (.txt)": "txt"}
        _fmt_display = {"md": "Markdown (.md)", "txt": "Текст (.txt)"}
        dict_fmt_var = ctk.StringVar(
            value=_fmt_display.get(config.get("dictation_format", "md"), "Markdown (.md)"))
        ctk.CTkComboBox(fmt_row, variable=dict_fmt_var, values=_fmt_opts,
                        width=150, height=26, font=("Segoe UI", 11),
                        text_color=C["text"], fg_color=C["card_alt"],
                        button_color=C["accent"], border_color=C["border"],
                        dropdown_fg_color=C["card"], dropdown_text_color=C["text"],
                        dropdown_hover_color=C["surface"],
                        command=lambda v: None).pack(side="left", padx=(8, 0))

        obsidian_var = ctk.BooleanVar(value=config.get("dictation_obsidian", True))
        ctk.CTkCheckBox(fmt_row, text="Obsidian frontmatter", variable=obsidian_var,
                        font=("Segoe UI", 11), text_color=C["text"],
                        fg_color=C["accent"], hover_color=C["accent"],
                        border_color=C["border"]).pack(side="left", padx=(14, 0))

        # Tags
        tags_row = ctk.CTkFrame(df, fg_color="transparent")
        tags_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(tags_row, text="Теги (через запятую):", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(side="left")
        dict_tags_entry = ctk.CTkEntry(tags_row, font=("Segoe UI", 11),
                                        text_color=C["text"], fg_color=C["card_alt"],
                                        border_color=C["border"], height=26,
                                        placeholder_text="dictation, notes")
        dict_tags_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        dict_tags_entry.insert(0, config.get("dictation_tags", "dictation"))

        # --- Hotkeys ---
        hf = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=12,
                           border_width=1, border_color=C["border"])
        hf.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(hf, text="Hotkeys", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=14, pady=(12, 8), anchor="w")

        hotkey_entries = {}
        for name, label in [("popup", "Show Popup (Ctrl+Alt+T)"),
                            ("replace", "Replace Text (Ctrl+Alt+R)"),
                            ("clipboard", "Translate Clipboard (Ctrl+Alt+Y)"),
                            ("whisper", "Voice to Text (Ctrl+Alt+W)"),
                            ("dictation", "Voice Dictation (Ctrl+Alt+D)"),
                            ("voicechat", "Voice AI Chat (Ctrl+Alt+V)"),
                            ("negotiator", "Negotiator (Ctrl+Alt+N)"),
                            ("teacher", "English Teacher (Ctrl+Alt+E)")]:
            ctk.CTkLabel(hf, text=label, font=("Segoe UI", 12),
                         text_color=C["subtext"]).pack(padx=14, anchor="w")
            entry = ctk.CTkEntry(hf, font=("Consolas", 11), text_color=C["text"],
                                 fg_color=C["card"], border_color=C["border"],
                                 placeholder_text="e.g., Ctrl+Alt+T")
            entry.pack(padx=14, pady=(0, 8), fill="x")
            entry.insert(0, config.get(f"hotkey_{name}", DEFAULT_HOTKEYS.get(name, "")))
            hotkey_entries[name] = entry

        # --- Save Button ---
        def _on_save():
            _save_settings(
                win, key_entry, yandex_key_entry, yandex_folder_entry,
                ollama_entry, neg_lang_var, autostart_var, clipboard_var, direct_var,
                hotkey_entries, update_tray_icon, rebuild_menu,
                lang_var, target_var, _name_to_code,
                tts_engine_var, _tts_stored,
                dict_folder_var, dict_fmt_var, _fmt_stored,
                obsidian_var, dict_tags_entry,
            )

        save_btn = ctk.CTkButton(win, text="Save Settings", font=("Segoe UI Semibold", 14),
                                 fg_color=C["accent"], text_color=C["bg"],
                                 hover_color="#7ba4e8", corner_radius=10,
                                 height=48, command=_on_save)
        save_btn.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

        _log.info("Settings window mainloop starting")
        win.mainloop()
      except Exception as e:
        _log.error("Settings window crashed: %s\n%s", e, traceback.format_exc())

    threading.Thread(target=_run, daemon=True).start()

def _save_settings(win, key_entry, yandex_key_entry, yandex_folder_entry,
                   ollama_entry, neg_lang_var, autostart_var, clipboard_var, direct_var,
                   hotkey_entries, update_tray_icon, rebuild_menu,
                   lang_var=None, target_var=None, name_to_code=None,
                   tts_engine_var=None, tts_stored_map=None,
                   dict_folder_var=None, dict_fmt_var=None, dict_fmt_stored=None,
                   obsidian_var=None, dict_tags_entry=None):
    """Save all settings."""
    config["api_key"]          = key_entry.get().strip()
    config["yandex_api_key"]   = yandex_key_entry.get().strip()
    config["yandex_folder_id"] = yandex_folder_entry.get().strip()
    ollama_val = ollama_entry.get().strip()
    if ollama_val:
        config["ollama_model"] = ollama_val
    config["negotiator_lang"] = neg_lang_var.get()
    config["autostart"]       = autostart_var.get()
    config["clipboard_only"]  = clipboard_var.get()
    config["direct_type"]     = direct_var.get()
    if tts_engine_var and tts_stored_map:
        config["tts_engine"] = tts_stored_map.get(tts_engine_var.get(), "gtts")

    # Dictation settings
    if dict_folder_var:
        config["dictation_folder"] = dict_folder_var.get().strip()
    if dict_fmt_var and dict_fmt_stored:
        config["dictation_format"] = dict_fmt_stored.get(dict_fmt_var.get(), "md")
    if obsidian_var is not None:
        config["dictation_obsidian"] = obsidian_var.get()
    if dict_tags_entry is not None:
        config["dictation_tags"] = dict_tags_entry.get().strip()

    # Source and target languages
    if lang_var and name_to_code is not None:
        src_name = lang_var.get()
        config["source_lang"] = name_to_code.get(src_name, src_name)

    if target_var and name_to_code is not None:
        tgt_name = target_var.get()
        if tgt_name == "(Same as source)":
            config["target_lang"] = ""
        else:
            config["target_lang"] = name_to_code.get(tgt_name, tgt_name)

    for name in hotkey_entries:
        hk = hotkey_entries[name].get().strip()
        if hk:
            try:
                parse_hotkey_string(hk)
                config[f"hotkey_{name}"] = hk
            except Exception:
                pass

    save_config_full()

    # Destroy window first so tkinter mainloop ends cleanly
    try:
        win.destroy()
    except Exception:
        pass

    # Run autostart and tray updates in a background thread
    # to avoid blocking or cross-thread tkinter/pystray conflicts
    def _post_save():
        from ui.tray_menu import set_autostart
        set_autostart(config["autostart"])
        update_tray_icon()
        rebuild_menu()
    threading.Thread(target=_post_save, daemon=True).start()

def _open_role_editor():
    from ui.role_editor import show_role_editor
    show_role_editor()
