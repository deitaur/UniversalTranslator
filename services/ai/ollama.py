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


def _stream_response(messages, body_base, on_token):
    """Stream a response from Ollama, return full text."""
    body = {**body_base, "messages": messages, "stream": True}
    body.pop("tools", None)  # no tools on final streaming call
    full_text = []
    r = requests.post(OLLAMA_URL, json=body, timeout=120, stream=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    for line in r.iter_lines(decode_unicode=True):
        if line:
            data = json.loads(line)
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                full_text.append(chunk)
                on_token(chunk)
            if data.get("done"):
                break
    return "".join(full_text)


def _non_stream_response(messages, body_base):
    """Single non-streaming call, returns (content, tool_calls)."""
    body = {**body_base, "messages": messages, "stream": False}
    r = requests.post(OLLAMA_URL, json=body, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    data = r.json()
    msg = data.get("message", {})
    return msg.get("content", ""), msg.get("tool_calls", []), msg


def chat_ollama(messages, on_token=None, on_status=None, mode="negotiator"):
    """
    Chat with Ollama.  Supports tool calling (web_search).
    on_token(chunk: str)  — called per streaming token
    on_status(text: str)  — called with status like "🔍 Searching…"
    """
    from services.ai.rag_engine import search_materials
    from services.ai.web_search import search as web_search, WEB_SEARCH_TOOL

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
            system_prompt += "\n\n--- REFERENCE MATERIALS ---\n" + rag_context + "\n--- END MATERIALS ---"

    num_ctx = config.get("ollama_num_ctx", 4096)
    body_base = {
        "model": model,
        "options": {
            "num_ctx": int(num_ctx) if num_ctx else 4096,
            "num_predict": 4096,
        },
        "tools": [WEB_SEARCH_TOOL],
    }

    working = [{"role": "system", "content": system_prompt}] + list(messages)

    # ── Tool-calling loop (max 3 rounds to prevent runaway) ──────────────────
    MAX_ROUNDS = 3
    for _round in range(MAX_ROUNDS):
        content, tool_calls, raw_msg = _non_stream_response(working, body_base)

        if not tool_calls:
            # No tool calls — deliver final response
            if on_status:
                on_status("")  # clear status
            if on_token:
                # Re-stream so the caller gets live tokens
                working.append({"role": "assistant", "content": content})
                # Ask to regenerate with streaming (drop tools to avoid loop)
                working_no_tools = working[:-1]  # remove the assistant echo
                result = _stream_response(working_no_tools, body_base, on_token)
            else:
                result = content
            if mode == "teacher":
                update_progress_from_response(result)
            return result

        # Execute tool calls
        working.append(raw_msg)   # assistant message with tool_calls
        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}

            if fn_name == "web_search":
                query = fn_args.get("query", "")
                label = query[:45] + ("…" if len(query) > 45 else "")
                if on_status:
                    on_status(f"🔍 Searching: {label}")
                result_text = web_search(query)
                working.append({"role": "tool", "content": result_text})
            else:
                working.append({"role": "tool", "content": f"Unknown tool: {fn_name}"})

    # Fallback if loop exhausted without a final answer
    if on_status:
        on_status("")
    if on_token:
        result = _stream_response(working, body_base, on_token)
    else:
        content, _, _ = _non_stream_response(working, body_base)
        result = content
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
