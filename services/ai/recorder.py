"""
Shared audio recording infrastructure for all voice pipelines.

Single responsibility:
  - AudioSession  — one recording session with its own cancellation token
  - Pipeline mutex — ensures only one pipeline records at a time
  - Whisper model  — thread-safe singleton loader
  - Click hook     — mouse-click → stop current session
  - Audio validation

Usage:
    with AudioSession(max_seconds=120) as session:
        start_click_hook(session.stop_event)
        audio = session.record()
        err = session.validate(audio)
        ...
"""

import threading
import time
import logging

import numpy as np

log = logging.getLogger("recorder")

SAMPLE_RATE = 16000
BLOCK_SIZE  = 1024
MIN_RMS     = 0.008
MIN_SECONDS = 0.5


# ── Whisper model — loaded once, thread-safe ──────────────────────────────────

_model_lock    = threading.Lock()
_whisper_model = None


def load_whisper_model():
    """Return the shared Whisper model, loading it on the first call (thread-safe)."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _model_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            from services.ai.whisper import WHISPER_MODEL_ID
            log.info("Loading Whisper model %s…", WHISPER_MODEL_ID)
            _whisper_model = WhisperModel(
                WHISPER_MODEL_ID, device="cpu", compute_type="int8"
            )
    return _whisper_model


# ── Pipeline mutex — only one audio session at a time ─────────────────────────

_pipeline_lock = threading.Lock()
_active_stop:  "threading.Event | None" = None
_active_guard  = threading.Lock()   # guards _active_stop pointer


def stop_active():
    """Stop whichever pipeline is currently recording. Safe to call from any thread."""
    with _active_guard:
        if _active_stop is not None:
            _active_stop.set()


def is_recording() -> bool:
    """True if a pipeline currently holds the lock."""
    return _pipeline_lock.locked()


# ── AudioSession ──────────────────────────────────────────────────────────────

class AudioSession:
    """
    Lifecycle of one recording session. Use as a context manager:

        with AudioSession(max_seconds=120) as session:
            ...

    Entering raises RuntimeError if another pipeline is already running.
    Exiting always releases the mutex and unblocks the click hook.
    """

    def __init__(self, max_seconds: int = 120):
        self._max_seconds = max_seconds
        self.stop_event   = threading.Event()
        self._chunks: list = []

    # ── Context manager ──

    def __enter__(self) -> "AudioSession":
        if not _pipeline_lock.acquire(blocking=False):
            raise RuntimeError("another pipeline is already recording")
        with _active_guard:
            global _active_stop
            _active_stop = self.stop_event
        return self

    def __exit__(self, *_):
        with _active_guard:
            global _active_stop
            _active_stop = None
        try:
            _pipeline_lock.release()
        except RuntimeError:
            pass
        self.stop_event.set()   # unblock any lingering click-hook thread

    def stop(self):
        self.stop_event.set()

    # ── Recording ──

    def record(self) -> "np.ndarray | None":
        """
        Block until stop_event, click, or max_seconds elapsed.
        Returns float32 mono audio array, or None if nothing was captured.
        """
        import sounddevice as sd

        self._chunks.clear()

        def _cb(indata, frames, t, status):
            self._chunks.append(indata.copy())

        with sd.InputStream(callback=_cb, channels=1,
                            samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE):
            t0 = time.time()
            while not self.stop_event.is_set():
                if (time.time() - t0) >= self._max_seconds:
                    break
                time.sleep(0.05)

        if not self._chunks:
            return None
        return np.concatenate(self._chunks, axis=0).flatten()

    # ── Validation ──

    def validate(self, audio: np.ndarray) -> "str | None":
        """
        Return None if audio is usable speech, else a human-readable error string.
        """
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_SECONDS:
            return "Слишком короткая запись — говорите дольше"
        rms = float(np.sqrt(np.mean(audio ** 2)))
        log.debug("Audio RMS=%.4f  duration=%.1fs", rms, duration)
        if rms < MIN_RMS:
            return "Ничего не слышно — говорите громче или выберите другой микрофон"
        return None


# ── Mouse-click hook ──────────────────────────────────────────────────────────

def start_click_hook(stop_event: threading.Event) -> threading.Thread:
    """Spawn a daemon thread that sets stop_event on any mouse button press."""
    t = threading.Thread(target=_click_hook_loop, args=(stop_event,), daemon=True)
    t.start()
    return t


def _click_hook_loop(stop_event: threading.Event):
    import ctypes
    import ctypes.wintypes

    WH_MOUSE_LL    = 14
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204

    HOOKPROC = ctypes.CFUNCTYPE(
        ctypes.c_long, ctypes.c_int,
        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    )
    user32 = ctypes.windll.user32

    def _cb(nCode, wParam, lParam):
        if nCode >= 0 and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            stop_event.set()
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    ref  = HOOKPROC(_cb)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ref, None, 0)
    msg  = ctypes.wintypes.MSG()
    while not stop_event.is_set():
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    user32.UnhookWindowsHookEx(hook)
    del ref
