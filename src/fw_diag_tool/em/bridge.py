"""Bridge between BoardProfile SSOT, OpenBMC Entity-Manager configurations, and Device Tree sources."""

from __future__ import annotations

import re

from fw_diag_tool.board_profile import BoardProfile, I2CDeviceProfile
from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.em.builder import EMBuilder
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
    EMDeviceTemplate,
)
from fw_diag_tool.em.templates import get_template

_SPEED_MODE_FREQ_MAP: dict[str, int] = {
    "standard": 100000,
    "fast": 400000,
    "fast_plus": 1000000,
    "high_speed": 3400000,
    "ultra_fast": 5000000,
}


def _dts_name(name: str) -> str:
    return re.sub(r"[\s_]+", "-", name.strip()).lower()


class EMBridge:
    """Bidirectional bridge for converting BoardProfile into Entity-Manager and Device Tree representations."""

    @classmethod
    def _create_device_entry(cls, dev: I2CDeviceProfile, bus_num: int) -> EMDeviceEntry:
        """Create an EMDeviceEntry from an I2CDeviceProfile."""
        chip_name = dev.compatible.split(",")[-1].strip()
        template = get_template(chip_name)
        if template is None and chip_name.lower().startswith("24c"):
            template = get_template(f"AT{chip_name}")

        if template is None:
            template = EMDeviceTemplate(
                category=dev.category,
                chip_name=chip_name,
                em_type=chip_name,
                default_power_state="On",
                required_fields=["Bus", "Address", "Name"],
                optional_fields={},
                description=f"Generic {dev.category} device ({dev.compatible})",
            )

        return EMDeviceEntry(
            template=template,
            bus=bus_num,
            address=dev.address_7bit,
            name=dev.name,
        )

    @classmethod
    def from_board_profile(
        cls,
        profile: BoardProfile,
        bus_num: int | None = None,
    ) -> EMBoardConfig:
        """Convert a BoardProfile into an OpenBMC Entity-Manager EMBoardConfig.

        Args:
            profile: Source BoardProfile containing bus and device topology.
            bus_num: Optional target I2C bus number.

        Returns:
            EMBoardConfig with configured device entries.

        Raises:
            ValueError: If bus_num is specified but not found in profile.
        """
        target_buses = profile.i2c_buses
        if bus_num is not None:
            target_buses = [b for b in profile.i2c_buses if b.bus_num == bus_num]
            if not target_buses:
                raise ValueError(
                    f"Bus number {bus_num} not found in BoardProfile '{profile.board_name}'"
                )

        all_entries: list[EMDeviceEntry] = []
        for bus in target_buses:
            for dev in bus.devices:
                all_entries.append(cls._create_device_entry(dev, bus.bus_num))
            for mux in bus.muxes:
                all_entries.append(cls._create_device_entry(mux, bus.bus_num))
                for channel in mux.channels:
                    if channel.devices and channel.downstream_bus_num is None:
                        raise ValueError(
                            f"MUX {mux.name} channel {channel.channel} requires downstream_bus_num "
                            "for Entity-Manager generation"
                        )
                    for dev in channel.devices:
                        assert channel.downstream_bus_num is not None
                        all_entries.append(cls._create_device_entry(dev, channel.downstream_bus_num))

        return EMBoardConfig(board_name=profile.board_name, devices=all_entries)

    @classmethod
    def to_em_json(
        cls,
        profile: BoardProfile,
        *,
        indent: int = 4,
        bus_num: int | None = None,
    ) -> str:
        """Convert a BoardProfile directly into Entity-Manager JSON string."""
        config = cls.from_board_profile(profile, bus_num=bus_num)
        return EMBuilder.generate(config, indent=indent)

    @classmethod
    def to_dts(
        cls,
        profile: BoardProfile,
        bus_num: int | None = None,
    ) -> str:
        """Generate Linux/OpenBMC Device Tree Source (.dts) from a BoardProfile.

        Args:
            profile: Source BoardProfile.
            bus_num: Optional target I2C bus number.

        Returns:
            Concatenated DTS string for the specified buses.

        Raises:
            ValueError: If bus_num is specified but not found in profile.
        """
        target_buses = profile.i2c_buses
        if bus_num is not None:
            target_buses = [b for b in profile.i2c_buses if b.bus_num == bus_num]
            if not target_buses:
                raise ValueError(
                    f"Bus number {bus_num} not found in BoardProfile '{profile.board_name}'"
                )

        dts_blocks: list[str] = []
        for bus in target_buses:
            clock_freq = _SPEED_MODE_FREQ_MAP.get(bus.speed_mode, 400000)
            direct_devices = [
                {"addr": dev.address_7bit, "name": _dts_name(dev.name), "compatible": dev.compatible}
                for dev in bus.devices
            ]
            muxes = [
                {
                    "addr": mux.address_7bit,
                    "compatible": mux.compatible,
                    "channels": [
                        {
                            "channel": channel.channel,
                            "devices": [
                                {"addr": dev.address_7bit, "name": _dts_name(dev.name), "compatible": dev.compatible}
                                for dev in channel.devices
                            ],
                        }
                        for channel in mux.channels
                    ],
                }
                for mux in bus.muxes
            ]

            dts_str = DeviceTreeGenerator.generate_i2c_bus(
                bus_num=bus.bus_num,
                direct_devices=direct_devices,
                muxes=muxes,
                clock_frequency=clock_freq,
            )
            dts_blocks.append(dts_str)

        return "\n\n".join(dts_blocks)
