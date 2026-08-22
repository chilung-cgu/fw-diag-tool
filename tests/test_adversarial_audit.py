from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.pmbus import decode_linear16, decode_pmbus_payload
from fw_diag_tool.pcie.diagnostics import diagnose_pcie_device
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine


def test_pcie_diagnostics_no_attribute_error():
    raw = bytearray(4096)
    raw[0:4] = bytes([0xEE, 0x10, 0x24, 0x70])
    raw[6] = 0x10
    raw[0x34] = 0x40
    raw[0x40] = 0x10
    raw[0x41] = 0x00
    raw[0x100:0x104] = bytes([0x01, 0x00, 0x01, 0x00])  # AER Ext Cap
    raw[0x104] = 0x10  # Uncorr Error: DLP Error (Bit 4)
    raw[0x110] = 0x01  # Corr Error (Offset 0x10 in AER): Receiver Error (Bit 0)
    cfg = PCIeAnalyzer.decode_config_space(bytes(raw), bdf="0000:01:00.0")
    findings = diagnose_pcie_device(cfg)
    assert len(findings) >= 2
    assert any(f["type"] == "AER_UNCORRECTABLE" for f in findings)
    assert any(f["type"] == "AER_CORRECTABLE" for f in findings)

def test_pcie_config_tlp_dw2_ext_register():
    # TLP CfgRd0: Fmt=0b000 (3DW no data), Type=0b00100 (CfgRd0)
    # DW0: Fmt/Type=0x04000001 (1 DW length)
    dw0 = 0x04000001
    # DW1: Requester ID=0x0010, Tag=0x01, FirstBE=0xF
    dw1 = 0x0010010F
    # DW2: Bus=0x01, Dev=0x00, Func=0x00, ExtReg=0x1, Reg=0x00 -> Address target 0x100 (AER)
    # Bus: bits[31:24]=0x01, Dev: bits[23:19]=0x00, Func: bits[18:16]=0x00, ExtReg: bits[11:8]=0x1, Reg: bits[7:2]=0x00
    dw2 = (0x01 << 24) | (0x01 << 8)
    tlp = PCIeAnalyzer.decode_tlp_header(dw0, dw1, dw2, 0)
    assert tlp.type_name == "CfgRd0 (Config Read Type 0)"
    # Expected address target has Bus 1 and Reg 0x100 without collision
    assert (tlp.address & 0xFFF) == 0x100

def test_pmbus_linear16_signed_trim():
    # Negative trim of -26 with exp = -9 (-0.0508 V)
    raw_word = 0xFFE6  # -26 in 16-bit 2s complement
    val_signed = decode_linear16(raw_word, vout_mode_exponent=-9, signed=True)
    assert -0.06 < val_signed < -0.04
    # Unsigned should give large value
    val_unsigned = decode_linear16(raw_word, vout_mode_exponent=-9, signed=False)
    assert val_unsigned > 100.0
    # decode_pmbus_payload for 0x22 (VOUT_TRIM)
    res = decode_pmbus_payload(0x22, [0xE6, 0xFF], vout_exponent=-9)
    assert res["value"] < 0.0

def test_pmbus_vout_mode_read_dynamic_update():
    # Master reads VOUT_MODE (0x20) -> returns 0x14 (exp = -12)
    # Then reads READ_VOUT (0x8B) -> returns 0x1000 (4096 -> 1.000 V)
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x58,Write,0x20,ACK
0.002,1,0x58,Read,0x14,ACK
0.003,2,0x58,Write,0x8B,ACK
0.004,3,0x58,Read,0x00 0x10,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    # Last transaction is READ_VOUT
    tx_vout = report.transactions[-1]
    assert tx_vout.command_name == "READ_VOUT"
    assert tx_vout.decoded_values.get("value") == 1.0

def test_spi_volatile_wren_and_chip_erase_alt():
    # 1. 0x50 (Volatile WREN) followed by 0x01 (Write Status Reg 1) -> No Anomaly
    # 2. 0x60 (Chip Erase Alt) without WREN -> SPI_WRITE_NO_WREN Anomaly
    csv_data = """Time [s],MOSI,MISO,Enable
0.001,0x50,0x00,0
0.002,0x00,0x00,1
0.003,0x01,0x00,0
0.004,0x00,0x00,0
0.005,0x00,0x00,1
0.010,0x60,0x00,0
0.011,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.anomaly_count == 1
    assert report.anomalies[0].code == "SPI_WRITE_NO_WREN"
    assert report.anomalies[0].transaction_id == 3