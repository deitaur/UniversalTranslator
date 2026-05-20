"""Win32 screen-geometry helpers — safe to call from any thread."""

import ctypes


def _win32_cursor() -> tuple[int, int]:
    """Cursor position via Win32 — safe from any thread."""
    class _P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = _P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _screen_w() -> int:
    return ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN


def _work_area() -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the desktop work area (screen minus taskbar)."""
    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rc = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)  # SPI_GETWORKAREA
    return rc.left, rc.top, rc.right, rc.bottom
