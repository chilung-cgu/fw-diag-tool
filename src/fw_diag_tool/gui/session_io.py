from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.gui.pages.i2c_page import analyze_i2c
from fw_diag_tool.i2c.input import I2CInputFormat, normalize_i2c_input_format
from fw_diag_tool.limits import AnalysisLimits
from fw_diag_tool.session.session_manager import SessionDocument, SessionManager


def _profile_identity(profile: BoardProfile) -> tuple[str, str, str]:
    normalized = profile.to_yaml()
    return (
        profile.board_name,
        profile.version,
        hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )


def _coerce_board_profile(
    board_profile: BoardProfile | Mapping[str, Any] | str | None,
    board_profile_yaml: str | None,
) -> BoardProfile | None:
    if board_profile is not None and board_profile_yaml is not None:
        raise ValueError("provide board_profile or board_profile_yaml, not both")
    source: BoardProfile | Mapping[str, Any] | str | None = board_profile
    if board_profile_yaml is not None:
        source = board_profile_yaml
    if source is None:
        return None
    if isinstance(source, BoardProfile):
        return source
    return load_board_profile(source)


def serialize_i2c_session(
    report: dict[str, Any],
    *,
    input_name: str,
    input_bytes: bytes,
    input_mode: I2CInputFormat | str | None = None,
    smbus_timeout_ms: float = 25.0,
    board_profile: BoardProfile | Mapping[str, Any] | str | None = None,
    board_profile_yaml: str | None = None,
    input_format: I2CInputFormat | str | None = None,
    board_profile_name: str | None = None,
    board_profile_content: str | None = None,
    board_profile_hash: str | None = None,
) -> str:
    if board_profile_content is not None:
        if board_profile_yaml is not None:
            raise ValueError("provide board_profile_content or board_profile_yaml, not both")
        board_profile_yaml = board_profile_content
    profile = _coerce_board_profile(board_profile, board_profile_yaml)
    resolved_mode = normalize_i2c_input_format(input_mode) if input_mode is not None else None
    resolved_format = normalize_i2c_input_format(input_format) if input_format is not None else None
    if (
        resolved_mode is not None
        and resolved_format is not None
        and resolved_mode is not resolved_format
    ):
        raise ValueError("input_mode and input_format identify different I2C formats")
    config: dict[str, Any] = {
        "input_name": input_name,
        "input_mode": (
            input_mode.value
            if isinstance(input_mode, I2CInputFormat)
            else input_mode
            or (input_format.value if isinstance(input_format, I2CInputFormat) else input_format)
            or I2CInputFormat.DECODED_CSV.value
        ),
        "smbus_timeout_ms": smbus_timeout_ms,
    }
    if input_format is not None:
        config["input_format"] = normalize_i2c_input_format(input_format).value
    elif isinstance(input_mode, I2CInputFormat):
        config["input_format"] = input_mode.value
    elif input_mode is not None and input_mode != "Saleae Analyzer table / text trace":
        config["input_format"] = normalize_i2c_input_format(input_mode).value

    profile_name = board_profile_name
    if profile is not None:
        profile_name, profile_version, profile_sha256 = _profile_identity(profile)
        if board_profile_name is not None and board_profile_name != profile_name:
            raise ValueError("board_profile_name does not match board profile content")
        if board_profile_hash is not None and board_profile_hash != profile_sha256:
            raise ValueError("board_profile_hash does not match board profile content")
        config.update(
            {
                "board_profile_name": profile_name,
                "board_profile_version": profile_version,
                "board_profile_sha256": profile_sha256,
                "board_profile_hash": profile_sha256,
                "board_profile_content": profile.to_yaml(),
            }
        )
    elif board_profile_name is not None or board_profile_hash is not None:
        config.update(
            {
                "board_profile_name": board_profile_name,
                "board_profile_sha256": board_profile_hash,
                "board_profile_hash": board_profile_hash,
            }
        )
    return SessionManager.serialize_session(
        "i2c-analysis",
        {"report": report},
        capture_sha256=hashlib.sha256(input_bytes).hexdigest(),
        board_profile_name=profile_name,
        config=config,
        provenance={"interface": "streamlit"},
    )


def capture_matches(document: SessionDocument, content: bytes) -> bool | None:
    if document.capture_sha256 is None:
        return None
    return hashlib.sha256(content).hexdigest() == document.capture_sha256


def restore_i2c_board_profile(document: SessionDocument) -> BoardProfile | None:
    """Restore and verify the board profile embedded in a session config."""

    content = document.config.get("board_profile_content")
    if content is None:
        return None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("session board_profile_content must be non-empty text")
    profile = load_board_profile(content)
    name, version, digest = _profile_identity(profile)
    expected_name = document.config.get("board_profile_name", document.board_profile_name)
    expected_version = document.config.get("board_profile_version")
    expected_digests = [
        document.config.get(field_name)
        for field_name in ("board_profile_sha256", "board_profile_hash")
    ]
    if expected_name is None:
        raise ValueError("session board profile name is required when profile content is embedded")
    if expected_version is None:
        raise ValueError(
            "session board profile version is required when profile content is embedded"
        )
    if not any(expected_digests):
        raise ValueError(
            "session board profile sha256 is required when profile content is embedded"
        )
    if document.board_profile_name is not None and document.board_profile_name != name:
        raise ValueError("session top-level board profile name does not match embedded content")
    if expected_name is not None and expected_name != name:
        raise ValueError("session board profile name does not match embedded content")
    if expected_version is not None and expected_version != version:
        raise ValueError("session board profile version does not match embedded content")
    for field_name in ("board_profile_sha256", "board_profile_hash"):
        expected_digest = document.config.get(field_name)
        if expected_digest is not None and expected_digest != digest:
            raise ValueError(f"session {field_name} does not match embedded content")
    return profile


def replay_i2c_session(
    document: SessionDocument,
    content: bytes | str,
    *,
    limits: AnalysisLimits | None = None,
) -> tuple[Any, Any]:
    """Replay a session against its original capture and saved configuration."""

    if not isinstance(document, SessionDocument):
        raise TypeError("document must be a SessionDocument")
    if isinstance(content, bytes):
        capture_bytes = content
        try:
            capture_text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("I2C capture must be valid UTF-8 text") from exc
    elif isinstance(content, str):
        capture_text = content
        capture_bytes = content.encode("utf-8")
    else:
        raise TypeError("I2C capture must be text or bytes")
    match = capture_matches(document, capture_bytes)
    if match is None:
        raise ValueError("session has no capture SHA-256; replay cannot be verified")
    if match is False:
        raise ValueError("session capture SHA-256 does not match replay input")

    config = document.config
    saved_mode = config.get("input_mode")
    saved_format = config.get("input_format")
    mode = saved_format if saved_format is not None else saved_mode
    if (
        saved_mode is not None
        and saved_format is not None
        and normalize_i2c_input_format(saved_mode) is not normalize_i2c_input_format(saved_format)
    ):
        raise ValueError("session input_mode and input_format identify different I2C formats")
    if mode is None:
        mode = I2CInputFormat.DECODED_CSV
    # v1 sessions often have no timeout metadata; use the documented GUI
    # default instead of leaking a low-level float(None) TypeError.
    timeout = config.get("smbus_timeout_ms", 25.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError("session smbus_timeout_ms must be numeric")
    profile = restore_i2c_board_profile(document)
    return analyze_i2c(
        capture_text,
        mode,
        float(timeout),
        board_profile=profile,
        limits=limits,
    )


restore_i2c_session = replay_i2c_session


__all__ = [
    "capture_matches",
    "replay_i2c_session",
    "restore_i2c_board_profile",
    "restore_i2c_session",
    "serialize_i2c_session",
]
