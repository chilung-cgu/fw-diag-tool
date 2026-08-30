"""Small end-to-end checks across protocol parsers, analyzers, and reports."""

from __future__ import annotations

import pytest

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.parser import I2CParser
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.statistics import compute_mctp_statistics
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.statistics import compute_pcie_statistics
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.statistics import compute_spi_statistics
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.timing import analyze_uart_timing


def test_i2c_text_trace_to_markdown_report() -> None:
    trace = "S 0x50 W 0x00 A 0x12 A P"
    events = I2CParser.parse_text_trace(trace)
    report = I2CDiagnosticEngine().analyze(events)
    markdown = I2CReporter.to_markdown(report)
    assert len(events) == 5
    assert report.total_transactions == 1
    assert report.transactions[0].address_7bit == 0x50
    assert "I2C" in markdown


def test_i2c_engine_text_entrypoint_matches_parser_pipeline() -> None:
    report = I2CDiagnosticEngine().analyze_text("S 0x50 W 0x00 A P")
    assert report.total_transactions == 1
    assert report.transactions[0].data_bytes == [0x00]


def test_i2c_malformed_trace_keeps_source_evidence() -> None:
    report = I2CDiagnosticEngine().analyze_text("S 0x50 W ??? P")
    assert report.total_transactions >= 1
    assert any(tx.source_error for tx in report.transactions) or report.data_quality_issues


def test_spi_csv_to_statistics_pipeline() -> None:
    csv_text = "Time,MOSI,MISO,Enable\n0.001,0x03,0x00,0\n0.002,0xAA,0x55,0\n0.003,0x00,0x00,1\n"
    report = SPIDiagnosticEngine().analyze_csv_content(csv_text)
    stats = compute_spi_statistics(report)
    assert len(report.transactions) == 1
    assert stats.total_bytes_transferred == 2
    assert stats.command_distribution
    assert stats.throughput_bytes_per_sec is not None


def test_spi_empty_capture_returns_quality_finding() -> None:
    report = SPIDiagnosticEngine().analyze_csv_content("Time,MOSI,MISO,Enable\n")
    assert report.transactions == []
    assert any(issue.code == "SPI_SOURCE_EMPTY" for issue in report.data_quality_issues)


def test_spi_malformed_csv_raises_value_error_without_partial_report() -> None:
    with pytest.raises(ValueError, match="invalid timestamp"):
        SPIDiagnosticEngine().analyze_csv_content("Time,MOSI,MISO,Enable\nnope,0x03,0x00,0\n")


def test_uart_log_to_timing_pipeline() -> None:
    log = """[0.000] U-Boot SPL
[1.000] Starting kernel
[2.500] Linux version 6.1
[4.000] systemd[1]: Starting init:"""
    report = UARTCrashParser.parse_log_text(log)
    timing = analyze_uart_timing(report, log)
    assert report.raw_log_lines == 4
    assert timing.timestamp_coverage == 1.0
    assert timing.total_log_duration_s == 4.0
    assert timing.boot_phase_durations["bootloader"] == 2.5


def test_uart_generic_log_is_safe_for_unrecognized_input() -> None:
    report = UARTCrashParser.parse_log_text("normal output\nwithout timestamps")
    timing = analyze_uart_timing(report, "normal output\nwithout timestamps")
    assert report.kernel_panic is None
    assert report.arm_hardfault is None
    assert timing.total_log_duration_s is None
    assert timing.timestamp_coverage == 0.0


def test_pcie_lspci_dump_to_statistics_pipeline() -> None:
    raw = bytearray(64)
    raw[0:2] = (0x34, 0x12)
    raw[2:4] = (0x78, 0x56)
    line = "0000:01:00.0 Example device\n00: " + " ".join(f"{value:02x}" for value in raw)
    bdf, data = PCIeAnalyzer.parse_lspci_text(line)
    config = PCIeAnalyzer.decode_config_space(data, bdf=bdf)
    stats = compute_pcie_statistics([config])
    assert bdf == "0000:01:00.0"
    assert config.vendor_id == 0x1234
    assert stats.device_count == 1
    assert sum(stats.topology_summary.values()) == 1


def test_pcie_malformed_lspci_does_not_crash_multi_parser() -> None:
    configs = PCIeAnalyzer.parse_multi_lspci_text("0000:02:00.0 broken dump")
    assert len(configs) == 1
    assert configs[0].data_quality_issues
    assert configs[0].bdf == "0000:02:00.0"


def test_mctp_hex_dump_to_statistics_pipeline() -> None:
    dump = "01 08 00 C0 01 00 02 01 00"
    report = ServerMgmtParser.parse_hex_dump(dump)
    stats = compute_mctp_statistics(report)
    assert report.total_frames == 1
    assert len(report.mctp_messages) == 1
    assert stats.total_packets == 1
    assert stats.total_messages == 1
    assert stats.reassembly_success_rate == 1.0


def test_mctp_malformed_line_is_reported_not_raised() -> None:
    report = ServerMgmtParser.parse_text_dump("not-a-packet\n01F")
    stats = compute_mctp_statistics(report)
    assert report.total_frames == 0
    assert report.source_errors
    assert stats.error_count == len(report.source_errors)


def test_mctp_mixed_valid_and_malformed_lines_preserves_valid_packet() -> None:
    report = ServerMgmtParser.parse_text_dump("01 08 00 C0 01 00 02 01 00\n01F")
    assert report.total_frames == 1
    assert len(report.mctp_packets) == 1
    assert report.unparsed_lines == ["01F"]
