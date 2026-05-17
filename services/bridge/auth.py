"""Bridge authentication — single shared token stored in config."""
import hashlib
import hmac
import secrets


def get_or_create_token() -> str:
    """Return the bridge token, creating one if absent."""
    from config import config, save_config_full
    token = config.get("bridge_token", "")
    if not token:
        token = secrets.token_urlsafe(32)
        config["bridge_token"] = token
        save_config_full()
    return token


def validate_token(provided: str) -> bool:
    if not provided:
        return False
    expected = get_or_create_token()
    return hmac.compare_digest(
        hashlib.sha256(provided.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )
