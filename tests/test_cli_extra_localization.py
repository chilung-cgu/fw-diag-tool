from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fw_diag_tool.cli import app


def test_cli_waveform_diff_is_chinese_first_and_keeps_canonical_tokens(tmp_path: Path) -> None:
    golden = tmp_path / "golden.csv"
    failing = tmp_path / "failing.csv"
    golden.write_text(
        "Time, Packet ID, Address, Data, Read/Write, ACK/NAK\n0.001,0,0x50,,Write,ACK\n",
        encoding="utf-8",
    )
    failing.write_text(
        "Time, Packet ID, Address, Data, Read/Write, ACK/NAK\n0.001,0,0x50,,Write,NAK\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["i2c", "diff", str(golden), str(failing)])

    assert result.exit_code == 0
    output = result.output.lstrip()
    assert output.startswith("找到 1 個分歧點")
    assert "Divergence at Tx #1" in output
    assert "類型（Type）" in output
    assert "NACK_MISMATCH" in output
    assert "Found 1 divergence point(s)." in output
    assert "Transaction #1." in output


def test_cli_fuzz_is_chinese_first_and_keeps_canonical_summary() -> None:
    result = CliRunner().invoke(app, ["fuzz", "--seeds", "2"])

    assert result.exit_code == 0
    output = result.output.lstrip()
    assert output.startswith("模糊測試完成：")
    assert "Fuzzing:" in output
    assert "passed" in output
