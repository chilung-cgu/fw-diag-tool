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
