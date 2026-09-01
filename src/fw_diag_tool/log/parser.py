"""System log parser engine and incident correlation logic."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fw_diag_tool.board_profile import BoardProfile
from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log.models import (
    Incident,
    LogEvent,
    LogReport,
    LogSourceType,
    LogSummary,
    Subsystem,
)
from fw_diag_tool.log.patterns import PATTERN_LIBRARY

_DMESG_TS_RE = re.compile(r"^\s*\[\s*(\d+\.\d+)\]")
_JOURNAL_TS_RE = re.compile(
    r"^(?:([A-Za-z]{3}\s+\d+\s+\d{2}:\d{2}:\d{2})|(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?))"
)
_JOURNAL_DAEMON_RE = re.compile(r"(?:^|\s)[a-zA-Z0-9_\-\.]+\[\d+\]:")
_BDF_RE = re.compile(r"\b([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F])\b")
_DRIVER_RE = re.compile(
    r"(?:\[\s*\d+\.\d+\]\s+)?([a-zA-Z0-9_\-]+)(?:\[\d+\])?(?:\s+[0-9a-fA-F\-:\.]+)?\s*:\s*"
)
_ERRNO_NAME_RE = re.compile(r"\((-E[A-Z]+)\)|\b(-E[A-Z]+)\b")
_ERRNO_NUM_RE = re.compile(
    r"(?:failed with error|error|status|errno)\s*[:=]?\s*(-?\d+)", re.IGNORECASE
)
_ERRNO_TRAILING_RE = re.compile(r":\s*(-?\d+)\s*$")

_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}

_RELATED_TOOL_PAGES: dict[Subsystem, str] = {
    Subsystem.I2C: "i2c-diagnosis",
    Subsystem.HWMON: "i2c-diagnosis",
    Subsystem.PCIE: "pcie",
    Subsystem.SPI: "spi",
    Subsystem.MCTP: "mctp",
    Subsystem.THERMAL: "thermal",
    Subsystem.POWER: "power",
    Subsystem.WATCHDOG: "watchdog",
    Subsystem.GPIO: "gpio",
    Subsystem.USB: "usb",
}


class LogParser:
    """Parser and correlation engine for firmware and system diagnostic logs."""

    @classmethod
    def parse_log_text(
        cls,
        text: str,
        *,
        board_profile: BoardProfile | None = None,
    ) -> LogReport:
        """Parse raw log text into a structured LogReport with incidents and summary."""
        if not text or not text.strip():
            return LogReport(
                source_type=LogSourceType.DMESG,
                events=[],
                incidents=[],
                summary=LogSummary(
                    total_lines=0,
                    total_events=0,
                    total_incidents=0,
                    subsystem_counts={},
                    severity_counts={},
                    time_span_seconds=None,
                ),
            )

        lines = text.strip().splitlines()
        source_type = cls._detect_source_type(lines)
        events = cls._extract_events(lines, source_type)
        incidents = cls._correlate_incidents(events, board_profile)
        summary = cls._build_summary(lines, events, incidents)

        return LogReport(
            source_type=source_type,
            events=events,
            incidents=incidents,
            summary=summary,
        )

    @classmethod
    def _detect_source_type(cls, lines: list[str]) -> LogSourceType:
        """Detect whether log originates from dmesg, journalctl, or a mixed source."""
        dmesg_count = sum(1 for line in lines if _DMESG_TS_RE.search(line))
        journalctl_count = sum(
            1 for line in lines if _JOURNAL_TS_RE.search(line) or _JOURNAL_DAEMON_RE.search(line)
        )

        if dmesg_count > 0 and journalctl_count > 0:
            return LogSourceType.MIXED
        if journalctl_count > dmesg_count:
            return LogSourceType.JOURNALCTL
        return LogSourceType.DMESG

    @classmethod
    def _extract_timestamp(cls, line: str, source_type: LogSourceType) -> float | None:
        """Extract timestamp in seconds from a log line."""
        m_dmesg = _DMESG_TS_RE.search(line)
        if m_dmesg:
            return float(m_dmesg.group(1))

        m_journal = _JOURNAL_TS_RE.search(line)
        if m_journal:
            syslog_str = m_journal.group(1)
            iso_str = m_journal.group(2)
            if syslog_str:
                try:
                    dt = datetime.strptime(syslog_str, "%b %d %H:%M:%S").replace(
                        year=2026, tzinfo=timezone.utc
                    )
                    return dt.timestamp()
                except ValueError:
                    pass
            elif iso_str:
                try:
                    dt = datetime.fromisoformat(iso_str)
                    return dt.timestamp()
                except ValueError:
                    pass
        return None

    @classmethod
    def _extract_bus_address(
        cls, line: str, extra: dict[str, Any]
    ) -> tuple[int | None, int | None]:
        """Extract I2C bus number and 7-bit slave address from log line."""
        bus: int | None = None
        address: int | None = None

        m_dev = re.search(r"\b(\d+)-([0-9a-fA-F]{4})\b", line)
        if m_dev:
            bus = int(m_dev.group(1))
            address = int(m_dev.group(2), 16)
            return bus, address

        m_bus = re.search(r"\b(?:i2c[-_]|i2c\s+|bus\s+)(\d+)\b", line, re.IGNORECASE)
        if m_bus:
            bus = int(m_bus.group(1))

        m_addr = re.search(
            r"(?:client at|slave at|address|addr|at address)\s*(?:0x)?([0-9a-fA-F]{2})\b",
            line,
            re.IGNORECASE,
        )
        if m_addr:
            address = int(m_addr.group(1), 16)
        elif bus is not None:
            m_hex = re.search(r"\b0x([0-9a-fA-F]{2})\b", line)
            if m_hex:
                val = int(m_hex.group(1), 16)
                if 0x08 <= val <= 0x77:
                    address = val

        return bus, address

    @classmethod
    def _extract_events(cls, lines: list[str], source_type: LogSourceType) -> list[LogEvent]:
        """Match log lines against the pattern library and extract structured LogEvents."""
        events: list[LogEvent] = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            for pattern in PATTERN_LIBRARY:
                if not pattern.regex.search(line_str):
                    continue

                timestamp = cls._extract_timestamp(line_str, source_type)
                extra: dict[str, Any] = {}
                bus, address = cls._extract_bus_address(line_str, extra)

                bdf: str | None = None
                m_bdf = _BDF_RE.search(line_str)
                if m_bdf:
                    bdf = m_bdf.group(1)

                driver: str | None = None
                m_drv = _DRIVER_RE.search(line_str)
                if m_drv:
                    driver = m_drv.group(1)

                errno_code: str | None = None
                m_errno_name = _ERRNO_NAME_RE.search(line_str)
                if m_errno_name:
                    errno_code = m_errno_name.group(1) or m_errno_name.group(2)
                else:
                    m_errno_num = _ERRNO_NUM_RE.search(line_str)
                    if m_errno_num:
                        errno_code = m_errno_num.group(1)
                    else:
                        m_trailing = _ERRNO_TRAILING_RE.search(line_str)
                        if m_trailing:
                            errno_code = m_trailing.group(1)

                event = LogEvent(
                    timestamp=timestamp,
                    subsystem=pattern.subsystem,
                    severity=pattern.severity,
                    message=line_str,
                    bus=bus,
                    address=address,
                    bdf=bdf,
                    driver=driver,
                    errno_code=errno_code,
                    extra=extra,
                    pattern_id=pattern.id,
                    triage_hint=pattern.triage_hint,
                )
                events.append(event)
                break

        return events

    @classmethod
    def _correlate_incidents(
        cls,
        events: list[LogEvent],
        board_profile: BoardProfile | None,
    ) -> list[Incident]:
        """Correlate log events sharing physical context into Incidents with root cause hypotheses."""
        groups: dict[str, list[LogEvent]] = {}
        for event in events:
            if event.bus is not None and event.address is not None:
                key = f"i2c:bus{event.bus}:addr{event.address}"
            elif event.bus is not None:
                key = f"i2c:bus{event.bus}"
            elif event.bdf is not None:
                key = f"{event.subsystem.value}:bdf:{event.bdf}"
            else:
                key = f"{event.subsystem.value}:{event.pattern_id or 'general'}"
            groups.setdefault(key, []).append(event)

        incidents: list[Incident] = []
        for idx, (_, ev_list) in enumerate(groups.items(), start=1):
            inc_id = f"INC-{idx:03d}"
            max_sev = max(ev_list, key=lambda e: _SEVERITY_ORDER.get(e.severity, 0)).severity

            has_i2c = any(e.subsystem in (Subsystem.I2C, Subsystem.HWMON) for e in ev_list)
            if has_i2c and any(e.bus is not None for e in ev_list):
                primary_subsystem = Subsystem.I2C
            else:
                primary_subsystem = ev_list[0].subsystem

            first_event = ev_list[0]
            if first_event.bus is not None and first_event.address is not None:
                title = f"I2C Bus {first_event.bus} Device 0x{first_event.address:02X} Communication Failure"
            elif first_event.bus is not None:
                title = f"I2C Bus {first_event.bus} Anomaly"
            elif first_event.bdf is not None:
                title = f"PCIe Device {first_event.bdf} Error"
            elif primary_subsystem == Subsystem.WATCHDOG:
                title = "Watchdog Timeout and System Reset"
            elif primary_subsystem == Subsystem.THERMAL:
                title = "Thermal Alert and Throttling"
            elif primary_subsystem == Subsystem.POWER:
                title = "Power Supply or Rail Fault"
            else:
                title = f"{primary_subsystem.value.upper()} Diagnostic Incident"

            pattern_ids = {e.pattern_id for e in ev_list}
            if ("I2C_DW_TX_ABORT" in pattern_ids and "HWMON_PROBE_FAIL" in pattern_ids) or (
                "HWMON_PROBE_FAIL" in pattern_ids
                and any(e.subsystem == Subsystem.I2C for e in ev_list)
            ):
                hypothesis = "I2C controller abort caused downstream sensor probe failure"
            elif "I2C_SLAVE_ENXIO" in pattern_ids or "I2C_TRANSFER_TIMEOUT" in pattern_ids:
                hypothesis = "I2C slave device not responding or bus line held low"
            elif "PCIE_AER_ERROR" in pattern_ids or "PCIE_LINK_DOWN" in pattern_ids:
                hypothesis = "PCIe physical link degradation or uncorrectable protocol error"
            elif "THERMAL_ZONE_TRIP" in pattern_ids or "THERMAL_CRITICAL" in pattern_ids:
                hypothesis = "Thermal threshold exceeded, cooling or airflow constraint"
            elif "WATCHDOG_TIMEOUT" in pattern_ids:
                hypothesis = "System watchdog expired due to kernel hang or unresponsive task"
            elif "POWER_SUPPLY_FAULT" in pattern_ids:
                hypothesis = "Power supply rail anomaly or PMBus hardware fault"
            else:
                hypothesis = f"Identified {len(ev_list)} correlated anomaly event(s) in {primary_subsystem.value} subsystem"

            actions: list[str] = []
            for e in ev_list:
                if e.triage_hint and e.triage_hint not in actions:
                    actions.append(e.triage_hint)
                    if len(actions) == 5:
                        break

            related_tool_page = _RELATED_TOOL_PAGES.get(primary_subsystem)
            board_context = cls._enrich_with_board_profile(ev_list, board_profile)

            inc = Incident(
                id=inc_id,
                title=title,
                subsystem=primary_subsystem,
                severity=max_sev,
                events=ev_list,
                root_cause_hypothesis=hypothesis,
                recommended_actions=actions,
                related_tool_page=related_tool_page,
                board_context=board_context,
            )
            incidents.append(inc)

        return incidents

    @classmethod
    def _build_summary(
        cls,
        lines: list[str],
        events: list[LogEvent],
        incidents: list[Incident],
    ) -> LogSummary:
        """Calculate metrics, categorical distributions, and time spans across log entries."""
        total_lines = len(lines)
        total_events = len(events)
        total_incidents = len(incidents)

        subsystem_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        timestamps: list[float] = []

        for e in events:
            subsystem_counts[e.subsystem.value] = subsystem_counts.get(e.subsystem.value, 0) + 1
            severity_counts[e.severity.value] = severity_counts.get(e.severity.value, 0) + 1
            if e.timestamp is not None:
                timestamps.append(e.timestamp)

        time_span = (max(timestamps) - min(timestamps)) if timestamps else None

        return LogSummary(
            total_lines=total_lines,
            total_events=total_events,
            total_incidents=total_incidents,
            subsystem_counts=subsystem_counts,
            severity_counts=severity_counts,
            time_span_seconds=time_span,
        )

    @classmethod
    def _enrich_with_board_profile(
        cls,
        events: list[LogEvent],
        profile: BoardProfile | None,
    ) -> str | None:
        """Look up device identity and topology in BoardProfile for bus and address."""
        if profile is None:
            return None

        for event in events:
            if event.bus is not None and event.address is not None:
                for bus_prof in profile.i2c_buses:
                    if bus_prof.bus_num == event.bus:
                        for dev in bus_prof.devices:
                            if dev.address_7bit == event.address:
                                return (
                                    f"Board profile identifies Bus {event.bus} Address 0x{event.address:02X} "
                                    f"as '{dev.name}' ({dev.compatible})"
                                )
                        for mux in bus_prof.muxes:
                            if mux.address_7bit == event.address:
                                return (
                                    f"Board profile identifies Bus {event.bus} Address 0x{event.address:02X} "
                                    f"as '{mux.name}' ({mux.compatible})"
                                )
                            for ch in mux.channels:
                                for dev in ch.devices:
                                    if dev.address_7bit == event.address:
                                        return (
                                            f"Board profile identifies Bus {event.bus} (MUX ch{ch.channel}) "
                                            f"Address 0x{event.address:02X} as '{dev.name}' ({dev.compatible})"
                                        )
        return None
