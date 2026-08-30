from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.shared import analyze_i2c_input, analyze_spi_input
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.resources import (
    _I2C_SAMPLE_FILES,
    _MCTP_SAMPLE_FILES,
    _UART_SAMPLE_FILES,
    load_i2c_sample,
    load_mctp_sample,
    load_pcie_dmesg_sample,
    load_pcie_lspci_sample,
    load_spi_sample,
    load_uart_sample,
    load_waveform_diff_samples,
)
from fw_diag_tool.uart.parser import UARTCrashParser


def test_resources_load_i2c_samples() -> None:
    for key in _I2C_SAMPLE_FILES:
        sample = load_i2c_sample(key)
        assert isinstance(sample, str)
        assert len(sample.strip()) > 0

    with pytest.raises(ValueError, match="unknown I2C sample"):
        load_i2c_sample("non-existent-sample")


def test_resources_load_spi_sample() -> None:
    sample = load_spi_sample()
    assert isinstance(sample, str)
    assert "Time" in sample
    assert "MOSI" in sample


def test_resources_load_waveform_diff_samples() -> None:
    golden, failing = load_waveform_diff_samples()
    assert isinstance(golden, str) and len(golden.strip()) > 0
    assert isinstance(failing, str) and len(failing.strip()) > 0


def test_resources_load_pcie_samples() -> None:
    dmesg = load_pcie_dmesg_sample()
    assert isinstance(dmesg, str) and len(dmesg.strip()) > 0
    assert "AER" in dmesg

    lspci = load_pcie_lspci_sample()
    assert isinstance(lspci, str) and len(lspci.strip()) > 0
    assert "00:" in lspci


def test_resources_load_uart_samples() -> None:
    for key in _UART_SAMPLE_FILES:
        sample = load_uart_sample(key)
        assert isinstance(sample, str)
        assert len(sample.strip()) > 0

    with pytest.raises(ValueError, match="unknown UART sample"):
        load_uart_sample("invalid_uart_sample")


def test_resources_load_mctp_samples() -> None:
    for key in _MCTP_SAMPLE_FILES:
        sample = load_mctp_sample(key)
        assert isinstance(sample, str)
        assert len(sample.strip()) > 0

    with pytest.raises(ValueError, match="unknown MCTP sample"):
        load_mctp_sample("invalid_mctp_sample")


def test_parsers_successfully_parse_sample_data() -> None:
    # 1. I2C decoded and NACK
    i2c_decoded = load_i2c_sample("builtin-decoded")
    i2c_rep, _ = analyze_i2c_input(i2c_decoded, "decoded_csv", 25.0)
    assert i2c_rep.total_transactions > 0

    i2c_nack = load_i2c_sample("address-nack")
    i2c_nack_rep, _ = analyze_i2c_input(i2c_nack, "decoded_csv", 25.0)
    assert len(i2c_nack_rep.issues) >= 1

    # 2. SPI
    spi_sample = load_spi_sample()
    spi_rep = analyze_spi_input(spi_sample)
    assert spi_rep.summary.total_transactions > 0

    # 3. PCIe
    dmesg_sample = load_pcie_dmesg_sample()
    events = PCIeAnalyzer.parse_dmesg_aer(dmesg_sample)
    assert len(events) >= 1

    lspci_sample = load_pcie_lspci_sample()
    devices = PCIeAnalyzer.parse_multi_lspci_text(lspci_sample)
    assert len(devices) >= 1

    # 4. UART
    kp_sample = load_uart_sample("kernel-panic")
    kp_rep = UARTCrashParser.parse_log_text(kp_sample)
    assert kp_rep.crash_type.name == "KERNEL_PANIC"

    hf_sample = load_uart_sample("hardfault")
    hf_rep = UARTCrashParser.parse_log_text(hf_sample)
    assert hf_rep.crash_type.name == "ARM_HARDFAULT"

    # 5. MCTP
    mctp_sample = load_mctp_sample("mctp-pldm")
    mctp_rep = ServerMgmtParser.parse_text_dump(mctp_sample)
    assert mctp_rep.total_frames >= 1

    ipmb_sample = load_mctp_sample("ipmb")
    ipmb_rep = ServerMgmtParser.parse_text_dump(ipmb_sample)
    assert ipmb_rep.total_frames >= 1


def _correlation_app() -> None:
    from fw_diag_tool.gui.pages.correlation_ui import render

    render()


def _mctp_app() -> None:
    from fw_diag_tool.gui.pages.mctp_ui import render

    render()


def _uart_app() -> None:
    from fw_diag_tool.gui.pages.uart_ui import render

    render()


def test_gui_correlation_page_one_click_three_protocol_examples() -> None:
    at = AppTest.from_function(_correlation_app, default_timeout=30).run()
    next(button for button in at.button if button.label == "📋 載入三協定範例資料").click().run()

    assert not at.exception
    assert at.session_state["corr_i2c_text"] == load_i2c_sample("address-nack")
    assert at.session_state["corr_spi_text"] == load_spi_sample()
    assert at.session_state["corr_uart_text"] == load_uart_sample("kernel-panic")
    assert any("跨協定時間線" in s.value for s in at.subheader)
    assert any(metric.label == "總事件數" for metric in at.metric)


def test_gui_correlation_individual_sample_buttons() -> None:
    at = AppTest.from_function(_correlation_app, default_timeout=30).run()
    next(button for button in at.button if button.label == "📋 載入 I2C 範例").click().run()
    assert at.session_state["corr_i2c_text"] == load_i2c_sample("address-nack")

    next(button for button in at.button if button.label == "📋 載入 SPI 範例").click().run()
    assert at.session_state["corr_spi_text"] == load_spi_sample()

    next(button for button in at.button if button.label == "📋 載入 UART 範例").click().run()
    assert at.session_state["corr_uart_text"] == load_uart_sample("kernel-panic")


def test_gui_mctp_load_sample_button() -> None:
    at = AppTest.from_function(_mctp_app, default_timeout=30).run()
    next(button for button in at.button if button.label == "📋 載入內建範例").click().run()

    assert not at.exception
    assert any("已載入內建 MCTP／IPMB 範例！" in info.value for info in at.info)
    assert any("MCTP Packets" in item.value for item in at.markdown)


def test_gui_uart_load_sample_button_in_pasted_mode() -> None:
    at = AppTest.from_function(_uart_app, default_timeout=30).run()
    assert at.radio[0].value == "貼上 UART 日誌（UART Log）／崩潰轉儲（Crash Dump）"
    next(button for button in at.button if button.label == "📋 載入範例資料").click().run()

    assert not at.exception
    assert at.session_state["uart_pasted_text"] == load_uart_sample("kernel-panic")
