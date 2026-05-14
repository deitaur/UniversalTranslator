import json
import datetime
from config import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "chat_sessions.json"

def load_sessions():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}

def save_session(session_id, history, name=None):
    sessions = load_sessions()
    
    # Auto-generate name from first user message if needed
    if name is None:
        if session_id in sessions and sessions[session_id].get("name") and sessions[session_id]["name"] != "New Chat":
            name = sessions[session_id]["name"]
        else:
            name = "New Chat"
            for msg in history:
                if msg["role"] == "user":
                    name = msg["content"][:25].replace("\n", " ") + "..."
                    break

    sessions[session_id] = {
        "name": name,
        "history": history,
        "updated": datetime.datetime.now().isoformat()
    }
    
    try:
        HISTORY_FILE.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error saving session: {e}")

def delete_session(session_id):
    sessions = load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        try:
            HISTORY_FILE.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass
