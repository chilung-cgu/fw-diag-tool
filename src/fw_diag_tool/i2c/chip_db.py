"""I2C / SMBus / PMBus Chip Identification & Device Registry Database.

Maps 7-bit and 8-bit I2C addresses to known peripheral devices, categorizing
their functions, typical registers, addressing modes, and default protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChipProfile:
    """Known chip profile information."""

    name: str
    category: str
    protocol: str  # "I2C", "SMBus", "PMBus", "EEPROM", etc.
    typical_speed_khz: int
    description: str
    addr_7bit_range: list[int]
    default_register_len: int = 1  # 1 byte or 2 bytes
    extra_info: dict[str, Any] = field(default_factory=dict)


# Comprehensive database of standard I2C / SMBus / PMBus chips and peripheral ranges
CHIP_DATABASE: list[ChipProfile] = [
    # 1. EEPROM / NVM
    ChipProfile(
        name="AT24Cxx / 24LCxx EEPROM",
        category="EEPROM / Memory",
        protocol="EEPROM",
        typical_speed_khz=400,
        description="I2C Serial EEPROM (e.g. 24C02/04/08/16/32/64/128/256/512/M01)",
        addr_7bit_range=list(range(0x50, 0x58)),  # 0x50 - 0x57
        default_register_len=1,
        extra_info={"page_size_bytes": 16, "write_cycle_ms": 5.0},
    ),
    ChipProfile(
        name="DDC / EDID Display EEPROM",
        category="Display / DDC",
        protocol="EEPROM",
        typical_speed_khz=100,
        description="VESA Display Data Channel (EDID) EEPROM on HDMI/DisplayPort/VGA",
        addr_7bit_range=[0x50],
        default_register_len=1,
    ),
    # 2. Temperature & Environmental Sensors
    ChipProfile(
        name="LM75 / TMP75 / TMP102 Temperature Sensor",
        category="Temperature Sensor",
        protocol="I2C",
        typical_speed_khz=400,
        description="Digital Temperature Sensor with 9-bit to 12-bit Two's Complement resolution",
        addr_7bit_range=list(range(0x48, 0x50)),  # 0x48 - 0x4F
        default_register_len=1,
        extra_info={"reg_temp": 0x00, "reg_config": 0x01, "reg_thyst": 0x02, "reg_tos": 0x03},
    ),
    ChipProfile(
        name="ADT7410 / ADT7420 High-Accuracy Temp Sensor",
        category="Temperature Sensor",
        protocol="I2C",
        typical_speed_khz=400,
        description="13-bit/16-bit Temperature Sensor",
        addr_7bit_range=[0x48, 0x49, 0x4A, 0x4B],
        default_register_len=1,
    ),
    ChipProfile(
        name="MCP9808 Precision Temperature Sensor",
        category="Temperature Sensor",
        protocol="I2C",
        typical_speed_khz=400,
        description="Microchip 0.0625°C Max Accuracy Digital Temperature Sensor",
        addr_7bit_range=list(range(0x18, 0x20)),  # 0x18 - 0x1F
        default_register_len=1,
    ),
    # 3. Voltage, Current, and Power Monitors
    ChipProfile(
        name="INA219 / INA226 / INA230 Current/Power Monitor",
        category="Power Monitor",
        protocol="I2C",
        typical_speed_khz=400,
        description="Bi-directional Current and Power Monitor with I2C/SMBus Interface",
        addr_7bit_range=list(range(0x40, 0x46)),  # 0x40 - 0x45
        default_register_len=1,
        extra_info={
            "reg_config": 0x00,
            "reg_shunt_v": 0x01,
            "reg_bus_v": 0x02,
            "reg_power": 0x03,
            "reg_current": 0x04,
            "reg_cal": 0x05,
        },
    ),
    ChipProfile(
        name="PAC1934 Multi-Channel Power Monitor",
        category="Power Monitor",
        protocol="I2C",
        typical_speed_khz=1000,
        description="Microchip 4-Channel DC Power/Energy Monitor",
        addr_7bit_range=[0x10, 0x11, 0x12],
        default_register_len=1,
    ),
    # 4. GPIO Expanders
    ChipProfile(
        name="PCA9555 / TCA9539 / PCA9535 16-bit GPIO Expander",
        category="GPIO Expander",
        protocol="I2C",
        typical_speed_khz=400,
        description="16-bit I2C/SMBus I/O Expander with Interrupt Output and Config Registers",
        addr_7bit_range=list(range(0x20, 0x28)),  # 0x20 - 0x27
        default_register_len=1,
        extra_info={
            "reg_in0": 0x00,
            "reg_in1": 0x01,
            "reg_out0": 0x02,
            "reg_out1": 0x03,
            "reg_cfg0": 0x06,
            "reg_cfg1": 0x07,
        },
    ),
    ChipProfile(
        name="PCF8574 / PCF8574A 8-bit Quasi-bidirectional GPIO Expander",
        category="GPIO Expander",
        protocol="I2C",
        typical_speed_khz=100,
        description="8-bit Remote I/O Expander for I2C-bus (Quasi-bidirectional, No Register Byte)",
        addr_7bit_range=list(range(0x20, 0x28)) + list(range(0x38, 0x40)),
        default_register_len=0,
    ),
    ChipProfile(
        name="MCP23017 / MCP23008 GPIO Expander",
        category="GPIO Expander",
        protocol="I2C",
        typical_speed_khz=400,
        description="16-bit I2C I/O Expander with Serial Interface",
        addr_7bit_range=list(range(0x20, 0x28)),
        default_register_len=1,
    ),
    # 5. PMBus Power Controllers & Voltage Regulators (VR)
    ChipProfile(
        name="PMBus Power Controller / VR (XDPE / ISL / TPS / MP / MAX)",
        category="PMBus Power Management",
        protocol="PMBus",
        typical_speed_khz=400,
        description="PMBus Digital Multiphase Controller / Point-of-Load VR (e.g. XDPE12284, ISL68137, TPS53681, MP2975)",
        addr_7bit_range=list(range(0x58, 0x60)) + list(range(0x40, 0x48)) + list(range(0x60, 0x68)),
        default_register_len=1,
    ),
    ChipProfile(
        name="Delta / Murata / BelPower PMBus PSU",
        category="PMBus Power Supply",
        protocol="PMBus",
        typical_speed_khz=100,
        description="Server / Telecom AC-DC or DC-DC Power Supply with PMBus Command Interface",
        addr_7bit_range=list(range(0x58, 0x60)),
        default_register_len=1,
    ),
    # 6. Real-Time Clocks (RTC)
    ChipProfile(
        name="DS1307 / DS3231 / PCF8563 Real-Time Clock",
        category="Real-Time Clock (RTC)",
        protocol="I2C",
        typical_speed_khz=400,
        description="I2C Real-Time Clock / Calendar with Battery Backup",
        addr_7bit_range=[0x68, 0x51, 0x6F],
        default_register_len=1,
        extra_info={"reg_seconds": 0x00, "reg_minutes": 0x01, "reg_hours": 0x02},
    ),
    # 7. Displays
    ChipProfile(
        name="SSD1306 / SH1106 OLED Display Controller",
        category="Display Controller",
        protocol="I2C",
        typical_speed_khz=400,
        description="128x64 Dot Matrix OLED/PLED Segment/Common Driver with Controller",
        addr_7bit_range=[0x3C, 0x3D],
        default_register_len=1,
        extra_info={"control_cmd": 0x00, "control_data": 0x40},
    ),
    # 8. I2C Bus Multiplexers / Switches
    ChipProfile(
        name="PCA9548A / PCA9546A / TCA9548A I2C Multiplexer",
        category="I2C Switch / Mux",
        protocol="I2C",
        typical_speed_khz=400,
        description="8-Channel or 4-Channel I2C Bus Switch with Reset",
        addr_7bit_range=list(range(0x70, 0x78)),  # 0x70 - 0x77
        default_register_len=0,
    ),
    # 9. Special Addresses (I2C Spec & SMBus Spec)
    ChipProfile(
        name="General Call / START Byte",
        category="Special / Broadcast",
        protocol="I2C",
        typical_speed_khz=100,
        description="I2C General Call (0x00 write) / START Byte / Software Reset",
        addr_7bit_range=[0x00],
        default_register_len=1,
    ),
    ChipProfile(
        name="SMBus Alert Response Address (ARA)",
        category="SMBus Alert",
        protocol="SMBus",
        typical_speed_khz=100,
        description="SMBus Alert Response Address (0x0C Read returns address of alerting slave)",
        addr_7bit_range=[0x0C],
        default_register_len=0,
    ),
]


def lookup_device(address_7bit: int) -> ChipProfile | None:
    """Look up the most likely peripheral device profile for a given 7-bit I2C address."""
    for profile in CHIP_DATABASE:
        if address_7bit in profile.addr_7bit_range:
            return profile
    return None


def get_all_matching_devices(address_7bit: int) -> list[ChipProfile]:
    """Retrieve all possible peripheral matches for a 7-bit I2C address."""
    return [p for p in CHIP_DATABASE if address_7bit in p.addr_7bit_range]
