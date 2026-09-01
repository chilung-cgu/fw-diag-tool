"""Pre-built Entity-Manager device templates catalog for common BMC sensors and ICs."""

from __future__ import annotations

from fw_diag_tool.em.models import EMDeviceTemplate

DEVICE_TEMPLATES: dict[str, EMDeviceTemplate] = {
    # 1. Temperature Sensors
    "TMP75": EMDeviceTemplate(
        category="temperature",
        chip_name="TMP75",
        em_type="TMP75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={
            "Thresholds": [
                {
                    "Direction": "greater than",
                    "Name": "upper critical",
                    "Severity": 1,
                    "Value": 95,
                },
                {
                    "Direction": "greater than",
                    "Name": "upper non critical",
                    "Severity": 0,
                    "Value": 85,
                },
            ]
        },
        description="Texas Instruments TMP75 Digital Temperature Sensor",
    ),
    "TMP421": EMDeviceTemplate(
        category="temperature",
        chip_name="TMP421",
        em_type="TMP421",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={
            "Thresholds": [
                {
                    "Direction": "greater than",
                    "Name": "upper critical",
                    "Severity": 1,
                    "Value": 90,
                },
                {
                    "Direction": "greater than",
                    "Name": "upper non critical",
                    "Severity": 0,
                    "Value": 80,
                },
            ]
        },
        description="Texas Instruments TMP421 Remote/Local Temperature Sensor",
    ),
    "LM75": EMDeviceTemplate(
        category="temperature",
        chip_name="LM75",
        em_type="LM75",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={
            "Thresholds": [
                {
                    "Direction": "greater than",
                    "Name": "upper critical",
                    "Severity": 1,
                    "Value": 85,
                },
                {
                    "Direction": "greater than",
                    "Name": "upper non critical",
                    "Severity": 0,
                    "Value": 75,
                },
            ]
        },
        description="National Semiconductor / TI LM75 Temperature Sensor",
    ),
    "EMC1413": EMDeviceTemplate(
        category="temperature",
        chip_name="EMC1413",
        em_type="EMC1413",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={
            "Thresholds": [
                {
                    "Direction": "greater than",
                    "Name": "upper critical",
                    "Severity": 1,
                    "Value": 95,
                },
                {
                    "Direction": "greater than",
                    "Name": "upper non critical",
                    "Severity": 0,
                    "Value": 85,
                },
            ]
        },
        description="Microchip EMC1413 Multiple Channel Temperature Sensor",
    ),
    # 2. ADC
    "ADC128D818": EMDeviceTemplate(
        category="adc",
        chip_name="ADC128D818",
        em_type="ADC128D818",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Channel": 0},
        description="TI ADC128D818 12-Bit 8-Channel System Monitor",
    ),
    # 3. FRU / EEPROM
    "AT24C256": EMDeviceTemplate(
        category="fru",
        chip_name="AT24C256",
        em_type="EEPROM",
        default_power_state="Always",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={},
        description="Atmel/Microchip AT24C256 I2C 256K Serial EEPROM",
    ),
    "AT24C64": EMDeviceTemplate(
        category="fru",
        chip_name="AT24C64",
        em_type="EEPROM",
        default_power_state="Always",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={},
        description="Atmel/Microchip AT24C64 I2C 64K Serial EEPROM",
    ),
    # 4. Fan Controller
    "MAX31790": EMDeviceTemplate(
        category="fan",
        chip_name="MAX31790",
        em_type="MAX31790",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"TachConnector": "Tach0", "TargetConnector": "Pwm0"},
        description="Maxim MAX31790 6-Channel PWM Fan Controller and Tachometer",
    ),
    "EMC2305": EMDeviceTemplate(
        category="fan",
        chip_name="EMC2305",
        em_type="EMC2305",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"PwmChannel": 0},
        description="Microchip EMC2305 RPM-Based PWM Fan Controller",
    ),
    # 5. Power Supply / PMBus
    "PMBus": EMDeviceTemplate(
        category="psu",
        chip_name="PMBus",
        em_type="PMBus",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={},
        description="Generic PMBus Power Supply Monitor",
    ),
    # 6. GPIO Expander
    "PCA9555": EMDeviceTemplate(
        category="gpio",
        chip_name="PCA9555",
        em_type="PCA9555",
        default_power_state="Always",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"PolarityInversion": False},
        description="NXP PCA9555 16-bit I2C GPIO Expander",
    ),
    # 7. Hot-swap Controller
    "ADM1272": EMDeviceTemplate(
        category="hotswap",
        chip_name="ADM1272",
        em_type="ADM1272",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Rsense": 0.001},
        description="Analog Devices ADM1272 High Voltage Hot-Swap Controller",
    ),
    "LTC4282": EMDeviceTemplate(
        category="hotswap",
        chip_name="LTC4282",
        em_type="LTC4282",
        default_power_state="On",
        required_fields=["Bus", "Address", "Name"],
        optional_fields={"Rsense": 0.001},
        description="Linear Technology / ADI LTC4282 Hot-Swap Controller",
    ),
}


def get_template(chip_name: str) -> EMDeviceTemplate | None:
    """Retrieve an EMDeviceTemplate by chip name (case-insensitive)."""
    if chip_name in DEVICE_TEMPLATES:
        return DEVICE_TEMPLATES[chip_name]
    chip_lower = chip_name.strip().lower()
    for name, tmpl in DEVICE_TEMPLATES.items():
        if name.lower() == chip_lower or tmpl.chip_name.lower() == chip_lower:
            return tmpl
    return None


def get_templates_by_category(category: str) -> list[EMDeviceTemplate]:
    """Retrieve all device templates belonging to a specific category (case-insensitive)."""
    cat_lower = category.strip().lower()
    return [tmpl for tmpl in DEVICE_TEMPLATES.values() if tmpl.category.lower() == cat_lower]


def get_all_categories() -> list[str]:
    """Retrieve all unique template categories in order of appearance."""
    seen: set[str] = set()
    categories: list[str] = []
    for tmpl in DEVICE_TEMPLATES.values():
        if tmpl.category not in seen:
            seen.add(tmpl.category)
            categories.append(tmpl.category)
    return categories
