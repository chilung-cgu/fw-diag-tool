"""Comprehensive edge-case and boundary tests for virtual hardware emulators."""

from __future__ import annotations

import pytest

from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64
from fw_diag_tool.emulator.lm75 import VirtualLM75
from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128

# ---------------------------------------------------------------------------
# VirtualLM75 Temperature Sensor Tests
# ---------------------------------------------------------------------------


def test_lm75_boundary_temperatures() -> None:
    """Test LM75 extremes: minimum -128.0°C, maximum representable +127.9375°C, and 0.0°C."""
    sensor = VirtualLM75(addr_7bit=0x48)

    # Minimum boundary: -128.0 C
    sensor.set_temperature(-128.0)
    sensor.write([0x00])
    raw = sensor.read(2)
    # -128.0 / 0.0625 = -2048 -> 12-bit 0x800 -> 16-bit 0x8000
    assert raw == bytes([0x80, 0x00])

    # Maximum boundary: +127.9375 C
    sensor.set_temperature(127.9375)
    sensor.write([0x00])
    raw = sensor.read(2)
    # 127.9375 / 0.0625 = 2047 -> 12-bit 0x7FF -> 16-bit 0x7FF0
    assert raw == bytes([0x7F, 0xF0])

    # Zero boundary: 0.0 C
    sensor.set_temperature(0.0)
    sensor.write([0x00])
    raw = sensor.read(2)
    assert raw == bytes([0x00, 0x00])


def test_lm75_temperature_out_of_range_rejected() -> None:
    """Verify temperatures exceeding [-128.0, +128.0) are rejected."""
    sensor = VirtualLM75()
    with pytest.raises(ValueError, match="representable"):
        sensor.set_temperature(-128.01)
    with pytest.raises(ValueError, match="representable"):
        sensor.set_temperature(128.0)
    with pytest.raises(ValueError, match="representable"):
        sensor.set_temperature(200.0)


def test_lm75_register_pointer_and_config_flow() -> None:
    """Verify register pointer switching and configuration register read/write."""
    sensor = VirtualLM75(addr_7bit=0x49)
    # Write to CONFIG register (0x01) with shutdown mode bit set (0x01)
    res = sensor.write([0x01, 0x01])
    assert res["type"] == "Set Register Pointer"
    assert res["register"] == "CONFIG"
    assert sensor.config_reg == 0x01

    # Read 1 byte from config register
    assert sensor.read(1) == bytes([0x01])

    # Switch pointer to THYST (0x02) and read 2 bytes
    sensor.write([0x02])
    assert sensor.read(2) == bytes([0x4B, 0x00])

    # Switch pointer to TOS (0x03) and read 2 bytes
    sensor.write([0x03])
    assert sensor.read(2) == bytes([0x50, 0x00])


# ---------------------------------------------------------------------------
# VirtualSPIFlashW25Q128 SPI NOR Flash Tests
# ---------------------------------------------------------------------------


def test_spi_flash_page_program_wraps_within_page() -> None:
    """SPI NOR page programming must wrap within the 256-byte page boundary."""
    flash = VirtualSPIFlashW25Q128(total_size=4096)
    flash.write_enable()

    # Program starting at offset 0x00FE across the 256-byte boundary
    payload = [0x11, 0x22, 0x33, 0x44]
    ok = flash.page_program(address=0x00FE, data=payload)
    assert ok is True
    flash.complete_operation()

    # 0x00FE -> 0x11, 0x00FF -> 0x22
    # Wrapped back to page start: 0x0000 -> 0x33, 0x0001 -> 0x44
    assert flash.read_data(0x00FE, 2) == [0x11, 0x22]
    assert flash.read_data(0x0000, 2) == [0x33, 0x44]
    # Next page (0x0100) must remain unwritten (0xFF)
    assert flash.read_data(0x0100, 2) == [0xFF, 0xFF]


def test_spi_flash_nor_and_logic_and_erase() -> None:
    """NOR flash programming can only clear bits (1->0); erase resets sector to 0xFF."""
    flash = VirtualSPIFlashW25Q128(total_size=8192)

    # Write 0xAA (10101010)
    flash.write_enable()
    flash.page_program(0x0010, [0xAA])
    flash.complete_operation()
    assert flash.read_data(0x0010, 1) == [0xAA]

    # Write 0x55 (01010101) without erase -> result should be 0xAA & 0x55 = 0x00
    flash.write_enable()
    flash.page_program(0x0010, [0x55])
    flash.complete_operation()
    assert flash.read_data(0x0010, 1) == [0x00]

    # Sector erase resets the entire 4KB sector to 0xFF
    flash.write_enable()
    assert flash.sector_erase(0x0000) is True
    flash.complete_operation()
    assert flash.read_data(0x0010, 1) == [0xFF]


def test_spi_flash_busy_cycle_blocks_operations() -> None:
    """While busy, write_enable, page_program, and sector_erase must fail or be ignored."""
    flash = VirtualSPIFlashW25Q128(total_size=4096)
    flash.write_enable()
    assert flash.page_program(0x0000, [0x12, 0x34]) is True
    assert flash.busy is True

    # Attempt write enable while busy -> rejected
    flash.write_enable()
    assert flash.wel_latched is False

    # Attempt page_program while busy -> False
    assert flash.page_program(0x0010, [0x56]) is False

    # Attempt sector_erase while busy -> False
    assert flash.sector_erase(0x0000) is False

    # Clear busy
    flash.complete_operation()
    assert flash.busy is False


# ---------------------------------------------------------------------------
# VirtualEEPROM24C64 I2C EEPROM Tests
# ---------------------------------------------------------------------------


def test_eeprom_page_rollover_32byte_page() -> None:
    """EEPROM page write must roll over within 32-byte page and flag rollover_hazard."""
    eeprom = VirtualEEPROM24C64(page_size=32, capacity=1024)

    # Write 4 bytes starting at offset 30 (within page 0: 0..31)
    # Bytes should go to 30, 31, 0, 1
    write_res = eeprom.write([0x00, 30, 0xDE, 0xAD, 0xBE, 0xEF])
    assert write_res["rollover_hazard"] is True
    assert write_res["payload_len"] == 4
    assert "Rollover" in write_res["summary"]

    # ACK polling to finish write cycle
    assert eeprom.ack_polling() is True

    assert eeprom.memory[30] == 0xDE
    assert eeprom.memory[31] == 0xAD
    assert eeprom.memory[0] == 0xBE
    assert eeprom.memory[1] == 0xEF
    # Page 1 (offset 32) must be untouched
    assert eeprom.memory[32] == 0x00


def test_eeprom_sequential_write_within_page_no_hazard() -> None:
    """Writes staying fully within the page boundary should not flag rollover_hazard."""
    eeprom = VirtualEEPROM24C64(page_size=32, capacity=1024)
    write_res = eeprom.write([0x00, 0x04, 0x01, 0x02, 0x03])
    assert write_res["rollover_hazard"] is False
    assert eeprom.ack_polling() is True
    assert eeprom.read(0x0004, 3) == bytes([0x01, 0x02, 0x03])


def test_eeprom_dump_memory_formatting() -> None:
    """Verify dump_memory produces valid formatted hexadecimal lines."""
    eeprom = VirtualEEPROM24C64(page_size=32, capacity=512)
    eeprom.write([0x00, 0x00, 0xCA, 0xFE])
    eeprom.ack_polling()

    dump = eeprom.dump_memory(start=0, length=32)
    lines = dump.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("0x0000: CA FE")
    assert lines[1].startswith("0x0010: 00 00")
