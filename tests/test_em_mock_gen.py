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
    assert "IO_Expander0" in script
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

