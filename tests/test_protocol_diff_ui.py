from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fw_diag_tool.gui.pages.protocol_diff_ui import (
    _analyze_input,
    _compare,
    _diff_lists,
    format_protocol_diff_json,
    format_protocol_diff_markdown,
)
from fw_diag_tool.resources import load_pcie_lspci_sample


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
    if protocol == "PCIe":
        return SimpleNamespace(
            summary="PCIe 對比結果：Link 狀態變更。",
            new_aer_errors=["Unsupported Request"],
            resolved_aer_errors=["Bad TLP"],
            common_aer_errors=["Receiver Error"],
            vendor_changed=False,
            device_changed=False,
            link_degradation_changed=True,
            baseline_link_summary="Gen3 x8",
            candidate_link_summary="Gen3 x4",
            is_identical=False,
        )
    if protocol == "MCTP":
        return SimpleNamespace(
            summary="MCTP/IPMB 對比結果：訊息數變化 +3。",
            new_errors=["line 2: bad checksum"],
            resolved_errors=["line 1: timeout"],
            common_errors=["line 3: unknown type"],
            message_count_delta=3,
            protocol_mode_changed=True,
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


def test_analyze_input_parses_pcie_text() -> None:
    lspci_text = load_pcie_lspci_sample()
    report = _analyze_input("PCIe", lspci_text)
    assert report.vendor_id == 0x10EE
    assert report.device_id == 0x7024


def test_analyze_input_parses_mctp_text() -> None:
    hex_text = "01 08 00 C0 01"
    report = _analyze_input("MCTP", hex_text)
    assert len(report.mctp_messages) >= 1


def test_compare_pcie_and_mctp() -> None:
    lspci_text = load_pcie_lspci_sample()
    pcie_dev = _analyze_input("PCIe", lspci_text)
    pcie_res = _compare("PCIe", pcie_dev, pcie_dev)
    assert pcie_res.is_identical is True

    hex_text = "01 08 00 C0 01"
    mctp_rep = _analyze_input("MCTP", hex_text)
    mctp_res = _compare("MCTP", mctp_rep, mctp_rep)
    assert mctp_res.is_identical is True


def test_diff_lists_selects_pcie_aer_errors() -> None:
    result = _result("PCIe")
    assert _diff_lists("PCIe", result) == (
        ["Unsupported Request"],
        ["Bad TLP"],
        ["Receiver Error"],
    )


def test_diff_lists_selects_mctp_errors() -> None:
    result = _result("MCTP")
    assert _diff_lists("MCTP", result) == (
        ["line 2: bad checksum"],
        ["line 1: timeout"],
        ["line 3: unknown type"],
    )


def test_pcie_markdown_contains_link_metrics() -> None:
    report = format_protocol_diff_markdown("PCIe", _result("PCIe"))
    assert "# PCIe A/B 對比報告" in report
    assert "Vendor 變更：False" in report
    assert "Device 變更：False" in report
    assert "Link 降級變更：True" in report
    assert "Baseline Link：Gen3 x8" in report
    assert "Candidate Link：Gen3 x4" in report
    assert "- Unsupported Request" in report
    assert "- Bad TLP" in report
    assert "- Receiver Error" in report


def test_mctp_markdown_contains_message_delta() -> None:
    report = format_protocol_diff_markdown("MCTP", _result("MCTP"))
    assert "# MCTP A/B 對比報告" in report
    assert "訊息數變化：+3" in report
    assert "協定模式變更：True" in report
    assert "- line 2: bad checksum" in report
    assert "- line 1: timeout" in report
    assert "- line 3: unknown type" in report


def test_format_protocol_diff_json_structure() -> None:
    json_report = format_protocol_diff_json("I2C", _result("I2C"), timestamp="2026-08-30T12:00:00Z")
    data = json.loads(json_report)
    assert data["protocol"] == "I2C"
    assert data["timestamp"] == "2026-08-30T12:00:00Z"
    assert "baseline_summary" in data
    assert "candidate_summary" in data
    assert "diff" in data
    assert data["diff"]["new_anomalies"] == ["New NACK"]
    assert data["diff"]["resolved_anomalies"] == ["Old NACK"]
    assert data["diff"]["common_anomalies"] == ["Clock Stretching"]


def test_protocol_diff_ui_render_and_sample_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages import protocol_diff_ui

    # Mock button clicks and session state
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(st, "selectbox", lambda *args, **kwargs: "I2C")
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "text_area", lambda *args, **kwargs: "")
    monkeypatch.setattr(st, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "info", lambda *args, **kwargs: None)

    st.session_state.clear()
    protocol_diff_ui.render()

    assert "protocol_diff_baseline_text" in st.session_state
    assert "protocol_diff_candidate_text" in st.session_state
    assert st.session_state["protocol_diff_sample_active"] is True
