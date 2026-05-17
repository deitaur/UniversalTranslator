"""Per-WebSocket connection session state."""
import time
import uuid


class BridgeSession:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.mode = "negotiator"
        self.lang = "ru"
        self.history: list[dict] = []
        self.created_at = time.time()
        self.audio_buffer = bytearray()
        self.interrupted = False

    def reset_audio(self):
        self.audio_buffer = bytearray()
        self.interrupted = False

    def add_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def get_history(self, max_messages: int = 20) -> list[dict]:
        return self.history[-max_messages:]

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.created_at
