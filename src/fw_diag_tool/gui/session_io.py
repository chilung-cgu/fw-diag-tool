from __future__ import annotations

import hashlib
from typing import Any

from fw_diag_tool.session.session_manager import SessionDocument, SessionManager


def serialize_i2c_session(
    report: dict[str, Any],
    *,
    input_name: str,
    input_bytes: bytes,
    input_mode: str,
    smbus_timeout_ms: float,
) -> str:
    return SessionManager.serialize_session(
        "i2c-analysis",
        {"report": report},
        capture_sha256=hashlib.sha256(input_bytes).hexdigest(),
        config={
            "input_name": input_name,
            "input_mode": input_mode,
            "smbus_timeout_ms": smbus_timeout_ms,
        },
        provenance={"interface": "streamlit"},
    )


def capture_matches(document: SessionDocument, content: bytes) -> bool | None:
    if document.capture_sha256 is None:
        return None
    return hashlib.sha256(content).hexdigest() == document.capture_sha256


__all__ = ["capture_matches", "serialize_i2c_session"]
