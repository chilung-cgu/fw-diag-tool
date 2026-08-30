from __future__ import annotations

from typing import Any

import streamlit as st

from fw_diag_tool.gui.charts.stats_charts import distribution_bar, distribution_pie
from fw_diag_tool.gui.notifications import show_error_toast, show_success_toast
from fw_diag_tool.gui.sarif_export import render_sarif_download
from fw_diag_tool.gui.shared import (
    _localize_pcie_input_error,
    render_guide_expander,
    render_page_footer,
    render_session_controls,
)
from fw_diag_tool.gui.uploads import MAX_TEXT_BYTES, decode_uploaded_text, validate_pasted_text
from fw_diag_tool.pcie.diagnostics import diagnose_pcie_device
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.pcie.statistics import compute_pcie_statistics
from fw_diag_tool.pcie.topology import build_topology, topology_to_mermaid, topology_to_text_tree
from fw_diag_tool.reporting.csv_export import export_pcie_csv
from fw_diag_tool.resources import load_pcie_dmesg_sample, load_pcie_lspci_sample


def render() -> None:
    st.header("PCIe 設定空間、能力鏈結（Capability chain）與 AER 嚴重錯誤診斷")
    render_guide_expander(
        "chapters/ch07_pcie_aer.md", "📖 點擊展開：PCIe Config Space 與 AER 診斷教學"
    )
    lspci_mode = "貼上 lspci -xxxx／十六進位傾印（Hex Dump）"
    dmesg_mode = "貼上 Linux dmesg AER 錯誤日誌（AER Error Log）"
    if st.button(
        "載入內建 lspci PCIe 設定空間範例（Config Space）",
        key="pcie_lspci_load_sample",
        help="載入套件內建的最小 lspci PCIe 設定空間（Config Space），方便先確認廠商／裝置 ID（Vendor／Device ID）與能力（Capability）欄位。",
    ):
        st.session_state["pcie_input_mode"] = lspci_mode
        st.session_state["pcie_lspci_sample_active"] = True
        st.session_state["pcie_lspci_sample_content"] = load_pcie_lspci_sample()
        st.session_state["pcie_dmesg_sample_active"] = False
        st.session_state.pop("pcie_dmesg_sample_content", None)
        st.session_state["pcie_raw_input"] = st.session_state["pcie_lspci_sample_content"]
    if st.button(
        "載入內建 dmesg AER 範例",
        key="pcie_dmesg_load_sample",
        help="載入套件內建的最小 Linux AER 日誌（AER log），方便先確認輸出欄位與 TLP 標頭（TLP Header）。",
    ):
        st.session_state["pcie_input_mode"] = dmesg_mode
        st.session_state["pcie_dmesg_sample_active"] = True
        st.session_state["pcie_dmesg_sample_content"] = load_pcie_dmesg_sample()
        st.session_state["pcie_lspci_sample_active"] = False
        st.session_state.pop("pcie_lspci_sample_content", None)
        st.session_state["pcie_raw_input"] = st.session_state["pcie_dmesg_sample_content"]
    input_mode = st.radio(
        "輸入方式",
        [lspci_mode, dmesg_mode],
        key="pcie_input_mode",
    )
    if input_mode != dmesg_mode and st.session_state.get("pcie_dmesg_sample_active"):
        st.session_state["pcie_dmesg_sample_active"] = False
        st.session_state.pop("pcie_dmesg_sample_content", None)
        st.session_state["pcie_raw_input"] = ""
    if input_mode != lspci_mode and st.session_state.get("pcie_lspci_sample_active"):
        st.session_state["pcie_lspci_sample_active"] = False
        st.session_state.pop("pcie_lspci_sample_content", None)
        st.session_state["pcie_raw_input"] = ""
    lspci_sample = st.session_state.get("pcie_lspci_sample_content")
    if (
        input_mode == lspci_mode
        and st.session_state.get("pcie_lspci_sample_active") is True
        and isinstance(lspci_sample, str)
    ):
        st.info(
            "已載入內建 lspci PCIe 設定空間範例（Config Space）；可直接分析，或下載檔案後替換成自己的傾印。"
        )
        st.download_button(
            "下載 lspci PCIe 設定空間範例（Config Space）",
            data=lspci_sample,
            file_name="pcie_aer_lspci.txt",
            mime="text/plain",
            key="pcie_lspci_download_sample",
        )
    dmesg_sample = st.session_state.get("pcie_dmesg_sample_content")
    if (
        input_mode == dmesg_mode
        and st.session_state.get("pcie_dmesg_sample_active") is True
        and isinstance(dmesg_sample, str)
    ):
        st.info("已載入內建 dmesg AER 範例；可直接分析，或下載檔案後保存到自己的除錯紀錄。")
        st.download_button(
            "下載 dmesg AER 範例",
            data=dmesg_sample,
            file_name="pcie_aer_dmesg.log",
            mime="text/plain",
            key="pcie_dmesg_download_sample",
        )
    uploaded_file = st.file_uploader("上傳 lspci/dmesg 日誌檔案", type=["txt", "log", "dmesg"])
    if uploaded_file is not None:
        try:
            st.session_state["pcie_raw_input"] = decode_uploaded_text(
                uploaded_file, allowed_extensions={".txt", ".log", ".dmesg"}
            )
        except ValueError as exc:
            st.error(f"PCIe 檔案讀取錯誤：{exc}")
    raw_input = st.text_area(
        "輸入日誌或傾印內容（Log / Dump）：",
        height=200,
        max_chars=MAX_TEXT_BYTES,
        key="pcie_raw_input",
    )
    if st.button("執行 PCIe 分析") and raw_input.strip():
        try:
            raw_input = validate_pasted_text(raw_input, label="PCIe 日誌／傾印（log/dump）")
        except (TypeError, ValueError) as exc:
            st.error(f"PCIe 輸入錯誤：{_localize_pcie_input_error(exc)}")
            show_error_toast("PCIe 分析失敗")
            st.stop()
        if input_mode == dmesg_mode:
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(
                f"Linux 核心 dmesg AER 診斷結果（Kernel dmesg AER 診斷結果；共 {len(events)} 個事件）"
            )
            if not events:
                st.warning(
                    "沒有找到可解析的 AER 事件；請確認貼上的內容包含完整核心 dmesg 日誌（kernel dmesg）。"
                )
            stats = compute_pcie_statistics([], dmesg_events=events)
            with st.expander("📊 PCIe 統計摘要", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.metric("AER 錯誤總數", stats.total_aer_errors)
                c2.metric(
                    "不可更正 / 可更正", f"{stats.uncorrectable_count} / {stats.correctable_count}"
                )
                rate_str = (
                    f"{stats.error_rate_per_sec:.4f} 次/秒"
                    if stats.error_rate_per_sec is not None
                    else "N/A"
                )
                c3.metric("錯誤發生率", rate_str)
            pcie_dmesg_md = PCIeReporter.format_dmesg_events(events)
            show_success_toast("PCIe AER 分析完成")
            st.markdown(pcie_dmesg_md)
            st.download_button(
                "下載 PCIe dmesg Markdown 診斷報告",
                data=pcie_dmesg_md,
                file_name="pcie_dmesg_aer_report.md",
                mime="text/markdown",
                key="pcie_dmesg_download_report",
            )
            st.download_button(
                "📥 下載 CSV",
                data=export_pcie_csv([], events=events),
                file_name="pcie_aer_events.csv",
                mime="text/csv",
                key="pcie_dmesg_download_csv",
                help="將分析結果匯出為 CSV 格式檔案",
            )
            dmesg_findings = [
                {
                    "code": "PCIE_AER_DMESG",
                    "title": ev.error_name,
                    "severity": "CRITICAL"
                    if "Fatal" in ev.severity
                    else ("ERROR" if "Uncorr" in ev.severity else "WARNING"),
                    "message": f"[{ev.bdf}] {ev.error_name}: {ev.root_cause_guide or ev.raw_line}",
                }
                for ev in events
            ]
            render_sarif_download(dmesg_findings, protocol="PCIe", filename_prefix="pcie_dmesg")
            report_dict = {
                "protocol": "PCIe",
                "mode": "dmesg",
                "summary": f"Linux 核心 dmesg AER 診斷結果（共 {len(events)} 個事件）",
                "anomaly_count": len(events),
                "events": [
                    {
                        "timestamp": ev.timestamp,
                        "bdf": ev.bdf,
                        "severity": ev.severity,
                        "error_name": ev.error_name,
                        "tlp_header": ev.tlp_header,
                        "raw_line": ev.raw_line,
                        "root_cause_guide": ev.root_cause_guide,
                    }
                    for ev in events
                ],
            }
            render_session_controls(
                protocol="PCIe",
                report_data=report_dict,
                config_data={"mode": "dmesg"},
            )
        else:
            try:
                devices = PCIeAnalyzer.parse_multi_lspci_text(raw_input)
                if not devices:
                    bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(raw_input)
                    devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
            except (TypeError, ValueError) as exc:
                st.error(f"PCIe 輸入錯誤：{_localize_pcie_input_error(exc)}")
                show_error_toast("PCIe 分析失敗")
                devices = []
            if any(cfg.data_quality_issues for cfg in devices):
                quality_messages = "；".join(
                    _localize_pcie_input_error(issue)
                    for cfg in devices
                    for issue in cfg.data_quality_issues
                )
                st.error(
                    "PCIe 輸入錯誤：部分裝置無法完整解碼。"
                    f"{quality_messages}；請先檢查資料品質限制（Data Quality Limitations），"
                    "不要把空欄位當成有效的 Config Space。"
                )
            all_findings: list[dict[str, Any]] = []
            devices_data: list[dict[str, Any]] = []
            for cfg_index, cfg in enumerate(devices, 1):
                dev_findings = diagnose_pcie_device(cfg)
                for f in dev_findings:
                    all_findings.append(
                        {
                            "code": f.get("type", "PCIE_DIAG_ISSUE"),
                            "title": f.get("name", "PCIe Diagnostic Finding"),
                            "severity": f.get("severity", "WARNING"),
                            "message": f.get("guide", f.get("name", "")),
                        }
                    )
                devices_data.append(
                    {
                        "index": cfg_index,
                        "vendor_id": f"0x{cfg.vendor_id:04X}",
                        "device_id": f"0x{cfg.device_id:04X}",
                        "header_type": cfg.header_type.name
                        if hasattr(cfg.header_type, "name")
                        else str(cfg.header_type),
                        "bdf": cfg.bdf,
                        "findings": dev_findings,
                        "is_degraded": cfg.link_info.is_degraded if cfg.link_info else False,
                    }
                )
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "廠商／裝置 ID（Vendor / Device ID）",
                    f"0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}",
                )
                c2.metric(
                    "標頭類型（Header Type）",
                    PCIeReporter.localize_header_type(cfg.header_type),
                )
                c3.metric(
                    "能力數量（Capabilities）",
                    len(cfg.standard_capabilities) + len(cfg.extended_capabilities),
                )
                if cfg.link_info and cfg.link_info.is_degraded:
                    st.error(
                        f"🚨 {PCIeReporter.localize_link_reason(cfg.link_info.degradation_reason)}"
                    )
                pcie_cfg_md = PCIeReporter.to_markdown(cfg)
                st.markdown(pcie_cfg_md)
                st.download_button(
                    f"下載 PCIe 診斷報告 #{cfg_index}",
                    data=pcie_cfg_md,
                    file_name=f"pcie_config_report_{cfg_index}.md",
                    mime="text/markdown",
                    key=f"pcie_config_download_{cfg_index}",
                )
            if devices:
                roots = build_topology(devices)
                with st.expander("🌳 PCIe 拓撲樹（PCIe Topology Tree）", expanded=True):
                    tree_text = topology_to_text_tree(roots)
                    st.code(tree_text or "（無法從輸入資料建立拓撲）", language="text")
                    if roots:
                        st.code(topology_to_mermaid(roots), language="mermaid")
                st.download_button(
                    "📥 下載 CSV",
                    data=export_pcie_csv(devices),
                    file_name="pcie_devices.csv",
                    mime="text/csv",
                    key="pcie_devices_download_csv",
                    help="將分析結果匯出為 CSV 格式檔案",
                )
                stats = compute_pcie_statistics(devices)
                with st.expander("📊 PCIe 統計摘要", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("裝置總數", stats.device_count)
                    c2.metric("AER 錯誤總數", stats.total_aer_errors)
                    c3.metric(
                        "不可更正 / 可更正",
                        f"{stats.uncorrectable_count} / {stats.correctable_count}",
                    )
                    c4.metric("連線降級數量", stats.link_degradation_count)
                    if stats.topology_summary:
                        st.markdown("**裝置類別分佈（Topology Summary）**")
                        st.plotly_chart(
                            distribution_bar(
                                stats.topology_summary,
                                "裝置類別分佈（Topology Summary）",
                                horizontal=True,
                            ),
                            use_container_width=True,
                        )
                        for cls_name, count in sorted(stats.topology_summary.items()):
                            st.write(f"- {PCIeReporter.localize_class_name(cls_name)}: {count}")
                    if stats.link_speed_distribution:
                        st.markdown("**速率世代分佈（Link Speed Distribution）**")
                        st.plotly_chart(
                            distribution_pie(
                                stats.link_speed_distribution,
                                "速率世代分佈（Link Speed Distribution）",
                            ),
                            use_container_width=True,
                        )
                        for spd, count in sorted(stats.link_speed_distribution.items()):
                            st.write(f"- {spd}: {count}")
                render_sarif_download(all_findings, protocol="PCIe", filename_prefix="pcie_config")
                total_anomalies = len(all_findings)
                report_dict = {
                    "protocol": "PCIe",
                    "mode": "lspci",
                    "summary": f"PCIe 設定空間分析（共 {len(devices)} 個裝置，{total_anomalies} 項發現）",
                    "anomaly_count": total_anomalies,
                    "devices": devices_data,
                }
                render_session_controls(
                    protocol="PCIe",
                    report_data=report_dict,
                    config_data={"mode": "lspci"},
                )
    else:
        render_session_controls(
            protocol="PCIe",
            report_data=None,
            config_data={"mode": input_mode},
        )

    render_page_footer()


__all__ = ["render"]
