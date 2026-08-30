"""Tests for the Board Profile Visual Editor GUI page and its conversion logic."""

from __future__ import annotations

import importlib

from streamlit.testing.v1 import AppTest

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.gui.pages.board_profile_ui import (
    editor_state_to_board_profile,
    editor_state_to_yaml,
    format_hex_address,
    get_default_editor_state,
    parse_address_integer,
    validate_editor_state,
    yaml_to_editor_state,
)


def test_board_profile_ui_module_importable() -> None:
    """Verify that board_profile_ui is importable and exposes render()."""
    mod = importlib.import_module("fw_diag_tool.gui.pages.board_profile_ui")
    assert hasattr(mod, "render")
    assert callable(mod.render)
    assert mod.__all__ == ["render"]


def test_parse_address_integer() -> None:
    """Verify address parsing for hex strings, ints, and fallback values."""
    assert parse_address_integer("0x48") == 0x48
    assert parse_address_integer("0x20") == 0x20
    assert parse_address_integer(72) == 72
    assert parse_address_integer("72") == 72
    assert parse_address_integer("  0x50  ") == 0x50
    assert parse_address_integer("invalid", default=0x48) == 0x48
    assert format_hex_address(0x48) == "0x48"
    assert format_hex_address(0x08) == "0x08"


def test_default_editor_state_validity() -> None:
    """Default editor state should pass all validation rules without errors."""
    state = get_default_editor_state()
    messages = validate_editor_state(state)
    errors = [m for m in messages if m["level"] == "error"]
    assert not errors, f"Default state should have no errors: {errors}"

    profile = editor_state_to_board_profile(state)
    assert isinstance(profile, BoardProfile)
    assert profile.board_name == "YV4-CraterLake-reference"
    assert profile.version == "1.0"
    assert len(profile.i2c_buses) == 1
    assert profile.i2c_buses[0].bus_num == 1


def test_form_to_yaml_and_profile_roundtrip() -> None:
    """Verify conversion from form state dict to YAML and back to BoardProfile."""
    state = {
        "board_name": "Test-Board-Alpha",
        "version": "2.0",
        "description": "Roundtrip test board",
        "buses": [
            {
                "bus_num": 2,
                "speed_mode": "fast",
                "devices": [
                    {
                        "name": "inlet-temp",
                        "address_7bit": 0x48,
                        "category": "temperature-sensor",
                        "protocol": "I2C",
                        "compatible": "ti,tmp75",
                        "register_width": 8,
                        "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                    }
                ],
                "muxes": [
                    {
                        "name": "i2c-switch",
                        "address_7bit": 0x70,
                        "category": "i2c-mux",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9548",
                        "register_width": 8,
                        "num_channels": 8,
                        "channels": [
                            {
                                "channel": 0,
                                "devices": [
                                    {
                                        "name": "sensor-ch0",
                                        "address_7bit": 0x48,
                                        "category": "temperature-sensor",
                                        "protocol": "I2C",
                                        "compatible": "ti,tmp75",
                                        "register_width": 8,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    yaml_text = editor_state_to_yaml(state)
    assert "board_name: Test-Board-Alpha" in yaml_text
    assert "version: '2.0'" in yaml_text or 'version: "2.0"' in yaml_text
    assert "0x48" in yaml_text
    assert "0x70" in yaml_text

    # Verify YAML is directly loadable by load_board_profile
    reloaded_profile = load_board_profile(yaml_text)
    assert reloaded_profile.board_name == "Test-Board-Alpha"
    assert reloaded_profile.version == "2.0"
    assert len(reloaded_profile.i2c_buses) == 1
    assert reloaded_profile.i2c_buses[0].devices[0].address_7bit == 0x48
    assert reloaded_profile.i2c_buses[0].muxes[0].channels[0].devices[0].address_7bit == 0x48


def test_yaml_import_and_reverse_parsing() -> None:
    """Verify importing a raw YAML string into editor state."""
    raw_yaml = """
board_name: Imported-Board
version: "3.1"
i2c_buses:
  - bus_num: 0
    speed_mode: fast_plus
    devices:
      - address_7bit: 0x50
        name: eeprom-main
        category: eeprom
        protocol: EEPROM
        compatible: atmel,24c64
        register_width: 8
    muxes: []
"""
    state = yaml_to_editor_state(raw_yaml)
    assert state["board_name"] == "Imported-Board"
    assert state["version"] == "3.1"
    assert len(state["buses"]) == 1
    assert state["buses"][0]["bus_num"] == 0
    assert state["buses"][0]["speed_mode"] == "fast_plus"
    assert len(state["buses"][0]["devices"]) == 1
    assert state["buses"][0]["devices"][0]["address_7bit"] == 0x50
    assert state["buses"][0]["devices"][0]["name"] == "eeprom-main"


def test_address_conflict_detection_direct_devices() -> None:
    """Detect conflict when two direct devices on the same bus share an address."""
    state = {
        "board_name": "Conflict-Board",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [
                    {
                        "name": "sensor-a",
                        "address_7bit": 0x48,
                        "category": "temperature-sensor",
                        "protocol": "I2C",
                        "compatible": "ti,tmp75",
                    },
                    {
                        "name": "sensor-b",
                        "address_7bit": 0x48,
                        "category": "temperature-sensor",
                        "protocol": "I2C",
                        "compatible": "ti,tmp75",
                    },
                ],
                "muxes": [],
            }
        ],
    }

    messages = validate_editor_state(state)
    errors = [m for m in messages if m["level"] == "error"]
    assert any("位址衝突" in e["message"] and "0x48" in e["message"] for e in errors)


def test_address_conflict_detection_device_and_mux() -> None:
    """Detect conflict when a direct device and a mux share an address."""
    state = {
        "board_name": "Conflict-Mux-Board",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [
                    {
                        "name": "expander",
                        "address_7bit": 0x70,
                        "category": "gpio-expander",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9555",
                    }
                ],
                "muxes": [
                    {
                        "name": "pca9548-mux",
                        "address_7bit": 0x70,
                        "category": "i2c-mux",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9548",
                        "num_channels": 8,
                        "channels": [],
                    }
                ],
            }
        ],
    }

    messages = validate_editor_state(state)
    errors = [m for m in messages if m["level"] == "error"]
    assert any("位址衝突" in e["message"] and "0x70" in e["message"] for e in errors)


def test_address_conflict_detection_mux_channel() -> None:
    """Detect conflict when two devices on the same mux channel share an address."""
    state = {
        "board_name": "Conflict-Channel-Board",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [],
                "muxes": [
                    {
                        "name": "board-mux",
                        "address_7bit": 0x70,
                        "category": "i2c-mux",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9548",
                        "channels": [
                            {
                                "channel": 0,
                                "devices": [
                                    {
                                        "name": "ch0-dev1",
                                        "address_7bit": 0x50,
                                        "category": "eeprom",
                                        "protocol": "EEPROM",
                                        "compatible": "atmel,24c64",
                                    },
                                    {
                                        "name": "ch0-dev2",
                                        "address_7bit": 0x50,
                                        "category": "eeprom",
                                        "protocol": "EEPROM",
                                        "compatible": "atmel,24c64",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    messages = validate_editor_state(state)
    errors = [m for m in messages if m["level"] == "error"]
    assert any("通道位址衝突" in e["message"] and "0x50" in e["message"] for e in errors)


def test_reserved_address_validation() -> None:
    """Flag error when devices use addresses in reserved ranges (0x00..0x07 or 0x78..0x7F)."""
    # 0x00: General Call
    state_00 = {
        "board_name": "Reserved-Test",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 0,
                "speed_mode": "standard",
                "devices": [
                    {
                        "name": "gen-call-device",
                        "address_7bit": 0x00,
                        "category": "special",
                        "protocol": "I2C",
                        "compatible": "generic,broadcast",
                    }
                ],
                "muxes": [],
            }
        ],
    }
    messages_00 = validate_editor_state(state_00)
    errors_00 = [m for m in messages_00 if m["level"] == "error"]
    assert any("保留位址" in e["message"] and "0x00" in e["message"] for e in errors_00)

    # 0x78: 10-bit addressing header
    state_78 = {
        "board_name": "Reserved-Test-2",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 0,
                "speed_mode": "standard",
                "devices": [
                    {
                        "name": "ten-bit-device",
                        "address_7bit": 0x78,
                        "category": "special",
                        "protocol": "I2C",
                        "compatible": "generic,10bit",
                    }
                ],
                "muxes": [],
            }
        ],
    }
    messages_78 = validate_editor_state(state_78)
    errors_78 = [m for m in messages_78 if m["level"] == "error"]
    assert any("保留位址" in e["message"] and "0x78" in e["message"] for e in errors_78)


def test_speed_compatibility_validation() -> None:
    """Warn when a 100 kHz typical speed chip is configured on a 400 kHz or 1000 kHz bus."""
    state = {
        "board_name": "Speed-Test",
        "version": "1.0",
        "buses": [
            {
                "bus_num": 0,
                "speed_mode": "fast",  # 400 kHz
                "devices": [
                    {
                        "name": "pcf8574-gpio",
                        "address_7bit": 0x20,
                        "category": "gpio-expander",
                        "protocol": "I2C",
                        "compatible": "nxp,pcf8574",
                        "chip_model": "PCF8574 / PCF8574A 8-bit Quasi-bidirectional GPIO Expander",
                    }
                ],
                "muxes": [],
            }
        ],
    }

    messages = validate_editor_state(state)
    warnings = [m for m in messages if m["level"] == "warning"]
    assert any("時鐘速度相容性警示" in w["message"] and "100 kHz" in w["message"] for w in warnings)


def test_compatible_and_metadata_validation() -> None:
    """Validate board identity and compatible regex."""
    state = {
        "board_name": "",
        "version": "",
        "buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [
                    {
                        "name": "bad-compat-device",
                        "address_7bit": 0x48,
                        "category": "sensor",
                        "protocol": "I2C",
                        "compatible": "no-comma-compatible",
                    }
                ],
                "muxes": [],
            }
        ],
    }

    messages = validate_editor_state(state)
    errors = [m for m in messages if m["level"] == "error"]
    assert any("board_name" in e["message"] for e in errors)
    assert any("version" in e["message"] for e in errors)
    assert any("相容字串" in e["message"] and "vendor,device" in e["message"] for e in errors)


def board_profile_render() -> None:
    from fw_diag_tool.gui.pages.board_profile_ui import render

    render()


def test_gui_board_profile_page_renders_with_apptest() -> None:
    """Verify that Streamlit AppTest can render the Board Profile Visual Editor."""
    at = AppTest.from_function(board_profile_render, default_timeout=15).run()
    assert not at.exception
    assert any("Board Profile 視覺化拓撲編輯器" in item.value for item in at.header)
    assert any("YV4-CraterLake-reference" in item.value for item in at.text_input)
    assert any(code_block.language == "yaml" for code_block in at.code)


def test_gui_board_profile_preset_buttons() -> None:
    """Verify clicking preset buttons updates the session state and re-renders."""
    at = AppTest.from_function(board_profile_render, default_timeout=15).run()
    assert not at.exception

    # Click '⚡ 載入單 Bus 簡易範本' (button index 1)
    at.button[1].click().run()
    assert not at.exception
    assert any("Simple-Carrier-Card" in item.value for item in at.text_input)
