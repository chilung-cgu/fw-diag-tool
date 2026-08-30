from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.shared import (
    _localize_pcie_input_error,
    render_guide_expander,
)
from fw_diag_tool.gui.uploads import MAX_TEXT_BYTES, decode_uploaded_text, validate_pasted_text
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
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
        st.info("已載入內建 lspci PCIe 設定空間範例（Config Space）；可直接分析，或下載檔案後替換成自己的傾印。")
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
    uploaded_file = st.file_uploader(
        "上傳 lspci/dmesg 日誌檔案", type=["txt", "log", "dmesg"]
    )
    if uploaded_file is not None:
        try:
            st.session_state["pcie_raw_input"] = decode_uploaded_text(
                uploaded_file, allowed_extensions={".txt", ".log", ".dmesg"}
            )
        except ValueError as exc:
            st.error(f"PCIe 檔案讀取錯誤：{exc}")
    raw_input = st.text_area(
        "輸入日誌或傾印內容（Log / Dump）：", height=200, max_chars=MAX_TEXT_BYTES, key="pcie_raw_input"
    )
    if st.button("執行 PCIe 分析") and raw_input.strip():
        try:
            raw_input = validate_pasted_text(raw_input, label="PCIe 日誌／傾印（log/dump）")
        except (TypeError, ValueError) as exc:
            st.error(f"PCIe 輸入錯誤：{_localize_pcie_input_error(exc)}")
            st.stop()
        if input_mode == dmesg_mode:
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(
                f"Linux 核心 dmesg AER 診斷結果（Kernel dmesg AER 診斷結果；共 {len(events)} 個事件）"
            )
            if not events:
                st.warning("沒有找到可解析的 AER 事件；請確認貼上的內容包含完整核心 dmesg 日誌（kernel dmesg）。")
            pcie_dmesg_md = PCIeReporter.format_dmesg_events(events)
            st.markdown(pcie_dmesg_md)
            st.download_button(
                "下載 PCIe dmesg Markdown 診斷報告",
                data=pcie_dmesg_md,
                file_name="pcie_dmesg_aer_report.md",
                mime="text/markdown",
                key="pcie_dmesg_download_report",
            )
        else:
            try:
                devices = PCIeAnalyzer.parse_multi_lspci_text(raw_input)
                if not devices:
                    bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(raw_input)
                    devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
            except (TypeError, ValueError) as exc:
                st.error(f"PCIe 輸入錯誤：{_localize_pcie_input_error(exc)}")
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
            for cfg_index, cfg in enumerate(devices, 1):
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


__all__ = ["render"]
