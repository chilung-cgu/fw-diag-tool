from __future__ import annotations

import json
from types import SimpleNamespace

from fw_diag_tool.gui.pages.protocol_diff_ui import (
    format_protocol_diff_dict,
    format_protocol_diff_json,
)
from fw_diag_tool.i2c.diff import I2CDiffEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CAnalysisReport,
    I2CDiagnosticIssue,
    I2CDirection,
    I2CTransaction,
    Severity,
    TimingStatistics,
)
from fw_diag_tool.mctp.diff import MCTPDiffEngine
from fw_diag_tool.mctp.models import (
    IPMBFrame,
    MCTPMessage,
    ProtocolMode,
    ServerMgmtReport,
)
from fw_diag_tool.pcie.diff import PCIeDiffEngine
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERUncorrectableError,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)
from fw_diag_tool.spi.diff import SPIDiffEngine
from fw_diag_tool.spi.models import (
    SPIDiagnosticIssue,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
)
from fw_diag_tool.uart.diff import UARTDiffEngine
from fw_diag_tool.uart.models import (
    CallTraceFrame,
    CrashType,
    KernelPanicReport,
    UARTReport,
)


def _create_i2c_report(addresses: list[int], issues: list[str]) -> I2CAnalysisReport:
    txs = [
        I2CTransaction(
            id=i + 1,
            start_time=float(i),
            end_time=float(i) + 0.001,
            address_7bit=addr,
            address_8bit=addr << 1,
            direction=I2CDirection.WRITE,
            address_ack=AckType.ACK,
        )
        for i, addr in enumerate(addresses)
    ]
    diag_issues = [
        I2CDiagnosticIssue(
            code=f"I2C_ERR_{i}",
            title=title,
            severity=Severity.WARNING,
            category="Protocol",
            description="Test issue",
            root_cause_analysis="Test RCA",
            actionable_advice=[],
        )
        for i, title in enumerate(issues)
    ]
    return I2CAnalysisReport(
        total_events=len(txs),
        total_transactions=len(txs),
        total_duration_s=0.01,
        devices_detected={},
        transactions=txs,
        timing_stats=TimingStatistics(),
        issues=diag_issues,
        summary_text="I2C Test Summary",
    )


def _create_spi_report(
    titles: list[str], total_tx: int = 10, chip: str | None = "Winbond W25Q128"
) -> SPIReport:
    anomalies = [
        SPIDiagnosticIssue(
            code=f"SPI_ERR_{i}",
            title=title,
            severity=SPISeverity.ERROR,
            timestamp=float(i),
            transaction_id=i,
            description="SPI Desc",
            root_cause_guide="Check flash",
        )
        for i, title in enumerate(titles)
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


def _create_uart_report(
    crash_type: CrashType, fault_func: str = "nvme_pci_complete_rq", fault_addr: str = "0x10"
) -> UARTReport:
    panic = KernelPanicReport(
        architecture="x86_64",
        panic_reason="unable to handle page fault",
        faulting_address=fault_addr,
        faulting_func=fault_func,
        call_trace=[
            CallTraceFrame(index=0, function_name=fault_func, offset="0x38"),
        ],
    )
    return UARTReport(
        crash_type=crash_type,
        summary_title="Kernel Panic Report",
        kernel_panic=panic,
        raw_log_lines=50,
    )


def _create_pcie_config(
    vendor_id: int = 0x10EE, device_id: int = 0x7024, uncorr_errors: list[str] | None = None
) -> PCIeConfigSpace:
    uncorr_list = [
        AERUncorrectableError(
            bit_pos=i,
            name=name,
            short_code=name[:4],
            is_active=True,
            is_masked=False,
            severity="Fatal",
        )
        for i, name in enumerate(uncorr_errors or [])
    ]
    aer_analysis = AERAnalysisResult(
        offset=0x100,
        uncorr_status_raw=0,
        uncorr_mask_raw=0,
        uncorr_severity_raw=0,
        corr_status_raw=0,
        corr_mask_raw=0,
        cap_control_raw=0,
        header_log_raw=[],
        uncorr_errors=uncorr_list,
    )
    link_info = PCIeLinkInfo(
        current_speed_str="8.0 GT/s",
        current_width=8,
        is_degraded=False,
    )
    return PCIeConfigSpace(
        raw_data=b"\x00" * 256,
        vendor_id=vendor_id,
        device_id=device_id,
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=link_info,
        aer_analysis=aer_analysis,
        class_name="Bridge",
    )


def _create_mctp_report(
    errors: list[str] | None = None, warnings: list[str] | None = None
) -> ServerMgmtReport:
    return ServerMgmtReport(
        mctp_messages=[
            MCTPMessage(
                src_eid=0x0A,
                dest_eid=0x08,
                msg_tag=1,
                msg_type=1,
                msg_type_name="PLDM",
                packets_count=1,
            )
        ],
        ipmb_frames=[
            IPMBFrame(
                rs_addr=0x20,
                netfn=0x06,
                netfn_name="App",
                rs_lun=0,
                checksum1_valid=True,
                rq_addr=0x2C,
                rq_seq=1,
                rq_lun=0,
                cmd=1,
                cmd_name="Get Device ID",
            )
        ],
        protocol_mode=ProtocolMode.AUTO,
        errors=list(errors or []),
        warnings=list(warnings or []),
        total_frames=2,
    )


# --- Tests for to_dict() and to_json() on DiffResults ---


def test_i2c_diff_result_to_dict_and_to_json() -> None:
    base = _create_i2c_report([0x50], ["Old NACK"])
    cand = _create_i2c_report([0x50, 0x58], ["New NACK"])
    result = I2CDiffEngine.compare(base, cand)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["baseline_transaction_count"] == 1
    assert d["candidate_transaction_count"] == 2
    assert d["transaction_count_delta"] == 1
    assert d["new_anomalies"] == ["New NACK"]
    assert d["resolved_anomalies"] == ["Old NACK"]
    assert d["common_anomalies"] == []
    assert d["is_identical"] is False
    assert "交易數變化" in d["summary"]

    raw_json = result.to_json()
    parsed = json.loads(raw_json)
    assert parsed["new_anomalies"] == ["New NACK"]


def test_spi_diff_result_to_dict_and_to_json() -> None:
    base = _create_spi_report(["Old Anomaly"], total_tx=10, chip="Winbond W25Q128")
    cand = _create_spi_report(["New Anomaly"], total_tx=15, chip="Macronix MX25L128")
    result = SPIDiffEngine.compare(base, cand)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["new_anomalies"] == ["New Anomaly"]
    assert d["resolved_anomalies"] == ["Old Anomaly"]
    assert d["common_anomalies"] == []
    assert d["transaction_count_delta"] == 5
    assert d["chip_changed"] is True
    assert d["baseline_detected_chip"] == "Winbond W25Q128"
    assert d["candidate_detected_chip"] == "Macronix MX25L128"
    assert d["is_identical"] is False

    parsed = json.loads(result.to_json())
    assert parsed["new_anomalies"] == ["New Anomaly"]
    assert parsed["chip_changed"] is True


def test_uart_diff_result_to_dict_and_to_json() -> None:
    base = _create_uart_report(CrashType.KERNEL_PANIC, "func_old", "0x10")
    cand = _create_uart_report(CrashType.KERNEL_PANIC, "func_new", "0x20")
    result = UARTDiffEngine.compare(base, cand)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["new_symbols"] == ["func_new"]
    assert d["resolved_symbols"] == ["func_old"]
    assert d["new_anomalies"] == ["func_new"]
    assert d["resolved_anomalies"] == ["func_old"]
    assert d["fault_address_changed"] is True
    assert d["baseline_fault_address"] == "0x10"
    assert d["candidate_fault_address"] == "0x20"
    assert d["is_identical"] is False

    parsed = json.loads(result.to_json())
    assert parsed["new_anomalies"] == ["func_new"]


def test_pcie_diff_result_to_dict_and_to_json() -> None:
    base = _create_pcie_config(vendor_id=0x10EE, device_id=0x7024, uncorr_errors=["Old AER"])
    cand = _create_pcie_config(vendor_id=0x10EE, device_id=0x7024, uncorr_errors=["New AER"])
    result = PCIeDiffEngine.compare(base, cand)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["new_aer_errors"] == ["New AER"]
    assert d["resolved_aer_errors"] == ["Old AER"]
    assert d["new_anomalies"] == ["New AER"]
    assert d["resolved_anomalies"] == ["Old AER"]
    assert d["vendor_changed"] is False
    assert d["is_identical"] is False

    parsed = json.loads(result.to_json())
    assert parsed["new_anomalies"] == ["New AER"]


def test_mctp_diff_result_to_dict_and_to_json() -> None:
    base = _create_mctp_report(errors=["Err Old"], warnings=["Warn Old"])
    cand = _create_mctp_report(errors=["Err New"], warnings=["Warn New"])
    result = MCTPDiffEngine.compare(base, cand)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["new_errors"] == ["Err New"]
    assert d["resolved_errors"] == ["Err Old"]
    assert d["new_anomalies"] == ["Err New"]
    assert d["resolved_anomalies"] == ["Err Old"]
    assert d["new_warnings"] == ["Warn New"]
    assert d["resolved_warnings"] == ["Warn Old"]
    assert d["is_identical"] is False

    parsed = json.loads(result.to_json())
    assert parsed["new_anomalies"] == ["Err New"]


# --- Tests for format_protocol_diff_json and format_protocol_diff_dict ---


def test_format_protocol_diff_json_i2c() -> None:
    base = _create_i2c_report([0x50], ["Old NACK"])
    cand = _create_i2c_report([0x50, 0x58], ["New NACK"])
    result = I2CDiffEngine.compare(base, cand)

    json_str = format_protocol_diff_json(
        "I2C",
        result,
        baseline_report=base,
        candidate_report=cand,
        baseline_name="base.csv",
        candidate_name="cand.csv",
        timestamp="2026-08-30T12:00:00Z",
    )
    data = json.loads(json_str)
    assert data["protocol"] == "I2C"
    assert data["timestamp"] == "2026-08-30T12:00:00Z"
    assert data["baseline_summary"]["name"] == "base.csv"
    assert data["baseline_summary"]["total_transactions"] == 1
    assert data["candidate_summary"]["name"] == "cand.csv"
    assert data["candidate_summary"]["total_transactions"] == 2
    assert data["diff"]["new_anomalies"] == ["New NACK"]
    assert data["diff"]["resolved_anomalies"] == ["Old NACK"]
    assert data["diff"]["common_anomalies"] == []


def test_format_protocol_diff_json_spi() -> None:
    base = _create_spi_report(["Old Anomaly"], total_tx=10, chip="Winbond W25Q128")
    cand = _create_spi_report(["New Anomaly"], total_tx=15, chip="Macronix MX25L128")
    result = SPIDiffEngine.compare(base, cand)

    json_str = format_protocol_diff_json(
        "SPI",
        result,
        baseline_report=base,
        candidate_report=cand,
        baseline_name="spi_base.csv",
        candidate_name="spi_cand.csv",
        timestamp="2026-08-30T13:00:00Z",
    )
    data = json.loads(json_str)
    assert data["protocol"] == "SPI"
    assert data["timestamp"] == "2026-08-30T13:00:00Z"
    assert data["baseline_summary"]["detected_flash_chip"] == "Winbond W25Q128"
    assert data["candidate_summary"]["detected_flash_chip"] == "Macronix MX25L128"
    assert data["diff"]["new_anomalies"] == ["New Anomaly"]
    assert data["diff"]["resolved_anomalies"] == ["Old Anomaly"]
    assert data["diff"]["common_anomalies"] == []


def test_format_protocol_diff_json_uart() -> None:
    base = _create_uart_report(CrashType.KERNEL_PANIC, "func_old", "0x10")
    cand = _create_uart_report(CrashType.KERNEL_PANIC, "func_new", "0x20")
    result = UARTDiffEngine.compare(base, cand)

    json_str = format_protocol_diff_json(
        "UART",
        result,
        baseline_report=base,
        candidate_report=cand,
        baseline_name="panic1.log",
        candidate_name="panic2.log",
    )
    data = json.loads(json_str)
    assert data["protocol"] == "UART"
    assert data["baseline_summary"]["crash_type"] == CrashType.KERNEL_PANIC.value
    assert data["baseline_summary"]["fault_address"] == "0x10"
    assert data["candidate_summary"]["fault_address"] == "0x20"
    assert data["diff"]["new_anomalies"] == ["func_new"]
    assert data["diff"]["resolved_anomalies"] == ["func_old"]


def test_format_protocol_diff_json_pcie() -> None:
    base = _create_pcie_config(vendor_id=0x10EE, device_id=0x7024, uncorr_errors=["Old AER"])
    cand = _create_pcie_config(vendor_id=0x10EE, device_id=0x7024, uncorr_errors=["New AER"])
    result = PCIeDiffEngine.compare(base, cand)

    json_str = format_protocol_diff_json(
        "PCIe",
        result,
        baseline_report=base,
        candidate_report=cand,
    )
    data = json.loads(json_str)
    assert data["protocol"] == "PCIe"
    assert data["baseline_summary"]["vendor_id"] == "0x10EE"
    assert data["diff"]["new_anomalies"] == ["New AER"]
    assert data["diff"]["resolved_anomalies"] == ["Old AER"]


def test_format_protocol_diff_json_mctp() -> None:
    base = _create_mctp_report(errors=["Err Old"], warnings=["Warn Old"])
    cand = _create_mctp_report(errors=["Err New"], warnings=["Warn New"])
    result = MCTPDiffEngine.compare(base, cand)

    json_str = format_protocol_diff_json(
        "MCTP",
        result,
        baseline_report=base,
        candidate_report=cand,
    )
    data = json.loads(json_str)
    assert data["protocol"] == "MCTP"
    assert data["baseline_summary"]["protocol_mode"] == "auto"
    assert data["diff"]["new_anomalies"] == ["Err New"]
    assert data["diff"]["resolved_anomalies"] == ["Err Old"]


def test_format_protocol_diff_json_with_none_reports_fallback() -> None:
    mock_res = SimpleNamespace(
        summary="I2C Mock Diff",
        is_identical=False,
        new_anomalies=["New Issue"],
        resolved_anomalies=["Old Issue"],
        common_anomalies=[],
        baseline_transaction_count=5,
        candidate_transaction_count=7,
    )
    data = format_protocol_diff_dict(
        "I2C",
        mock_res,
        baseline_name="Base",
        candidate_name="Cand",
        timestamp="2026-08-30T10:00:00Z",
    )
    assert data["protocol"] == "I2C"
    assert data["timestamp"] == "2026-08-30T10:00:00Z"
    assert data["baseline_summary"]["name"] == "Base"
    assert data["baseline_summary"]["total_transactions"] == 5
    assert data["candidate_summary"]["name"] == "Cand"
    assert data["candidate_summary"]["total_transactions"] == 7
    assert data["diff"]["new_anomalies"] == ["New Issue"]
    assert data["diff"]["resolved_anomalies"] == ["Old Issue"]
