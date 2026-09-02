"""Unit tests for Entity-Manager D-Bus Mock Script Generator."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
    assert "<<'PYTHON_MOCK'" in script
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
    assert "PYTHON_MOCK" in script


def test_generate_python_mock(sample_board_config: EMBoardConfig) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    assert script.startswith("#!/usr/bin/env python3")
    assert "from dbus_next.aio import MessageBus" in script
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



def test_mock_mapping_handles_multi_channel_same_bus_addr_collision() -> None:
    template = get_template("TMP75")
    assert template is not None
    # e.g., two downstream sensor items exposed with identical bus & address
    config = EMBoardConfig(board_name="B", devices=[
        EMDeviceEntry(template=template, bus=1, address=0x48, name="CPU Temp"),
        EMDeviceEntry(template=template, bus=1, address=0x48, name="CPU-Temp"),
    ])
    objects = EMMockGenerator._build_mock_objects(config)
    paths = [obj["path"] for obj in objects]
    assert len(paths) == len(set(paths)) == 2
    assert paths[0] == "/xyz/openbmc_project/sensors/temperature/CPU_Temp_b1_a48"
    assert paths[1] == "/xyz/openbmc_project/sensors/temperature/CPU_Temp_b1_a48_2"


def test_mock_mapping_handles_three_way_name_collision() -> None:
    template = get_template("TMP75")
    assert template is not None
    config = EMBoardConfig(board_name="B", devices=[
        EMDeviceEntry(template=template, bus=1, address=0x48, name="CPU Temp"),
        EMDeviceEntry(template=template, bus=2, address=0x48, name="CPU_Temp"),
        EMDeviceEntry(template=template, bus=3, address=0x48, name="CPU-Temp"),
    ])
    paths = [obj["path"] for obj in EMMockGenerator._build_mock_objects(config)]
    assert len(paths) == len(set(paths)) == 3
    assert paths[0].endswith("/CPU_Temp_b1_a48")
    assert paths[1].endswith("/CPU_Temp_b2_a48")
    assert paths[2].endswith("/CPU_Temp_b3_a48")


def test_mock_mapping_handles_case_collision_on_case_insensitive_comparisons() -> None:
    template = get_template("TMP75")
    assert template is not None
    config = EMBoardConfig(board_name="B", devices=[
        EMDeviceEntry(template=template, bus=1, address=0x48, name="cpu_temp"),
        EMDeviceEntry(template=template, bus=1, address=0x49, name="CPU_TEMP"),
    ])
    paths = [obj["path"] for obj in EMMockGenerator._build_mock_objects(config)]
    assert len(paths) == len(set(paths)) == 2


@pytest.mark.parametrize(
    "board_name",
    [
        'Board"""evil',
        'Board"\\\nraise RuntimeError("INJECTED")#',
    ],
)
def test_generated_python_is_valid_and_treats_board_name_as_data(board_name: str) -> None:
    config = EMBoardConfig(board_name=board_name, devices=[])
    script = EMMockGenerator.generate_python_mock(config)
    compile(script, "<generated-mock>", "exec")
    assert "BOARD_NAME = " + repr(board_name) in script


def test_generated_python_uses_python_booleans_not_json_tokens(
    sample_board_config: EMBoardConfig,
) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    compile(script, "<generated-mock>", "exec")
    assert "'is_sensor': True" in script
    assert '"is_sensor": true' not in script


def test_generated_bash_does_not_execute_device_text(
    sample_board_config: EMBoardConfig,
    tmp_path: Path,
) -> None:
    sample_board_config.devices[0].name = 'FRU"; echo INJECTED; #'
    script_path = tmp_path / "mock.sh"
    script_path.write_text(EMMockGenerator.generate_busctl_script(sample_board_config))
    result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "<<'PYTHON_MOCK'" in script_path.read_text()


def test_generated_bash_does_not_execute_heredoc_delimiter_from_board_text(
    sample_board_config: EMBoardConfig,
    tmp_path: Path,
) -> None:
    sample_board_config.board_name = "Board\nPYTHON_MOCK\necho INJECTED"
    script_path = tmp_path / "mock.sh"
    script_path.write_text(EMMockGenerator.generate_busctl_script(sample_board_config))
    result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert script_path.read_text().splitlines().count("PYTHON_MOCK") == 1


def test_generated_python_owns_name_and_exports_objects(
    sample_board_config: EMBoardConfig,
) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    assert "await bus.request_name(MOCK_SERVICE)" in script
    assert "bus.export(obj['path'], interface)" in script
    assert "ServiceInterface" in script
    assert "busctl set-property" not in script
    assert "|| true" not in script


def test_generated_python_rejects_non_owner_name_reply(
    sample_board_config: EMBoardConfig,
) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    assert "from dbus_next.constants import RequestNameReply" in script
    assert (
        "if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):"
        in script
    )
