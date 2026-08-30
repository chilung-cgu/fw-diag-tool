from __future__ import annotations

import pandas as pd
import streamlit as st

from fw_diag_tool.gui.shared import render_guide_expander, render_page_footer


def render() -> None:
    st.header("Firmware 工程師韌體除錯指南與心智模型（SOP／Mental Model）")
    render_guide_expander(
        "chapters/appendix_gui_reading_guide.md", "🧭 點擊展開：附錄 B 12 個 GUI 頁面第一輪閱讀地圖"
    )
    render_guide_expander("chapters/ch12_sop.md", "📖 點擊展開：L1~L7 系統化除錯 SOP 手冊")
    st.info(
        "先確認證據，再提出假設：工具的圖表與報告能縮小範圍，不能取代示波器、datasheet、"
        "kernel source、matching ELF 或目標板上的重現。"
    )
    st.subheader("🎯 L1～L7 分層診斷模型")
    st.table(
        pd.DataFrame(
            [
                {
                    "層次（Layer）": "L1 物理／電氣（Physical / Electrical）",
                    "先問什麼（Question）": "電源、接地、pull-up、線路電平與 clock 是否真的存在？",
                    "本工具能提供的證據（Evidence）": "Raw I2C 的 digital 0/1 edge、tHIGH/tLOW；不能量類比電壓或 PCIe eye。",
                },
                {
                    "層次（Layer）": "L2 連結／框架（Link / Framing）",
                    "先問什麼（Question）": "CS/START/STOP、ACK/NACK、stretch 或 frame boundary 是否合理？",
                    "本工具能提供的證據（Evidence）": "I2C/SPI analyzer decode、raw I2C bit decode、PCIe AER/config 欄位。",
                },
                {
                    "層次（Layer）": "L3 協定（Protocol）",
                    "先問什麼（Question）": "opcode、command、register offset、checksum 或 message type 是否正確？",
                    "本工具能提供的證據（Evidence）": "PMBus、EEPROM、SPI opcode、MCTP/IPMB、PCIe capability 解碼。",
                },
                {
                    "層次（Layer）": "L4 驅動／傳輸（Driver / Transport）",
                    "先問什麼（Question）": "Linux i2c-dev、SPI driver、MCTP transport 或 DMA 是否送出預期序列？",
                    "本工具能提供的證據（Evidence）": "把 capture/log 對回交易順序；不會直接檢查 live kernel state。",
                },
                {
                    "層次（Layer）": "L5 重試／狀態（Retry / State）",
                    "先問什麼（Question）": "是否有 retry、timeout、WREN/Busy、MUX channel 或 reset 狀態機問題？",
                    "本工具能提供的證據（Evidence）": "列出已觀察的重試、NACK、clock stretch、SPI WREN/Busy 證據。",
                },
                {
                    "層次（Layer）": "L6 平台／板級（Platform / Board）",
                    "先問什麼（Question）": "board wiring、Device Tree binding、power/reset/ownership 是否吻合？",
                    "本工具能提供的證據（Evidence）": "產生 DTS/driver 起始模板；必須用 schematic、datasheet、dtc/dt-schema 驗證。",
                },
                {
                    "層次（Layer）": "L7 應用／語意（Application / Meaning）",
                    "先問什麼（Question）": "這個 register/telemetry 值對產品行為代表什麼？",
                    "本工具能提供的證據（Evidence）": "Bitfield/PMBus/sensor 候選解碼；需要正確 device profile 才能下語意結論。",
                },
            ]
        )
    )

    st.subheader("🧭 每次除錯固定走這 7 步")
    st.markdown(
        "1. **保存原始證據**：不要只截圖；保留原始 CSV/log、來源工具設定與 capture 時間。\n"
        "2. **標記輸入型態**：decoded table、raw digital、analog、log 或 register dump；看不到的欄位就是 unavailable。\n"
        "3. **先查 L1**：確認供電、ground、pull-up/termination、CS/START 與 clock；需要時用示波器或公司的 LA。\n"
        "4. **再查 L2/L3**：看 frame boundary、address/opcode、ACK/checksum、register/data 是否符合 datasheet。\n"
        "5. **對回 L4/L5**：把 transaction 對到 driver log、retry/timeout、WREN/Busy、MUX 或 reset state。\n"
        "6. **最後查 L6/L7**：確認 DTS/binding、board variant、symbolicated source 與產品需求；不要由單一圖表直接宣布 root cause。\n"
        "7. **記錄可重現結論**：分開寫 observed facts、hypotheses、下一個 discriminating test 與尚未驗證項目。"
    )

    st.subheader("📏 報告中的證據詞怎麼讀")
    st.table(
        pd.DataFrame(
            [
                {
                    "詞（Term）": "實測（Measured）",
                    "意思（Meaning）": "直接由輸入 timestamp/edge/value 計算。",
                },
                {
                    "詞（Term）": "推論（Inferred）",
                    "意思（Meaning）": "由多個觀察欄位推論，仍可能有替代解釋。",
                },
                {
                    "詞（Term）": "協定重建（Reconstructed）",
                    "意思（Meaning）": "依 decoded bytes 畫出的理想示意，不是實測波形。",
                },
                {
                    "詞（Term）": "假設（Hypothesis）",
                    "意思（Meaning）": "排查方向，不是已證明的 root cause。",
                },
                {
                    "詞（Term）": "不可用（Unavailable）",
                    "意思（Meaning）": "輸入缺少必要證據；工具不補 0 或猜測。",
                },
            ]
        )
    )

    render_page_footer()


__all__ = ["render"]
