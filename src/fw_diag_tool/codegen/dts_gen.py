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
    def _normalize_device(
        cls,
        device: Any,
        *,
        path: str,
    ) -> tuple[int, str, str]:
        if not isinstance(device, dict):
            raise TypeError(f"{path} must be a mapping")
        if "addr" not in device:
            raise ValueError(f"{path} is missing addr")
        address = cls._validate_address(f"{path}.addr", device["addr"])
        name = cls._validate_node_name(device.get("name", "device"))
        compatible = cls._validate_compatible(device.get("compatible", ""))
        return address, name, compatible

    @classmethod
    def generate_i2c_bus(
        cls,
        *,
        bus_num: int,
        direct_devices: list[dict[str, Any]],
        muxes: list[dict[str, Any]],
        clock_frequency: int = 400000,
    ) -> str:
        bus = cls._parse_int("bus_num", bus_num)
        if not 0 <= bus <= 0xFFFF:
            raise ValueError("bus_num must be between 0 and 65535")
        frequency = cls._parse_int("clock_frequency", clock_frequency)
        if not 1 <= frequency <= 0xFFFFFFFF:
            raise ValueError("clock_frequency must be between 1 and 0xFFFFFFFF")
        if not isinstance(direct_devices, list):
            raise TypeError("direct_devices must be a list of mappings")
        if not isinstance(muxes, list):
            raise TypeError("muxes must be a list of mappings")

        normalized_direct = [
            cls._normalize_device(device, path=f"direct_devices[{index}]")
            for index, device in enumerate(direct_devices)
        ]
        normalized_muxes: list[tuple[int, str, list[tuple[int, list[tuple[int, str, str]]]]]] = []
        parent_addresses = {address for address, _, _ in normalized_direct}

        for mux_index, mux in enumerate(muxes):
            path = f"muxes[{mux_index}]"
            if not isinstance(mux, dict):
                raise TypeError(f"{path} must be a mapping")
            if "addr" not in mux:
                raise ValueError(f"{path} is missing addr")
            mux_address = cls._validate_address(f"{path}.addr", mux["addr"])
            mux_compatible = cls._validate_compatible(mux.get("compatible", ""))
            if mux_address in parent_addresses:
                raise ValueError(f"duplicate I2C address 0x{mux_address:02X} on parent bus {bus}")
            parent_addresses.add(mux_address)
            raw_channels = mux.get("channels", [])
            if not isinstance(raw_channels, list):
                raise TypeError(f"{path}.channels must be a list of mappings")

            normalized_channels: list[tuple[int, list[tuple[int, str, str]]]] = []
            seen_channels: set[int] = set()
            for channel_index, channel in enumerate(raw_channels):
                channel_path = f"{path}.channels[{channel_index}]"
                if not isinstance(channel, dict):
                    raise TypeError(f"{channel_path} must be a mapping")
                channel_num = cls._parse_int(
                    f"{channel_path}.channel", channel.get("channel", 0)
                )
                if not 0 <= channel_num <= 7:
                    raise ValueError(f"{channel_path}.channel must be between 0 and 7")
                if channel_num in seen_channels:
                    raise ValueError(f"duplicate MUX channel {channel_num} in {path}")
                seen_channels.add(channel_num)
                raw_devices = channel.get("devices", [])
                if not isinstance(raw_devices, list):
                    raise TypeError(f"{channel_path}.devices must be a list of mappings")
                normalized_devices = [
                    cls._normalize_device(device, path=f"{channel_path}.devices[{device_index}]")
                    for device_index, device in enumerate(raw_devices)
                ]
                addresses = [address for address, _, _ in normalized_devices]
                if len(addresses) != len(set(addresses)):
                    raise ValueError(f"duplicate I2C address on MUX channel {channel_num}")
                normalized_channels.append((channel_num, normalized_devices))
            normalized_muxes.append((mux_address, mux_compatible, normalized_channels))

        lines = [
            "// SPDX-License-Identifier: GPL-2.0+ or MIT",
            f"&i2c{bus} {{",
            '    status = "okay";',
            f"    clock-frequency = <{frequency}>;",
            "",
        ]
        for address, name, compatible in normalized_direct:
            lines.extend([
                f"    {name}@{address:x} {{",
                f'        compatible = "{compatible}";',
                f"        reg = <0x{address:02x}>;",
                "    };",
                "",
            ])
        for mux_address, mux_compatible, channels in normalized_muxes:
            lines.extend([
                f"    i2c-mux@{mux_address:x} {{",
                f'        compatible = "{mux_compatible}";',
                f"        reg = <0x{mux_address:02x}>;",
                "        #address-cells = <1>;",
                "        #size-cells = <0>;",
                "        i2c-mux-idle-disconnect;",
                "",
            ])
            for channel_num, devices in channels:
                lines.extend([
                    f"        i2c@{channel_num} {{",
                    "            #address-cells = <1>;",
                    "            #size-cells = <0>;",
                    f"            reg = <{channel_num}>;",
                    "",
                ])
                for address, name, compatible in devices:
                    lines.extend([
                        f"            {name}@{address:x} {{",
                        f'                compatible = "{compatible}";',
                        f"                reg = <0x{address:02x}>;",
                        "            };",
                        "",
                    ])
                lines.extend(["        };", ""])
            lines.extend(["    };", ""])
        lines.extend(["};", ""])
        return "\n".join(lines)

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
        cls._validate_node_name(node_name)
        if devices is not None and not isinstance(devices, list):
            raise TypeError("devices must be a list of mappings")

        grouped_devices: dict[int, list[dict[str, Any]]] = {ch: [] for ch in range(8)}
        for index, device in enumerate(devices or []):
            if not isinstance(device, dict):
                raise TypeError(f"devices[{index}] must be a mapping")
            channel = cls._parse_int(f"devices[{index}].channel", device.get("channel", 0))
            if not 0 <= channel <= 7:
                raise ValueError(f"devices[{index}].channel must be between 0 and 7")
            grouped_devices[channel].append(device)

        return cls.generate_i2c_bus(
            bus_num=bus_num,
            direct_devices=[],
            muxes=[{
                "addr": mux_addr,
                "compatible": mux_compatible,
                "channels": [
                    {"channel": channel, "devices": channel_devices}
                    for channel, channel_devices in grouped_devices.items()
                ],
            }],
            clock_frequency=clock_frequency,
        )
