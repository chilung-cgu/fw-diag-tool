from fw_diag_tool.i2c.engine import I2CDiagnosticEngine


def test_i2c_mux_topology_tracking():
    # 1. Write to Mux 0x70 data=0x04 (Enable Channel 2)
    # 2. Read from EEPROM 0x50
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x70,Write,0x04,ACK
0.002,1,0x50,Write,0x00,ACK
0.003,1,0x50,Read,0x12 0x34,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert len(report.transactions) >= 2
    tx_mux = report.transactions[0]
    assert "MUX 0x70" in tx_mux.semantic_summary
    # Subsequent transaction to 0x50 should have topology path
    tx_eeprom = report.transactions[1]
    assert tx_eeprom.mux_topology is not None
    assert "MUX 0x70: Ch2" in tx_eeprom.mux_topology
    assert tx_eeprom.mux_channels == [2]

def test_i2c_mux_multi_channel_hazard():
    # Write to Mux 0x70 with 0x05 (Ch0 and Ch2 enabled simultaneously)
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x70,Write,0x05,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert any(a.code == "I2C_MUX_MULTI_CHANNEL" for a in report.anomalies)