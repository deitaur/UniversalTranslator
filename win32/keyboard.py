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

def _send_combo(vk_modifier: int, vk_key: int):
    """Press modifier+key via SendInput, then release both."""
    inputs = (INPUT_STRUCT * 4)(
        _mk(vk_modifier, 0),
        _mk(vk_key,      0),
        _mk(vk_key,      KEYEVENTF_KEYUP),
        _mk(vk_modifier, KEYEVENTF_KEYUP),
    )
    user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT_STRUCT))


def send_ctrl_c():
    """Copy selection to clipboard via SendInput (works in Electron/browser/UWP)."""
    from config import config
    if config.get("remote_session_mode", False):
        return  # Skip keyboard operations in remote mode
    _wait_for_modifiers_release()
    time.sleep(0.05)   # brief settle after modifiers released
    _send_combo(0x11, 0x43)   # Ctrl+C
    time.sleep(0.25)          # wait for clipboard to be written


def get_foreground_hwnd() -> int:
    """Return the current foreground window handle (HWND as int)."""
    return user32.GetForegroundWindow()


def restore_foreground(hwnd: int) -> bool:
    """Bring `hwnd` back to the foreground.

    Windows blocks SetForegroundWindow from non-foreground processes; the
    documented workaround is to press a key first (the OS treats that as
    user activity and grants our process foreground rights for one call).
    Returns True on success."""
    from config import config
    if not hwnd:
        return False
    if config.get("remote_session_mode", False):
        return False  # Skip in remote mode - Alt press can interfere
    try:
        # Tap Alt to gain SetForegroundWindow privilege for the next call.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def send_ctrl_v(skip_wait: bool = False):
    """Paste from clipboard via SendInput.
    skip_wait=True skips modifier-release wait (safe when called after a long operation
    like a translation API call, since keys are definitely released by then)."""
    from config import config
    if config.get("remote_session_mode", False):
        return  # Skip keyboard operations in remote mode
    if not skip_wait:
        _wait_for_modifiers_release()
    time.sleep(0.05)
    _send_combo(0x11, 0x56)   # Ctrl+V
    time.sleep(0.15)

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