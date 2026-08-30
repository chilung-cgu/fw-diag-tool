from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool.gui.notifications import show_error_toast, show_success_toast
from fw_diag_tool.gui.sarif_export import render_sarif_download
from fw_diag_tool.gui.session_io import serialize_spi_session
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    analyze_spi_input,
    render_guide_expander,
    render_html_download,
    render_page_footer,
    render_pdf_download,
)
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.resources import load_spi_sample
from fw_diag_tool.session.session_manager import SessionManager
from fw_diag_tool.spi.diff import SPIDiffEngine
from fw_diag_tool.spi.reporter import SPIReporter

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)


def render() -> None:
    st.header("SPI／QSPI Flash 協定解析與寫入異常診斷")
    render_guide_expander(
        "chapters/ch08_spi_flash.md", "📖 點擊展開：SPI Flash 協定與狀態機診斷教學"
    )
    session_upload = st.file_uploader(
        "載入可重現 Session（.fwsession.json）",
        type=["json"],
        max_upload_size=SessionManager.MAX_SESSION_BYTES // (1024 * 1024),
        key="spi_session_upload",
    )
    if session_upload is not None:
        try:
            loaded_session = SessionManager.deserialize_session(session_upload.getvalue())
            st.info(
                f"已載入 Session：{loaded_session.name or 'SPI Analysis'}｜"
                f"工具版本：{loaded_session.tool_version}"
            )
            with st.expander("檢視 Session 報告摘要", expanded=False):
                st.json(loaded_session.report, expanded=False)
        except (TypeError, ValueError) as exc:
            st.error(f"無法載入 Session：{_localize_gui_error(exc, domain='session')}")
    spi_col1, spi_col2 = st.columns([3, 1])
    with spi_col1:
        uploaded_spi = st.file_uploader(
            "選擇 Saleae SPI CSV 檔案",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    with spi_col2:
        use_spi_sample = st.button("載入內建 SPI 測試波形")
    spi_page_size = st.number_input(
        "頁面大小（Page Size；bytes）",
        min_value=1,
        max_value=4096,
        value=256,
        step=1,
        help="請依實際 Flash datasheet 設定；這會影響 Page Program 跨頁風險判定。",
    )
    with st.expander("⚖️ SPI Before/After 對比分析", expanded=False):
        st.markdown("比對修復前後或正常／異常板卡的 SPI Trace，分析異常消除與交易計數變化。")
        diff_col1, diff_col2 = st.columns(2)
        with diff_col1:
            uploaded_baseline = st.file_uploader(
                "選擇 Baseline（修復前／正常）SPI CSV",
                type=["csv", "txt"],
                key="spi_diff_baseline_uploader",
            )
        with diff_col2:
            uploaded_candidate = st.file_uploader(
                "選擇 Candidate（修復後／待測）SPI CSV",
                type=["csv", "txt"],
                key="spi_diff_candidate_uploader",
            )

        if uploaded_baseline is not None and uploaded_candidate is not None:
            try:
                base_text = decode_uploaded_text(
                    uploaded_baseline, allowed_extensions={".csv", ".txt"}
                )
                cand_text = decode_uploaded_text(
                    uploaded_candidate, allowed_extensions={".csv", ".txt"}
                )
                base_rep = analyze_spi_input(base_text, int(spi_page_size))
                cand_rep = analyze_spi_input(cand_text, int(spi_page_size))
                diff_result = SPIDiffEngine.compare(base_rep, cand_rep)

                if diff_result.is_identical:
                    st.success(f"✔ {diff_result.summary}")
                elif len(diff_result.new_anomalies) > 0:
                    st.error(f"❌ {diff_result.summary}")
                elif len(diff_result.resolved_anomalies) > 0:
                    st.success(f"✅ {diff_result.summary}")
                else:
                    st.warning(f"⚠ {diff_result.summary}")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric(
                    "交易總數變化",
                    f"{cand_rep.summary.total_transactions}",
                    delta=f"{diff_result.transaction_count_delta:+d}",
                )
                m2.metric(
                    "Baseline 異常數",
                    f"{base_rep.summary.anomaly_count}",
                )
                m3.metric(
                    "Candidate 異常數",
                    f"{cand_rep.summary.anomaly_count}",
                    delta=f"{cand_rep.summary.anomaly_count - base_rep.summary.anomaly_count:+d}",
                    delta_color="inverse",
                )
                m4.metric(
                    "修復異常數",
                    f"{len(diff_result.resolved_anomalies)} 項",
                )

                if diff_result.new_anomalies:
                    st.error(
                        "🚨 **新增異常（New Anomalies in Candidate）**：\n"
                        + "\n".join(f"- {a}" for a in diff_result.new_anomalies)
                    )
                if diff_result.resolved_anomalies:
                    st.success(
                        "🎉 **已修復異常（Resolved Anomalies）**：\n"
                        + "\n".join(f"- {a}" for a in diff_result.resolved_anomalies)
                    )
                if diff_result.common_anomalies:
                    st.info(
                        "ℹ️ **兩者皆存在之異常（Common Anomalies）**：\n"
                        + "\n".join(f"- {a}" for a in diff_result.common_anomalies)
                    )

                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=["異常事件數", "讀取次數", "寫入次數", "抹除次數"],
                        y=[
                            base_rep.summary.anomaly_count,
                            base_rep.summary.read_count,
                            base_rep.summary.write_count,
                            base_rep.summary.erase_count,
                        ],
                        name="Baseline（基準）",
                        marker_color="#EF553B",
                    )
                )
                fig.add_trace(
                    go.Bar(
                        x=["異常事件數", "讀取次數", "寫入次數", "抹除次數"],
                        y=[
                            cand_rep.summary.anomaly_count,
                            cand_rep.summary.read_count,
                            cand_rep.summary.write_count,
                            cand_rep.summary.erase_count,
                        ],
                        name="Candidate（待測）",
                        marker_color="#00CC96",
                    )
                )
                fig.update_layout(
                    barmode="group",
                    title="<b>SPI Before / After 統計指標對比</b>",
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=30, r=20, t=40, b=30),
                )
                st.plotly_chart(fig, use_container_width=True)

            except (TypeError, ValueError) as exc:
                st.error(f"SPI 對比分析失敗：{_localize_gui_error(exc, domain='spi')}")

    csv_text = None
    if uploaded_spi is not None:
        try:
            csv_text = decode_uploaded_text(uploaded_spi, allowed_extensions={".csv", ".txt"})
            st.session_state["spi_sample_active"] = False
        except ValueError as exc:
            st.error(f"無法讀取 SPI 追蹤記錄（trace）：{exc}")
    elif use_spi_sample:
        csv_text = load_spi_sample()
        st.session_state["spi_sample_active"] = True
        st.session_state["spi_sample_content"] = csv_text
        st.info("已載入內建 SPI 範例 CSV（Winbond W25Q128）！")
    elif st.session_state.get("spi_sample_active"):
        sample_text = st.session_state.get("spi_sample_content")
        if isinstance(sample_text, str):
            csv_text = sample_text
    if st.session_state.get("spi_sample_active") and isinstance(csv_text, str):
        st.download_button(
            "下載內建 SPI 範例 CSV",
            data=csv_text,
            file_name="spi_w25q128_sample.csv",
            mime="text/csv",
            key="spi_download_example",
        )
    if csv_text is not None:
        try:
            rep = analyze_spi_input(csv_text, int(spi_page_size))
        except (TypeError, ValueError) as exc:
            st.error(f"無法解析 SPI 追蹤記錄（trace）：{_localize_gui_error(exc, domain='spi')}")
            show_error_toast("SPI 分析失敗")
        else:
            st.caption(
                "本頁分析的是分析器已解碼的 MOSI／MISO／CS 交易（analyzer-decoded transaction）。"
                "若沒有原始 SCLK 邊緣（raw SCLK edge），無法證明 CPOL／CPHA、位元時序（bit timing）"
                "或訊號完整性（signal integrity）。頁面大小（Page Size）僅供規則判定，不會自動取代"
                "資料表（datasheet）。"
            )
            s1, s2, s3, s4 = st.columns(4)
            show_success_toast("SPI 分析完成")
            s1.metric("總傳輸次數", rep.summary.total_transactions)
            s2.metric("讀取次數", rep.summary.read_count)
            s3.metric("頁面程式寫入（Page Program）", rep.summary.write_count)
            s4.metric("異常事件", rep.summary.anomaly_count)
            if rep.summary.detected_flash_chip:
                st.info(f"識別晶片型號：{rep.summary.detected_flash_chip}")
            spi_md = SPIReporter.to_markdown(rep)
            st.markdown(spi_md)
            st.download_button(
                "下載 SPI Markdown 診斷報告",
                data=spi_md,
                file_name="spi_flash_report.md",
                mime="text/markdown",
                key="spi_download_report",
            )
            render_html_download(spi_md, protocol="SPI", filename_prefix="spi_flash")
            render_pdf_download(spi_md, protocol="SPI", filename_prefix="spi_flash")
            findings = [
                {
                    "code": issue.code,
                    "title": issue.title,
                    "severity": issue.severity.value
                    if hasattr(issue.severity, "value")
                    else str(issue.severity),
                    "message": issue.description,
                }
                for issue in rep.issues
            ]
            render_sarif_download(findings, protocol="SPI", filename_prefix="spi_flash")
            report_dict = rep.to_dict()
            report_dict["protocol"] = "SPI"
            report_dict["summary"] = rep.summary.to_dict()
            report_dict["anomaly_count"] = rep.summary.anomaly_count
            session_json = serialize_spi_session(
                report_dict,
                input_name=uploaded_spi.name if uploaded_spi is not None else "spi_capture.csv",
                input_bytes=csv_text.encode("utf-8") if csv_text else None,
                max_page_size=int(spi_page_size),
            )
            st.download_button(
                "💾 儲存分析 Session",
                data=session_json,
                file_name="spi_analysis.fwsession.json",
                mime="application/json",
                key="spi_download_session",
            )

    render_page_footer()
