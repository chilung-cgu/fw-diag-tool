from __future__ import annotations

import re
from typing import Any


class DeviceTreeGenerator:
    # Generates Linux Kernel and OpenBMC compliant Device Tree (.dts) nodes from topology

    _NODE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9,._+\-]*$")
    _COMPATIBLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9,._+\-]*,[A-Za-z0-9][A-Za-z0-9,._+\-]*$")

    @staticmethod
    def _parse_int(name: str, value: int | str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError(f"{name} must be an integer")
        try:
            parsed = int(value, 0) if isinstance(value, str) else int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc
        return parsed

    @classmethod
    def _validate_address(cls, name: str, value: int | str) -> int:
        address = cls._parse_int(name, value)
        if not 0x08 <= address <= 0x77:
            raise ValueError(f"{name} must be a non-reserved 7-bit I2C address (0x08..0x77)")
        return address

    @classmethod
    def _validate_node_name(cls, name: str) -> str:
        if not isinstance(name, str):
            raise TypeError("device name must be a string")
        if not cls._NODE_NAME_RE.fullmatch(name):
            raise ValueError(
                "device name must start with a letter and contain only Device Tree name characters"
            )
        return name

    @classmethod
    def _validate_compatible(cls, compatible: str) -> str:
        if not isinstance(compatible, str):
            raise TypeError("compatible must be a string")
        if not cls._COMPATIBLE_RE.fullmatch(compatible):
            raise ValueError("compatible must be an explicit 'vendor,device' string")
        return compatible

    @classmethod
    def generate_dts_from_topology(
        cls,
        bus_num: int = 1,
        mux_addr: int | str = 0x70,
        devices: list[dict[str, Any]] | None = None,
        node_name: str = "i2c_bus",
        clock_frequency: int = 400000,
        mux_compatible: str = "nxp,pca9548",
    ) -> str:
        bus = cls._parse_int("bus_num", bus_num)
        if not 0 <= bus <= 0xFFFF:
            raise ValueError("bus_num must be between 0 and 65535")
        frequency = cls._parse_int("clock_frequency", clock_frequency)
        if not 1 <= frequency <= 0xFFFFFFFF:
            raise ValueError("clock_frequency must be between 1 and 0xFFFFFFFF")
        cls._validate_node_name(node_name)
        m_addr = cls._validate_address("mux_addr", mux_addr)
        mux_compat = cls._validate_compatible(mux_compatible)
        if devices is not None and not isinstance(devices, list):
            raise TypeError("devices must be a list of mappings")

        channels: dict[int, list[tuple[int, str, str]]] = {ch: [] for ch in range(8)}
        seen_addresses: set[tuple[int, int]] = set()
        for index, device in enumerate(devices or []):
            if not isinstance(device, dict):
                raise TypeError(f"devices[{index}] must be a mapping")
            if "addr" not in device:
                raise ValueError(f"devices[{index}] is missing addr")
            d_addr = cls._validate_address(f"devices[{index}].addr", device["addr"])
            channel = cls._parse_int(f"devices[{index}].channel", device.get("channel", 0))
            if not 0 <= channel <= 7:
                raise ValueError(f"devices[{index}].channel must be between 0 and 7")
            if (channel, d_addr) in seen_addresses:
                raise ValueError(f"duplicate I2C address 0x{d_addr:02X} on MUX channel {channel}")
            seen_addresses.add((channel, d_addr))

            name = cls._validate_node_name(device.get("name", "device"))
            compatible = cls._validate_compatible(device.get("compatible", ""))
            channels[channel].append((d_addr, name, compatible))

        lines = [
            "// SPDX-License-Identifier: GPL-2.0+ or MIT",
            "/*",
            " * 自動產生的 Linux／OpenBMC Device Tree Source（.dts）",
            " * 由 fw-diag-tool（Firmware Diagnostic Toolkit）產生",
            " */",
            "",
            f"&i2c{bus} {{",
            '    status = "okay";',
            f"    clock-frequency = <{frequency}>;",
            "",
            f"    i2c-mux@{m_addr:x} {{",
            f'        compatible = "{mux_compat}";',
            f"        reg = <0x{m_addr:02x}>;",
            "        #address-cells = <1>;",
            "        #size-cells = <0>;",
            "        i2c-mux-idle-disconnect;",
            "",
        ]

        for channel in range(8):
            lines.append(f"        i2c@{channel} {{")
            lines.append("            #address-cells = <1>;")
            lines.append("            #size-cells = <0>;")
            lines.append(f"            reg = <{channel}>;")
            lines.append("")
            for address, name, compatible in channels[channel]:
                lines.append(f"            {name}@{address:x} {{")
                lines.append(f'                compatible = "{compatible}";')
                lines.append(f"                reg = <0x{address:02x}>;")
                lines.append("            };")
                lines.append("")
            lines.append("        };")
            lines.append("")

        lines.append("    };")
        lines.append("};")
        lines.append("")
        return "\n".join(lines)
