from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class SessionManager:
    # Saves and restores diagnostic analysis sessions as .fwsession JSON files

    def __init__(self, session_dir: str | Path | None = None):
        self.session_dir = Path(session_dir) if session_dir else Path.home() / ".fw-diag-sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, name: str, data: dict[str, Any]) -> Path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = name.replace(" ", "_").replace("/", "_").lower()
        filename = f"{safe_name}_{timestamp}.fwsession.json"
        filepath = self.session_dir / filename
        payload = {
            "version": "1.0",
            "created_at": timestamp,
            "name": name,
            "data": data,
        }
        filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return filepath

    def load_session(self, filepath: str | Path) -> dict[str, Any]:
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Session file not found: {p}")
        content = json.loads(p.read_text(encoding="utf-8"))
        return content.get("data", {})

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for f in sorted(self.session_dir.glob("*.fwsession.json"), reverse=True):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(
                    {
                        "filename": f.name,
                        "name": d.get("name", "Unknown"),
                        "created_at": d.get("created_at", "N/A"),
                        "path": str(f),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                continue
        return sessions
