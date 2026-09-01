"""OpenBMC Entity-Manager JSON configuration builder."""

from __future__ import annotations

import json

from fw_diag_tool.em.models import EMBoardConfig, EMDeviceEntry


class EMBuilder:
    """Builder for generating valid OpenBMC Entity-Manager JSON configurations."""

    @classmethod
    def generate(cls, config: EMBoardConfig, *, indent: int = 4) -> str:
        """Validate and generate an Entity-Manager JSON configuration string.

        Args:
            config: Complete board configuration with devices.
            indent: JSON indentation spacing (default: 4).

        Returns:
            Well-formatted JSON string.

        Raises:
            ValueError: If any device address is out of range, bus is invalid,
                or duplicate bus/address endpoints exist.
        """
        seen_endpoints: set[tuple[int, int]] = set()

        for dev in config.devices:
            if not isinstance(dev.address, int) or dev.address < 0x08 or dev.address > 0x77:
                addr_hex = (
                    f"0x{dev.address:02x}" if isinstance(dev.address, int) else str(dev.address)
                )
                raise ValueError(
                    f"Device '{dev.name}' address {addr_hex} is out of valid 7-bit I2C range (0x08..0x77)"
                )

            if not isinstance(dev.bus, int) or dev.bus < 0 or dev.bus > 65535:
                raise ValueError(
                    f"Device '{dev.name}' bus {dev.bus} is out of valid range (0..65535)"
                )

            endpoint = (dev.bus, dev.address)
            if endpoint in seen_endpoints:
                raise ValueError(
                    f"Duplicate device endpoint conflict: Bus {dev.bus}, Address 0x{dev.address:02x} "
                    f"(device '{dev.name}')"
                )
            seen_endpoints.add(endpoint)

        return json.dumps(config.to_dict(), indent=indent)

    @classmethod
    def generate_from_devices(
        cls,
        board_name: str,
        devices: list[EMDeviceEntry],
        *,
        probe_expression: str = "TRUE",
        indent: int = 4,
    ) -> str:
        """Helper to construct EMBoardConfig and generate JSON in one call.

        Args:
            board_name: Name of the board or subsystem.
            devices: List of configured device entries.
            probe_expression: Entity-Manager probe expression (default: 'TRUE').
            indent: JSON indentation spacing (default: 4).

        Returns:
            Well-formatted JSON string.
        """
        config = EMBoardConfig(
            board_name=board_name,
            devices=devices,
            probe_expression=probe_expression,
        )
        return cls.generate(config, indent=indent)
