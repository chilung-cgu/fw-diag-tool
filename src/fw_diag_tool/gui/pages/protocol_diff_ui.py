"""I2C、SPI、UART、PCIe、MCTP 協定 A/B 對比分析頁面。"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.gui.uploads import (
    MAX_UPLOAD_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)
from fw_diag_tool.i2c.diff import I2CDiffEngine
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i18n import t
from fw_diag_tool.mctp.diff import MCTPDiffEngine
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.diff import PCIeDiffEngine
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.resources import (
    load_mctp_sample,
    load_pcie_lspci_sample,
    load_spi_sample,
    load_uart_sample,
    load_waveform_diff_samples,
)
from fw_diag_tool.spi.diff import SPIDiffEngine
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.diff import UARTDiffEngine
from fw_diag_tool.uart.parser import UARTCrashParser

MAX_UPLOAD_MIB = max(1, MAX_UPLOAD_BYTES // (1024 * 1024))
_PROTOCOLS = ("I2C", "SPI", "UART", "PCIe", "MCTP")


def _tr(key: str, fallback: str, **kwargs: Any) -> str:
    translated = t(key, domain="gui", **kwargs)
    return fallback if translated == key else translated


def _uploaded_text(uploaded: Any) -> str:
    return decode_uploaded_text(uploaded, allowed_extensions={".csv", ".txt", ".log", ".hex"})


def _write_temp_input(text: str, suffix: str = ".csv") -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=suffix, delete=False
    ) as handle:
        handle.write(text)
        return Path(handle.name)


def _analyze_input(protocol: str, text: str, source_name: str | None = None) -> Any:
    """解析單側輸入；回傳對應協定的分析報告。"""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("輸入內容不可為空")
    if protocol == "I2C":
        engine = I2CDiagnosticEngine()
        if source_name and Path(source_name).suffix.lower() == ".csv":
            path = _write_temp_input(text)
            try:
                return engine.analyze_csv_file(str(path))
            finally:
                path.unlink(missing_ok=True)
        return engine.analyze_text(text)
    if protocol == "SPI":
        path = _write_temp_input(text)
        try:
            return SPIDiagnosticEngine().analyze_csv_file(path)
        finally:
            path.unlink(missing_ok=True)
    if protocol == "UART":
        return UARTCrashParser.parse_log_text(text)
    if protocol == "PCIe":
        results = PCIeAnalyzer.parse_multi_lspci_text(text)
        if not results:
            raise ValueError("無有效的 PCIe 配置空間資料")
        return results[0]
    if protocol == "MCTP":
        return ServerMgmtParser.parse_hex_input(text)
    raise ValueError(f"不支援的協定：{protocol}")


def _compare(protocol: str, baseline: Any, candidate: Any) -> Any:
    if protocol == "I2C":
        return I2CDiffEngine.compare(baseline, candidate)
    if protocol == "SPI":
        return SPIDiffEngine.compare(baseline, candidate)
    if protocol == "UART":
        return UARTDiffEngine.compare(baseline, candidate)
    if protocol == "PCIe":
        return PCIeDiffEngine.compare(baseline, candidate)
    if protocol == "MCTP":
        return MCTPDiffEngine.compare(baseline, candidate)
    raise ValueError(f"不支援的協定：{protocol}")


def _diff_lists(protocol: str, result: Any) -> tuple[list[str], list[str], list[str]]:
    if protocol == "UART":
        return result.new_symbols, result.resolved_symbols, result.common_symbols
    if protocol == "PCIe":
        return result.new_aer_errors, result.resolved_aer_errors, result.common_aer_errors
    if protocol == "MCTP":
        return result.new_errors, result.resolved_errors, result.common_errors
    return result.new_anomalies, result.resolved_anomalies, result.common_anomalies


def _extract_report_summary(
    protocol: str,
    report: Any,
    name: str = "Report",
    result: Any = None,
    role: str = "baseline",
) -> dict[str, Any]:
    """提取個別協定報告的摘要資訊為字典。"""
    summary: dict[str, Any] = {"name": name}
    if protocol == "I2C":
        if report is not None and hasattr(report, "total_transactions"):
            summary.update(
                {
                    "total_events": getattr(report, "total_events", 0),
                    "total_transactions": getattr(report, "total_transactions", 0),
                    "total_duration_s": getattr(report, "total_duration_s", 0.0),
                    "devices_count": len(getattr(report, "devices_detected", {})),
                    "issues_count": len(getattr(report, "issues", [])),
                    "summary_text": getattr(report, "summary_text", ""),
                }
            )
        elif result is not None:
            tx_count = (
                getattr(result, "baseline_transaction_count", 0)
                if role == "baseline"
                else getattr(result, "candidate_transaction_count", 0)
            )
            summary["total_transactions"] = tx_count
    elif protocol == "SPI":
        if report is not None and hasattr(report, "summary"):
            s = report.summary
            summary.update(
                {
                    "total_transactions": getattr(s, "total_transactions", 0),
                    "read_count": getattr(s, "read_count", 0),
                    "write_count": getattr(s, "write_count", 0),
                    "erase_count": getattr(s, "erase_count", 0),
                    "detected_flash_chip": getattr(s, "detected_flash_chip", None),
                    "anomaly_count": len(getattr(report, "anomalies", [])),
                }
            )
        elif result is not None:
            chip = (
                getattr(result, "baseline_detected_chip", None)
                if role == "baseline"
                else getattr(result, "candidate_detected_chip", None)
            )
            summary["detected_flash_chip"] = chip
    elif protocol == "UART":
        if report is not None and hasattr(report, "crash_type"):
            crash_type_val = (
                report.crash_type.value
                if hasattr(report.crash_type, "value")
                else str(report.crash_type)
            )
            fault_addr = UARTDiffEngine._extract_fault_address(report)
            summary.update(
                {
                    "crash_type": crash_type_val,
                    "summary_title": getattr(report, "summary_title", ""),
                    "raw_log_lines": getattr(report, "raw_log_lines", 0),
                    "fault_address": fault_addr,
                }
            )
        elif result is not None:
            crash_type = (
                getattr(result, "baseline_crash_type", "")
                if role == "baseline"
                else getattr(result, "candidate_crash_type", "")
            )
            fault_addr = (
                getattr(result, "baseline_fault_address", None)
                if role == "baseline"
                else getattr(result, "candidate_fault_address", None)
            )
            summary.update(
                {
                    "crash_type": crash_type,
                    "fault_address": fault_addr,
                }
            )
    elif protocol == "PCIe":
        if report is not None and hasattr(report, "vendor_id"):
            summary.update(
                {
                    "vendor_id": f"0x{report.vendor_id:04X}",
                    "device_id": f"0x{report.device_id:04X}",
                    "class_name": getattr(report, "class_name", ""),
                    "link_summary": PCIeDiffEngine._format_link_summary(
                        getattr(report, "link_info", None)
                    ),
                    "is_degraded": getattr(report.link_info, "is_degraded", False)
                    if getattr(report, "link_info", None)
                    else False,
                    "quality_issues_count": len(getattr(report, "data_quality_issues", [])),
                }
            )
        elif result is not None:
            link_summary = (
                getattr(result, "baseline_link_summary", "N/A")
                if role == "baseline"
                else getattr(result, "candidate_link_summary", "N/A")
            )
            summary["link_summary"] = link_summary
    elif protocol == "MCTP":
        if report is not None and (
            hasattr(report, "mctp_messages") or hasattr(report, "ipmb_frames")
        ):
            summary.update(
                {
                    "protocol_mode": MCTPDiffEngine._extract_protocol_mode(report),
                    "mctp_messages_count": len(getattr(report, "mctp_messages", [])),
                    "mctp_packets_count": len(getattr(report, "mctp_packets", [])),
                    "ipmb_frames_count": len(getattr(report, "ipmb_frames", [])),
                    "total_frames": getattr(report, "total_frames", 0),
                    "errors_count": len(MCTPDiffEngine._extract_errors(report)),
                    "warnings_count": len(MCTPDiffEngine._extract_warnings(report)),
                }
            )
        elif result is not None:
            proto_mode = (
                getattr(result, "baseline_protocol_mode", "")
                if role == "baseline"
                else getattr(result, "candidate_protocol_mode", "")
            )
            summary["protocol_mode"] = proto_mode
    return summary


def format_protocol_diff_dict(
    protocol: str,
    result: Any,
    *,
    baseline_report: Any = None,
    candidate_report: Any = None,
    baseline_name: str = "Baseline",
    candidate_name: str = "Candidate",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """將協定差分結果格式化為結構化字典。"""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    baseline_summary = _extract_report_summary(
        protocol, baseline_report, name=baseline_name, result=result, role="baseline"
    )
    candidate_summary = _extract_report_summary(
        protocol, candidate_report, name=candidate_name, result=result, role="candidate"
    )

    new_items, resolved_items, common_items = _diff_lists(protocol, result)

    diff_dict: dict[str, Any]
    if hasattr(result, "to_dict"):
        diff_dict = result.to_dict()
    else:
        diff_dict = {
            "summary": getattr(result, "summary", ""),
            "is_identical": getattr(result, "is_identical", False),
        }

    diff_dict["new_anomalies"] = new_items
    diff_dict["resolved_anomalies"] = resolved_items
    diff_dict["common_anomalies"] = common_items

    return {
        "protocol": protocol,
        "timestamp": timestamp,
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "diff": diff_dict,
    }


def format_protocol_diff_json(
    protocol: str,
    result: Any,
    *,
    baseline_report: Any = None,
    candidate_report: Any = None,
    baseline_name: str = "Baseline",
    candidate_name: str = "Candidate",
    timestamp: str | None = None,
    indent: int = 2,
) -> str:
    """將協定差分結果格式化為 JSON 字串。"""
    data = format_protocol_diff_dict(
        protocol,
        result,
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        baseline_name=baseline_name,
        candidate_name=candidate_name,
        timestamp=timestamp,
    )
    return json.dumps(data, indent=indent, ensure_ascii=False)


def format_protocol_diff_markdown(
    protocol: str,
    result: Any,
    *,
    baseline_name: str = "Baseline",
    candidate_name: str = "Candidate",
) -> str:
    """將協定差分結果格式化為可下載的 Markdown 報告。"""
    new_items, resolved_items, common_items = _diff_lists(protocol, result)
    lines = [
        f"# {protocol} A/B 對比報告（Protocol Diff Report）",
        "",
        f"- **Baseline（基準）**：{baseline_name}",
        f"- **Candidate（待測）**：{candidate_name}",
        f"- **分析摘要（Summary）**：{result.summary}",
        "",
        "## 指標（Metrics）",
        "",
    ]
    if protocol == "I2C":
        lines.append(
            f"- 交易數：{result.baseline_transaction_count} -> {result.candidate_transaction_count}"
        )
        lines.append(f"- 交易數變化：{result.transaction_count_delta:+d}")
        lines.append(f"- 位址變更：{len(result.address_changes)}")
    elif protocol == "SPI":
        lines.append(f"- 交易數變化：{result.transaction_count_delta:+d}")
        lines.append(f"- Baseline 晶片：{result.baseline_detected_chip or '未識別'}")
        lines.append(f"- Candidate 晶片：{result.candidate_detected_chip or '未識別'}")
    elif protocol == "UART":
        lines.append(f"- 崩潰類型：{result.baseline_crash_type} -> {result.candidate_crash_type}")
        lines.append(
            f"- 故障位址：{result.baseline_fault_address or 'N/A'} -> "
            f"{result.candidate_fault_address or 'N/A'}"
        )
    elif protocol == "PCIe":
        lines.append(f"- Vendor 變更：{result.vendor_changed}")
        lines.append(f"- Device 變更：{result.device_changed}")
        lines.append(f"- Link 降級變更：{result.link_degradation_changed}")
        lines.append(f"- Baseline Link：{result.baseline_link_summary}")
        lines.append(f"- Candidate Link：{result.candidate_link_summary}")
    elif protocol == "MCTP":
        lines.append(f"- 訊息數變化：{result.message_count_delta:+d}")
        lines.append(f"- 協定模式變更：{result.protocol_mode_changed}")
    for title, items in (
        ("新增項目（New）", new_items),
        ("已解決項目（Resolved）", resolved_items),
        ("共同項目（Common）", common_items),
    ):
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {item}" for item in items) if items else lines.append("- 無")
    if protocol == "I2C" and result.address_changes:
        lines.extend(["", "## 位址變更（Address Changes）", ""])
        lines.extend(f"- {item}" for item in result.address_changes)
    return "\n".join(lines) + "\n"


def _render_details(protocol: str, result: Any) -> None:
    new_items, resolved_items, common_items = _diff_lists(protocol, result)
    labels: tuple[tuple[str, str, list[str]], ...] = (
        ("diff_section_new", "新增項目（New）", new_items),
        ("diff_section_resolved", "已解決項目（Resolved）", resolved_items),
        ("diff_section_common", "共同項目（Common）", common_items),
    )
    if protocol == "I2C" and result.address_changes:
        labels += (
            ("diff_section_address_changes", "位址變更（Address Changes）", result.address_changes),
        )
    for key, fallback, items in labels:
        label = _tr(key, fallback)
        with st.expander(f"{label}（{len(items)}）", expanded=bool(items)):
            if items:
                for item in items:
                    st.write(f"- {item}")
            else:
                st.caption(_tr("diff_section_none", "無"))


def _render_metrics(protocol: str, result: Any) -> None:
    new_items, resolved_items, common_items = _diff_lists(protocol, result)
    if protocol == "UART":
        columns = st.columns(4)
        columns[0].metric(_tr("diff_metric_new_symbols", "新增符號"), len(new_items))
        columns[1].metric(_tr("diff_metric_resolved_symbols", "已解決符號"), len(resolved_items))
        columns[2].metric(_tr("diff_metric_common_symbols", "共同符號"), len(common_items))
        status_label = (
            _tr("diff_status_changed", "變更")
            if result.fault_address_changed
            else _tr("diff_status_identical", "相同")
        )
        columns[3].metric(_tr("diff_metric_fault_address", "故障位址"), status_label)
        return
    if protocol == "PCIe":
        columns = st.columns(4)
        columns[0].metric(_tr("diff_metric_new_aer", "新增 AER 錯誤"), len(new_items))
        columns[1].metric(_tr("diff_metric_resolved_aer", "已解決 AER 錯誤"), len(resolved_items))
        columns[2].metric(_tr("diff_metric_common_aer", "共同 AER 錯誤"), len(common_items))
        status_label = (
            _tr("diff_status_changed", "變更")
            if result.link_degradation_changed
            else _tr("diff_status_identical", "相同")
        )
        columns[3].metric(_tr("diff_metric_link_degradation", "Link 降級"), status_label)
        return
    if protocol == "MCTP":
        columns = st.columns(4)
        columns[0].metric(_tr("diff_metric_new_errors", "新增錯誤"), len(new_items))
        columns[1].metric(_tr("diff_metric_resolved_errors", "已解決錯誤"), len(resolved_items))
        columns[2].metric(_tr("diff_metric_common_errors", "共同錯誤"), len(common_items))
        columns[3].metric(
            _tr("diff_metric_message_count_delta", "訊息數變化"), f"{result.message_count_delta:+d}"
        )
        return
    columns = st.columns(4)
    columns[0].metric(_tr("diff_metric_new_anomalies", "新增異常"), len(new_items))
    columns[1].metric(_tr("diff_metric_resolved_anomalies", "已解決異常"), len(resolved_items))
    columns[2].metric(_tr("diff_metric_common_anomalies", "共同異常"), len(common_items))
    columns[3].metric(
        _tr("diff_metric_tx_count_delta", "交易數變化"), f"{result.transaction_count_delta:+d}"
    )


def render() -> None:
    st.header(_tr("title_protocol_diff", "協定 A/B 對比分析（Protocol Diff）"))
    protocol = st.selectbox(
        _tr("protocol_diff_select_protocol", "選擇協定"),
        _PROTOCOLS,
        key="protocol_diff_protocol",
    )
    if st.button(
        _tr("protocol_diff_load_sample", "載入示範對比資料"),
        key="protocol_diff_load_sample",
        help=_tr("protocol_diff_load_sample_help", "載入套件內建的 Golden 與 Failing 示範資料"),
    ):
        if protocol == "I2C":
            golden_sample, failing_sample = load_waveform_diff_samples()
            st.session_state["protocol_diff_baseline_text"] = golden_sample
            st.session_state["protocol_diff_candidate_text"] = failing_sample
        elif protocol == "UART":
            st.session_state["protocol_diff_baseline_text"] = load_uart_sample("kernel-panic")
            st.session_state["protocol_diff_candidate_text"] = load_uart_sample("hardfault")
        elif protocol == "PCIe":
            st.session_state["protocol_diff_baseline_text"] = load_pcie_lspci_sample()
            st.session_state["protocol_diff_candidate_text"] = load_pcie_lspci_sample()
        elif protocol == "MCTP":
            st.session_state["protocol_diff_baseline_text"] = load_mctp_sample("mctp-pldm")
            st.session_state["protocol_diff_candidate_text"] = load_mctp_sample("ipmb")
        elif protocol == "SPI":
            sample = load_spi_sample()
            st.session_state["protocol_diff_baseline_text"] = sample
            st.session_state["protocol_diff_candidate_text"] = sample
        st.session_state.pop("protocol_diff_baseline_file", None)
        st.session_state.pop("protocol_diff_candidate_file", None)
        st.session_state["protocol_diff_sample_active"] = True

    if st.session_state.get("protocol_diff_sample_active"):
        st.info(_tr("protocol_diff_sample_loaded", "已載入內建示範對比資料！"))

    if protocol == "UART":
        file_types = ["txt", "log"]
    elif protocol in ("PCIe", "MCTP"):
        file_types = ["txt", "hex", "log"]
    else:
        file_types = ["csv", "txt"]
    columns = st.columns(2)
    uploaded: list[Any] = []
    pasted: list[str] = []
    for index, (column, role) in enumerate(zip(columns, ("baseline", "candidate"))):
        with column:
            st.subheader(
                _tr(
                    f"protocol_diff_{role}",
                    "Baseline（基準）" if role == "baseline" else "Candidate（待測）",
                )
            )
            uploaded.append(
                st.file_uploader(
                    _tr("diff_uploader_file_label", f"上傳 {role} 檔案", role=role),
                    type=file_types,
                    max_upload_size=MAX_UPLOAD_MIB,
                    key=f"protocol_diff_{role}_file",
                )
            )
            pasted.append(
                st.text_area(
                    _tr("diff_pasted_text_label", "或貼上內容"),
                    height=180,
                    key=f"protocol_diff_{role}_text",
                )
            )

    if not st.button(_tr("btn_analyze", "開始分析"), key="protocol_diff_analyze"):
        render_page_footer()
        return
    texts: list[str] = []
    names: list[str] = []
    try:
        for file, text, role in zip(uploaded, pasted, ("Baseline", "Candidate")):
            if file is not None:
                texts.append(_uploaded_text(file))
                names.append(str(file.name))
            elif text.strip():
                texts.append(validate_pasted_text(text, label=f"{role} 內容"))
                names.append(f"{role} 貼上內容")
            else:
                raise ValueError(f"請提供 {role} 檔案或貼上內容")
        reports = [
            _analyze_input(protocol, text, source_name=name) for text, name in zip(texts, names)
        ]
        result = _compare(protocol, reports[0], reports[1])
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        st.error(f"對比分析失敗：{exc}")
        render_page_footer()
        return

    if result.is_identical:
        st.success(f"✔ {result.summary}")
    else:
        st.warning(f"⚠ {result.summary}")
    _render_metrics(protocol, result)
    summary_title = _tr("diff_summary_label", "分析摘要")
    st.markdown(f"**{summary_title}**：{result.summary}")
    _render_details(protocol, result)
    markdown = format_protocol_diff_markdown(
        protocol,
        result,
        baseline_name=names[0],
        candidate_name=names[1],
    )
    json_report = format_protocol_diff_json(
        protocol,
        result,
        baseline_report=reports[0],
        candidate_report=reports[1],
        baseline_name=names[0],
        candidate_name=names[1],
    )
    col_md, col_json = st.columns(2)
    with col_md:
        st.download_button(
            _tr("protocol_diff_download_report", "下載 Markdown 對比報告"),
            data=markdown,
            file_name=f"{protocol.lower()}_protocol_diff_report.md",
            mime="text/markdown",
            key="protocol_diff_download_report",
        )
    with col_json:
        st.download_button(
            _tr("protocol_diff_download_json_report", "下載 JSON 差異報告"),
            data=json_report,
            file_name=f"{protocol.lower()}_protocol_diff_report.json",
            mime="application/json",
            key="protocol_diff_download_json_report",
        )
    render_page_footer()


__all__ = [
    "format_protocol_diff_dict",
    "format_protocol_diff_json",
    "format_protocol_diff_markdown",
    "render",
]
