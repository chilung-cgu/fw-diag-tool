# v2.0.0 System-Level Correlation & Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Linux Kernel / OpenBMC log correlation engine and an Entity-Manager visual JSON builder to fw-diag-tool, transforming it from a bottom-up protocol analyzer into an end-to-end firmware diagnostic suite.

**Architecture:** Two independent subsystems — a heuristic log parser that extracts hardware events from dmesg/journalctl and correlates them into triageable Incidents, and a template-driven EM JSON builder/validator modeled after the existing DTS generator. Both integrate into the GUI as new pages and into the CLI as new subcommands.

**Tech Stack:** Python 3.10+, Streamlit 1.62, Typer, Rich, Pydantic v2, pytest, dataclasses (frozen), regex pattern library

**Spec:** docs/superpowers/specs/2026-09-01-system-diagnostics-design.md

## Global Constraints

- Python >= 3.10 (no tomllib; use tomli if needed)
- All commands via `uv run`
- Traditional Chinese (zh-TW) for all GUI strings; register in i18n/domains/gui.py
- Follow existing patterns: frozen dataclasses for results, classmethod parsers, AnalysisLimits guard
- Zero LaTeX in any output
- Git identity from existing ~/.gitconfig
- Do not bump version until final verification task

---

### Task 1: Log Data Models and Pattern Library

**Files:**
- Create: `src/fw_diag_tool/log/__init__.py`
- Create: `src/fw_diag_tool/log/models.py`
- Create: `src/fw_diag_tool/log/patterns.py`
- Test: `tests/test_log_models.py`

**Interfaces:**
- Consumes: `fw_diag_tool.i2c.models.Severity` (reuse existing enum)
- Produces: `LogSourceType`, `Subsystem`, `LogEvent`, `Incident`, `LogSummary`, `LogReport`, `LogPattern`, `PATTERN_LIBRARY: list[LogPattern]`

- [ ] **Step 1: Write the failing test for data models**

```python
# tests/test_log_models.py
from __future__ import annotations

import pytest


def test_log_event_frozen():
    from fw_diag_tool.log.models import LogEvent, Subsystem
    from fw_diag_tool.i2c.models import Severity

    ev = LogEvent(
        timestamp=1.234,
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        message="i2c i2c-2: sendbytes: NAK bailout",
        bus=2,
        address=0x48,
        bdf=None,
        driver="i2c_designware",
        errno_code="ENXIO",
        extra={},
        pattern_id="I2C_NAK_BAILOUT",
        triage_hint="Check I2C bus 2 device 0x48 with fw-diag i2c analyzer",
    )
    assert ev.subsystem == Subsystem.I2C
    assert ev.bus == 2
    with pytest.raises(AttributeError):
        ev.bus = 3  # type: ignore[misc]


def test_log_source_type_values():
    from fw_diag_tool.log.models import LogSourceType

    assert LogSourceType.DMESG == "dmesg"
    assert LogSourceType.JOURNALCTL == "journalctl"
    assert LogSourceType.MIXED == "mixed"


def test_subsystem_values():
    from fw_diag_tool.log.models import Subsystem

    assert len(Subsystem) >= 10
    assert Subsystem.I2C == "i2c"
    assert Subsystem.PCIE == "pcie"
    assert Subsystem.HWMON == "hwmon"


def test_incident_frozen():
    from fw_diag_tool.log.models import Incident, Subsystem
    from fw_diag_tool.i2c.models import Severity

    inc = Incident(
        id="INC-001",
        title="I2C Bus 2 Device 0x48 Communication Failure",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        events=[],
        root_cause_hypothesis="Device not responding on bus",
        recommended_actions=["Check physical connection", "Verify pull-up resistors"],
        related_tool_page="i2c-diagnosis",
        board_context=None,
    )
    assert inc.id == "INC-001"
    assert inc.related_tool_page == "i2c-diagnosis"


def test_log_report_structure():
    from fw_diag_tool.log.models import LogReport, LogSourceType, LogSummary

    summary = LogSummary(
        total_lines=100,
        total_events=5,
        total_incidents=2,
        subsystem_counts={"i2c": 3, "pcie": 2},
        severity_counts={"error": 4, "warning": 1},
        time_span_seconds=120.5,
    )
    report = LogReport(
        source_type=LogSourceType.DMESG,
        events=[],
        incidents=[],
        summary=summary,
    )
    assert report.summary.total_events == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_models.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the log data models**

```python
# src/fw_diag_tool/log/__init__.py
"""System log correlation engine for dmesg and journalctl diagnostics."""

# src/fw_diag_tool/log/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fw_diag_tool.i2c.models import Severity


class LogSourceType(str, Enum):
    DMESG = "dmesg"
    JOURNALCTL = "journalctl"
    MIXED = "mixed"


class Subsystem(str, Enum):
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
    timestamp: float | None
    subsystem: Subsystem
    severity: Severity
    message: str
    bus: int | None
    address: int | None
    bdf: str | None
    driver: str | None
    errno_code: str | None
    extra: dict[str, Any]
    pattern_id: str
    triage_hint: str


@dataclass(frozen=True)
class Incident:
    id: str
    title: str
    subsystem: Subsystem
    severity: Severity
    events: list[LogEvent]
    root_cause_hypothesis: str
    recommended_actions: list[str]
    related_tool_page: str | None
    board_context: str | None


@dataclass(frozen=True)
class LogSummary:
    total_lines: int
    total_events: int
    total_incidents: int
    subsystem_counts: dict[str, int]
    severity_counts: dict[str, int]
    time_span_seconds: float | None


@dataclass(frozen=True)
class LogReport:
    source_type: LogSourceType
    events: list[LogEvent]
    incidents: list[Incident]
    summary: LogSummary
```

- [ ] **Step 4: Write the pattern library**

```python
# src/fw_diag_tool/log/patterns.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log.models import Subsystem


@dataclass(frozen=True)
class LogPattern:
    id: str
    subsystem: Subsystem
    severity: Severity
    regex: re.Pattern[str]
    extract_fields: list[str]
    triage_hint: str
    description: str


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# --- I2C Patterns ---
_I2C_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="I2C_DW_TX_ABORT",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=_compile(
            r"i2c[_-]designware\s+(?P<controller>[\w.]+):\s+"
            r"i2c_dw_handle_tx_abort:\s+(?P<reason>.+)"
        ),
        extract_fields=["controller", "reason"],
        triage_hint="Check I2C bus pull-up resistors and device presence with fw-diag I2C analyzer",
        description="DesignWare I2C controller TX abort",
    ),
    LogPattern(
        id="I2C_TRANSFER_TIMEOUT",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=_compile(
            r"i2c[_-](?:designware|aspeed)\s+(?P<controller>[\w.]+):\s+"
            r"(?:timeout|timed?\s*out).*?(?:bus\s*(?P<bus>\d+))?"
        ),
        extract_fields=["controller", "bus"],
        triage_hint="Possible clock stretching or bus hang; check with fw-diag I2C raw digital mode",
        description="I2C controller transfer timeout",
    ),
    LogPattern(
        id="I2C_SLAVE_ENXIO",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=_compile(r"i2c\s+i2c-(?P<bus>\d+):\s+sendbytes:\s+NAK\s+bailout"),
        extract_fields=["bus"],
        triage_hint="Device not responding; verify address and power state",
        description="I2C NAK during send — device not acknowledging",
    ),
    LogPattern(
        id="I2C_BUS_RECOVERY",
        subsystem=Subsystem.I2C,
        severity=Severity.WARNING,
        regex=_compile(
            r"i2c[_-](?:designware|aspeed)\s+(?P<controller>[\w.]+):\s+"
            r"(?:bus\s+recovery|trying\s+to\s+recover)"
        ),
        extract_fields=["controller"],
        triage_hint="Bus recovery attempted; check for stuck SDA line or clock stretching",
        description="I2C bus recovery initiated",
    ),
    LogPattern(
        id="I2C_LOST_ARBITRATION",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=_compile(
            r"i2c[_-](?:designware|aspeed)\s+(?P<controller>[\w.]+):\s+"
            r"lost\s+arbitration"
        ),
        extract_fields=["controller"],
        triage_hint="Multi-master conflict or noise; check bus topology",
        description="I2C arbitration lost — another master on bus",
    ),
]

# --- hwmon Patterns ---
_HWMON_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="HWMON_PROBE_FAIL",
        subsystem=Subsystem.HWMON,
        severity=Severity.ERROR,
        regex=_compile(
            r"(?P<driver>[\w_]+)\s+(?P<bus_addr>[\w.-]+):\s+"
            r"(?:probe\s+failed|Failed\s+to\s+(?:register|read|detect))"
            r".*?(?:err(?:or)?\s*=?\s*(?P<errno>-?\d+))?"
        ),
        extract_fields=["driver", "bus_addr", "errno"],
        triage_hint="Sensor driver probe failed; check I2C address and device presence",
        description="hwmon / sensor driver probe failure",
    ),
    LogPattern(
        id="HWMON_READ_FAIL",
        subsystem=Subsystem.HWMON,
        severity=Severity.WARNING,
        regex=_compile(
            r"(?P<driver>[\w_]+)\s+(?P<bus_addr>[\w.-]+):\s+"
            r"(?:failed\s+to\s+read|read\s+error|update\s+error)"
        ),
        extract_fields=["driver", "bus_addr"],
        triage_hint="Sensor read failure; may be intermittent I2C issue or power state problem",
        description="hwmon sensor read/update failure",
    ),
]

# --- PCIe Patterns ---
_PCIE_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="PCIE_AER_ERROR",
        subsystem=Subsystem.PCIE,
        severity=Severity.ERROR,
        regex=_compile(
            r"pcieport\s+(?P<bdf>[0-9a-fA-F:.]+):\s+AER:\s+"
            r"(?P<severity>Correctable|Fatal|Non-Fatal|Uncorrected)\s+error"
        ),
        extract_fields=["bdf", "severity"],
        triage_hint="Check PCIe AER registers with fw-diag pcie analyzer",
        description="PCIe Advanced Error Reporting event",
    ),
    LogPattern(
        id="PCIE_LINK_DOWN",
        subsystem=Subsystem.PCIE,
        severity=Severity.CRITICAL,
        regex=_compile(
            r"pci(?:eport)?\s+(?P<bdf>[0-9a-fA-F:.]+):\s+"
            r"(?:link\s+(?:down|disabled|not\s+ready)|no\s+link)"
        ),
        extract_fields=["bdf"],
        triage_hint="PCIe link failure; check physical slot and power",
        description="PCIe link down or disabled",
    ),
    LogPattern(
        id="PCIE_BUS_ERROR",
        subsystem=Subsystem.PCIE,
        severity=Severity.ERROR,
        regex=_compile(
            r"(?P<bdf>[0-9a-fA-F:.]+):\s+PCIe\s+Bus\s+Error:\s+"
            r"severity=(?P<err_severity>[^,]+),\s+type=(?P<err_type>[^,]+)"
        ),
        extract_fields=["bdf", "err_severity", "err_type"],
        triage_hint="Detailed PCIe bus error; correlate with AER dump",
        description="PCIe Bus Error with severity and type",
    ),
]

# --- Thermal / Power Patterns ---
_THERMAL_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="THERMAL_ZONE_TRIP",
        subsystem=Subsystem.THERMAL,
        severity=Severity.CRITICAL,
        regex=_compile(
            r"thermal\s+thermal_zone(?P<zone>\d+):\s+"
            r"(?P<trip_type>\w+)\s+point\s+(?P<trip_id>\d+)\s+reached"
        ),
        extract_fields=["zone", "trip_type", "trip_id"],
        triage_hint="Temperature threshold exceeded; check fan and thermal paste",
        description="Thermal zone trip point reached",
    ),
    LogPattern(
        id="THERMAL_CRITICAL",
        subsystem=Subsystem.THERMAL,
        severity=Severity.CRITICAL,
        regex=_compile(
            r"(?:critical\s+temperature\s+reached|"
            r"thermal_zone\d+.*?above.*?critical)"
        ),
        extract_fields=[],
        triage_hint="System at critical temperature; immediate action required",
        description="Critical temperature threshold",
    ),
]

_POWER_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="POWER_SUPPLY_FAULT",
        subsystem=Subsystem.POWER,
        severity=Severity.CRITICAL,
        regex=_compile(
            r"(?P<driver>[\w_]+)\s+(?P<bus_addr>[\w.-]+):\s+"
            r"(?:power\s+supply\s+fault|STATUS_WORD.*?fault|"
            r"VIN_UV_FAULT|VOUT_OV_FAULT|IOUT_OC_FAULT|OT_FAULT)"
        ),
        extract_fields=["driver", "bus_addr"],
        triage_hint="PMBus power supply fault; check STATUS_WORD with fw-diag I2C PMBus decoder",
        description="PMBus power supply fault condition",
    ),
]

# --- Watchdog Patterns ---
_WATCHDOG_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="WATCHDOG_TIMEOUT",
        subsystem=Subsystem.WATCHDOG,
        severity=Severity.CRITICAL,
        regex=_compile(r"(?:watchdog|wdt).*?(?:timeout|expired|triggered|reset)"),
        extract_fields=[],
        triage_hint="Watchdog fired; check system responsiveness and main loop health",
        description="Watchdog timer timeout or reset",
    ),
]

# --- GPIO Patterns ---
_GPIO_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="GPIO_REQUEST_FAIL",
        subsystem=Subsystem.GPIO,
        severity=Severity.ERROR,
        regex=_compile(
            r"(?:gpio[_-]\d+|gpiochip\d+).*?(?:failed\s+to\s+request|"
            r"request\s+failed|could\s+not\s+get)"
        ),
        extract_fields=[],
        triage_hint="GPIO request failed; check pin configuration and conflicts",
        description="GPIO request/allocation failure",
    ),
]

# --- OpenBMC user-space Patterns (journalctl) ---
_OPENBMC_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="DBUS_SENSOR_UNAVAILABLE",
        subsystem=Subsystem.HWMON,
        severity=Severity.WARNING,
        regex=_compile(
            r"(?:psusensor|adcsensor|fansensor|hwmontempsensor|"
            r"intrusionsensor|externalsensor).*?"
            r"(?:sensor\s+(?P<sensor_name>[\w_]+)\s+(?:not\s+found|unavailable|"
            r"failed)|(?:value|reading)\s+(?:error|unavailable))"
        ),
        extract_fields=["sensor_name"],
        triage_hint="dbus-sensors cannot read sensor; check EM config and hwmon driver",
        description="OpenBMC dbus-sensors service cannot read a sensor",
    ),
    LogPattern(
        id="ENTITY_MANAGER_NO_MATCH",
        subsystem=Subsystem.GENERAL,
        severity=Severity.WARNING,
        regex=_compile(
            r"entity[_-]manager.*?(?:no\s+(?:match|configuration)|"
            r"failed\s+to\s+find|unmatched)"
        ),
        extract_fields=[],
        triage_hint="Entity-Manager config mismatch; verify JSON config matches probed hardware",
        description="Entity-Manager configuration not matching probed devices",
    ),
    LogPattern(
        id="PHOSPHOR_STATE_TRANSITION",
        subsystem=Subsystem.POWER,
        severity=Severity.INFO,
        regex=_compile(
            r"(?:phosphor[_-]state[_-]manager|obmc[_-]host[_-]ctl).*?"
            r"(?:transition|moving).*?(?:to|->)\s*(?P<target_state>\w+)"
        ),
        extract_fields=["target_state"],
        triage_hint="Host power state change; sensor availability depends on this",
        description="OpenBMC host/chassis power state transition",
    ),
]

# --- SPI Patterns ---
_SPI_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="SPI_NOR_TIMEOUT",
        subsystem=Subsystem.SPI,
        severity=Severity.ERROR,
        regex=_compile(
            r"spi[_-]nor\s+spi(?P<bus>\d+)\.(?P<cs>\d+):\s+"
            r"(?:timeout|flash\s+(?:read|write|erase)\s+error)"
        ),
        extract_fields=["bus", "cs"],
        triage_hint="SPI NOR flash timeout; check chip select and bus speed",
        description="SPI NOR flash operation timeout",
    ),
]

# --- MCTP Patterns ---
_MCTP_PATTERNS: list[LogPattern] = [
    LogPattern(
        id="MCTP_ROUTE_FAIL",
        subsystem=Subsystem.MCTP,
        severity=Severity.ERROR,
        regex=_compile(
            r"mctp.*?(?:route.*?(?:failed|error|not\s+found)|"
            r"(?:no|missing)\s+route)"
        ),
        extract_fields=[],
        triage_hint="MCTP routing failure; check EID assignment and bus binding",
        description="MCTP route lookup or setup failure",
    ),
]

PATTERN_LIBRARY: list[LogPattern] = [
    *_I2C_PATTERNS,
    *_HWMON_PATTERNS,
    *_PCIE_PATTERNS,
    *_THERMAL_PATTERNS,
    *_POWER_PATTERNS,
    *_WATCHDOG_PATTERNS,
    *_GPIO_PATTERNS,
    *_OPENBMC_PATTERNS,
    *_SPI_PATTERNS,
    *_MCTP_PATTERNS,
]
```

- [ ] **Step 5: Write the pattern library test**

Add to `tests/test_log_models.py`:
```python
def test_pattern_library_not_empty():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    assert len(PATTERN_LIBRARY) >= 20


def test_pattern_ids_unique():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    ids = [p.id for p in PATTERN_LIBRARY]
    assert len(ids) == len(set(ids)), (
        f"Duplicate pattern IDs: {[x for x in ids if ids.count(x) > 1]}"
    )


def test_patterns_compile_and_match():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    # Every pattern must have a compiled regex that does not raise
    for p in PATTERN_LIBRARY:
        assert p.regex is not None
        assert p.regex.pattern  # non-empty


def test_i2c_nak_pattern_matches():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    line = "[  123.456789] i2c i2c-2: sendbytes: NAK bailout"
    nak_pattern = next(p for p in PATTERN_LIBRARY if p.id == "I2C_SLAVE_ENXIO")
    m = nak_pattern.regex.search(line)
    assert m is not None
    assert m.group("bus") == "2"


def test_pcie_aer_pattern_matches():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    line = "[  45.123] pcieport 0000:00:1c.0: AER: Correctable error received"
    aer_pattern = next(p for p in PATTERN_LIBRARY if p.id == "PCIE_AER_ERROR")
    m = aer_pattern.regex.search(line)
    assert m is not None
    assert m.group("bdf") == "0000:00:1c.0"
    assert m.group("severity") == "Correctable"


def test_hwmon_probe_pattern_matches():
    from fw_diag_tool.log.patterns import PATTERN_LIBRARY

    line = "[   12.345] tmp75 2-0048: probe failed, err = -6"
    probe_pattern = next(p for p in PATTERN_LIBRARY if p.id == "HWMON_PROBE_FAIL")
    m = probe_pattern.regex.search(line)
    assert m is not None
    assert m.group("driver") == "tmp75"
    assert m.group("bus_addr") == "2-0048"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_log_models.py -v`
Expected: PASS (all 10+ tests)

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/log/ tests/test_log_models.py
git commit -m "feat(log): add log data models and pattern library for dmesg/journalctl analysis"
```


---

### Task 2: Log Parser Engine

**Files:**
- Create: `src/fw_diag_tool/log/parser.py`
- Test: `tests/test_log_parser.py`

**Interfaces:**
- Consumes: `LogEvent`, `Incident`, `LogReport`, `LogSummary`, `LogSourceType`, `Subsystem` from `log/models.py`; `PATTERN_LIBRARY`, `LogPattern` from `log/patterns.py`; `BoardProfile` from `board_profile.py`
- Produces: `LogParser.parse_log_text(text, board_profile=None) -> LogReport` (classmethod)

- [ ] **Step 1: Write the failing test for log parser**

Create `tests/test_log_parser.py` with tests for: parse_dmesg_basic, parse_dmesg_extracts_i2c_events, parse_dmesg_extracts_pcie_events, parse_journalctl_basic, incident_correlation_groups_related_events, board_profile_enrichment, empty_log, clean_log_no_events. Use synthetic dmesg/journalctl strings containing at least I2C NAK, PCIe AER, hwmon probe fail, watchdog timeout, and thermal trip patterns.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_parser.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

Implement `LogParser` as a classmethod-based stateless parser:
- `parse_log_text(text, board_profile=None) -> LogReport`: entry point
- `_detect_source_type(lines)`: count dmesg timestamps vs journalctl prefixes
- `_extract_events(lines, source_type)`: iterate lines, match against PATTERN_LIBRARY, extract first matching pattern per line, build LogEvent with bus/address from regex groups or bus-addr pattern (e.g. "2-0048")
- `_correlate_incidents(events, board_profile)`: group events by subsystem+bus+address or subsystem+BDF key, generate Incident per group with title, hypothesis, actions, and optional board profile enrichment
- `_build_summary(lines, events, incidents)`: count by subsystem and severity, compute time span

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_log_parser.py -v`
Expected: PASS

- [ ] **Step 5: Run ruff and mypy**

Run: `uv run ruff check src/fw_diag_tool/log/ tests/test_log_parser.py`
Run: `uv run mypy src/fw_diag_tool/log/`

- [ ] **Step 6: Commit**

```bash
git add src/fw_diag_tool/log/parser.py tests/test_log_parser.py
git commit -m "feat(log): implement log parser engine with incident correlation"
```

---

### Task 3: Log Diff Engine

**Files:**
- Create: `src/fw_diag_tool/log/diff.py`
- Test: `tests/test_log_diff.py`

**Interfaces:**
- Consumes: `LogReport` from `log/models.py`
- Produces: `LogDiffEngine.compare(baseline: LogReport, candidate: LogReport) -> LogDiffResult` (classmethod)

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_diff.py` testing: identical logs -> is_identical=True, new incident detection, resolved incident detection, to_dict/to_json serialization.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_diff.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `LogDiffResult(frozen dataclass)` with: baseline_event_count, candidate_event_count, event_count_delta, new_incidents, resolved_incidents, common_incidents, new_event_patterns, resolved_event_patterns, summary, is_identical, to_dict(), to_json(). Implement `LogDiffEngine.compare()` using set operations on incident titles and event pattern_ids — same pattern as `I2CDiffEngine`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_log_diff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/log/diff.py tests/test_log_diff.py
git commit -m "feat(log): add log diff engine for baseline/candidate comparison"
```

---

### Task 4: Entity-Manager Data Models and Device Templates

**Files:**
- Create: `src/fw_diag_tool/em/__init__.py`
- Create: `src/fw_diag_tool/em/models.py`
- Create: `src/fw_diag_tool/em/templates.py`
- Test: `tests/test_em_models.py`

**Interfaces:**
- Consumes: `Severity` from `fw_diag_tool.i2c.models`
- Produces: `EMDeviceTemplate`, `EMDeviceEntry`, `EMBoardConfig`, `EMValidationIssue`, `DEVICE_TEMPLATES: dict[str, EMDeviceTemplate]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_em_models.py` testing: EMDeviceTemplate frozen, template catalog has 7+ categories (temperature, adc, fru, fan, psu, gpio, hotswap), EMDeviceEntry construction, EMBoardConfig with multiple devices, EMValidationIssue frozen.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_em_models.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the EM data models**

`em/models.py`: Define EMDeviceTemplate(frozen dataclass), EMDeviceEntry(dataclass), EMBoardConfig(dataclass), EMValidationIssue(frozen dataclass). EMDeviceTemplate fields: category, chip_name, em_type (the xyz.openbmc_project.Configuration.* string), default_power_state, required_fields, optional_fields, description.

- [ ] **Step 4: Write the device template catalog**

`em/templates.py`: Define DEVICE_TEMPLATES dict mapping chip_name to EMDeviceTemplate. Include at minimum:
- TMP75 (temperature, xyz.openbmc_project.Configuration.TMP75, PowerState="On")
- TMP421 (temperature)
- LM75 (temperature)
- EMC1413 (temperature)
- ADC128D818 (adc)
- AT24C256 (fru, xyz.openbmc_project.Configuration.AT24C256, PowerState="Always")
- MAX31790 (fan, xyz.openbmc_project.Configuration.MAX31790)
- EMC2305 (fan)
- PMBus PSU (psu, xyz.openbmc_project.Configuration.PMBus, PowerState="On")
- PCA9555 (gpio)
- ADM1272 (hotswap, xyz.openbmc_project.Configuration.ADM1272, PowerState="On")
- LTC4282 (hotswap)

Each template defines reasonable default thresholds where applicable (e.g., TMP75 WarningHigh=85, CriticalHigh=95 for Celsius).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_em_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/fw_diag_tool/em/ tests/test_em_models.py
git commit -m "feat(em): add Entity-Manager data models and device template catalog"
```

---

### Task 5: Entity-Manager Builder and Validator

**Files:**
- Create: `src/fw_diag_tool/em/builder.py`
- Create: `src/fw_diag_tool/em/validator.py`
- Test: `tests/test_em_builder.py`

**Interfaces:**
- Consumes: `EMDeviceTemplate`, `EMDeviceEntry`, `EMBoardConfig`, `EMValidationIssue` from `em/models.py`; `DEVICE_TEMPLATES` from `em/templates.py`; `BoardProfile` from `board_profile.py`
- Produces: `EMBuilder.generate(config: EMBoardConfig) -> str` (JSON string), `EMValidator.validate(json_text: str, board_profile: BoardProfile | None) -> list[EMValidationIssue]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_em_builder.py` testing:
- generate single TMP75 device -> valid JSON with correct structure
- generate multiple devices -> all present in Exposes array
- generate detects bus/address conflict -> raises ValueError
- validate valid JSON -> no issues
- validate missing required field -> returns issue
- validate bus/address conflict -> returns issue
- validate with board profile cross-reference -> detects mismatch
- round-trip: generate then validate -> no issues

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_em_builder.py -v`
Expected: FAIL

- [ ] **Step 3: Write EMBuilder implementation**

`em/builder.py`: EMBuilder with classmethod `generate(config: EMBoardConfig) -> str`. The output JSON follows OpenBMC Entity-Manager structure:
```json
{
  "Exposes": [
    {
      "Bus": 2,
      "Address": "0x48",
      "Name": "BMC_TEMP0",
      "Type": "TMP75",
      "PowerState": "On",
      "Thresholds": [...]
    }
  ],
  "Name": "BoardName",
  "Probe": "TRUE"
}
```
Validate bus/address uniqueness before generating. Apply template defaults, override with user custom_fields.

- [ ] **Step 4: Write EMValidator implementation**

`em/validator.py`: EMValidator with classmethod `validate(json_text: str, board_profile: BoardProfile | None = None) -> list[EMValidationIssue]`. Check: valid JSON parse, Exposes array exists, each entry has Bus/Address/Name/Type, bus/address uniqueness, address in valid I2C range (0x08-0x77), optional board profile cross-reference (warn if address in profile has different device type).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_em_builder.py -v`
Expected: PASS

- [ ] **Step 6: Run ruff and mypy**

Run: `uv run ruff check src/fw_diag_tool/em/`
Run: `uv run mypy src/fw_diag_tool/em/`

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/em/builder.py src/fw_diag_tool/em/validator.py tests/test_em_builder.py
git commit -m "feat(em): implement Entity-Manager JSON builder and validator"
```

---

### Task 6: CLI Integration (log and em subcommands)

**Files:**
- Modify: `src/fw_diag_tool/cli.py`
- Test: `tests/test_cli_log_em.py`

**Interfaces:**
- Consumes: `LogParser` from `log/parser.py`; `LogDiffEngine` from `log/diff.py`; `EMBuilder` from `em/builder.py`; `EMValidator` from `em/validator.py`
- Produces: `fw-diag log analyze <file>`, `fw-diag log diff <baseline> <candidate>`, `fw-diag em validate <file>`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_log_em.py` testing via CliRunner:
- `fw-diag log analyze` with a tmp dmesg file -> exit 0, output contains incident summary
- `fw-diag log analyze` with empty file -> exit 0, "no events"
- `fw-diag log diff` with two files -> exit 0, shows diff
- `fw-diag em validate` with valid JSON -> exit 0
- `fw-diag em validate` with invalid JSON -> exit 1 or shows issues
- `fw-diag log analyze --md` -> writes markdown report

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_log_em.py -v`
Expected: FAIL

- [ ] **Step 3: Write CLI subcommands**

Add `log_app = typer.Typer(name="log", help="Linux kernel and BMC log analysis")` and `em_app = typer.Typer(name="em", help="Entity-Manager JSON tools")` to cli.py. Register with `app.add_typer()`.

`log analyze`: read file, call LogParser.parse_log_text(), render Rich Table of incidents (ID, severity, title, event count, triage hint). Optional --md flag writes markdown. Optional --board-profile/-b for enrichment.

`log diff`: read two files, parse both, call LogDiffEngine.compare(), render Rich Panel with new/resolved/common incidents.

`em validate`: read JSON file, call EMValidator.validate(), render Rich Table of issues. Optional --board-profile/-b for cross-reference.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_log_em.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/cli.py tests/test_cli_log_em.py
git commit -m "feat(cli): add log analyze/diff and em validate subcommands"
```

---

### Task 7: GUI Log Analyzer Page

**Files:**
- Create: `src/fw_diag_tool/gui/pages/log_analyzer_ui.py`
- Modify: `src/fw_diag_tool/gui/app.py` (add navigation entry)
- Modify: `src/fw_diag_tool/gui/page_index.py` (add PAGE_INDEX entry)
- Modify: `src/fw_diag_tool/i18n/domains/gui.py` (add i18n keys)
- Test: `tests/test_log_analyzer_ui.py`

**Interfaces:**
- Consumes: `LogParser` from `log/parser.py`; `LogDiffEngine` from `log/diff.py`; shared GUI helpers from `gui/shared.py`
- Produces: `render()` function for Streamlit page

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_analyzer_ui.py` testing: module importable, render function exists, i18n keys registered (nav_category_system_log, log_analyzer_page_title, etc.).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_analyzer_ui.py -v`
Expected: FAIL

- [ ] **Step 3: Write the GUI page**

`gui/pages/log_analyzer_ui.py` with `render()` function:
- st.header with zh-TW title
- render_guide_expander linking to ch24_log_analyzer.md
- Input section: st.file_uploader for .log/.txt/.dmesg files + st.text_area fallback
- Optional: st.expander for Board Profile YAML upload
- Sample log buttons: "載入 I2C 逾時範例", "載入 PCIe AER 範例", "載入 OpenBMC 感測器範例"
- Analysis results: 4-column KPI metrics (total events, incidents, subsystems, time span)
- Tabs: Incidents (expandable cards with severity badges, events list, hypothesis, actions, tool page link), Events Timeline (sorted table), Subsystem Distribution (Plotly pie chart)
- Diff section: st.expander for baseline/candidate log comparison using LogDiffEngine
- Export: Markdown download button
- render_page_footer()

- [ ] **Step 4: Register page in app.py and page_index.py**

Add new nav category `nav_category_system_log` ("系統日誌與組態" / "System Logs & Configuration") in app.py. Register log_analyzer_ui.render as st.Page. Add PAGE_INDEX entry with url="log-analyzer", keywords="log dmesg journalctl kernel bmc incident triage".

- [ ] **Step 5: Add i18n keys**

Add to gui.py: nav_category_system_log, log_analyzer_page_title, log_upload_label, log_text_area_label, log_sample_i2c_timeout, log_sample_pcie_aer, log_sample_openbmc_sensor, log_tab_incidents, log_tab_events, log_tab_subsystems, log_no_events_info, log_incident_severity, log_incident_actions, log_incident_tool_link, log_diff_section_title.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_log_analyzer_ui.py tests/test_gui.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/gui/pages/log_analyzer_ui.py src/fw_diag_tool/gui/app.py src/fw_diag_tool/gui/page_index.py src/fw_diag_tool/i18n/domains/gui.py tests/test_log_analyzer_ui.py
git commit -m "feat(gui): add Log Analyzer page with incident triage and diff"
```

---

### Task 8: GUI Entity-Manager Builder Page

**Files:**
- Create: `src/fw_diag_tool/gui/pages/em_builder_ui.py`
- Modify: `src/fw_diag_tool/gui/app.py` (add navigation entry under same category)
- Modify: `src/fw_diag_tool/gui/page_index.py` (add PAGE_INDEX entry)
- Modify: `src/fw_diag_tool/i18n/domains/gui.py` (add i18n keys)
- Test: `tests/test_em_builder_ui.py`

**Interfaces:**
- Consumes: `EMBuilder` from `em/builder.py`; `EMValidator` from `em/validator.py`; `DEVICE_TEMPLATES` from `em/templates.py`; shared GUI helpers
- Produces: `render()` function for Streamlit page

- [ ] **Step 1: Write the failing test**

Create `tests/test_em_builder_ui.py` testing: module importable, render function exists, i18n keys registered.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_em_builder_ui.py -v`
Expected: FAIL

- [ ] **Step 3: Write the GUI page**

`gui/pages/em_builder_ui.py` with `render()` function:
- st.header with zh-TW title
- render_guide_expander linking to ch25_em_builder.md
- Mode selector: st.radio("模式", ["建置模式 (Build)", "驗證模式 (Validate)"])
- **Build mode**:
  - st.text_input for board name
  - st.selectbox for device template category (溫度感測器/ADC/FRU EEPROM/風扇控制器/電源/GPIO/Hot-swap)
  - st.selectbox for specific chip within category
  - st.number_input for bus number (0-65535)
  - st.text_input for address (hex, e.g. "0x48")
  - st.text_input for device name
  - st.selectbox for PowerState override
  - st.button("新增裝置") -> accumulate in session_state list
  - st.dataframe showing current device list with delete buttons
  - st.button("產生 Entity-Manager JSON") -> call EMBuilder.generate(), display with st.code(json, language="json"), offer st.download_button
- **Validate mode**:
  - st.file_uploader for .json files + st.text_area fallback
  - Optional board profile upload
  - st.button("驗證") -> call EMValidator.validate(), display issues as colored cards (error=red, warning=yellow, info=blue)
  - If no issues: st.success("驗證通過")
- render_page_footer()

- [ ] **Step 4: Register page in app.py and page_index.py**

Add em_builder_ui.render as st.Page under nav_category_system_log. Add PAGE_INDEX entry with url="em-builder", keywords="entity manager openbmc json config generate validate".

- [ ] **Step 5: Add i18n keys**

Add to gui.py: em_builder_page_title, em_mode_build, em_mode_validate, em_board_name_label, em_device_category_label, em_chip_select_label, em_bus_label, em_address_label, em_device_name_label, em_power_state_label, em_add_device_button, em_generate_button, em_validate_button, em_download_button, em_validation_passed, em_no_devices_info.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_em_builder_ui.py tests/test_gui.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/gui/pages/em_builder_ui.py src/fw_diag_tool/gui/app.py src/fw_diag_tool/gui/page_index.py src/fw_diag_tool/i18n/domains/gui.py tests/test_em_builder_ui.py
git commit -m "feat(gui): add Entity-Manager Builder page with build and validate modes"
```

---

### Task 9: Documentation

**Files:**
- Create: `docs/chapters/ch24_log_analyzer.md`
- Create: `docs/chapters/ch25_em_builder.md`
- Modify: `mkdocs.yml` (add nav entries)
- Modify: `docs/chapters/appendix_gui_reading_guide.md` (update page count)
- Modify: `tests/test_docs.py` (add assertions for new chapters)

**Interfaces:**
- Consumes: completed GUI pages and CLI commands from Tasks 1-8
- Produces: user-facing documentation chapters

- [ ] **Step 1: Write failing docs test**

Add assertions to `tests/test_docs.py` that ch24_log_analyzer.md and ch25_em_builder.md exist and contain expected section headings.

- [ ] **Step 2: Write ch24_log_analyzer.md**

Structure: what the log analyzer does, supported log formats (dmesg, journalctl), GUI walkthrough (upload -> incidents -> triage), CLI usage (fw-diag log analyze), pattern library overview, board profile enrichment, diff comparison, evidence boundaries (log analysis is heuristic triage, not root cause proof).

- [ ] **Step 3: Write ch25_em_builder.md**

Structure: what Entity-Manager is, why manual JSON is error-prone, GUI build mode walkthrough (select template -> fill fields -> generate -> download), validate mode walkthrough (upload -> check -> fix), CLI usage (fw-diag em validate), supported device templates table, PowerState explanation, safety notes (generated JSON is a starting template, must be validated with actual hardware).

- [ ] **Step 4: Update mkdocs.yml**

Add under nav:
```yaml
- 系統日誌關聯分析: chapters/ch24_log_analyzer.md
- Entity-Manager 組態產生器: chapters/ch25_em_builder.md
```

- [ ] **Step 5: Update appendix**

Update appendix_gui_reading_guide.md page count to 28+ pages.

- [ ] **Step 6: Run docs verification**

Run: `uv run pytest tests/test_docs.py -v`
Run: `uv run mkdocs build --strict`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/chapters/ch24_log_analyzer.md docs/chapters/ch25_em_builder.md mkdocs.yml docs/chapters/appendix_gui_reading_guide.md tests/test_docs.py
git commit -m "docs: add Log Analyzer and Entity-Manager Builder chapters"
```

---

### Task 10: Version Bump, CHANGELOG, and Full Verification

**Files:**
- Modify: `pyproject.toml` (version 1.7.0 -> 2.0.0)
- Modify: `CHANGELOG.md` (add v2.0.0 section)
- Modify: `README.md` (update version references and feature highlights)
- Test: existing `tests/test_packaging.py`, `tests/test_release_notes.py`

**Interfaces:**
- Consumes: all prior task outputs
- Produces: release-ready metadata and full verification evidence

- [ ] **Step 1: Bump version in pyproject.toml**

Change `version = "1.7.0"` to `version = "2.0.0"`.

- [ ] **Step 2: Add CHANGELOG entry**

Insert `## [2.0.0] - 2026-09-01` before v1.7.0 with:
- Added: System Log Correlation Engine (dmesg/journalctl parsing, incident correlation, board profile enrichment)
- Added: Entity-Manager Visual Builder (template-driven JSON generation, dual-mode build/validate)
- Added: Log Analyzer GUI page with incident triage and A/B diff
- Added: EM Builder GUI page with build and validate modes
- Added: CLI subcommands fw-diag log analyze/diff and fw-diag em validate
- Added: 30+ log pattern rules for I2C, PCIe, hwmon, thermal, watchdog, power, GPIO, SPI, MCTP
- Added: 12+ EM device templates (TMP75, AT24C256, MAX31790, ADM1272, etc.)
- Added: Documentation chapters ch24 (Log Analyzer) and ch25 (EM Builder)

- [ ] **Step 3: Update README**

Update version marker and highlights heading to v2.0.0. Add brief description of the two new subsystems.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -q`
Expected: 1393+ passed (1313 existing + 80+ new)

- [ ] **Step 5: Run static checks**

Run: `uv run ruff check .`
Run: `uv run ruff format --check .`
Run: `uv run mypy src/fw_diag_tool`
Run: `uv run mkdocs build --strict`
Run: `uv lock --check`

- [ ] **Step 6: Verify git state**

```bash
git status --short --branch
git log --oneline --decorate -15
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml CHANGELOG.md README.md
git commit -m "release: bump version to 2.0.0 with system diagnostics engine"
```

