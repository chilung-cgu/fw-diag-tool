from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator


def test_device_tree_generator():
    dts = DeviceTreeGenerator.generate_dts_from_topology(bus_num=2, mux_addr=0x70)
    assert "&i2c2 {" in dts
    assert "i2c-mux@70 {" in dts
    assert "compatible = \"nxp,pca9548\";" in dts
    assert "i2c@0 {" in dts
    assert "compatible = \"atmel,24c64\";" in dts
    assert "compatible = \"national,lm75\";" in dts