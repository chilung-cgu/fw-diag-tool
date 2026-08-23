from fw_diag_tool.codegen.c_header import CHeaderGenerator


def test_c_header_generation():
    sample_yaml = """
registers:
  - name: "DEVICE_CTRL"
    offset: 0x08
    size: 32
    reset: 0x00000001
    description: "Main Device Control Register"
    fields:
      - name: "ENABLE"
        bits: "0"
        access: "RW"
        values:
          0: "DISABLED"
          1: "ENABLED"
      - name: "SPEED_MODE"
        bits: "5:4"
        access: "RW"
        values:
          0: "LOW_SPEED"
          1: "FULL_SPEED"
          2: "HIGH_SPEED"
"""
    gen = CHeaderGenerator.from_yaml_str(sample_yaml)
    h_code = gen.generate_header(module_name="TEST_CHIP")
    assert "#ifndef TEST_CHIP_H" in h_code
    assert "#ifndef _TEST_CHIP_H_" not in h_code
    assert "#define REG_DEVICE_CTRL_OFFSET              (0x0008U)" in h_code
    assert "#define REG_DEVICE_CTRL_ENABLE_POS        (0U)" in h_code
    assert "#define REG_DEVICE_CTRL_ENABLE_MSK        (0x00000001U)" in h_code
    assert "#define REG_DEVICE_CTRL_SPEED_MODE_POS        (4U)" in h_code
    assert "#define REG_DEVICE_CTRL_SPEED_MODE_MSK        (0x00000030U)" in h_code
    assert "#define VAL_DEVICE_CTRL_SPEED_MODE_HIGH_SPEED (2U)" in h_code
    assert "REG_DEVICE_CTRL_ENABLE_GET(val)" in h_code
    assert "REG_DEVICE_CTRL_ENABLE_SET(reg, val)" in h_code
