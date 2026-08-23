from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any


class SessionManager:
    # Saves and restores diagnostic analysis sessions as .fwsession JSON files

    CURRENT_VERSION = "1.0"
    MAX_SESSION_BYTES = 10 * 1024 * 1024

    def __init__(self, session_dir: str | Path | None = None):
        self.session_dir = Path(session_dir) if session_dir else Path.home() / ".fw-diag-sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("session name must not be empty")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._-")
        if not safe_name:
            raise ValueError("session name must contain a letter or number")
        return safe_name[:80].lower()

    @classmethod
    def build_payload(
        cls,
        name: str,
        data: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise TypeError("session data must be a mapping")
        if provenance is not None and not isinstance(provenance, dict):
            raise TypeError("session provenance must be a mapping")
        payload: dict[str, Any] = {
            "version": cls.CURRENT_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "name": name,
            "data": data,
        }
        if provenance is not None:
            payload["provenance"] = provenance
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload

    @classmethod
    def serialize_session(
        cls,
        name: str,
        data: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        return (
            json.dumps(
                cls.build_payload(name, data, provenance=provenance),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )

    def save_session(
        self,
        name: str,
        data: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> Path:
        safe_name = self._safe_name(name)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        filename = f"{safe_name}_{timestamp}_{uuid.uuid4().hex[:10]}.fwsession.json"
        filepath = self.session_dir / filename
        payload_text = self.serialize_session(name, data, provenance=provenance)
        temporary_path = self.session_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
        try:
            temporary_path.write_text(payload_text, encoding="utf-8")
            temporary_path.replace(filepath)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return filepath

    def load_session(self, filepath: str | Path) -> dict[str, Any]:
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Session file not found: {p}")
        if p.stat().st_size > self.MAX_SESSION_BYTES:
            raise ValueError("session file exceeds the 10 MiB safety limit")
        try:
            content = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid session JSON: {p}") from exc
        if not isinstance(content, dict):
            raise TypeError("session root must be a mapping")
        if content.get("version") != self.CURRENT_VERSION:
            raise ValueError(f"unsupported session version: {content.get('version')!r}")
        data = content.get("data")
        if not isinstance(data, dict):
            raise TypeError("session data must be a mapping")
        return data

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for f in sorted(self.session_dir.glob("*.fwsession.json"), reverse=True):
            try:
                if f.stat().st_size > self.MAX_SESSION_BYTES:
                    continue
                d = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(d, dict):
                    continue
                sessions.append(
                    {
                        "filename": f.name,
                        "name": d.get("name", "Unknown"),
                        "created_at": d.get("created_at", "N/A"),
                        "version": d.get("version", "N/A"),
                        "path": str(f),
                    }
                )
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
                continue
        return sessions
