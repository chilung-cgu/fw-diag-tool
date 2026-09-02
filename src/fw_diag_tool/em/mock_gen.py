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
    if any(k in token for k in ("mux", "pca954", "tca954")):
        return "mux"
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


def _parse_int_field(value: Any, *, path: str, minimum: int, maximum: int) -> int:
    """Parse and validate an integer field with explicit bounds."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"{path} must be an integer")
    try:
        parsed = int(value, 0) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError(f"{path} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        if path.endswith("Address"):
            raise ValueError(f"{path} must be a non-reserved 7-bit I2C address (0x08..0x77)")
        raise ValueError(f"{path} must be between {minimum} and {maximum}")
    return parsed


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
            raise TypeError("Entity-Manager configuration root must be a JSON object")

        if "Exposes" not in data:
            raise ValueError("Entity-Manager configuration is missing Exposes")
        exposes_list = data["Exposes"]
        if not isinstance(exposes_list, list):
            raise TypeError("Exposes must be a JSON array")

        board_name = str(data.get("Name", "Mock_Board"))
        probe_expr = str(data.get("Probe", "TRUE"))

        devices: list[EMDeviceEntry] = []
        for idx, item in enumerate(exposes_list):
            path = f"Exposes[{idx}]"
            if not isinstance(item, dict):
                raise TypeError(f"{path} must be a JSON object")

            for field_name in ("Name", "Type", "Bus", "Address"):
                if field_name not in item:
                    raise ValueError(f"{path} is missing {field_name}")

            name = str(item["Name"])
            type_name = str(item["Type"])
            bus = _parse_int_field(item["Bus"], path=f"{path}.Bus", minimum=0, maximum=65535)
            address = _parse_int_field(
                item["Address"], path=f"{path}.Address", minimum=0x08, maximum=0x77
            )

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

            custom_fields: dict[str, Any] = {
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
    def _get_sensor_mapping(cls, dev: EMDeviceEntry) -> dict[str, Any] | None:
        """Map a device entry to its category metadata, unit, and default value."""
        cat = dev.template.category.lower()
        if cat in ("gpio", "mux"):
            return None

        if cat == "temperature":
            return {
                "kind": "temperature",
                "unit": "xyz.openbmc_project.Sensor.Value.Unit.DegreesC",
                "value": 25.0,
                "is_sensor": True,
            }
        elif cat == "fan":
            return {
                "kind": "fan_tach",
                "unit": "xyz.openbmc_project.Sensor.Value.Unit.RPMS",
                "value": 5000.0,
                "is_sensor": True,
            }
        elif cat in ("psu", "hotswap"):
            return {
                "kind": "power",
                "unit": "xyz.openbmc_project.Sensor.Value.Unit.Watts",
                "value": 100.0,
                "is_sensor": True,
            }
        elif cat == "adc":
            return {
                "kind": "voltage",
                "unit": "xyz.openbmc_project.Sensor.Value.Unit.Volts",
                "value": 3.3,
                "is_sensor": True,
            }
        elif cat == "fru":
            return {
                "kind": "inventory",
                "unit": "",
                "value": 0.0,
                "is_sensor": False,
            }
        else:
            return {
                "kind": "temperature",
                "unit": "xyz.openbmc_project.Sensor.Value.Unit.DegreesC",
                "value": 25.0,
                "is_sensor": True,
            }

    @classmethod
    def _build_mock_objects(cls, config: EMBoardConfig) -> list[dict[str, Any]]:
        """Construct deterministic, collision-free mock sensor object records."""
        supported: list[tuple[EMDeviceEntry, dict[str, Any]]] = []
        for dev in config.devices:
            mapping = cls._get_sensor_mapping(dev)
            if mapping is not None:
                supported.append((dev, mapping))

        base_counts: dict[str, int] = {}
        for dev, _ in supported:
            base = _sanitize_name(dev.name)
            base_counts[base] = base_counts.get(base, 0) + 1

        used_paths: set[str] = set()
        objects: list[dict[str, Any]] = []
        for dev, mapping in supported:
            base = _sanitize_name(dev.name)
            component = f"{base}_b{dev.bus}_a{dev.address:02x}" if base_counts[base] > 1 else base
            sensor_kind = mapping["kind"]
            prefix = (
                "/xyz/openbmc_project/inventory/system/board"
                if sensor_kind == "inventory"
                else f"/xyz/openbmc_project/sensors/{sensor_kind}"
            )
            candidate_path = f"{prefix}/{component}"
            if candidate_path in used_paths:
                counter = 2
                while f"{candidate_path}_{counter}" in used_paths:
                    counter += 1
                candidate_path = f"{candidate_path}_{counter}"

            used_paths.add(candidate_path)
            objects.append({
                "name": dev.name,
                "chip": dev.template.chip_name,
                "category": dev.template.category.lower(),
                "bus": dev.bus,
                "address": f"0x{dev.address:02x}",
                "path": candidate_path,
                "unit": mapping["unit"],
                "value": mapping["value"],
                "is_sensor": mapping["is_sensor"],
            })
        return objects

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

        objects = cls._build_mock_objects(config)
        for obj in objects:
            clean_name = _sanitize_name(obj["name"])
            path = obj["path"]

            if not obj["is_sensor"]:
                lines.extend([
                    f"# --- FRU Inventory: {obj['name']} (Bus {obj['bus']}, Addr {obj['address']}) ---",
                    f"# Expected Object Path: {path}",
                    f'# Verify with: busctl call xyz.openbmc_project.ObjectMapper /xyz/openbmc_project/object_mapper xyz.openbmc_project.ObjectMapper GetObject sas \"{path}\" 0',
                    f'echo "[MOCK] Registering FRU Board Object: {clean_name}"',
                    f'busctl set-property {cls.MOCK_SERVICE} {path} {cls.BOARD_INTF} PrettyName s \"{clean_name}\" 2>/dev/null || true',
                    "",
                ])
                continue

            cat = obj["category"]
            val = obj["value"]
            unit = obj["unit"]
            unit_short = unit.split(".")[-1]

            lines.extend([
                f"# --- Sensor: {obj['name']} ({obj['chip']}, Bus {obj['bus']}, Addr {obj['address']}) ---",
                f"# Expected Object Path: {path}",
                f'# Verify with: busctl call xyz.openbmc_project.ObjectMapper /xyz/openbmc_project/object_mapper xyz.openbmc_project.ObjectMapper GetObject sas \"{path}\" 0',
                f'echo "[MOCK] Publishing {cat} sensor: {clean_name} -> {val} ({unit_short})"',
                f"busctl set-property {cls.MOCK_SERVICE} {path} {cls.SENSOR_VALUE_INTF} Value d {val} 2>/dev/null || true",
                f'busctl set-property {cls.MOCK_SERVICE} {path} {cls.SENSOR_VALUE_INTF} Unit s \"{unit}\" 2>/dev/null || true',
                "",
            ])

        lines.extend([
            f'echo "[SUCCESS] Successfully registered {len(objects)} D-Bus mock objects for {config.board_name}."',
            'echo "[INFO] Inspect active sensors with: busctl tree xyz.openbmc_project.FWDiagMock"',
        ])
        return "\n".join(lines) + "\n"

    @classmethod
    def generate_python_mock(cls, config: EMBoardConfig) -> str:
        """Generate a standalone Python script using subprocess and busctl."""
        devices_data = cls._build_mock_objects(config)
        json_mock_data = json.dumps(devices_data, indent=4)

        board = config.board_name

        lines: list[str] = [
            "#!/usr/bin/env python3",
            f'\"\"\"OpenBMC D-Bus Sensor Mock Script for {board}.',
            "",
            "Generated by fw-diag-tool (Entity-Manager Mock Generator).",
            "Publishes and updates mock D-Bus sensor values via busctl.",
            '\"\"\"',
            "",
            "from __future__ import annotations",
            "",
            "import argparse",
            "import subprocess",
            "import sys",
            "import time",
            "",
            f'MOCK_SERVICE = \"{cls.MOCK_SERVICE}\"',
            f'SENSOR_VALUE_INTF = \"{cls.SENSOR_VALUE_INTF}\"',
            f'BOARD_INTF = \"{cls.BOARD_INTF}\"',
            "",
            f"MOCK_OBJECTS = {json_mock_data}",
            "",
            "",
            "def run_busctl(args: list[str]) -> bool:",
            '    \"\"\"Execute a busctl command safely via subprocess.\"\"\"',
            '    cmd = [\"busctl\"] + args',
            "    try:",
            "        res = subprocess.run(cmd, capture_output=True, text=True, check=False)",
            "        return res.returncode == 0",
            "    except FileNotFoundError:",
            '        print(\"[WARN] busctl not found. Simulating:\", \" \".join(cmd))',
            "        return False",
            "",
            "",
            "def setup_mock_objects() -> None:",
            '    \"\"\"Register and initialize all mock objects on D-Bus.\"\"\"',
            f'    print(f\"[INFO] Publishing {{len(MOCK_OBJECTS)}} mock objects for {board}...\")',
            "    for obj in MOCK_OBJECTS:",
            '        path = obj[\"path\"]',
            '        name = obj[\"name\"]',
            '        if obj[\"is_sensor\"]:',
            '            val = obj[\"value\"]',
            '            unit = obj[\"unit\"]',
            '            print(f\"  -> Publishing {obj[\x27category\x27]} sensor \x27{name}\x27 at {path} = {val}\")',
            '            run_busctl([\"set-property\", MOCK_SERVICE, path, SENSOR_VALUE_INTF, \"Value\", \"d\", str(val)])',
            '            run_busctl([\"set-property\", MOCK_SERVICE, path, SENSOR_VALUE_INTF, \"Unit\", \"s\", unit])',
            "        else:",
            '            print(f\"  -> Registering FRU inventory \x27{name}\x27 at {path}\")',
            '            run_busctl([\"set-property\", MOCK_SERVICE, path, BOARD_INTF, \"PrettyName\", \"s\", name])',
            '    print(\"[SUCCESS] All mock objects initialized.\")',
            "",
            "",
            "def main() -> int:",
            '    \"\"\"Main entrypoint for D-Bus mock script.\"\"\"',
            f'    parser = argparse.ArgumentParser(description=\"Mock D-Bus sensor daemon for {board}\")',
            '    parser.add_argument(\"--interval\", type=float, default=2.0, help=\"Periodic refresh interval\")',
            '    parser.add_argument(\"--once\", action=\"store_true\", help=\"Set properties once and exit\")',
            "    args = parser.parse_args()",
            "",
            "    setup_mock_objects()",
            "",
            "    if args.once:",
            "        return 0",
            "",
            '    print(\"[INFO] Monitoring mock state (Ctrl+C to stop)...\")',
            "    try:",
            "        while True:",
            "            time.sleep(args.interval)",
            "    except KeyboardInterrupt:",
            '        print(\"\\n[INFO] Stopped mock daemon.\")',
            "        return 0",
            "",
            "",
            'if __name__ == \"__main__\":',
            "    sys.exit(main())",
        ]

        return "\n".join(lines) + "\n"
