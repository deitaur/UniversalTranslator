"""
Role management system.
Stores custom AI roles with system prompts and materials folders.
"""

import json
import os
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
            "You are an expert communication coach and professional negotiator.\n"
            "Your role is to help the user communicate more persuasively, inspiringly, and professionally.\n\n"
            "When the user sends you text:\n"
            "1. First, rewrite it to sound more persuasive, confident, and inspiring\n"
            "2. Keep the same meaning but make it sound like a seasoned negotiator/leader\n"
            "3. Use power words, confident tone, clear structure\n\n"
            "You can also:\n"
            "- Teach negotiation techniques when asked\n"
            "- Explain WHY certain phrasing is more effective\n"
            "- Suggest alternative approaches to the conversation\n"
            "- Ask clarifying questions about the context to give better advice\n\n"
            "Keep responses concise and actionable. No fluff."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#cba6f7",
        "show_in_tray": True,
    },
    "teacher": {
        "name": "English Teacher",
        "system_prompt": (
            "You are a skilled, patient English teacher working one-on-one with a Russian-speaking student.\n"
            "Your teaching approach is based on the book 'Make It Stick' -- use these techniques:\n\n"
            "1. RETRIEVAL PRACTICE: Ask recall questions from previous sessions.\n"
            "2. SPACED REPETITION: Revisit older topics at increasing intervals.\n"
            "3. INTERLEAVING: Alternate exercise types (grammar, vocabulary, translation).\n"
            "4. ELABORATION: Ask the student to explain in their own words.\n"
            "5. GENERATION: Let the student attempt before giving answers.\n\n"
            "Session structure:\n"
            "- Start with 2-3 recall questions from previous sessions.\n"
            "- Introduce new material or practice.\n"
            "- Mix exercise types: fill-in-the-blank, translate, correct errors, rephrase.\n"
            "- End with a brief summary.\n"
            "- Give encouraging but honest feedback.\n\n"
            "Use Russian for explanations when needed, but push the student to respond in English."
        ),
        "builtin": True,
        "materials_folder": "",
        "color": "#94e2d5",
        "show_in_tray": True,
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
