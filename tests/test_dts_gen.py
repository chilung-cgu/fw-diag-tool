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


def test_generate_i2c_bus_without_mux_renders_direct_children_only() -> None:
    dts = DeviceTreeGenerator.generate_i2c_bus(
        bus_num=1,
        direct_devices=[{"addr": 0x48, "name": "temp", "compatible": "ti,tmp75"}],
        muxes=[],
    )
    assert "temp@48" in dts
    assert "i2c-mux@" not in dts


def test_generate_i2c_bus_renders_direct_devices_and_all_muxes() -> None:
    dts = DeviceTreeGenerator.generate_i2c_bus(
        bus_num=3,
        direct_devices=[{"addr": 0x48, "name": "local-temp", "compatible": "ti,tmp75"}],
        muxes=[
            {"addr": 0x70, "compatible": "nxp,pca9548", "channels": [
                {"channel": 0, "devices": [{"addr": 0x50, "name": "fru-a", "compatible": "atmel,24c64"}]}
            ]},
            {"addr": 0x71, "compatible": "nxp,pca9548", "channels": [
                {"channel": 1, "devices": [{"addr": 0x50, "name": "fru-b", "compatible": "atmel,24c64"}]}
            ]},
        ],
    )
    assert "local-temp@48" in dts
    assert dts.count("i2c-mux@") == 2
    assert "i2c-mux@70" in dts
    assert "i2c-mux@71" in dts
    assert "fru-a@50" in dts
    assert "fru-b@50" in dts
