"""Tests for SPI and UART Before/After protocol diff engines and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.spi.diff import SPIDiffEngine, SPIDiffResult
from fw_diag_tool.spi.models import (
    SPIDiagnosticIssue,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
)
from fw_diag_tool.uart.diff import UARTDiffEngine, UARTDiffResult
from fw_diag_tool.uart.models import (
    ARMHardFaultReport,
    CallTraceFrame,
    CrashType,
    KernelPanicReport,
    UARTReport,
)


def _make_spi_report(
    anomalies_titles: list[str],
    total_tx: int = 10,
    chip: str | None = "Winbond W25Q128",
) -> SPIReport:
    anomalies = [
        SPIDiagnosticIssue(
            code=f"SPI_ERR_{i}",
            title=title,
            severity=SPISeverity.ERROR,
            timestamp=float(i),
            transaction_id=i,
            description=f"Description for {title}",
            root_cause_guide="Check flash datasheet",
        )
        for i, title in enumerate(anomalies_titles)
    ]
    summary = SPIReportSummary(
        total_transactions=total_tx,
        read_count=total_tx // 2,
        write_count=total_tx // 4,
        erase_count=1,
        anomaly_count=len(anomalies),
        detected_flash_chip=chip,
    )
    return SPIReport(summary=summary, anomalies=anomalies)


def test_spi_diff_identical():
    rep1 = _make_spi_report(["Write Without WEL", "Sector Erase Timeout"], total_tx=20)
    rep2 = _make_spi_report(["Write Without WEL", "Sector Erase Timeout"], total_tx=20)

    result = SPIDiffEngine.compare(rep1, rep2)
    assert isinstance(result, SPIDiffResult)
    assert result.is_identical is True
    assert result.new_anomalies == []
    assert result.resolved_anomalies == []
    assert result.common_anomalies == ["Sector Erase Timeout", "Write Without WEL"]
    assert result.transaction_count_delta == 0
    assert result.chip_changed is False
    assert "完全一致" in result.summary


def test_spi_diff_different():
    base = _make_spi_report(
        ["Write Without WEL", "Page Boundary Crossing"],
        total_tx=10,
        chip="Winbond W25Q128",
    )
    cand = _make_spi_report(
        ["Page Boundary Crossing", "Deep Power Down Read"],
        total_tx=15,
        chip="Macronix MX25L128",
    )

    result = SPIDiffEngine.compare(base, cand)
    assert result.is_identical is False
    assert result.new_anomalies == ["Deep Power Down Read"]
    assert result.resolved_anomalies == ["Write Without WEL"]
    assert result.common_anomalies == ["Page Boundary Crossing"]
    assert result.transaction_count_delta == 5
    assert result.chip_changed is True
    assert result.baseline_detected_chip == "Winbond W25Q128"
    assert result.candidate_detected_chip == "Macronix MX25L128"
    assert "交易數變化 +5" in result.summary
    assert "新增 1 項異常" in result.summary
    assert "修復 1 項異常" in result.summary


def test_spi_diff_type_error():
    with pytest.raises(TypeError):
        SPIDiffEngine.compare("not a report", _make_spi_report([]))  # type: ignore[arg-type]


def test_uart_diff_identical():
    panic = KernelPanicReport(
        architecture="x86_64",
        panic_reason="unable to handle page fault",
        faulting_ip="0xffffffff81001234",
        faulting_func="nvme_pci_complete_rq",
        faulting_address="0x0000000000000010",
        call_trace=[
            CallTraceFrame(index=0, function_name="nvme_pci_complete_rq", offset="0x38"),
            CallTraceFrame(index=1, function_name="blk_mq_complete_request", offset="0x24"),
        ],
    )
    rep1 = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="Kernel Panic",
        kernel_panic=panic,
    )
    rep2 = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="Kernel Panic",
        kernel_panic=panic,
    )

    result = UARTDiffEngine.compare(rep1, rep2)
    assert isinstance(result, UARTDiffResult)
    assert result.is_identical is True
    assert result.crash_type_changed is False
    assert result.fault_address_changed is False
    assert result.new_symbols == []
    assert result.resolved_symbols == []
    assert result.baseline_fault_address == "0x0000000000000010"
    assert "完全一致" in result.summary


def test_uart_diff_different_crash_type():
    panic = KernelPanicReport(
        architecture="x86_64",
        panic_reason="unable to handle page fault",
        faulting_address="0x0000000000000010",
    )
    rep1 = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="Kernel Panic",
        kernel_panic=panic,
    )
    hf = ARMHardFaultReport(
        pc_faulting=0x08001234,
        symbolicated_pc="main+0x12",
        fault_flags=["DIVBYZERO"],
    )
    rep2 = UARTReport(
        crash_type=CrashType.ARM_HARDFAULT,
        summary_title="ARM HardFault",
        arm_hardfault=hf,
    )

    result = UARTDiffEngine.compare(rep1, rep2)
    assert result.is_identical is False
    assert result.crash_type_changed is True
    assert result.fault_address_changed is True
    assert result.baseline_crash_type == CrashType.KERNEL_PANIC.value
    assert result.candidate_crash_type == CrashType.ARM_HARDFAULT.value
    assert "main+0x12" in result.new_symbols


def test_uart_diff_symbols_and_fault_address():
    panic1 = KernelPanicReport(
        architecture="x86_64",
        panic_reason="unable to handle page fault",
        faulting_address="0x10",
        faulting_func="nvme_pci_complete_rq",
        call_trace=[
            CallTraceFrame(index=0, function_name="nvme_pci_complete_rq", offset="0x38"),
            CallTraceFrame(index=1, function_name="old_driver_func", offset="0x10"),
        ],
    )
    panic2 = KernelPanicReport(
        architecture="x86_64",
        panic_reason="unable to handle page fault",
        faulting_address="0x20",
        faulting_func="nvme_pci_complete_rq",
        call_trace=[
            CallTraceFrame(index=0, function_name="nvme_pci_complete_rq", offset="0x38"),
            CallTraceFrame(index=1, function_name="new_driver_func", offset="0x20"),
        ],
    )
    rep1 = UARTReport(crash_type=CrashType.KERNEL_PANIC, summary_title="Panic 1", kernel_panic=panic1)
    rep2 = UARTReport(crash_type=CrashType.KERNEL_PANIC, summary_title="Panic 2", kernel_panic=panic2)

    result = UARTDiffEngine.compare(rep1, rep2)
    assert result.is_identical is False
    assert result.crash_type_changed is False
    assert result.fault_address_changed is True
    assert result.baseline_fault_address == "0x10"
    assert result.candidate_fault_address == "0x20"
    assert result.new_symbols == ["new_driver_func"]
    assert result.resolved_symbols == ["old_driver_func"]
    assert "nvme_pci_complete_rq" in result.common_symbols


def test_uart_diff_type_error():
    with pytest.raises(TypeError):
        UARTDiffEngine.compare("invalid", "invalid")  # type: ignore[arg-type]


def test_cli_spi_diff(tmp_path: Path):
    runner = CliRunner()
    csv_baseline = """Time [s],MOSI,MISO,Enable
0.0001,0x9F,0x00,0
0.0002,0x00,0xEF,0
0.0003,0x00,0x40,0
0.0004,0x00,0x18,0
0.0005,0x00,0x00,1
0.0010,0x06,0x00,0
0.0011,0x00,0x00,1
"""
    csv_candidate = """Time [s],MOSI,MISO,Enable
0.0001,0x9F,0x00,0
0.0002,0x00,0xEF,0
0.0003,0x00,0x40,0
0.0004,0x00,0x18,0
0.0005,0x00,0x00,1
0.0010,0x02,0x00,0
0.0011,0x00,0x00,0
0.0012,0x10,0x00,0
0.0013,0x00,0x00,0
0.0014,0xAA,0x00,0
0.0015,0x00,0x00,1
"""
    base_file = tmp_path / "spi_base.csv"
    cand_file = tmp_path / "spi_cand.csv"
    base_file.write_text(csv_baseline, encoding="utf-8")
    cand_file.write_text(csv_candidate, encoding="utf-8")

    # Compare different
    res = runner.invoke(app, ["spi", "diff", str(base_file), str(cand_file)])
    assert res.exit_code == 0
    assert "SPI Before/After" in res.output

    # Compare identical
    res_id = runner.invoke(app, ["spi", "diff", str(base_file), str(base_file)])
    assert res_id.exit_code == 0
    assert "完全一致" in res_id.output

    # Missing file
    res_err = runner.invoke(app, ["spi", "diff", str(base_file), str(tmp_path / "non_existent.csv")])
    assert res_err.exit_code == 1


def test_cli_uart_diff(tmp_path: Path):
    runner = CliRunner()
    log1 = """BUG: unable to handle page fault for address: 0000000000000010
RIP: 0010:func_a+0x38/0x120
Call Trace:
 <TASK>
 [ffff888100123450] func_b+0x24/0x50
 </TASK>"""

    log2 = """BUG: unable to handle page fault for address: 0000000000000020
RIP: 0010:func_a+0x38/0x120
Call Trace:
 <TASK>
 [ffff888100123450] func_c+0x24/0x50
 </TASK>"""

    log1_file = tmp_path / "log1.txt"
    log2_file = tmp_path / "log2.txt"
    log1_file.write_text(log1, encoding="utf-8")
    log2_file.write_text(log2, encoding="utf-8")

    # Compare different
    res = runner.invoke(app, ["uart", "diff", str(log1_file), str(log2_file)])
    assert res.exit_code == 0
    assert "UART Crash Before/After" in res.output
    assert "func_c" in res.output

    # Compare identical
    res_id = runner.invoke(app, ["uart", "diff", str(log1_file), str(log1_file)])
    assert res_id.exit_code == 0
    assert "完全一致" in res_id.output

    # Missing file
    res_err = runner.invoke(app, ["uart", "diff", str(log1_file), str(tmp_path / "missing.txt")])
    assert res_err.exit_code == 1

