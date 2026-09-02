"""Unit tests for Entity-Manager D-Bus Mock Script Generator."""

from __future__ import annotations

import json

import pytest

from fw_diag_tool.em.mock_gen import EMMockGenerator
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
)
from fw_diag_tool.em.templates import get_template


@pytest.fixture
def sample_board_config() -> EMBoardConfig:
    tmp75 = get_template("TMP75")
    assert tmp75 is not None
    max31790 = get_template("MAX31790")
    assert max31790 is not None
    pmbus = get_template("PMBus")
    assert pmbus is not None
    adc = get_template("ADC128D818")
    assert adc is not None
    fru = get_template("AT24C256")
    assert fru is not None
    gpio = get_template("PCA9555")
    assert gpio is not None
    adm1272 = get_template("ADM1272")
    assert adm1272 is not None

    devices = [
        EMDeviceEntry(template=tmp75, bus=1, address=0x48, name="Inlet_Temp"),
        EMDeviceEntry(template=max31790, bus=2, address=0x20, name="Fan_Tach0"),
        EMDeviceEntry(template=pmbus, bus=3, address=0x58, name="PSU0_Pwr"),
        EMDeviceEntry(template=adc, bus=4, address=0x1D, name="P12V_Sens"),
        EMDeviceEntry(template=fru, bus=1, address=0x50, name="Baseboard_FRU"),
        EMDeviceEntry(template=gpio, bus=5, address=0x21, name="IO_Expander0"),
        EMDeviceEntry(template=adm1272, bus=6, address=0x10, name="Hotswap_Pwr"),
    ]
    return EMBoardConfig(board_name="Yosemite_V4_MB", devices=devices, probe_expression="TRUE")


def test_parse_em_json_valid() -> None:
    em_json = json.dumps({
        "Name": "Test_Board",
        "Probe": "TRUE",
        "Exposes": [
            {"Name": "CPU_Temp", "Type": "TMP75", "Bus": 1, "Address": "0x48"},
            {"Name": "FAN_0", "Type": "MAX31790", "Bus": 2, "Address": 32},
        ],
    })
    config = EMMockGenerator.parse_em_json(em_json)
    assert config.board_name == "Test_Board"
    assert len(config.devices) == 2
    assert config.devices[0].name == "CPU_Temp"
    assert config.devices[0].address == 0x48
    assert config.devices[0].template.category == "temperature"
    assert config.devices[1].name == "FAN_0"
    assert config.devices[1].address == 32
    assert config.devices[1].template.category == "fan"


def test_parse_em_json_unknown_chip() -> None:
    em_json = json.dumps({
        "Name": "Custom_Board",
        "Exposes": [
            {"Name": "Custom_Sensor", "Type": "CustomTempSensor", "Bus": 1, "Address": "0x4A"}
        ],
    })
    config = EMMockGenerator.parse_em_json(em_json)
    assert len(config.devices) == 1
    assert config.devices[0].template.chip_name == "CustomTempSensor"
    assert config.devices[0].template.category == "temperature"


def test_generate_busctl_script(sample_board_config: EMBoardConfig) -> None:
    script = EMMockGenerator.generate_busctl_script(sample_board_config)
    assert script.startswith("#!/bin/bash")
    assert "set -euo pipefail" in script
    assert "Yosemite_V4_MB" in script
    assert "/xyz/openbmc_project/sensors/temperature/Inlet_Temp" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.DegreesC" in script
    assert "25.0" in script
    assert "/xyz/openbmc_project/sensors/fan_tach/Fan_Tach0" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.RPMS" in script
    assert "5000.0" in script
    assert "/xyz/openbmc_project/sensors/power/PSU0_Pwr" in script
    assert "/xyz/openbmc_project/sensors/power/Hotswap_Pwr" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.Watts" in script
    assert "100.0" in script
    assert "/xyz/openbmc_project/sensors/voltage/P12V_Sens" in script
    assert "xyz.openbmc_project.Sensor.Value.Unit.Volts" in script
    assert "3.3" in script
    assert "/xyz/openbmc_project/inventory/system/board/Baseboard_FRU" in script
    assert "xyz.openbmc_project.ObjectMapper" in script


def test_generate_python_mock(sample_board_config: EMBoardConfig) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    assert script.startswith("#!/usr/bin/env python3")
    assert "import subprocess" in script
    assert 'if __name__ == "__main__":' in script
    assert "Yosemite_V4_MB" in script
    assert "/xyz/openbmc_project/sensors/temperature/Inlet_Temp" in script
    assert "/xyz/openbmc_project/sensors/fan_tach/Fan_Tach0" in script
    assert "/xyz/openbmc_project/sensors/power/PSU0_Pwr" in script
    assert "/xyz/openbmc_project/sensors/voltage/P12V_Sens" in script
    assert "/xyz/openbmc_project/inventory/system/board/Baseboard_FRU" in script



@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Exposes": {}}, "Exposes must be a JSON array"),
        ({"Exposes": ["not-an-object"]}, r"Exposes\[0\] must be a JSON object"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Address": "0x48"}]}, "Bus"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": True, "Address": "0x48"}]}, "Bus must be an integer"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": 1.5, "Address": "0x48"}]}, "Bus must be an integer"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": 1, "Address": "0x78"}]}, "Address must be a non-reserved"),
    ],
)
def test_parse_em_json_rejects_malformed_contract(payload: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        EMMockGenerator.parse_em_json(json.dumps(payload))


def test_mock_mapping_skips_mux_instead_of_inventing_temperature_sensor() -> None:
    config = EMMockGenerator.parse_em_json(json.dumps({
        "Name": "MuxBoard",
        "Probe": "TRUE",
        "Exposes": [
            {"Name": "Main Mux", "Type": "PCA9548", "Bus": 1, "Address": "0x70"}
        ],
    }))
    assert EMMockGenerator._build_mock_objects(config) == []


def test_mock_mapping_disambiguates_sanitized_path_collisions() -> None:
    template = get_template("TMP75")
    assert template is not None
    config = EMBoardConfig(board_name="B", devices=[
        EMDeviceEntry(template=template, bus=1, address=0x48, name="CPU Temp"),
        EMDeviceEntry(template=template, bus=2, address=0x48, name="CPU-Temp"),
    ])
    paths = [obj["path"] for obj in EMMockGenerator._build_mock_objects(config)]
    assert len(paths) == len(set(paths)) == 2
    assert paths[0].endswith("/CPU_Temp_b1_a48")
    assert paths[1].endswith("/CPU_Temp_b2_a48")
