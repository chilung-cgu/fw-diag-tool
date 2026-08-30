from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    analyze_spi_input,
    render_guide_expander,
)
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.resources import load_spi_sample
from fw_diag_tool.spi.reporter import SPIReporter

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)


def render() -> None:
    st.header("SPI／QSPI Flash 協定解析與寫入異常診斷")
    render_guide_expander(
        "chapters/ch08_spi_flash.md", "📖 點擊展開：SPI Flash 協定與狀態機診斷教學"
    )
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
            st.error(
                "無法解析 SPI 追蹤記錄（trace）："
                f"{_localize_gui_error(exc, domain='spi')}"
            )
        else:
            st.caption(
                "本頁分析的是分析器已解碼的 MOSI／MISO／CS 交易（analyzer-decoded transaction）。"
                "若沒有原始 SCLK 邊緣（raw SCLK edge），無法證明 CPOL／CPHA、位元時序（bit timing）"
                "或訊號完整性（signal integrity）。頁面大小（Page Size）僅供規則判定，不會自動取代"
                "資料表（datasheet）。"
            )
            s1, s2, s3, s4 = st.columns(4)
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
