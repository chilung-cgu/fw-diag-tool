from __future__ import annotations

import dataclasses

import pytest

from fw_diag_tool.i2c.models import Severity


def test_em_device_template_frozen():
    from fw_diag_tool.em.models import EMDeviceTemplate

    tmpl = EMDeviceTemplate(
        category="temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Thresholds": [{"Direction": "greater than", "Severity": 1, "Value": 95}]},
        description="TI TMP75 Digital Temperature Sensor",
    )
    assert tmpl.category == "temperature"
    assert tmpl.chip_name == "TMP75"
    assert tmpl.em_type == "TMP75"
    assert tmpl.default_power_state == "On"
    assert "Bus" in tmpl.required_fields
    assert tmpl.description == "TI TMP75 Digital Temperature Sensor"

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        tmpl.chip_name = "TMP421"  # type: ignore[misc]

    d = tmpl.to_dict()
    assert d["chip_name"] == "TMP75"
    assert d["category"] == "temperature"
    assert d["em_type"] == "TMP75"
    assert d["default_power_state"] == "On"
    assert d["required_fields"] == ["Bus", "Address", "Name"]
    assert "Thresholds" in d["optional_fields"]


def test_em_validation_issue_frozen():
    from fw_diag_tool.em.models import EMValidationIssue

    issue = EMValidationIssue(
        severity=Severity.ERROR,
        field_path="Exposes[0].Address",
        message="Address 0x48 conflicts with Exposes[1]",
        suggestion="Change I2C address to unique value",
    )
    assert issue.severity == Severity.ERROR
    assert issue.field_path == "Exposes[0].Address"
    assert issue.message == "Address 0x48 conflicts with Exposes[1]"
    assert issue.suggestion == "Change I2C address to unique value"

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        issue.message = "Changed"  # type: ignore[misc]

    d = issue.to_dict()
    assert d["severity"] == "ERROR"
    assert d["field_path"] == "Exposes[0].Address"
    assert d["message"] == "Address 0x48 conflicts with Exposes[1]"
    assert d["suggestion"] == "Change I2C address to unique value"


def test_em_device_entry_to_exposes_dict_default_power():
    from fw_diag_tool.em.models import EMDeviceEntry, EMDeviceTemplate

    tmpl = EMDeviceTemplate(
        category="temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={
            "Thresholds": [
                {"Direction": "greater than", "Name": "upper critical", "Severity": 1, "Value": 95}
            ]
        },
        description="TMP75",
    )
    dev = EMDeviceEntry(
        template=tmpl,
        bus=2,
        address=0x48,
        name="BMC_TEMP0",
    )
    assert dev.bus == 2
    assert dev.address == 0x48
    assert dev.name == "BMC_TEMP0"
    assert dev.power_state is None

    exposes = dev.to_exposes_dict()
    assert exposes["Bus"] == 2
    assert exposes["Address"] == "0x48"
    assert exposes["Name"] == "BMC_TEMP0"
    assert exposes["Type"] == "TMP75"
    assert exposes["PowerState"] == "On"
    assert "Thresholds" in exposes
    assert len(exposes["Thresholds"]) == 1


def test_em_device_entry_to_exposes_dict_override_power_and_custom_fields():
    from fw_diag_tool.em.models import EMDeviceEntry, EMDeviceTemplate

    tmpl = EMDeviceTemplate(
        category="fru",
        chip_name="AT24C256",
        em_type="EEPROM",
        default_power_state="Always",
        description="AT24C256 EEPROM",
    )
    dev = EMDeviceEntry(
        template=tmpl,
        bus=1,
        address=0x50,
        name="MB_FRU",
        power_state="BiosPost",
        custom_fields={"WriteProtect": True, "CustomTag": "PROD"},
    )
    exposes = dev.to_exposes_dict()
    assert exposes["Bus"] == 1
    assert exposes["Address"] == "0x50"
    assert exposes["Name"] == "MB_FRU"
    assert exposes["Type"] == "EEPROM"
    assert exposes["PowerState"] == "BiosPost"
    assert exposes["WriteProtect"] is True
    assert exposes["CustomTag"] == "PROD"


def test_em_board_config_to_dict():
    from fw_diag_tool.em.models import EMBoardConfig, EMDeviceEntry, EMDeviceTemplate

    tmpl_tmp = EMDeviceTemplate(
        category="temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        description="TMP75",
    )
    tmpl_fru = EMDeviceTemplate(
        category="fru",
        chip_name="AT24C256",
        em_type="EEPROM",
        default_power_state="Always",
        description="AT24C256",
    )
    dev1 = EMDeviceEntry(template=tmpl_tmp, bus=2, address=0x48, name="TEMP_SENSOR")
    dev2 = EMDeviceEntry(template=tmpl_fru, bus=1, address=0x50, name="SYS_FRU")

    board = EMBoardConfig(
        board_name="Yosemite_V4",
        devices=[dev1, dev2],
        probe_expression="xyz.openbmc_project.FruDevice({'PRODUCT_PRODUCT_NAME': 'Yosemite'})",
    )
    d = board.to_dict()
    assert d["Name"] == "Yosemite_V4"
    assert d["Probe"] == "xyz.openbmc_project.FruDevice({'PRODUCT_PRODUCT_NAME': 'Yosemite'})"
    assert len(d["Exposes"]) == 2
    assert d["Exposes"][0]["Name"] == "TEMP_SENSOR"
    assert d["Exposes"][0]["Address"] == "0x48"
    assert d["Exposes"][1]["Name"] == "SYS_FRU"
    assert d["Exposes"][1]["Address"] == "0x50"


def test_device_templates_catalog_coverage():
    from fw_diag_tool.em.templates import DEVICE_TEMPLATES, get_all_categories

    assert len(DEVICE_TEMPLATES) >= 12

    categories = get_all_categories()
    expected_categories = {"temperature", "adc", "fru", "fan", "psu", "gpio", "hotswap"}
    assert expected_categories.issubset(set(categories))

    # Verify specific chips exist in catalog
    required_chips = [
        "TMP75",
        "TMP421",
        "LM75",
        "EMC1413",
        "ADC128D818",
        "AT24C256",
        "AT24C64",
        "MAX31790",
        "EMC2305",
        "PMBus",
        "PCA9555",
        "ADM1272",
        "LTC4282",
    ]
    for chip in required_chips:
        assert chip in DEVICE_TEMPLATES, f"Missing required chip template: {chip}"
        tmpl = DEVICE_TEMPLATES[chip]
        assert tmpl.chip_name == chip
        assert tmpl.category in expected_categories
        assert tmpl.em_type
        assert tmpl.default_power_state in {"On", "Always", "BiosPost"}


def test_get_template_helper():
    from fw_diag_tool.em.templates import get_template

    tmpl = get_template("TMP75")
    assert tmpl is not None
    assert tmpl.chip_name == "TMP75"

    tmpl_lower = get_template("tmp75")
    assert tmpl_lower is not None
    assert tmpl_lower.chip_name == "TMP75"

    assert get_template("NON_EXISTENT_CHIP") is None


def test_get_templates_by_category_helper():
    from fw_diag_tool.em.templates import get_templates_by_category

    temp_templates = get_templates_by_category("temperature")
    assert len(temp_templates) >= 4
    for t in temp_templates:
        assert t.category == "temperature"

    # Case insensitivity
    temp_templates_upper = get_templates_by_category("TEMPERATURE")
    assert len(temp_templates_upper) == len(temp_templates)

    # Empty for unknown category
    assert get_templates_by_category("unknown_category") == []


def test_package_exports():
    from fw_diag_tool import em

    assert hasattr(em, "EMDeviceTemplate")
    assert hasattr(em, "EMDeviceEntry")
    assert hasattr(em, "EMBoardConfig")
    assert hasattr(em, "EMValidationIssue")
    assert hasattr(em, "DEVICE_TEMPLATES")
    assert hasattr(em, "get_template")
    assert hasattr(em, "get_templates_by_category")
    assert hasattr(em, "get_all_categories")
