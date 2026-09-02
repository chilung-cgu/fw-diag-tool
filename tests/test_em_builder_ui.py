"""Unit tests and Streamlit AppTest coverage for Entity-Manager Builder & Validator UI."""

from __future__ import annotations

import dataclasses
import enum
import os
import pathlib
import subprocess
import sys

from pydantic import BaseModel
from streamlit.testing.v1 import AppTest

from fw_diag_tool.em.models import EMDeviceEntry, EMDeviceTemplate
from fw_diag_tool.gui.pages import em_builder_ui
from fw_diag_tool.gui.pages.em_builder_ui import (
    _freeze_value,
    _get_default_sample_devices,
    _mock_generation_key,
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


def _mock_mode_with_corrupt_artifact_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import _get_default_sample_devices, render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = list(_get_default_sample_devices())
    st.session_state["em_mock_artifact"] = {"corrupt": True}
    render()


def _mock_mode_empty_devices_with_stale_artifact_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = []
    st.session_state["em_mock_artifact"] = {
        "key": ("Yosemite_V4_Mainboard", "TRUE", "bash", ()),
        "content": "echo stale",
        "format": "bash",
    }
    render()


def _mock_mode_with_legacy_script_state_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.em_builder_ui import _get_default_sample_devices, render
    from fw_diag_tool.i18n import t

    st.session_state["em_mode_select"] = t("em_mode_mock", domain="gui")
    st.session_state["em_devices_list"] = list(_get_default_sample_devices())
    st.session_state["em_mock_script"] = "legacy script text"
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


def test_mock_generation_key_changes_with_format_and_devices() -> None:
    devices = list(_get_default_sample_devices())
    bash_key = _mock_generation_key("Board", "TRUE", "bash", devices)
    python_key = _mock_generation_key("Board", "TRUE", "python", devices)
    changed_devices = list(devices)
    changed_devices[0] = EMDeviceEntry(
        template=devices[0].template,
        bus=devices[0].bus,
        address=devices[0].address,
        name="Changed_Name",
    )
    assert bash_key != python_key
    assert bash_key != _mock_generation_key("Board", "TRUE", "bash", changed_devices)

    tmpl1 = EMDeviceTemplate(category="Temperature", chip_name="TMP75", em_type="TMP75")
    tmpl2 = EMDeviceTemplate(category="Temperature", chip_name="LM75", em_type="TMP75")
    dev_tmpl1 = [EMDeviceEntry(template=tmpl1, bus=1, address=0x48, name="Temp")]
    dev_tmpl2 = [EMDeviceEntry(template=tmpl2, bus=1, address=0x48, name="Temp")]
    dev_custom = [
        EMDeviceEntry(
            template=tmpl1, bus=1, address=0x48, name="Temp", custom_fields={"Threshold": 85}
        )
    ]

    k_tmpl1 = _mock_generation_key("Board", "TRUE", "bash", dev_tmpl1)
    k_tmpl2 = _mock_generation_key("Board", "TRUE", "bash", dev_tmpl2)
    k_custom = _mock_generation_key("Board", "TRUE", "bash", dev_custom)
    assert k_tmpl1 != k_tmpl2
    assert k_tmpl1 != k_custom


def test_mock_generation_key_template_fields_and_nested_custom_fields() -> None:
    base_tmpl = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Max": 100},
        description="TI TMP75",
    )
    dev_base = [EMDeviceEntry(template=base_tmpl, bus=1, address=0x48, name="Temp")]
    k_base = _mock_generation_key("Board", "TRUE", "bash", dev_base)

    # default_power_state change
    tmpl_pwr = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="AlwaysOn",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Max": 100},
        description="TI TMP75",
    )
    k_pwr = _mock_generation_key(
        "Board",
        "TRUE",
        "bash",
        [EMDeviceEntry(template=tmpl_pwr, bus=1, address=0x48, name="Temp")],
    )
    assert k_base != k_pwr

    # required_fields change
    tmpl_req = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name", "Extra"],
        optional_fields={"Max": 100},
        description="TI TMP75",
    )
    k_req = _mock_generation_key(
        "Board",
        "TRUE",
        "bash",
        [EMDeviceEntry(template=tmpl_req, bus=1, address=0x48, name="Temp")],
    )
    assert k_base != k_req

    # optional_fields nested change
    tmpl_opt = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Max": 100, "Nested": {"sub": [1, 2]}},
        description="TI TMP75",
    )
    tmpl_opt2 = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Max": 100, "Nested": {"sub": [1, 3]}},
        description="TI TMP75",
    )
    k_opt = _mock_generation_key(
        "Board",
        "TRUE",
        "bash",
        [EMDeviceEntry(template=tmpl_opt, bus=1, address=0x48, name="Temp")],
    )
    k_opt2 = _mock_generation_key(
        "Board",
        "TRUE",
        "bash",
        [EMDeviceEntry(template=tmpl_opt2, bus=1, address=0x48, name="Temp")],
    )
    assert k_base != k_opt
    assert k_opt != k_opt2

    # description change
    tmpl_desc = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Max": 100},
        description="Different description",
    )
    k_desc = _mock_generation_key(
        "Board",
        "TRUE",
        "bash",
        [EMDeviceEntry(template=tmpl_desc, bus=1, address=0x48, name="Temp")],
    )
    assert k_base != k_desc

    # nested custom_fields
    dev_nested1 = [
        EMDeviceEntry(
            template=base_tmpl,
            bus=1,
            address=0x48,
            name="Temp",
            custom_fields={"Thresholds": {"high": [80, 90]}},
        )
    ]
    dev_nested2 = [
        EMDeviceEntry(
            template=base_tmpl,
            bus=1,
            address=0x48,
            name="Temp",
            custom_fields={"Thresholds": {"high": [80, 95]}},
        )
    ]
    k_nest1 = _mock_generation_key("Board", "TRUE", "bash", dev_nested1)
    k_nest2 = _mock_generation_key("Board", "TRUE", "bash", dev_nested2)
    assert k_nest1 != k_nest2
    assert hash(k_nest1) == hash(_mock_generation_key("Board", "TRUE", "bash", dev_nested1))

    # power_state=None vs explicit default
    dev_pwr_none = [
        EMDeviceEntry(template=base_tmpl, bus=1, address=0x48, name="Temp", power_state=None)
    ]
    dev_pwr_explicit = [
        EMDeviceEntry(template=base_tmpl, bus=1, address=0x48, name="Temp", power_state="On")
    ]
    assert _mock_generation_key("Board", "TRUE", "bash", dev_pwr_none) == _mock_generation_key(
        "Board", "TRUE", "bash", dev_pwr_explicit
    )

    # board name and probe normalization
    k_default = _mock_generation_key("Yosemite_V4_Mainboard", "TRUE", "bash", dev_base)
    assert (
        _mock_generation_key("  Yosemite_V4_Mainboard  ", "  TRUE  ", "bash", dev_base) == k_default
    )
    assert _mock_generation_key("", "", "bash", dev_base) == k_default
    assert _mock_generation_key("   ", "   ", "bash", dev_base) == k_default


def test_mock_generation_key_deterministic_set_and_frozenset_order() -> None:
    tmpl = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        optional_fields={"Tags": {"b", "a", "c"}, "Modes": frozenset([3, 1, 2])},
    )
    dev = [EMDeviceEntry(template=tmpl, bus=1, address=0x48, name="Temp")]

    key1 = _mock_generation_key("Board", "TRUE", "bash", dev)
    assert hash(key1) is not None

    tmpl_reordered = EMDeviceTemplate(
        category="Temperature",
        chip_name="TMP75",
        em_type="TMP75",
        optional_fields={"Tags": {"c", "b", "a"}, "Modes": frozenset([1, 2, 3])},
    )
    dev_reordered = [EMDeviceEntry(template=tmpl_reordered, bus=1, address=0x48, name="Temp")]
    key2 = _mock_generation_key("Board", "TRUE", "bash", dev_reordered)

    assert key1 == key2
    assert hash(key1) == hash(key2)


def test_mock_generation_key_nested_bytearray_and_set_in_custom_fields() -> None:
    tmpl = EMDeviceTemplate(category="Temperature", chip_name="TMP75", em_type="TMP75")
    dev1 = [
        EMDeviceEntry(
            template=tmpl,
            bus=1,
            address=0x48,
            name="Temp",
            custom_fields={"raw": bytearray(b"\x01\x02"), "flags": {"debug", "active"}},
        )
    ]
    dev2 = [
        EMDeviceEntry(
            template=tmpl,
            bus=1,
            address=0x48,
            name="Temp",
            custom_fields={"raw": bytearray(b"\x01\x03"), "flags": {"debug", "active"}},
        )
    ]

    k1 = _mock_generation_key("Board", "TRUE", "bash", dev1)
    k2 = _mock_generation_key("Board", "TRUE", "bash", dev2)

    assert hash(k1) is not None
    assert hash(k2) is not None
    assert k1 != k2


def test_mock_generation_key_hashseed_invariance_subprocess() -> None:
    code = (
        "from fw_diag_tool.em.models import EMDeviceTemplate, EMDeviceEntry\n"
        "from fw_diag_tool.gui.pages.em_builder_ui import _mock_generation_key\n"
        "tmpl = EMDeviceTemplate(\n"
        "    category='Temp',\n"
        "    chip_name='TMP75',\n"
        "    em_type='TMP75',\n"
        "    optional_fields={'Tags': {'zeta', 'alpha', 'beta', 'gamma'}},\n"
        ")\n"
        "dev = [EMDeviceEntry(template=tmpl, bus=1, address=0x48, name='T')]\n"
        "key = _mock_generation_key('Board', 'TRUE', 'bash', dev)\n"
        "print(repr(key))\n"
    )
    outputs: set[str] = set()
    seeds = ["0", "1", "42", "1337", "999999", "random"]
    for seed in seeds:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        outputs.add(res.stdout.strip())
    assert len(outputs) == 1


def test_apptest_em_mock_invalidates_malformed_session_state() -> None:
    at = AppTest.from_function(_mock_mode_with_corrupt_artifact_app, default_timeout=15).run()
    assert not at.exception
    assert not at.code
    assert not at.download_button


def test_apptest_em_mock_clears_artifact_when_devices_list_is_empty() -> None:
    at = AppTest.from_function(
        _mock_mode_empty_devices_with_stale_artifact_app, default_timeout=15
    ).run()
    assert not at.exception
    assert not at.code
    assert not at.download_button
    assert "em_mock_artifact" not in at.session_state


def test_apptest_em_mock_clears_legacy_script_state() -> None:
    at = AppTest.from_function(_mock_mode_with_legacy_script_state_app, default_timeout=15).run()
    assert not at.exception
    assert not at.code
    assert not at.download_button
    assert "em_mock_script" not in at.session_state


def test_apptest_em_mock_format_change_invalidates_generated_artifact() -> None:
    at = AppTest.from_function(_mock_mode_with_devices_app, default_timeout=15).run()
    generate = next(button for button in at.button if "產生 D-Bus Mock" in button.label)
    generate.click().run()
    assert any(code.language == "bash" for code in at.code)

    format_radio = next(
        radio
        for radio in at.radio
        if "輸出格式" in radio.label or "Python daemon" in getattr(radio, "options", [])
    )
    format_radio.set_value("Python daemon").run()

    assert not at.code
    assert not at.download_button


class _SampleEnum(enum.Enum):
    MODE_A = "fast"
    MODE_B = "slow"


@dataclasses.dataclass
class _SampleConfigDC:
    retries: int
    target: str


class _SampleConfigModel(BaseModel):
    gain: float
    label: str


class _UnhashablePublicState:
    __hash__ = None

    def __init__(self, value: object) -> None:
        self.value = value


class _HashablePublicState:
    def __init__(self, value: object) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _HashablePublicState) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


def test_freeze_value_mixed_dict_keys_and_uncomparable_values() -> None:
    # Keys with matching str representations but different types and uncomparable values
    raw_dict = {1: (1, 2), "1": 5}
    frozen = _freeze_value(raw_dict)
    assert isinstance(frozen, tuple)
    assert hash(frozen) is not None

    # Re-ordered dictionary items must produce identical frozen representation
    raw_dict_reordered = {"1": 5, 1: (1, 2)}
    assert _freeze_value(raw_dict_reordered) == frozen
    assert hash(_freeze_value(raw_dict_reordered)) == hash(frozen)


def test_freeze_value_handles_nan_enums_paths_dataclasses_and_models() -> None:
    nan1 = _freeze_value({"nan_val": float("nan")})
    nan2 = _freeze_value({"nan_val": float("nan")})
    assert nan1 == nan2
    assert hash(nan1) == hash(nan2)

    enum_val = _freeze_value(_SampleEnum.MODE_A)
    assert hash(enum_val) is not None
    assert enum_val != _freeze_value(_SampleEnum.MODE_B)

    path_val1 = _freeze_value(pathlib.Path("/etc/sensors.conf"))
    path_val2 = _freeze_value(pathlib.Path("/etc/sensors.conf"))
    assert path_val1 == path_val2
    assert hash(path_val1) is not None

    dc_val1 = _freeze_value(_SampleConfigDC(retries=3, target="i2c1"))
    dc_val2 = _freeze_value(_SampleConfigDC(retries=3, target="i2c1"))
    assert dc_val1 == dc_val2
    assert hash(dc_val1) is not None

    model_val1 = _freeze_value(_SampleConfigModel(gain=1.5, label="temp"))
    model_val2 = _freeze_value(_SampleConfigModel(gain=1.5, label="temp"))
    assert model_val1 == model_val2
    assert hash(model_val1) is not None


def test_freeze_value_distinguishes_types_with_equal_python_values() -> None:
    # bool vs int vs float
    assert _freeze_value(True) != _freeze_value(1)
    assert _freeze_value(False) != _freeze_value(0)
    assert _freeze_value(1) != _freeze_value(1.0)
    assert _freeze_value(0) != _freeze_value(0.0)

    # list vs tuple vs set
    assert _freeze_value([1, 2]) != _freeze_value((1, 2))
    assert _freeze_value({1, 2}) != _freeze_value([1, 2])
    assert _freeze_value({1, 2}) != _freeze_value((1, 2))

    # infinities and None
    assert _freeze_value(float("inf")) == _freeze_value(float("inf"))
    assert _freeze_value(float("-inf")) == _freeze_value(float("-inf"))
    assert _freeze_value(float("inf")) != _freeze_value(float("-inf"))
    assert _freeze_value(None) == _freeze_value(None)
    assert _freeze_value(None) != _freeze_value(0)
    assert _freeze_value(None) != _freeze_value(False)

    # dicts containing type-confusable values
    assert _freeze_value({"flag": True}) != _freeze_value({"flag": 1})
    assert _freeze_value({"val": 1}) != _freeze_value({"val": 1.0})
    assert _freeze_value({"mode": 0}) != _freeze_value({"mode": False})


def test_freeze_value_float_signed_zero_and_supported_results_are_stable_hashable() -> None:
    assert _freeze_value(0.0) != _freeze_value(-0.0)
    assert _freeze_value(1.25) == ("float", "0x1.4000000000000p+0")
    for value in (None, True, 1, 1.25, "text", b"bytes", [1], (1,), {1}, frozenset({1}), {"a": 1}):
        frozen = _freeze_value(value)
        assert isinstance(frozen, tuple)
        assert hash(frozen) is not None


def test_freeze_value_unhashable_public_state_is_structural_without_identity() -> None:
    first = _freeze_value(_UnhashablePublicState({"mode": "fast"}))
    second = _freeze_value(_UnhashablePublicState({"mode": "fast"}))
    changed = _freeze_value(_UnhashablePublicState({"mode": "slow"}))

    assert first == second
    assert first != changed
    assert "0x" not in repr(first)
    assert hash(first) is not None


def test_freeze_value_hashable_public_state_is_structural_not_raw_object() -> None:
    value = _HashablePublicState("fast")
    frozen = _freeze_value(value)
    equivalent = _freeze_value(_HashablePublicState("fast"))

    assert frozen == equivalent
    assert frozen[1] != value
    assert "0x" not in repr(frozen)
    assert hash(frozen) is not None


def test_freeze_value_constant_repr_mapping_and_set_are_hashseed_invariant() -> None:
    code = (
        "from fw_diag_tool.gui.pages.em_builder_ui import _freeze_value\n"
        "class C:\n"
        "    def __init__(self, value): self.value = value\n"
        "    def __hash__(self): return hash(self.value)\n"
        "    def __eq__(self, other): return isinstance(other, C) and self.value == other.value\n"
        "    def __repr__(self): return '<constant>'\n"
        "items = [C('alpha'), C('beta'), C('gamma')]\n"
        "order = [2, 1, 0] if __import__('os').environ.get('ORDER') == 'reverse' else [0, 1, 2]\n"
        "mapping = {items[index]: chr(97 + index) for index in order}\n"
        "values = {items[0], items[1], items[2]}\n"
        "print(repr(_freeze_value({'mapping': mapping, 'values': values})))\n"
    )
    outputs: set[str] = set()
    for seed in ("0", "1", "42", "1337", "random"):
        for order in ("forward", "reverse"):
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                env=dict(os.environ, PYTHONHASHSEED=seed, ORDER=order),
            )
            outputs.add(result.stdout.strip())
    assert len(outputs) == 1
