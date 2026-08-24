from __future__ import annotations

import json

from fw_diag_tool.envelope import DiagnosticReportEnvelope
from fw_diag_tool.spi.raw_capture import parse_raw_spi_csv
from fw_diag_tool.uart.models import ARMHardFaultReport, CrashType, UARTReport
from fw_diag_tool.uart.symbols import SymbolTable


def test_symbol_table_parsing_and_lookup():
    map_content = (
        "08001000 T Reset_Handler\n"
        "08001200 T HardFault_Handler\n"
        "08002000 T main\n"
        "08002450 T sensor_read_loop\n"
    )
    table = SymbolTable.from_system_map(map_content)
    assert table.lookup(0x08002000) == ("main", 0)
    assert table.lookup(0x08002010) == ("main", 0x10)
    assert table.lookup(0x08002460) == ("sensor_read_loop", 0x10)
    assert table.lookup(0x08000500) is None


def test_symbolicate_arm_hardfault_and_panic():
    map_content = "08001234 T error_function\n08000450 T caller_function\n"
    table = SymbolTable.from_system_map(map_content)

    hf_report = UARTReport(
        crash_type=CrashType.ARM_HARDFAULT,
        summary_title="HardFault",
        arm_hardfault=ARMHardFaultReport(pc_faulting=0x08001238, lr_exc_return=0x08000456),
    )
    table.symbolicate(hf_report)
    assert hf_report.arm_hardfault is not None
    assert hf_report.arm_hardfault.symbolicated_pc == "error_function+0x4"
    assert hf_report.arm_hardfault.symbolicated_lr == "caller_function+0x6"


def test_diagnostic_report_envelope_serialization():
    envelope = DiagnosticReportEnvelope(
        protocol="i2c",
        status="success",
        input_sha256="abc12345",
        findings_count=1,
        anomalies=[{"code": "I2C_ADDR_NACK", "severity": "ERROR"}],
        payload={"total_transactions": 5},
    )
    text = envelope.to_json()
    data = json.loads(text)
    assert data["schema_version"] == "1.0"
    assert data["protocol"] == "i2c"
    assert data["findings_count"] == 1
    assert data["payload"]["total_transactions"] == 5


def test_raw_spi_transition_parsing_mode0():
    bits = [1, 0, 0, 1, 1, 1, 1, 1]
    rows = ["Time,SCLK,CS,MOSI,MISO\n"]
    rows.append("0.000000,0,1,1,1\n")
    rows.append("0.000001,0,0,1,1\n")
    for idx, b in enumerate(bits):
        rows.append(f"0.0000{idx*2+2:02d},0,0," + str(b) + ",1\n")
        rows.append(f"0.0000{idx*2+3:02d},1,0," + str(b) + ",1\n")
    rows.append("0.000020,0,0,0,1\n")
    rows.append("0.000021,0,1,0,1\n")
    csv_text = "".join(rows)
    res = parse_raw_spi_csv(csv_text, cpol=0, cpha=0)
    assert res.total_transitions > 0
    assert len(res.transactions) == 1
    tx = res.transactions[0]
    assert tx.opcode == 0x9F
    assert "Read JEDEC ID" in tx.opcode_name
    assert tx.mosi_bytes == [0x9F]
