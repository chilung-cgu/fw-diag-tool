"""Tests for Batch processing and HTML report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.gui.shared import render_html_download
from fw_diag_tool.reporting.batch import (
    _detect_protocol_for_file,
    batch_analyze_directory,
)
from fw_diag_tool.reporting.html_report import (
    convert_markdown_to_html,
    write_html_report,
)

runner = CliRunner()


def test_convert_markdown_to_html_basic() -> None:
    """Test basic Markdown to HTML conversion with dark theme CSS and structure."""
    md = "# 診斷報告標題\n\n> 摘要：正常\n\n- 項目 1\n- 項目 2\n\n`0x50` 正常\n"
    html_doc = convert_markdown_to_html(md, title="測試診斷報告", tool_version="1.1.1")
    assert "<!DOCTYPE html>" in html_doc
    assert "<title>測試診斷報告</title>" in html_doc
    assert "#0f172a" in html_doc  # dark theme bg
    assert "#0ea5e9" in html_doc  # primary accent
    assert "<h1>⚡ 測試診斷報告</h1>" in html_doc
    assert "<h1>診斷報告標題</h1>" in html_doc
    assert "<blockquote><p>摘要：正常</p></blockquote>" in html_doc
    assert "<ul>" in html_doc
    assert "<li>項目 1</li>" in html_doc
    assert "<code>0x50</code>" in html_doc
    assert "fw-diag-tool v1.1.1" in html_doc


def test_html_report_table_and_code_blocks(tmp_path: Path) -> None:
    """Test HTML conversion of markdown tables, fenced code blocks, badges, and file output."""
    md = (
        "## 時序表\n\n"
        "| 項目 | 數值 | 狀態 |\n"
        "|:---|:---:|---:|\n"
        "| 頻率 | 100 kHz | [OK] |\n"
        "| 錯誤 | NACK | [ERROR] |\n\n"
        "```python\nprint('hello')\n```\n"
    )
    out_file = tmp_path / "test_report.html"
    res_path = write_html_report(md, out_file, title="進階測試")
    assert res_path == out_file
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "<table" in content
    assert "<th>項目</th>" in content
    assert 'style="text-align: center"' in content
    assert "badge badge-success" in content
    assert "badge badge-error" in content
    assert '<pre><code class="language-python">' in content
    assert "print(&#x27;hello&#x27;)" in content or "print('hello')" in content


def test_detect_protocol_for_file(tmp_path: Path) -> None:
    """Test protocol detection for various file types and contents."""
    # I2C CSV
    i2c_csv = tmp_path / "i2c_trace.csv"
    i2c_csv.write_text("Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,1,0x50,0x00,W,ACK\n", encoding="utf-8")
    assert _detect_protocol_for_file(i2c_csv) == "i2c"

    # SPI CSV
    spi_csv = tmp_path / "spi_trace.csv"
    spi_csv.write_text("Time,MOSI,MISO,CS,Enable\n0.001,0x9F,0x00,0,1\n", encoding="utf-8")
    assert _detect_protocol_for_file(spi_csv) == "spi"

    # UART Panic Log
    uart_log = tmp_path / "crash.log"
    uart_log.write_text("Kernel panic - not syncing: Fatal exception\nCPU: 0 PID: 1\n", encoding="utf-8")
    assert _detect_protocol_for_file(uart_log) == "uart"

    # PCIe text
    pcie_txt = tmp_path / "pcie.txt"
    pcie_txt.write_text("00:1f.0 Bridge: Intel Device\n00: 86 80 01 02\n", encoding="utf-8")
    assert _detect_protocol_for_file(pcie_txt) == "pcie"


def test_batch_analyze_directory(tmp_path: Path) -> None:
    """Test scanning a directory and executing multi-protocol batch analysis with all export formats."""
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    output_dir = tmp_path / "outputs"

    # Create sample files
    (input_dir / "i2c_ok.csv").write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,1,0x50,0x00,Write,ACK\n",
        encoding="utf-8",
    )
    (input_dir / "uart_crash.log").write_text(
        "Kernel panic - not syncing: Fatal exception in interrupt\nCPU: 0 PID: 1 Comm: swapper/0\n",
        encoding="utf-8",
    )
    (input_dir / "pcie_aer.log").write_text(
        "PCIe Bus Error: severity=Fatal, type=Transaction Layer, id=0020(Receiver ID)\n",
        encoding="utf-8",
    )

    entries = batch_analyze_directory(
        input_dir,
        output_dir=output_dir,
        formats="all",
    )
    assert len(entries) == 3
    assert output_dir.exists()

    # Check manifest JSON
    manifest_file = output_dir / "batch_manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["total"] == 3
    assert manifest_data["schema_version"] == "1.0"

    # Check exported files for i2c_ok
    assert (output_dir / "i2c_ok_report.md").exists()
    assert (output_dir / "i2c_ok_report.html").exists()
    assert (output_dir / "i2c_ok.sarif.json").exists()

    # Check exported files for uart_crash
    assert (output_dir / "uart_crash_report.html").exists()


def test_batch_analyze_protocol_filter(tmp_path: Path) -> None:
    """Test protocol filtering in batch analysis."""
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "i2c_ok.csv").write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,1,0x50,0x00,Write,ACK\n",
        encoding="utf-8",
    )
    (input_dir / "uart_crash.log").write_text(
        "Kernel panic - not syncing: Fatal exception in interrupt\n",
        encoding="utf-8",
    )

    entries = batch_analyze_directory(input_dir, protocols=["i2c"])
    assert len(entries) == 1
    assert entries[0]["protocol"] == "i2c"


def test_batch_cli_command(tmp_path: Path) -> None:
    """Test the batch CLI command with various flags."""
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    output_dir = tmp_path / "outputs"
    (input_dir / "i2c_test.csv").write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,1,0x50,0x00,Write,ACK\n",
        encoding="utf-8",
    )

    # Valid batch run
    res = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--format",
            "all",
        ],
    )
    assert res.exit_code == 0
    assert "批次分析結果摘要" in res.output
    assert "I2C_TEST.CSV" in res.output or "i2c_test.csv" in res.output
    assert (output_dir / "i2c_test_report.html").exists()

    # Non-existent directory should exit with code 1
    res_err = runner.invoke(app, ["batch", str(tmp_path / "nonexistent")])
    assert res_err.exit_code == 1
    assert "錯誤" in res_err.output or "Error" in res_err.output


def test_render_html_download_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GUI render_html_download helper function."""
    download_calls: list[dict[str, Any]] = []

    def mock_download_button(label: str, data: str, file_name: str, mime: str, key: str) -> None:
        download_calls.append(
            {
                "label": label,
                "data": data,
                "file_name": file_name,
                "mime": mime,
                "key": key,
            }
        )

    import streamlit as st
    monkeypatch.setattr(st, "download_button", mock_download_button)

    # Empty markdown should be a no-op
    render_html_download("", protocol="I2C")
    assert len(download_calls) == 0

    # Valid markdown should invoke download_button with HTML content
    md_sample = "# 測試報告\n\n內容摘要\n"
    render_html_download(md_sample, protocol="I2C", filename_prefix="i2c_report")
    assert len(download_calls) == 1
    call = download_calls[0]
    assert "HTML" in call["label"]
    assert call["file_name"] == "i2c_report.html"
    assert call["mime"] == "text/html"
    assert "<!DOCTYPE html>" in call["data"]
    assert "#0f172a" in call["data"]
