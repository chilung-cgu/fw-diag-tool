"""Unit tests and Streamlit AppTest coverage for Entity-Manager Builder & Validator UI."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.pages import em_builder_ui
from fw_diag_tool.gui.pages.em_builder_ui import (
    _get_default_sample_devices,
    _parse_address,
    render,
)
from fw_diag_tool.i18n.domains.gui import GUI_TRANSLATIONS


def test_em_builder_ui_exports() -> None:
    """Verify module exports and callables."""
    assert callable(render)
    assert hasattr(em_builder_ui, "render")
    assert callable(_get_default_sample_devices)
    assert callable(_parse_address)


def test_parse_address_helper() -> None:
    """Verify address parsing for hex strings, decimal strings, and integers."""
    assert _parse_address("0x48") == 0x48
    assert _parse_address("0X50") == 0x50
    assert _parse_address("72") == 72
    assert _parse_address("  0x20  ") == 0x20


def test_get_default_sample_devices() -> None:
    """Verify standard sample devices structure."""
    devices = _get_default_sample_devices()
    assert len(devices) == 4
    names = [d.name for d in devices]
    assert "BMC_TEMP0" in names
    assert "BASEBOARD_FRU" in names
    assert "FAN_CTRL0" in names
    assert "PSU0_PMBUS" in names


def test_i18n_gui_keys_exist() -> None:
    """Verify that all required EM builder i18n keys are registered with zh-TW and en-US."""
    required_keys = [
        "title_em_builder",
        "em_builder_title",
        "em_work_mode",
        "em_mode_build",
        "em_mode_validate",
        "em_mode_mock",
        "em_board_name",
        "em_probe_expr",
        "em_category",
        "em_chip_model",
        "em_bus_num",
        "em_i2c_addr",
        "em_device_name",
        "em_power_state",
        "em_add_device",
        "em_load_sample_devices",
        "em_clear_devices",
        "em_generate_json",
        "em_download_json",
        "em_validate_json",
        "em_val_uploader_label",
        "em_val_text_label",
        "em_load_sample_conflict",
        "em_val_success",
        "em_mock_format",
        "em_mock_generate",
        "em_mock_download",
        "em_mock_no_devices",
    ]
    for key in required_keys:
        assert key in GUI_TRANSLATIONS, f"Missing i18n key: {key}"
        assert "zh-TW" in GUI_TRANSLATIONS[key]
        assert "en-US" in GUI_TRANSLATIONS[key]
        assert GUI_TRANSLATIONS[key]["zh-TW"].strip()
        assert GUI_TRANSLATIONS[key]["en-US"].strip()


def _em_app() -> None:
    from fw_diag_tool.gui.pages.em_builder_ui import render

    render()


def test_apptest_em_builder_initial_render() -> None:
    """Test initial render of em_builder_ui in Build Mode."""
    at = AppTest.from_function(_em_app, default_timeout=15).run()
    assert not at.exception
    # Verify header is rendered
    assert any("Entity-Manager" in h.value for h in at.header)
    # Verify radio mode select is present
    assert len(at.radio) >= 1


def test_apptest_em_builder_sample_load_and_generate() -> None:
    """Test loading standard sample devices and generating JSON in Build Mode."""
    at = AppTest.from_function(_em_app, default_timeout=15).run()
    assert not at.exception

    # Click sample load button
    btn_sample = next((b for b in at.button if "載入標準" in b.label or "4 裝置" in b.label), None)
    assert btn_sample is not None
    btn_sample.click().run()
    assert not at.exception

    # Current device list should show 4 devices in subheader or dataframe
    assert any("4 個裝置" in sh.value for sh in at.subheader)
    assert len(at.dataframe) >= 1

    # Click generate JSON button
    btn_gen = next((b for b in at.button if "產生 Entity-Manager JSON" in b.label), None)
    assert btn_gen is not None
    btn_gen.click().run()
    assert not at.exception

    # Verify code block and download button appear
    assert len(at.code) >= 1
    assert any("Exposes" in c.value for c in at.code)
    assert len(at.download_button) >= 1

    # Click clear devices button
    btn_clear = next((b for b in at.button if "清空" in b.label), None)
    assert btn_clear is not None
    btn_clear.click().run()
    assert not at.exception
    assert any("0 個裝置" in sh.value for sh in at.subheader)


def test_apptest_em_builder_add_device_and_validation_error() -> None:
    """Test adding a device and invalid address handling."""
    at = AppTest.from_function(_em_app, default_timeout=15).run()
    assert not at.exception

    # Add a device with invalid address 0x02
    addr_input = next(
        (ti for ti in at.text_input if "0x08..0x77" in ti.label or "7-bit" in ti.label), None
    )
    assert addr_input is not None
    addr_input.set_value("0x02")

    btn_add = next((b for b in at.button if "新增裝置至板卡" in b.label), None)
    assert btn_add is not None
    btn_add.click().run()
    assert not at.exception
    assert any("超出有效範圍" in err.value for err in at.error)

    # Now fix address to valid 0x49 and add
    addr_input.set_value("0x49")
    btn_add.click().run()
    assert not at.exception
    assert any("已新增裝置" in s.value for s in at.success)


def _validate_mode_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_validate", domain="gui")
    render()


def test_apptest_em_validate_mode_with_conflict_sample() -> None:
    """Test Validate Mode with conflicting sample JSON."""
    at = AppTest.from_function(_validate_mode_app, default_timeout=15).run()
    assert not at.exception

    # Click load conflict sample button
    btn_sample = next(
        (b for b in at.button if "Address 衝突" in b.label or "範例" in b.label), None
    )
    assert btn_sample is not None
    btn_sample.click().run()
    assert not at.exception

    # Click run validation button
    btn_val = next((b for b in at.button if "執行 Entity-Manager 規格校驗" in b.label), None)
    assert btn_val is not None
    btn_val.click().run()
    assert not at.exception

    # Check that metrics and issue list appear
    metric_labels = [m.label for m in at.metric]
    assert any("總問題數" in lbl for lbl in metric_labels)
    assert any("Error" in lbl for lbl in metric_labels)


def _validate_clean_app() -> None:
    import json

    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_validate", domain="gui")
    st.session_state["em_validate_raw_text"] = json.dumps(
        {
            "Name": "Valid_Mainboard",
            "Probe": "TRUE",
            "Exposes": [
                {
                    "Address": "0x48",
                    "Bus": 1,
                    "Name": "BMC_TEMP0",
                    "Type": "TMP75",
                }
            ],
        }
    )
    render()


def test_apptest_em_validate_mode_clean_success() -> None:
    """Test Validate Mode with valid clean JSON producing success message."""
    at = AppTest.from_function(_validate_clean_app, default_timeout=15).run()
    assert not at.exception

    btn_val = next((b for b in at.button if "執行 Entity-Manager 規格校驗" in b.label), None)
    assert btn_val is not None
    btn_val.click().run()
    assert not at.exception

    assert any("校驗通過" in s.value for s in at.success)


def _validate_with_board_profile_app() -> None:
    import json

    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_validate", domain="gui")
    st.session_state["em_val_bp_text"] = (
        'board_name: "Yosemite_V4"\n'
        'version: "1.0"\n'
        "i2c_buses:\n"
        "  - bus_num: 1\n"
        '    speed_mode: "standard"\n'
        "    devices:\n"
        "      - address_7bit: 0x48\n"
        '        name: "baseboard-temp-sensor"\n'
        '        category: "Temperature"\n'
        '        protocol: "I2C"\n'
        '        compatible: "ti,tmp75"\n'
        "        register_width: 8\n"
        "      - address_7bit: 0x50\n"
        '        name: "baseboard-fru-eeprom"\n'
        '        category: "EEPROM"\n'
        '        protocol: "I2C"\n'
        '        compatible: "atmel,24c64"\n'
        "        register_width: 8\n"
    )
    st.session_state["em_validate_raw_text"] = json.dumps(
        {
            "Name": "Yosemite_V4",
            "Probe": "TRUE",
            "Exposes": [
                {
                    "Address": "0x48",
                    "Bus": 1,
                    "Name": "BMC_TEMP0",
                    "Type": "TMP75",
                }
            ],
        }
    )
    render()


def test_apptest_em_validate_with_board_profile() -> None:
    """Test Validate Mode with Board Profile producing missing device info issue."""
    at = AppTest.from_function(_validate_with_board_profile_app, default_timeout=15).run()
    assert not at.exception

    btn_val = next((b for b in at.button if "執行 Entity-Manager 規格校驗" in b.label), None)
    assert btn_val is not None
    btn_val.click().run()
    assert not at.exception

    # Should find missing device 0x50 from BoardProfile -> 1 Info issue
    metric_labels = [m.label for m in at.metric]
    assert any("Info" in lbl for lbl in metric_labels)


def _mock_mode_empty_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = []
    render()


def test_apptest_em_mock_mode_no_devices() -> None:
    """Test Mock Generator Mode when no devices are configured."""
    at = AppTest.from_function(_mock_mode_empty_app, default_timeout=15).run()
    assert not at.exception

    assert any("尚未設定任何裝置" in info.value for info in at.info)
    btn_load = next((b for b in at.button if "載入標準" in b.label or "4 裝置" in b.label), None)
    assert btn_load is not None


def _mock_mode_with_devices_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import _get_default_sample_devices, render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = list(_get_default_sample_devices())
    render()


def test_apptest_em_mock_mode_generate_bash_and_python() -> None:
    """Test Mock Generator Mode generating Bash and Python mock scripts."""
    at = AppTest.from_function(_mock_mode_with_devices_app, default_timeout=15).run()
    assert not at.exception

    assert len(at.dataframe) >= 1
    assert len(at.radio) >= 2  # mode select + mock format select

    # Click Generate Mock Script button
    btn_gen = next((b for b in at.button if "產生 D-Bus Mock 腳本" in b.label), None)
    assert btn_gen is not None
    btn_gen.click().run()
    assert not at.exception

    # Code block and download button should appear
    assert len(at.code) >= 1
    assert any("busctl" in c.value or "xyz.openbmc_project" in c.value for c in at.code)
    assert len(at.download_button) >= 1
