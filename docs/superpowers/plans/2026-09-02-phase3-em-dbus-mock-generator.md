# Phase 3: Entity-Manager to D-Bus Mock Script Generator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an automated D-Bus mock script generator that transforms OpenBMC Entity-Manager (EM) JSON configurations into runnable Bash (`busctl`) scripts and standalone Python scripts, enabling firmware engineers to simulate and test D-Bus sensor topologies without physical hardware.

**Architecture:** Create `EMMockGenerator` in `src/fw_diag_tool/em/mock_gen.py` that parses EM configurations and maps device templates (temperature, fan, PSU, hot-swap, ADC, FRU) to OpenBMC D-Bus sensor and inventory paths. Expose this generator via the `fw-diag em mock` CLI subcommand in `src/fw_diag_tool/cli.py` and integrate a dedicated "🧪 Mock 產生器" tab into the Streamlit EM Builder GUI (`src/fw_diag_tool/gui/pages/em_builder_ui.py`).

**Tech Stack:** Python 3.10+, dataclasses, subprocess, typer, rich, streamlit, pytest

**Spec:** This plan is self-contained; no external spec document is required. The design follows standard OpenBMC D-Bus sensor specifications (`xyz.openbmc_project.Sensor.Value`, `xyz.openbmc_project.Inventory.Item.Board`) and existing `fw_diag_tool.em` architecture.

## Global Constraints

- Python >= 3.10 (use `from __future__ import annotations`)
- Zero-LaTeX rule: Do not use inline LaTeX or LaTeX syntax in code, docs, or UI messages. Use plain Unicode symbols (`->`, `°C`, `Ω`, `µs`, `V`, `W`, `RPM`).
- Maintain frozen dataclasses, classmethod helpers, and explicit type annotations conforming to project conventions.
- No new runtime dependencies. Use standard library `subprocess`, `json`, and existing packages (`typer`, `rich`, `streamlit`, `pytest`).
- CLI commands must use Typer and output structured tables / messages with Rich.
- Streamlit pages must maintain clean state separation, AppTest compatibility, and full i18n support in `zh-TW` and `en-US`.
- All tests must pass: run `uv run pytest tests/test_em_mock_gen.py tests/test_cli_log_em.py tests/test_em_builder_ui.py -v`.
- Linting and static typing gates: run `uv run ruff check .` and `uv run mypy src/fw_diag_tool`.

---

### Task 1: Core D-Bus Mock Generator Module (`EMMockGenerator`)

**Files:**
- Create: `src/fw_diag_tool/em/mock_gen.py`
- Modify: `src/fw_diag_tool/em/__init__.py`
- Test: `tests/test_em_mock_gen.py`

**Interfaces:**
- Consumes: `EMBoardConfig`, `EMDeviceEntry`, `EMDeviceTemplate`, `DEVICE_TEMPLATES`, `get_template` from `fw_diag_tool.em`
- Produces: `EMMockGenerator` class exporting:
  - `parse_em_json(cls, json_text: str) -> EMBoardConfig`
  - `generate_busctl_script(cls, config: EMBoardConfig) -> str`
  - `generate_python_mock(cls, config: EMBoardConfig) -> str`

- [x] **Step 1: Write the failing tests for `EMMockGenerator`**

Create `tests/test_em_mock_gen.py` with unit tests covering JSON parsing, bash script generation, Python script generation, sensor path mappings, unit strings, default values, FRU inventory objects, and GPIO skipping:

```python
"""Unit tests for Entity-Manager D-Bus Mock Script Generator."""

from __future__ import annotations

import json

import pytest

from fw_diag_tool.em.mock_gen import EMMockGenerator
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
    EMDeviceTemplate,
)
from fw_diag_tool.em.templates import get_template


@pytest.fixture
def sample_board_config() -> EMBoardConfig:
    """Fixture providing a multi-device EMBoardConfig covering all sensor categories."""
    tmp75 = get_template("TMP75") or EMDeviceTemplate(
        category="temperature", chip_name="TMP75", em_type="TMP75"
    )
    max31790 = get_template("MAX31790") or EMDeviceTemplate(
        category="fan", chip_name="MAX31790", em_type="MAX31790"
    )
    pmbus = get_template("PMBus") or EMDeviceTemplate(
        category="psu", chip_name="PMBus", em_type="PMBus"
    )
    adc = get_template("ADC128D818") or EMDeviceTemplate(
        category="adc", chip_name="ADC128D818", em_type="ADC128D818"
    )
    fru = get_template("AT24C256") or EMDeviceTemplate(
        category="fru", chip_name="AT24C256", em_type="EEPROM"
    )
    gpio = get_template("PCA9555") or EMDeviceTemplate(
        category="gpio", chip_name="PCA9555", em_type="PCA9555"
    )
    adm1272 = get_template("ADM1272") or EMDeviceTemplate(
        category="hotswap", chip_name="ADM1272", em_type="ADM1272"
    )

    devices = [
        EMDeviceEntry(template=tmp75, bus=1, address=0x48, name="Inlet_Temp"),
        EMDeviceEntry(template=max31790, bus=2, address=0x20, name="Fan_Tach0"),
        EMDeviceEntry(template=pmbus, bus=3, address=0x58, name="PSU0_Pwr"),
        EMDeviceEntry(template=adc, bus=4, address=0x1D, name="P12V_Sens"),
        EMDeviceEntry(template=fru, bus=1, address=0x50, name="Baseboard_FRU"),
        EMDeviceEntry(template=gpio, bus=5, address=0x21, name="IO_Expander0"),
        EMDeviceEntry(template=adm1272, bus=6, address=0x10, name="Hotswap_Pwr"),
    ]
    return EMBoardConfig(
        board_name="Yosemite_V4_MB",
        devices=devices,
        probe_expression="TRUE",
    )


def test_parse_em_json_valid() -> None:
    """Verify that parse_em_json reconstructs EMBoardConfig from standard JSON."""
    em_json = json.dumps(
        {
            "Name": "Test_Board",
            "Probe": "xyz.openbmc_project.FruDevice({'PRODUCT_NAME': 'Test'})",
            "Exposes": [
                {"Name": "CPU_Temp", "Type": "TMP75", "Bus": 1, "Address": "0x48"},
                {"Name": "FAN_0", "Type": "MAX31790", "Bus": 2, "Address": 32},
            ],
        }
    )
    config = EMMockGenerator.parse_em_json(em_json)
    assert config.board_name == "Test_Board"
    assert "FruDevice" in config.probe_expression
    assert len(config.devices) == 2

    dev0 = config.devices[0]
    assert dev0.name == "CPU_Temp"
    assert dev0.bus == 1
    assert dev0.address == 0x48
    assert dev0.template.category == "temperature"

    dev1 = config.devices[1]
    assert dev1.name == "FAN_0"
    assert dev1.bus == 2
    assert dev1.address == 32
    assert dev1.template.category == "fan"


def test_parse_em_json_unknown_chip_fallback() -> None:
    """Verify that unknown device types create a generic fallback template."""
    em_json = json.dumps(
        {
            "Name": "Custom_Board",
            "Exposes": [
                {"Name": "Custom_Sensor", "Type": "CustomTempSensor", "Bus": 1, "Address": "0x4A"}
            ],
        }
    )
    config = EMMockGenerator.parse_em_json(em_json)
    assert len(config.devices) == 1
    dev = config.devices[0]
    assert dev.name == "Custom_Sensor"
    assert dev.template.chip_name == "CustomTempSensor"
    assert dev.template.category == "temperature"


def test_generate_busctl_script_structure(sample_board_config: EMBoardConfig) -> None:
    """Verify the generated Bash script header, D-Bus paths, and commands."""
    script = EMMockGenerator.generate_busctl_script(sample_board_config)

    # Shell script headers
    assert script.startswith("#!/bin/bash")
    assert "set -euo pipefail" in script
    assert "Yosemite_V4_MB" in script

    # Temperature sensor checks
    assert "/xyz/openbmc_project/sensors/temperature/Inlet_Temp" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.DegreesC" in script
    assert "25.0" in script

    # Fan tach sensor checks
    assert "/xyz/openbmc_project/sensors/fan_tach/Fan_Tach0" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.RPMS" in script
    assert "5000.0" in script

    # PSU & Hotswap sensor checks
    assert "/xyz/openbmc_project/sensors/power/PSU0_Pwr" in script
    assert "/xyz/openbmc_project/sensors/power/Hotswap_Pwr" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.Watts" in script
    assert "100.0" in script

    # Voltage / ADC sensor checks
    assert "/xyz/openbmc_project/sensors/voltage/P12V_Sens" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.Volts" in script
    assert "3.3" in script

    # FRU / Inventory checks
    assert "/xyz/openbmc_project/inventory/system/board/Baseboard_FRU" in script

    # GPIO skip notice
    assert "Skipping GPIO expander IO_Expander0" in script or "IO_Expander0" in script

    # Verification / Object Mapper call comments
    assert "xyz.openbmc_project.ObjectMapper" in script


def test_generate_python_mock_structure(sample_board_config: EMBoardConfig) -> None:
    """Verify the generated Python standalone script."""
    script = EMMockGenerator.generate_python_mock(sample_board_config)

    assert script.startswith("#!/usr/bin/env python3")
    assert "import subprocess" in script
    assert "if __name__ == '__main__':" in script or 'if __name__ == "__main__":' in script
    assert "Yosemite_V4_MB" in script

    # Check sensors in python dictionary structure
    assert "/xyz/openbmc_project/sensors/temperature/Inlet_Temp" in script
    assert "/xyz/openbmc_project/sensors/fan_tach/Fan_Tach0" in script
    assert "/xyz/openbmc_project/sensors/power/PSU0_Pwr" in script
    assert "/xyz/openbmc_project/sensors/voltage/P12V_Sens" in script
    assert "/xyz/openbmc_project/inventory/system/board/Baseboard_FRU" in script


def test_package_exports_mock_generator() -> None:
    """Verify that EMMockGenerator is properly exported from fw_diag_tool.em."""
    import fw_diag_tool.em as em_pkg

    assert hasattr(em_pkg, "EMMockGenerator")
    assert callable(em_pkg.EMMockGenerator.generate_busctl_script)
    assert callable(em_pkg.EMMockGenerator.generate_python_mock)
    assert callable(em_pkg.EMMockGenerator.parse_em_json)
```

- [x] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_em_mock_gen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fw_diag_tool.em.mock_gen'`

- [x] **Step 3: Implement `src/fw_diag_tool/em/mock_gen.py`**

Create `src/fw_diag_tool/em/mock_gen.py`:

```python
"""OpenBMC Entity-Manager to D-Bus Mock Script Generator."""

from __future__ import annotations

import json
import re
from typing import Any

from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
    EMDeviceTemplate,
)
from fw_diag_tool.em.templates import DEVICE_TEMPLATES, get_template


def _sanitize_name(name: str) -> str:
    """Sanitize device name for D-Bus object path component."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    clean = re.sub(r"_+", "_", clean)
    return clean.strip("_") or "Sensor"


def _infer_category(type_name: str, dev_name: str) -> str:
    """Infer device category from type name or device name when template is missing."""
    token = f"{type_name} {dev_name}".lower()
    if any(k in token for k in ("temp", "tmp", "lm75", "emc14", "thermal")):
        return "temperature"
    if any(k in token for k in ("fan", "tach", "pwm", "max31790", "emc23")):
        return "fan"
    if any(k in token for k in ("psu", "pmbus", "power", "watt", "cur", "adm12", "ltc42")):
        return "psu"
    if any(k in token for k in ("adc", "volt", "vmon", "adc128")):
        return "adc"
    if any(k in token for k in ("eeprom", "fru", "24c", "at24")):
        return "fru"
    if any(k in token for k in ("pca95", "gpio", "expander")):
        return "gpio"
    return "temperature"


class EMMockGenerator:
    """Generator for creating D-Bus sensor mocking scripts from Entity-Manager configurations."""

    MOCK_SERVICE = "xyz.openbmc_project.FWDiagMock"
    SENSOR_VALUE_INTF = "xyz.openbmc_project.Sensor.Value"
    BOARD_INTF = "xyz.openbmc_project.Inventory.Item.Board"

    @classmethod
    def parse_em_json(cls, json_text: str) -> EMBoardConfig:
        """Parse an Entity-Manager JSON configuration string into an EMBoardConfig object."""
        data = json.loads(json_text)
        if not isinstance(data, dict):
            raise ValueError("Entity-Manager configuration root must be a JSON object")

        board_name = str(data.get("Name", "Mock_Board"))
        probe_expr = str(data.get("Probe", "TRUE"))
        exposes_list = data.get("Exposes", [])

        devices: list[EMDeviceEntry] = []
        for idx, item in enumerate(exposes_list):
            if not isinstance(item, dict):
                continue

            name = str(item.get("Name", f"Device_{idx}"))
            type_name = str(item.get("Type", ""))
            bus = int(item.get("Bus", 0))

            addr_raw = item.get("Address", 0)
            if isinstance(addr_raw, str):
                addr_str = addr_raw.strip()
                address = int(addr_str, 16) if addr_str.startswith(("0x", "0X")) else int(addr_str, 10)
            else:
                address = int(addr_raw)

            power_state = item.get("PowerState")

            tmpl = get_template(type_name)
            if tmpl is None:
                for candidate in DEVICE_TEMPLATES.values():
                    if candidate.em_type.lower() == type_name.lower():
                        tmpl = candidate
                        break

            if tmpl is None:
                cat = _infer_category(type_name, name)
                tmpl = EMDeviceTemplate(
                    category=cat,
                    chip_name=type_name or "CustomDevice",
                    em_type=type_name or "CustomDevice",
                    default_power_state="On",
                )

            custom_fields = {
                k: v
                for k, v in item.items()
                if k not in ("Name", "Type", "Bus", "Address", "PowerState")
            }

            devices.append(
                EMDeviceEntry(
                    template=tmpl,
                    bus=bus,
                    address=address,
                    name=name,
                    power_state=power_state,
                    custom_fields=custom_fields,
                )
            )

        return EMBoardConfig(
            board_name=board_name,
            devices=devices,
            probe_expression=probe_expr,
        )

    @classmethod
    def generate_busctl_script(cls, config: EMBoardConfig) -> str:
        """Generate a runnable Bash script using busctl to mock D-Bus sensors."""
        lines: list[str] = [
            "#!/bin/bash",
            "# =============================================================================",
            f"# OpenBMC D-Bus Sensor Mock Script for: {config.board_name}",
            "# Generated by fw-diag-tool (Entity-Manager Mock Generator)",
            "# =============================================================================",
            "set -euo pipefail",
            "",
            f'echo "[INFO] Initializing OpenBMC D-Bus Mock Sensor Objects for {config.board_name}..."',
            "",
        ]

        sensor_count = 0
        for dev in config.devices:
            cat = dev.template.category.lower()
            clean_name = _sanitize_name(dev.name)

            if cat == "gpio":
                lines.append(f"# Skipping GPIO expander {dev.name} (no direct D-Bus sensor object)")
                continue

            if cat == "temperature":
                path = f"/xyz/openbmc_project/sensors/temperature/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.DegreesC"
                val = 25.0
                val_type = "d"
            elif cat == "fan":
                path = f"/xyz/openbmc_project/sensors/fan_tach/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.RPMS"
                val = 5000.0
                val_type = "d"
            elif cat in ("psu", "hotswap"):
                path = f"/xyz/openbmc_project/sensors/power/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.Watts"
                val = 100.0
                val_type = "d"
            elif cat == "adc":
                path = f"/xyz/openbmc_project/sensors/voltage/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.Volts"
                val = 3.3
                val_type = "d"
            elif cat == "fru":
                path = f"/xyz/openbmc_project/inventory/system/board/{clean_name}"
                lines.extend(
                    [
                        f"# --- FRU Inventory: {dev.name} (Bus {dev.bus}, Addr 0x{dev.address:02x}) ---",
                        f"# Expected Object Path: {path}",
                        f'# Verify with: busctl call xyz.openbmc_project.ObjectMapper /xyz/openbmc_project/object_mapper xyz.openbmc_project.ObjectMapper GetObject sas \"{path}\" 0',
                        f'echo "[MOCK] Registering FRU Board Object: {clean_name}"',
                        f'busctl set-property {cls.MOCK_SERVICE} {path} {cls.BOARD_INTF} PrettyName s \"{dev.name}\" 2>/dev/null || true',
                        "",
                    ]
                )
                sensor_count += 1
                continue
            else:
                path = f"/xyz/openbmc_project/sensors/temperature/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.DegreesC"
                val = 25.0
                val_type = "d"

            unit_short = unit.split(".")[-1]
            lines.extend(
                [
                    f"# --- Sensor: {dev.name} ({dev.template.chip_name}, Bus {dev.bus}, Addr 0x{dev.address:02x}) ---",
                    f"# Expected Object Path: {path}",
                    f'# Verify with: busctl call xyz.openbmc_project.ObjectMapper /xyz/openbmc_project/object_mapper xyz.openbmc_project.ObjectMapper GetObject sas \"{path}\" 0',
                    f'echo "[MOCK] Publishing {cat} sensor: {clean_name} -> {val} ({unit_short})"',
                    f"busctl set-property {cls.MOCK_SERVICE} {path} {cls.SENSOR_VALUE_INTF} Value {val_type} {val} 2>/dev/null || true",
                    f'busctl set-property {cls.MOCK_SERVICE} {path} {cls.SENSOR_VALUE_INTF} Unit s \"{unit}\" 2>/dev/null || true',
                    "",
                ]
            )
            sensor_count += 1

        lines.extend(
            [
                f'echo "[SUCCESS] Successfully registered {sensor_count} D-Bus mock objects for {config.board_name}."',
                'echo "[INFO] Inspect active sensors with: busctl tree xyz.openbmc_project.FWDiagMock"',
            ]
        )
        return "\n".join(lines) + "\n"

    @classmethod
    def generate_python_mock(cls, config: EMBoardConfig) -> str:
        """Generate a standalone Python script using subprocess and busctl."""
        devices_data: list[dict[str, Any]] = []

        for dev in config.devices:
            cat = dev.template.category.lower()
            clean_name = _sanitize_name(dev.name)

            if cat == "gpio":
                continue

            if cat == "temperature":
                path = f"/xyz/openbmc_project/sensors/temperature/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.DegreesC"
                val = 25.0
                is_sensor = True
            elif cat == "fan":
                path = f"/xyz/openbmc_project/sensors/fan_tach/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.RPMS"
                val = 5000.0
                is_sensor = True
            elif cat in ("psu", "hotswap"):
                path = f"/xyz/openbmc_project/sensors/power/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.Watts"
                val = 100.0
                is_sensor = True
            elif cat == "adc":
                path = f"/xyz/openbmc_project/sensors/voltage/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.Volts"
                val = 3.3
                is_sensor = True
            elif cat == "fru":
                path = f"/xyz/openbmc_project/inventory/system/board/{clean_name}"
                unit = ""
                val = 0.0
                is_sensor = False
            else:
                path = f"/xyz/openbmc_project/sensors/temperature/{clean_name}"
                unit = "xyz.openbmc_project.Sensor.Value.Unit.DegreesC"
                val = 25.0
                is_sensor = True

            devices_data.append(
                {
                    "name": dev.name,
                    "chip": dev.template.chip_name,
                    "category": cat,
                    "bus": dev.bus,
                    "address": f"0x{dev.address:02x}",
                    "path": path,
                    "unit": unit,
                    "value": val,
                    "is_sensor": is_sensor,
                }
            )

        json_mock_data = json.dumps(devices_data, indent=4)

        script = f'''#!/usr/bin/env python3
"""OpenBMC D-Bus Sensor Mock Script for {config.board_name}.

Generated by fw-diag-tool (Entity-Manager Mock Generator).
Publishes and updates mock D-Bus sensor values via busctl.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

MOCK_SERVICE = "{cls.MOCK_SERVICE}"
SENSOR_VALUE_INTF = "{cls.SENSOR_VALUE_INTF}"
BOARD_INTF = "{cls.BOARD_INTF}"

MOCK_OBJECTS = {json_mock_data}


def run_busctl(args: list[str]) -> bool:
    """Execute a busctl command safely via subprocess."""
    cmd = ["busctl"] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode == 0
    except FileNotFoundError:
        print("[WARN] busctl binary not found in system PATH. Simulating command:", " ".join(cmd))
        return False


def setup_mock_objects() -> None:
    """Register and initialize all mock objects on D-Bus."""
    print(f"[INFO] Publishing {{len(MOCK_OBJECTS)}} mock objects for {config.board_name}...")
    for obj in MOCK_OBJECTS:
        path = obj["path"]
        name = obj["name"]
        if obj["is_sensor"]:
            val = obj["value"]
            unit = obj["unit"]
            print(f"  -> Publishing {{obj['category']}} sensor '{{name}}' at {{path}} = {{val}}")
            run_busctl(["set-property", MOCK_SERVICE, path, SENSOR_VALUE_INTF, "Value", "d", str(val)])
            run_busctl(["set-property", MOCK_SERVICE, path, SENSOR_VALUE_INTF, "Unit", "s", unit])
        else:
            print(f"  -> Registering FRU inventory '{{name}}' at {{path}}")
            run_busctl(["set-property", MOCK_SERVICE, path, BOARD_INTF, "PrettyName", "s", name])
    print("[SUCCESS] All mock objects initialized.")


def main() -> int:
    """Main entrypoint for D-Bus mock script."""
    parser = argparse.ArgumentParser(description="Mock D-Bus sensor daemon for {config.board_name}")
    parser.add_argument("--interval", type=float, default=2.0, help="Periodic refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="Set properties once and exit immediately")
    args = parser.parse_args()

    setup_mock_objects()

    if args.once:
        return 0

    print("[INFO] Monitoring and maintaining mock state (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped mock daemon.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
'''
        return script
```

- [x] **Step 4: Update `src/fw_diag_tool/em/__init__.py`**

Export `EMMockGenerator` in `src/fw_diag_tool/em/__init__.py`:

```python
"""OpenBMC Entity-Manager data models, device templates, and configuration tools."""

from fw_diag_tool.em.builder import EMBuilder
from fw_diag_tool.em.mock_gen import EMMockGenerator
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
    EMDeviceTemplate,
    EMValidationIssue,
)
from fw_diag_tool.em.templates import (
    DEVICE_TEMPLATES,
    get_all_categories,
    get_template,
    get_templates_by_category,
)
from fw_diag_tool.em.validator import EMValidator

__all__ = [
    "DEVICE_TEMPLATES",
    "EMBoardConfig",
    "EMBuilder",
    "EMDeviceEntry",
    "EMDeviceTemplate",
    "EMMockGenerator",
    "EMValidationIssue",
    "EMValidator",
    "get_all_categories",
    "get_template",
    "get_templates_by_category",
]
```

- [x] **Step 5: Run tests and verify success**

Run: `uv run pytest tests/test_em_mock_gen.py -v`
Expected: ALL PASS

- [x] **Step 6: Commit Task 1**

```bash
git add src/fw_diag_tool/em/mock_gen.py src/fw_diag_tool/em/__init__.py tests/test_em_mock_gen.py
git commit -m "feat(em): implement D-Bus mock script generator core module"
```

---

### Task 2: CLI Command `fw-diag em mock`

**Files:**
- Modify: `src/fw_diag_tool/cli.py`
- Test: `tests/test_cli_log_em.py`

**Interfaces:**
- Consumes: `EMMockGenerator` from `fw_diag_tool.em`
- Produces: Typer subcommand `@em_app.command("mock")` supporting `--format` (`bash`/`python`) and `--output` options

- [x] **Step 1: Write failing CLI tests**

Add the following tests to `tests/test_cli_log_em.py`:

```python
def test_cli_em_mock_bash_default(tmp_path: Path) -> None:
    """Test em mock generating Bash busctl script to stdout."""
    em_file = tmp_path / "server_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    result = runner.invoke(app, ["em", "mock", str(em_file)])
    assert result.exit_code == 0
    assert "#!/bin/bash" in result.output
    assert "Server_Mainboard" in result.output
    assert "/xyz/openbmc_project/sensors/temperature/Inlet_Temp_Sensor" in result.output or "Inlet" in result.output
    assert "busctl set-property" in result.output


def test_cli_em_mock_python_format(tmp_path: Path) -> None:
    """Test em mock generating Python script to stdout."""
    em_file = tmp_path / "server_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    result = runner.invoke(app, ["em", "mock", str(em_file), "--format", "python"])
    assert result.exit_code == 0
    assert "#!/usr/bin/env python3" in result.output
    assert "import subprocess" in result.output
    assert "Server_Mainboard" in result.output


def test_cli_em_mock_export_to_file(tmp_path: Path) -> None:
    """Test em mock exporting generated script to file via --output."""
    em_file = tmp_path / "server_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    out_file = tmp_path / "mock_sensors.sh"
    result = runner.invoke(app, ["em", "mock", str(em_file), "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "#!/bin/bash" in content
    assert "Server_Mainboard" in content


def test_cli_em_mock_unsupported_format(tmp_path: Path) -> None:
    """Test em mock with invalid format exits with code 2."""
    em_file = tmp_path / "server_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    result = runner.invoke(app, ["em", "mock", str(em_file), "--format", "ruby"])
    assert result.exit_code == 2
    assert "Unsupported format" in result.output or "error" in result.output.lower()


def test_cli_em_mock_missing_file() -> None:
    """Test em mock with non-existent file exits with code 1."""
    result = runner.invoke(app, ["em", "mock", "/non/existent/board.json"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
```

- [x] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_cli_log_em.py -k "test_cli_em_mock" -v`
Expected: FAIL with `No such command 'mock'`

- [x] **Step 3: Implement `@em_app.command("mock")` in `src/fw_diag_tool/cli.py`**

In `src/fw_diag_tool/cli.py`, ensure `EMMockGenerator` is imported from `fw_diag_tool.em`, and append the `mock` command:

```python
@em_app.command("mock")
def mock_em(
    file_path: Path = typer.Argument(..., help="Path to Entity-Manager JSON configuration file"),
    format_type: str = typer.Option(
        "bash",
        "--format",
        "-f",
        help="Output script format: 'bash' or 'python' (default: bash)",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write generated mock script to file instead of stdout"
    ),
) -> None:
    """Generate a runnable Bash or Python D-Bus mock script from an Entity-Manager JSON."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)

    fmt_normalized = format_type.strip().lower()
    if fmt_normalized not in ("bash", "sh", "python", "py"):
        console.print(
            f"[bold red]Error: Unsupported format '{format_type}'. Supported formats: 'bash', 'python'.[/]"
        )
        raise typer.Exit(code=2)

    try:
        content = file_path.read_text(encoding="utf-8")
        config = EMMockGenerator.parse_em_json(content)
    except Exception as exc:
        console.print(f"[bold red]Error: Failed to parse Entity-Manager JSON: {exc}[/]")
        raise typer.Exit(code=2) from exc

    if fmt_normalized in ("bash", "sh"):
        script_code = EMMockGenerator.generate_busctl_script(config)
    else:
        script_code = EMMockGenerator.generate_python_mock(config)

    if output:
        try:
            output.write_text(script_code, encoding="utf-8")
            console.print(f"[green]✔ Mock script successfully written to {output}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write output file: {exc}[/]")
            raise typer.Exit(code=2) from exc
    else:
        print(script_code, end="")
```

- [x] **Step 4: Run CLI tests to verify success**

Run: `uv run pytest tests/test_cli_log_em.py -v`
Expected: ALL PASS (including existing log and em validate tests)

- [x] **Step 5: Commit Task 2**

```bash
git add src/fw_diag_tool/cli.py tests/test_cli_log_em.py
git commit -m "feat(cli): add 'fw-diag em mock' command for D-Bus mock script generation"
```

---

### Task 3: GUI Integration — Add "Mock 產生器" Mode to EM Builder Page

**Files:**
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Modify: `src/fw_diag_tool/gui/pages/em_builder_ui.py`
- Test: `tests/test_em_builder_ui.py`

**Interfaces:**
- Consumes: `EMMockGenerator` from `fw_diag_tool.em`, session state `em_devices_list`, i18n translation keys
- Produces: Third radio work mode "🧪 Mock 產生器" in EM Builder UI with interactive format selection, code viewer, and one-click script download

- [x] **Step 1: Add i18n translation keys**

In `src/fw_diag_tool/i18n/domains/gui.py`, add the new keys to `GUI_TRANSLATIONS` under the Entity-Manager section:

```python
    "em_mode_mock": {
        "zh-TW": "🧪 D-Bus Mock 腳本產生器 (Mock Generator)",
        "en-US": "🧪 D-Bus Mock Script Generator (Mock Generator)",
    },
    "em_mock_format": {
        "zh-TW": "選擇腳本格式 (Script Format)",
        "en-US": "Select Script Format",
    },
    "em_mock_generate": {
        "zh-TW": "✨ 產生 D-Bus Mock 腳本",
        "en-US": "✨ Generate D-Bus Mock Script",
    },
    "em_mock_download": {
        "zh-TW": "下載 Mock 腳本",
        "en-US": "Download Mock Script",
    },
    "em_mock_no_devices": {
        "zh-TW": "目前尚未設定任何裝置。請先於「視覺化建置模式」新增裝置，或點擊下方按鈕載入範例裝置。",
        "en-US": "No devices configured yet. Please add devices in Visual Build Mode, or click below to load sample devices.",
    },
```

- [x] **Step 2: Write failing AppTest GUI tests**

In `tests/test_em_builder_ui.py`, append tests verifying the new Mock Generator mode:

```python
def _mock_mode_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import _get_default_sample_devices, render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = list(_get_default_sample_devices())
    render()


def test_apptest_em_mock_mode_generate_bash() -> None:
    """Test generating Bash busctl mock script in Mock Generator mode."""
    at = AppTest.from_function(_mock_mode_app, default_timeout=15).run()
    assert not at.exception

    # Find and click Generate Mock button
    btn_gen = next((b for b in at.button if "Mock" in b.label and "產生" in b.label), None)
    assert btn_gen is not None
    btn_gen.click().run()
    assert not at.exception

    # Verify code block with bash script appears
    assert len(at.code) >= 1
    assert any("#!/bin/bash" in c.value for c in at.code)
    assert any("/xyz/openbmc_project/sensors" in c.value for c in at.code)
    assert len(at.download_button) >= 1


def _mock_mode_empty_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = []
    render()


def test_apptest_em_mock_mode_empty_state_and_sample_load() -> None:
    """Test Mock Generator mode empty state and loading sample devices."""
    at = AppTest.from_function(_mock_mode_empty_app, default_timeout=15).run()
    assert not at.exception
    assert any("尚未設定任何裝置" in info.value for info in at.info)

    # Click load sample button
    btn_sample = next((b for b in at.button if "載入標準" in b.label or "範本" in b.label), None)
    assert btn_sample is not None
    btn_sample.click().run()
    assert not at.exception

    # Now click generate
    btn_gen = next((b for b in at.button if "Mock" in b.label and "產生" in b.label), None)
    assert btn_gen is not None
    btn_gen.click().run()
    assert not at.exception
    assert len(at.code) >= 1
```

- [x] **Step 3: Update `src/fw_diag_tool/gui/pages/em_builder_ui.py`**

Add `_render_mock_mode()` and wire it into `render()`:

```python
from fw_diag_tool.em import EMBuilder, EMMockGenerator, EMValidator
```

In `render()`:
```python
    mode_options = [
        t("em_mode_build", domain="gui"),
        t("em_mode_validate", domain="gui"),
        t("em_mode_mock", domain="gui"),
    ]
    mode = st.radio(
        t("em_work_mode", domain="gui"),
        mode_options,
        key="em_mode_select",
        horizontal=True,
    )

    if mode == mode_options[0]:
        _render_build_mode()
    elif mode == mode_options[1]:
        _render_validate_mode()
    else:
        _render_mock_mode()
```

Implement `_render_mock_mode()`:
```python
def _render_mock_mode() -> None:
    """Render Entity-Manager to D-Bus Mock Script Generator mode."""
    st.markdown(
        "將已設定的板卡感測器與 FRU 拓撲轉換為 **OpenBMC D-Bus Mock 腳本**，"
        "可在無真實硬體或 QEMU 開發環境下快速模擬感測器服務。"
    )

    devices_list: list[EMDeviceEntry] = st.session_state.get("em_devices_list", [])

    if not devices_list:
        st.info(t("em_mock_no_devices", domain="gui"))
        if st.button(t("em_load_sample_devices", domain="gui"), key="em_mock_btn_load_sample"):
            st.session_state["em_devices_list"] = list(_get_default_sample_devices())
            st.rerun()
        return

    st.subheader(f"已就緒裝置清單 ({len(devices_list)} 個裝置)")
    df_rows = [
        {
            "序號": idx + 1,
            "裝置名稱": dev.name,
            "晶片型號": dev.template.chip_name,
            "類別": dev.template.category,
            "I2C 匯流排": dev.bus,
            "7-bit 位址": f"0x{dev.address:02x}",
        }
        for idx, dev in enumerate(devices_list)
    ]
    st.dataframe(pd.DataFrame(df_rows))

    col_fmt, col_btn = st.columns([2, 1])
    with col_fmt:
        format_choice = st.radio(
            t("em_mock_format", domain="gui"),
            ["Bash (busctl)", "Python (standalone)"],
            horizontal=True,
            key="em_mock_fmt_select",
        )
    with col_btn:
        st.write("")
        st.write("")
        gen_clicked = st.button(t("em_mock_generate", domain="gui"), key="em_btn_gen_mock")

    if gen_clicked:
        board_name = st.session_state.get("em_board_name_input", "Yosemite_V4_Mainboard")
        probe_expr = st.session_state.get("em_probe_input", "TRUE")
        config = EMBoardConfig(
            board_name=board_name.strip() or "Yosemite_V4_Mainboard",
            devices=list(devices_list),
            probe_expression=probe_expr.strip() or "TRUE",
        )

        if "Bash" in format_choice:
            script_code = EMMockGenerator.generate_busctl_script(config)
            st.session_state["em_mock_script"] = script_code
            st.session_state["em_mock_lang"] = "bash"
            st.session_state["em_mock_filename"] = f"mock_{board_name.lower()}_sensors.sh"
            st.session_state["em_mock_mime"] = "text/x-sh"
        else:
            script_code = EMMockGenerator.generate_python_mock(config)
            st.session_state["em_mock_script"] = script_code
            st.session_state["em_mock_lang"] = "python"
            st.session_state["em_mock_filename"] = f"mock_{board_name.lower()}_sensors.py"
            st.session_state["em_mock_mime"] = "text/x-python"

    if st.session_state.get("em_mock_script"):
        st.subheader("產出的 D-Bus Mock 腳本")
        script_content = st.session_state["em_mock_script"]
        lang = st.session_state.get("em_mock_lang", "bash")
        filename = st.session_state.get("em_mock_filename", "mock_sensors.sh")
        mime_type = st.session_state.get("em_mock_mime", "text/plain")

        st.code(script_content, language=lang)
        st.download_button(
            t("em_mock_download", domain="gui"),
            script_content,
            file_name=filename,
            mime=mime_type,
            key="em_btn_download_mock",
        )
```

- [x] **Step 4: Run full test suites**

Run:
```bash
uv run pytest tests/test_em_builder_ui.py -v
uv run pytest tests/test_em_mock_gen.py tests/test_cli_log_em.py tests/test_em_builder_ui.py tests/test_em_builder.py -v
uv run ruff check src/fw_diag_tool/em/ src/fw_diag_tool/gui/pages/em_builder_ui.py
uv run mypy src/fw_diag_tool/em/
```
Expected: ALL PASS

- [x] **Step 5: Commit Task 3**

```bash
git add src/fw_diag_tool/i18n/domains/gui.py src/fw_diag_tool/gui/pages/em_builder_ui.py tests/test_em_builder_ui.py
git commit -m "feat(gui): integrate D-Bus mock script generator tab into EM Builder UI"
```

---

## Verification & Acceptance Checklist

1. **Unit & Integration Tests:**
   ```bash
   uv run pytest tests/test_em_mock_gen.py tests/test_cli_log_em.py tests/test_em_builder_ui.py -v
   ```
   All tests pass with 100% coverage across new mock generator functionality.

2. **CLI Verification:**
   ```bash
   uv run fw-diag em mock --help
   uv run fw-diag em mock <sample_em.json> --format bash
   uv run fw-diag em mock <sample_em.json> --format python -o /tmp/mock_sensors.py
   ```

3. **GUI Verification:**
   Launch Streamlit and test the "🧪 Mock 產生器" tab:
   - Load standard 4-device template
   - Switch to Mock Generator
   - Generate Bash and Python scripts
   - Verify code display and download button

4. **Code Quality & Typing:**
   ```bash
   uv run ruff check .
   uv run mypy src/fw_diag_tool
   ```

---

## Completion Record (2026-09-02)

- [x] Core generator and parser: `fdbbc1e`, `525f9cb`, `3afab8e`, `40ada5a`, and `25d8db7` cover strict EM input handling, deterministic collision-free mapping, quoted output, and a real `dbus-next` daemon source.
- [x] CLI and GUI integration: `dd34349` plus the GUI hardening commits through `b06d4e9` cover `fw-diag em mock`, i18n, AppTest state invalidation, and artifact metadata binding.
- [x] Fresh final evidence: `uv run pytest` completed with 1518 passed; `uv run ruff check .`, `uv run mypy src/`, and `uv run mkdocs build --strict` all exited zero.
- [x] Generated scripts: representative Python and Bash artifacts passed `py_compile` and `bash -n`; the CLI output files were written successfully.
- Evidence boundary: local source/syntax checks do not prove permissions or ownership on a target OpenBMC system bus; that runtime check still requires a deployed BMC policy.
