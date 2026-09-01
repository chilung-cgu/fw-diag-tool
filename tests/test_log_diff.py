"""Unit tests for Log Diff Engine and Comparison Results."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log import (
    Incident,
    LogDiffEngine,
    LogDiffResult,
    LogEvent,
    LogParser,
    LogReport,
    LogSourceType,
    Subsystem,
)


def _make_dummy_event(pattern_id: str, message: str, subsystem: Subsystem = Subsystem.I2C) -> LogEvent:
    """Helper to create minimal LogEvent for testing."""
    return LogEvent(
        timestamp=10.0,
        subsystem=subsystem,
        severity=Severity.ERROR,
        message=message,
        pattern_id=pattern_id,
    )


def _make_dummy_incident(id_str: str, title: str, events: list[LogEvent]) -> Incident:
    """Helper to create minimal Incident for testing."""
    return Incident(
        id=id_str,
        title=title,
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        events=events,
        root_cause_hypothesis="Test hypothesis",
        recommended_actions=["Check bus"],
    )


def test_log_diff_result_frozen() -> None:
    """Verify LogDiffResult is immutable and frozen."""
    diff_res = LogDiffResult(
        baseline_event_count=1,
        candidate_event_count=2,
        event_count_delta=1,
        summary="1 new incident(s)",
    )
    with pytest.raises(FrozenInstanceError):
        diff_res.summary = "New summary"  # type: ignore[misc]


def test_log_diff_identical_empty() -> None:
    """Verify comparing two empty log reports yields an identical result."""
    base = LogReport(source_type=LogSourceType.DMESG)
    cand = LogReport(source_type=LogSourceType.DMESG)

    result = LogDiffEngine.compare(base, cand)

    assert result.is_identical is True
    assert result.baseline_event_count == 0
    assert result.candidate_event_count == 0
    assert result.event_count_delta == 0
    assert result.new_incidents == []
    assert result.resolved_incidents == []
    assert result.common_incidents == []
    assert result.new_event_patterns == []
    assert result.resolved_event_patterns == []
    assert "identical" in result.summary.lower()


def test_log_diff_identical_with_incidents() -> None:
    """Verify comparing reports with the exact same incidents and events."""
    ev = _make_dummy_event("i2c_nack_001", "i2c transfer timed out")
    inc = _make_dummy_incident("inc-1", "I2C Bus 3 NAK", [ev])

    base = LogReport(events=[ev], incidents=[inc])
    cand = LogReport(events=[ev], incidents=[inc])

    result = LogDiffEngine.compare(base, cand)

    assert result.is_identical is True
    assert result.baseline_event_count == 1
    assert result.candidate_event_count == 1
    assert result.event_count_delta == 0
    assert result.new_incidents == []
    assert result.resolved_incidents == []
    assert result.common_incidents == ["I2C Bus 3 NAK"]
    assert result.new_event_patterns == []
    assert result.resolved_event_patterns == []
    assert "identical" in result.summary.lower()


def test_log_diff_new_incident() -> None:
    """Verify new incident detection when candidate has issue not present in baseline."""
    base = LogReport(source_type=LogSourceType.DMESG)

    ev = _make_dummy_event("i2c_nack_001", "i2c transfer timed out")
    inc = _make_dummy_incident("inc-1", "I2C Bus 3 NAK", [ev])
    cand = LogReport(events=[ev], incidents=[inc])

    result = LogDiffEngine.compare(base, cand)

    assert result.is_identical is False
    assert result.baseline_event_count == 0
    assert result.candidate_event_count == 1
    assert result.event_count_delta == 1
    assert result.new_incidents == ["I2C Bus 3 NAK"]
    assert result.resolved_incidents == []
    assert result.common_incidents == []
    assert result.new_event_patterns == ["i2c_nack_001"]
    assert result.resolved_event_patterns == []
    assert "1 new incident(s)" in result.summary
    assert "+1" in result.summary


def test_log_diff_resolved_incident() -> None:
    """Verify resolved incident detection when baseline had issue resolved in candidate."""
    ev = _make_dummy_event("pcie_aer_001", "AER uncorrectable error", subsystem=Subsystem.PCIE)
    inc = _make_dummy_incident("inc-pcie", "PCIe Device Degradation", [ev])
    base = LogReport(events=[ev], incidents=[inc])
    cand = LogReport(source_type=LogSourceType.DMESG)

    result = LogDiffEngine.compare(base, cand)

    assert result.is_identical is False
    assert result.baseline_event_count == 1
    assert result.candidate_event_count == 0
    assert result.event_count_delta == -1
    assert result.new_incidents == []
    assert result.resolved_incidents == ["PCIe Device Degradation"]
    assert result.common_incidents == []
    assert result.new_event_patterns == []
    assert result.resolved_event_patterns == ["pcie_aer_001"]
    assert "1 resolved incident(s)" in result.summary
    assert "-1" in result.summary


def test_log_diff_mixed_changes() -> None:
    """Verify handling when some incidents are common, some resolved, and some new."""
    ev_common = _make_dummy_event("common_pat", "common event")
    ev_old = _make_dummy_event("old_pat", "old event")
    ev_new = _make_dummy_event("new_pat", "new event")

    inc_common = _make_dummy_incident("inc-comm", "Common Problem", [ev_common])
    inc_resolved = _make_dummy_incident("inc-res", "Resolved Problem", [ev_old])
    inc_new = _make_dummy_incident("inc-new", "Brand New Problem", [ev_new])

    base = LogReport(events=[ev_common, ev_old], incidents=[inc_common, inc_resolved])
    cand = LogReport(events=[ev_common, ev_new, ev_new], incidents=[inc_common, inc_new])

    result = LogDiffEngine.compare(base, cand)

    assert result.is_identical is False
    assert result.baseline_event_count == 2
    assert result.candidate_event_count == 3
    assert result.event_count_delta == 1
    assert result.common_incidents == ["Common Problem"]
    assert result.resolved_incidents == ["Resolved Problem"]
    assert result.new_incidents == ["Brand New Problem"]
    assert result.resolved_event_patterns == ["old_pat"]
    assert result.new_event_patterns == ["new_pat"]
    assert "1 new incident(s)" in result.summary
    assert "1 resolved incident(s)" in result.summary


def test_log_diff_to_dict_and_to_json() -> None:
    """Verify dictionary conversion and JSON serialization of diff result."""
    result = LogDiffResult(
        baseline_event_count=5,
        candidate_event_count=8,
        event_count_delta=3,
        new_incidents=["Incident B"],
        resolved_incidents=["Incident A"],
        common_incidents=["Incident C"],
        new_event_patterns=["pat_2"],
        resolved_event_patterns=["pat_1"],
        summary="1 new incident(s); 1 resolved incident(s); event count delta: +3",
        is_identical=False,
    )

    d = result.to_dict()
    assert d["baseline_event_count"] == 5
    assert d["candidate_event_count"] == 8
    assert d["event_count_delta"] == 3
    assert d["new_incidents"] == ["Incident B"]
    assert d["resolved_incidents"] == ["Incident A"]
    assert d["common_incidents"] == ["Incident C"]
    assert d["new_event_patterns"] == ["pat_2"]
    assert d["resolved_event_patterns"] == ["pat_1"]
    assert d["is_identical"] is False
    assert d["summary"] == "1 new incident(s); 1 resolved incident(s); event count delta: +3"

    json_str = result.to_json(indent=4)
    parsed = json.loads(json_str)
    assert parsed == d


def test_log_diff_with_parser_integration() -> None:
    """End-to-end integration test parsing logs with LogParser and running LogDiffEngine."""
    log_baseline = """
[ 10.123456] i2c i2c-3: controller timed out
[ 10.123500] i2c 3-0050: NAK received from device
"""
    log_candidate = """
[ 12.000000] systemd[1]: Started OpenBMC service.
[ 15.654321] pcieport 0000:00:01.0: AER: Uncorrectable error received: 0000:01:00.0
"""
    report_base = LogParser.parse_log_text(log_baseline)
    report_cand = LogParser.parse_log_text(log_candidate)

    diff_res = LogDiffEngine.compare(report_base, report_cand)

    assert diff_res.is_identical is False
    assert diff_res.baseline_event_count >= 1
    assert diff_res.candidate_event_count >= 1
    assert len(diff_res.resolved_event_patterns) >= 1
    assert len(diff_res.new_event_patterns) >= 1
    assert diff_res.to_dict()["baseline_event_count"] == diff_res.baseline_event_count


def test_log_diff_instance_call() -> None:
    """Verify compare can be called on an instance of LogDiffEngine as well."""
    engine = LogDiffEngine()
    base = LogReport()
    cand = LogReport()
    res = engine.compare(base, cand)
    assert res.is_identical is True
