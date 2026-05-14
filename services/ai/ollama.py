"""
Ollama local LLM integration.
Supports custom roles with RAG material search.
"""

import json
import datetime
import requests
from config import config, CONFIG_DIR

OLLAMA_URL = "http://localhost:11434/api/chat"

_LANG_INSTRUCTIONS = {
    "English": "\n\nALWAYS respond in English, regardless of input language.",
    "Russian": "\n\nALWAYS respond in Russian, regardless of input language.",
    "Same as input": "\n\nRespond in the same language as the user's input.",
}

PROGRESS_FILE = CONFIG_DIR / "teacher_progress.json"


def _load_progress():
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "level": "beginner",
        "sessions_count": 0,
        "topics_covered": [],
        "vocabulary": [],
        "grammar_points": [],
        "last_session": None,
        "notes": "",
    }


def _save_progress(progress):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def update_progress_from_response(response_text):
    progress = _load_progress()
    progress["sessions_count"] += 1
    progress["last_session"] = datetime.datetime.now().isoformat()
    _save_progress(progress)


def _get_system_prompt(mode="negotiator"):
    """Build system prompt for the given role/mode."""
    from storage.roles import get_role

    lang = config.get("negotiator_lang", "Same as input")
    lang_suffix = _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["Same as input"])

    role = get_role(mode)
    if role:
        prompt = role.get("system_prompt", "You are a helpful assistant.")
        # For teacher, append progress
        if mode == "teacher":
            progress = _load_progress()
            progress_str = json.dumps(progress, indent=2, ensure_ascii=False)
            prompt = prompt + "\n\nPROGRESS INFO:\n" + progress_str
        return prompt + lang_suffix
    else:
        return "You are a helpful assistant." + lang_suffix


def get_ollama_model():
    return config.get("ollama_model", "qwen2.5:14b")


def check_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def chat_ollama(messages, on_token=None, mode="negotiator"):
    from services.ai.rag_engine import search_materials

    model = get_ollama_model()
    system_prompt = _get_system_prompt(mode)

    # RAG: search materials for relevant context based on last user message
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    if last_user_msg:
        rag_context = search_materials(mode, last_user_msg)
        if rag_context:
            system_prompt = system_prompt + "\n\n--- REFERENCE MATERIALS ---\n" + rag_context + "\n--- END MATERIALS ---"

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    body = {
        "model": model,
        "messages": full_messages,
        "stream": on_token is not None,
    }

    # Add options (num_ctx and num_predict to avoid cutoff)
    num_ctx = config.get("ollama_num_ctx", 4096)
    
    body["options"] = {
        "num_ctx": int(num_ctx) if num_ctx else 4096,
        "num_predict": 4096  # Allow up to 4096 tokens in the response
    }

    if on_token:
        full_text = []
        r = requests.post(OLLAMA_URL, json=body, timeout=120, stream=True)
        r.raise_for_status()
        r.encoding = 'utf-8'  # Force UTF-8 — prevents Cyrillic garbling
        for line in r.iter_lines(decode_unicode=True):
            if line:
                data = json.loads(line)
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    full_text.append(chunk)
                    on_token(chunk)
                if data.get("done"):
                    break
        result = "".join(full_text)
        if mode == "teacher":
            update_progress_from_response(result)
        return result
    else:
        r = requests.post(OLLAMA_URL, json=body, timeout=120)
        r.raise_for_status()
        r.encoding = 'utf-8'  # Force UTF-8 — prevents Cyrillic garbling
        data = r.json()
        result = data.get("message", {}).get("content", "")
        if mode == "teacher":
            update_progress_from_response(result)
        return result


def preload_model():
    """Load model into memory without generating a response."""
    model = get_ollama_model()
    try:
        url = "http://localhost:11434/api/generate"
        body = {
            "model": model,
            "keep_alive": "60m"
        }
        requests.post(url, json=body, timeout=120)
        return True
    except Exception:
        return False
