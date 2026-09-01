"""OpenBMC Entity-Manager JSON configuration validator."""

from __future__ import annotations

import json
from typing import Any

from fw_diag_tool.board_profile import BoardProfile, I2CDeviceProfile
from fw_diag_tool.em.models import EMValidationIssue
from fw_diag_tool.em.templates import get_template
from fw_diag_tool.i2c.models import Severity


class EMValidator:
    """Validator for OpenBMC Entity-Manager JSON configurations and board profile cross-referencing."""

    @classmethod
    def validate(
        cls,
        json_text: str,
        *,
        board_profile: BoardProfile | None = None,
    ) -> list[EMValidationIssue]:
        """Validate an Entity-Manager JSON string against structural rules and an optional BoardProfile.

        Args:
            json_text: Raw JSON string to validate.
            board_profile: Optional BoardProfile instance for topology cross-referencing.

        Returns:
            List of EMValidationIssue objects discovered during inspection.
        """
        issues: list[EMValidationIssue] = []

        # 1. Valid JSON syntax
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            return [
                EMValidationIssue(
                    severity=Severity.CRITICAL,
                    field_path="root",
                    message=f"JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                    suggestion="Fix the JSON syntax errors",
                )
            ]

        # 2. Root structure check
        if not isinstance(data, (dict, list)):
            return [
                EMValidationIssue(
                    severity=Severity.CRITICAL,
                    field_path="root",
                    message="Root element must be a JSON object or array of objects",
                    suggestion="Wrap configuration in a JSON object with 'Exposes' array",
                )
            ]

        configs: list[dict[str, Any]] = (
            [data] if isinstance(data, dict) else [item for item in data if isinstance(item, dict)]
        )

        if isinstance(data, list) and not configs:
            return [
                EMValidationIssue(
                    severity=Severity.CRITICAL,
                    field_path="root",
                    message="Root list must contain JSON configuration objects",
                    suggestion="Provide at least one configuration object in the array",
                )
            ]

        for config in configs:
            cls._validate_single_config(config, issues, board_profile=board_profile)

        return issues

    @classmethod
    def _validate_single_config(
        cls,
        data: dict[str, Any],
        issues: list[EMValidationIssue],
        *,
        board_profile: BoardProfile | None = None,
    ) -> None:
        """Validate a single Entity-Manager configuration object."""
        # 3. Name field check
        board_name = data.get("Name")
        if not board_name or not isinstance(board_name, str) or not board_name.strip():
            issues.append(
                EMValidationIssue(
                    severity=Severity.WARNING,
                    field_path="Name",
                    message="Missing or empty 'Name' field",
                    suggestion="Provide a descriptive board or module name",
                )
            )

        # 4. Exposes field check
        if "Exposes" not in data:
            issues.append(
                EMValidationIssue(
                    severity=Severity.ERROR,
                    field_path="Exposes",
                    message="Missing 'Exposes' array in configuration",
                    suggestion="Add an 'Exposes' list of device configurations",
                )
            )
            return

        exposes = data.get("Exposes")
        if not isinstance(exposes, list):
            issues.append(
                EMValidationIssue(
                    severity=Severity.ERROR,
                    field_path="Exposes",
                    message="'Exposes' must be an array of device configurations",
                    suggestion="Ensure 'Exposes' is a list",
                )
            )
            return

        seen_endpoints: dict[tuple[int, int], int] = {}
        configured_em_devices: dict[tuple[int, int], tuple[str, str, int]] = {}

        for i, entry in enumerate(exposes):
            if not isinstance(entry, dict):
                issues.append(
                    EMValidationIssue(
                        severity=Severity.ERROR,
                        field_path=f"Exposes[{i}]",
                        message="Exposes entry must be an object",
                        suggestion="Provide a JSON object representing the device entry",
                    )
                )
                continue

            # Type check
            em_type = entry.get("Type")
            if not em_type or not isinstance(em_type, str) or not em_type.strip():
                issues.append(
                    EMValidationIssue(
                        severity=Severity.ERROR,
                        field_path=f"Exposes[{i}].Type",
                        message="Missing or empty 'Type' field",
                        suggestion="Specify an Entity-Manager device type (e.g. 'TMP75')",
                    )
                )

            # Name check
            em_name = entry.get("Name")
            if not em_name or not isinstance(em_name, str) or not em_name.strip():
                issues.append(
                    EMValidationIssue(
                        severity=Severity.ERROR,
                        field_path=f"Exposes[{i}].Name",
                        message="Missing or empty 'Name' field",
                        suggestion="Specify a descriptive name for the device",
                    )
                )

            # Bus check
            bus_val: int | None = None
            if "Bus" not in entry:
                issues.append(
                    EMValidationIssue(
                        severity=Severity.ERROR,
                        field_path=f"Exposes[{i}].Bus",
                        message="Missing 'Bus' field",
                        suggestion="Specify the I2C bus index",
                    )
                )
            else:
                raw_bus = entry["Bus"]
                if isinstance(raw_bus, bool) or not isinstance(raw_bus, (int, str)):
                    issues.append(
                        EMValidationIssue(
                            severity=Severity.ERROR,
                            field_path=f"Exposes[{i}].Bus",
                            message="Invalid 'Bus' value, must be a non-negative integer",
                            suggestion="Provide a valid integer for the I2C bus index",
                        )
                    )
                else:
                    try:
                        bus_int = (
                            int(raw_bus) if isinstance(raw_bus, int) else int(raw_bus.strip(), 0)
                        )
                        if bus_int < 0 or bus_int > 65535:
                            issues.append(
                                EMValidationIssue(
                                    severity=Severity.ERROR,
                                    field_path=f"Exposes[{i}].Bus",
                                    message=f"Bus value {bus_int} out of range (0..65535)",
                                    suggestion="Use a valid I2C bus number between 0 and 65535",
                                )
                            )
                        else:
                            bus_val = bus_int
                    except ValueError:
                        issues.append(
                            EMValidationIssue(
                                severity=Severity.ERROR,
                                field_path=f"Exposes[{i}].Bus",
                                message="Invalid 'Bus' format, must be an integer",
                                suggestion="Provide a numeric integer for the I2C bus",
                            )
                        )

            # Address check
            addr_val: int | None = None
            if "Address" not in entry:
                issues.append(
                    EMValidationIssue(
                        severity=Severity.ERROR,
                        field_path=f"Exposes[{i}].Address",
                        message="Missing 'Address' field",
                        suggestion="Specify the 7-bit I2C address (e.g. '0x48')",
                    )
                )
            else:
                raw_addr = entry["Address"]
                if isinstance(raw_addr, bool) or not isinstance(raw_addr, (int, str)):
                    issues.append(
                        EMValidationIssue(
                            severity=Severity.ERROR,
                            field_path=f"Exposes[{i}].Address",
                            message="Invalid 'Address' format, must be an integer or hex string",
                            suggestion="Provide address as integer (e.g. 72) or hex string (e.g. '0x48')",
                        )
                    )
                else:
                    try:
                        if isinstance(raw_addr, int):
                            addr_int = raw_addr
                        else:
                            token = raw_addr.strip()
                            addr_int = (
                                int(token, 0)
                                if token.startswith(("0x", "0X"))
                                else (int(token, 10) if token.isdecimal() else int(token, 0))
                            )

                        if not (0x08 <= addr_int <= 0x77):
                            issues.append(
                                EMValidationIssue(
                                    severity=Severity.ERROR,
                                    field_path=f"Exposes[{i}].Address",
                                    message=f"Address 0x{addr_int:02x} is out of valid 7-bit I2C range (0x08..0x77)",
                                    suggestion="Use a standard 7-bit non-reserved I2C address (0x08..0x77)",
                                )
                            )
                        else:
                            addr_val = addr_int
                    except ValueError:
                        issues.append(
                            EMValidationIssue(
                                severity=Severity.ERROR,
                                field_path=f"Exposes[{i}].Address",
                                message="Invalid 'Address' format, must be an integer or hex string",
                                suggestion="Provide address as integer or hex string (e.g. '0x48')",
                            )
                        )

            # 5. Duplicate endpoint conflict check
            if bus_val is not None and addr_val is not None:
                endpoint = (bus_val, addr_val)
                if endpoint in seen_endpoints:
                    prior_idx = seen_endpoints[endpoint]
                    issues.append(
                        EMValidationIssue(
                            severity=Severity.ERROR,
                            field_path=f"Exposes[{i}]",
                            message=f"Duplicate bus and address conflict with Exposes[{prior_idx}] (Bus {bus_val}, Address 0x{addr_val:02x})",
                            suggestion="Assign unique bus/address combinations to each device",
                        )
                    )
                else:
                    seen_endpoints[endpoint] = i
                    configured_em_devices[endpoint] = (
                        str(em_name or ""),
                        str(em_type or ""),
                        i,
                    )

        # 6. Optional BoardProfile cross-reference
        if board_profile is not None and configured_em_devices:
            cls._cross_reference_board_profile(configured_em_devices, board_profile, issues)

    @classmethod
    def _cross_reference_board_profile(
        cls,
        configured_em_devices: dict[tuple[int, int], tuple[str, str, int]],
        board_profile: BoardProfile,
        issues: list[EMValidationIssue],
    ) -> None:
        """Cross-reference Entity-Manager endpoints against a BoardProfile."""
        em_buses = {endpoint[0] for endpoint in configured_em_devices}

        for bus_prof in board_profile.i2c_buses:
            bus = bus_prof.bus_num
            if bus not in em_buses:
                continue

            # Gather devices and muxes on this bus
            bp_devices: list[I2CDeviceProfile] = list(bus_prof.devices) + list(bus_prof.muxes)

            for dev in bp_devices:
                addr = dev.address_7bit
                endpoint = (bus, addr)

                if endpoint in configured_em_devices:
                    em_name, em_type, em_idx = configured_em_devices[endpoint]
                    if not cls._devices_match(dev, em_name, em_type):
                        issues.append(
                            EMValidationIssue(
                                severity=Severity.WARNING,
                                field_path=f"Exposes[{em_idx}]",
                                message=(
                                    f"Address 0x{addr:02x} on Bus {bus} is defined as '{dev.name}' "
                                    f"({dev.compatible}) in BoardProfile, but configured as '{em_name}' "
                                    f"({em_type}) in Entity-Manager JSON."
                                ),
                                suggestion="Verify if the device type and name correspond to the board profile specification",
                            )
                        )
                else:
                    issues.append(
                        EMValidationIssue(
                            severity=Severity.INFO,
                            field_path=f"Bus[{bus}].0x{addr:02x}",
                            message=(
                                f"BoardProfile device '{dev.name}' (0x{dev.address_7bit:02x}) on Bus {bus} "
                                f"is not present in this Entity-Manager configuration."
                            ),
                            suggestion="Consider adding this device to the Entity-Manager Exposes list if needed",
                        )
                    )

    @classmethod
    def _devices_match(cls, dev: I2CDeviceProfile, em_name: str, em_type: str) -> bool:
        """Check whether a BoardProfile device matches an Entity-Manager entry."""
        if not em_name and not em_type:
            return False

        # Name match
        if dev.name.strip().casefold() == em_name.strip().casefold():
            return True

        # Compatible / Type match
        compat_part = dev.compatible.split(",", 1)[-1].strip().casefold()
        em_type_cf = em_type.strip().casefold()

        if em_type_cf and (compat_part in em_type_cf or em_type_cf in compat_part):
            return True

        # EEPROM / 24C match
        if em_type_cf == "eeprom" and ("24c" in compat_part or "eeprom" in compat_part):
            return True

        # PMBus match
        if em_type_cf == "pmbus" and (
            "pmbus" in compat_part or dev.category.strip().casefold() == "psu"
        ):
            return True

        # Template lookup match
        tmpl = get_template(em_type)
        if tmpl is not None:
            return (
                tmpl.chip_name.strip().casefold() in compat_part
                or compat_part in tmpl.chip_name.strip().casefold()
            )

        return False
