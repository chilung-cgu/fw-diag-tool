import pytest

from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64
from fw_diag_tool.emulator.i2c_mux import VirtualPCA9548A
from fw_diag_tool.emulator.ina219 import VirtualINA219
from fw_diag_tool.emulator.lm75 import VirtualLM75


def test_ina219_defaults_and_address_probe():
    ina = VirtualINA219(addr_7bit=0x40)
    assert ina.addr == 0x40
    assert ina.read_register(0x00) == 0x399F
    assert ina.read_register(0x05) == 0x0000
    probe_res = ina.write([])
    assert probe_res["type"] == "Address Probe"


def test_ina219_calibration_and_current_power_math():
    ina = VirtualINA219(addr_7bit=0x40, shunt_ohms=0.1, max_expected_amps=3.2)
    # With R_shunt = 0.1 ohm, current_lsb_ma = 0.1 mA -> Cal = 4096 (0x1000)
    ina.set_current_lsb(0.1)
    cal_val = ina.calculate_expected_calibration(current_lsb_ma=0.1, shunt_ohms=0.1)
    assert cal_val == 4096

    # Uncalibrated: current and power should be 0
    ina.set_shunt_voltage(25000.0)  # 25 mV = 250 mA across 0.1 ohm
    ina.set_bus_voltage(12.0)  # 12 V
    assert ina.calculate_current() == 0.0
    assert ina.calculate_power() == 0.0
    assert ina.read_register(0x04) == 0
    assert ina.read_register(0x03) == 0

    # Apply calibration
    ina.write_calibration(cal_val)
    assert ina.read_register(0x05) == 4096

    # 25 mV / 10 uV = 2500 raw shunt. Raw current = (2500 * 4096) / 4096 = 2500.
    # Current = 2500 * 0.1 mA = 250.0 mA
    assert pytest.approx(ina.calculate_current(), rel=1e-3) == 250.0
    raw_cur = ina.read_register(0x04)
    assert raw_cur == 2500

    # Bus voltage: 12V = 12000 mV / 4 mV = 3000 raw. Shift left 3 + CNVR(2) = (3000 << 3) | 2 = 24002
    assert ina.read_register(0x02) == (3000 << 3) | 2

    # Raw power = (2500 * 3000) // 5000 = 1500.
    # Power = 1500 * (20 * 0.1) mW = 1500 * 2 mW = 3000 mW = 3.0 W
    assert pytest.approx(ina.calculate_power(), rel=1e-3) == 3000.0
    assert ina.read_register(0x03) == 1500


def test_ina219_negative_shunt_voltage():
    ina = VirtualINA219()
    ina.set_current_lsb(0.1)
    ina.write_calibration(4096)
    ina.set_shunt_voltage(-10000.0)  # -10 mV -> -100 mA
    ina.set_bus_voltage(5.0)
    assert pytest.approx(ina.calculate_current(), rel=1e-3) == -100.0
    # Raw shunt = -1000. 16-bit signed as unsigned = (-1000) & 0xFFFF = 0xFC18
    assert ina.read_register(0x01) == (-1000) & 0xFFFF


def test_ina219_i2c_write_and_read_protocol():
    ina = VirtualINA219()
    # Set pointer to CONFIG (0x00)
    ina.write([0x00])
    data = ina.read(2)
    assert len(data) == 2
    assert data == bytes([0x39, 0x9F])

    # Write Calibration register via I2C write (0x05, 0x10, 0x00 -> 0x1000 = 4096)
    res = ina.write([0x05, 0x10, 0x00])
    assert res["type"] == "Write Register"
    assert ina.cal_reg == 0x1000

    # Read Calibration register
    ina.write([0x05])
    cal_bytes = ina.read(2)
    assert cal_bytes == bytes([0x10, 0x00])

    # Soft Reset via CONFIG register MSB bit (0x8000)
    res_reset = ina.write([0x00, 0x80, 0x00])
    assert res_reset["type"] == "Reset"
    assert ina.cal_reg == 0x0000
    assert ina.config_reg == 0x399F


def test_ina219_validation_and_boundaries():
    ina = VirtualINA219()
    with pytest.raises(ValueError, match="addr_7bit"):
        VirtualINA219(addr_7bit=0x80)
    with pytest.raises(ValueError, match="addr_7bit"):
        VirtualINA219(addr_7bit=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="shunt_ohms"):
        VirtualINA219(shunt_ohms=-0.1)
    with pytest.raises(ValueError, match="max_expected_amps"):
        VirtualINA219(max_expected_amps=0)
    with pytest.raises(ValueError, match="bus voltage"):
        ina.set_bus_voltage(35.0)
    with pytest.raises(ValueError, match="shunt voltage"):
        ina.set_shunt_voltage(400000.0)
    with pytest.raises(ValueError, match="calibration register"):
        ina.write_calibration(-1)
    with pytest.raises(ValueError, match="calibration register"):
        ina.write_calibration(0x10000)
    with pytest.raises(ValueError, match="unsupported INA219 register"):
        ina.read_register(6)
    with pytest.raises(ValueError, match="unsupported INA219 register"):
        ina.write([0x08])
    with pytest.raises(ValueError, match="num_bytes"):
        ina.read(-1)
    with pytest.raises(ValueError, match="register provides"):
        ina.read(3)
    with pytest.raises(TypeError, match="data_bytes"):
        ina.write("invalid")  # type: ignore[arg-type]


def test_pca9548a_channel_selection_and_control():
    mux = VirtualPCA9548A(addr_7bit=0x70)
    assert mux.addr == 0x70
    assert mux.read_control() == 0x00
    assert mux.get_active_channels() == []

    # Select single channel
    mux.select_channel(3)
    assert mux.read_control() == 0x08
    assert mux.get_active_channels() == [3]

    # Select multiple channels
    mux.select_channels([0, 2, 5])
    assert mux.read_control() == (1 | 4 | 32)  # 0x25 = 37
    assert mux.get_active_channels() == [0, 2, 5]

    # Deselect all
    mux.deselect_all()
    assert mux.read_control() == 0x00
    assert mux.get_active_channels() == []

    # Write control directly
    mux.write_control(0xFF)
    assert mux.read_control() == 0xFF
    assert mux.get_active_channels() == list(range(8))

    # Hardware reset simulation
    mux.reset()
    assert mux.read_control() == 0x00
    assert mux.get_active_channels() == []


def test_pca9548a_i2c_write_and_read():
    mux = VirtualPCA9548A()
    # Probe
    probe_res = mux.write([])
    assert probe_res["type"] == "Address Probe"

    # Write control byte via I2C write
    res = mux.write([0x05])  # CH0 and CH2
    assert res["control"] == 0x05
    assert mux.get_active_channels() == [0, 2]

    # Read control byte via I2C read
    data = mux.read(1)
    assert data == bytes([0x05])


def test_pca9548a_device_attachment_and_conflict_detection():
    mux = VirtualPCA9548A()
    lm1 = VirtualLM75(addr_7bit=0x48)
    lm2 = VirtualLM75(addr_7bit=0x48)
    eeprom = VirtualEEPROM24C64(addr_7bit=0x50)

    mux.attach_device(0, lm1)
    mux.attach_device(1, lm2)
    mux.attach_device(2, eeprom)

    assert mux.get_devices_on_channel(0) == [lm1]
    assert mux.get_devices_on_channel(1) == [lm2]
    assert mux.get_devices_on_channel(2) == [eeprom]

    # When only CH0 and CH2 are active -> no conflicts
    mux.select_channels([0, 2])
    conflicts = mux.detect_address_conflicts()
    assert len(conflicts) == 0

    # When CH0 and CH1 are both active -> conflict on address 0x48!
    mux.select_channels([0, 1])
    conflicts = mux.detect_address_conflicts()
    assert 0x48 in conflicts
    assert len(conflicts[0x48]) == 2
    assert conflicts[0x48][0] == (0, lm1)
    assert conflicts[0x48][1] == (1, lm2)

    # Detach device
    mux.detach_device(1, lm2)
    assert mux.get_devices_on_channel(1) == []
    assert len(mux.detect_address_conflicts()) == 0


def test_pca9548a_routing():
    mux = VirtualPCA9548A()
    lm = VirtualLM75(addr_7bit=0x48)
    lm.set_temperature(30.0)
    mux.attach_device(0, lm)

    # When channel 0 is not active, route_write and route_read find no devices
    mux.deselect_all()
    assert mux.route_write(0x48, [0x00]) == []
    assert mux.route_read(0x48, 2) == []

    # Activate channel 0
    mux.select_channel(0)
    w_res = mux.route_write(0x48, [0x00])
    assert len(w_res) == 1
    assert w_res[0]["channel"] == 0
    assert w_res[0]["device"] == lm

    r_res = mux.route_read(0x48, 2)
    assert len(r_res) == 1
    ch, dev, raw_bytes = r_res[0]
    assert ch == 0
    assert dev == lm
    # 30.0 / 0.0625 = 480 = 0x01E0 -> 0x1E00 -> bytes [0x1E, 0x00]
    assert raw_bytes == bytes([0x1E, 0x00])


def test_pca9548a_validation():
    mux = VirtualPCA9548A()
    with pytest.raises(ValueError, match="addr_7bit"):
        VirtualPCA9548A(addr_7bit=0x80)
    with pytest.raises(ValueError, match="addr_7bit"):
        VirtualPCA9548A(addr_7bit=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="channel"):
        mux.select_channel(8)
    with pytest.raises(ValueError, match="channel"):
        mux.select_channel(-1)
    with pytest.raises(TypeError, match="channels"):
        mux.select_channels("invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="channels"):
        mux.select_channels([8])
    with pytest.raises(ValueError, match="control register"):
        mux.write_control(256)
    with pytest.raises(ValueError, match="device cannot be None"):
        mux.attach_device(0, None)
    with pytest.raises(ValueError, match="addr"):
        mux.attach_device(0, object())
    with pytest.raises(ValueError, match="num_bytes"):
        mux.read(-1)
    with pytest.raises(ValueError, match="control register provides"):
        mux.read(2)
    with pytest.raises(TypeError, match="data_bytes"):
        mux.write("invalid")  # type: ignore[arg-type]
