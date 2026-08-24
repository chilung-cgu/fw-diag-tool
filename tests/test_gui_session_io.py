from __future__ import annotations

from fw_diag_tool.gui.session_io import capture_matches, serialize_i2c_session
from fw_diag_tool.session.session_manager import SessionManager


def test_i2c_gui_session_uses_canonical_v2_provenance_fields():
    capture = b"Time,Address\n0,0x50\n"

    text = serialize_i2c_session(
        {"total_transactions": 1},
        input_name="capture.csv",
        input_bytes=capture,
        input_mode="Saleae Analyzer table / text trace",
        smbus_timeout_ms=25.0,
    )
    document = SessionManager.deserialize_session(text)

    assert document.capture_sha256 is not None
    assert document.config == {
        "input_name": "capture.csv",
        "input_mode": "Saleae Analyzer table / text trace",
        "smbus_timeout_ms": 25.0,
    }
    assert document.provenance == {"interface": "streamlit"}
    assert capture_matches(document, capture) is True
    assert capture_matches(document, b"different") is False
