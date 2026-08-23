import pytest

from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64
from fw_diag_tool.emulator.lm75 import VirtualLM75
from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128


def test_eeprom_basic_write_and_read():
    eeprom = VirtualEEPROM24C64(addr_7bit=0x50, page_size=32)
    result = eeprom.write([0x00, 0x00, 0xAB, 0xCD])
    assert result["offset"] == 0x00
    assert eeprom.ack_polling() is True
    data = eeprom.read(offset=0x00, length=2)
    assert data == bytes([0xAB, 0xCD])


def test_eeprom_page_boundary_rollover():
    eeprom = VirtualEEPROM24C64(page_size=8)
    result = eeprom.write([0x06, 0xAA, 0xBB, 0xCC, 0xDD], preferred_address_bytes=1)
    assert result["rollover_hazard"] is True
    assert eeprom.memory[6] == 0xAA
    assert eeprom.memory[7] == 0xBB
    assert eeprom.memory[0] == 0xCC
    assert eeprom.memory[1] == 0xDD


def test_24c64_emulator_defaults_to_two_byte_word_address():
    eeprom = VirtualEEPROM24C64()
    result = eeprom.write([0x01, 0x00, 0xAA])
    assert result["offset"] == 0x0100
    assert eeprom.ack_polling() is True
    assert eeprom.read(0x0100, 1) == b"\xaa"


def test_lm75_temperature_encoding():
    sensor = VirtualLM75(addr_7bit=0x48)
    sensor.set_temperature(25.5)
    # Write pointer to TEMP register
    sensor.write([0x00])
    data = sensor.read(2)
    # 25.5C / 0.0625 = 408 -> raw_12bit=408 -> shifted left by 4 = 0x1980
    assert data == bytes([0x19, 0x80])


def test_lm75_negative_temperature():
    sensor = VirtualLM75()
    sensor.set_temperature(-10.0)
    sensor.write([0x00])
    data = sensor.read(2)
    # -10.0C / 0.0625 = -160 -> 12-bit two complement: 0xF60 -> shifted left by 4 = 0xF600
    assert data == bytes([0xF6, 0x00])


def test_spi_flash_jedec_and_wren_program_read():
    flash = VirtualSPIFlashW25Q128()
    jedec = flash.read_jedec_id()
    assert jedec == [0xEF, 0x40, 0x18]
    assert flash.read_data(0x001000, 4) == [0xFF, 0xFF, 0xFF, 0xFF]
    flash.write_enable()
    ok = flash.page_program(address=0x001000, data=[0xDE, 0xAD, 0xBE, 0xEF])
    assert ok is True
    read_back = flash.read_data(address=0x001000, length=4)
    assert read_back == [0xDE, 0xAD, 0xBE, 0xEF]


def test_spi_flash_program_obeys_nor_one_to_zero_and_busy_cycle():
    flash = VirtualSPIFlashW25Q128(total_size=256)
    flash.write_enable()
    assert flash.page_program(0, [0x00]) is True
    assert flash.read_data(0, 1) == [0x00]
    flash.write_enable()
    assert flash.page_program(1, [0xAA]) is False
    assert flash.wel_latched is False
    flash.complete_operation()
    flash.write_enable()
    assert flash.page_program(0, [0xFF]) is True
    assert flash.read_data(0, 1) == [0x00]


def test_spi_flash_write_without_wren_returns_false():
    flash = VirtualSPIFlashW25Q128()
    ok = flash.page_program(address=0x000000, data=[0x55])
    assert ok is False


def test_emulators_reject_invalid_boundaries_instead_of_silent_wrap_or_truncation():
    eeprom = VirtualEEPROM24C64()
    with pytest.raises(ValueError, match="length"):
        eeprom.read(0, -1)
    with pytest.raises(ValueError, match="page_size"):
        VirtualEEPROM24C64(page_size=0)
    with pytest.raises(ValueError, match="out of range"):
        eeprom.write([0x20, 0x00, 0x01], preferred_address_bytes=2)
    with pytest.raises(ValueError, match="data_bytes"):
        eeprom.write([0x00, 0x100])
    with pytest.raises(ValueError, match="start"):
        eeprom.dump_memory(-1, 2)

    flash = VirtualSPIFlashW25Q128(total_size=4096)
    flash.write_enable()
    with pytest.raises(ValueError, match="address"):
        flash.page_program(-1, [0x01])
    with pytest.raises(ValueError, match="length"):
        flash.read_data(0, -1)
    with pytest.raises(ValueError, match="capacity"):
        flash.read_data(4095, 2)

    sensor = VirtualLM75()
    with pytest.raises(ValueError, match="num_bytes"):
        sensor.read(-1)
    assert sensor.read(0) == b""
    with pytest.raises(ValueError, match="data_bytes"):
        sensor.write([0x01, 0x100])
    with pytest.raises(ValueError, match="finite"):
        sensor.set_temperature(float("nan"))


def test_spi_page_program_is_atomic_on_capacity_failure():
    flash = VirtualSPIFlashW25Q128(total_size=257)
    flash.write_enable()
    with pytest.raises(ValueError, match="capacity"):
        flash.page_program(0x100, [0xAA, 0xBB])
    assert flash.memory[0x100] == 0xFF
    assert flash.wel_latched is True


def test_eeprom_rejects_boolean_or_float_address_width():
    eeprom = VirtualEEPROM24C64()
    for address_width in (True, 1.0, 2.0):
        with pytest.raises(ValueError, match="preferred_address_bytes"):
            eeprom.write([0x00, 0x01], preferred_address_bytes=address_width)


def test_eeprom_busy_cycle_requires_ack_polling_and_idle_poll_is_false():
    eeprom = VirtualEEPROM24C64()
    assert eeprom.ack_polling() is False
    eeprom.write([0x00, 0x00, 0xAA])
    with pytest.raises(RuntimeError, match="busy"):
        eeprom.read(0, 1)
    with pytest.raises(RuntimeError, match="busy"):
        eeprom.write([0x00, 0x01, 0xBB])
    assert eeprom.ack_polling() is True
    assert eeprom.read(0, 1) == b"\xaa"


def test_eeprom_rejects_unreasonably_large_allocations():
    with pytest.raises(ValueError, match="capacity"):
        VirtualEEPROM24C64(capacity=VirtualEEPROM24C64.MAX_CAPACITY + 1)
