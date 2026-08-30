"""韌體訊號與協定診斷套件 — Streamlit 入口模組。

此檔案僅負責頁面註冊與導覽；各頁面的邏輯實作位於
``fw_diag_tool.gui.pages.*_ui`` 模組。
"""

from __future__ import annotations

import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.gui.accessibility import render_skip_nav_link
from fw_diag_tool.gui.pages import (
    batch_ui,
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
    protocol_diff_ui,
    register_ui,
    session_analytics_ui,
    session_compare_ui,
    settings_ui,
    sop_ui,
    spi_ui,
    tutorial_ui,
    uart_ui,
    waveform_diff_ui,
)
from fw_diag_tool.gui.shared import (
    render_global_search,
    render_keyboard_shortcuts,
    render_language_selector,
)
from fw_diag_tool.i18n import t

st.set_page_config(page_title="韌體訊號與協定診斷套件", page_icon="⚡", layout="wide")

from fw_diag_tool.gui.theme import inject_custom_theme, render_theme_toggle

inject_custom_theme()

st.markdown(render_skip_nav_link(), unsafe_allow_html=True)

render_language_selector()

pages = {
    t("nav_category_protocols", domain="gui"): [
        st.Page(
            i2c_diagnosis.render,
            title=t("title_i2c_diagnosis", domain="gui"),
            icon="📊",
            url_path="i2c-diagnosis",
        ),
        st.Page(
            i2c_builder_ui.render,
            title=t("title_i2c_builder", domain="gui"),
            icon="🎨",
            url_path="i2c-builder",
        ),
        st.Page(
            waveform_diff_ui.render,
            title=t("title_waveform_diff", domain="gui"),
            icon="⚖️",
            url_path="waveform-diff",
        ),
        st.Page(
            protocol_diff_ui.render,
            title=t("title_protocol_diff", domain="gui"),
            icon="🔀",
            url_path="protocol-diff",
        ),
    ],
    t("nav_category_advanced", domain="gui"): [
        st.Page(
            batch_ui.render,
            title=t("title_batch_analysis", domain="gui"),
            icon="📦",
            url_path="batch-analysis",
        ),
        st.Page(
            correlation_ui.render,
            title=t("title_correlation", domain="gui"),
            icon="🔗",
            url_path="correlation",
        ),
        st.Page(
            session_analytics_ui.render,
            title=t("title_session_analytics", domain="gui"),
            icon="📈",
            url_path="session-analytics",
        ),
        st.Page(
            session_compare_ui.render,
            title=t("title_session_compare", domain="gui"),
            icon="⚖️",
            url_path="session-compare",
        ),
    ],
    t("nav_category_overview", domain="gui"): [
        st.Page(
            dashboard_ui.render,
            title=t("title_overview", domain="gui"),
            icon="🏠",
            url_path="dashboard",
        ),
    ],
    t("nav_category_system", domain="gui"): [
        st.Page(
            uart_ui.render,
            title=t("title_uart", domain="gui"),
            icon="📟",
            url_path="uart",
        ),
        st.Page(
            mctp_ui.render,
            title=t("title_mctp", domain="gui"),
            icon="🌐",
            url_path="mctp",
        ),
        st.Page(
            pcie_ui.render,
            title=t("title_pcie", domain="gui"),
            icon="🚀",
            url_path="pcie",
        ),
        st.Page(
            spi_ui.render,
            title=t("title_spi", domain="gui"),
            icon="⚡",
            url_path="spi",
        ),
    ],
    t("nav_category_tools", domain="gui"): [
        st.Page(
            settings_ui.render,
            title=t("title_settings", domain="gui"),
            icon="⚙️",
            url_path="settings",
        ),
        st.Page(
            board_profile_ui.render,
            title=t("title_board_profile", domain="gui"),
            icon="📋",
            url_path="board-profile",
        ),
        st.Page(
            dts_ui.render,
            title=t("title_dts", domain="gui"),
            icon="🌲",
            url_path="dts",
        ),
        st.Page(
            register_ui.render,
            title=t("title_register", domain="gui"),
            icon="🎛",
            url_path="register",
        ),
        st.Page(
            codegen_ui.render,
            title=t("title_codegen", domain="gui"),
            icon="🛠",
            url_path="codegen",
        ),
    ],
    t("nav_category_labs", domain="gui"): [
        st.Page(
            tutorial_ui.render,
            title=t("title_tutorial", domain="gui"),
            icon="🎓",
            url_path="tutorial",
        ),
        st.Page(
            fault_arena_ui.render,
            title=t("title_fault_arena", domain="gui"),
            icon="🏆",
            url_path="fault-arena",
        ),
        st.Page(
            sop_ui.render,
            title=t("title_sop", domain="gui"),
            icon="📚",
            url_path="sop",
        ),
        st.Page(
            chip_db_ui.render,
            title=t("title_chip_db", domain="gui"),
            icon="🔍",
            url_path="chip-db",
        ),
        st.Page(
            emulator_ui.render,
            title=t("title_emulator", domain="gui"),
            icon="🧪",
            url_path="emulator",
        ),
        st.Page(
            fuzz_lab_ui.render,
            title=t("title_fuzz_lab", domain="gui"),
            icon="🎲",
            url_path="fuzz-lab",
        ),
    ],
}

nav = st.navigation(pages)

render_theme_toggle()
render_global_search()
render_keyboard_shortcuts()

st.sidebar.caption(f"fw-diag-tool v{__version__}")

st.markdown('<div id="main-content"></div>', unsafe_allow_html=True)

nav.run()
