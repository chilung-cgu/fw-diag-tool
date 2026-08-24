from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fw_diag_tool import __version__


@dataclass(frozen=True)
class SessionDocument:
    schema_version: str
    tool_version: str
    created_at: str | None
    name: str | None
    capture_sha256: str | None
    board_profile_name: str | None
    config: dict[str, Any]
    report: dict[str, Any]
    notes: str
    provenance: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SessionDocument:
        config = payload.get("config", {})
        report = payload.get("report")
        provenance = payload.get("provenance")
        if not isinstance(config, dict):
            raise TypeError("session config must be a mapping")
        if not isinstance(report, dict):
            raise TypeError("session report must be a mapping")
        if provenance is not None and not isinstance(provenance, dict):
            raise TypeError("session provenance must be a mapping")
        notes = payload.get("notes", "")
        if not isinstance(notes, str):
            raise TypeError("session notes must be a string")
        return cls(
            schema_version=str(payload["schema_version"]),
            tool_version=str(payload.get("tool_version", "unknown")),
            created_at=payload.get("created_at"),
            name=payload.get("name"),
            capture_sha256=payload.get("capture_sha256"),
            board_profile_name=payload.get("board_profile_name"),
            config=dict(config),
            report=dict(report),
            notes=notes,
            provenance=dict(provenance) if provenance is not None else None,
        )


class SessionManager:
    # Saves and restores diagnostic analysis sessions as .fwsession JSON files.
    # Session v2 keeps provenance metadata at the top level so a report can be
    # traced back to its original capture without opening nested structures.

    CURRENT_VERSION = "2.0"
    # Session v1 files are migrated in memory on load; they are never rewritten
    # behind the user's back.
    LEGACY_VERSION = "1.0"
    MAX_SESSION_BYTES = 10 * 1024 * 1024

    def __init__(self, session_dir: str | Path | None = None):
        self.session_dir = Path(session_dir) if session_dir else Path.home() / ".fw-diag-sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self.session_dir.chmod(0o700)

    @classmethod
    def _size_limit_label(cls) -> str:
        mib = 1024 * 1024
        if cls.MAX_SESSION_BYTES % mib == 0:
            return f"{cls.MAX_SESSION_BYTES // mib} MiB"
        return f"{cls.MAX_SESSION_BYTES}-byte"

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
        capture_sha256: str | None = None,
        board_profile_name: str | None = None,
        config: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise TypeError("session data must be a mapping")
        if provenance is not None and not isinstance(provenance, dict):
            raise TypeError("session provenance must be a mapping")
        if provenance is not None and (
            "capture_sha256" in provenance or "board_profile_name" in provenance
        ):
            raise ValueError(
                "provenance must not carry capture_sha256/board_profile_name; "
                "pass them via capture_sha256=/board_profile_name= so they stay top-level"
            )
        if capture_sha256 is not None and not isinstance(capture_sha256, str):
            raise TypeError("capture_sha256 must be a string or None")
        if board_profile_name is not None and not isinstance(board_profile_name, str):
            raise TypeError("board_profile_name must be a string or None")
        if config is not None and not isinstance(config, dict):
            raise TypeError("session config must be a mapping")
        if not isinstance(notes, str):
            raise TypeError("session notes must be a string")
        payload: dict[str, Any] = {
            "schema_version": cls.CURRENT_VERSION,
            "tool_version": __version__,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "name": name,
            "capture_sha256": capture_sha256,
            "board_profile_name": board_profile_name,
            "config": config if config is not None else {},
            "report": data,
            "notes": notes,
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
        capture_sha256: str | None = None,
        board_profile_name: str | None = None,
        config: dict[str, Any] | None = None,
        notes: str = "",
    ) -> str:
        text = (
            json.dumps(
                cls.build_payload(
                    name,
                    data,
                    provenance=provenance,
                    capture_sha256=capture_sha256,
                    board_profile_name=board_profile_name,
                    config=config,
                    notes=notes,
                ),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        if len(text.encode("utf-8")) > cls.MAX_SESSION_BYTES:
            raise ValueError(f"session exceeds the {cls._size_limit_label()} safety limit")
        return text

    def save_session(
        self,
        name: str,
        data: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
        capture_sha256: str | None = None,
        board_profile_name: str | None = None,
        config: dict[str, Any] | None = None,
        notes: str = "",
    ) -> Path:
        safe_name = self._safe_name(name)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        filename = f"{safe_name}_{timestamp}_{uuid.uuid4().hex[:10]}.fwsession.json"
        filepath = self.session_dir / filename
        payload_text = self.serialize_session(
            name,
            data,
            provenance=provenance,
            capture_sha256=capture_sha256,
            board_profile_name=board_profile_name,
            config=config,
            notes=notes,
        )
        # Atomic replace: write a same-directory temporary file first, fsync it,
        # then rename over the destination so readers never see a partial file.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{safe_name}.", suffix=".fwsession.json.tmp", dir=self.session_dir
        )
        try:
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload_text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, filepath)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
        return filepath

    @classmethod
    def migrate_v1(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Upgrade an in-memory Session v1 mapping to the v2 schema."""

        legacy_data = payload.get("data")
        if not isinstance(legacy_data, dict):
            raise TypeError("session data must be a mapping")
        legacy_provenance = payload.get("provenance")
        if legacy_provenance is not None and not isinstance(legacy_provenance, dict):
            raise TypeError("session provenance must be a mapping")

        capture_sha256 = None
        board_profile_name = None
        config: dict[str, Any] = {}
        if isinstance(legacy_provenance, dict):
            for key in ("capture_sha256", "input_sha256"):
                value = legacy_provenance.get(key)
                if isinstance(value, str) and value:
                    capture_sha256 = value
                    break
            profile_value = legacy_provenance.get("board_profile_name")
            if isinstance(profile_value, str) and profile_value:
                board_profile_name = profile_value
            for key in ("smbus_timeout_ms", "input_mode", "input_name"):
                if key in legacy_provenance:
                    config[key] = legacy_provenance[key]

        migrated: dict[str, Any] = {
            "schema_version": cls.CURRENT_VERSION,
            "tool_version": payload.get("tool_version") or "unknown (v1 session)",
            "created_at": payload.get("created_at"),
            "name": payload.get("name"),
            "capture_sha256": capture_sha256,
            "board_profile_name": board_profile_name,
            "config": config,
            "report": legacy_data,
            "notes": "",
            "_v1_provenance": legacy_provenance,
            "_migrated_from": cls.LEGACY_VERSION,
        }
        json.dumps(migrated, ensure_ascii=False, allow_nan=False)
        return migrated

    @classmethod
    def deserialize_session(cls, content: str | bytes) -> SessionDocument:
        if isinstance(content, str):
            encoded = content.encode("utf-8")
        elif isinstance(content, bytes):
            encoded = content
        else:
            raise TypeError("session content must be text or bytes")
        if len(encoded) > cls.MAX_SESSION_BYTES:
            raise ValueError(f"session exceeds the {cls._size_limit_label()} safety limit")
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid session JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("session root must be a mapping")
        version = payload.get("schema_version", payload.get("version"))
        if version == cls.LEGACY_VERSION and "data" in payload:
            payload = cls.migrate_v1(payload)
        elif version != cls.CURRENT_VERSION:
            raise ValueError(f"unsupported session version: {version!r}")
        return SessionDocument.from_payload(payload)

    def load_document(self, filepath: str | Path) -> SessionDocument:
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Session file not found: {p}")
        if p.stat().st_size > self.MAX_SESSION_BYTES:
            raise ValueError(f"session file exceeds the {self._size_limit_label()} safety limit")
        try:
            return self.deserialize_session(p.read_bytes())
        except OSError as exc:
            raise ValueError(f"invalid session JSON: {p}") from exc

    def load_session(self, filepath: str | Path) -> dict[str, Any]:
        return self.load_document(filepath).report

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
                        "version": d.get("schema_version", d.get("version", "N/A")),
                        "path": str(f),
                    }
                )
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
                continue
        return sessions


__all__ = ["SessionDocument", "SessionManager"]
