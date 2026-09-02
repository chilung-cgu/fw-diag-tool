"""Tests for Entity-Manager and Device Tree Bridge (EMBridge)."""

from __future__ import annotations

import json

import pytest

from fw_diag_tool.board_profile import BoardProfile
from fw_diag_tool.em.bridge import EMBridge
from fw_diag_tool.em.models import EMBoardConfig

SAMPLE_BOARD_PROFILE_YAML = """
board_name: "OpenBMC_Baseboard_EVT"
version: "2.1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: "fast"
    devices:
      - address_7bit: 0x48
        name: "TMP75_Inlet"
        category: "temperature"
        protocol: "i2c"
        compatible: "ti,tmp75"
        register_width: 8
      - address_7bit: 0x50
        name: "MB_FRU_EEPROM"
        category: "fru"
        protocol: "i2c"
        compatible: "atmel,24c64"
        register_width: 8
  - bus_num: 2
    speed_mode: "standard"
    devices:
      - address_7bit: 0x49
        name: "LM75_Outlet"
        category: "temperature"
        protocol: "i2c"
        compatible: "national,lm75"
        register_width: 8
"""

SAMPLE_BOARD_WITH_MUX_YAML = """
board_name: "Mux_Carrier_Board"
version: "1.0.0"
i2c_buses:
  - bus_num: 3
    speed_mode: "fast"
    devices:
      - address_7bit: 0x48
        name: "TMP75_Local"
        category: "temperature"
        protocol: "i2c"
        compatible: "ti,tmp75"
        register_width: 8
    muxes:
      - address_7bit: 0x70
        name: "PCA9548_Mux"
        category: "mux"
        protocol: "i2c"
        compatible: "nxp,pca9548"
        register_width: 8
        channels:
          - channel: 0
            devices:
              - address_7bit: 0x52
                name: "DIMM0_SPD"
                category: "fru"
                protocol: "i2c"
                compatible: "atmel,24c64"
                register_width: 8
          - channel: 1
            devices:
              - address_7bit: 0x53
                name: "DIMM1_SPD"
                category: "fru"
                protocol: "i2c"
                compatible: "atmel,24c64"
                register_width: 8
"""

SAMPLE_UNKNOWN_DEVICE_YAML = """
board_name: "Custom_Sensor_Board"
version: "1.0.0"
i2c_buses:
  - bus_num: 4
    speed_mode: "fast"
    devices:
      - address_7bit: 0x36
        name: "Custom_Power_IC"
        category: "custom_power"
        protocol: "i2c"
        compatible: "custom_vendor,xyz1234"
        register_width: 8
"""


def test_from_board_profile_basic() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    config = EMBridge.from_board_profile(profile)
    assert isinstance(config, EMBoardConfig)
    assert config.board_name == "OpenBMC_Baseboard_EVT"
    assert len(config.devices) == 3
    dev_map = {d.name: d for d in config.devices}
    assert dev_map["TMP75_Inlet"].bus == 1
    assert dev_map["TMP75_Inlet"].address == 0x48
    assert dev_map["TMP75_Inlet"].template.em_type == "TMP75"
    assert dev_map["MB_FRU_EEPROM"].template.em_type == "EEPROM"
    assert dev_map["LM75_Outlet"].bus == 2


def test_from_board_profile_with_mux() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_WITH_MUX_YAML)
    config = EMBridge.from_board_profile(profile)
    assert config.board_name == "Mux_Carrier_Board"
    assert len(config.devices) == 4
    dev_names = [d.name for d in config.devices]
    assert "TMP75_Local" in dev_names
    assert "PCA9548_Mux" in dev_names
    assert "DIMM0_SPD" in dev_names
    assert "DIMM1_SPD" in dev_names


def test_from_board_profile_filter_by_bus() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    config_bus1 = EMBridge.from_board_profile(profile, bus_num=1)
    assert len(config_bus1.devices) == 2
    config_bus2 = EMBridge.from_board_profile(profile, bus_num=2)
    assert len(config_bus2.devices) == 1
    with pytest.raises(ValueError, match=r"Bus number 99 not found"):
        EMBridge.from_board_profile(profile, bus_num=99)


def test_from_board_profile_unknown_device() -> None:
    profile = BoardProfile.from_text(SAMPLE_UNKNOWN_DEVICE_YAML)
    config = EMBridge.from_board_profile(profile)
    assert len(config.devices) == 1
    dev = config.devices[0]
    assert dev.name == "Custom_Power_IC"
    assert dev.template.chip_name == "xyz1234"


def test_to_em_json_roundtrip() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    json_text = EMBridge.to_em_json(profile)
    data = json.loads(json_text)
    assert data["Name"] == "OpenBMC_Baseboard_EVT"
    assert len(data["Exposes"]) == 3


def test_to_dts_basic() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    dts_text = EMBridge.to_dts(profile)
    assert "&i2c1 {" in dts_text
    assert "&i2c2 {" in dts_text
    assert 'compatible = "ti,tmp75";' in dts_text
    assert 'compatible = "national,lm75";' in dts_text


def test_to_dts_with_mux() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_WITH_MUX_YAML)
    dts_text = EMBridge.to_dts(profile, bus_num=3)
    assert "&i2c3 {" in dts_text
    assert "i2c-mux@70 {" in dts_text
    assert 'compatible = "nxp,pca9548";' in dts_text
    assert 'compatible = "atmel,24c64";' in dts_text


def test_to_dts_invalid_bus() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    with pytest.raises(ValueError, match=r"Bus number 42 not found"):
        EMBridge.to_dts(profile, bus_num=42)

