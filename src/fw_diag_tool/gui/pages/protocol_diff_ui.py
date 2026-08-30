"""I2C、SPI、UART 協定 A/B 對比分析頁面。"""

from __future__ import annotations

import tempfile
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
from fw_diag_tool.spi.diff import SPIDiffEngine
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.diff import UARTDiffEngine
from fw_diag_tool.uart.parser import UARTCrashParser

MAX_UPLOAD_MIB = max(1, MAX_UPLOAD_BYTES // (1024 * 1024))
_PROTOCOLS = ("I2C", "SPI", "UART")


def _tr(key: str, fallback: str, **kwargs: Any) -> str:
    translated = t(key, domain="gui", **kwargs)
    return fallback if translated == key else translated


def _uploaded_text(uploaded: Any) -> str:
    return decode_uploaded_text(uploaded, allowed_extensions={".csv", ".txt", ".log"})


def _write_temp_input(text: str, suffix: str = ".csv") -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=suffix, delete=False) as handle:
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
    raise ValueError(f"不支援的協定：{protocol}")


def _compare(protocol: str, baseline: Any, candidate: Any) -> Any:
    if protocol == "I2C":
        return I2CDiffEngine.compare(baseline, candidate)
    if protocol == "SPI":
        return SPIDiffEngine.compare(baseline, candidate)
    if protocol == "UART":
        return UARTDiffEngine.compare(baseline, candidate)
    raise ValueError(f"不支援的協定：{protocol}")


def _diff_lists(protocol: str, result: Any) -> tuple[list[str], list[str], list[str]]:
    if protocol == "UART":
        return result.new_symbols, result.resolved_symbols, result.common_symbols
    return result.new_anomalies, result.resolved_anomalies, result.common_anomalies


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
        lines.append(f"- 交易數：{result.baseline_transaction_count} -> {result.candidate_transaction_count}")
        lines.append(f"- 交易數變化：{result.transaction_count_delta:+d}")
        lines.append(f"- 位址變更：{len(result.address_changes)}")
    elif protocol == "SPI":
        lines.append(f"- 交易數變化：{result.transaction_count_delta:+d}")
        lines.append(f"- Baseline 晶片：{result.baseline_detected_chip or '未識別'}")
        lines.append(f"- Candidate 晶片：{result.candidate_detected_chip or '未識別'}")
    else:
        lines.append(f"- 崩潰類型：{result.baseline_crash_type} -> {result.candidate_crash_type}")
        lines.append(
            f"- 故障位址：{result.baseline_fault_address or 'N/A'} -> "
            f"{result.candidate_fault_address or 'N/A'}"
        )
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
    labels: tuple[tuple[str, list[str]], ...] = (
        ("新增項目（New）", new_items),
        ("已解決項目（Resolved）", resolved_items),
        ("共同項目（Common）", common_items),
    )
    if protocol == "I2C" and result.address_changes:
        labels += (("位址變更（Address Changes）", result.address_changes),)
    for label, items in labels:
        with st.expander(f"{label}（{len(items)}）", expanded=bool(items)):
            if items:
                for item in items:
                    st.write(f"- {item}")
            else:
                st.caption("無")


def _render_metrics(protocol: str, result: Any) -> None:
    new_items, resolved_items, common_items = _diff_lists(protocol, result)
    if protocol == "UART":
        columns = st.columns(4)
        columns[0].metric("新增符號", len(new_items))
        columns[1].metric("已解決符號", len(resolved_items))
        columns[2].metric("共同符號", len(common_items))
        columns[3].metric("故障位址", "變更" if result.fault_address_changed else "相同")
        return
    columns = st.columns(4)
    columns[0].metric("新增異常", len(new_items))
    columns[1].metric("已解決異常", len(resolved_items))
    columns[2].metric("共同異常", len(common_items))
    columns[3].metric("交易數變化", f"{result.transaction_count_delta:+d}")


def render() -> None:
    st.header(_tr("title_protocol_diff", "協定 A/B 對比分析（Protocol Diff）"))
    protocol = st.selectbox(
        _tr("protocol_diff_select_protocol", "選擇協定"),
        _PROTOCOLS,
        key="protocol_diff_protocol",
    )
    file_types = ["txt", "log"] if protocol == "UART" else ["csv", "txt"]
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
                    f"上傳 {role} 檔案",
                    type=file_types,
                    max_upload_size=MAX_UPLOAD_MIB,
                    key=f"protocol_diff_{role}_file",
                )
            )
            pasted.append(
                st.text_area(
                    "或貼上內容",
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
            _analyze_input(protocol, text, source_name=name)
            for text, name in zip(texts, names)
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
    st.markdown(f"**分析摘要**：{result.summary}")
    _render_details(protocol, result)
    markdown = format_protocol_diff_markdown(
        protocol,
        result,
        baseline_name=names[0],
        candidate_name=names[1],
    )
    st.download_button(
        _tr("protocol_diff_download_report", "下載 Markdown 對比報告"),
        data=markdown,
        file_name=f"{protocol.lower()}_protocol_diff_report.md",
        mime="text/markdown",
        key="protocol_diff_download_report",
    )
    render_page_footer()


__all__ = ["format_protocol_diff_markdown", "render"]
