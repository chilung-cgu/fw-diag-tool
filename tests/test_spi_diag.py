import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.models import (
    FlashStatusRegister1,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
    SPITransaction,
)
from fw_diag_tool.spi.parser import SPIParser
from fw_diag_tool.spi.reporter import SPIReporter


def test_spi_jedec_id_and_wren_program():
    # Simulated SPI trace:
    # 1. Read JEDEC ID (0x9F -> 0xEF 0x40 0x18 Winbond W25Q128)
    # 2. Write Enable (0x06)
    # 3. Page Program (0x02 0x00 0x10 0x00, 4 bytes data)
    csv_data = """Time [s],MOSI,MISO,Enable
0.0001,0x9F,0x00,0
0.0002,0x00,0xEF,0
0.0003,0x00,0x40,0
0.0004,0x00,0x18,0
0.0005,0x00,0x00,1
0.0010,0x06,0x00,0
0.0011,0x00,0x00,1
0.0020,0x02,0x00,0
0.0021,0x00,0x00,0
0.0022,0x10,0x00,0
0.0023,0x00,0x00,0
0.0024,0xAA,0x00,0
0.0025,0xBB,0x00,0
0.0026,0xCC,0x00,0
0.0027,0xDD,0x00,0
0.0028,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.total_transactions == 3
    assert report.summary.detected_flash_chip == "Winbond W25Q128 (128 Mbit / 16 MB)"
    assert report.summary.write_count == 1
    assert report.summary.anomaly_count == 0
    md = SPIReporter.to_markdown(report)
    assert "Winbond W25Q128" in md


def test_spi_write_without_wren_anomaly():
    # Page program issued directly without 0x06
    csv_data = """Time [s],MOSI,MISO,Enable
0.0010,0x02,0x00,0
0.0011,0x00,0x00,0
0.0012,0x00,0x00,0
0.0013,0x00,0x00,0
0.0014,0x55,0x00,0
0.0015,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.anomaly_count == 1
    assert report.anomalies[0].code == "SPI_WEL_STATE_UNKNOWN"
    assert report.anomalies[0].severity == SPISeverity.WARNING


def test_spi_status_wel_evidence_controls_program_diagnosis():
    status_then_program = """Time [s],MOSI,MISO,Enable
0.001,0x05,0x00,0
0.002,0x00,0x02,0
0.003,0x00,0x00,1
0.010,0x02,0x00,0
0.011,0x00,0x00,0
0.012,0x00,0x00,0
0.013,0x00,0x00,0
0.014,0x55,0x00,0
0.015,0x00,0x00,1
"""
    report = SPIDiagnosticEngine().analyze_csv_content(status_then_program)
    assert report.summary.anomaly_count == 0
    assert report.transactions[0].wel_state_before is True

    wren_then_wel_clear = """Time [s],MOSI,MISO,Enable
0.001,0x06,0x00,0
0.002,0x00,0x00,1
0.010,0x05,0x00,0
0.011,0x00,0x00,0
0.012,0x00,0x00,1
0.020,0x02,0x00,0
0.021,0x00,0x00,0
0.022,0x00,0x00,0
0.023,0x00,0x00,0
0.024,0x55,0x00,0
0.025,0x00,0x00,1
"""
    cleared = SPIDiagnosticEngine().analyze_csv_content(wren_then_wel_clear)
    assert [issue.code for issue in cleared.anomalies] == ["SPI_WEL_NOT_LATCHED"]


def test_spi_page_program_wrap_around_hazard():
    # Program starting at offset 0xF0 with 30 bytes (> 256 page wrap)
    tx1_csv = "0.001,0x06,0x00,0\n0.002,0x00,0x00,1\n"
    tx2_rows = ["0.010,0x02,0x00,0", "0.011,0x00,0x00,0", "0.012,0x00,0x00,0", "0.013,0xF0,0x00,0"]
    for i in range(30):
        tx2_rows.append(f"0.0{20 + i},0x{i:02X},0x00,0")
    tx2_rows.append("0.060,0x00,0x00,1")
    csv_data = "Time [s],MOSI,MISO,Enable\n" + tx1_csv + "\n".join(tx2_rows)

    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert any(a.code == "SPI_PAGE_PROGRAM_WRAP" for a in report.anomalies)


def test_spi_custom_page_size_is_used_by_parser_and_anomaly_detector():
    rows = [
        "0.001,0x06,0x00,0",
        "0.002,0x00,0x00,1",
        "0.010,0x02,0x00,0",
        "0.011,0x00,0x00,0",
        "0.012,0x00,0x00,0",
        "0.013,0x0C,0x00,0",
        "0.014,0xAA,0x00,0",
        "0.015,0xBB,0x00,0",
        "0.016,0xCC,0x00,0",
        "0.017,0xDD,0x00,0",
        "0.018,0xEE,0x00,0",
        "0.019,0x00,0x00,1",
    ]
    csv_data = "Time [s],MOSI,MISO,Enable\n" + "\n".join(rows)

    report = SPIDiagnosticEngine(max_page_size=16).analyze_csv_content(csv_data)

    wrap = next(issue for issue in report.anomalies if issue.code == "SPI_PAGE_PROGRAM_WRAP")
    assert wrap.details["page_size"] == 16
    assert "16-byte page boundary" in wrap.description


def test_spi_page_size_rejects_non_positive_or_boolean_values():
    for value in (0, -1, True):
        with pytest.raises(ValueError):
            SPIDiagnosticEngine(max_page_size=value)

    for value in (0, -1, True):
        with pytest.raises(ValueError):
            SPIParser.parse_csv_content("", page_size=value)


@pytest.mark.parametrize(
    "csv_text",
    [
        "Time [s],MOSI,MISO,Enable\n0.001,0x100,0x00,0\n",
        "Time [s],MOSI,MISO,Enable\n0.001,0x06,0x00,invalid\n",
        "Time [s],MOSI,MISO,Enable\n0.002,0x06,0x00,0\n0.001,0x00,0x00,1\n",
        "Time [s],MOSI\n0.001,0x06\n",
    ],
)
def test_spi_parser_rejects_invalid_cells_instead_of_silently_wrapping(csv_text):
    with pytest.raises(ValueError):
        SPIParser.parse_csv_content(csv_text)


def test_spi_parser_requires_cs_framing_and_rejects_one_sided_rows():
    with pytest.raises(ValueError, match="CS/Enable"):
        SPIParser.parse_csv_content("Time,MOSI,MISO\n0.001,0x06,0x00\n")
    with pytest.raises(ValueError, match="both MOSI and MISO"):
        SPIParser.parse_csv_content("Time,MOSI,MISO,Enable\n0.001,,0x00,0\n")


def test_spi_parser_rejects_ambiguous_headers_extra_columns_and_channel_mismatch():
    with pytest.raises(ValueError, match="duplicate"):
        SPIParser.parse_csv_content("Time,MOSI,MOSI,MISO,Enable\n0,0x06,0x00,0x00,0\n")
    with pytest.raises(ValueError, match="expected"):
        SPIParser.parse_csv_content("Time,MOSI,MISO,Enable\n0,0x06,0x00\n")
    with pytest.raises(ValueError, match="same number"):
        SPIParser.decode_single_transaction(1, 0.0, 0.1, [0x06, 0x00], [0x00])


def test_spi_parser_requires_explicit_wire_aliases_and_rejects_si_collision():
    with pytest.raises(ValueError, match="MOSI"):
        SPIParser.parse_csv_content(
            "Time,Signal,MISO,CS\n0.0,0x9F,0xEF,0\n0.1,0x00,0x40,1\n"
        )
    with pytest.raises(ValueError, match="ambiguous MOSI"):
        SPIParser.parse_csv_content(
            "Time,SI,MOSI,MISO,CS\n0.0,0x9F,0x9F,0xEF,0\n0.1,0x00,0x00,0x40,1\n"
        )
    with pytest.raises(ValueError, match="ambiguous MISO"):
        SPIParser.parse_csv_content(
            "Time,MOSI,SO,MISO,CS\n0.0,0x9F,0xEF,0xEF,0\n0.1,0x00,0x40,0x40,1\n"
        )


def test_spi_hex_byte_helper_rejects_boolean_values():
    assert SPIParser.parse_hex_byte(True) is None
    assert SPIParser.parse_hex_byte(False) is None


def test_spi_direct_decoder_rejects_malformed_time_and_bytes():
    with pytest.raises(ValueError, match="finite"):
        SPIParser.decode_single_transaction(1, float("nan"), 1.0, [0x06], [0x00])
    with pytest.raises(ValueError, match="end_time"):
        SPIParser.decode_single_transaction(1, 2.0, 1.0, [0x06], [0x00])
    with pytest.raises(ValueError, match="range"):
        SPIParser.decode_single_transaction(1, 1.0, 1.0, [0x06, 256], [0x00])
    with pytest.raises(ValueError, match="non-empty"):
        SPIParser.decode_single_transaction(1, 1.0, 1.0, [], [0x00])


def test_spi_status_decoder_rejects_out_of_range_raw_values():
    with pytest.raises(ValueError, match="0..0xFF"):
        FlashStatusRegister1.decode(256)
    with pytest.raises(ValueError, match="0..0xFF"):
        FlashStatusRegister1.decode(True)


@pytest.mark.parametrize(
    "mosi,miso",
    [
        ("0x9F,0x00", "0x9F,0x00"),
        ("0x05", "0x05"),
        ("0x02,0x00,0x00,0x00", "0x02,0x00,0x00,0x00"),
        ("0x01", "0x01"),
        ("0x90", "0x90"),
        ("0x4B", "0x4B"),
        ("0x5A", "0x5A"),
    ],
)
def test_spi_command_specific_short_responses_are_data_quality(mosi, miso):
    # Add any remaining command bytes while CS is asserted.
    mosi_bytes = mosi.split(",")
    miso_bytes = miso.split(",")
    rows = ["Time,MOSI,MISO,Enable"]
    for index, (tx_byte, rx_byte) in enumerate(zip(mosi_bytes, miso_bytes), start=1):
        rows.append(f"0.00{index},{tx_byte},{rx_byte},0")
    rows.append("0.010,0x00,0x00,1")
    report = SPIDiagnosticEngine().analyze_csv_content("\n".join(rows) + "\n")
    assert any(issue.code == "SPI_RESPONSE_TRUNCATED" for issue in report.data_quality_issues)


def test_spi_status_write_overlong_payload_is_data_quality():
    tx = SPIParser.decode_single_transaction(
        1, 0.0, 0.001, [0x01, 0xAA, 0xBB], [0x00, 0x00, 0x00]
    )
    assert tx.decoded_details["response_overlong"] is True
    report = SPIDiagnosticEngine().analyze_csv_content(
        "Time,MOSI,MISO,Enable\n"
        "0.0,0x01,0x00,0\n"
        "0.1,0xAA,0x00,0\n"
        "0.2,0xBB,0x00,0\n"
        "0.3,0x00,0x00,1\n"
    )
    assert any(issue.code == "SPI_RESPONSE_OVERLONG" for issue in report.data_quality_issues)


def test_spi_device_reset_clears_observed_wel_before_program():
    rows = [
        "0.001,0x06,0x00,0",
        "0.002,0x00,0x00,1",
        "0.003,0x66,0x00,0",
        "0.004,0x00,0x00,1",
        "0.005,0x99,0x00,0",
        "0.006,0x00,0x00,1",
        "0.010,0x02,0x00,0",
        "0.011,0x00,0x00,0",
        "0.012,0x00,0x00,0",
        "0.013,0x00,0x00,0",
        "0.014,0x55,0x00,0",
        "0.015,0x00,0x00,1",
    ]
    report = SPIDiagnosticEngine().analyze_csv_content(
        "Time,MOSI,MISO,Enable\n" + "\n".join(rows) + "\n"
    )
    assert any(issue.code == "SPI_WEL_NOT_LATCHED" for issue in report.anomalies)


@pytest.mark.parametrize(
    "csv_text", ["", "   \n", "# comment only\n", "Time [s],MOSI,MISO,Enable\n"]
)
def test_spi_empty_or_header_only_capture_is_not_reported_clean(csv_text):
    report = SPIDiagnosticEngine().analyze_csv_content(csv_text)

    assert report.summary.total_transactions == 0
    assert any(issue.code == "SPI_SOURCE_EMPTY" for issue in report.data_quality_issues)


def test_spi_unterminated_or_unframed_capture_is_marked_incomplete():
    unterminated = SPIDiagnosticEngine().analyze_csv_content(
        "Time [s],MOSI,MISO,Enable\n0.001,0x06,0x00,0\n"
    )
    assert any(issue.code == "SPI_CS_UNTERMINATED" for issue in unterminated.data_quality_issues)

    no_transaction = SPIDiagnosticEngine().analyze_csv_content(
        "Time [s],MOSI,MISO,Enable\n0.001,0x06,0x00,1\n"
    )
    assert any(issue.code == "SPI_NO_TRANSACTIONS" for issue in no_transaction.data_quality_issues)


def test_spi_markdown_reporter_handles_unavailable_timestamps():
    report = SPIReport(
        summary=SPIReportSummary(total_transactions=1),
        transactions=[
            SPITransaction(
                index=1,
                start_time=None,  # type: ignore[arg-type]
                end_time=None,  # type: ignore[arg-type]
                duration_us=0.0,
                mosi_bytes=[0x06],
                miso_bytes=[0x00],
            )
        ],
    )
    markdown = SPIReporter.to_markdown(report)
    assert "n/a" in markdown


def test_spi_cli_reports_invalid_csv_without_traceback(tmp_path):
    trace_path = tmp_path / "invalid.csv"
    trace_path.write_text("Time [s],MOSI,MISO,Enable\n0.001,0x100,0x00,0\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["spi", "analyze", str(trace_path)])

    assert result.exit_code == 2
    assert "SPI CSV is invalid" in result.output
