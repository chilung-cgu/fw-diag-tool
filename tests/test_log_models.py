"""Unit tests for Log Analysis Data Models and Pattern Library."""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log.models import (
    Incident,
    LogEvent,
    LogReport,
    LogSourceType,
    LogSummary,
    Subsystem,
)
from fw_diag_tool.log.patterns import PATTERN_LIBRARY, LogPattern


def test_log_source_type_enum() -> None:
    """Verify LogSourceType enum values."""
    assert LogSourceType.DMESG == "dmesg"
    assert LogSourceType.JOURNALCTL == "journalctl"
    assert LogSourceType.MIXED == "mixed"
    assert len(LogSourceType) == 3


def test_subsystem_enum() -> None:
    """Verify Subsystem enum contains all expected hardware and firmware subsystems."""
    expected = {
        "i2c": Subsystem.I2C,
        "pcie": Subsystem.PCIE,
        "hwmon": Subsystem.HWMON,
        "spi": Subsystem.SPI,
        "mctp": Subsystem.MCTP,
        "gpio": Subsystem.GPIO,
        "watchdog": Subsystem.WATCHDOG,
        "thermal": Subsystem.THERMAL,
        "power": Subsystem.POWER,
        "usb": Subsystem.USB,
        "general": Subsystem.GENERAL,
    }
    for val, enum_obj in expected.items():
        assert enum_obj.value == val
    assert len(Subsystem) >= 11


def test_log_event_frozen_and_dict() -> None:
    """Verify LogEvent is an immutable frozen dataclass and serializes to dict."""
    event = LogEvent(
        timestamp=12.345678,
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        message="i2c-1: controller timed out",
        bus=1,
        address=0x50,
        bdf=None,
        driver="i2c_designware",
        errno_code="-ETIMEDOUT",
        extra={"retry_count": 3},
        pattern_id="I2C_TRANSFER_TIMEOUT",
        triage_hint="Check SCL/SDA bus pull-up voltage or slave clock stretching",
    )
    assert event.timestamp == 12.345678
    assert event.subsystem == Subsystem.I2C
    assert event.severity == Severity.ERROR
    assert event.bus == 1
    assert event.address == 0x50
    assert event.pattern_id == "I2C_TRANSFER_TIMEOUT"

    d = event.to_dict()
    assert d["timestamp"] == 12.345678
    assert d["subsystem"] == "i2c"
    assert d["severity"] == "ERROR"
    assert d["address"] == "0x50"
    assert d["errno_code"] == "-ETIMEDOUT"

    with pytest.raises(FrozenInstanceError):
        event.timestamp = 99.0  # type: ignore[misc]


def test_incident_frozen_and_dict() -> None:
    """Verify Incident dataclass holds correlated events, is frozen, and serializes."""
    event = LogEvent(
        timestamp=100.1,
        subsystem=Subsystem.PCIE,
        severity=Severity.CRITICAL,
        message="pcieport 0000:00:01.0: AER: Uncorrectable error received",
        bdf="0000:00:01.0",
        pattern_id="PCIE_AER_ERROR",
        triage_hint="Check PCIe lane signal integrity and AER status registers",
    )
    incident = Incident(
        id="INC-PCIE-001",
        title="PCIe Uncorrectable AER Error",
        subsystem=Subsystem.PCIE,
        severity=Severity.CRITICAL,
        events=[event],
        root_cause_hypothesis="Physical link degradation on root port 0000:00:01.0",
        recommended_actions=["Inspect Eye Diagram", "Verify PCIe RefClk Jitter"],
        related_tool_page="pcie_analyzer",
        board_context="Yosemite 4 Slot 1",
    )
    assert incident.id == "INC-PCIE-001"
    assert incident.subsystem == Subsystem.PCIE
    assert len(incident.events) == 1
    assert incident.related_tool_page == "pcie_analyzer"

    d = incident.to_dict()
    assert d["id"] == "INC-PCIE-001"
    assert d["subsystem"] == "pcie"
    assert d["severity"] == "CRITICAL"
    assert d["event_count"] == 1
    assert len(d["events"]) == 1
    assert d["events"][0]["bdf"] == "0000:00:01.0"

    with pytest.raises(FrozenInstanceError):
        incident.title = "Changed Title"  # type: ignore[misc]


def test_log_summary_frozen_and_dict() -> None:
    """Verify LogSummary counts, immutability, and serialization."""
    summary = LogSummary(
        total_lines=1500,
        total_events=12,
        total_incidents=3,
        subsystem_counts={"i2c": 8, "pcie": 4},
        severity_counts={"ERROR": 10, "CRITICAL": 2},
        time_span_seconds=345.678912,
    )
    assert summary.total_lines == 1500
    assert summary.total_events == 12
    assert summary.total_incidents == 3
    assert summary.subsystem_counts["i2c"] == 8

    d = summary.to_dict()
    assert d["total_lines"] == 1500
    assert d["time_span_seconds"] == 345.678912

    with pytest.raises(FrozenInstanceError):
        summary.total_lines = 0  # type: ignore[misc]


def test_log_report_structure_and_json() -> None:
    """Verify complete LogReport structure and JSON serialization."""
    event = LogEvent(
        timestamp=1.0,
        subsystem=Subsystem.THERMAL,
        severity=Severity.WARNING,
        message="thermal thermal_zone0: critical temperature reached (105 C)",
        pattern_id="THERMAL_ZONE_TRIP",
        triage_hint="Check fan speed and heatsink mounting",
    )
    incident = Incident(
        id="INC-THM-01",
        title="Thermal Zone 0 Overheat",
        subsystem=Subsystem.THERMAL,
        severity=Severity.WARNING,
        events=[event],
        root_cause_hypothesis="Insufficient airflow or fan failure",
        recommended_actions=["Check chassis fan RPM"],
    )
    summary = LogSummary(
        total_lines=10,
        total_events=1,
        total_incidents=1,
        subsystem_counts={"thermal": 1},
        severity_counts={"WARNING": 1},
        time_span_seconds=0.0,
    )
    report = LogReport(
        source_type=LogSourceType.DMESG,
        events=[event],
        incidents=[incident],
        summary=summary,
    )
    assert report.source_type == LogSourceType.DMESG
    assert len(report.events) == 1
    assert len(report.incidents) == 1
    assert report.summary.total_events == 1

    d = report.to_dict()
    assert d["source_type"] == "dmesg"
    assert len(d["events"]) == 1
    assert len(d["incidents"]) == 1

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["source_type"] == "dmesg"
    assert parsed["summary"]["total_events"] == 1

    with pytest.raises(FrozenInstanceError):
        report.source_type = LogSourceType.JOURNALCTL  # type: ignore[misc]


def test_pattern_library_size_and_uniqueness() -> None:
    """Verify pattern library has >= 20 patterns and all IDs are unique."""
    assert len(PATTERN_LIBRARY) >= 20
    pattern_ids = [p.id for p in PATTERN_LIBRARY]
    assert len(pattern_ids) == len(set(pattern_ids)), f"Duplicate pattern IDs found: {pattern_ids}"


def test_pattern_library_attributes() -> None:
    """Verify every pattern adheres to LogPattern schema."""
    for p in PATTERN_LIBRARY:
        assert isinstance(p, LogPattern)
        assert isinstance(p.id, str) and len(p.id) > 0
        assert isinstance(p.subsystem, Subsystem)
        assert isinstance(p.severity, Severity)
        assert isinstance(p.regex, re.Pattern)
        assert isinstance(p.extract_fields, list)
        assert isinstance(p.triage_hint, str) and len(p.triage_hint) > 0
        assert isinstance(p.description, str) and len(p.description) > 0


@pytest.mark.parametrize(
    ("pattern_id", "sample_line"),
    [
        (
            "I2C_DW_TX_ABORT",
            "[  12.345678] i2c_designware 0000:00:15.0: i2c_dw_handle_tx_abort: lost arbitration",
        ),
        (
            "I2C_TRANSFER_TIMEOUT",
            "[  14.100200] i2c i2c-1: controller timed out waiting for bus",
        ),
        (
            "I2C_SLAVE_ENXIO",
            "[  15.200300] i2c-1: client at 0x50: No such device or address (-ENXIO)",
        ),
        (
            "I2C_BUS_RECOVERY",
            "[  16.300400] i2c i2c-2: bus recovery failed: -110",
        ),
        (
            "I2C_LOST_ARBITRATION",
            "[  17.400500] i2c-core: master_send lost arbitration on bus 3",
        ),
        (
            "HWMON_PROBE_FAIL",
            "[  18.500600] tmp421 2-004c: probe of 2-004c failed with error -121",
        ),
        (
            "HWMON_READ_FAIL",
            "[  19.600700] hwmon hwmon1: Failed to read sensor value: -110",
        ),
        (
            "PCIE_AER_ERROR",
            "[  20.700800] pcieport 0000:00:01.0: AER: Uncorrectable error received: 0000:01:00.0",
        ),
        (
            "PCIE_LINK_DOWN",
            "[  21.800900] pcieport 0000:00:01.0: pciehp: Slot(1): Link Down",
        ),
        (
            "PCIE_BUS_ERROR",
            "[  22.901000] pcieport 0000:00:01.0: PCIe Bus Error: severity=Corrected, type=Physical Layer",
        ),
        (
            "THERMAL_ZONE_TRIP",
            "[  23.001100] thermal thermal_zone0: critical temperature reached (105 C), shutting down",
        ),
        (
            "THERMAL_CRITICAL",
            "[  24.101200] cpu: critical thermal condition detected, throttling active",
        ),
        (
            "POWER_SUPPLY_FAULT",
            "[  25.201300] power_supply psu1: fault detected: power good lost",
        ),
        (
            "WATCHDOG_TIMEOUT",
            "[  26.301400] watchdog: watchdog0: watchdog timeout occurred, system reset pending",
        ),
        (
            "GPIO_REQUEST_FAIL",
            "[  27.401500] gpiolib: failed to request GPIO 42: -16",
        ),
        (
            "DBUS_SENSOR_UNAVAILABLE",
            "psusensor[1024]: Sensor /xyz/openbmc_project/sensors/power/PSU0_Power not available: -110",
        ),
        (
            "ENTITY_MANAGER_NO_MATCH",
            "entity-manager[512]: Probe failed for /xyz/openbmc_project/inventory/system/chassis: Configuration not found",
        ),
        (
            "PHOSPHOR_STATE_TRANSITION",
            "phosphor-state-manager[768]: Chassis power state changed to xyz.openbmc_project.State.Chassis.PowerState.Off",
        ),
        (
            "SPI_NOR_TIMEOUT",
            "[  28.501600] spi-nor spi0.0: timeout waiting for erase completion",
        ),
        (
            "MCTP_ROUTE_FAIL",
            "mctpd[890]: failed to route packet to destination EID 18: no route to host",
        ),
        (
            "USB_DEVICE_OVER_CURRENT",
            "[  29.601700] usb usb1-port2: over-current condition",
        ),
        (
            "MEMORY_ECC_ERROR",
            "[  30.701800] EDAC MC0: 1 CE correctable error on DIMM_A1",
        ),
    ],
)
def test_patterns_match_samples(pattern_id: str, sample_line: str) -> None:
    """Verify that specific representative patterns correctly match expected failure logs."""
    matching_patterns = [p for p in PATTERN_LIBRARY if p.id == pattern_id]
    assert len(matching_patterns) == 1, f"Pattern with ID {pattern_id} not found"
    pattern = matching_patterns[0]
    match = pattern.regex.search(sample_line)
    assert match is not None, f"Pattern {pattern_id} ({pattern.regex.pattern}) did not match: {sample_line}"

