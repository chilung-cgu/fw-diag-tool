"""統一多協定診斷報告產生器（Unified Multi-Protocol Report Generator）GUI 頁面。

整合 I2C、SPI、UART、PCIe、MCTP 等多協定診斷結果，計算整體健康分數與簽核檢查清單，並匯出 Markdown 與 HTML 報告。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from fw_diag_tool.gui.page_index import render_breadcrumb
from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES
from fw_diag_tool.i18n import t
from fw_diag_tool.reporting.unified_report import (
    ProtocolResult,
    UnifiedReport,
    analyze_file_for_unified_report,
    build_unified_report,
    detect_file_protocol,
)

MAX_UPLOAD_MIB = max(1, MAX_UPLOAD_BYTES // (1024 * 1024))


def _tr(key: str, fallback: str, **kwargs: Any) -> str:
    translated = t(key, domain="gui", **kwargs)
    return fallback if translated == key else translated


# Sample preset datasets for demonstration
_SAMPLE_I2C_DATA = """Time,Packet ID,Address,Data,Read/Write,ACK/NAK
0.000100,1,0x50,0x00,Write,ACK
0.000200,1,0x50,0x55,Read,ACK
0.000300,1,0x50,0xAA,Read,ACK"""

_SAMPLE_UART_DATA = """[   12.345678] Kernel panic - not syncing: Fatal exception in interrupt
[   12.345680] CPU: 0 PID: 123 Comm: fw_worker Tainted: G        W  O
[   12.345685] Call Trace:
[   12.345690]  [<ffffffff81054321>] dump_stack+0x12/0x18
[   12.345695]  [<ffffffff81065432>] panic+0xab/0x210"""

_SAMPLE_PCIE_DATA = """00:01.0 PCI bridge: Intel Corporation PCIe Root Port (prog-if 00 [Normal decode])
00: 86 80 01 19 07 00 10 00 00 00 04 06 00 00 01 00
10: 00 00 00 00 00 00 00 00 00 01 01 00 f0 00 00 00
100: 01 00 01 10 00 00 00 00 00 00 00 00 00 00 00 00
110: 20 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"""

_SAMPLE_SPI_DATA = """Time,MOSI,MISO,CS,Description
0.000001,0x06,0xFF,0,WREN
0.000005,0x02,0xFF,0,Page Program
0.000010,0x00,0xFF,0,Address Byte 1
0.000015,0x00,0xFF,0,Address Byte 2
0.000020,0x00,0xFF,0,Address Byte 3
0.000025,0x55,0xFF,0,Data Byte"""

_SAMPLE_MCTP_DATA = """DSP0236 MCTP Packet Dump
Timestamp: 1629876543.123
Header: 01 00 08 c8 0a 14 00 00
Payload: 01 00 00 00"""


def render() -> None:
    """Streamlit 統一多協定報告頁面渲染入口。"""
    render_breadcrumb(
        _tr("nav_category_advanced", "進階分析 (Advanced Analysis)"),
        _tr("title_unified_report", "統一多協定報告"),
    )

    st.header(
        _tr(
            "title_unified_report_full",
            "統一多協定診斷報告產生器（Unified Multi-Protocol Report Generator）",
        )
    )
    st.caption(
        _tr(
            "desc_unified_report",
            "整合 I2C、SPI、UART、PCIe、MCTP 等多協定診斷結果，計算整體健康分數與簽核檢查清單，產出標準化 Markdown 與 HTML 報告。",
        )
    )

    st.markdown("---")

    tab_multi, tab_dedicated, tab_sample = st.tabs(
        [
            "📁 " + _tr("tab_multi_upload", "批次多檔上傳 (Multi-File)"),
            "🎛 " + _tr("tab_dedicated_upload", "各協定獨立上傳 (Per-Protocol)"),
            "📋 " + _tr("tab_sample_presets", "載入範例資料 (Preset Examples)"),
        ]
    )

    files_to_process: list[tuple[str, str, str]] = []  # (filename, content, protocol_hint)

    with tab_multi:
        st.markdown("##### " + _tr("lbl_multi_upload_title", "批次多協定日誌／擷取檔上傳"))
        uploaded_multi = st.file_uploader(
            _tr(
                "lbl_multi_upload_desc",
                "上傳多個檔案（支援 .csv, .log, .txt, .hex），系統將自動識別協定類型",
            ),
            type=["csv", "log", "txt", "hex"],
            accept_multiple_files=True,
            key="unified_multi_files",
        )
        if uploaded_multi:
            for uf in uploaded_multi:
                text_content = uf.getvalue().decode("utf-8", errors="replace")
                proto = detect_file_protocol(uf.name, text_content)
                files_to_process.append((uf.name, text_content, proto))
            st.success(f"已選擇 {len(uploaded_multi)} 個檔案進行整合分析。")

    with tab_dedicated:
        st.markdown("##### " + _tr("lbl_dedicated_upload_title", "指定協定專用上傳區"))
        col1, col2 = st.columns(2)
        with col1:
            f_i2c = st.file_uploader("I2C / PMBus (.csv / .txt)", type=["csv", "txt"], key="u_i2c")
            if f_i2c:
                files_to_process.append(
                    (f_i2c.name, f_i2c.getvalue().decode("utf-8", errors="replace"), "I2C")
                )
            f_spi = st.file_uploader("SPI Flash (.csv / .txt)", type=["csv", "txt"], key="u_spi")
            if f_spi:
                files_to_process.append(
                    (f_spi.name, f_spi.getvalue().decode("utf-8", errors="replace"), "SPI")
                )
            f_uart = st.file_uploader(
                "UART Crash Log (.log / .txt)", type=["log", "txt"], key="u_uart"
            )
            if f_uart:
                files_to_process.append(
                    (f_uart.name, f_uart.getvalue().decode("utf-8", errors="replace"), "UART")
                )
        with col2:
            f_pcie = st.file_uploader(
                "PCIe lspci / AER (.log / .txt / .hex)", type=["log", "txt", "hex"], key="u_pcie"
            )
            if f_pcie:
                files_to_process.append(
                    (f_pcie.name, f_pcie.getvalue().decode("utf-8", errors="replace"), "PCIe")
                )
            f_mctp = st.file_uploader(
                "MCTP / IPMB (.log / .txt / .hex)", type=["log", "txt", "hex"], key="u_mctp"
            )
            if f_mctp:
                files_to_process.append(
                    (f_mctp.name, f_mctp.getvalue().decode("utf-8", errors="replace"), "MCTP")
                )

    with tab_sample:
        st.markdown("##### " + _tr("lbl_sample_title", "快速載入多協定範例資料進行體驗"))
        sample_options = st.multiselect(
            _tr("lbl_sample_select", "選擇要納入統一報告的範例協定"),
            options=["I2C", "SPI", "UART", "PCIe", "MCTP"],
            default=["I2C", "UART", "PCIe", "SPI", "MCTP"],
            key="sample_protocols_selected",
        )
        if sample_options:
            if "I2C" in sample_options:
                files_to_process.append(("sample_i2c_trace.csv", _SAMPLE_I2C_DATA, "I2C"))
            if "UART" in sample_options:
                files_to_process.append(("sample_kernel_panic.log", _SAMPLE_UART_DATA, "UART"))
            if "PCIe" in sample_options:
                files_to_process.append(("sample_pcie_config.log", _SAMPLE_PCIE_DATA, "PCIe"))
            if "SPI" in sample_options:
                files_to_process.append(("sample_spi_trace.csv", _SAMPLE_SPI_DATA, "SPI"))
            if "MCTP" in sample_options:
                files_to_process.append(("sample_mctp_dump.txt", _SAMPLE_MCTP_DATA, "MCTP"))
            st.info(f"已載入 {len(files_to_process)} 個協定範例資料。")

    st.markdown("---")

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        generate_clicked = st.button(
            _tr("btn_generate_unified_report", "🚀 產生統一多協定報告"),
            type="primary",
        )

    if generate_clicked:
        if not files_to_process:
            st.warning(_tr("msg_no_files_uploaded", "請先上傳檔案或載入範例資料再產生報告。"))
            render_page_footer()
            return

        with (
            st.spinner(_tr("msg_generating_report", "正在平行分析各協定數據並編制統一報告…")),
            tempfile.TemporaryDirectory() as temp_dir_str,
        ):
            temp_dir = Path(temp_dir_str)
            results: list[ProtocolResult] = []
            for filename, content, proto in files_to_process:
                file_p = temp_dir / filename
                file_p.write_text(content, encoding="utf-8")
                res = analyze_file_for_unified_report(file_p, protocol=proto)
                results.append(res)

            report = build_unified_report(results)
            st.session_state["unified_report"] = report
            st.success(_tr("msg_report_ready", "統一多協定診斷報告已成功產生！"))

    report_obj: UnifiedReport | None = st.session_state.get("unified_report")

    if report_obj is not None:
        st.markdown(
            "### "
            + _tr("lbl_report_dashboard_title", "診斷報告總覽 (Diagnostic Executive Overview)")
        )

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            m1.metric(
                _tr("lbl_health_score", "整體健康分數 (Health Score)"),
                f"{report_obj.overall_health_score:.1f} / 100.0",
            )
        with m2:
            status_badge = {
                "success": "✔ 正常 (PASS)",
                "warning": "⚠ 警告 (WARN)",
                "error": "✖ 異常 (FAIL)",
            }.get(report_obj.overall_status, report_obj.overall_status)
            m2.metric(_tr("lbl_overall_status", "整體狀態 (Overall Status)"), status_badge)
        with m3:
            m3.metric(
                _tr("lbl_protocol_count", "納入協定數 (Protocols)"), str(len(report_obj.results))
            )
        with m4:
            total_anomalies = sum(r.anomaly_count for r in report_obj.results)
            m4.metric(
                _tr("lbl_total_anomalies", "累計異常數 (Total Anomalies)"), str(total_anomalies)
            )

        st.markdown("#### " + _tr("lbl_export_section", "匯出與下載報告 (Export & Downloads)"))
        c_down1, c_down2 = st.columns(2)
        with c_down1:
            st.download_button(
                label=_tr("btn_download_unified_md", "⬇️ 下載 Markdown 報告 (.md)"),
                data=report_obj.to_markdown(),
                file_name="unified_fw_report.md",
                mime="text/markdown",
            )
        with c_down2:
            st.download_button(
                label=_tr("btn_download_unified_html", "⬇️ 下載完整 HTML 報告 (.html)"),
                data=report_obj.to_html(),
                file_name="unified_fw_report.html",
                mime="text/html",
            )

        st.markdown("---")
        st.markdown("### " + _tr("lbl_report_preview", "報告內容即時預覽 (Live Report Preview)"))

        preview_tab1, preview_tab2 = st.tabs(
            [
                "📄 " + _tr("tab_rendered_md", "視覺化排版 (Rendered)"),
                "📝 " + _tr("tab_raw_md", "原始 Markdown (Raw)"),
            ]
        )
        with preview_tab1:
            st.markdown(report_obj.to_markdown())
        with preview_tab2:
            st.code(report_obj.to_markdown(), language="markdown")

    render_page_footer()
