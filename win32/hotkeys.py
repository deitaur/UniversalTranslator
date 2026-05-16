"""
Win32 hotkey management
"""

import ctypes
import ctypes.wintypes

# Constants
MOD_CTRL = 0x0002
MOD_ALT = 0x0001
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

HOTKEY_POPUP = 1
HOTKEY_REPLACE = 2
HOTKEY_CLIPBOARD = 3
HOTKEY_WHISPER = 4
HOTKEY_NEGOTIATOR = 5
HOTKEY_TEACHER = 6
HOTKEY_DICTATION  = 7
HOTKEY_VOICECHAT  = 8

WM_HOTKEY = 0x0312

VK_NAMES = {
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45, "F": 0x46,
    "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A, "K": 0x4B, "L": 0x4C,
    "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50, "Q": 0x51, "R": 0x52,
    "S": 0x53, "T": 0x54, "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58,
    "Y": 0x59, "Z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
    "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
    "F11": 0x7A, "F12": 0x7B,
}
VK_CODES_TO_NAMES = {v: k for k, v in VK_NAMES.items()}

DEFAULT_HOTKEYS = {
    "popup":      "Ctrl+Alt+T",
    "replace":    "Ctrl+Alt+R",
    "clipboard":  "Ctrl+Alt+Y",
    "whisper":    "Ctrl+Alt+W",
    "negotiator": "Ctrl+Alt+N",
    "teacher":    "Ctrl+Alt+E",
    "dictation":  "Ctrl+Alt+D",
    "voicechat":  "Ctrl+Alt+V",
}

user32 = ctypes.windll.user32

def parse_hotkey_string(s):
    parts = [p.strip() for p in s.upper().split("+")]
    mods = 0
    vk = 0
    for p in parts:
        if p == "CTRL":
            mods |= MOD_CTRL
        elif p == "ALT":
            mods |= MOD_ALT
        elif p == "SHIFT":
            mods |= MOD_SHIFT
        elif p == "WIN":
            mods |= MOD_WIN
        elif p in VK_NAMES:
            vk = VK_NAMES[p]
    return mods, vk

def hotkey_display(name):
    from config import config
    s = config.get(f"hotkey_{name}", DEFAULT_HOTKEYS.get(name, ""))
    return s

def hotkey_mods_vk(name):
    return parse_hotkey_string(hotkey_display(name))

def register_hotkey(id, mods, vk):
    return user32.RegisterHotKey(None, id, mods, vk)

def unregister_hotkey(id):
    return user32.UnregisterHotKey(None, id)
