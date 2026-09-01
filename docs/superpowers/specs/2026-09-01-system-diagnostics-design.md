# v2.0.0 系統級關聯診斷引擎 — Design Spec

> **Date:** 2026-09-01
> **Status:** Pending Approval
> **Scope:** Add Linux Kernel / OpenBMC log correlation engine, Entity-Manager visual builder, and system diagnostics GUI pages.

## 1. Problem Statement

fw-diag-tool excels at bottom-up protocol analysis (I2C waveforms, PCIe AER registers, SPI opcodes). However, firmware engineers almost always start debugging top-down: they see a dmesg error or a journalctl crash, then need to figure out which bus, device, or configuration is at fault.

Two critical gaps remain:

1. **No log analysis**: Engineers must manually grep through dmesg / journalctl output to find hardware-related errors, then mentally correlate them with I2C bus numbers, device addresses, and driver names.

2. **No Entity-Manager tooling**: OpenBMC Entity-Manager JSON configuration is error-prone (wrong bus, wrong address, missing PowerState, typos in compatible strings). Engineers hand-write JSON and only discover mistakes after a full build-flash-boot cycle.

## 2. Architecture

### 2.1 Log Correlation Engine

New module: src/fw_diag_tool/log/

The engine parses Linux Kernel dmesg and OpenBMC journalctl log text, extracts hardware-related events, and correlates them into actionable Incidents.

Pattern Library: a data-driven collection of regex rules, each tagged with subsystem, severity, extraction fields, and triage guidance.

Incident Correlation: groups related LogEvents by timestamp proximity, shared hardware context (same bus+address, same BDF), and causal chains.

Board Profile Cross-Reference: when a BoardProfile is provided, the engine enriches incidents with device names and specific diagnostic recommendations.

### 2.2 Entity-Manager Visual Builder

New module: src/fw_diag_tool/em/

A template-driven builder that generates valid OpenBMC Entity-Manager JSON configurations, following the same pattern as the existing Device Tree generator.

Device Templates: Temperature sensors (TMP75, TMP421, LM75, EMC1413), ADC (ADC128D818), FRU EEPROM (AT24C256), Fan controllers (MAX31790, EMC2305), PSU/PMBus, GPIO expanders (PCA9555), Hot-swap controllers (ADM1272, LTC4282).

Dual-Mode Operation: Build mode (select from catalog, generate JSON) and Validate mode (upload existing JSON, check for errors).

### 2.3 GUI Integration

New navigation category: System Logs and Configuration. Two new pages: log_analyzer_ui.py and em_builder_ui.py.

### 2.4 CLI Integration

New CLI subcommands: fw-diag log analyze, fw-diag em validate, fw-diag em generate.

## 3. Data Models

### 3.1 Log Models (log/models.py)

- LogSourceType(str, Enum): DMESG, JOURNALCTL, MIXED
- Subsystem(str, Enum): I2C, PCIE, HWMON, SPI, MCTP, GPIO, WATCHDOG, THERMAL, POWER, USB, GENERAL
- LogEvent(frozen dataclass): timestamp, subsystem, severity, message, bus, address, bdf, driver, errno_code, extra, pattern_id, triage_hint
- Incident(frozen dataclass): id, title, subsystem, severity, events, root_cause_hypothesis, recommended_actions, related_tool_page, board_context
- LogSummary(frozen dataclass): total_lines, total_events, total_incidents, subsystem_counts, severity_counts, time_span_seconds
- LogReport(frozen dataclass): source_type, events, incidents, summary

### 3.2 EM Models (em/models.py)

- EMDeviceTemplate(frozen dataclass): category, chip_name, em_type, default_power_state, required_fields, optional_fields, description
- EMDeviceEntry(dataclass): template, bus, address, name, power_state, custom_fields
- EMBoardConfig(dataclass): board_name, devices
- EMValidationIssue(frozen dataclass): severity, field_path, message, suggestion

## 4. Pattern Library Design

Python data structure containing ~30 LogPattern(frozen dataclass) rules covering common Linux kernel / OpenBMC error signatures across I2C, PCIe, hwmon, thermal, watchdog, and power subsystems.

## 5. Testing Strategy

- Each module gets its own test file with synthetic log fixtures
- EM templates validated against known-good EM JSON examples
- GUI pages tested via import/render smoke tests
- CLI commands tested via CliRunner
- Pattern library tested with real-world log snippets (sanitized)
- Cross-reference with BoardProfile tested with existing examples/data/board_yv4.yaml

## 6. i18n Requirements

All new user-facing strings registered in i18n/domains/gui.py with zh-TW and en-US translations.

## 7. Documentation

- docs/chapters/ch24_log_analyzer.md
- docs/chapters/ch25_em_builder.md
- mkdocs.yml nav updated
- appendix_gui_reading_guide.md updated

## 8. Version

Bump pyproject.toml version to 2.0.0.

## 9. Success Criteria

- Log engine correctly parses and correlates at least 30 common dmesg/journalctl error patterns
- EM builder generates valid Entity-Manager JSON for 7+ device template categories
- EM validator catches bus/address conflicts, missing required fields, and board profile mismatches
- All existing 1313+ tests continue passing
- New features add 80+ tests
- ruff, mypy, mkdocs build --strict all clean

## 10. Non-Goals

- U-Boot / bootloader log parsing
- Live BMC connection or remote log collection
- PLDM / SPDM deep message decode in log context
- Automated EM JSON deployment to target BMC
- Full JSON Schema validation against upstream phosphor-dbus-interfaces
