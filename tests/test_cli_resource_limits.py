from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fw_diag_tool.cli import app


def test_i2c_cli_rejects_record_override_above_hard_ceiling(tmp_path: Path):
    trace = tmp_path / "trace.csv"
    trace.write_text("Time,Packet ID,Address,Data\n", encoding="utf-8")

    result = CliRunner().invoke(
        app, ["i2c", "analyze", str(trace), "--max-records", "250001"]
    )

    assert result.exit_code == 2
    assert "between 1 and 250000" in " ".join(result.output.split())


def test_i2c_cli_reports_record_limit_without_traceback(tmp_path: Path):
    trace = tmp_path / "trace.csv"
    trace.write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n"
        "0.0,1,0x50,0x00,Write,ACK\n"
        "0.1,2,0x50,0x01,Write,ACK\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["i2c", "analyze", str(trace), "--max-records", "1"])

    assert result.exit_code == 2
    assert "1-record safety limit" in " ".join(result.output.split())


def test_i2c_cli_normalizes_oversized_csv_field(tmp_path: Path):
    trace = tmp_path / "oversized-field.csv"
    trace.write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n"
        f"0.0,1,0x50,{'A' * 200_000},Write,ACK\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["i2c", "analyze", str(trace)])

    assert result.exit_code == 2
    assert "invalid CSV input" in result.output


def test_spi_cli_reports_record_limit_without_traceback(tmp_path: Path):
    trace = tmp_path / "spi.csv"
    trace.write_text(
        "Time,MOSI,MISO,Enable\n0.0,0x06,0x00,1\n0.1,0x05,0x02,1\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["spi", "analyze", str(trace), "--max-records", "1"])

    assert result.exit_code == 2
    assert "1-record safety limit" in " ".join(result.output.split())
