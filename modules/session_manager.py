"""
Session Manager
Persist and restore AI chat sessions as JSON files.
Each session is stored in ./sessions/<session_id>.json.
"""
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

SESSIONS_DIR = "./sessions"


def _ensure_dir() -> None:
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def _session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def new_session_id() -> str:
    return str(uuid.uuid4())


def auto_session_name(messages: List[Dict]) -> str:
    """Generate a session name from the first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")[:40].strip()
            return content if content else "New Session"
    return f"Session {datetime.now().strftime('%m-%d %H:%M')}"


def list_sessions() -> List[Dict]:
    """Return all sessions sorted by last-modified (newest first)."""
    _ensure_dir()
    sessions = []
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "id":       data.get("id", fname.replace(".json", "")),
                "name":     data.get("name", "Untitled"),
                "modified": data.get("modified", ""),
            })
        except Exception:
            pass
    return sorted(sessions, key=lambda s: s["modified"], reverse=True)


def load_session(session_id: str) -> Dict:
    path = _session_path(session_id)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"id": session_id, "name": "Untitled", "messages": []}


def save_session(session_id: str, name: str, messages: List[Dict]) -> None:
    _ensure_dir()
    # Serialise only safe fields (drop non-JSON-serialisable objects like Plotly figs)
    safe_messages = []
    for msg in messages:
        safe_msg = {
            "role":    msg.get("role", "user"),
            "content": msg.get("content", ""),
        }
        if "skill" in msg:
            safe_msg["skill"] = msg["skill"]
        if "code" in msg:
            safe_msg["code"] = msg["code"]
        safe_messages.append(safe_msg)

    data = {
        "id":       session_id,
        "name":     name,
        "messages": safe_messages,
        "modified": datetime.now().isoformat(),
    }
    with open(_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_session(session_id: str) -> None:
    path = _session_path(session_id)
    if os.path.exists(path):
        os.remove(path)
