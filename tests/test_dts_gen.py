from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator


def test_device_tree_generator():
    devices = [
        {
            "addr": 0x50,
            "channel": 0,
            "name": "eeprom",
            "compatible": "atmel,24c64",
        },
        {
            "addr": 0x48,
            "channel": 1,
            "name": "temp-sensor",
            "compatible": "national,lm75",
        },
    ]
    dts = DeviceTreeGenerator.generate_dts_from_topology(bus_num=2, mux_addr=0x70, devices=devices)
    assert "&i2c2 {" in dts
    assert "clock-frequency = <400000>;" in dts
    assert "bus-frequency" not in dts
    assert "i2c-mux@70 {" in dts
    assert 'compatible = "nxp,pca9548";' in dts
    assert "i2c@0 {" in dts
    assert 'compatible = "atmel,24c64";' in dts
    assert 'compatible = "national,lm75";' in dts
