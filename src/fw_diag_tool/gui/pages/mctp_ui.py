from __future__ import annotations

import dataclasses

import streamlit as st

from fw_diag_tool.gui.notifications import show_error_toast, show_success_toast
from fw_diag_tool.gui.shared import (
    _localize_mctp_error,
    render_guide_expander,
    render_page_footer,
    render_session_controls,
)
from fw_diag_tool.gui.uploads import (
    MAX_TEXT_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.mctp.statistics import compute_mctp_statistics
from fw_diag_tool.reporting.csv_export import export_mctp_csv
from fw_diag_tool.resources import load_mctp_sample


def render() -> None:
    st.header("伺服器管理協定解碼：MCTP（DSP0236；PLDM／SPDM）與 IPMB")
    render_guide_expander(
        "chapters/ch05_mctp_ipmb.md", "📖 點擊展開：MCTP 與 IPMB 伺服器協定解析教學"
    )
    m_sample = load_mctp_sample("mctp-pldm")
    m_col1, m_col2 = st.columns([3, 1])
    with m_col1:
        uploaded_mctp = st.file_uploader(
            "上傳 MCTP/IPMB Hex Dump 檔案",
            type=["txt", "hex", "log"],
        )
    with m_col2:
        use_mctp_sample = st.button(
            "📋 載入內建範例",
            key="mctp_load_sample",
            help="載入內建 MCTP PLDM 十六進位範例封包",
        )
    if use_mctp_sample:
        st.session_state["mctp_sample_active"] = True
        st.info("已載入內建 MCTP／IPMB 範例！")

    m_pasted = st.text_area(
        "請貼上 MCTP／IPMB 封包的十六進位位元組（Hex Dump；每行一個完整封包）：",
        height=150,
        max_chars=MAX_TEXT_BYTES,
        value=m_sample,
        help=(
            "每行一個封包；位元組可用空白、逗號或分號分隔，也可使用 0x 前綴。"
            "請保留原始擷取資料（capture）與協定標頭（header）供核對。"
        ),
    )
    m_raw = m_pasted
    if uploaded_mctp is not None:
        try:
            m_raw = decode_uploaded_text(
                uploaded_mctp,
                allowed_extensions={".txt", ".hex", ".log"},
            )
        except ValueError as exc:
            st.error(f"MCTP／IPMB 檔案讀取錯誤：{exc}")
    st.download_button(
        "下載內建 MCTP／IPMB 範例",
        data=m_sample,
        file_name="mctp_ipmb_minimal.hex",
        mime="text/plain",
        key="mctp_download_example",
    )
    m_protocol_mode = st.selectbox(
        "協定模式（Protocol mode）",
        ["auto", "mctp", "ipmb"],
        format_func=lambda value: {
            "auto": "自動判斷（auto；依結構／Checksum 證據）",
            "mctp": "強制 MCTP（DSP0236）",
            "ipmb": "強制 IPMB（IPMI v2.0／Checksum）",
        }[value],
        help="自動判斷會依 MCTP Header Version 與 IPMB Checksum 證據選擇協定；必要時可強制指定模式。",
        key="mctp_protocol_mode",
    )
    st.caption(
        "證據範圍：本頁只根據貼上的十六進位內容離線解碼（offline decode）MCTP／IPMB；"
        "可呈現 DSP0236 標頭（Header）、EID、SOM/EOM/Seq/Tag、PLDM 欄位、"
        "SPDM 訊息類型（message type）與 IPMB Checksum。"
        "報告屬輸入 bytes 的解碼／重建證據（Source-provided／Reconstructed），"
        "不是實體鏈路的 Measured 量測；不會確認 BMC／端點的即時狀態，也不能單靠一行封包證明根因。"
        "請保留原始擷取資料（capture）、時間戳與協定設定，依 DSP0236／PLDM／SPDM／IPMB 規格人工核對。"
    )
    execute_decode = st.button("執行 MCTP／IPMB 伺服器管理協定解碼")
    if (execute_decode or use_mctp_sample) and m_raw.strip():
        try:
            m_report = ServerMgmtParser.parse_text_dump(
                validate_pasted_text(m_raw, label="MCTP/IPMB 十六進位輸入"),
                protocol_mode=m_protocol_mode,
            )
        except (TypeError, ValueError) as exc:
            st.error(f"MCTP／IPMB 輸入錯誤：{_localize_mctp_error(exc)}")
            show_error_toast("MCTP 分析失敗")
        else:
            if not m_report.total_frames:
                st.warning(
                    "沒有解出可辨識的 MCTP／IPMB 封包框架（frame）；"
                    "請確認每行都是完整的十六進位位元組（hex bytes），"
                    "並保留原始擷取資料（capture）與協定標頭（header）以便人工核對。"
                )
            else:
                show_success_toast("MCTP 分析完成")
                mctp_md = ServerMgmtReporter.to_markdown(m_report)
                st.markdown(mctp_md)
                st.download_button(
                    "下載 MCTP／IPMB Markdown 診斷報告",
                    data=mctp_md,
                    file_name="mctp_ipmb_report.md",
                    mime="text/markdown",
                    key="mctp_download_report",
                )
                st.download_button(
                    "📥 下載 CSV",
                    data=export_mctp_csv(m_report),
                    file_name="mctp_ipmb_analysis.csv",
                    mime="text/csv",
                    key="mctp_download_csv",
                    help="將分析結果匯出為 CSV 格式檔案",
                )
                mctp_stats = compute_mctp_statistics(m_report)
                with st.expander("📊 MCTP/IPMB 統計摘要", expanded=False):
                    s_c1, s_c2, s_c3, s_c4 = st.columns(4)
                    s_c1.metric("MCTP 封包總數", mctp_stats.total_packets)
                    s_c2.metric("重組訊息數", mctp_stats.total_messages)
                    s_c3.metric(
                        "訊息重組成功率",
                        f"{mctp_stats.reassembly_success_rate * 100:.1f}%",
                    )
                    s_c4.metric("IPMB 訊框數", mctp_stats.ipmb_frame_count)

                    s_c5, s_c6, s_c7 = st.columns(3)
                    s_c5.metric("Checksum 錯誤數", mctp_stats.checksum_error_count)
                    s_c6.metric("錯誤計數", mctp_stats.error_count)
                    s_c7.metric("警告計數", mctp_stats.warning_count)

                    if mctp_stats.message_type_distribution:
                        st.markdown("##### 訊息類型分佈（Message Type Distribution）")
                        for msg_type, count in sorted(mctp_stats.message_type_distribution.items()):
                            st.write(f"- **{msg_type}**: {count}")

                    if mctp_stats.eid_matrix:
                        st.markdown("##### 端點通訊統計（EID Matrix: Src -> Dest）")
                        for pair, count in sorted(mctp_stats.eid_matrix.items()):
                            st.write(f"- `{pair}`: {count} 個封包")

                report_dict = dataclasses.asdict(m_report)
                anomaly_count = (
                    len(m_report.errors)
                    + len(m_report.warnings)
                    + len(m_report.source_errors)
                    + sum(1 for m in m_report.mctp_messages if not m.is_complete or m.error)
                    + sum(
                        1
                        for f in m_report.ipmb_frames
                        if not f.checksum1_valid or not f.checksum2_valid
                    )
                )
                report_dict["protocol"] = "MCTP"
                report_dict["summary"] = (
                    m_report.summary_text or f"MCTP/IPMB 共 {m_report.total_frames} 框架"
                )
                report_dict["anomaly_count"] = anomaly_count
                render_session_controls(
                    protocol="MCTP",
                    report_data=report_dict,
                    config_data={"protocol_mode": m_protocol_mode},
                )
    else:
        render_session_controls(
            protocol="MCTP",
            report_data=None,
            config_data={"protocol_mode": m_protocol_mode},
        )

    render_page_footer()


__all__ = ["render"]
