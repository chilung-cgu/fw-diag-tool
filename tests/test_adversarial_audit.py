import pytest

from fw_diag_tool.analyzers.register_mapper import BitField, RegisterMapCatalog
from fw_diag_tool.i2c.anomaly import I2CAnomalyDetector
from fw_diag_tool.i2c.eeprom import decode_eeprom_read, decode_eeprom_write
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import RawEventType, RawI2CEvent
from fw_diag_tool.i2c.parser import I2CParser, parse_hex_or_int
from fw_diag_tool.i2c.pmbus import (
    decode_linear11,
    decode_linear16,
    decode_pmbus_payload,
    decode_status_byte,
    encode_linear11,
    parse_vout_mode_exponent,
)
from fw_diag_tool.i2c.sensor_decoders import (
    decode_ina2xx_power,
    decode_lm75_temperature,
    decode_pca9555_gpio,
)
from fw_diag_tool.i2c.timing import analyze_timing_statistics
from fw_diag_tool.pcie.diagnostics import diagnose_pcie_device
from fw_diag_tool.pcie.models import AERAnalysisResult, PCIeConfigSpace, TLPHeaderDecoded
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
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


def test_pcie_truncated_aer_is_reported_as_data_quality_not_struct_error():
    raw = bytearray(4096)
    raw[0x04:0x06] = (0x10).to_bytes(2, "little")
    raw[0x100:0x104] = (0x0001 | (0xFFC << 20)).to_bytes(4, "little")
    raw[0xFFC:0x1000] = (0x0001).to_bytes(4, "little")

    cfg = PCIeAnalyzer.decode_config_space(bytes(raw))

    assert any("truncated" in issue for issue in cfg.data_quality_issues)
    assert "Data Quality Limitations" in PCIeReporter.to_markdown(cfg)


def test_pcie_reporter_handles_incomplete_tlp_model():
    tlp = TLPHeaderDecoded(
        fmt=0,
        type_=0,
        length=1,
        is_3dw=True,
        is_4dw=False,
        has_data=False,
        tc=0,
        td=False,
        ep=False,
        attr=0,
        type_name="MRd",
        requester_id=0x0100,
        tag=None,
        raw_dw=[],
    )
    aer = AERAnalysisResult(
        offset=0x100,
        uncorr_status_raw=0,
        uncorr_mask_raw=0,
        uncorr_severity_raw=0,
        corr_status_raw=0,
        corr_mask_raw=0,
        cap_control_raw=0,
        header_log_raw=[],
        decoded_tlp=tlp,
    )
    markdown = PCIeReporter.to_markdown(PCIeConfigSpace(raw_data=b"", aer_analysis=aer))
    assert "n/a n/a n/a n/a" in markdown
    assert "Tag**: `n/a`" in markdown


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
    assert report.summary.erase_count == 1
    assert report.anomalies[0].code == "SPI_WEL_NOT_LATCHED"
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


def test_eeprom_decoder_rejects_invalid_geometry_and_bytes():
    with pytest.raises(ValueError, match="page_size"):
        decode_eeprom_write([0x00, 0x12, 0x34], page_size=0)
    with pytest.raises(ValueError, match="data_bytes"):
        decode_eeprom_write([-1, 0x12])
    with pytest.raises(ValueError, match="data_bytes"):
        decode_eeprom_write([0x100])
    with pytest.raises(ValueError, match="preferred_address_bytes"):
        decode_eeprom_write([0x00], preferred_address_bytes=3)
    with pytest.raises(ValueError, match="data_bytes"):
        decode_eeprom_read([0x100])


def test_eeprom_two_byte_profile_does_not_downgrade_one_byte_offset():
    result = decode_eeprom_write([0x10], preferred_address_bytes=2)
    assert result["evidence"] == "truncated"
    assert result["address_bytes"] == 2
    assert result["offset"] is None
    assert result["payload"] == []


def test_eeprom_profile_capacity_rejects_out_of_range_offset():
    result = decode_eeprom_write(
        [0xFF, 0xFF, 0xAA],
        preferred_address_bytes=2,
        page_size=32,
        capacity_bytes=8 * 1024,
    )
    assert result["evidence"] == "address-out-of-range"
    assert result["offset"] == 0xFFFF
    assert result["capacity_bytes"] == 8 * 1024


def test_engine_surfaces_eeprom_profile_capacity_limit():
    report = I2CDiagnosticEngine(eeprom_profile="24C64").analyze_csv_content(
        "Time,Packet ID,Address,Read/Write,Data,ACK/NACK\n"
        "0.001,0,0x50,Write,0xFF 0xFF 0xAA,ACK\n"
        "0.002,1,0x50,Read,0x12,ACK\n"
    )
    tx = report.transactions[0]
    assert tx.decoded_values["evidence"] == "address-out-of-range"
    assert "0xFFFF" not in report.transactions[1].semantic_summary
    assert any(
        issue.code == "I2C_EEPROM_ADDRESS_OUT_OF_RANGE" for issue in report.data_quality_issues
    )


def test_engine_surfaces_eeprom_truncated_address_as_data_quality():
    report = I2CDiagnosticEngine(eeprom_profile="24C64").analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n0.002,,Write,0x10,ACK\n"
    )
    assert any(issue.code == "I2C_EEPROM_ADDRESS_TRUNCATED" for issue in report.data_quality_issues)


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


def test_register_catalog_rejects_empty_sources_and_invalid_direct_offsets():
    catalog = RegisterMapCatalog()
    for source in ("", "{}", "registers: []", "null"):
        with pytest.raises(ValueError, match="at least one register"):
            catalog.load_from_yaml(source)
    with pytest.raises(TypeError, match="must be text"):
        catalog.load_from_yaml(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between 0 and 0xFFFFFFFF"):
        catalog.decode_register(-1, 0)
    with pytest.raises(ValueError, match="between 0 and 0xFFFFFFFF"):
        catalog.decode_register(0x1_0000_0000, 0)
    with pytest.raises(TypeError, match="integer offset or string name"):
        catalog.decode_register(1.0, 0)  # type: ignore[arg-type]


def test_i2c_raw_record_boundaries_are_rejected_not_reinterpreted():
    assert parse_hex_or_int("#50") == 0x50
    with pytest.raises(TypeError, match="mapping"):
        I2CParser.parse_raw_records([None])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="unknown event_type"):
        I2CParser.parse_raw_records([{"type": "GARBAGE"}])
    with pytest.raises(ValueError, match="address"):
        I2CParser.parse_raw_records([{"type": "ADDRESS", "address": -1}])
    with pytest.raises(ValueError, match="data byte"):
        I2CParser.parse_raw_records([{"type": "DATA", "data": 256}])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"smbus_timeout_ms": None},
        {"smbus_timeout_ms": "25"},
        {"smbus_timeout_ms": 0},
        {"smbus_timeout_ms": float("nan")},
        {"high_jitter_threshold_pct": 0},
        {"default_eeprom_page_size": 0},
        {"default_vout_exponent": 1024},
    ],
)
def test_i2c_engine_rejects_invalid_configuration(kwargs):
    with pytest.raises((TypeError, ValueError)):
        I2CDiagnosticEngine(**kwargs)


def test_i2c_anomaly_detector_rejects_invalid_configuration():
    with pytest.raises((TypeError, ValueError)):
        I2CAnomalyDetector(smbus_timeout_ms="25")
    with pytest.raises((TypeError, ValueError)):
        I2CAnomalyDetector(high_jitter_threshold_pct=float("nan"))


def test_ambiguous_eeprom_requires_explicit_profile_before_offset_decode():
    csv_data = """Time,Address,Read/Write,Data,ACK/NACK
0.001,0x50,Write,0x01 0x23 0xAA,ACK
"""
    ambiguous = I2CDiagnosticEngine().analyze_csv_content(csv_data)
    tx = ambiguous.transactions[0]
    assert tx.decoded_values["evidence"] == "ambiguous-address-profile"
    assert tx.decoded_values["address_bytes"] is None
    assert any(
        issue.code == "I2C_EEPROM_PROFILE_UNAVAILABLE" for issue in ambiguous.data_quality_issues
    )

    identified = I2CDiagnosticEngine(eeprom_profile="24C64").analyze_csv_content(csv_data)
    decoded = identified.transactions[0].decoded_values
    assert decoded["address_bytes"] == 2
    assert decoded["offset"] == 0x0123
    assert decoded["payload"] == ["0xAA"]


def test_pmbus_linear_formats_reject_unrepresentable_values_and_exponents():
    with pytest.raises(ValueError, match="representable"):
        encode_linear11(1e300)
    with pytest.raises(ValueError, match="representable"):
        encode_linear11(1e-300)
    with pytest.raises(ValueError, match="-16..15"):
        decode_linear16(1, 1024)


def test_pmbus_decoders_reject_out_of_range_raw_values():
    with pytest.raises(ValueError, match="0..0xFFFF"):
        decode_linear11(-1)
    with pytest.raises(ValueError, match="0..0xFFFF"):
        decode_linear11(0x1_0000)
    with pytest.raises(ValueError, match="0..0xFFFF"):
        decode_linear16(-1)
    with pytest.raises(ValueError, match="0..0xFF"):
        decode_status_byte(0x100)
    with pytest.raises(ValueError, match="0..0xFF"):
        parse_vout_mode_exponent(True)
    with pytest.raises(ValueError, match="0..0xFF"):
        decode_pmbus_payload(0x78, [0x100])


@pytest.mark.parametrize("cmd_code", [0x79, 0x8D])
def test_pmbus_known_word_commands_mark_short_payload_as_truncated(cmd_code):
    result = decode_pmbus_payload(cmd_code, [0x01])
    assert result["evidence"] == "truncated"
    assert result["is_complete"] is False
    assert result["required_bytes"] == 2
    assert result["received_bytes"] == 1
    assert "insufficient data" in result["summary"]


def test_pmbus_empty_known_status_is_not_reported_as_clean_or_quick_command():
    result = decode_pmbus_payload(0x78, [])
    assert result["evidence"] == "truncated"
    assert result["is_complete"] is False
    assert result["required_bytes"] == 1
    assert result["received_bytes"] == 0


def test_pmbus_write_command_selection_is_not_called_a_truncated_response():
    result = decode_pmbus_payload(0x8D, [], phase="write")
    assert result["evidence"] == "command-select"
    assert result["is_complete"] is True
    assert "response bytes are not present" in result["summary"]


def test_pmbus_block_read_count_mismatch_is_explicit():
    result = decode_pmbus_payload(0x99, [3, 0x41, 0x42])
    assert result["evidence"] == "block-count-mismatch"
    assert result["is_complete"] is False
    assert result["declared_count"] == 3
    assert result["received_count"] == 2


@pytest.mark.parametrize(
    ("cmd_code", "payload", "phase", "evidence"),
    [
        (0x88, [0x01, 0x02, 0x03], "read", "overlong"),
        (0x88, [0x01], "write", "phase-mismatch"),
        (0x03, [0x01], "write", "phase-mismatch"),
        (0x99, [0x01, 0x41], "write", "phase-mismatch"),
    ],
)
def test_pmbus_rejects_overlong_or_phase_invalid_payloads(cmd_code, payload, phase, evidence):
    result = decode_pmbus_payload(cmd_code, payload, phase=phase)
    assert result["evidence"] == evidence
    assert result["is_complete"] is False


def test_engine_surfaces_pmbus_overlong_payload_as_data_quality():
    report = I2CDiagnosticEngine().analyze_records(
        [
            {"timestamp": 0.0, "event_type": "START"},
            {
                "timestamp": 0.00001,
                "event_type": "ADDRESS",
                "address": 0x58,
                "direction": "READ",
                "ack": "ACK",
            },
            {"timestamp": 0.00002, "event_type": "DATA", "data": 0x01, "ack": "ACK"},
            {"timestamp": 0.00003, "event_type": "DATA", "data": 0x02, "ack": "ACK"},
            {"timestamp": 0.00004, "event_type": "DATA", "data": 0x03, "ack": "NACK"},
            {"timestamp": 0.00005, "event_type": "STOP"},
        ]
    )
    assert any(issue.code == "I2C_PMBUS_PAYLOAD_OVERLONG" for issue in report.data_quality_issues)


def test_engine_surfaces_pmbus_incomplete_response_as_data_quality():
    report = I2CDiagnosticEngine().analyze_records(
        [
            {"timestamp": 0.0, "event_type": "START"},
            {
                "timestamp": 0.00001,
                "event_type": "ADDRESS",
                "address": 0x58,
                "direction": "READ",
                "ack": "ACK",
            },
            {"timestamp": 0.00002, "event_type": "DATA", "data": 0x01, "ack": "NACK"},
            {"timestamp": 0.00003, "event_type": "STOP"},
        ]
    )
    assert any(issue.code == "I2C_PMBUS_PAYLOAD_TRUNCATED" for issue in report.data_quality_issues)


def test_engine_rejects_malformed_direct_event_and_reports_unknown_csv_rows():
    with pytest.raises(ValueError, match="timestamp"):
        I2CDiagnosticEngine().analyze(
            [RawI2CEvent(timestamp=None, event_type=RawEventType.DATA)]  # type: ignore[arg-type]
        )

    report = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Type,Address,Data\n0,GARBAGE,not-an-address,not-a-byte\n"
    )
    assert report.total_transactions == 0
    assert {issue.code for issue in report.data_quality_issues} >= {
        "I2C_UNKNOWN_EVENT_TYPE",
        "I2C_SOURCE_PARSE_ERROR",
    }
    invalid_address = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Address,Data\n0,invalid,0x12\n"
    )
    assert any(
        issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in invalid_address.data_quality_issues
    )
    invalid_type = I2CDiagnosticEngine(eeprom_profile="24C02").analyze_csv_content(
        "Time,Type,Address,Read/Write,Data,ACK\n0,BOGUS,0x50,WRITE,0x01,ACK\n"
    )
    assert invalid_type.total_transactions == 0
    assert any(issue.code == "I2C_UNKNOWN_EVENT_TYPE" for issue in invalid_type.data_quality_issues)
    with pytest.raises(ValueError, match="packet_id"):
        I2CParser.parse_raw_records([{"type": "DATA", "packet_id": -1, "data": 0x01}])
    with pytest.raises(TypeError, match="text trace"):
        I2CParser.parse_text_trace(None)  # type: ignore[arg-type]
    text_report = I2CDiagnosticEngine().analyze(
        I2CParser.parse_text_trace("S 0x50 W xyz 0x100 A P")
    )
    assert any(issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in text_report.data_quality_issues)


def test_i2c_parser_does_not_coerce_malformed_numeric_or_schema_values():
    assert parse_hex_or_int(1.5) is None
    assert parse_hex_or_int(float("nan")) is None
    assert parse_hex_or_int(True) is None
    with pytest.raises(ValueError, match="duplicate"):
        I2CParser.parse_csv_string("Time,Address,address,Data\n0,0x50,0x51,0x01\n")

    report = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Packet ID,Address,Read/Write,Data,ACK/NACK,Duration\n"
        "0,not-a-number,0x50,SIDEWAYS,0x01,WHAT,nan\n"
    )
    assert any(issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in report.data_quality_issues)


def test_i2c_row_width_mismatch_is_not_decoded_as_a_transaction():
    report = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Type,Address,Data,ACK\n0,DATA,0x50,0x01,ACK,unexpected\n"
    )
    assert report.total_transactions == 0
    assert any(issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in report.data_quality_issues)


def test_sensor_decoders_reject_invalid_direct_byte_inputs():
    with pytest.raises(ValueError, match="data_bytes"):
        decode_lm75_temperature([256])
    with pytest.raises(ValueError, match="data_bytes"):
        decode_ina2xx_power(0x02, [-1, 0])
    with pytest.raises(ValueError, match="data_bytes"):
        decode_pca9555_gpio(0x00, [0x100])
    with pytest.raises(ValueError, match="reg_pointer"):
        decode_ina2xx_power(0x100, [0, 0])


def test_sensor_short_register_response_is_explicitly_incomplete():
    result = decode_ina2xx_power(0x02, [0x12])
    assert result["evidence"] == "truncated"
    assert result["is_complete"] is False
    assert result["required_bytes"] == 2


def test_i2c_direct_timing_and_waveform_inputs_reject_nonfinite_values():
    with pytest.raises(ValueError, match="duration_s"):
        I2CDiagnosticEngine().analyze(
            [RawI2CEvent(0.0, RawEventType.DATA, duration_s=float("inf"))]
        )
    with pytest.raises(ValueError, match="total_trace_duration_s"):
        analyze_timing_statistics([], float("nan"))
    with pytest.raises(ValueError, match="default_clock_khz"):
        I2CWaveformReconstructor(default_clock_khz=float("nan"))


def test_i2c_missing_direction_and_data_are_not_guessed():
    report = I2CDiagnosticEngine().analyze(
        [
            RawI2CEvent(
                timestamp=0.0,
                event_type=RawEventType.ADDRESS,
                address_7bit=0x50,
                ack=AckType.ACK,
            ),
            RawI2CEvent(
                timestamp=0.0001,
                event_type=RawEventType.DATA,
                address_7bit=0x50,
                data_byte=None,
            ),
        ]
    )
    tx = report.transactions[0]
    assert tx.address_available is True
    assert tx.direction_available is False
    assert tx.data_bytes == []
    assert tx.hex_dump == "[unavailable]"
    serialized = report.to_dict()["transactions"][0]
    assert serialized["direction"] is None
    assert any(issue.code == "I2C_DIRECTION_UNAVAILABLE" for issue in report.data_quality_issues)
    assert any(issue.code == "I2C_DATA_UNAVAILABLE" for issue in report.data_quality_issues)
    assert not any(issue.code == "I2C_DATA_NACK" for issue in report.issues)


def test_i2c_missing_middle_byte_is_visible_and_withholds_semantics():
    report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze(
        [
            RawI2CEvent(0.0, RawEventType.ADDRESS, address_7bit=0x50, direction=I2CDirection.WRITE),
            RawI2CEvent(0.0001, RawEventType.DATA, address_7bit=0x50, direction=I2CDirection.WRITE),
            RawI2CEvent(
                0.0002,
                RawEventType.DATA,
                address_7bit=0x50,
                direction=I2CDirection.WRITE,
                data_byte=0x12,
            ),
            RawI2CEvent(0.0003, RawEventType.STOP),
        ]
    )
    tx = report.transactions[0]
    assert tx.hex_dump == "[unavailable, 0x12]"
    assert tx.semantic_summary == "Data byte unavailable; semantic decoding withheld"
    assert tx.decoded_values == {"evidence": "data-unavailable"}
    assert any(issue.code == "I2C_DATA_UNAVAILABLE" for issue in report.data_quality_issues)


def test_reused_engine_does_not_leak_mux_state_between_captures():
    engine = I2CDiagnosticEngine()
    first = engine.analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x70,Write,0x01,ACK\n"
    )
    assert "MUX 0x70" in first.transactions[0].semantic_summary

    second = engine.analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,0x10,ACK\n"
    )
    assert second.transactions[0].mux_topology is None


from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.i2c.waveform_diff import DivergencePoint, WaveformDiffEngine, WaveformDiffReport
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.uart.models import CrashType
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def test_uart_arm64_kernel_panic_parsing():
    arm64_log = """Internal error: Oops: 96000005 [#1] SMP
Modules linked in: nvme nvme_core pci_hyperv
CPU: 2 PID: 1234 Comm: kworker/u8:2 Not tainted 5.15.0-arm64
Hardware name: Wiwynn Yosemite V4 (DT)
pstate: 60400005 (nZCv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
pc : [<ffff800008123456>] nvme_pci_complete_rq+0x38/0x120 [nvme]
lr : [<ffff800008123418>] nvme_irq_handler+0x8c/0x100 [nvme]
sp : ffff80000a113bc0
x0 : 0000000000000000 x1 : ffff000082345000 x2 : 0000000000000000
FAR_EL1: 0000000000000010
Call trace:
 [<ffff800008123456>] nvme_pci_complete_rq+0x38/0x120 [nvme]
 [<ffff800008123418>] nvme_irq_handler+0x8c/0x100 [nvme]
 [<ffff800008012340>] handle_irq_event+0x4c/0x90
---[ end trace 0000000000000000 ]---
"""
    report = UARTCrashParser.parse_log_text(arm64_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "ARM64"
    assert report.kernel_panic.faulting_func == "nvme_pci_complete_rq"
    assert report.kernel_panic.faulting_address == "0x0000000000000010"
    assert "nvme" in report.kernel_panic.modules_linked
    assert len(report.kernel_panic.call_trace) == 3
    assert "NULL Pointer Dereference" in report.kernel_panic.root_cause_analysis
    md = UARTReporter.to_markdown(report)
    assert "ARM64" in md
    assert "nvme, nvme_core, pci_hyperv" in md


def test_uart_riscv_kernel_panic_parsing():
    riscv_log = """Kernel panic - not syncing: Fatal exception in interrupt
epc : [<ffffffe000012345>] faulting_driver_isr+0x14/0x30 [riscv_drv]
ra : [<ffffffe000012300>] generic_irq_handler+0x20/0x40
sstatus: 0000000200000100
Call Trace:
 [<ffffffe000012345>] faulting_driver_isr+0x14/0x30 [riscv_drv]
 [<ffffffe000012300>] generic_irq_handler+0x20/0x40
Code: 01 02 03 04
"""
    report = UARTCrashParser.parse_log_text(riscv_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "RISC-V"
    assert report.kernel_panic.faulting_func == "faulting_driver_isr"


def test_uart_arm_hardfault_all_flags_and_zero_address():
    # CFSR: MMFSR has MMARVALID (0x80) and DACCVIOL (0x02) -> 0x82
    # BFSR has BFARVALID (0x80) and PRECISERR (0x02) -> 0x82
    # UFSR has DIVBYZERO (0x0200) and UNALIGNED (0x0100) -> 0x0300
    # CFSR = 0x03008282
    # MMFAR = 0x00000000, BFAR = 0x00000000
    hardfault_log = """HardFault Exception!
HFSR: 0x40000000
CFSR: 0x03008282
MMFAR: 0x00000000
BFAR: 0x00000000
Stacked PC: 0x08001000
Stacked LR: 0xFFFFFFF9
"""
    report = UARTCrashParser.parse_log_text(hardfault_log)
    assert report.crash_type == CrashType.ARM_HARDFAULT
    assert report.arm_hardfault is not None
    hf = report.arm_hardfault
    assert hf.mmfar_raw == 0x00000000
    assert hf.bfar_raw == 0x00000000
    assert any("MMFSR.MMARVALID (Fault Address: 0x00000000)" in f for f in hf.fault_flags)
    assert any("BFSR.BFARVALID (Fault Address: 0x00000000)" in f for f in hf.fault_flags)
    assert any("DIVBYZERO" in f for f in hf.fault_flags)
    assert any("UNALIGNED" in f for f in hf.fault_flags)
    md = UARTReporter.to_markdown(report)
    assert "0x00000000" in md
    assert "MMFAR" in md


def test_mctp_ipmb_checksum_corruption_disambiguation():
    # IPMB frame with corrupted Checksum 1 (Chk1 = 0x00 instead of valid sum)
    # rsSA=0x20, NetFn=0x18, Chk1=0x00 (Corrupted), rqSA=0x81, rqSeq=0x20, Cmd=0x01, Chk2=0x5E
    hex_dump = "20 18 00 81 20 01 5E"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.ipmb_frames) == 1
    assert len(report.mctp_packets) == 0
    assert report.ipmb_frames[0].checksum1_valid is False
    assert report.ipmb_frames[0].cmd_name == "Get Device ID"


def test_mctp_som_zero_no_pldm_decode():
    # Multi-packet continuation segment where SOM=0, Flags = 0x40 (SOM=0, EOM=1, Seq=0, Tag=0)
    # Even if payload bytes resemble PLDM, it should NOT decode as PLDM command
    hex_dump = "01 08 00 40 80 02 01 00"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.mctp_packets) == 1
    pkt = report.mctp_packets[0]
    assert pkt.som is False
    assert pkt.pldm_command is None
    assert pkt.msg_type_name == "Continuation Segment (SOM=0)"


def test_dts_gen_empty_devices_list():
    # Explicitly passing devices=[] should NOT fallback to default mock devices
    dts = DeviceTreeGenerator.generate_dts_from_topology(bus_num=1, mux_addr=0x70, devices=[])
    assert "&i2c1 {" in dts
    assert "i2c-mux@70 {" in dts
    assert 'compatible = "atmel,24c64";' not in dts
    assert 'compatible = "national,lm75";' not in dts


def test_dts_gen_rejects_duplicate_address_on_same_channel():
    # String addresses are accepted, but duplicate unit addresses are invalid Device Tree.
    devices = [
        {
            "addr": "0x50",
            "channel": "0",
            "name": "eeprom",
            "compatible": "atmel,24c64",
        },
        {
            "addr": "0x50",
            "channel": "0",
            "name": "eeprom-copy",
            "compatible": "atmel,24c64",
        },
    ]
    with pytest.raises(ValueError, match="duplicate I2C address"):
        DeviceTreeGenerator.generate_dts_from_topology(bus_num=2, mux_addr="0x70", devices=devices)


def test_waveform_diff_identical_traces_figure():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    diff = WaveformDiffReport(
        is_identical=True,
        total_compared=1,
        divergence_points=[],
        summary="Identical",
        golden_first_tx=tx,
        failing_first_tx=tx,
    )
    fig = WaveformDiffEngine.create_comparison_figure(diff)
    assert len(fig.data) >= 2  # Has traces in subplots


def test_waveform_diff_missing_tx_figure():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    dp = DivergencePoint(
        tx_index=1,
        golden_tx=tx,
        failing_tx=None,
        mismatch_type="MISSING_TX",
        description="Premature termination",
        root_cause_hint="Check driver",
    )
    diff = WaveformDiffReport(
        is_identical=False, total_compared=1, divergence_points=[dp], summary="Diverged"
    )
    fig = WaveformDiffEngine.create_comparison_figure(diff)
    assert fig is not None


def test_waveform_reconstructor_rejects_zero_clock():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    with pytest.raises(ValueError, match="default_clock_khz"):
        I2CWaveformReconstructor(default_clock_khz=0.0)
    rec = I2CWaveformReconstructor(default_clock_khz=100.0)
    with pytest.raises(ValueError, match="clock_khz"):
        rec.reconstruct_transaction_waveform(tx, clock_khz=-10.0)
