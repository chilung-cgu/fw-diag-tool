"""Comprehensive Test Suite for I2C / SMBus / PMBus Diagnostic Engine."""

from pathlib import Path

from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.i2c.chip_db import lookup_device
from fw_diag_tool.i2c.eeprom import (
    decode_eeprom_read,
    decode_eeprom_write,
)
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CDirection,
    I2CSpeedMode,
    Severity,
)
from fw_diag_tool.i2c.parser import parse_ack, parse_direction, parse_hex_or_int
from fw_diag_tool.i2c.pmbus import (
    decode_linear11,
    decode_linear16,
    decode_status_byte,
    decode_status_cml,
    decode_status_word,
    encode_linear11,
    parse_vout_mode_exponent,
)
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.sensor_decoders import (
    decode_ina2xx_power,
    decode_lm75_temperature,
    decode_pca9555_gpio,
)


def test_parse_helpers():
    assert parse_hex_or_int("0x50") == 0x50
    assert parse_hex_or_int("50h") == 0x50
    assert parse_hex_or_int("80") == 80
    assert parse_hex_or_int(123) == 123
    assert parse_hex_or_int(None) is None

    assert parse_direction("Write") == I2CDirection.WRITE
    assert parse_direction("READ") == I2CDirection.READ
    assert parse_direction("W") == I2CDirection.WRITE
    assert parse_direction("R") == I2CDirection.READ

    assert parse_ack("ACK") == AckType.ACK
    assert parse_ack("NAK") == AckType.NACK
    assert parse_ack("NACK") == AckType.NACK


def test_linear11_decoding():
    # 0xE200 -> Exponent=-4, Mantissa=512 -> 512 * 2^-4 = 32.0
    assert decode_linear11(0xE200) == 32.0

    # 12V encoded: Exponent=-4, Mantissa=192 -> (11100b << 11) | 192 = 0xE0C0
    val_12 = decode_linear11(0xE0C0)
    assert val_12 == 12.0

    # Negative value: -15.5°C
    neg_encoded = encode_linear11(-15.5)
    val_neg = decode_linear11(neg_encoded)
    assert abs(val_neg - (-15.5)) < 0.1

    # Round trip encode/decode
    encoded = encode_linear11(12.0)
    assert decode_linear11(encoded) == 12.0

    encoded_46 = encode_linear11(46.0)
    assert abs(decode_linear11(encoded_46) - 46.0) < 0.1


def test_linear16_decoding():
    # VOUT_MODE exponent -9: raw 0x021A (538) -> 538 * 2^-9 = 1.05078125
    vout = decode_linear16(0x021A, vout_mode_exponent=-9)
    assert abs(vout - 1.05078) < 0.001

    assert parse_vout_mode_exponent(0x17) == -9
    assert parse_vout_mode_exponent(0x14) == -12


def test_pmbus_status_decoding():
    # STATUS_BYTE with VOUT_OV and CML
    flags_byte = decode_status_byte(0x22)
    assert any("VOUT_OV" in f for f in flags_byte)
    assert any("CML" in f for f in flags_byte)

    # STATUS_WORD with POWER_GOOD# negated and IOUT_OC
    flags_word = decode_status_word(0x0810)
    assert any("POWER_GOOD#" in f for f in flags_word)
    assert any("IOUT_OC" in f for f in flags_word)

    # STATUS_CML with INVALID_COMMAND
    flags_cml = decode_status_cml(0x80)
    assert any("INVALID_COMMAND" in f for f in flags_cml)


def test_eeprom_decoding_and_rollover():
    # Normal write within page
    res_ok = decode_eeprom_write([0x00, 0x11, 0x22, 0x33], page_size=8)
    assert res_ok["rollover_hazard"] is False
    assert res_ok["offset"] == 0x00

    # Rollover hazard: offset 6, length 4 in 8-byte page -> 6+4=10 > 8!
    res_hazard = decode_eeprom_write([0x06, 0x11, 0x22, 0x33, 0x44], page_size=8)
    assert res_hazard["rollover_hazard"] is True
    assert "Page rollover hazard" in res_hazard["rollover_details"]

    # 2-byte word addressing (24C64 / 24C256)
    res_2byte = decode_eeprom_write(
        [0x01, 0x00, 0xAA, 0xBB], preferred_address_bytes=2, page_size=64
    )
    assert res_2byte["offset"] == 0x0100
    assert res_2byte["payload_len"] == 2

    # Sequential read
    res_read = decode_eeprom_read([0x55, 0xAA, 0x12], last_known_offset=0x10)
    assert res_read["payload_len"] == 3
    assert "0x0010" in res_read["summary"]


def test_sensor_decoders():
    # LM75 temperature 25.125°C -> raw 0x1920 (0x192 = 402 -> 402 * 0.0625 = 25.125)
    t_res = decode_lm75_temperature([0x19, 0x20])
    assert abs(t_res["temp_c"] - 25.125) < 0.01

    # Negative LM75 temperature: -25.0°C -> 0xE700 -> raw_9 = 0x1CE = 462 -> 462 - 512 = -50 * 0.5 = -25.0
    t_neg = decode_lm75_temperature([0xE7, 0x00])
    assert t_neg["temp_c_9bit"] == -25.0

    # INA226 Bus Voltage: 0x2710 (10000) * 1.25mV = 12.5V
    p_res = decode_ina2xx_power(0x02, [0x27, 0x10])
    assert abs(p_res["bus_voltage_v"] - 12.5) < 0.01

    # PCA9555 GPIO Output port 0 write
    g_res = decode_pca9555_gpio(0x02, [0xA5])
    assert "OUTPUT_PORT_0" in g_res["summary"]


def test_chip_lookup():
    eeprom = lookup_device(0x50)
    assert eeprom is not None
    assert "EEPROM" in eeprom.category

    lm75 = lookup_device(0x48)
    assert lm75 is not None
    assert "Temperature Sensor" in lm75.category

    pmbus_vr = lookup_device(0x58)
    assert pmbus_vr is not None
    assert pmbus_vr.protocol == "PMBus"


def test_text_trace_parser():
    trace = """
    # Read LM75 Temperature
    [0.001000] S 0x48 W 0x00 A P
    [0.001200] S 0x48 R 0x19 A 0x20 N P
    """
    engine = I2CDiagnosticEngine()
    report = engine.analyze_text(trace)
    assert report.total_transactions == 2
    assert report.transactions[0].address_7bit == 0x48
    assert report.transactions[0].direction == I2CDirection.WRITE
    assert report.transactions[1].direction == I2CDirection.READ
    assert len(report.transactions[1].data_bytes) == 2
    assert "Temperature" in report.transactions[1].semantic_summary


def test_raw_records_analysis():
    records = [
        {"timestamp": 0.001, "event_type": "START"},
        {
            "timestamp": 0.001025,
            "event_type": "ADDRESS",
            "address": 0x58,
            "direction": "WRITE",
            "ack": "ACK",
        },
        {"timestamp": 0.001050, "event_type": "DATA", "data": 0x88, "ack": "ACK"},
        {"timestamp": 0.001075, "event_type": "STOP"},
        {"timestamp": 0.001200, "event_type": "START"},
        {
            "timestamp": 0.001225,
            "event_type": "ADDRESS",
            "address": 0x58,
            "direction": "READ",
            "ack": "ACK",
        },
        {"timestamp": 0.001250, "event_type": "DATA", "data": 0x00, "ack": "ACK"},
        {"timestamp": 0.001275, "event_type": "DATA", "data": 0xE2, "ack": "NACK"},
        {"timestamp": 0.001300, "event_type": "STOP"},
    ]
    engine = I2CDiagnosticEngine()
    report = engine.analyze_records(records)
    assert report.total_transactions == 2
    assert report.transactions[1].decoded_values.get("value") == 32.0


def test_normal_saleae_csv_analysis():
    csv_path = Path(__file__).parent / "data" / "saleae_normal_pmbus_eeprom.csv"
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_file(str(csv_path))

    assert report.total_transactions >= 10
    assert "0x58" in report.devices_detected
    assert "0x50" in report.devices_detected
    assert "0x48" in report.devices_detected
    assert "0x20" in report.devices_detected

    # Analyzer-table timestamps do not provide per-byte SCL timing evidence.
    assert report.timing_stats.avg_frequency_khz == 0
    assert report.timing_stats.frequency_sample_count == 0
    assert report.timing_stats.speed_mode == I2CSpeedMode.UNKNOWN

    # Verify PMBus decoded summaries exist
    pmbus_txs = [tx for tx in report.transactions if tx.address_7bit == 0x58]
    assert any("READ_VIN" in (tx.semantic_summary or "") for tx in pmbus_txs)
    assert any("READ_VOUT" in (tx.semantic_summary or "") for tx in pmbus_txs)

    # Check terminal rendering and markdown generation work without error
    md = I2CReporter.generate_markdown(report)
    assert "# I2C / SMBus / PMBus Protocol Diagnostic Report" in md
    assert "READ_VIN" in md


def test_anomaly_addr_nack():
    csv_path = Path(__file__).parent / "data" / "saleae_anomaly_addr_nack.csv"
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_file(str(csv_path))

    # Should detect Address NACK on 0x3A and EEPROM Write Polling on 0x50
    addr_nack_issues = [i for i in report.issues if i.code == "I2C_ADDR_NACK"]
    assert len(addr_nack_issues) >= 1
    assert addr_nack_issues[0].address_7bit == 0x3A
    assert any("萬用電表" in advice for advice in addr_nack_issues[0].actionable_advice)

    # Polling on 0x50 should be INFO
    poll_issues = [i for i in report.issues if i.code == "I2C_EEPROM_ACK_POLL"]
    assert len(poll_issues) >= 1
    assert poll_issues[0].severity == Severity.INFO


def test_anomaly_clock_stretching():
    csv_path = Path(__file__).parent / "data" / "saleae_anomaly_clock_stretching.csv"
    engine = I2CDiagnosticEngine(smbus_timeout_ms=25.0)
    report = engine.analyze_csv_file(str(csv_path))

    timeout_issues = [i for i in report.issues if i.code == "I2C_SMBUS_TIMEOUT"]
    assert len(timeout_issues) >= 1
    assert timeout_issues[0].severity == Severity.CRITICAL
    assert "28.50 ms" in timeout_issues[0].title
    assert timeout_issues[0].address_7bit == 0x58

    long_stretch = [i for i in report.issues if i.code == "I2C_LONG_CLOCK_STRETCH"]
    assert len(long_stretch) >= 1


def test_anomaly_eeprom_rollover_and_data_nack():
    csv_path = Path(__file__).parent / "data" / "saleae_anomaly_eeprom_rollover_and_data_nack.csv"
    # 0x50 is shared by multiple EEPROM families; provide the address width
    # explicitly so page-wrap analysis is evidence-backed rather than guessed.
    engine = I2CDiagnosticEngine(default_eeprom_page_size=8, default_eeprom_address_bytes=1)
    report = engine.analyze_csv_file(str(csv_path))

    # Page rollover check
    rollover_issues = [i for i in report.issues if i.code == "I2C_EEPROM_PAGE_ROLLOVER"]
    assert len(rollover_issues) == 1
    assert "Wrap-Around Hazard" in rollover_issues[0].title

    # Data NACK check
    data_nack_issues = [i for i in report.issues if i.code == "I2C_DATA_NACK"]
    assert len(data_nack_issues) == 1
    assert data_nack_issues[0].address_7bit == 0x58
    assert data_nack_issues[0].affected_bytes == [0xFF]


def test_anomaly_bus_hang_no_stop():
    csv_path = Path(__file__).parent / "data" / "saleae_anomaly_bus_hang_no_stop.csv"
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_file(str(csv_path))

    missing_stop_issues = [i for i in report.issues if i.code == "I2C_MISSING_STOP"]
    assert len(missing_stop_issues) >= 1
    assert any("9-Clock Reset" in advice for advice in missing_stop_issues[0].actionable_advice)


def test_cli_runner(tmp_path):
    runner = CliRunner()
    csv_path = Path(__file__).parent / "data" / "saleae_normal_pmbus_eeprom.csv"
    out_md = tmp_path / "report.md"
    out_json = tmp_path / "report.json"

    result = runner.invoke(
        app, ["i2c", "analyze", str(csv_path), "--md", str(out_md), "--json", str(out_json)]
    )
    assert result.exit_code == 0
    assert out_md.exists()
    assert out_json.exists()
    assert "READ_VIN" in out_md.read_text(encoding="utf-8")
