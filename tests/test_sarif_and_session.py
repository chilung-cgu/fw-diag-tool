from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from fw_diag_tool.session.session_manager import SessionManager
from fw_diag_tool.spi.models import (
    SPIDataQualityIssue,
    SPIDiagnosticIssue,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
    SPITransaction,
)


def spi_render() -> None:
    from fw_diag_tool.gui.pages.spi_ui import render

    render()


def pcie_render() -> None:
    from fw_diag_tool.gui.pages.pcie_ui import render

    render()


def i2c_diagnosis_render() -> None:
    from fw_diag_tool.gui.pages.i2c_diagnosis import render

    render()


def sarif_helper_render() -> None:
    from fw_diag_tool.gui.sarif_export import render_sarif_download

    findings = [
        {"code": "SPI_ERR", "title": "SPI Error", "severity": "ERROR", "message": "Anomaly"},
    ]
    render_sarif_download(findings, protocol="SPI", filename_prefix="custom")
    render_sarif_download([], protocol="I2C", filename_prefix="empty")


def test_sarif_export_helper():
    at = AppTest.from_function(sarif_helper_render, default_timeout=15).run()
    assert not at.exception
    assert len(at.download_button) == 1
    btn = at.download_button[0]
    assert btn.label == "📥 下載 SARIF 報告（SPI）"
    assert btn.key == "sarif_download_spi"


def test_spi_report_models_to_dict_and_issues_alias():
    summary = SPIReportSummary(total_transactions=10, anomaly_count=1)
    tx = SPITransaction(
        index=0,
        start_time=0.0,
        end_time=0.001,
        duration_us=1000.0,
        mosi_bytes=[0x06],
        miso_bytes=[0x00],
        opcode=0x06,
        opcode_name="WREN",
    )
    issue = SPIDiagnosticIssue(
        code="SPI_WREN_MISSING",
        title="WREN Missing",
        severity=SPISeverity.ERROR,
        timestamp=0.0,
        transaction_id=0,
        description="Page program without WREN",
        root_cause_guide="Send 0x06 before 0x02",
    )
    quality = SPIDataQualityIssue(code="SPI_SAMPLE_INCOMPLETE", message="Truncated", count=1)
    report = SPIReport(
        summary=summary,
        transactions=[tx],
        anomalies=[issue],
        data_quality_issues=[quality],
    )

    assert report.issues == [issue]
    d = report.to_dict()
    assert d["summary"]["total_transactions"] == 10
    assert d["transactions"][0]["opcode_name"] == "WREN"
    assert d["anomalies"][0]["code"] == "SPI_WREN_MISSING"
    assert d["issues"][0]["code"] == "SPI_WREN_MISSING"
    assert d["data_quality_issues"][0]["code"] == "SPI_SAMPLE_INCOMPLETE"


def test_gui_spi_page_session_and_sarif():
    at = AppTest.from_function(spi_render, default_timeout=15).run()

    # Upload valid session
    session_json = SessionManager.serialize_session(
        name="SPI Test",
        data={"summary": {"total_transactions": 4}},
        config={"max_page_size": 256},
    )
    session_uploader = next(u for u in at.file_uploader if u.key and "session" in u.key.lower())
    session_uploader.upload(
        "spi.fwsession.json", session_json.encode("utf-8"), "application/json"
    ).run()
    assert not at.exception
    assert any("已載入 Session：SPI Test" in info.value for info in at.info)

    # Upload an SPI trace with an anomaly (write without WREN)
    bad_spi_csv = (
        "Time [s],MOSI,MISO,Enable\n"
        "0.0020,0x02,0x00,0\n"
        "0.0021,0x00,0x00,0\n"
        "0.0022,0x10,0x00,0\n"
        "0.0023,0x00,0x00,0\n"
        "0.0024,0x55,0x00,0\n"
        "0.0025,0xAA,0x00,0\n"
        "0.0026,0x00,0x00,1\n"
    )
    csv_uploader = next(u for u in at.file_uploader if not u.key or "session" not in u.key.lower())
    csv_uploader.upload("bad_spi.csv", bad_spi_csv.encode("utf-8"), "text/csv").run()
    assert not at.exception
    assert any(btn.label == "下載 SPI Markdown 診斷報告" for btn in at.download_button)
    assert any(btn.label == "📥 下載 SARIF 報告（SPI）" for btn in at.download_button)
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)

    # Also test with builtin clean sample (has session download but no SARIF button since 0 findings)
    at.button[0].click().run()
    assert not at.exception
    assert any(btn.label == "下載 SPI Markdown 診斷報告" for btn in at.download_button)
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)


def test_gui_pcie_page_dmesg_session_and_sarif():
    at = AppTest.from_function(pcie_render, default_timeout=15).run()
    at.radio[0].set_value("貼上 Linux dmesg AER 錯誤日誌（AER Error Log）")
    at.text_area[0].input(
        "[  124.582910] pcieport 0000:00:01.0: AER: Uncorrected (Fatal) error received: 0000:01:00.0\n"
        "[  124.582922] pcieport 0000:00:01.0:    [18] MalformedTLP           (First)\n"
        "[  124.582925] pcieport 0000:00:01.0:   TLP Header: 00000001 0100000f fe000000 00000000"
    )
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any(btn.label == "下載 PCIe dmesg Markdown 診斷報告" for btn in at.download_button)
    assert any(btn.label == "📥 下載 SARIF 報告（PCIe）" for btn in at.download_button)
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)


def test_gui_pcie_page_lspci_session_and_sarif():
    at = AppTest.from_function(pcie_render, default_timeout=15).run()
    next(
        button
        for button in at.button
        if button.label == "載入內建 lspci PCIe 設定空間範例（Config Space）"
    ).click().run()
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any(btn.label.startswith("下載 PCIe 診斷報告") for btn in at.download_button)
    assert any(btn.label == "📥 下載 SARIF 報告（PCIe）" for btn in at.download_button)
    assert any(btn.label == "💾 儲存分析 Session" for btn in at.download_button)


def test_gui_i2c_page_sarif_export():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    nack_csv = Path("examples/data/i2c_address_nack.csv").read_bytes()
    at.file_uploader[1].upload("i2c_address_nack.csv", nack_csv, "text/csv").run()

    assert not at.exception
    assert any(btn.label == "下載 Markdown 報告" for btn in at.download_button)
    assert any(btn.label == "📥 下載 SARIF 報告（I2C）" for btn in at.download_button)
