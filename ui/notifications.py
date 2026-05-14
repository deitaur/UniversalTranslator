"""
Toast notifications — lightweight popups near the mouse cursor.
Uses plain tkinter (not customtkinter) to avoid conflicts with
CTk() root windows running in other threads.
"""

import ctypes
import logging
import traceback
import threading
import tkinter as tk

log = logging.getLogger("notifications")

# Catppuccin Mocha palette (duplicated here to avoid circular imports)
_BG       = "#1e1e2e"
_SURFACE  = "#313244"
_BORDER   = "#585b70"
_ACCENT   = "#89b4fa"
_TEXT     = "#cdd6f4"
_MUTED    = "#6c7086"

# Win32 constants for non-activating windows
_GWL_EXSTYLE       = -20
_WS_EX_NOACTIVATE  = 0x08000000
_WS_EX_TOOLWINDOW  = 0x00000080


def _make_noactivate(root):
    """Prevent the toast window from stealing keyboard focus."""
    try:
        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                              style | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
    except Exception as ex:
        log.debug("_make_noactivate failed: %s", ex)


def show_toast(message, duration_ms=2000):
    """Display a small temporary pop-up notification near the cursor."""
    def _run():
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.95)
            root.configure(bg=_BG)
            root.withdraw()  # hide until positioned

            cx, cy = root.winfo_pointerx(), root.winfo_pointery()
            root.geometry(f"+{cx + 20}+{cy - 40}")

            frame = tk.Frame(root, bg=_SURFACE, bd=1, relief="solid",
                             highlightbackground=_BORDER, highlightthickness=1)
            frame.pack(padx=2, pady=2)
            tk.Label(frame, text=message, fg=_TEXT, bg=_SURFACE,
                     font=("Segoe UI", 13), padx=16, pady=10).pack()

            root.update_idletasks()
            _make_noactivate(root)
            root.deiconify()  # show

            def fade_out(alpha=0.95):
                alpha -= 0.05
                if alpha <= 0:
                    root.destroy()
                    return
                root.attributes("-alpha", alpha)
                root.after(30, fade_out, alpha)

            root.after(duration_ms, fade_out)
            root.mainloop()
        except Exception as e:
            log.error("show_toast error: %s\n%s", e, traceback.format_exc())
    threading.Thread(target=_run, daemon=True).start()


def show_translation_toast(message, duration_ms=5000):
    """Display a larger popup for showing full translation text near cursor."""
    def _run():
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.95)
            root.configure(bg=_BG)
            root.withdraw()  # hide until positioned

            # Position near cursor but ensure it fits on screen
            cx, cy = root.winfo_pointerx(), root.winfo_pointery()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            max_w = min(500, sw - 40)
            x = min(cx + 20, sw - max_w - 20)
            y = max(cy - 60, 40)
            root.geometry(f"+{x}+{y}")

            frame = tk.Frame(root, bg=_SURFACE, bd=1, relief="solid",
                             highlightbackground=_ACCENT, highlightthickness=2)
            frame.pack(padx=2, pady=2)

            # Header — NOTE: pady must be an int in Label; use pack() for tuples
            header = tk.Label(frame, text="Translation", fg=_ACCENT, bg=_SURFACE,
                              font=("Segoe UI Semibold", 10), padx=12,
                              anchor="w")
            header.pack(fill="x", pady=(6, 0))

            # Translation text — wrapping label
            label = tk.Label(frame, text=message, fg=_TEXT, bg=_SURFACE,
                             font=("Segoe UI", 13), padx=16,
                             wraplength=max_w - 40, justify="left", anchor="w")
            label.pack(fill="x", pady=(4, 12))

            # Copied indicator
            hint = tk.Label(frame, text="copied to clipboard  •  click to close",
                            fg=_MUTED, bg=_SURFACE,
                            font=("Segoe UI", 9), padx=12, anchor="w")
            hint.pack(fill="x", pady=(0, 6))

            # Adjust position if window goes off bottom of screen
            root.update_idletasks()
            wh = root.winfo_reqheight()
            if y + wh > sh - 40:
                y = sh - wh - 40
                root.geometry(f"+{x}+{y}")

            # ── Critical: prevent toast from stealing keyboard focus ──
            _make_noactivate(root)

            root.deiconify()  # show after positioning
            log.debug("Translation toast shown at (%d, %d), duration=%dms", x, y, duration_ms)

            # Click to dismiss
            def _dismiss(e=None):
                try:
                    root.destroy()
                except Exception:
                    pass

            for w in (root, frame, label, header, hint):
                w.bind("<Button-1>", _dismiss)

            # Escape to dismiss
            root.bind("<Escape>", _dismiss)

            def fade_out(alpha=0.95):
                try:
                    alpha -= 0.05
                    if alpha <= 0:
                        root.destroy()
                        return
                    root.attributes("-alpha", alpha)
                    root.after(30, fade_out, alpha)
                except Exception:
                    pass

            root.after(duration_ms, fade_out)
            root.mainloop()
        except Exception as e:
            log.error("show_translation_toast error: %s\n%s", e, traceback.format_exc())
    threading.Thread(target=_run, daemon=True).start()
