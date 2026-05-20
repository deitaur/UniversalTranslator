"""
Role management system.
Stores custom AI roles with system prompts and materials folders.
"""

import json
import re
from pathlib import Path
from config import CONFIG_DIR

ROLES_FILE = CONFIG_DIR / "roles.json"
MATERIALS_BASE = CONFIG_DIR / "role_materials"

# Built-in roles (cannot be deleted, but can be customized)
BUILTIN_ROLES = {
    "negotiator": {
        "name": "Negotiator",
        "system_prompt": (
            "You are an expert business communicator and proactive negotiator.\n"
            "Your role is to transform emotional, dead-end, or unconstructive messages into professional, businesslike, and proactive communication.\n\n"
            "When the user sends you text to rewrite:\n"
            "1. Strip away raw emotion, complaints, and dead-ends.\n"
            "2. Ensure the tone is strictly businesslike, confident, and constructive.\n"
            "3. ALWAYS add a proactive proposal, solution, or next step if the original text lacks one.\n"
            "4. Output ONLY the rewritten message, ready to be sent, without unnecessary words or fluff.\n\n"
            "If the user asks a direct question instead of providing text to rewrite, answer concisely."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#cba6f7",
        "show_in_tray": True,
    },
    "web_search": {
        "name": "Web Search (AI)",
        "system_prompt": (
            "You are a helpful, smart AI assistant with access to the internet.\n"
            "Whenever the user asks a question about facts, news, current events, prices, or anything you don't know for sure, YOU MUST use the 'web_search' tool to find the answer.\n"
            "Base your answers on the search results provided. Be concise, accurate, and cite your sources if possible.\n"
            "If the user is just chatting, be friendly and conversational."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#a6e3a1",
        "show_in_tray": True,
    },

    # ── Mobile walking-companion roles ────────────────────────────────────────
    # All have voice-optimized prompts: short replies, no markdown, conversational tone.

    "health_coach": {
        "name": "Health Coach",
        "system_prompt": (
            "You are an enthusiastic, knowledgeable health and fitness coach.\n"
            "Topics: nutrition, exercise, sleep, hydration, recovery, motivation.\n"
            "Never give medical diagnoses or prescribe medications.\n\n"
            "IMPORTANT — the user is walking outdoors with headphones:\n"
            "- Keep every response to 2-3 sentences maximum.\n"
            "- Use natural conversational language, no bullet points or markdown.\n"
            "- Be warm, encouraging, and direct."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#a6e3a1",
        "show_in_tray": False,
    },
    "psychologist": {
        "name": "Psychologist",
        "system_prompt": (
            "You are a compassionate psychological support coach trained in CBT techniques.\n"
            "You listen actively, ask clarifying questions, and help the user reframe thoughts.\n"
            "You are NOT a licensed therapist — always recommend professional help for serious issues.\n\n"
            "IMPORTANT — the user is walking outdoors with headphones:\n"
            "- Keep every response to 2-3 sentences maximum.\n"
            "- Use natural conversational language, no bullet points or markdown.\n"
            "- Be calm, empathetic, and non-judgmental."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#cba6f7",
        "show_in_tray": False,
    },
    "language_tutor": {
        "name": "Language Tutor",
        "system_prompt": (
            "You are a conversational language tutor. The user wants to practice speaking their target language.\n"
            "Conduct the conversation mostly in the target language.\n"
            "Gently correct errors mid-sentence and continue — don't lecture.\n"
            "Introduce new vocabulary naturally in context.\n\n"
            "IMPORTANT — the user is walking outdoors with headphones:\n"
            "- Keep every response to 2-3 sentences maximum.\n"
            "- Use natural conversational language, no bullet points or markdown.\n"
            "- Make it feel like chatting with a friendly native speaker."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#89dceb",
        "show_in_tray": False,
    },
    "topic_learning": {
        "name": "Topic Learning",
        "system_prompt": (
            "You are a knowledgeable tutor who explains topics using the Socratic method.\n"
            "Ask the user what they already know, then build on it.\n"
            "Explain complex ideas with vivid analogies and simple language.\n"
            "Check recall with a quick question after each explanation.\n\n"
            "IMPORTANT — the user is walking outdoors with headphones:\n"
            "- Keep every response to 2-3 sentences maximum.\n"
            "- Use natural conversational language, no bullet points or markdown.\n"
            "- Keep the pace engaging, like a great podcast."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#f9e2af",
        "show_in_tray": False,
    },
}


def _ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MATERIALS_BASE.mkdir(parents=True, exist_ok=True)


def load_roles():
    """Load all roles (builtin + custom) from disk."""
    roles = dict(BUILTIN_ROLES)
    if ROLES_FILE.exists():
        try:
            custom = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
            for role_id, role_data in custom.items():
                if role_id in roles and roles[role_id].get("builtin"):
                    # Allow customizing builtin role prompts
                    roles[role_id].update(role_data)
                    roles[role_id]["builtin"] = True
                else:
                    roles[role_id] = role_data
        except Exception:
            pass
    return roles


def save_roles(roles):
    """Save custom roles to disk (builtins saved only if modified)."""
    try:
        _ensure_dirs()
        to_save = {}
        for role_id, role_data in roles.items():
            if role_id in BUILTIN_ROLES:
                # Only save if prompt was modified
                builtin = BUILTIN_ROLES[role_id]
                if (role_data.get("system_prompt") != builtin["system_prompt"] or 
                    role_data.get("materials_folder") or
                    role_data.get("show_in_tray", True) != builtin["show_in_tray"]):
                    to_save[role_id] = {
                        "system_prompt": role_data.get("system_prompt", ""),
                        "materials_folder": role_data.get("materials_folder", ""),
                        "show_in_tray": role_data.get("show_in_tray", True),
                    }
            else:
                to_save[role_id] = role_data
        ROLES_FILE.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[roles.py] Error saving roles to disk: {e}")
        return False


def create_role(name, system_prompt, materials_folder="", color="#89b4fa", show_in_tray=True):
    """Create a new custom role. Returns role_id."""
    _ensure_dirs()
    role_id = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    # QA FIX: Truncate long role_id to prevent OS MAX_PATH errors
    role_id = role_id[:50]
    if not role_id:
        role_id = "custom_role"
    roles = load_roles()
    # Avoid collision
    base_id = role_id
    counter = 1
    while role_id in roles:
        role_id = base_id + "_" + str(counter)
        counter += 1
    roles[role_id] = {
        "name": name,
        "system_prompt": system_prompt,
        "materials_folder": materials_folder,
        "builtin": False,
        "color": color,
        "show_in_tray": show_in_tray,
    }
    save_roles(roles)
    return role_id


def delete_role(role_id):
    """Delete a custom role. Cannot delete builtins."""
    roles = load_roles()
    if role_id in roles and not roles[role_id].get("builtin"):
        del roles[role_id]
        save_roles(roles)
        return True
    return False


def update_role(role_id, name=None, system_prompt=None, materials_folder=None, color=None, show_in_tray=None):
    """Update an existing role."""
    roles = load_roles()
    if role_id not in roles:
        return False
    if name is not None:
        roles[role_id]["name"] = name
    if system_prompt is not None:
        roles[role_id]["system_prompt"] = system_prompt
    if materials_folder is not None:
        roles[role_id]["materials_folder"] = materials_folder
    if color is not None:
        roles[role_id]["color"] = color
    if show_in_tray is not None:
        roles[role_id]["show_in_tray"] = show_in_tray
    save_roles(roles)
    return True


def get_role(role_id):
    """Get a single role by ID."""
    roles = load_roles()
    return roles.get(role_id)


def get_materials_folder(role_id):
    """Get or create materials folder for a role."""
    _ensure_dirs()
    role = get_role(role_id)
    if not role:
        return None
    folder = role.get("materials_folder", "")
    if folder and Path(folder).exists():
        return Path(folder)
    # Default folder
    default = MATERIALS_BASE / role_id
    default.mkdir(parents=True, exist_ok=True)
    return default


def list_materials(role_id):
    """List material files for a role."""
    folder = get_materials_folder(role_id)
    if not folder or not folder.exists():
        return []
    exts = {".txt", ".md", ".text", ".csv", ".json", ".html", ".py", ".pdf"}
    files = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in exts:
            files.append(f)
    return files
