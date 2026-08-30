from __future__ import annotations

from types import SimpleNamespace

import pytest

from fw_diag_tool.gui.pages.protocol_diff_ui import (
    _analyze_input,
    _diff_lists,
    format_protocol_diff_markdown,
)


def _result(protocol: str = "I2C") -> SimpleNamespace:
    if protocol == "UART":
        return SimpleNamespace(
            summary="UART 對比結果：新增 1 個符號。",
            new_symbols=["candidate_func"],
            resolved_symbols=["baseline_func"],
            common_symbols=["shared_func"],
            crash_type_changed=True,
            fault_address_changed=False,
            baseline_crash_type="kernel_panic",
            candidate_crash_type="arm_hardfault",
            baseline_fault_address="0x10",
            candidate_fault_address="0x10",
            is_identical=False,
        )
    return SimpleNamespace(
        summary="I2C 對比結果：交易數變化 +2。",
        new_anomalies=["New NACK"],
        resolved_anomalies=["Old NACK"],
        common_anomalies=["Clock Stretching"],
        address_changes=["交易 #1: 0x20 -> 0x21"],
        baseline_transaction_count=3,
        candidate_transaction_count=5,
        transaction_count_delta=2,
        is_identical=False,
    )


def test_i2c_markdown_contains_summary_metrics_and_lists() -> None:
    report = format_protocol_diff_markdown("I2C", _result())
    assert "# I2C A/B 對比報告" in report
    assert "交易數變化：+2" in report
    assert "- New NACK" in report
    assert "- Old NACK" in report
    assert "交易 #1: 0x20 -> 0x21" in report


def test_uart_markdown_uses_symbol_sections_and_fault_addresses() -> None:
    report = format_protocol_diff_markdown("UART", _result("UART"))
    assert "崩潰類型：kernel_panic -> arm_hardfault" in report
    assert "故障位址：0x10 -> 0x10" in report
    assert "- candidate_func" in report
    assert "- baseline_func" in report


def test_diff_lists_selects_uart_symbols() -> None:
    result = _result("UART")
    assert _diff_lists("UART", result) == (
        ["candidate_func"],
        ["baseline_func"],
        ["shared_func"],
    )


def test_diff_lists_selects_protocol_anomalies() -> None:
    result = _result()
    assert _diff_lists("SPI", result) == (
        ["New NACK"],
        ["Old NACK"],
        ["Clock Stretching"],
    )


def test_analyze_input_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="不可為空"):
        _analyze_input("UART", "  ")


def test_analyze_input_parses_uart_text() -> None:
    report = _analyze_input("UART", "normal boot output")
    assert report.crash_type.value == "Generic Serial Log / Boot Trace"
