"""Tests for OpenBMC Entity-Manager JSON builder and validator."""

from __future__ import annotations

import json

import pytest

from fw_diag_tool.board_profile import BoardProfile
from fw_diag_tool.em.builder import EMBuilder
from fw_diag_tool.em.models import (
    EMBoardConfig,
    EMDeviceEntry,
)
from fw_diag_tool.em.templates import get_template
from fw_diag_tool.em.validator import EMValidator
from fw_diag_tool.i2c.models import Severity

# ---------------------------------------------------------------------------
# Builder Tests
# ---------------------------------------------------------------------------


def test_builder_generate_single_device() -> None:
    """Test generating JSON for a single TMP75 device."""
    tmpl = get_template("TMP75")
    assert tmpl is not None

    entry = EMDeviceEntry(template=tmpl, bus=1, address=0x48, name="TMP75_Ambient")
    config = EMBoardConfig(board_name="Test_Motherboard", devices=[entry], probe_expression="TRUE")

    json_str = EMBuilder.generate(config)
    data = json.loads(json_str)

    assert data["Name"] == "Test_Motherboard"
    assert data["Probe"] == "TRUE"
    assert len(data["Exposes"]) == 1

    dev = data["Exposes"][0]
    assert dev["Name"] == "TMP75_Ambient"
    assert dev["Type"] == "TMP75"
    assert dev["Bus"] == 1
    assert dev["Address"] == "0x48"
    assert dev["PowerState"] == "On"
    assert "Thresholds" in dev


def test_builder_generate_multiple_devices_different_buses() -> None:
    """Test generating JSON for multiple devices across different buses."""
    tmp75_tmpl = get_template("TMP75")
    eeprom_tmpl = get_template("AT24C64")
    assert tmp75_tmpl is not None
    assert eeprom_tmpl is not None

    dev1 = EMDeviceEntry(template=tmp75_tmpl, bus=1, address=0x48, name="TMP75_U1")
    dev2 = EMDeviceEntry(
        template=tmp75_tmpl, bus=2, address=0x48, name="TMP75_U2"
    )  # Same address, different bus
    dev3 = EMDeviceEntry(template=eeprom_tmpl, bus=1, address=0x50, name="EEPROM_MB")

    config = EMBoardConfig(board_name="MultiBus_Board", devices=[dev1, dev2, dev3])
    json_str = EMBuilder.generate(config)
    data = json.loads(json_str)

    assert len(data["Exposes"]) == 3
    names = [d["Name"] for d in data["Exposes"]]
    assert names == ["TMP75_U1", "TMP75_U2", "EEPROM_MB"]


def test_builder_generate_duplicate_endpoint_raises_value_error() -> None:
    """Test that duplicate (bus, address) endpoints raise a ValueError."""
    tmpl = get_template("TMP75")
    assert tmpl is not None

    dev1 = EMDeviceEntry(template=tmpl, bus=1, address=0x48, name="TMP75_U1")
    dev2 = EMDeviceEntry(template=tmpl, bus=1, address=0x48, name="TMP75_U2")  # Conflict

    config = EMBoardConfig(board_name="Conflict_Board", devices=[dev1, dev2])
    with pytest.raises(ValueError, match=r"Duplicate.*[Bb]us.*1.*0x48"):
        EMBuilder.generate(config)


def test_builder_generate_invalid_address_raises_value_error() -> None:
    """Test that address outside 0x08..0x77 raises ValueError."""
    tmpl = get_template("TMP75")
    assert tmpl is not None

    # Below 0x08
    dev_low = EMDeviceEntry(template=tmpl, bus=1, address=0x07, name="TMP75_Low")
    config_low = EMBoardConfig(board_name="Low_Addr_Board", devices=[dev_low])
    with pytest.raises(ValueError, match=r"address.*0x07.*out of valid.*range"):
        EMBuilder.generate(config_low)

    # Above 0x77
    dev_high = EMDeviceEntry(template=tmpl, bus=1, address=0x78, name="TMP75_High")
    config_high = EMBoardConfig(board_name="High_Addr_Board", devices=[dev_high])
    with pytest.raises(ValueError, match=r"address.*0x78.*out of valid.*range"):
        EMBuilder.generate(config_high)


def test_builder_generate_invalid_bus_raises_value_error() -> None:
    """Test that bus < 0 or > 65535 raises ValueError."""
    tmpl = get_template("TMP75")
    assert tmpl is not None

    dev_neg_bus = EMDeviceEntry(template=tmpl, bus=-1, address=0x48, name="TMP75_Neg")
    config_neg = EMBoardConfig(board_name="Neg_Bus_Board", devices=[dev_neg_bus])
    with pytest.raises(ValueError, match=r"bus.*-1.*out of valid range"):
        EMBuilder.generate(config_neg)


def test_builder_generate_from_devices_helper() -> None:
    """Test the generate_from_devices classmethod helper."""
    tmpl = get_template("TMP75")
    assert tmpl is not None

    devices = [EMDeviceEntry(template=tmpl, bus=3, address=0x49, name="TMP75_Aux")]
    json_str = EMBuilder.generate_from_devices(
        "Helper_Board",
        devices,
        probe_expression="xyz.openbmc_project.FruDevice({'PRODUCT_PRODUCT_NAME': 'MyBoard'})",
    )
    data = json.loads(json_str)

    assert data["Name"] == "Helper_Board"
    assert "FruDevice" in data["Probe"]
    assert len(data["Exposes"]) == 1
    assert data["Exposes"][0]["Bus"] == 3


# ---------------------------------------------------------------------------
# Validator Tests
# ---------------------------------------------------------------------------


def test_validator_valid_json_no_issues() -> None:
    """Test validating properly formed Entity-Manager JSON returns empty issue list."""
    valid_json = json.dumps(
        {
            "Name": "Valid_Board",
            "Probe": "TRUE",
            "Exposes": [
                {
                    "Address": "0x48",
                    "Bus": 1,
                    "Name": "TMP75_Sensor",
                    "Type": "TMP75",
                    "PowerState": "On",
                }
            ],
        }
    )
    issues = EMValidator.validate(valid_json)
    assert issues == []


def test_validator_malformed_json_syntax_error() -> None:
    """Test validating malformed JSON returns CRITICAL syntax error."""
    malformed_json = '{"Name": "Broken_Board", "Exposes": [ '  # Unterminated
    issues = EMValidator.validate(malformed_json)

    assert len(issues) == 1
    assert issues[0].severity == Severity.CRITICAL
    assert issues[0].field_path == "root"
    assert "syntax error" in issues[0].message.lower()


def test_validator_invalid_root_structure() -> None:
    """Test validating JSON with primitive root element returns CRITICAL error."""
    issues = EMValidator.validate('"Just A String"')
    assert len(issues) == 1
    assert issues[0].severity == Severity.CRITICAL
    assert issues[0].field_path == "root"


def test_validator_missing_name_warning() -> None:
    """Test missing or empty Name field generates a WARNING issue."""
    json_no_name = json.dumps(
        {
            "Probe": "TRUE",
            "Exposes": [
                {
                    "Address": "0x48",
                    "Bus": 1,
                    "Name": "TMP75_Sensor",
                    "Type": "TMP75",
                }
            ],
        }
    )
    issues = EMValidator.validate(json_no_name)
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert issues[0].field_path == "Name"


def test_validator_missing_required_fields_in_exposes() -> None:
    """Test missing Type, Name, Bus, and Address in Exposes generates ERROR issues."""
    incomplete_json = json.dumps(
        {
            "Name": "Incomplete_Board",
            "Exposes": [
                {},  # Missing all required fields
            ],
        }
    )
    issues = EMValidator.validate(incomplete_json)
    paths = [iss.field_path for iss in issues]

    assert "Exposes[0].Type" in paths
    assert "Exposes[0].Name" in paths
    assert "Exposes[0].Bus" in paths
    assert "Exposes[0].Address" in paths
    assert all(iss.severity == Severity.ERROR for iss in issues)


def test_validator_address_out_of_range() -> None:
    """Test address < 0x08 or > 0x77 generates ERROR issue."""
    invalid_addr_json = json.dumps(
        {
            "Name": "Bad_Addr_Board",
            "Exposes": [
                {"Name": "Dev_03", "Type": "TMP75", "Bus": 1, "Address": "0x03"},
                {"Name": "Dev_78", "Type": "TMP75", "Bus": 1, "Address": 120},  # 120 = 0x78
            ],
        }
    )
    issues = EMValidator.validate(invalid_addr_json)
    addr_issues = [iss for iss in issues if iss.field_path.endswith(".Address")]

    assert len(addr_issues) == 2
    assert all(iss.severity == Severity.ERROR for iss in addr_issues)
    assert "0x03" in addr_issues[0].message
    assert "0x78" in addr_issues[1].message


def test_validator_duplicate_bus_address_conflict() -> None:
    """Test duplicate (bus, address) across Exposes entries generates ERROR issue."""
    conflict_json = json.dumps(
        {
            "Name": "Conflict_Board",
            "Exposes": [
                {"Name": "Sensor_1", "Type": "TMP75", "Bus": 1, "Address": "0x48"},
                {
                    "Name": "Sensor_2",
                    "Type": "LM75",
                    "Bus": 1,
                    "Address": 72,
                },  # 72 == 0x48 -> conflict
            ],
        }
    )
    issues = EMValidator.validate(conflict_json)
    conflict_issues = [
        iss for iss in issues if iss.severity == Severity.ERROR and "Duplicate" in iss.message
    ]

    assert len(conflict_issues) == 1
    assert conflict_issues[0].field_path == "Exposes[1]"
    assert "Exposes[0]" in conflict_issues[0].message


def test_validator_board_profile_cross_reference() -> None:
    """Test cross-referencing with BoardProfile for matching, mismatch, and missing devices."""
    profile_yaml = """
board_name: "Server_Baseboard"
version: "1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: "fast"
    devices:
      - name: "TMP75_U1"
        address_7bit: 0x48
        category: "temperature"
        protocol: "i2c"
        compatible: "ti,tmp75"
        register_width: 8
      - name: "LM75_U2"
        address_7bit: 0x49
        category: "temperature"
        protocol: "i2c"
        compatible: "national,lm75"
        register_width: 8
      - name: "EEPROM_U3"
        address_7bit: 0x50
        category: "fru"
        protocol: "i2c"
        compatible: "atmel,24c64"
        register_width: 8
"""
    profile = BoardProfile.from_text(profile_yaml)

    # EM JSON configures:
    # 0x48: TMP75 (matches)
    # 0x49: PCA9555 / GPIO_Expander (mismatch with LM75_U2)
    # 0x50: missing from EM Exposes
    em_json = json.dumps(
        {
            "Name": "Server_Baseboard",
            "Exposes": [
                {"Name": "TMP75_U1", "Type": "TMP75", "Bus": 1, "Address": "0x48"},
                {"Name": "GPIO_Expander", "Type": "PCA9555", "Bus": 1, "Address": "0x49"},
            ],
        }
    )

    issues = EMValidator.validate(em_json, board_profile=profile)

    # We expect 1 WARNING (mismatch on 0x49) and 1 INFO (missing 0x50)
    warning_issues = [iss for iss in issues if iss.severity == Severity.WARNING]
    info_issues = [iss for iss in issues if iss.severity == Severity.INFO]

    assert len(warning_issues) == 1
    assert "0x49" in warning_issues[0].message
    assert "LM75_U2" in warning_issues[0].message
    assert "GPIO_Expander" in warning_issues[0].message

    assert len(info_issues) == 1
    assert "EEPROM_U3" in info_issues[0].message
    assert "0x50" in info_issues[0].message


def test_round_trip_build_generate_validate() -> None:
    """Test full round-trip: build config -> generate JSON -> validate -> 0 issues."""
    tmp75 = get_template("TMP75")
    max31790 = get_template("MAX31790")
    assert tmp75 is not None
    assert max31790 is not None

    dev1 = EMDeviceEntry(template=tmp75, bus=2, address=0x48, name="Ambient_Temp")
    dev2 = EMDeviceEntry(template=max31790, bus=2, address=0x20, name="Fan_Controller")

    config = EMBoardConfig(board_name="Production_Board", devices=[dev1, dev2])
    json_str = EMBuilder.generate(config)

    issues = EMValidator.validate(json_str)
    assert issues == []
