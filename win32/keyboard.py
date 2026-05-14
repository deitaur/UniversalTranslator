"""
Win32 keyboard input simulation
"""

import ctypes
import ctypes.wintypes
import time

# Constants
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

# Structs
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class INPUT(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT_STRUCT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT)]

user32 = ctypes.windll.user32

def _mk(vk, flags=0, scan=0):
    i = INPUT_STRUCT()
    i.type = INPUT_KEYBOARD
    i.union.ki.wVk = vk
    i.union.ki.wScan = scan
    i.union.ki.dwFlags = flags
    return i

def _wait_for_modifiers_release(timeout=1.5):
    """Wait until the user physically releases Ctrl, Alt, Shift keys."""
    start = time.time()
    while time.time() - start < timeout:
        ctrl = user32.GetAsyncKeyState(0x11) & 0x8000
        alt = user32.GetAsyncKeyState(0x12) & 0x8000
        shift = user32.GetAsyncKeyState(0x10) & 0x8000
        if not (ctrl or alt or shift):
            return True
        time.sleep(0.02)
    # Timeout: force-release via keybd_event
    for vk in (0x11, 0x12, 0x10):  # Ctrl, Alt, Shift
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    return False

def has_caret():
    """Check if the focused window has a text caret (= editable field)."""
    import ctypes.wintypes

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("hwndActive", ctypes.wintypes.HWND),
            ("hwndFocus", ctypes.wintypes.HWND),
            ("hwndCapture", ctypes.wintypes.HWND),
            ("hwndMenuOwner", ctypes.wintypes.HWND),
            ("hwndMoveSize", ctypes.wintypes.HWND),
            ("hwndCaret", ctypes.wintypes.HWND),
            ("rcCaret", ctypes.wintypes.RECT),
        ]

    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(0, ctypes.byref(gti)):
        # hwndCaret != 0 means there's a caret → editable field
        return bool(gti.hwndCaret)
    return False

def send_ctrl_c():
    """Send Ctrl+C using keybd_event (more reliable than SendInput for hotkeys)."""
    _wait_for_modifiers_release()
    user32.keybd_event(0x11, 0, 0, 0)           # Ctrl down
    time.sleep(0.01)
    user32.keybd_event(0x43, 0, 0, 0)           # C down
    time.sleep(0.01)
    user32.keybd_event(0x43, 0, KEYEVENTF_KEYUP, 0)  # C up
    time.sleep(0.01)
    user32.keybd_event(0x11, 0, KEYEVENTF_KEYUP, 0)  # Ctrl up
    time.sleep(0.2)

def send_ctrl_v():
    """Send Ctrl+V using keybd_event."""
    _wait_for_modifiers_release()
    user32.keybd_event(0x11, 0, 0, 0)           # Ctrl down
    time.sleep(0.01)
    user32.keybd_event(0x56, 0, 0, 0)           # V down
    time.sleep(0.01)
    user32.keybd_event(0x56, 0, KEYEVENTF_KEYUP, 0)  # V up
    time.sleep(0.01)
    user32.keybd_event(0x11, 0, KEYEVENTF_KEYUP, 0)  # Ctrl up
    time.sleep(0.2)

def type_unicode_text(text):
    """Type text directly via Unicode SendInput events (no clipboard needed)."""
    for ch in text:
        code = ord(ch)
        if ch == "\n":
            inputs = (INPUT_STRUCT * 2)(_mk(0x0D, 0), _mk(0x0D, KEYEVENTF_KEYUP))
            user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT_STRUCT))
        else:
            down = INPUT_STRUCT()
            down.type = INPUT_KEYBOARD
            down.union.ki.wVk = 0
            down.union.ki.wScan = code
            down.union.ki.dwFlags = KEYEVENTF_UNICODE
            up = INPUT_STRUCT()
            up.type = INPUT_KEYBOARD
            up.union.ki.wVk = 0
            up.union.ki.wScan = code
            up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            inputs = (INPUT_STRUCT * 2)(down, up)
            user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT_STRUCT))
        time.sleep(0.005)