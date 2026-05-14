"""
Chat popup with role selector, copy/paste buttons, language switch.
Supports selectable text in bubbles, right-click copy, font/size settings,
and in-chat translation via Ctrl+Alt+T in the input field.
"""

import tkinter as tk
import threading
import customtkinter as ctk
from config import APP_NAME, ICON_FILE, C, config, save_config_full

_chat_win = None
_chat_history = []
_chat_lock = threading.Lock()
_current_mode = "negotiator"
_current_session_id = None

# ── Font configuration ──
# Three highly readable fonts available on Windows
FONT_FAMILIES = {
    "Segoe UI": "Segoe UI",
    "Verdana": "Verdana",
    "Cascadia Code": "Cascadia Code",
}
FONT_FAMILY_LIST = list(FONT_FAMILIES.keys())

FONT_SIZES = {
    "Small": 11,
    "Medium": 13,
    "Large": 15,
}
FONT_SIZE_LIST = list(FONT_SIZES.keys())


def _get_chat_font():
    """Get the current chat font family and size from config."""
    family = config.get("chat_font_family", "Segoe UI")
    size_label = config.get("chat_font_size", "Medium")
    size = FONT_SIZES.get(size_label, 13)
    return family, size


def _close_chat():
    global _chat_win
    if _chat_win is not None:
        try:
            _chat_win.destroy()
        except Exception:
            pass
    _chat_win = None


def show_chat_window(initial_text="", mode="negotiator"):
    global _chat_win, _chat_history, _current_mode, _current_session_id

    if _chat_win is not None:
        try:
            _chat_win.winfo_exists()
            if mode != _current_mode:
                _current_mode = mode
                _update_header_for_mode(_chat_win)
                # Update role selector
                try:
                    _chat_win._role_var.set(_current_mode)
                except Exception:
                    pass
            _chat_win.deiconify()
            _chat_win.lift()
            _chat_win.focus_force()
            if initial_text.strip():
                _send_message(_chat_win, initial_text)
            return
        except Exception:
            _chat_win = None

    import uuid
    from storage.history import load_sessions
    
    sessions = load_sessions()
    if not _current_session_id or _current_session_id not in sessions:
        if sessions:
            _current_session_id = max(sessions.keys(), key=lambda k: sessions[k].get("updated", ""))
            _chat_history = sessions[_current_session_id].get("history", [])
        else:
            _current_session_id = str(uuid.uuid4())
            _chat_history = []

    _current_mode = mode

    def _save_current_session():
        from storage.history import save_session
        save_session(_current_session_id, _chat_history)

    def _run():
        global _chat_win
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        win = ctk.CTk()
        _chat_win = win
        win._save_current_session = _save_current_session
        win.attributes("-topmost", True)
        win.configure(fg_color=C["bg"])

        try:
            cx, cy = win.winfo_pointerx(), win.winfo_pointery()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            ww, wh = 560, 640
            x = min(cx + 20, sw - ww - 20)
            y = max(cy - wh // 2, 40)
            if y + wh > sh - 60:
                y = sh - wh - 60
            win.geometry(str(ww) + "x" + str(wh) + "+" + str(x) + "+" + str(y))
        except Exception:
            win.geometry("560x640")

        win.resizable(True, True)
        win.minsize(440, 400)

        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        # ── Header ──
        header = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Role selector dropdown
        from storage.roles import load_roles
        roles = load_roles()
        role_ids = list(roles.keys())
        role_names_map = {rid: roles[rid].get("name", rid) for rid in role_ids}
        role_display = [role_names_map[rid] for rid in role_ids]

        role_var = ctk.StringVar(value=_current_mode)
        win._role_var = role_var

        def _display_to_id(display_name):
            for rid, rname in role_names_map.items():
                if rname == display_name:
                    return rid
            return display_name

        def on_role_change(val):
            global _current_mode
            rid = _display_to_id(val)
            if rid != _current_mode:
                _current_mode = rid
                _update_header_for_mode(win)

        # Show current role name
        current_display = role_names_map.get(_current_mode, _current_mode)

        role_combo = ctk.CTkComboBox(header, values=role_display,
                                      width=140, height=30,
                                      font=("Segoe UI Semibold", 12),
                                      text_color=C["text"],
                                      fg_color=C["card_alt"],
                                      button_color=C["accent"],
                                      border_color=C["border"],
                                      dropdown_fg_color=C["card"],
                                      dropdown_text_color=C["text"],
                                      dropdown_hover_color=C["surface"],
                                      command=on_role_change)
        role_combo.set(current_display)
        role_combo.pack(side="left", padx=(10, 4), pady=9)
        win._role_combo = role_combo

        # Model name label
        model_label = ctk.CTkLabel(header, text=config.get("ollama_model", "qwen2.5:14b"),
                                    font=("Segoe UI", 10), text_color=C["muted"])
        model_label.pack(side="left", padx=(2, 4))

        # Language selector
        lang_values = ["Auto", "English", "Russian"]
        lang_map_to_ui = {"Same as input": "Auto", "English": "English", "Russian": "Russian"}
        lang_map_from_ui = {"Auto": "Same as input", "English": "English", "Russian": "Russian"}
        current_lang = config.get("negotiator_lang", "Same as input")

        def on_lang_change(val):
            config["negotiator_lang"] = lang_map_from_ui.get(val, "Same as input")
            save_config_full()

        lang_combo = ctk.CTkComboBox(header, values=lang_values,
                                      width=82, height=28,
                                      font=("Segoe UI", 11),
                                      text_color=C["text"],
                                      fg_color=C["card_alt"],
                                      button_color=C["accent"],
                                      border_color=C["border"],
                                      dropdown_fg_color=C["card"],
                                      dropdown_text_color=C["text"],
                                      dropdown_hover_color=C["surface"],
                                      command=on_lang_change)
        lang_combo.set(lang_map_to_ui.get(current_lang, "Auto"))
        lang_combo.pack(side="left", padx=(0, 4), pady=9)

        # Close button
        ctk.CTkButton(header, text="X", width=30, height=28,
                       font=("Segoe UI Bold", 12), fg_color=C["card_alt"],
                       text_color=C["red"], hover_color=C["border"],
                       corner_radius=6, command=_close_chat
                       ).pack(side="right", padx=(0, 6), pady=10)

        # ── Toolbar (font family + font size + sessions) ──
        toolbar = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=34)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        # Font family selector
        ctk.CTkLabel(toolbar, text="Font:", font=("Segoe UI", 10),
                     text_color=C["muted"]).pack(side="left", padx=(10, 2), pady=4)

        font_family_var = ctk.StringVar(value=config.get("chat_font_family", "Segoe UI"))
        font_family_combo = ctk.CTkComboBox(toolbar, values=FONT_FAMILY_LIST,
                                             variable=font_family_var,
                                             width=110, height=26,
                                             font=("Segoe UI", 10),
                                             text_color=C["text"],
                                             fg_color=C["card_alt"],
                                             button_color=C["accent"],
                                             border_color=C["border"],
                                             dropdown_fg_color=C["card"],
                                             dropdown_text_color=C["text"],
                                             dropdown_hover_color=C["surface"],
                                             command=lambda val: _on_font_change(win, val, font_size_var.get()))
        font_family_combo.pack(side="left", padx=(0, 8), pady=4)

        # Font size selector
        ctk.CTkLabel(toolbar, text="Size:", font=("Segoe UI", 10),
                     text_color=C["muted"]).pack(side="left", padx=(0, 2), pady=4)

        font_size_var = ctk.StringVar(value=config.get("chat_font_size", "Medium"))
        font_size_combo = ctk.CTkComboBox(toolbar, values=FONT_SIZE_LIST,
                                           variable=font_size_var,
                                           width=90, height=26,
                                           font=("Segoe UI", 10),
                                           text_color=C["text"],
                                           fg_color=C["card_alt"],
                                           button_color=C["accent"],
                                           border_color=C["border"],
                                           dropdown_fg_color=C["card"],
                                           dropdown_text_color=C["text"],
                                           dropdown_hover_color=C["surface"],
                                           command=lambda val: _on_font_change(win, font_family_var.get(), val))
        font_size_combo.pack(side="left", padx=(0, 8), pady=4)

        # Sessions Dropdown & Actions
        from storage.history import load_sessions, save_session, delete_session
        import uuid
        
        def _update_sessions_combo():
            sess = load_sessions()
            if not sess:
                sess_combo.configure(values=["No saved chats"])
                sess_combo.set("No saved chats")
                return
            
            val_list = []
            current_name = ""
            for k, v in sorted(sess.items(), key=lambda item: item[1].get("updated", ""), reverse=True):
                n = v.get("name", "New Chat")
                val_list.append(n)
                if k == _current_session_id:
                    current_name = n
            
            sess_combo.configure(values=val_list)
            if current_name:
                sess_combo.set(current_name)
                
        def _on_session_select(val):
            global _current_session_id, _chat_history
            sess = load_sessions()
            for k, v in sess.items():
                if v.get("name") == val:
                    _current_session_id = k
                    _chat_history = v.get("history", [])
                    _rebuild_chat_ui(win)
                    break
                    
        def _new_session():
            global _current_session_id, _chat_history
            _current_session_id = str(uuid.uuid4())
            _chat_history = []
            save_session(_current_session_id, _chat_history)
            _clear_chat(win)
            _update_sessions_combo()
            
        def _del_session():
            global _current_session_id, _chat_history
            delete_session(_current_session_id)
            sess = load_sessions()
            if sess:
                _current_session_id = max(sess.keys(), key=lambda k: sess[k].get("updated", ""))
                _chat_history = sess[_current_session_id].get("history", [])
            else:
                _current_session_id = str(uuid.uuid4())
                _chat_history = []
                save_session(_current_session_id, _chat_history)
            _rebuild_chat_ui(win)
            _update_sessions_combo()

        def _compress_context():
            global _chat_history
            if not _chat_history:
                return
            
            from services.ai.ollama import chat_ollama
            win._send_btn.configure(state="disabled")
            
            def _task():
                global _chat_history
                try:
                    from services.ai.ollama import chat_ollama

                    compress_prompt = "You are an expert summarizer. Summarize the following dialogue. Capture the core context, the conflict/situation, and any decisions made. Output ONLY the summary in Russian."
                    compress_msgs = [{"role": "system", "content": compress_prompt}] + _chat_history
                    summary = chat_ollama(compress_msgs, mode=_current_mode)
                    
                    _chat_history = [{"role": "user", "content": f"[Сжатый контекст предыдущего диалога]:\n{summary}"}]
                    _save_current_session()
                    win.after(0, lambda: _rebuild_chat_ui(win))
                except Exception as e:
                    print(f"Compress Error: {e}")
                finally:
                    win.after(0, lambda: win._send_btn.configure(state="normal"))
            threading.Thread(target=_task, daemon=True).start()

        win._compress_context = _compress_context

        sess_combo = ctk.CTkComboBox(toolbar, values=["Loading..."], width=130, height=26,
                                     font=("Segoe UI", 10), text_color=C["text"], fg_color=C["card_alt"],
                                     button_color=C["accent"], border_color=C["border"],
                                     command=_on_session_select)
        sess_combo.pack(side="right", padx=(2, 10), pady=4)
        
        btn_del = ctk.CTkButton(toolbar, text="Del", width=36, height=26, font=("Segoe UI", 10),
                                fg_color=C["red"], text_color=C["bg"], hover_color="#e06080",
                                command=_del_session)
        btn_del.pack(side="right", padx=2)
        
        btn_new = ctk.CTkButton(toolbar, text="New", width=36, height=26, font=("Segoe UI", 10),
                                fg_color=C["green"], text_color=C["bg"], hover_color="#73daca",
                                command=_new_session)
        btn_new.pack(side="right", padx=2)
        
        btn_comp = ctk.CTkButton(toolbar, text="Compress", width=60, height=26, font=("Segoe UI", 10),
                                 fg_color=C["accent"], text_color=C["bg"], hover_color="#7ba4e8",
                                 command=_compress_context)
        btn_comp.pack(side="right", padx=(10, 2))
        
        _update_sessions_combo()

        win._font_family_var = font_family_var
        win._font_size_var = font_size_var

        # ── Chat area ──
        chat_frame = ctk.CTkScrollableFrame(win, fg_color=C["bg"],
                                             corner_radius=0,
                                             scrollbar_button_color=C["card_alt"])
        chat_frame.pack(fill="both", expand=True, padx=0, pady=0)
        win._chat_frame = chat_frame

        # ── Input bar ──
        input_bar = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=56)
        input_bar.pack(fill="x", side="bottom")
        input_bar.pack_propagate(False)

        # Paste button
        paste_btn = ctk.CTkButton(input_bar, text="P", width=34, height=38,
                                   font=("Segoe UI Bold", 13), fg_color=C["card_alt"],
                                   text_color=C["subtext"], hover_color=C["border"],
                                   corner_radius=8,
                                   command=lambda: _paste_to_entry(win))
        paste_btn.pack(side="left", padx=(10, 4), pady=9)

        entry = ctk.CTkEntry(input_bar, placeholder_text="Type message...",
                              font=("Segoe UI", 13), fg_color=C["card"],
                              text_color=C["text"], border_color=C["border"],
                              corner_radius=8, height=38)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=9)
        win._entry = entry

        def on_send():
            msg = entry.get().strip()
            if msg:
                entry.delete(0, "end")
                _send_message(win, msg)

        send_btn = ctk.CTkButton(input_bar, text=">", width=50, height=38,
                                  font=("Segoe UI Bold", 16),
                                  fg_color=C["accent"], text_color=C["bg"],
                                  hover_color="#7ba4e8", corner_radius=8,
                                  command=on_send)
        send_btn.pack(side="right", padx=(0, 10), pady=9)
        win._send_btn = send_btn

        entry.bind("<Return>", lambda e: on_send())

        def _paste_key(e):
            try:
                clip = win.clipboard_get()
                entry.insert("insert", clip.strip())
            except Exception:
                pass
            return "break"
        entry.bind("<Control-v>", _paste_key)
        entry.bind("<Control-V>", _paste_key)

        # ── In-chat translation hotkey (Ctrl+Alt+T) ──
        # Translates selected text in the entry field, or the entire entry if nothing selected
        def _translate_in_entry(e=None):
            try:
                # Try to get selected text from entry
                try:
                    sel_start = entry.index(tk.SEL_FIRST)
                    sel_end = entry.index(tk.SEL_LAST)
                    text_to_translate = entry.get()[sel_start:sel_end]
                    has_selection = True
                except (tk.TclError, AttributeError):
                    text_to_translate = entry.get().strip()
                    has_selection = False

                if not text_to_translate:
                    return "break"

                # Translate in background to avoid blocking UI
                def _do_translate():
                    try:
                        from main import translate_text
                        translated = translate_text(text_to_translate)
                        if translated:
                            def _apply():
                                try:
                                    if has_selection:
                                        # Replace only selected text
                                        current = entry.get()
                                        new_text = current[:sel_start] + translated + current[sel_end:]
                                        entry.delete(0, "end")
                                        entry.insert(0, new_text)
                                    else:
                                        # Replace entire entry
                                        entry.delete(0, "end")
                                        entry.insert(0, translated)
                                except Exception:
                                    pass
                            win.after(0, _apply)
                    except Exception:
                        pass

                threading.Thread(target=_do_translate, daemon=True).start()
            except Exception:
                pass
            return "break"

        # Bind Ctrl+Alt+T to the entry widget for in-place translation
        entry.bind("<Control-Alt-t>", _translate_in_entry)
        entry.bind("<Control-Alt-T>", _translate_in_entry)

        win.bind("<Escape>", lambda e: _close_chat())

        _update_header_for_mode(win)

        if initial_text.strip():
            win.after(200, lambda: _send_message(win, initial_text))

        win.mainloop()

    threading.Thread(target=_run, daemon=True).start()


def _on_font_change(win, family, size_label):
    """Handle font family or size change — save to config and refresh bubbles."""
    config["chat_font_family"] = family
    config["chat_font_size"] = size_label
    save_config_full()
    # Refresh all text widgets in chat
    _refresh_bubble_fonts(win)


def _refresh_bubble_fonts(win):
    """Update font on all selectable text widgets in chat bubbles."""
    family, size = _get_chat_font()
    try:
        chat_frame = win._chat_frame
        for wrapper in chat_frame.winfo_children():
            _update_fonts_recursive(wrapper, family, size)
    except Exception:
        pass


def _update_fonts_recursive(widget, family, size):
    """Recursively find Text widgets and update their font."""
    if isinstance(widget, tk.Text):
        widget.configure(font=(family, size))
    try:
        for child in widget.winfo_children():
            _update_fonts_recursive(child, family, size)
    except Exception:
        pass


def _update_header_for_mode(win):
    from storage.roles import get_role
    role = get_role(_current_mode)
    if role:
        title = role.get("name", _current_mode)
    else:
        title = _current_mode
    try:
        win.title(APP_NAME + " - " + title)
    except Exception:
        pass


def _paste_to_entry(win):
    try:
        clip = win.clipboard_get()
        if clip.strip():
            win._entry.insert("insert", clip.strip())
            win._entry.focus()
    except Exception:
        pass


def _copy_to_clipboard(win, text):
    try:
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(text)
    except Exception:
        # Fallback to tkinter clipboard
        try:
            win.clipboard_clear()
            win.clipboard_append(text)
        except Exception:
            pass


def _get_role_label():
    from storage.roles import get_role
    role = get_role(_current_mode)
    if role:
        return role.get("name", _current_mode)
    return _current_mode


def _get_role_color():
    from storage.roles import get_role
    role = get_role(_current_mode)
    if role:
        return role.get("color", C["mauve"])
    return C["mauve"]


def _create_selectable_text(parent, text, fg_color, text_color, font_tuple, win):
    """Create a tk.Text widget that looks like a label but allows text selection
    and right-click copy. The widget auto-sizes to its content."""
    tw = tk.Text(parent, wrap="word", font=font_tuple,
                 bg=fg_color, fg=text_color,
                 relief="flat", borderwidth=0,
                 highlightthickness=0,
                 padx=12, pady=8,
                 cursor="arrow",
                 selectbackground=C["accent"],
                 selectforeground=C["bg"],
                 insertwidth=0,
                 width=1,    # minimal char width — let pack fill="x" control actual width
                 height=1)   # start small, auto-resize below
    tw.insert("1.0", text)
    tw.configure(state="disabled")  # Read-only but selectable

    # Track previous width to avoid redundant resizes
    _prev_width = [0]

    # Auto-height: count display lines (accounts for word-wrap) and resize
    def _resize(event=None):
        try:
            # Only recalc if widget width actually changed
            cur_w = tw.winfo_width()
            if cur_w == _prev_width[0] and _prev_width[0] > 1:
                return
            _prev_width[0] = cur_w

            tw.configure(state="normal")
            tw.update_idletasks()
            # count "displaylines" returns wrapped line count
            display_lines = tw.count("1.0", "end", "displaylines")
            if display_lines is None:
                # Fallback to logical line count
                display_lines = int(tw.index("end-1c").split(".")[0])
            else:
                # count() returns a tuple in some Tk versions
                if isinstance(display_lines, (tuple, list)):
                    display_lines = display_lines[0]
                display_lines = max(1, display_lines)
            tw.configure(height=display_lines)
            tw.configure(state="disabled")
        except Exception:
            pass

    tw.bind("<Configure>", _resize)
    tw.after(10, _resize)
    # Second delayed resize to catch late geometry updates
    tw.after(100, _resize)

    # Right-click context menu
    ctx_menu = tk.Menu(tw, tearoff=0, bg=C["card"], fg=C["text"],
                       activebackground=C["accent"], activeforeground=C["bg"],
                       font=("Segoe UI", 10))
    ctx_menu.add_command(label="Copy", command=lambda: _copy_selected_or_all(tw, win))
    ctx_menu.add_command(label="Copy All", command=lambda: _copy_to_clipboard(win, text))

    def _show_context_menu(event):
        try:
            ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            ctx_menu.grab_release()

    tw.bind("<Button-3>", _show_context_menu)

    # Allow selection with mouse even though state is disabled
    def _on_button1(event):
        tw.configure(state="normal")
        tw.focus_set()
        # Let the default handler process the click for selection
        tw.after(1, lambda: tw.configure(state="disabled"))

    # Enable selection: temporarily set state to normal for mouse events
    def _enable_select(event):
        tw.configure(state="normal")

    def _disable_select(event):
        tw.after(50, lambda: tw.configure(state="disabled"))

    tw.bind("<ButtonPress-1>", _enable_select, add=True)
    tw.bind("<ButtonRelease-1>", _disable_select, add=True)
    tw.bind("<B1-Motion>", lambda e: None)  # allow drag selection

    return tw


def _copy_selected_or_all(tw, win):
    """Copy selected text, or all text if nothing is selected."""
    try:
        sel = tw.get(tk.SEL_FIRST, tk.SEL_LAST)
        _copy_to_clipboard(win, sel)
    except tk.TclError:
        # No selection — copy all
        _copy_to_clipboard(win, tw.get("1.0", "end-1c"))


def _add_bubble(win, role, text):
    chat_frame = win._chat_frame
    is_user = (role == "user")
    bubble_fg = C["card"] if is_user else C["surface"]
    text_color = C["text"] if is_user else C["green"]
    anchor = "e" if is_user else "w"
    padx_l = (60, 10) if is_user else (10, 60)

    family, size = _get_chat_font()

    wrapper = ctk.CTkFrame(chat_frame, fg_color="transparent")
    wrapper.pack(fill="x", pady=(4, 2), padx=6)

    role_row = ctk.CTkFrame(wrapper, fg_color="transparent")
    role_row.pack(fill="x", padx=padx_l)

    role_text = "You" if is_user else _get_role_label()
    role_color = C["muted"] if is_user else _get_role_color()

    ctk.CTkLabel(role_row, text=role_text, font=("Segoe UI", 10),
                 text_color=role_color, anchor="w").pack(side="left")

    copy_btn = ctk.CTkButton(role_row, text="[copy]", width=40, height=18,
                              font=("Segoe UI", 9), fg_color="transparent",
                              text_color=C["muted"], hover_color=C["card_alt"],
                              corner_radius=4,
                              command=lambda t=text: _copy_to_clipboard(win, t))
    copy_btn.pack(side="left", padx=(6, 0))
    wrapper._copy_btn = copy_btn

    bubble = ctk.CTkFrame(wrapper, fg_color=bubble_fg, corner_radius=10,
                           border_width=1, border_color=C["border"])
    bubble.pack(anchor=anchor, padx=padx_l, pady=(2, 0), fill="x")

    # Selectable text widget instead of CTkLabel
    tw = _create_selectable_text(bubble, text, bubble_fg, text_color,
                                  (family, size), win)
    tw.pack(fill="x", expand=True)

    bubble._text_widget = tw
    bubble._wrapper = wrapper
    return bubble


def _add_streaming_bubble(win):
    chat_frame = win._chat_frame
    family, size = _get_chat_font()

    wrapper = ctk.CTkFrame(chat_frame, fg_color="transparent")
    wrapper.pack(fill="x", pady=(4, 2), padx=6)

    role_row = ctk.CTkFrame(wrapper, fg_color="transparent")
    role_row.pack(fill="x", padx=(10, 60))

    ctk.CTkLabel(role_row, text=_get_role_label(),
                 font=("Segoe UI", 10), text_color=_get_role_color(),
                 anchor="w").pack(side="left")

    copy_btn = ctk.CTkButton(role_row, text="[copy]", width=40, height=18,
                              font=("Segoe UI", 9), fg_color="transparent",
                              text_color=C["muted"], hover_color=C["card_alt"],
                              corner_radius=4, command=lambda: None)
    copy_btn.pack(side="left", padx=(6, 0))
    wrapper._copy_btn = copy_btn

    bubble = ctk.CTkFrame(wrapper, fg_color=C["surface"], corner_radius=10,
                           border_width=1, border_color=C["border"])
    bubble.pack(anchor="w", padx=(10, 60), pady=(2, 0), fill="x")

    # Use a CTkLabel for streaming (will be replaced with selectable text when done)
    label = ctk.CTkLabel(bubble, text="...", font=(family, size),
                          text_color=C["green"], wraplength=400,
                          justify="left", anchor="w", padx=12, pady=8)
    label.pack(fill="x")

    bubble._label = label
    bubble._wrapper = wrapper
    return bubble, label, copy_btn


def _replace_label_with_selectable(win, bubble, label, final_text):
    """After streaming is done, replace the CTkLabel with a selectable Text widget."""
    try:
        family, size = _get_chat_font()
        label.destroy()
        tw = _create_selectable_text(bubble, final_text, C["surface"], C["green"],
                                      (family, size), win)
        tw.pack(fill="x", expand=True)
        bubble._text_widget = tw
    except Exception:
        pass


def _scroll_to_bottom(win):
    try:
        win._chat_frame._parent_canvas.yview_moveto(1.0)
    except Exception:
        pass


def _send_message(win, text):
    global _chat_history

    _add_bubble(win, "user", text)
    _chat_history.append({"role": "user", "content": text})
    win._save_current_session()
    _scroll_to_bottom(win)

    win._entry.configure(state="disabled")
    win._send_btn.configure(state="disabled")

    bubble, label, copy_btn = _add_streaming_bubble(win)
    _scroll_to_bottom(win)

    def _stream():
        from services.ai.ollama import chat_ollama, check_ollama

        if not check_ollama():
            _update_label(win, label, "Ollama is not running. Start it with: ollama serve")
            _re_enable(win)
            return

        chunks = []

        def on_token(chunk):
            chunks.append(chunk)
            full = "".join(chunks)
            try:
                win.after(0, lambda t=full: _update_label(win, label, t))
            except Exception:
                pass

        try:
            full_response = chat_ollama(
                _chat_history,
                on_token=on_token,
                mode=_current_mode
            )
            _chat_history.append({"role": "assistant", "content": full_response})
            win._save_current_session()
            try:
                # Replace streaming label with selectable text widget
                win.after(0, lambda r=full_response: (
                    _replace_label_with_selectable(win, bubble, label, r),
                    copy_btn.configure(
                        command=lambda t=r: _copy_to_clipboard(win, t)
                    ),
                    _check_auto_compress(win)
                ))
            except Exception:
                pass
        except Exception as e:
            err_msg = "Error: " + str(e)[:100]
            try:
                win.after(0, lambda: _update_label(win, label, err_msg))
            except Exception:
                pass

        _re_enable(win)

    threading.Thread(target=_stream, daemon=True).start()


def _update_label(win, label, text):
    try:
        label.configure(text=text)
        _scroll_to_bottom(win)
    except Exception:
        pass


def _re_enable(win):
    try:
        win.after(0, lambda: (
            win._entry.configure(state="normal"),
            win._send_btn.configure(state="normal"),
            win._entry.focus(),
        ))
    except Exception:
        pass


def _rebuild_chat_ui(win):
    _clear_chat(win)
    for msg in _chat_history:
        _add_bubble(win, msg["role"], msg["content"])
    _scroll_to_bottom(win)

def _clear_chat(win):
    for widget in win._chat_frame.winfo_children():
        widget.destroy()

def _check_auto_compress(win):
    global _chat_history
    total_chars = sum(len(m.get("content", "")) for m in _chat_history)
    # Context window is ~4096 tokens, ~16k chars. We summarize when > 12000 chars.
    if total_chars > 12000:
        if hasattr(win, "_compress_context"):
            win._compress_context()
