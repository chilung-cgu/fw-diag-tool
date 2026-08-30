from __future__ import annotations

from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.session_io import (
    replay_mctp_session,
    replay_pcie_session,
    replay_spi_session,
    replay_uart_session,
    serialize_mctp_session,
    serialize_pcie_session,
    serialize_spi_session,
    serialize_uart_session,
)
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.resources import (
    load_mctp_sample,
    load_pcie_dmesg_sample,
    load_pcie_lspci_sample,
    load_spi_sample,
    load_uart_sample,
)
from fw_diag_tool.session.session_manager import SessionDocument, SessionManager
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser


def test_spi_session_serialization_and_fields():
    spi_csv = load_spi_sample()
    engine = SPIDiagnosticEngine(max_page_size=256)
    report = engine.analyze_csv_content(spi_csv)

    serialized = serialize_spi_session(
        report,
        input_name="spi_w25q128.csv",
        input_bytes=spi_csv.encode("utf-8"),
        max_page_size=256,
    )
    doc: SessionDocument = SessionManager.deserialize_session(serialized)

    assert doc.schema_version == SessionManager.CURRENT_VERSION
    assert doc.name == "SPI Analysis"
    assert doc.report["protocol"] == "SPI"
    assert "summary" in doc.report
    assert "anomaly_count" in doc.report
    assert isinstance(doc.report["anomaly_count"], int)
    assert doc.config["max_page_size"] == 256
    assert doc.provenance == {"interface": "streamlit", "protocol": "spi"}

    replayed = replay_spi_session(doc, spi_csv)
    assert replayed.summary.total_transactions == report.summary.total_transactions


def test_uart_session_serialization_and_fields():
    uart_panic = load_uart_sample("kernel-panic")
    report = UARTCrashParser.parse_log_text(uart_panic)

    serialized = serialize_uart_session(
        report,
        input_name="kernel_panic.log",
        input_bytes=uart_panic.encode("utf-8"),
        mode="Linux Kernel Panic",
    )
    doc = SessionManager.deserialize_session(serialized)

    assert doc.schema_version == SessionManager.CURRENT_VERSION
    assert doc.name == "UART Analysis"
    assert doc.report["protocol"] == "UART"
    assert "summary" in doc.report
    assert isinstance(doc.report["summary"], str)
    assert "anomaly_count" in doc.report
    assert doc.report["anomaly_count"] >= 1
    assert doc.config["mode"] == "Linux Kernel Panic"
    assert doc.provenance == {"interface": "streamlit", "protocol": "uart"}

    replayed = replay_uart_session(doc, uart_panic)
    assert replayed.crash_type == report.crash_type


def test_pcie_session_serialization_and_fields():
    dmesg_text = load_pcie_dmesg_sample()
    events = PCIeAnalyzer.parse_dmesg_aer(dmesg_text)
    report_dict = {
        "mode": "dmesg",
        "events": [
            {
                "timestamp": ev.timestamp,
                "bdf": ev.bdf,
                "severity": ev.severity,
                "error_name": ev.error_name,
            }
            for ev in events
        ],
    }

    serialized_dmesg = serialize_pcie_session(
        report_dict,
        input_name="pcie_dmesg.log",
        input_bytes=dmesg_text.encode("utf-8"),
        mode="dmesg",
    )
    doc_dmesg = SessionManager.deserialize_session(serialized_dmesg)
    assert doc_dmesg.report["protocol"] == "PCIe"
    assert doc_dmesg.report["mode"] == "dmesg"
    assert "summary" in doc_dmesg.report
    assert doc_dmesg.report["anomaly_count"] == len(events)

    lspci_text = load_pcie_lspci_sample()
    bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(lspci_text)
    cfg = PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)
    lspci_report_dict = {
        "mode": "lspci",
        "devices": [
            {
                "vendor_id": f"0x{cfg.vendor_id:04X}",
                "device_id": f"0x{cfg.device_id:04X}",
                "findings": [{"type": "PCIE_DIAG_ISSUE", "name": "Degraded Link"}],
            }
        ],
    }
    serialized_lspci = serialize_pcie_session(
        lspci_report_dict,
        input_name="lspci.txt",
        input_bytes=lspci_text.encode("utf-8"),
        mode="lspci",
    )
    doc_lspci = SessionManager.deserialize_session(serialized_lspci)
    assert doc_lspci.report["protocol"] == "PCIe"
    assert doc_lspci.report["mode"] == "lspci"
    assert doc_lspci.report["anomaly_count"] == 1

    replayed_events = replay_pcie_session(doc_dmesg, dmesg_text)
    assert len(replayed_events) == len(events)


def test_mctp_session_serialization_and_fields():
    mctp_hex = load_mctp_sample("mctp-pldm")
    report = ServerMgmtParser.parse_text_dump(mctp_hex)

    serialized = serialize_mctp_session(
        report,
        input_name="mctp_pldm.hex",
        input_bytes=mctp_hex.encode("utf-8"),
        protocol_mode="auto",
    )
    doc = SessionManager.deserialize_session(serialized)

    assert doc.schema_version == SessionManager.CURRENT_VERSION
    assert doc.name == "MCTP Analysis"
    assert doc.report["protocol"] == "MCTP"
    assert "summary" in doc.report
    assert "anomaly_count" in doc.report
    assert isinstance(doc.report["anomaly_count"], int)
    assert doc.config["protocol_mode"] == "auto"
    assert doc.provenance == {"interface": "streamlit", "protocol": "mctp"}

    replayed = replay_mctp_session(doc, mctp_hex)
    assert replayed.total_frames == report.total_frames


def dummy_session_render() -> None:
    from fw_diag_tool.gui.shared import render_session_controls

    render_session_controls(
        "custom_proto",
        {"some_key": "some_value", "anomalies": ["issue1", "issue2"]},
        {"cfg_key": 123},
    )


def spi_app_render() -> None:
    from fw_diag_tool.gui.pages.spi_ui import render

    render()


def uart_app_render() -> None:
    from fw_diag_tool.gui.pages.uart_ui import render

    render()


def pcie_app_render() -> None:
    from fw_diag_tool.gui.pages.pcie_ui import render

    render()


def mctp_app_render() -> None:
    from fw_diag_tool.gui.pages.mctp_ui import render

    render()


def test_render_session_controls_auto_populates_missing_fields():
    at = AppTest.from_function(dummy_session_render, default_timeout=15).run()
    assert not at.exception
    save_btn = next(btn for btn in at.download_button if "儲存分析 Session" in btn.label)
    assert save_btn is not None
    assert "儲存分析 Session" in save_btn.label


def test_gui_spi_page_session_save():
    at = AppTest.from_function(spi_app_render, default_timeout=15).run()
    assert not at.exception

    # Click load builtin SPI sample
    at.button[0].click().run()
    assert not at.exception
    save_btn = next(btn for btn in at.download_button if "儲存分析 Session" in btn.label)
    assert save_btn is not None
    assert "儲存分析 Session" in save_btn.label


def test_gui_uart_page_session_save():
    at = AppTest.from_function(uart_app_render, default_timeout=15).run()
    assert not at.exception

    # Select hardfault example
    at.radio[0].set_value("載入範例：ARM Cortex-M HardFault 日誌（HardFault Log）").run()
    next(btn for btn in at.button if "執行 UART 崩潰轉儲分析" in btn.label).click().run()
    assert not at.exception

    save_btn = next(btn for btn in at.download_button if "儲存分析 Session" in btn.label)
    assert save_btn is not None
    assert "儲存分析 Session" in save_btn.label


def test_gui_pcie_page_session_save_dmesg_and_lspci():
    # 1. dmesg mode
    at_dmesg = AppTest.from_function(pcie_app_render, default_timeout=15).run()
    assert not at_dmesg.exception
    # Click load dmesg sample
    next(btn for btn in at_dmesg.button if "載入內建 dmesg AER 範例" in btn.label).click().run()
    next(btn for btn in at_dmesg.button if "執行 PCIe 分析" in btn.label).click().run()
    assert not at_dmesg.exception

    save_btn_dmesg = next(
        btn for btn in at_dmesg.download_button if "儲存分析 Session" in btn.label
    )
    assert save_btn_dmesg is not None
    assert "儲存分析 Session" in save_btn_dmesg.label

    # 2. lspci mode
    at_lspci = AppTest.from_function(pcie_app_render, default_timeout=15).run()
    assert not at_lspci.exception
    # Click load lspci sample
    next(
        btn for btn in at_lspci.button if "載入內建 lspci PCIe 設定空間範例" in btn.label
    ).click().run()
    next(btn for btn in at_lspci.button if "執行 PCIe 分析" in btn.label).click().run()
    assert not at_lspci.exception

    save_btn_lspci = next(
        btn for btn in at_lspci.download_button if "儲存分析 Session" in btn.label
    )
    assert save_btn_lspci is not None
    assert "儲存分析 Session" in save_btn_lspci.label


def test_gui_mctp_page_session_save():
    at = AppTest.from_function(mctp_app_render, default_timeout=15).run()
    assert not at.exception

    # Click decode button
    next(
        btn for btn in at.button if "執行 MCTP／IPMB 伺服器管理協定解碼" in btn.label
    ).click().run()
    assert not at.exception

    save_btn = next(btn for btn in at.download_button if "儲存分析 Session" in btn.label)
    assert save_btn is not None
    assert "儲存分析 Session" in save_btn.label
