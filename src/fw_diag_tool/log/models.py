"""Log data models and structured diagnostic report representations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fw_diag_tool.i2c.models import Severity


class LogSourceType(str, Enum):
    """Source format of the ingested log."""

    DMESG = "dmesg"
    JOURNALCTL = "journalctl"
    MIXED = "mixed"


class Subsystem(str, Enum):
    """Hardware or firmware subsystem associated with a log entry or incident."""

    I2C = "i2c"
    PCIE = "pcie"
    HWMON = "hwmon"
    SPI = "spi"
    MCTP = "mctp"
    GPIO = "gpio"
    WATCHDOG = "watchdog"
    THERMAL = "thermal"
    POWER = "power"
    USB = "usb"
    GENERAL = "general"


@dataclass(frozen=True)
class LogEvent:
    """Normalized structured event extracted from a raw log entry."""

    timestamp: float | None = None
    subsystem: Subsystem = Subsystem.GENERAL
    severity: Severity = Severity.INFO
    message: str = ""
    bus: int | None = None
    address: int | None = None
    bdf: str | None = None
    driver: str | None = None
    errno_code: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    pattern_id: str = ""
    triage_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "timestamp": self.timestamp,
            "subsystem": self.subsystem.value,
            "severity": self.severity.value,
            "message": self.message,
            "bus": self.bus,
            "address": f"0x{self.address:02X}" if self.address is not None else None,
            "bdf": self.bdf,
            "driver": self.driver,
            "errno_code": self.errno_code,
            "extra": self.extra,
            "pattern_id": self.pattern_id,
            "triage_hint": self.triage_hint,
        }


@dataclass(frozen=True)
class Incident:
    """Correlated group of log events representing a distinct diagnostic issue."""

    id: str
    title: str
    subsystem: Subsystem
    severity: Severity
    events: list[LogEvent] = field(default_factory=list)
    root_cause_hypothesis: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    related_tool_page: str | None = None
    board_context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert incident to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "subsystem": self.subsystem.value,
            "severity": self.severity.value,
            "events": [e.to_dict() for e in self.events],
            "event_count": len(self.events),
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "recommended_actions": self.recommended_actions,
            "related_tool_page": self.related_tool_page,
            "board_context": self.board_context,
        }


@dataclass(frozen=True)
class LogSummary:
    """Aggregate metrics and categorical counts across analyzed log entries."""

    total_lines: int = 0
    total_events: int = 0
    total_incidents: int = 0
    subsystem_counts: dict[str, int] = field(default_factory=dict)
    severity_counts: dict[str, int] = field(default_factory=dict)
    time_span_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert summary to dictionary."""
        return {
            "total_lines": self.total_lines,
            "total_events": self.total_events,
            "total_incidents": self.total_incidents,
            "subsystem_counts": self.subsystem_counts,
            "severity_counts": self.severity_counts,
            "time_span_seconds": (
                round(self.time_span_seconds, 6) if self.time_span_seconds is not None else None
            ),
        }


@dataclass(frozen=True)
class LogReport:
    """Complete system diagnostic report containing events, incidents, and summary."""

    source_type: LogSourceType = LogSourceType.MIXED
    events: list[LogEvent] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    summary: LogSummary = field(default_factory=LogSummary)

    def to_dict(self) -> dict[str, Any]:
        """Convert full report to dictionary."""
        return {
            "source_type": self.source_type.value,
            "summary": self.summary.to_dict(),
            "events": [e.to_dict() for e in self.events],
            "incidents": [inc.to_dict() for inc in self.incidents],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

