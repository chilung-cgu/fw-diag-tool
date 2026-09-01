"""Unit tests for LogParser engine and incident correlation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log.models import (
    LogReport,
    LogSourceType,
    Subsystem,
)
from fw_diag_tool.log.parser import LogParser


def test_detect_source_type_dmesg() -> None:
    """Verify dmesg log format detection."""
    lines = [
        "[    0.000000] Linux version 6.6.0-openbmc",
        "[   12.345678] i2c_designware 0000:00:15.0: i2c_dw_handle_tx_abort: lost arbitration",
        "[   14.100200] i2c i2c-1: controller timed out waiting for bus",
    ]
    assert LogParser._detect_source_type(lines) == LogSourceType.DMESG


def test_detect_source_type_journalctl() -> None:
    """Verify journalctl / syslog format detection."""
    lines = [
        "Sep 01 12:00:00 bmc-yv4 psusensor[1024]: Sensor /xyz/openbmc_project/sensors/power/PSU0_Power not available: -110",
        "Sep 01 12:00:01 bmc-yv4 entity-manager[512]: Probe failed for /xyz/openbmc_project/inventory/system/chassis: Configuration not found",
        "Sep 01 12:00:02 bmc-yv4 phosphor-state-manager[768]: Chassis power state changed to xyz.openbmc_project.State.Chassis.PowerState.Off",
    ]
    assert LogParser._detect_source_type(lines) == LogSourceType.JOURNALCTL


def test_detect_source_type_mixed() -> None:
    """Verify mixed log format detection when both timestamp styles exist."""
    lines = [
        "[   12.345678] i2c_designware 0000:00:15.0: tx abort",
        "Sep 01 12:00:00 bmc-yv4 psusensor[1024]: Sensor not available: -110",
    ]
    assert LogParser._detect_source_type(lines) == LogSourceType.MIXED


def test_empty_and_clean_logs() -> None:
    """Verify handling of empty strings and logs with zero matched errors."""
    # Empty text
    empty_report = LogParser.parse_log_text("")
    assert isinstance(empty_report, LogReport)
    assert empty_report.events == []
    assert empty_report.incidents == []
    assert empty_report.summary.total_lines == 0
    assert empty_report.summary.total_events == 0
    assert empty_report.summary.total_incidents == 0
    assert empty_report.summary.time_span_seconds is None

    # Clean log without errors
    clean_text = (
        "[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]\n"
        "[    0.000000] Linux version 6.6.0-openbmc\n"
        "[    1.234567] systemd[1]: Reached target Multi-User System.\n"
    )
    clean_report = LogParser.parse_log_text(clean_text)
    assert len(clean_report.events) == 0
    assert len(clean_report.incidents) == 0
    assert clean_report.summary.total_lines == 3
    assert clean_report.summary.total_events == 0
    assert clean_report.summary.total_incidents == 0


def test_dmesg_parsing_and_extraction() -> None:
    """Verify extraction of diverse dmesg error events."""
    log_text = """
[   12.345678] i2c_designware 0000:00:15.0: i2c_dw_handle_tx_abort: lost arbitration
[   15.200300] i2c-1: client at 0x50: No such device or address (-ENXIO)
[   18.500600] tmp421 2-004c: probe of 2-004c failed with error -121
[   20.700800] pcieport 0000:00:01.0: AER: Uncorrectable error received: 0000:01:00.0
[   23.001100] thermal thermal_zone0: critical temperature reached (105 C), shutting down
[   26.301400] watchdog: watchdog0: watchdog timeout occurred, system reset pending
"""
    report = LogParser.parse_log_text(log_text)
    assert report.source_type == LogSourceType.DMESG
    assert len(report.events) == 6

    # Event 0: I2C_DW_TX_ABORT
    e0 = report.events[0]
    assert e0.pattern_id == "I2C_DW_TX_ABORT"
    assert e0.subsystem == Subsystem.I2C
    assert e0.severity == Severity.ERROR
    assert e0.timestamp == 12.345678
    assert e0.bdf == "0000:00:15.0"

    # Event 1: I2C_SLAVE_ENXIO
    e1 = report.events[1]
    assert e1.pattern_id == "I2C_SLAVE_ENXIO"
    assert e1.subsystem == Subsystem.I2C
    assert e1.bus == 1
    assert e1.address == 0x50
    assert e1.errno_code == "-ENXIO"

    # Event 2: HWMON_PROBE_FAIL
    e2 = report.events[2]
    assert e2.pattern_id == "HWMON_PROBE_FAIL"
    assert e2.subsystem == Subsystem.HWMON
    assert e2.bus == 2
    assert e2.address == 0x4C
    assert e2.errno_code == "-121"

    # Event 3: PCIE_AER_ERROR
    e3 = report.events[3]
    assert e3.pattern_id == "PCIE_AER_ERROR"
    assert e3.subsystem == Subsystem.PCIE
    assert e3.severity == Severity.CRITICAL
    assert e3.bdf == "0000:00:01.0"

    # Event 4: THERMAL_ZONE_TRIP
    e4 = report.events[4]
    assert e4.pattern_id == "THERMAL_ZONE_TRIP"
    assert e4.subsystem == Subsystem.THERMAL

    # Event 5: WATCHDOG_TIMEOUT
    e5 = report.events[5]
    assert e5.pattern_id == "WATCHDOG_TIMEOUT"
    assert e5.subsystem == Subsystem.WATCHDOG
    assert e5.severity == Severity.CRITICAL


def test_journalctl_parsing_and_extraction() -> None:
    """Verify extraction of journalctl / OpenBMC daemon log events."""
    log_text = """
Sep 01 12:00:00 bmc-yv4 psusensor[1024]: Sensor /xyz/openbmc_project/sensors/power/PSU0_Power not available: -110
Sep 01 12:00:01 bmc-yv4 entity-manager[512]: Probe failed for /xyz/openbmc_project/inventory/system/chassis: Configuration not found
Sep 01 12:00:02 bmc-yv4 phosphor-state-manager[768]: Chassis power state changed to xyz.openbmc_project.State.Chassis.PowerState.Off
"""
    report = LogParser.parse_log_text(log_text)
    assert report.source_type == LogSourceType.JOURNALCTL
    assert len(report.events) == 3
    assert report.events[0].pattern_id == "DBUS_SENSOR_UNAVAILABLE"
    assert report.events[1].pattern_id == "ENTITY_MANAGER_NO_MATCH"
    assert report.events[2].pattern_id == "PHOSPHOR_STATE_TRANSITION"


def test_incident_correlation_and_hypothesis() -> None:
    """Verify grouping of related hardware errors into correlated incidents."""
    log_text = """
[   10.000000] i2c-2: client at 0x4c: No such device or address (-ENXIO)
[   10.050000] tmp421 2-004c: probe of 2-004c failed with error -121
[   15.000000] pcieport 0000:00:01.0: AER: Uncorrectable error received
[   15.010000] pcieport 0000:00:01.0: PCIe Bus Error: severity=Uncorrected
"""
    report = LogParser.parse_log_text(log_text)
    assert len(report.events) == 4
    assert len(report.incidents) == 2

    inc1 = report.incidents[0]
    assert inc1.id == "INC-001"
    assert len(inc1.events) == 2
    assert inc1.subsystem in (Subsystem.I2C, Subsystem.HWMON)
    assert inc1.severity == Severity.ERROR
    assert "i2c" in str(inc1.related_tool_page).lower()
    assert len(inc1.recommended_actions) >= 1

    inc2 = report.incidents[1]
    assert inc2.id == "INC-002"
    assert len(inc2.events) == 2
    assert inc2.subsystem == Subsystem.PCIE
    assert inc2.severity == Severity.CRITICAL
    assert inc2.related_tool_page == "pcie"


def test_board_profile_enrichment() -> None:
    """Verify board profile topology integration into incident context."""
    profile_path = Path("examples/data/board_yv4.yaml")
    board_profile = load_board_profile(profile_path)

    log_text = """
[   15.200300] i2c-1: client at 0x50: No such device or address (-ENXIO)
"""
    report = LogParser.parse_log_text(log_text, board_profile=board_profile)
    assert len(report.incidents) == 1
    incident = report.incidents[0]
    assert incident.board_context is not None
    assert "baseboard-fru-eeprom" in incident.board_context
    assert "atmel,24c64" in incident.board_context
    assert "Bus 1" in incident.board_context
    assert "0x50" in incident.board_context


def test_summary_metrics_and_json_export() -> None:
    """Verify metrics calculation and full report JSON serializability."""
    log_text = """
[   10.000000] i2c-1: client at 0x50: No such device or address (-ENXIO)
[   20.000000] pcieport 0000:00:01.0: AER: Uncorrectable error received
"""
    report = LogParser.parse_log_text(log_text)
    summary = report.summary
    assert summary.total_events == 2
    assert summary.total_incidents == 2
    assert summary.time_span_seconds == pytest.approx(10.0)
    assert "i2c" in summary.subsystem_counts
    assert "pcie" in summary.subsystem_counts

    json_str = report.to_json()
    loaded = json.loads(json_str)
    assert loaded["summary"]["total_events"] == 2
    assert len(loaded["incidents"]) == 2
