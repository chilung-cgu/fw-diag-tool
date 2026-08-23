import pytest

from fw_diag_tool.session.session_manager import SessionManager


def test_save_and_load_session(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    data = {"transactions": [1, 2, 3], "anomaly_count": 0, "tool": "fw-diag"}
    filepath = mgr.save_session("test_analysis", data)
    assert filepath.exists()
    loaded = mgr.load_session(filepath)
    assert loaded == data


def test_list_sessions(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    mgr.save_session("session_a", {"idx": 1})
    mgr.save_session("session_b", {"idx": 2})
    sessions = mgr.list_sessions()
    assert len(sessions) == 2


def test_load_nonexistent_raises(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.load_session(tmp_path / "nonexistent.fwsession.json")


def test_session_filename_is_safe_and_provenance_round_trips(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    filepath = mgr.save_session(
        "../Board Capture / A",
        {"report": {"count": 1}},
        provenance={"input_sha256": "abc", "tool_version": "1.0.0"},
    )

    assert filepath.parent == tmp_path
    assert "/" not in filepath.name
    assert mgr.load_session(filepath) == {"report": {"count": 1}}
    payload = filepath.read_text(encoding="utf-8")
    assert '"input_sha256": "abc"' in payload


def test_session_rejects_invalid_schema_and_non_json_values(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    with pytest.raises(TypeError, match="session data"):
        mgr.save_session("bad", [])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="session name"):
        mgr.save_session("../", {})

    invalid = tmp_path / "invalid.fwsession.json"
    invalid.write_text('{"version":"9.9","data":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported session version"):
        mgr.load_session(invalid)

    with pytest.raises((TypeError, ValueError)):
        SessionManager.serialize_session("nan", {"value": float("nan")})
