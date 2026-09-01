"""OpenBMC Entity-Manager configuration builder and validation GUI page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.em import EMBuilder, EMValidator
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
    EMValidationIssue,
)
from fw_diag_tool.em.templates import (
    DEVICE_TEMPLATES,
    get_all_categories,
    get_template,
    get_templates_by_category,
)
from fw_diag_tool.gui.page_index import render_breadcrumb
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    render_guide_expander,
    render_page_footer,
)
from fw_diag_tool.gui.uploads import decode_uploaded_text
from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.i18n import t

_SAMPLE_CONFLICT_JSON = """{
    "Name": "Sample_Server_Mainboard",
    "Probe": "TRUE",
    "Exposes": [
        {
            "Address": "0x48",
            "Bus": 1,
            "Name": "TEMP_SENSOR_1",
            "Type": "TMP75"
        },
        {
            "Address": "0x48",
            "Bus": 1,
            "Name": "TEMP_SENSOR_CONFLICT",
            "Type": "TMP75"
        },
        {
            "Address": "0x02",
            "Bus": 2,
            "Name": "INVALID_ADDR_DEVICE",
            "Type": "LM75"
        },
        {
            "Bus": 3,
            "Name": "MISSING_ADDR_DEVICE",
            "Type": "EEPROM"
        }
    ]
}"""


def _get_default_sample_devices() -> list[EMDeviceEntry]:
    """Return standard sample server mainboard device entries."""
    tmpl_tmp75 = get_template("TMP75") or DEVICE_TEMPLATES["TMP75"]
    tmpl_fru = get_template("AT24C256") or DEVICE_TEMPLATES["AT24C256"]
    tmpl_fan = get_template("MAX31790") or DEVICE_TEMPLATES["MAX31790"]
    tmpl_pmbus = get_template("PMBus") or DEVICE_TEMPLATES["PMBus"]

    return [
        EMDeviceEntry(
            template=tmpl_tmp75,
            bus=1,
            address=0x48,
            name="BMC_TEMP0",
            power_state="On",
        ),
        EMDeviceEntry(
            template=tmpl_fru,
            bus=1,
            address=0x50,
            name="BASEBOARD_FRU",
            power_state="Always",
        ),
        EMDeviceEntry(
            template=tmpl_fan,
            bus=2,
            address=0x20,
            name="FAN_CTRL0",
            power_state="On",
        ),
        EMDeviceEntry(
            template=tmpl_pmbus,
            bus=3,
            address=0x58,
            name="PSU0_PMBUS",
            power_state="On",
        ),
    ]


def _parse_address(addr_str: str) -> int:
    """Parse address string (hex or dec) into an integer."""
    token = addr_str.strip()
    if token.startswith(("0x", "0X")):
        return int(token, 16)
    if token.isdigit():
        return int(token, 10)
    return int(token, 0)


def render() -> None:
    """Render the OpenBMC Entity-Manager Builder and Validator UI page."""
    cat_title = t("nav_category_system_log", domain="gui")
    page_title = t("title_em_builder", domain="gui")
    render_breadcrumb(
        cat_title if cat_title != "nav_category_system_log" else "System Logs",
        page_title if page_title != "title_em_builder" else "Entity-Manager 產生器",
    )

    st.header(t("em_builder_title", domain="gui"))
    render_guide_expander(
        "chapters/ch25_em_builder.md",
        "📖 點擊展開：Entity-Manager 組態產生器教學",
        fallback_title="📖 點擊展開：Entity-Manager 組態產生器教學",
        fallback_body=(
            "Entity-Manager 為 OpenBMC 提供動態硬體組態掃描與 D-Bus 暴露機制。\n"
            "本工具提供：\n"
            "1. 🛠️ 視覺化建置模式：自訂或選用感測器範本，快速生成符合 OpenBMC 規範的 JSON Exposes 組態。\n"
            "2. 🔍 規格校驗模式：針對既有 JSON 檔案檢查語法、必填欄位、I2C 位址範圍與衝突，並可載入 Board Profile 比對硬體差異。"
        ),
    )

    mode_options = [
        t("em_mode_build", domain="gui"),
        t("em_mode_validate", domain="gui"),
    ]
    mode = st.radio(
        t("em_work_mode", domain="gui"),
        mode_options,
        key="em_mode_select",
        horizontal=True,
    )

    if mode == mode_options[0]:
        _render_build_mode()
    else:
        _render_validate_mode()

    render_page_footer()


def _render_build_mode() -> None:
    """Render Entity-Manager visual builder mode."""
    if "em_devices_list" not in st.session_state:
        st.session_state["em_devices_list"] = []

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        board_name = st.text_input(
            t("em_board_name", domain="gui"),
            value="Yosemite_V4_Mainboard",
            key="em_board_name_input",
        )
    with col_b2:
        probe_expr = st.text_input(
            t("em_probe_expr", domain="gui"),
            value="TRUE",
            key="em_probe_input",
        )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button(t("em_load_sample_devices", domain="gui"), key="em_btn_load_sample_devs"):
            st.session_state["em_devices_list"] = list(_get_default_sample_devices())
    with col_btn2:
        if st.button(t("em_clear_devices", domain="gui"), key="em_btn_clear_devs"):
            st.session_state["em_devices_list"] = []

    with st.expander("➕ 新增裝置設定 (Add Device Configuration)", expanded=True):
        categories = get_all_categories()
        col_cat, col_chip = st.columns(2)
        with col_cat:
            selected_cat = st.selectbox(
                t("em_category", domain="gui"),
                categories,
                key="em_category_select",
            )
        with col_chip:
            cat_templates = get_templates_by_category(selected_cat)
            chip_names = [tmpl.chip_name for tmpl in cat_templates]
            selected_chip = st.selectbox(
                t("em_chip_model", domain="gui"),
                chip_names,
                key="em_chip_select",
            )

        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            bus_num = st.number_input(
                t("em_bus_num", domain="gui"),
                min_value=0,
                max_value=65535,
                value=1,
                step=1,
                key="em_bus_input",
            )
        with col_d2:
            addr_str = st.text_input(
                t("em_i2c_addr", domain="gui"),
                value="0x48",
                key="em_addr_input",
            )
        with col_d3:
            dev_name = st.text_input(
                t("em_device_name", domain="gui"),
                value="BMC_TEMP0",
                key="em_devname_input",
            )

        power_options = ["(使用預設)", "Always", "On", "BiosPost", "Standby"]
        selected_power = st.selectbox(
            t("em_power_state", domain="gui"),
            power_options,
            key="em_power_select",
        )

        if st.button(t("em_add_device", domain="gui"), key="em_btn_add_device"):
            try:
                addr_int = _parse_address(addr_str)
                if not (0x08 <= addr_int <= 0x77):
                    st.error(f"7-bit I2C 位址 0x{addr_int:02x} 超出有效範圍 (0x08..0x77)")
                elif not dev_name.strip():
                    st.error("裝置名稱不得為空")
                else:
                    tmpl = get_template(selected_chip)
                    if tmpl is not None:
                        p_state = None if selected_power == "(使用預設)" else selected_power
                        entry = EMDeviceEntry(
                            template=tmpl,
                            bus=int(bus_num),
                            address=addr_int,
                            name=dev_name.strip(),
                            power_state=p_state,
                        )
                        st.session_state["em_devices_list"].append(entry)
                        st.success(
                            f"已新增裝置: {dev_name.strip()} (Bus {bus_num}, Address 0x{addr_int:02x})"
                        )
                    else:
                        st.error(f"找不到晶片範本: {selected_chip}")
            except ValueError:
                st.error(
                    f"無法解析 I2C 位址: '{addr_str}'，請輸入有效的十六進位 (例如 0x48) 或十進位數字"
                )

    devices_list: list[EMDeviceEntry] = st.session_state.get("em_devices_list", [])
    st.subheader(f"目前已設定裝置清單 ({len(devices_list)} 個裝置)")

    if devices_list:
        df_rows = [
            {
                "序號": idx + 1,
                "裝置名稱": dev.name,
                "晶片型號": dev.template.chip_name,
                "Entity-Manager Type": dev.template.em_type,
                "類別": dev.template.category,
                "I2C 匯流排": dev.bus,
                "7-bit 位址": f"0x{dev.address:02x}",
                "PowerState": dev.power_state or dev.template.default_power_state,
            }
            for idx, dev in enumerate(devices_list)
        ]
        st.dataframe(pd.DataFrame(df_rows), use_container_width=True)
    else:
        st.info("目前尚未加入任何裝置。請由上方新增裝置或載入標準範本。")

    if st.button(t("em_generate_json", domain="gui"), key="em_btn_generate_json"):
        config = EMBoardConfig(
            board_name=board_name.strip() or "Yosemite_V4_Mainboard",
            devices=list(devices_list),
            probe_expression=probe_expr.strip() or "TRUE",
        )
        try:
            json_output = EMBuilder.generate(config)
            st.session_state["em_generated_json"] = json_output
        except Exception as exc:
            err_msg = _localize_gui_error(str(exc), domain="common")
            st.error(f"產生 JSON 失敗: {err_msg}")

    if st.session_state.get("em_generated_json"):
        st.subheader("產出的 Entity-Manager JSON 組態")
        json_content = st.session_state["em_generated_json"]
        st.code(json_content, language="json")
        st.download_button(
            t("em_download_json", domain="gui"),
            json_content,
            file_name=f"{board_name.strip() or 'board_config'}.json",
            mime="application/json",
            key="em_btn_download_json",
        )


def _render_validate_mode() -> None:
    """Render Entity-Manager JSON syntax and topology validation mode."""
    st.session_state.setdefault("em_validate_raw_text", "")
    st.session_state.setdefault("em_val_bp_text", "")

    if st.button(t("em_load_sample_conflict", domain="gui"), key="em_btn_load_sample_conflict"):
        st.session_state["em_validate_raw_text"] = _SAMPLE_CONFLICT_JSON

    val_file = st.file_uploader(
        t("em_val_uploader_label", domain="gui"),
        type=["json"],
        key="em_val_file_uploader",
    )
    if val_file is not None:
        st.session_state["em_validate_raw_text"] = decode_uploaded_text(
            val_file, allowed_extensions={".json"}
        )

    val_text = st.text_area(
        t("em_val_text_label", domain="gui"),
        height=220,
        key="em_validate_raw_text",
    )

    with st.expander("板級拓撲設定檔（選填，用於硬體對照）", expanded=False):
        bp_file = st.file_uploader(
            "上傳 Board Profile (YAML/JSON)",
            type=["yaml", "yml", "json"],
            key="em_val_bp_uploader",
        )
        if bp_file is not None:
            st.session_state["em_val_bp_text"] = decode_uploaded_text(
                bp_file, allowed_extensions={".yaml", ".yml", ".json"}
            )

        bp_text = st.text_area(
            "或貼上 Board Profile 內容",
            height=120,
            key="em_val_bp_text",
        )

    if st.button(t("em_validate_json", domain="gui"), key="em_btn_validate_json"):
        if not val_text or not val_text.strip():
            st.warning("請先上傳或貼上欲校驗的 Entity-Manager JSON 內容。")
            st.session_state["em_val_has_run"] = False
        else:
            profile: BoardProfile | None = None
            bp_raw = bp_text.strip() if bp_text else ""
            if bp_raw:
                try:
                    profile = load_board_profile(bp_raw)
                except Exception as exc:
                    st.warning(f"Board Profile 解析失敗，將略過硬體拓撲交叉比對: {exc}")
                    profile = None

            issues = EMValidator.validate(val_text, board_profile=profile)
            st.session_state["em_val_issues"] = issues
            st.session_state["em_val_has_run"] = True

    if st.session_state.get("em_val_has_run"):
        val_issues: list[EMValidationIssue] = st.session_state.get("em_val_issues", [])
        if not val_issues:
            st.success(t("em_val_success", domain="gui"))
        else:
            crit_count = sum(1 for i in val_issues if i.severity == Severity.CRITICAL)
            err_count = sum(1 for i in val_issues if i.severity == Severity.ERROR)
            warn_count = sum(1 for i in val_issues if i.severity == Severity.WARNING)
            info_count = sum(1 for i in val_issues if i.severity == Severity.INFO)

            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
            m_col1.metric("總問題數", len(val_issues))
            m_col2.metric("Critical", crit_count)
            m_col3.metric("Error", err_count)
            m_col4.metric("Warning", warn_count)
            m_col5.metric("Info", info_count)

            st.subheader(f"校驗結果清單 ({len(val_issues)} 項問題)")
            severity_icons = {
                Severity.CRITICAL: "🔴",
                Severity.ERROR: "❌",
                Severity.WARNING: "⚠️",
                Severity.INFO: "ℹ️",
            }

            for issue in val_issues:
                icon = severity_icons.get(issue.severity, "⚠️")
                with st.expander(
                    f"{icon} [{issue.severity.value}] {issue.field_path}: {issue.message}",
                    expanded=True,
                ):
                    st.markdown(f"- **欄位路徑 (Field Path)**: `{issue.field_path}`")
                    st.markdown(f"- **錯誤訊息 (Message)**: {issue.message}")
                    if issue.suggestion:
                        st.markdown(f"- **建議修復行動 (Suggestion)**: {issue.suggestion}")
