"""Voice action implementations.

Called from the unified Whisper pipeline after transcription. Each
`apply_*` returns the processed text, or the original on failure.
"""

import json as _json
import logging
import time
from typing import Callable, Optional

import requests

log = logging.getLogger("voice_actions")


# ── Whisper hallucination filter ──────────────────────────────────────────────

_HALLUCINATIONS = {
    "продолжение следует", "спасибо за просмотр", "подпишитесь на канал",
    "до свидания", "thank you for watching", "thanks for watching",
    "please subscribe", "to be continued", "subscribe",
    "[музыка]", "[music]", "[аплодисменты]", "[applause]",
}


def is_hallucination(text: str) -> bool:
    cleaned = text.strip().lower().rstrip(".!?,…").strip()
    return cleaned in _HALLUCINATIONS or len(cleaned) < 3


# ── Prompts ───────────────────────────────────────────────────────────────────

_POLISH_SYSTEM = """\
Edit this voice-to-text. Remove filler words (um, uh, like, ну, вот, э-э, как бы, типа, значит). Fix punctuation. Keep the original language. Output ONLY the corrected text — no introduction, no explanation."""

_FORMAT_SYSTEM = """\
You are a professional text editor. The user sends a raw voice-to-text transcript. Your job: clean and restructure it. Output only the final result.

CLEAN: Delete filler words (do not replace, just remove).
  Russian: ну, вот, ну вот, э-э, ммм, как бы, в общем, собственно, типа, значит, это самое, короче, понимаешь, то есть, так сказать, на самом деле
  English: um, uh, like, you know, so, right, basically, actually, I mean, kind of, well, anyway
Delete repetitions, false starts, self-corrections. Fix grammar and spelling.

STRUCTURE: Choose the right format for the content.
  One or two ideas → clean paragraph.
  List of items → bullet list, each item on its own line starting with "- ".
  Steps or sequence → numbered list: 1. 2. 3.
  Tasks or to-do → checklist lines starting with "[ ] ".
  Multiple separate topics → topic name in CAPITALS + colon on its own line, then content below.
  Mixed content → combine formats, blank line between blocks.
  Plain text only — no markdown symbols (#, *, **, ~~).

OUTPUT: Start directly with the content. Do not write "Here is", "Sure", "Вот текст", or any preamble. Keep the original language, do not translate."""

_TASKS_SYSTEM = """\
You are a task extractor. The user dictated raw speech that may contain tasks, reminders, or items to do.

Extract every actionable item as a checklist. Output ONLY the checklist — no introduction, no commentary.
Each item on its own line starting with "- [ ] " (dash, space, brackets, space).
Keep the original language. Drop filler and repetitions. Keep verbs and objects, no fluff.
Group obviously related sub-tasks under a parent: parent line ends with ":" and sub-items are indented with two spaces.

If the input has NO actionable items, output a single cleaned paragraph of the input instead — no checklist syntax."""


# ── Ollama helper ─────────────────────────────────────────────────────────────

StatusCb = Optional[Callable[[str], None]]


def _ollama_chat(system_msg: str, user_text: str, status_cb: StatusCb = None) -> str:
    """Run Ollama chat with a streaming pass and a non-streaming fallback.
    Returns the model's text, or '' on failure."""
    from services.ai.ollama import check_ollama, get_polish_model

    if not check_ollama():
        log.warning("Ollama unavailable")
        return ""

    model_name = get_polish_model(format_mode=True)
    # Gemma ignores the system role — fold instruction into the user message.
    if "gemma" in model_name.lower():
        messages = [{"role": "user",
                     "content": f"{system_msg}\n\n---\n{user_text}"}]
    else:
        messages = [{"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_text}]
    options = {"num_predict": 2048, "num_ctx": 8192}
    url = "http://localhost:11434/api/chat"
    short = model_name.split(":")[0]

    # Pass 1: streaming
    result = ""
    try:
        body = {"model": model_name, "messages": messages,
                "stream": True, "options": options}
        t0 = time.time()
        chunks = []
        with requests.post(url, json=body, timeout=300, stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = _json.loads(line)
                except Exception:
                    continue
                token = data.get("message", {}).get("content", "")
                if token:
                    chunks.append(token)
                if status_cb and chunks and len(chunks) % 25 == 0:
                    status_cb(f"[{short}] {int(time.time()-t0)}s")
                if data.get("done"):
                    break
        result = "".join(chunks).strip()
    except Exception as e:
        log.warning("Ollama streaming error: %s", e)

    if result:
        return result

    # Pass 2: non-streaming retry
    log.warning("Streaming returned empty — retrying non-streaming")
    if status_cb:
        status_cb(f"[{short}] повтор…")
    try:
        body2 = {"model": model_name, "messages": messages,
                 "stream": False, "options": options}
        r2 = requests.post(url, json=body2, timeout=300)
        r2.raise_for_status()
        return r2.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning("Ollama non-streaming retry failed: %s", e)
        return ""


# ── Public actions ────────────────────────────────────────────────────────────

def apply_spelling(text: str, detected_lang: str, status_cb: StatusCb = None) -> str:
    """Fix spelling/punctuation. RU → sage-fredt5; other langs → Ollama mini polish."""
    if status_cb:
        status_cb("Исправляю орфографию…")
    if detected_lang == "ru":
        from services.ai.whisper import _fix_russian_spelling
        try:
            fixed = _fix_russian_spelling(text)
            return fixed if fixed.strip() else text
        except Exception as e:
            log.warning("sage spell-fix failed: %s", e)
            return text
    return _ollama_chat(_POLISH_SYSTEM, text, status_cb) or text


def apply_deep_edit(text: str, status_cb: StatusCb = None) -> str:
    if status_cb:
        status_cb("Глубокая редактура…")
    return _ollama_chat(_FORMAT_SYSTEM, text, status_cb) or text


def apply_tasks(text: str, status_cb: StatusCb = None) -> str:
    if status_cb:
        status_cb("Формирую список дел…")
    return _ollama_chat(_TASKS_SYSTEM, text, status_cb) or text


def apply_translate(text: str, status_cb: StatusCb = None) -> str:
    """Auto-direction translate via the currently selected engine."""
    if status_cb:
        status_cb("Перевожу…")
    from app.translation import translate_auto
    translated, _ = translate_auto(text)
    return translated or text
