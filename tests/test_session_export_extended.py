from __future__ import annotations

from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.shared import render_session_controls
from fw_diag_tool.session.session_manager import SessionDocument, SessionManager
from fw_diag_tool.spi.models import (
    SPIDiagnosticIssue,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
    SPITransaction,
)
from fw_diag_tool.uart.parser import UARTCrashParser


def test_render_session_controls_importable():
    assert callable(render_session_controls)


def test_session_manager_spi_payload_roundtrip():
    summary = SPIReportSummary(
        total_transactions=5,
        read_count=2,
        write_count=2,
        erase_count=1,
        anomaly_count=1,
        detected_flash_chip="Winbond W25Q128",
    )
    tx = SPITransaction(
        index=1,
        start_time=0.001,
        end_time=0.002,
        duration_us=1000.0,
        mosi_bytes=[0x06],
        miso_bytes=[0x00],
        opcode=0x06,
        opcode_name="WREN",
    )
    issue = SPIDiagnosticIssue(
        code="SPI_WRITE_PROTECT_VIOLATION",
        title="Write Protect Violation",
        severity=SPISeverity.ERROR,
        timestamp=0.002,
        transaction_id=1,
        description="Page program into protected block",
        root_cause_guide="Clear BP bits in status register",
    )
    spi_report = SPIReport(
        summary=summary,
        transactions=[tx],
        anomalies=[issue],
    )
    report_dict = spi_report.to_dict()
    config_dict = {"max_page_size": 256}

    payload = SessionManager.build_payload(
        name="SPI Test Session",
        data=report_dict,
        config=config_dict,
        notes="SPI automated test session",
    )

    assert payload["schema_version"] == SessionManager.CURRENT_VERSION
    assert payload["name"] == "SPI Test Session"
    assert payload["config"] == config_dict
    assert payload["report"]["summary"]["total_transactions"] == 5
    assert payload["report"]["summary"]["detected_flash_chip"] == "Winbond W25Q128"
    assert len(payload["report"]["transactions"]) == 1
    assert len(payload["report"]["anomalies"]) == 1

    serialized = SessionManager.serialize_session(
        name="SPI Test Session",
        data=report_dict,
        config=config_dict,
    )
    assert isinstance(serialized, str)

    doc: SessionDocument = SessionManager.deserialize_session(serialized)
    assert doc.schema_version == SessionManager.CURRENT_VERSION
    assert doc.name == "SPI Test Session"
    assert doc.config == config_dict
    assert doc.report["summary"]["total_transactions"] == 5
    assert doc.report["anomalies"][0]["code"] == "SPI_WRITE_PROTECT_VIOLATION"


def test_session_manager_uart_kernel_panic_roundtrip():
    panic_log = (
        "BUG: unable to handle page fault for address: 0000000000000010\n"
        "RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\n"
        "RAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000\n"
        "CR2: 0000000000000010\n"
        "Call Trace:\n"
        " <TASK>\n"
        " [ffff888100123450] blk_mq_complete_request+0x24/0x50\n"
        " </TASK>"
    )
    u_report = UARTCrashParser.parse_log_text(panic_log)
    report_dict = u_report.to_dict()
    config_dict = {"mode": "貼上 UART 日誌"}

    payload = SessionManager.build_payload(
        name="UART Kernel Panic Session",
        data=report_dict,
        config=config_dict,
    )

    assert payload["schema_version"] == SessionManager.CURRENT_VERSION
    assert payload["name"] == "UART Kernel Panic Session"
    assert payload["report"]["crash_type"] == "Linux Kernel Panic / Oops"
    assert payload["report"]["kernel_panic"]["faulting_func"] == "nvme_pci_complete_rq"

    serialized = SessionManager.serialize_session(
        name="UART Kernel Panic Session",
        data=report_dict,
        config=config_dict,
    )
    doc = SessionManager.deserialize_session(serialized)
    assert doc.name == "UART Kernel Panic Session"
    assert doc.report["crash_type"] == "Linux Kernel Panic / Oops"
    assert doc.report["kernel_panic"]["faulting_address"] == "0x0000000000000010"


def test_session_manager_uart_hardfault_roundtrip():
    hf_log = (
        "HardFault Exception Occurred!\n"
        "HFSR: 0x40000000 (FORCED)\n"
        "CFSR: 0x02000000 (DIVBYZERO)\n"
        "Stacked PC: 0x08001234\n"
        "Stacked LR: 0x08000456"
    )
    u_report = UARTCrashParser.parse_log_text(hf_log)
    report_dict = u_report.to_dict()

    serialized = SessionManager.serialize_session(
        name="UART HardFault Session",
        data=report_dict,
        config={"mode": "ARM Cortex-M HardFault"},
    )
    doc = SessionManager.deserialize_session(serialized)
    assert doc.name == "UART HardFault Session"
    assert doc.report["crash_type"] == "ARM Cortex-M HardFault"
    assert doc.report["arm_hardfault"]["pc_faulting"] == 0x08001234
    assert doc.report["arm_hardfault"]["cfsr_raw"] == 0x02000000


def uart_app_render() -> None:
    from fw_diag_tool.gui.pages.uart_ui import render

    render()


def spi_app_render() -> None:
    from fw_diag_tool.gui.pages.spi_ui import render

    render()


def standalone_session_render() -> None:
    from fw_diag_tool.gui.shared import render_session_controls

    render_session_controls("custom_proto", {"custom_key": "custom_val"}, {"cfg": 1})


def test_gui_uart_page_session_controls():
    at = AppTest.from_function(uart_app_render, default_timeout=15).run()
    assert not at.exception

    # 1. Upload valid session
    session_json = SessionManager.serialize_session(
        name="UART Test Saved Session",
        data={"crash_type": "ARM Cortex-M HardFault", "summary_title": "Test HF"},
        config={"mode": "test"},
    )
    session_uploader = next(u for u in at.file_uploader if u.key and "session" in u.key.lower())
    session_uploader.upload(
        "uart.fwsession.json", session_json.encode("utf-8"), "application/json"
    ).run()
    assert not at.exception
    assert any("已載入 Session：UART Test Saved Session" in info.value for info in at.info)

    # 2. Trigger analysis and verify save button appears
    at.radio[0].set_value("載入範例：ARM Cortex-M HardFault 日誌（HardFault Log）").run()
    next(btn for btn in at.button if "執行 UART 崩潰轉儲分析" in btn.label).click().run()
    assert not at.exception
    assert any(btn.label == "下載 UART Markdown 診斷報告" for btn in at.download_button)
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)


def test_gui_spi_page_session_controls_extended():
    at = AppTest.from_function(spi_app_render, default_timeout=15).run()
    assert not at.exception

    # Trigger analysis with builtin sample
    at.button[0].click().run()
    assert not at.exception
    assert any(btn.label == "下載 SPI Markdown 診斷報告" for btn in at.download_button)
    save_btn = next(btn for btn in at.download_button if btn.label == "💾 儲存分析 Session")
    assert save_btn is not None


def test_render_session_controls_standalone():
    at = AppTest.from_function(standalone_session_render, default_timeout=15).run()
    assert not at.exception
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)

    # Upload invalid JSON to verify error handling
    session_uploader = next(u for u in at.file_uploader if u.key and "session" in u.key.lower())
    session_uploader.upload("bad.fwsession.json", b"not valid json", "application/json").run()
    assert not at.exception
    assert any("無法載入 Session" in err.value for err in at.error)
