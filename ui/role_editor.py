"""
Role Editor window -- create, edit, delete AI roles.
Opened from Settings -> Manage Roles.
Uses raw tkinter.Text for the system prompt to avoid encoding issues
with Cyrillic text in CTkTextbox.
"""

import os
import tkinter as tk
import threading
import customtkinter as ctk
from tkinter import filedialog
from config import APP_NAME, ICON_FILE, C


def show_role_editor():
    """Open the Role Editor window."""
    def _run():
        from storage.roles import (load_roles, create_role, delete_role,
                                   update_role, get_materials_folder, list_materials)

        ctk.set_appearance_mode("dark")
        win = ctk.CTk()
        win.title(APP_NAME + " - Role Manager")
        win.geometry("750x580")
        win.minsize(650, 480)
        win.attributes("-topmost", True)
        win.configure(fg_color=C["bg"])

        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        roles = load_roles()
        selected_role_id = [None]

        # ── Header ──
        hdr = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Role Manager", font=("Segoe UI Semibold", 18),
                     text_color=C["text"]).pack(side="left", padx=18, pady=10)

        # ── Main body: left list + right editor ──
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel: role list
        left = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10,
                             border_width=1, border_color=C["border"], width=200)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="Roles", font=("Segoe UI Semibold", 13),
                     text_color=C["text"]).pack(padx=10, pady=(10, 6), anchor="w")

        role_list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        role_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=6, pady=(0, 8))

        # Right panel: editor
        right = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10,
                              border_width=1, border_color=C["border"])
        right.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(right, text="Role Name:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(padx=14, pady=(12, 2), anchor="w")

        # Use raw tk.Entry for the name to avoid Cyrillic encoding issues
        name_frame = ctk.CTkFrame(right, fg_color="transparent")
        name_frame.pack(padx=14, fill="x")
        name_entry = tk.Entry(name_frame, font=("Segoe UI", 13),
                               bg=C["card_alt"], fg=C["text"],
                               insertbackground=C["text"],
                               relief="flat", borderwidth=0,
                               highlightthickness=1,
                               highlightcolor=C["accent"],
                               highlightbackground=C["border"])
        name_entry.pack(fill="x", ipady=6)

        ctk.CTkLabel(right, text="System Prompt:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(padx=14, pady=(10, 2), anchor="w")

        # Use raw tk.Text for the system prompt — CTkTextbox garbles Cyrillic on Windows
        prompt_frame = ctk.CTkFrame(right, fg_color=C["card_alt"], corner_radius=8,
                                     border_width=1, border_color=C["border"])
        prompt_frame.pack(padx=14, fill="both", expand=True)

        prompt_text = tk.Text(prompt_frame, font=("Consolas", 11),
                               bg=C["card_alt"], fg=C["text"],
                               insertbackground=C["text"],
                               relief="flat", borderwidth=0,
                               highlightthickness=0,
                               wrap="word",
                               selectbackground=C["accent"],
                               selectforeground=C["bg"],
                               padx=8, pady=6,
                               undo=True)
        prompt_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Standard Ctrl+V paste (tkinter handles Unicode correctly)
        def _paste_prompt(e):
            try:
                clip = win.clipboard_get()
                if clip:
                    # If there's a selection, replace it
                    try:
                        prompt_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except tk.TclError:
                        pass
                    prompt_text.insert("insert", clip)
            except Exception:
                pass
            return "break"
        prompt_text.bind("<Control-v>", _paste_prompt)
        prompt_text.bind("<Control-V>", _paste_prompt)

        # Ctrl+A select all in prompt
        def _select_all_prompt(e):
            prompt_text.tag_add(tk.SEL, "1.0", "end-1c")
            return "break"
        prompt_text.bind("<Control-a>", _select_all_prompt)
        prompt_text.bind("<Control-A>", _select_all_prompt)

        # Right-click context menu for prompt
        prompt_ctx = tk.Menu(prompt_text, tearoff=0, bg=C["card"], fg=C["text"],
                              activebackground=C["accent"], activeforeground=C["bg"],
                              font=("Segoe UI", 10))
        prompt_ctx.add_command(label="Cut", command=lambda: _cut_prompt())
        prompt_ctx.add_command(label="Copy", command=lambda: _copy_prompt())
        prompt_ctx.add_command(label="Paste", command=lambda: _paste_prompt(None))
        prompt_ctx.add_separator()
        prompt_ctx.add_command(label="Select All", command=lambda: _select_all_prompt(None))

        def _cut_prompt():
            try:
                sel = prompt_text.get(tk.SEL_FIRST, tk.SEL_LAST)
                win.clipboard_clear()
                win.clipboard_append(sel)
                prompt_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass

        def _copy_prompt():
            try:
                sel = prompt_text.get(tk.SEL_FIRST, tk.SEL_LAST)
                win.clipboard_clear()
                win.clipboard_append(sel)
            except tk.TclError:
                pass

        def _show_prompt_ctx(event):
            try:
                prompt_ctx.tk_popup(event.x_root, event.y_root)
            finally:
                prompt_ctx.grab_release()
        prompt_text.bind("<Button-3>", _show_prompt_ctx)

        # Materials section
        mat_frame = ctk.CTkFrame(right, fg_color="transparent")
        mat_frame.pack(fill="x", padx=14, pady=(8, 4))

        ctk.CTkLabel(mat_frame, text="Materials Folder:", font=("Segoe UI", 12),
                     text_color=C["subtext"]).pack(side="left")

        folder_label = ctk.CTkLabel(mat_frame, text="(none)", font=("Segoe UI", 11),
                                     text_color=C["muted"])
        folder_label.pack(side="left", padx=(8, 0))

        def browse_folder():
            win.attributes("-topmost", False)
            folder = filedialog.askdirectory(title="Select Materials Folder", parent=win)
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
            if folder:
                folder_label.configure(text=os.path.basename(folder))
                folder_label._folder_path = folder

        folder_label._folder_path = ""

        ctk.CTkButton(mat_frame, text="Browse", width=70, height=26,
                       font=("Segoe UI", 11), fg_color=C["card_alt"],
                       text_color=C["text"], hover_color=C["border"],
                       corner_radius=6, command=browse_folder).pack(side="right", padx=(4, 0))

        ctk.CTkButton(mat_frame, text="Open", width=60, height=26,
                       font=("Segoe UI", 11), fg_color=C["card_alt"],
                       text_color=C["text"], hover_color=C["border"],
                       corner_radius=6,
                       command=lambda: _open_materials_folder(selected_role_id[0])
                       ).pack(side="right", padx=(4, 0))

        # File list
        files_frame = ctk.CTkFrame(right, fg_color=C["card_alt"], corner_radius=8,
                                    border_width=1, border_color=C["border"], height=80)
        files_frame.pack(padx=14, fill="x", pady=(2, 8))

        files_label = ctk.CTkLabel(files_frame, text="No materials loaded",
                                    font=("Segoe UI", 10), text_color=C["muted"],
                                    wraplength=400, justify="left")
        files_label.pack(padx=8, pady=6, anchor="w")

        # Context size & Options
        options_frame = ctk.CTkFrame(right, fg_color="transparent")
        options_frame.pack(fill="x", padx=14, pady=(0, 4))

        ctk.CTkLabel(options_frame, text="Context tokens (num_ctx):", font=("Segoe UI", 11),
                     text_color=C["subtext"]).pack(side="left")

        ctx_entry = ctk.CTkEntry(options_frame, width=80, font=("Consolas", 11),
                                  text_color=C["text"], fg_color=C["card_alt"],
                                  border_color=C["border"])
        ctx_entry.pack(side="left", padx=(8, 0))

        # Show in tray checkbox
        show_in_tray_var = tk.BooleanVar(value=True)
        tray_check = ctk.CTkCheckBox(options_frame, text="Show in tray menu", variable=show_in_tray_var,
                                     font=("Segoe UI", 11), text_color=C["text"],
                                     fg_color=C["accent"], hover_color="#7ba4e8")
        tray_check.pack(side="right", padx=(0, 8))

        # Save / Delete buttons
        action_row = ctk.CTkFrame(right, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(4, 12))

        def save_current():
            name = name_entry.get().strip()
            prompt = prompt_text.get("1.0", "end-1c").strip()
            mat_folder = getattr(folder_label, "_folder_path", "")
            ctx_val = ctx_entry.get().strip()
            in_tray = show_in_tray_var.get()

            if not name:
                return

            rid = selected_role_id[0]
            if rid:
                success = update_role(rid, name=name, system_prompt=prompt, materials_folder=mat_folder, show_in_tray=in_tray)
                if not success:
                    # Role was somehow deleted in the background, create it anew
                    rid = create_role(name, prompt, materials_folder=mat_folder, show_in_tray=in_tray)
                    selected_role_id[0] = rid
            else:
                rid = create_role(name, prompt, materials_folder=mat_folder, show_in_tray=in_tray)
                selected_role_id[0] = rid

            # Save context size to config
            if ctx_val:
                from config import config, save_config_full
                try:
                    config["ollama_num_ctx"] = int(ctx_val)
                    save_config_full()
                except ValueError:
                    pass

            _refresh_list()

        def delete_current():
            rid = selected_role_id[0]
            if rid:
                ok = delete_role(rid)
                if ok:
                    selected_role_id[0] = None
                    _clear_editor()
                    _refresh_list()

        ctk.CTkButton(action_row, text="Save Role", height=36,
                       font=("Segoe UI Semibold", 13), fg_color=C["accent"],
                       text_color=C["bg"], hover_color="#7ba4e8",
                       corner_radius=8, command=save_current).pack(side="left", expand=True, fill="x", padx=(0, 4))

        delete_btn = ctk.CTkButton(action_row, text="Delete", width=80, height=36,
                                    font=("Segoe UI Semibold", 13), fg_color=C["red"],
                                    text_color=C["bg"], hover_color="#e06080",
                                    corner_radius=8, command=delete_current)
        delete_btn.pack(side="right")

        # ── Functions ──
        def _clear_editor():
            name_entry.delete(0, "end")
            prompt_text.delete("1.0", "end")
            folder_label.configure(text="(none)")
            folder_label._folder_path = ""
            files_label.configure(text="No materials loaded")
            ctx_entry.delete(0, "end")
            from config import config
            ctx_entry.insert(0, str(config.get("ollama_num_ctx", 4096)))
            show_in_tray_var.set(True)
            delete_btn.configure(state="normal")

        def _load_role(role_id):
            selected_role_id[0] = role_id
            roles_now = load_roles()
            role = roles_now.get(role_id, {})
            name_entry.delete(0, "end")
            name_entry.insert(0, role.get("name", ""))
            prompt_text.delete("1.0", "end")
            try:
                prompt_text.insert("1.0", role.get("system_prompt", ""))
            except Exception as e:
                prompt_text.insert("1.0", f"Error loading prompt text: {str(e)}\n\nThe data file may be corrupted.")
                
            mat = role.get("materials_folder", "")
            if mat:
                folder_label.configure(text=os.path.basename(mat))
                folder_label._folder_path = mat
            else:
                folder_label.configure(text="(default)")
                folder_label._folder_path = ""

            show_in_tray_var.set(role.get("show_in_tray", True))

            # Show files
            materials = list_materials(role_id)
            if materials:
                names = [f.name for f in materials[:10]]
                txt = ", ".join(names)
                if len(materials) > 10:
                    txt += " +" + str(len(materials) - 10) + " more"
                files_label.configure(text=txt)
            else:
                files_label.configure(text="No materials - add files to folder")

            from config import config
            ctx_entry.delete(0, "end")
            ctx_entry.insert(0, str(config.get("ollama_num_ctx", 4096)))

            # Disable delete for builtins
            if role.get("builtin"):
                delete_btn.configure(state="disabled")
            else:
                delete_btn.configure(state="normal")

            _highlight_role(role_id)

        role_buttons = {}

        def _highlight_role(active_id):
            for rid, btn in role_buttons.items():
                if rid == active_id:
                    btn.configure(fg_color=C["accent"], text_color=C["bg"])
                else:
                    btn.configure(fg_color=C["card_alt"], text_color=C["text"])

        def _refresh_list():
            nonlocal roles
            roles = load_roles()
            for w in role_list_frame.winfo_children():
                w.destroy()
            role_buttons.clear()
            for rid, rdata in roles.items():
                btn = ctk.CTkButton(
                    role_list_frame, text=rdata.get("name", rid),
                    font=("Segoe UI", 12), height=32,
                    fg_color=C["card_alt"], text_color=C["text"],
                    hover_color=C["border"], corner_radius=6,
                    anchor="w",
                    command=lambda r=rid: _load_role(r),
                )
                btn.pack(fill="x", pady=2, padx=2)
                role_buttons[rid] = btn
            if selected_role_id[0]:
                _highlight_role(selected_role_id[0])

        # New role button
        def _new_role():
            selected_role_id[0] = None
            _clear_editor()
            name_entry.focus()

        ctk.CTkButton(btn_row, text="+ New", height=30,
                       font=("Segoe UI Semibold", 12), fg_color=C["accent"],
                       text_color=C["bg"], hover_color="#7ba4e8",
                       corner_radius=6, command=_new_role).pack(fill="x")

        _refresh_list()
        _clear_editor()

        win.mainloop()

    threading.Thread(target=_run, daemon=True).start()


def _open_materials_folder(role_id):
    """Open the materials folder in file explorer."""
    if not role_id:
        return
    from storage.roles import get_materials_folder
    folder = get_materials_folder(role_id)
    if folder and folder.exists():
        os.startfile(str(folder))
