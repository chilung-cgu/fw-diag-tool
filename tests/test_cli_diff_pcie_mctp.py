"""Tests for CLI pcie diff and mctp diff subcommands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.mctp.models import ProtocolMode, ServerMgmtReport
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)

LSPCI_DEV_A = (
    "0000:01:00.0 Processing accelerators: Xilinx Corporation Device 7024\n"
    "00: ee 10 24 70 06 00 10 00 01 00 80 12 00 00 00 00\n"
    "10: 0c 00 00 f0 00 00 00 00 00 00 00 00 00 00 00 00\n"
    "20: 00 00 00 00 00 00 00 00 00 00 00 00 ee 10 24 70\n"
    "30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
)

LSPCI_DEV_B = (
    "0000:01:00.0 Ethernet controller: Intel Corporation Device 1572\n"
    "00: 86 80 72 15 06 00 10 00 01 00 00 02 00 00 00 00\n"
    "10: 0c 00 00 f0 00 00 00 00 00 00 00 00 00 00 00 00\n"
    "20: 00 00 00 00 00 00 00 00 00 00 00 00 86 80 72 15\n"
    "30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
)

MCTP_DUMP_A = "# Baseline MCTP dump\n01 08 0A C8 00 80 00 01\n81 1C 63 20 20 01 00 BF\n"

MCTP_DUMP_B = "# Candidate MCTP dump\n01 08 0A C8 00 80 00 01\n01 08 0A C9 00 80 00 02\n"


def _format_hex_dump(data: bytearray, bdf: str = "0000:01:00.0") -> str:
    lines = [f"{bdf} Test Device"]
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_bytes = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"{offset:02x}: {hex_bytes}")
    return "\n".join(lines) + "\n"


def test_cli_pcie_diff_missing_files(tmp_path: Path) -> None:
    runner = CliRunner()
    valid_file = tmp_path / "valid.txt"
    valid_file.write_text(LSPCI_DEV_A, encoding="utf-8")
    missing_file = tmp_path / "missing.txt"

    res1 = runner.invoke(app, ["pcie", "diff", str(missing_file), str(valid_file)])
    assert res1.exit_code == 1
    assert "Baseline 與 Candidate 檔案都必須存在" in res1.output

    res2 = runner.invoke(app, ["pcie", "diff", str(valid_file), str(missing_file)])
    assert res2.exit_code == 1
    assert "Baseline 與 Candidate 檔案都必須存在" in res2.output


def test_cli_pcie_diff_exception_handling(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text(LSPCI_DEV_A, encoding="utf-8")
    file_b.write_text(LSPCI_DEV_B, encoding="utf-8")

    with patch(
        "fw_diag_tool.cli.PCIeAnalyzer.parse_multi_lspci_text",
        side_effect=ValueError("Corrupted parser state"),
    ):
        res = runner.invoke(app, ["pcie", "diff", str(file_a), str(file_b)])
        assert res.exit_code == 2
        assert "PCIe diff 執行失敗" in res.output


def test_cli_pcie_diff_identical(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.txt"
    file_b = tmp_path / "cand.txt"
    file_a.write_text(LSPCI_DEV_A, encoding="utf-8")
    file_b.write_text(LSPCI_DEV_A, encoding="utf-8")

    res = runner.invoke(app, ["pcie", "diff", str(file_a), str(file_b)])
    assert res.exit_code == 0
    assert "PCIe Diff Summary" in res.output
    assert "完全一致" in res.output


def test_cli_pcie_diff_divergent(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.txt"
    file_b = tmp_path / "cand.txt"
    file_a.write_text(LSPCI_DEV_A, encoding="utf-8")
    file_b.write_text(LSPCI_DEV_B, encoding="utf-8")

    res = runner.invoke(app, ["pcie", "diff", str(file_a), str(file_b)])
    assert res.exit_code == 0
    assert "PCIe Diff Summary" in res.output
    assert "變更（Changed）" in res.output
    assert "對比結論" in res.output
    assert "Vendor ID 變更" in res.output or "0x10EE" in res.output


def test_cli_pcie_diff_aer_and_quality_issues(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.txt"
    file_b = tmp_path / "cand.txt"
    file_a.write_text(LSPCI_DEV_A, encoding="utf-8")
    file_b.write_text(LSPCI_DEV_B, encoding="utf-8")

    cfg_a = PCIeConfigSpace(
        raw_data=b"\x00" * 256,
        vendor_id=0x10EE,
        device_id=0x7024,
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=PCIeLinkInfo(current_speed_str="8.0 GT/s", current_width=8, is_degraded=False),
        aer_analysis=AERAnalysisResult(
            offset=0x100,
            uncorr_status_raw=0,
            uncorr_mask_raw=0,
            uncorr_severity_raw=0,
            corr_status_raw=0,
            corr_mask_raw=0,
            cap_control_raw=0,
            header_log_raw=[],
            uncorr_errors=[
                AERUncorrectableError(
                    bit_pos=14,
                    name="Completion Timeout",
                    short_code="CTO",
                    is_active=True,
                    is_masked=False,
                    severity="Fatal",
                )
            ],
            corr_errors=[],
        ),
        data_quality_issues=["AER truncated"],
    )

    cfg_b = PCIeConfigSpace(
        raw_data=b"\x00" * 256,
        vendor_id=0x10EE,
        device_id=0x7024,
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=PCIeLinkInfo(current_speed_str="2.5 GT/s", current_width=1, is_degraded=True),
        aer_analysis=AERAnalysisResult(
            offset=0x100,
            uncorr_status_raw=0,
            uncorr_mask_raw=0,
            uncorr_severity_raw=0,
            corr_status_raw=0,
            corr_mask_raw=0,
            cap_control_raw=0,
            header_log_raw=[],
            uncorr_errors=[],
            corr_errors=[
                AERCorrectableError(
                    bit_pos=0,
                    name="Receiver Error",
                    short_code="RCVR",
                    is_active=True,
                    is_masked=False,
                )
            ],
        ),
        data_quality_issues=["Command MSE is 0"],
    )

    with patch(
        "fw_diag_tool.cli.PCIeAnalyzer.parse_multi_lspci_text", side_effect=[[cfg_a], [cfg_b]]
    ):
        res = runner.invoke(app, ["pcie", "diff", str(file_a), str(file_b)])
        assert res.exit_code == 0
        assert "新增 AER 錯誤" in res.output
        assert "已修復 AER 錯誤" in res.output
        assert "Receiver Error" in res.output
        assert "Completion Timeout" in res.output
        assert "新增資料品質問題" in res.output
        assert "已修復資料品質問題" in res.output
        assert "降級狀態變更" in res.output


def test_cli_mctp_diff_missing_files(tmp_path: Path) -> None:
    runner = CliRunner()
    valid_file = tmp_path / "valid.hex"
    valid_file.write_text(MCTP_DUMP_A, encoding="utf-8")
    missing_file = tmp_path / "missing.hex"

    res1 = runner.invoke(app, ["mctp", "diff", str(missing_file), str(valid_file)])
    assert res1.exit_code == 1
    assert "Baseline 與 Candidate 檔案都必須存在" in res1.output

    res2 = runner.invoke(app, ["mctp", "diff", str(valid_file), str(missing_file)])
    assert res2.exit_code == 1
    assert "Baseline 與 Candidate 檔案都必須存在" in res2.output


def test_cli_mctp_diff_identical(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.hex"
    file_b = tmp_path / "cand.hex"
    file_a.write_text(MCTP_DUMP_A, encoding="utf-8")
    file_b.write_text(MCTP_DUMP_A, encoding="utf-8")

    res = runner.invoke(app, ["mctp", "diff", str(file_a), str(file_b)])
    assert res.exit_code == 0
    assert "MCTP Diff Summary" in res.output
    assert "完全一致" in res.output


def test_cli_mctp_diff_divergent(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.hex"
    file_b = tmp_path / "cand.hex"
    file_a.write_text(MCTP_DUMP_A, encoding="utf-8")
    file_b.write_text(MCTP_DUMP_B, encoding="utf-8")

    res = runner.invoke(app, ["mctp", "diff", str(file_a), str(file_b)])
    assert res.exit_code == 0
    assert "MCTP Diff Summary" in res.output
    assert "MCTP 訊息數" in res.output
    assert "對比結論" in res.output


def test_cli_mctp_diff_protocol_option(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.hex"
    file_b = tmp_path / "cand.hex"
    file_a.write_text(MCTP_DUMP_A, encoding="utf-8")
    file_b.write_text(MCTP_DUMP_B, encoding="utf-8")

    res = runner.invoke(app, ["mctp", "diff", str(file_a), str(file_b), "-p", "mctp"])
    assert res.exit_code == 0
    assert "MCTP Diff Summary" in res.output
    assert "mctp" in res.output


def test_cli_mctp_diff_invalid_protocol(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.hex"
    file_b = tmp_path / "cand.hex"
    file_a.write_text(MCTP_DUMP_A, encoding="utf-8")
    file_b.write_text(MCTP_DUMP_B, encoding="utf-8")

    res = runner.invoke(app, ["mctp", "diff", str(file_a), str(file_b), "-p", "invalid_proto"])
    assert res.exit_code == 2
    assert "MCTP diff 執行失敗" in res.output


def test_cli_mctp_diff_errors_and_warnings(tmp_path: Path) -> None:
    runner = CliRunner()
    file_a = tmp_path / "base.hex"
    file_b = tmp_path / "cand.hex"
    file_a.write_text(MCTP_DUMP_A, encoding="utf-8")
    file_b.write_text(MCTP_DUMP_B, encoding="utf-8")

    rep_a = ServerMgmtReport(
        errors=["Checksum Error A"],
        warnings=["Timeout Warning A"],
        protocol_mode=ProtocolMode.AUTO,
    )
    rep_b = ServerMgmtReport(
        errors=["Checksum Error B"],
        warnings=["Timeout Warning B"],
        protocol_mode=ProtocolMode.AUTO,
    )

    with patch("fw_diag_tool.cli.ServerMgmtParser.parse_text_dump", side_effect=[rep_a, rep_b]):
        res = runner.invoke(app, ["mctp", "diff", str(file_a), str(file_b)])
        assert res.exit_code == 0
        assert "新增錯誤" in res.output
        assert "Checksum Error B" in res.output
        assert "已修復錯誤" in res.output
        assert "Checksum Error A" in res.output
        assert "新增警告" in res.output
        assert "Timeout Warning B" in res.output
        assert "已修復警告" in res.output
        assert "Timeout Warning A" in res.output
