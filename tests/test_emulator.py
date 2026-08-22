from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64
from fw_diag_tool.emulator.lm75 import VirtualLM75
from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128


def test_eeprom_basic_write_and_read():
    eeprom = VirtualEEPROM24C64(addr_7bit=0x50, page_size=32)
    result = eeprom.write([0x00, 0xAB, 0xCD])
    assert result["offset"] == 0x00
    data = eeprom.read(offset=0x00, length=2)
    assert data == bytes([0xAB, 0xCD])


def test_eeprom_page_boundary_rollover():
    eeprom = VirtualEEPROM24C64(page_size=8)
    result = eeprom.write([0x06, 0xAA, 0xBB, 0xCC, 0xDD])
    assert result["rollover_hazard"] is True
    assert eeprom.memory[6] == 0xAA
    assert eeprom.memory[7] == 0xBB
    assert eeprom.memory[0] == 0xCC
    assert eeprom.memory[1] == 0xDD


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
    flash.write_enable()
    ok = flash.page_program(address=0x001000, data=[0xDE, 0xAD, 0xBE, 0xEF])
    assert ok is True
    read_back = flash.read_data(address=0x001000, length=4)
    assert read_back == [0xDE, 0xAD, 0xBE, 0xEF]


def test_spi_flash_write_without_wren_returns_false():
    flash = VirtualSPIFlashW25Q128()
    ok = flash.page_program(address=0x000000, data=[0x55])
    assert ok is False
