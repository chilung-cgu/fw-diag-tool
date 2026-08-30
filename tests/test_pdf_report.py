"""Tests for PDF report generation, CLI integration, and GUI helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.gui.shared import render_pdf_download
from fw_diag_tool.reporting.pdf_report import (
    build_pdf_report,
    is_fpdf_available,
    write_pdf_report,
)

runner = CliRunner()


def test_is_fpdf_available() -> None:
    """Test that fpdf availability reflects environment."""
    assert is_fpdf_available() is True


def test_build_pdf_report_basic() -> None:
    """Test basic Markdown to PDF binary generation with CJK title and metadata."""
    md = (
        "# 韌體診斷報告標題\n\n"
        "> 總結摘要：測試正常，無異常事件。\n\n"
        "## 1. 時序統計\n\n"
        "- **時鐘頻率**: `100.0 kHz`\n"
        "- **狀態**: 正常 [OK]\n\n"
        "| 欄位 | 數值 | 判定 |\n"
        "|---|---|---|\n"
        "| 電壓 | 3.3V | PASS |\n"
        "| 電流 | 120mA | OK |\n\n"
        "```c\n"
        "#include <stdint.h>\n"
        "void main(void) { return 0; }\n"
        "```\n"
    )
    pdf_bytes = build_pdf_report(
        title="I2C 協定診斷報告",
        markdown_content=md,
        metadata={"tool": "fw-diag-tool 1.2.0", "board_profile": "SampleBoard@1.0"},
        tool_version="1.2.0",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_write_pdf_report(tmp_path: Path) -> None:
    """Test writing PDF report to a file on disk."""
    md = "## 快速檢驗\n\nSPI Flash 寫入成功。\n"
    out_file = tmp_path / "spi_report.pdf"
    result_path = write_pdf_report(
        markdown_content=md,
        output_path=out_file,
        title="SPI 診斷報告",
        metadata={"chip": "W25Q128"},
    )
    assert result_path == out_file
    assert out_file.exists()
    content = out_file.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(content) > 500


def test_cli_i2c_analyze_pdf_option(tmp_path: Path) -> None:
    """Test CLI fw-diag i2c analyze command with --pdf option."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n"
        "0.0001,1,0x50,0x00,Write,ACK\n"
        "0.0002,1,0x50,0x12,Read,ACK\n",
        encoding="utf-8",
    )
    pdf_out = tmp_path / "i2c_cli_report.pdf"
    result = runner.invoke(app, ["i2c", "analyze", str(csv_file), "--pdf", str(pdf_out)])
    assert result.exit_code == 0
    assert pdf_out.exists()
    assert pdf_out.read_bytes().startswith(b"%PDF-")
    assert "PDF 報告已匯出" in result.output or "PDF report exported to" in result.output


def test_cli_spi_analyze_pdf_option(tmp_path: Path) -> None:
    """Test CLI fw-diag spi analyze command with --pdf option."""
    spi_csv = tmp_path / "spi_sample.csv"
    spi_csv.write_text(
        "Time,MOSI,MISO,CS\n0.0001,0x9F,0x00,0\n0.0002,0x00,0xEF,0\n",
        encoding="utf-8",
    )
    pdf_out = tmp_path / "spi_cli_report.pdf"
    result = runner.invoke(app, ["spi", "analyze", str(spi_csv), "--pdf", str(pdf_out)])
    assert result.exit_code == 0
    assert pdf_out.exists()
    assert pdf_out.read_bytes().startswith(b"%PDF-")


def test_cli_pcie_uart_mctp_analyze_pdf_options(tmp_path: Path) -> None:
    """Test CLI analyze --pdf across PCIe, UART, and MCTP commands."""
    # 1. PCIe AER dmesg log
    pcie_log = tmp_path / "pcie_aer.log"
    pcie_log.write_text(
        "PCIe Bus Error: severity=Fatal, type=Transaction Layer, id=0020(Receiver ID)\n",
        encoding="utf-8",
    )
    pcie_pdf = tmp_path / "pcie.pdf"
    res_pcie = runner.invoke(app, ["pcie", "analyze", str(pcie_log), "--pdf", str(pcie_pdf)])
    assert res_pcie.exit_code == 0
    assert pcie_pdf.exists()
    assert pcie_pdf.read_bytes().startswith(b"%PDF-")

    # 2. UART Crash Panic
    uart_log = tmp_path / "panic.log"
    uart_log.write_text(
        "Kernel panic - not syncing: Fatal exception in interrupt\nCPU: 0 PID: 1\n",
        encoding="utf-8",
    )
    uart_pdf = tmp_path / "uart.pdf"
    res_uart = runner.invoke(app, ["uart", "analyze", str(uart_log), "--pdf", str(uart_pdf)])
    assert res_uart.exit_code == 0
    assert uart_pdf.exists()
    assert uart_pdf.read_bytes().startswith(b"%PDF-")

    # 3. MCTP hex dump
    mctp_hex = tmp_path / "mctp.hex"
    mctp_hex.write_text(
        "0f 10 00 00 00 01 00 00 00 00 00 00 00 00 00 00\n",
        encoding="utf-8",
    )
    mctp_pdf = tmp_path / "mctp.pdf"
    res_mctp = runner.invoke(app, ["mctp", "analyze", str(mctp_hex), "--pdf", str(mctp_pdf)])
    assert res_mctp.exit_code == 0
    assert mctp_pdf.exists()
    assert mctp_pdf.read_bytes().startswith(b"%PDF-")


def test_render_pdf_download_alternate_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test render_pdf_download when invoked as render_pdf_download(title, markdown_content, metadata)."""
    captured: list[dict[str, Any]] = []

    def mock_download_button(label: str, data: bytes, file_name: str, mime: str, key: str) -> None:
        captured.append({"label": label, "data": data, "file_name": file_name, "mime": mime})

    import streamlit as st

    monkeypatch.setattr(st, "download_button", mock_download_button)
    md = "## 內容\n\n正常分析完成。\n"
    render_pdf_download(title="自訂標題報告", markdown_content=md, metadata={"tool": "test"})
    assert len(captured) == 1
    assert captured[0]["mime"] == "application/pdf"
    assert captured[0]["data"].startswith(b"%PDF-")


def test_pdf_graceful_degrade_when_fpdf_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test graceful degradation when fpdf2 is not available."""
    import fw_diag_tool.reporting.pdf_report as pdf_mod

    monkeypatch.setattr(pdf_mod, "_FPDF_AVAILABLE", False)

    # 1. build_pdf_report raises descriptive RuntimeError
    with pytest.raises(RuntimeError, match=r"pip install fw-diag-tool\[pdf\]"):
        build_pdf_report("標題", "內文")

    # 2. CLI shows warning instead of crashing
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.0001,1,0x50,0x00,Write,ACK\n",
        encoding="utf-8",
    )
    pdf_out = tmp_path / "no_fpdf.pdf"
    res = runner.invoke(app, ["i2c", "analyze", str(csv_file), "--pdf", str(pdf_out)])
    assert res.exit_code == 0
    assert (
        "警告：PDF 匯出需安裝 pdf 額外套件" in res.output
        or "Warning: PDF export requires 'pdf' extra" in res.output
    )
    assert not pdf_out.exists()


def test_render_pdf_download_gui_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GUI render_pdf_download helper in Streamlit context."""
    download_calls: list[dict[str, Any]] = []
    info_calls: list[str] = []

    def mock_download_button(label: str, data: bytes, file_name: str, mime: str, key: str) -> None:
        download_calls.append(
            {
                "label": label,
                "data": data,
                "file_name": file_name,
                "mime": mime,
                "key": key,
            }
        )

    def mock_info(msg: str) -> None:
        info_calls.append(msg)

    import streamlit as st

    monkeypatch.setattr(st, "download_button", mock_download_button)
    monkeypatch.setattr(st, "info", mock_info)

    # 1. Empty markdown is a no-op
    render_pdf_download("", protocol="I2C")
    assert len(download_calls) == 0

    # 2. Valid markdown produces download button
    md = "# I2C 測試報告\n\n正常分析。\n"
    render_pdf_download(md, protocol="I2C", filename_prefix="i2c_test")
    assert len(download_calls) == 1
    call = download_calls[0]
    assert "PDF" in call["label"]
    assert call["file_name"] == "i2c_test.pdf"
    assert call["mime"] == "application/pdf"
    assert call["data"].startswith(b"%PDF-")

    # 3. Graceful degradation in GUI when fpdf unavailable
    import fw_diag_tool.reporting.pdf_report as pdf_mod

    monkeypatch.setattr(pdf_mod, "_FPDF_AVAILABLE", False)
    render_pdf_download(md, protocol="I2C", filename_prefix="i2c_test2")
    assert len(info_calls) == 1
    assert "pip install fw-diag-tool[pdf]" in info_calls[0]
