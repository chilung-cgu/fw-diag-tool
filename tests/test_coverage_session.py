"""Branch coverage for session persistence and discovery operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fw_diag_tool.session.session_manager import SessionDocument, SessionManager


def test_create_session_uses_private_directory(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    assert manager.session_dir == tmp_path
    assert tmp_path.exists()


def test_create_and_load_report_round_trip(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    report = {"transactions": [{"address": 80}], "anomaly_count": 0}
    path = manager.save_session("capture one", report)
    assert path.suffixes[-2:] == [".fwsession", ".json"]
    assert manager.load_session(path) == report


def test_save_normalizes_name_and_preserves_metadata(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager.save_session(
        "  Board/Capture #A  ",
        {"ok": True},
        provenance={"input_name": "trace.csv"},
        capture_sha256="abc123",
        board_profile_name="yv4",
        config={"input_mode": "decoded_csv"},
        notes="test note",
    )
    document = manager.load_document(path)
    assert document.name == "  Board/Capture #A  "
    assert document.capture_sha256 == "abc123"
    assert document.board_profile_name == "yv4"
    assert document.config == {"input_mode": "decoded_csv"}
    assert document.provenance == {"input_name": "trace.csv"}
    assert document.notes == "test note"


def test_list_sessions_returns_newest_first_with_paths(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    first = manager.save_session("first", {"n": 1})
    second = manager.save_session("second", {"n": 2})
    sessions = manager.list_sessions()
    assert {entry["name"] for entry in sessions} == {"first", "second"}
    assert all(Path(entry["path"]).exists() for entry in sessions)
    assert first.name in {entry["filename"] for entry in sessions}
    assert second.name in {entry["filename"] for entry in sessions}


def test_search_by_name_over_listed_sessions(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    manager.save_session("boot-capture", {"kind": "boot"})
    manager.save_session("sensor-capture", {"kind": "sensor"})
    matches = [entry for entry in manager.list_sessions() if "sensor" in str(entry["name"])]
    assert len(matches) == 1
    assert matches[0]["name"] == "sensor-capture"


def test_delete_session_file_removes_it_from_listing(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager.save_session("to-delete", {"remove": True})
    assert len(manager.list_sessions()) == 1
    path.unlink()
    assert manager.list_sessions() == []


def test_load_document_missing_file_raises(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    with pytest.raises(FileNotFoundError, match="Session file not found"):
        manager.load_document(tmp_path / "missing.fwsession.json")


def test_deserialize_accepts_text_and_bytes(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager.save_session("bytes", {"value": 7})
    content = path.read_bytes()
    assert manager.deserialize_session(content).report == {"value": 7}
    assert manager.deserialize_session(content.decode("utf-8")).report == {"value": 7}


def test_deserialize_version_alias_is_normalized() -> None:
    document = SessionManager.deserialize_session('{"version":"2.0","config":{},"report":{}}')
    assert isinstance(document, SessionDocument)
    assert document.schema_version == "2.0"


def test_v1_session_is_migrated_without_rewriting_file(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = tmp_path / "legacy.fwsession.json"
    payload = {
        "version": "1.0",
        "name": "legacy",
        "data": {"count": 3},
        "provenance": {"input_sha256": "deadbeef", "input_mode": "text"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert manager.load_session(path) == {"count": 3}
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "1.0"


def test_list_sessions_skips_invalid_json_and_non_session_files(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    manager.save_session("valid", {"ok": True})
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "broken.fwsession.json").write_text("{not-json", encoding="utf-8")
    (tmp_path / "scalar.fwsession.json").write_text("[]", encoding="utf-8")
    sessions = manager.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["name"] == "valid"


def test_invalid_session_content_reports_clear_errors(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    with pytest.raises(ValueError, match="invalid session JSON"):
        manager.deserialize_session("not-json")
    with pytest.raises(TypeError, match="session root"):
        manager.deserialize_session("[]")
    with pytest.raises(ValueError, match="unsupported session version"):
        manager.deserialize_session('{"schema_version":"9.9","config":{},"report":{}}')


def test_build_payload_rejects_reserved_provenance_fields() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        SessionManager.build_payload("bad", {}, provenance={"capture_sha256": "x"})


def test_save_rejects_non_mapping_and_empty_names(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    with pytest.raises(TypeError, match="session data"):
        manager.save_session("bad", [])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="session name"):
        manager.save_session("...", {})
