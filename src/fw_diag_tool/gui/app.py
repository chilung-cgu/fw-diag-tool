"""韌體訊號與協定診斷套件 — Streamlit 入口模組。

此檔案僅負責頁面註冊與導覽；各頁面的邏輯實作位於
``fw_diag_tool.gui.pages.*_ui`` 模組。
"""

from __future__ import annotations

import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.gui.pages import (
    board_profile_ui,
    chip_db_ui,
    codegen_ui,
    correlation_ui,
    dashboard_ui,
    dts_ui,
    emulator_ui,
    fault_arena_ui,
    fuzz_lab_ui,
    i2c_builder_ui,
    i2c_diagnosis,
    mctp_ui,
    pcie_ui,
    register_ui,
    sop_ui,
    spi_ui,
    tutorial_ui,
    uart_ui,
    waveform_diff_ui,
)

st.set_page_config(page_title="韌體訊號與協定診斷套件", page_icon="⚡", layout="wide")

from fw_diag_tool.gui.theme import inject_custom_theme

inject_custom_theme()

pages = {
    "協定分析與波形": [
        st.Page(
            i2c_diagnosis.render,
            title="I2C / PMBus 診斷與波形檢視",
            icon="📊",
            url_path="i2c-diagnosis",
        ),
        st.Page(
            i2c_builder_ui.render,
            title="I2C 封包模擬器與驅動產生",
            icon="🎨",
            url_path="i2c-builder",
        ),
        st.Page(
            waveform_diff_ui.render, title="雙波形對比檢視", icon="⚖️", url_path="waveform-diff"
        ),
    ],
    "進階分析": [
        st.Page(
            correlation_ui.render,
            title="跨協定時間線關聯分析",
            icon="🔗",
            url_path="correlation",
        ),
    ],
    "總覽": [
        st.Page(
            dashboard_ui.render,
            title="功能總覽與快速入門",
            icon="🏠",
            url_path="dashboard",
        ),
    ],
    "系統協定診斷": [
        st.Page(uart_ui.render, title="UART 崩潰轉儲與 HardFault 分析", icon="📟", url_path="uart"),
        st.Page(mctp_ui.render, title="MCTP／IPMB 伺服器管理協定解析", icon="🌐", url_path="mctp"),
        st.Page(pcie_ui.render, title="PCIe 設定空間與 AER 診斷", icon="🚀", url_path="pcie"),
        st.Page(spi_ui.render, title="SPI Flash 協定診斷", icon="⚡", url_path="spi"),
    ],
    "產生器與硬體工具": [
        st.Page(
            board_profile_ui.render,
            title="Board Profile 視覺化編輯器",
            icon="📋",
            url_path="board-profile",
        ),
        st.Page(dts_ui.render, title="Device Tree 產生器", icon="🌲", url_path="dts"),
        st.Page(register_ui.render, title="暫存器 Bitfield 解碼器", icon="🎛", url_path="register"),
        st.Page(codegen_ui.render, title="C Register 巨集產生器", icon="🛠", url_path="codegen"),
    ],
    "實驗室與學習": [
        st.Page(
            tutorial_ui.render,
            title="互動式教學導覽",
            icon="🎓",
            url_path="tutorial",
        ),
        st.Page(
            fault_arena_ui.render,
            title="Firmware 實戰除錯實驗室",
            icon="🏆",
            url_path="fault-arena",
        ),
        st.Page(sop_ui.render, title="韌體除錯指南與 SOP", icon="📚", url_path="sop"),
        st.Page(
            chip_db_ui.render,
            title="I2C 晶片資料庫瀏覽器",
            icon="🔍",
            url_path="chip-db",
        ),
        st.Page(
            emulator_ui.render,
            title="虛擬設備模擬器實驗室",
            icon="🧪",
            url_path="emulator",
        ),
        st.Page(
            fuzz_lab_ui.render,
            title="協定解析器 Fuzz 測試",
            icon="🎲",
            url_path="fuzz-lab",
        ),
    ],
}

nav = st.navigation(pages)

st.sidebar.caption(f"fw-diag-tool v{__version__}")

nav.run()
