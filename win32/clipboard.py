"""
Win32 clipboard operations
"""

import ctypes
import ctypes.wintypes

# Setup ctypes
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_bool
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p

def get_clipboard_text():
    """Get text from clipboard. Retries if clipboard is locked."""
    CF_UNICODETEXT = 13
    import time
    for attempt in range(20):
        if user32.OpenClipboard(0):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)  # clipboard locked by another app, retry
    return ""

def set_clipboard_text(text):
    """Set text to clipboard. Retries if clipboard is locked."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    import time
    
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)
        
    encoded = text.encode("utf-16-le") + b"\x00\x00"
    for attempt in range(20):
        if user32.OpenClipboard(0):
            try:
                user32.EmptyClipboard()
                h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                ptr = kernel32.GlobalLock(h)
                ctypes.memmove(ptr, encoded, len(encoded))
                kernel32.GlobalUnlock(h)
                if not user32.SetClipboardData(CF_UNICODETEXT, h):
                    kernel32.GlobalFree(h)   # OS does NOT own the handle on failure
                    return False
                return True   # OS now owns h — do not free
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)  # clipboard locked, retry
    return False