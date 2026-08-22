
import pytest

from fw_diag_tool.analyzers.register_mapper import BitField
from fw_diag_tool.i2c.eeprom import decode_eeprom_write
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.pmbus import decode_linear16, decode_pmbus_payload, encode_linear11
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
    dw0 = 0x04000001
    dw1 = 0x0010010F
    dw2 = (0x01 << 24) | (0x01 << 8)
    tlp = PCIeAnalyzer.decode_tlp_header(dw0, dw1, dw2, 0)
    assert tlp.type_name == "CfgRd0 (Config Read Type 0)"
    assert (tlp.address & 0xFFF) == 0x100

def test_pmbus_linear16_signed_trim():
    raw_word = 0xFFE6  # -26 in 16-bit 2s complement
    val_signed = decode_linear16(raw_word, vout_mode_exponent=-9, signed=True)
    assert -0.06 < val_signed < -0.04
    val_unsigned = decode_linear16(raw_word, vout_mode_exponent=-9, signed=False)
    assert val_unsigned > 100.0
    res = decode_pmbus_payload(0x22, [0xE6, 0xFF], vout_exponent=-9)
    assert res["value"] < 0.0

def test_pmbus_vout_mode_read_dynamic_update():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x58,Write,0x20,ACK
0.002,1,0x58,Read,0x14,ACK
0.003,2,0x58,Write,0x8B,ACK
0.004,3,0x58,Read,0x00 0x10,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    tx_vout = report.transactions[-1]
    assert tx_vout.command_name == "READ_VOUT"
    assert tx_vout.decoded_values.get("value") == 1.0

def test_spi_volatile_wren_and_chip_erase_alt():
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

def test_spi_jedec_line_fault():
    # MISO all 0xFF -> floating line
    csv_data = """Time [s],MOSI,MISO,Enable
0.001,0x9F,0x00,0
0.002,0x00,0xFF,0
0.003,0x00,0xFF,0
0.004,0x00,0xFF,0
0.005,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert any(a.code == "SPI_JEDEC_LINE_FAULT" for a in report.anomalies)

def test_eeprom_zero_page_size_guard():
    res = decode_eeprom_write([0x00, 0x12, 0x34], page_size=0)
    assert res["page_size"] == 0 or res["offset"] == 0

def test_linear11_nan_inf_guard():
    with pytest.raises(ValueError):
        encode_linear11(float("nan"))
    with pytest.raises(ValueError):
        encode_linear11(float("inf"))
    assert encode_linear11(0.0) == 0x0000

def test_bitfield_bracket_and_reverse_range():
    bf1 = BitField(name="TEST1", bit_range="[15:0]")
    assert bf1.high_bit == 15 and bf1.low_bit == 0
    bf2 = BitField(name="TEST2", bit_range="0:7")
    assert bf2.high_bit == 7 and bf2.low_bit == 0
    assert bf2.bit_mask == 0xFF