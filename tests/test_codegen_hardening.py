import pytest

from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator


def test_driver_register_read_uses_repeated_start_and_full_length():
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50,
        reg_offset=0x1234,
        is_read=True,
        read_length=4,
        register_width=16,
        bus_num=2,
    )

    linux = snippets["Linux Userspace (i2c-dev)"]
    assert "uint8_t reg_buf[2] = { 0x12, 0x34 };" in linux
    assert "struct i2c_msg msgs[2]" in linux
    assert "I2C_M_RD" in linux
    assert "I2C_RDWR" in linux

    cli = snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "i2ctransfer -y 2 w2@0x50 0x12 0x34 r4" in cli
    assert " -f " not in cli

    stm32 = snippets["STM32 HAL C Driver"]
    assert "HAL_I2C_Mem_Read" in stm32
    assert "I2C_MEMADD_SIZE_16BIT" in stm32
    assert "rx_buf, 4, 100" in stm32

    arduino = snippets["Arduino / Wire.h"]
    assert "Wire.write(0x12);" in arduino
    assert "Wire.write(0x34);" in arduino
    assert "Wire.endTransmission(false);" in arduino
    assert "Wire.requestFrom(0x50, 4)" in arduino
    assert "rx_buf[i] = Wire.read();" in arduino


def test_driver_16bit_register_write_preserves_every_data_byte():
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50,
        reg_offset=0x1234,
        data_bytes=[0xAB, 0xCD],
        register_width=16,
    )

    assert "{ 0x12, 0x34, 0xAB, 0xCD }" in snippets["Linux Userspace (i2c-dev)"]
    assert (
        "i2ctransfer -y 1 w4@0x50 0x12 0x34 0xAB 0xCD"
        in snippets["OpenBMC / Linux CLI (i2c-tools)"]
    )
    assert "I2C_MEMADD_SIZE_16BIT" in snippets["STM32 HAL C Driver"]
    assert "{ 0xAB, 0xCD }" in snippets["STM32 HAL C Driver"]
    assert snippets["Arduino / Wire.h"].count("Wire.write(") == 4


def test_driver_direct_read_and_write_without_register():
    read_snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x48, reg_offset=None, is_read=True, read_length=3
    )
    assert "read(file, rx_buf" in read_snippets["Linux Userspace (i2c-dev)"]
    assert "i2ctransfer -y 1 r3@0x48" in read_snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "HAL_I2C_Master_Receive" in read_snippets["STM32 HAL C Driver"]
    assert "Wire.requestFrom(0x48, 3)" in read_snippets["Arduino / Wire.h"]

    write_snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x48, reg_offset=None, data_bytes=[0x11, 0x22]
    )
    assert "{ 0x11, 0x22 }" in write_snippets["Linux Userspace (i2c-dev)"]
    assert "i2ctransfer -y 1 w2@0x48 0x11 0x22" in write_snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "HAL_I2C_Master_Transmit" in write_snippets["STM32 HAL C Driver"]
    assert write_snippets["Arduino / Wire.h"].count("Wire.write(") == 2


@pytest.mark.parametrize("address", [-1, 0x07, 0x78, 0x100])
def test_driver_rejects_invalid_or_reserved_address(address):
    with pytest.raises(ValueError, match="addr_7bit"):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=address, data_bytes=[0x00])


@pytest.mark.parametrize("data", [[-1], [0x100], []])
def test_driver_rejects_invalid_write_data(data):
    with pytest.raises(ValueError):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=0x50, data_bytes=data)


def test_driver_rejects_invalid_lengths_and_register_width():
    with pytest.raises(ValueError, match="read_length"):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=0x50, is_read=True, read_length=0)
    with pytest.raises(ValueError, match="register_width"):
        I2CDriverCodeGenerator.generate_all_snippets(
            addr_7bit=0x50, data_bytes=[0x00], register_width=24
        )
    with pytest.raises(ValueError, match="register_width"):
        I2CDriverCodeGenerator.generate_all_snippets(
            addr_7bit=0x50, data_bytes=[0x00], register_width=12
        )
    with pytest.raises(ValueError, match="reg_offset"):
        I2CDriverCodeGenerator.generate_all_snippets(
            addr_7bit=0x50, reg_offset=0x100, data_bytes=[0x00], register_width=8
        )


def test_driver_rejects_wrong_input_types_and_write_read_length():
    with pytest.raises(TypeError, match="addr_7bit"):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=True, data_bytes=[0x00])
    with pytest.raises(TypeError, match="data_bytes"):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=0x50, data_bytes=(0x00,))
    with pytest.raises(TypeError, match="is_read"):
        I2CDriverCodeGenerator.generate_all_snippets(addr_7bit=0x50, data_bytes=[0x00], is_read=1)
    with pytest.raises(ValueError, match="only valid for read"):
        I2CDriverCodeGenerator.generate_all_snippets(
            addr_7bit=0x50, data_bytes=[0x00], read_length=1
        )


def test_dts_without_devices_does_not_invent_peripherals():
    dts = DeviceTreeGenerator.generate_dts_from_topology(bus_num=1, mux_addr=0x70)
    assert "clock-frequency = <400000>;" in dts
    assert "bus-frequency" not in dts
    assert 'compatible = "nxp,pca9548";' in dts
    assert "atmel,24c64" not in dts
    assert "national,lm75" not in dts
    assert "pmbus-device" not in dts
    assert "generic,i2c-device" not in dts


def test_dts_requires_explicit_device_compatible():
    with pytest.raises(ValueError, match="explicit 'vendor,device'"):
        DeviceTreeGenerator.generate_dts_from_topology(
            devices=[{"addr": 0x50, "channel": 0, "name": "eeprom", "type": "EEPROM"}]
        )


def test_dts_rejects_invalid_devices_container_and_mapping():
    with pytest.raises(TypeError, match="devices must be a list"):
        DeviceTreeGenerator.generate_dts_from_topology(devices={})
    with pytest.raises(TypeError, match=r"devices\[0\]"):
        DeviceTreeGenerator.generate_dts_from_topology(devices=["not-a-mapping"])
    with pytest.raises(ValueError, match="missing addr"):
        DeviceTreeGenerator.generate_dts_from_topology(devices=[{}])


def test_dts_accepts_explicit_devices_and_string_numbers():
    dts = DeviceTreeGenerator.generate_dts_from_topology(
        bus_num="2",
        mux_addr="0x70",
        clock_frequency="0x61A80",
        devices=[
            {
                "addr": "0x50",
                "channel": "0x2",
                "name": "boot-eeprom",
                "compatible": "atmel,24c64",
            }
        ],
    )
    assert "&i2c2 {" in dts
    assert "clock-frequency = <400000>;" in dts
    assert "i2c@2 {" in dts
    assert "boot-eeprom@50 {" in dts
    assert 'compatible = "atmel,24c64";' in dts


@pytest.mark.parametrize(
    ("device", "match"),
    [
        (
            {"addr": 0x50, "channel": 8, "name": "dev", "compatible": "vendor,dev"},
            "channel",
        ),
        (
            {"addr": 0x07, "channel": 0, "name": "dev", "compatible": "vendor,dev"},
            "address",
        ),
        (
            {"addr": 0x50, "channel": 0, "name": "bad name", "compatible": "vendor,dev"},
            "device name",
        ),
        (
            {"addr": 0x50, "channel": 0, "name": "dev", "compatible": "generic"},
            "compatible",
        ),
    ],
)
def test_dts_rejects_invalid_device_fields(device, match):
    with pytest.raises(ValueError, match=match):
        DeviceTreeGenerator.generate_dts_from_topology(devices=[device])


def test_c_header_emits_explicit_zero_reset_and_omits_ro_setter():
    generator = CHeaderGenerator.from_yaml_str(
        """
registers:
  - name: STATUS
    offset: 0x00
    size: 8
    reset: 0
    fields:
      - name: READY
        bits: 0
        access: RO
      - name: ENABLE
        bits: 1
        access: RW
"""
    )
    header = generator.generate_header("TEST")
    assert "#ifndef TEST_H" in header
    assert "#ifndef _TEST_H" not in header
    assert "REG_STATUS_RESET               (0x00000000U)" in header
    assert "REG_STATUS_READY_GET(val)" in header
    assert "REG_STATUS_READY_SET(reg, val)" not in header
    assert "REG_STATUS_ENABLE_SET(reg, val)" in header


def test_c_header_does_not_invent_unspecified_reset():
    generator = CHeaderGenerator.from_yaml_str(
        """
registers:
  - name: STATUS
    offset: 0
    size: 8
    fields: []
"""
    )
    assert "REG_STATUS_RESET" not in generator.generate_header("TEST")


@pytest.mark.parametrize(
    ("yaml_text", "match"),
    [
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 24
    fields: []
""",
            "size must be",
        ),
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 8
    fields:
      - name: TOO_HIGH
        bits: 8
""",
            "exceed",
        ),
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 8
    fields:
      - name: FIRST
        bits: "3:0"
      - name: SECOND
        bits: "2:1"
""",
            "overlaps",
        ),
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 8
    fields:
      - name: MODE
        bits: "1:0"
        values:
          4: INVALID
""",
            "enum value",
        ),
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 8
    reset: 0x100
    fields: []
""",
            "reset value",
        ),
        (
            """
registers:
  - name: BAD
    offset: 0
    size: 8
    fields:
      - name: MODE
        bits: "1:0"
        values:
          0: "same-label"
          1: "same label"
""",
            "duplicate generated enum labels",
        ),
    ],
)
def test_c_header_rejects_invalid_register_schema(yaml_text, match):
    generator = CHeaderGenerator.from_yaml_str(yaml_text)
    with pytest.raises(ValueError, match=match):
        generator.generate_header("TEST")


def test_c_header_rejects_malformed_bit_range():
    generator = CHeaderGenerator.from_yaml_str(
        """
registers:
  - name: BAD
    offset: 0
    size: 8
    fields:
      - name: FIELD
        bits: "7:4:1"
"""
    )
    with pytest.raises(ValueError, match="invalid bit range"):
        generator.generate_header("TEST")
