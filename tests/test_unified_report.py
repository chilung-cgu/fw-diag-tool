"""Tests for the unified multi-protocol diagnostic report generator."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.gui.pages import unified_report_ui
from fw_diag_tool.reporting.unified_report import (
    ProtocolResult,
    analyze_file_for_unified_report,
    build_unified_report,
    detect_file_protocol,
    generate_unified_report_from_files,
)

runner = CliRunner()


def test_empty_results() -> None:
    """Empty results list should produce a valid report with 100.0 health score and success status."""
    report = build_unified_report([])
    assert report.results == []
    assert report.overall_health_score == 100.0
    assert report.overall_status == "success"
    assert report.generated_at
    assert report.tool_version

    md = report.to_markdown()
    assert "# 韌體診斷統一報告" in md
    assert "## 執行摘要" in md
    assert "## 簽核檢查清單" in md
    assert "未包含任何協定分析結果" in md

    html = report.to_html()
    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "韌體診斷統一報告" in html


def test_single_protocol_report_success() -> None:
    """Single protocol with success status."""
    res = ProtocolResult(
        protocol="I2C",
        summary="100 筆交易正常",
        anomaly_count=0,
        total_items=100,
        status="success",
        markdown_report="### I2C Diagnostic\n\nAll transactions ACKed.",
    )
    report = build_unified_report([res])
    assert len(report.results) == 1
    assert report.overall_health_score == 100.0
    assert report.overall_status == "success"

    md = report.to_markdown()
    assert "I2C" in md
    assert "100 筆交易正常" in md
    assert "All transactions ACKed" in md
    assert "PASS (核准簽核 / APPROVED)" in md


def test_single_protocol_report_warning() -> None:
    """Single protocol with warning status."""
    res = ProtocolResult(
        protocol="SPI",
        summary="發現 1 個逾時警告",
        anomaly_count=1,
        total_items=20,
        status="warning",
        markdown_report="### SPI Report\n\nTimeout on CS release.",
    )
    report = build_unified_report([res])
    assert len(report.results) == 1
    assert report.overall_health_score < 100.0
    assert report.overall_status == "warning"

    md = report.to_markdown()
    assert "SPI" in md
    assert "⚠ 警告" in md


def test_single_protocol_report_error() -> None:
    """Single protocol with error status."""
    res = ProtocolResult(
        protocol="UART",
        summary="Linux Kernel Panic",
        anomaly_count=2,
        total_items=10,
        status="error",
        markdown_report="### UART Crash\n\nKernel panic: fatal exception.",
    )
    report = build_unified_report([res])
    assert len(report.results) == 1
    assert report.overall_health_score <= 50.0
    assert report.overall_status == "error"

    md = report.to_markdown()
    assert "UART" in md
    assert "✖ 錯誤" in md
    assert "FAIL (未通過 / REJECTED)" in md


def test_multi_protocol_report() -> None:
    """Multiple protocols in a single unified report."""
    results = [
        ProtocolResult("I2C", "I2C OK", 0, 50, "success", "I2C details"),
        ProtocolResult("SPI", "SPI OK", 0, 30, "success", "SPI details"),
        ProtocolResult("UART", "UART Panic", 1, 10, "error", "UART details"),
        ProtocolResult("PCIe", "PCIe Degraded", 1, 4, "warning", "PCIe details"),
        ProtocolResult("MCTP", "MCTP OK", 0, 25, "success", "MCTP details"),
    ]
    report = build_unified_report(results)
    assert len(report.results) == 5
    assert report.overall_status == "error"

    md = report.to_markdown()
    for p in ["I2C", "SPI", "UART", "PCIe", "MCTP"]:
        assert p in md
    assert "I2C details" in md
    assert "SPI details" in md
    assert "UART details" in md
    assert "PCIe details" in md
    assert "MCTP details" in md


def test_health_score_all_success() -> None:
    """All success results should yield health score 100.0."""
    results = [
        ProtocolResult("I2C", "OK", 0, 10, "success", "md"),
        ProtocolResult("SPI", "OK", 0, 20, "success", "md"),
        ProtocolResult("MCTP", "OK", 0, 30, "success", "md"),
    ]
    report = build_unified_report(results)
    assert report.overall_health_score == 100.0
    assert report.overall_status == "success"


def test_health_score_all_error() -> None:
    """All error results should yield very low health score and error status."""
    results = [
        ProtocolResult("I2C", "Error", 5, 5, "error", "md"),
        ProtocolResult("UART", "Error", 10, 10, "error", "md"),
    ]
    report = build_unified_report(results)
    assert report.overall_health_score == 0.0
    assert report.overall_status == "error"


def test_health_score_mixed() -> None:
    """Mixed results calculation."""
    results = [
        ProtocolResult("I2C", "OK", 0, 10, "success", "md"),
        ProtocolResult("SPI", "Warn", 1, 100, "warning", "md"),
        ProtocolResult("UART", "Error", 5, 5, "error", "md"),
    ]
    report = build_unified_report(results)
    assert 0.0 < report.overall_health_score < 100.0
    assert report.overall_status == "error"


def test_health_score_zero_total_items() -> None:
    """Handling protocols with zero total items."""
    r_success = ProtocolResult("I2C", "OK", 0, 0, "success", "md")
    r_warning = ProtocolResult("SPI", "Warn", 1, 0, "warning", "md")
    r_error = ProtocolResult("UART", "Error", 1, 0, "error", "md")

    rep_s = build_unified_report([r_success])
    assert rep_s.overall_health_score == 100.0

    rep_w = build_unified_report([r_warning])
    assert rep_w.overall_health_score == 70.0

    rep_e = build_unified_report([r_error])
    assert rep_e.overall_health_score == 0.0


def test_to_markdown_structure() -> None:
    """Verify all 5 required structural sections of markdown."""
    res = ProtocolResult(
        protocol="I2C",
        summary="Summary test",
        anomaly_count=1,
        total_items=10,
        status="warning",
        markdown_report="Detailed content here",
    )
    report = build_unified_report([res])
    md = report.to_markdown()

    assert "# 韌體診斷統一報告" in md
    assert "## 執行摘要 (Executive Summary)" in md
    assert "## 跨協定異常摘要 (Cross-Protocol Anomaly Summary)" in md
    assert "## 簽核檢查清單 (Sign-off Checklist)" in md
    assert "## 協定詳細報告 (Protocol Detailed Reports)" in md
    assert "Detailed content here" in md


def test_signoff_checklist_pass_and_fail() -> None:
    """Verify sign-off checklist logic."""
    # Passing report
    rep_pass = build_unified_report([
        ProtocolResult("I2C", "All OK", 0, 50, "success", "md")
    ])
    md_pass = rep_pass.to_markdown()
    assert "[x] **協定分析完整性" in md_pass
    assert "[x] **無嚴重致命錯誤" in md_pass
    assert "[x] **異常數量受控" in md_pass
    assert "[x] **健康分數達標" in md_pass
    assert "PASS (核准簽核 / APPROVED)" in md_pass

    # Failing report
    rep_fail = build_unified_report([
        ProtocolResult("UART", "Panic", 3, 10, "error", "md")
    ])
    md_fail = rep_fail.to_markdown()
    assert "[ ] **無嚴重致命錯誤" in md_fail
    assert "FAIL (未通過 / REJECTED)" in md_fail


def test_to_html_formatting() -> None:
    """Verify HTML export has valid document wrapper and converted content."""
    res = ProtocolResult(
        protocol="I2C",
        summary="I2C Test",
        anomaly_count=0,
        total_items=10,
        status="success",
        markdown_report="### I2C Details\n- Item 1\n- Item 2",
    )
    report = build_unified_report([res])
    html = report.to_html()

    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "韌體診斷統一報告" in html
    assert "I2C Details" in html
    assert "Item 1" in html


def test_detect_file_protocol(tmp_path: Path) -> None:
    """Test auto-detection of protocols from file names and contents."""
    i2c_file = tmp_path / "trace.csv"
    i2c_file.write_text("Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.001,1,0x50,0x00,Write,ACK\n")
    assert detect_file_protocol(i2c_file) == "I2C"

    spi_file = tmp_path / "spi.csv"
    spi_file.write_text("Time,MOSI,MISO,CS\n0.001,0x06,0xFF,0\n")
    assert detect_file_protocol(spi_file) == "SPI"

    uart_file = tmp_path / "uart.log"
    uart_file.write_text("Kernel panic - not syncing: Fatal exception\nCall Trace:\n")
    assert detect_file_protocol(uart_file) == "UART"

    pcie_file = tmp_path / "pcie.log"
    pcie_file.write_text("PCIe Bus Error: severity=Corrected, type=Physical Layer\n")
    assert detect_file_protocol(pcie_file) == "PCIe"

    mctp_file = tmp_path / "mctp.txt"
    mctp_file.write_text("DSP0236 MCTP Packet Dump\nHeader: 01 00 08 c8\n")
    assert detect_file_protocol(mctp_file) == "MCTP"


def test_analyze_file_for_unified_report(tmp_path: Path) -> None:
    """Test analyzing files into ProtocolResult objects."""
    i2c_f = tmp_path / "i2c_test.csv"
    i2c_f.write_text("Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.001,1,0x50,0x00,Write,ACK\n")
    res_i2c = analyze_file_for_unified_report(i2c_f, protocol="I2C")
    assert res_i2c.protocol == "I2C"
    assert res_i2c.total_items >= 1

    missing_f = tmp_path / "non_existent.csv"
    res_missing = analyze_file_for_unified_report(missing_f)
    assert res_missing.status == "error"
    assert "不存在" in res_missing.summary


def test_generate_unified_report_from_files(tmp_path: Path) -> None:
    """Test generating unified report across multiple files."""
    i2c_f = tmp_path / "i2c.csv"
    i2c_f.write_text("Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.001,1,0x50,0x00,Write,ACK\n")
    uart_f = tmp_path / "uart.log"
    uart_f.write_text("Kernel panic - not syncing\nCall Trace:\n")

    report = generate_unified_report_from_files([i2c_f, uart_f])
    assert len(report.results) == 2
    assert any(r.protocol == "I2C" for r in report.results)
    assert any(r.protocol == "UART" for r in report.results)


def test_cli_report_command(tmp_path: Path) -> None:
    """Test fw-diag report CLI command."""
    i2c_f = tmp_path / "trace.csv"
    i2c_f.write_text("Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.001,1,0x50,0x00,Write,ACK\n")
    out_md = tmp_path / "report.md"
    out_html = tmp_path / "report.html"

    # Test markdown output
    res_md = runner.invoke(app, ["report", str(i2c_f), "-o", str(out_md)])
    assert res_md.exit_code == 0
    assert out_md.exists()
    assert "# 韌體診斷統一報告" in out_md.read_text(encoding="utf-8")

    # Test HTML output
    res_html = runner.invoke(app, ["report", str(i2c_f), "--format", "html", "-o", str(out_html)])
    assert res_html.exit_code == 0
    assert out_html.exists()
    assert "韌體診斷統一報告" in out_html.read_text(encoding="utf-8")


def test_gui_unified_report_ui_callable() -> None:
    """Test GUI render function is callable."""
    assert callable(unified_report_ui.render)
