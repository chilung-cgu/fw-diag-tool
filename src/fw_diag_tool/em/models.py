"""Entity-Manager configuration and validation data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fw_diag_tool.i2c.models import Severity


@dataclass(frozen=True)
class EMDeviceTemplate:
    """Template defining properties, exposed fields, and defaults for an Entity-Manager device."""

    category: str
    chip_name: str
    em_type: str
    default_power_state: str = "On"
    required_fields: list[str] = field(default_factory=lambda: ["Bus", "Address", "Name"])
    optional_fields: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "category": self.category,
            "chip_name": self.chip_name,
            "em_type": self.em_type,
            "default_power_state": self.default_power_state,
            "required_fields": list(self.required_fields),
            "optional_fields": dict(self.optional_fields),
            "description": self.description,
        }


@dataclass
class EMDeviceEntry:
    """Configured device entry on a board."""

    template: EMDeviceTemplate
    bus: int
    address: int
    name: str
    power_state: str | None = None
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def to_exposes_dict(self) -> dict[str, Any]:
        """Convert entry into OpenBMC Entity-Manager Exposes item format."""
        addr_str = f"0x{self.address:02x}" if isinstance(self.address, int) else str(self.address)
        p_state = (
            self.power_state if self.power_state is not None else self.template.default_power_state
        )

        exposes: dict[str, Any] = {
            "Address": addr_str,
            "Bus": self.bus,
            "Name": self.name,
            "Type": self.template.em_type,
        }
        if p_state:
            exposes["PowerState"] = p_state

        if self.template.optional_fields:
            for k, v in self.template.optional_fields.items():
                exposes[k] = v

        if self.custom_fields:
            for k, v in self.custom_fields.items():
                exposes[k] = v

        return exposes

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary."""
        return {
            "template": self.template.to_dict(),
            "bus": self.bus,
            "address": self.address,
            "name": self.name,
            "power_state": self.power_state,
            "custom_fields": dict(self.custom_fields),
            "exposes": self.to_exposes_dict(),
        }


@dataclass
class EMBoardConfig:
    """Complete board configuration containing multiple device entries."""

    board_name: str
    devices: list[EMDeviceEntry] = field(default_factory=list)
    probe_expression: str = "TRUE"

    def to_dict(self) -> dict[str, Any]:
        """Convert board configuration to OpenBMC Entity-Manager JSON dictionary format."""
        return {
            "Exposes": [dev.to_exposes_dict() for dev in self.devices],
            "Name": self.board_name,
            "Probe": self.probe_expression,
        }


@dataclass(frozen=True)
class EMValidationIssue:
    """Validation issue discovered during Entity-Manager configuration inspection."""

    severity: Severity
    field_path: str
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert validation issue to dictionary."""
        return {
            "severity": self.severity.value
            if hasattr(self.severity, "value")
            else str(self.severity),
            "field_path": self.field_path,
            "message": self.message,
            "suggestion": self.suggestion,
        }
