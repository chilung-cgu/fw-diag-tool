from __future__ import annotations

from types import SimpleNamespace

from fw_diag_tool.gui.pages.correlation_ui import (
    build_timeline_events,
    detect_cross_protocol_clusters,
    render,
)


def test_correlation_page_exports_render() -> None:
    assert callable(render)


def test_build_timeline_events_aligns_protocol_rows_and_marks_anomalies() -> None:
    i2c_issue = SimpleNamespace(
        title="Address NACK on 0x3A (WRITE)",
        code="I2C_ADDR_NACK",
        severity=SimpleNamespace(value="ERROR"),
        timestamp=0.005,
        address_7bit=0x3A,
    )
    i2c_report = SimpleNamespace(
        transactions=[SimpleNamespace(start_time=0.004, address_7bit=0x3A)],
        issues=[i2c_issue],
    )
    events = build_timeline_events(i2c_report=i2c_report)
    assert events[0]["protocol"] == "I2C"
    assert events[0]["timestamp"] == 0.004
    assert events[1]["anomaly"] is True
    assert events[1]["label"] == "Address NACK on 0x3A (WRITE)"


def test_detect_cross_protocol_clusters_within_window() -> None:
    events = [
        {"protocol": "I2C", "timestamp": 0.005, "label": "I2C NACK (0x3A)", "anomaly": True},
        {"protocol": "SPI", "timestamp": 0.0065, "label": "SPI Status Error", "anomaly": True},
        {"protocol": "UART", "timestamp": 0.020, "label": "Boot log", "anomaly": False},
    ]
    clusters = detect_cross_protocol_clusters(events, window_s=0.002)
    assert len(clusters) == 1
    assert clusters[0]["protocols"] == ["I2C", "SPI"]
    assert "I2C NACK (0x3A)" in clusters[0]["summary"]
    assert "SPI Status Error" in clusters[0]["summary"]
