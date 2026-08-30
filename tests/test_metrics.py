from __future__ import annotations

import csv
import io
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from fw_diag_tool.metrics import MetricsCollector, UsageEvent, get_metrics_collector


def test_usage_event_is_frozen_and_has_expected_fields() -> None:
    event = UsageEvent("2026-08-30T00:00:00+00:00", "dashboard", "view")

    assert event.page_name == "dashboard"
    assert event.action == "view"
    assert event.protocol is None
    assert event.duration_ms is None
    with pytest.raises(FrozenInstanceError):
        event.action = "click"  # type: ignore[misc]


def test_record_event_returns_event_with_utc_timestamp() -> None:
    collector = MetricsCollector()

    event = collector.record_event("i2c", "analyze", protocol="I2C", duration_ms=12)

    assert isinstance(event, UsageEvent)
    assert event.page_name == "i2c"
    assert event.protocol == "I2C"
    assert event.duration_ms == 12.0
    assert datetime.fromisoformat(event.timestamp).tzinfo is not None


def test_get_summary_counts_pages_and_non_null_protocols() -> None:
    collector = MetricsCollector()
    collector.record_event("dashboard", "view")
    collector.record_event("i2c", "analyze", protocol="I2C")
    collector.record_event("i2c", "download", protocol="I2C")
    collector.record_event("spi", "analyze", protocol="SPI")
    collector.record_event("dashboard", "view")

    assert collector.get_summary() == {
        "page_usage": {"dashboard": 2, "i2c": 2, "spi": 1},
        "protocol_usage": {"I2C": 2, "SPI": 1},
    }


def test_get_recent_events_returns_last_n_in_record_order() -> None:
    collector = MetricsCollector()
    events = [collector.record_event("page", str(index)) for index in range(3)]

    assert collector.get_recent_events(2) == events[-2:]
    assert collector.get_recent_events(0) == []
    assert collector.get_recent_events(-1) == []
    assert collector.get_recent_events(20) == events


def test_export_csv_contains_header_and_event_values() -> None:
    collector = MetricsCollector()
    event = collector.record_event("i2c", "analyze", protocol="I2C", duration_ms=12.5)

    rows = list(csv.DictReader(io.StringIO(collector.export_csv())))

    assert rows == [
        {
            "timestamp": event.timestamp,
            "page_name": "i2c",
            "action": "analyze",
            "protocol": "I2C",
            "duration_ms": "12.5",
        }
    ]


def test_export_csv_empty_collector_still_has_header() -> None:
    collector = MetricsCollector()

    assert collector.export_csv() == "timestamp,page_name,action,protocol,duration_ms\n"


def test_get_metrics_collector_returns_module_singleton() -> None:
    assert get_metrics_collector() is get_metrics_collector()
