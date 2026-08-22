from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64


def test_eeprom_basic_write_and_read():
    eeprom = VirtualEEPROM24C64(addr_7bit=0x50, page_size=32)
    result = eeprom.write([0x00, 0xAB, 0xCD])
    assert result["offset"] == 0x00
    data = eeprom.read(offset=0x00, length=2)
    assert data == bytes([0xAB, 0xCD])


def test_eeprom_page_boundary_rollover():
    """Verify that writing past page boundary wraps within same page."""
    eeprom = VirtualEEPROM24C64(page_size=8)
    # Start at offset 6 in page 0 (page boundary at offset 8)
    result = eeprom.write([0x06, 0xAA, 0xBB, 0xCC, 0xDD])
    assert result["rollover_hazard"] is True
    # Verify that offset 6 got 0xAA, offset 7 got 0xBB, but offset 0 got 0xCC (wrapped!)
    assert eeprom.memory[6] == 0xAA
    assert eeprom.memory[7] == 0xBB
    assert eeprom.memory[0] == 0xCC  # Wrapped to start of page!
    assert eeprom.memory[1] == 0xDD


def test_eeprom_ack_polling():
    eeprom = VirtualEEPROM24C64()
    eeprom.write([0x10, 0x55])
    assert eeprom.is_busy is True
    ready = eeprom.ack_polling()
    assert ready is True
    assert eeprom.is_busy is False
