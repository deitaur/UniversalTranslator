"""
Win32 single instance mutex
"""

import ctypes
import ctypes.wintypes

kernel32 = ctypes.windll.kernel32

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = ctypes.c_uint
kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
kernel32.ReleaseMutex.restype = ctypes.c_bool
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool

def check_single_instance(app_name="UniversalTranslator"):
    """Check if another instance is running using a mutex."""
    mutex = kernel32.CreateMutexW(None, False, app_name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False, None
    return True, mutex

def release_mutex(mutex):
    """Release the mutex."""
    if mutex:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)