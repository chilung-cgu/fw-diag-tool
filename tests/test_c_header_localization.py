from fw_diag_tool.codegen.c_header import CHeaderGenerator


def test_generated_c_header_uses_zh_tw_first_comments() -> None:
    generator = CHeaderGenerator.from_yaml_str(
        """
registers:
  - name: STATUS
    offset: 0x04
    size: 8
    description: "Status Register"
    fields:
      - name: ERROR
        bits: 0
        access: W1C
        values:
          0: "Normal"
          1: "Error Active"
"""
    )

    header = generator.generate_header("TEST")

    assert "暫存器位元欄位（Bitfield）定義" in header
    assert "暫存器位移（Register Offset）與遮罩（Mask）" in header
    assert "說明（Description）：Status Register" in header
    assert "列舉值（Enum values）" in header
    assert "W1C：寫入 1 清除；不可使用讀取-修改-寫入（read-modify-write" in header
    assert "REGISTER OFFSETS & MASKS" not in header
    assert "/* Values for" not in header
    assert "/* write a 1 to clear" not in header
    assert "/* Status Register */" not in header
