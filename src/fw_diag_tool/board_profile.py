"""Board Profile schema and YAML/JSON loading helpers.

The profile is intentionally a description of the wired I2C topology, not a
probe result.  A profile can contain devices directly on a bus and devices
behind an I2C mux.  Addresses are stored as 7-bit integers after parsing, so
JSON profiles can use either decimal integers or strings such as ``"0x50"``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from typing_extensions import Self


class SchemaError(ValueError):
    """Raised when a Board Profile cannot be parsed or violates the schema."""

    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


# Keep the aliases discoverable for callers that prefer a domain-specific name.
BoardProfileError = SchemaError
BoardProfileSchemaError = SchemaError


_COMPATIBLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9,._+\-]*,[A-Za-z0-9][A-Za-z0-9,._+\-]*$")
_REGISTER_ACCESSES = frozenset({"RO", "RW", "WO", "W1C"})
_SPEED_MODE_ALIASES = {
    "standard-mode": "standard",
    "standard_mode": "standard",
    "fast-mode": "fast",
    "fast_mode": "fast",
    "fast-mode-plus": "fast_plus",
    "fast_mode_plus": "fast_plus",
    "fast-plus": "fast_plus",
    "fast_plus": "fast_plus",
    "fastplus": "fast_plus",
    "high-speed": "high_speed",
    "high_speed": "high_speed",
    "highspeed": "high_speed",
    "ultra-fast": "ultra_fast",
    "ultra_fast": "ultra_fast",
}
_SPEED_MODES = frozenset({"standard", "fast", "fast_plus", "high_speed", "ultra_fast"})


class _DuplicateKeyError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise _DuplicateKeyError(f"found duplicate key {key!r}")
        mapping[key] = value
    return mapping


def _parse_int(value: Any, label: str) -> int:
    """Parse an integer without accepting booleans or lossy float coercion."""

    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SchemaError(f"{label} must be an integer")
    if isinstance(value, int):
        return value

    token = value.strip()
    if not token:
        raise ValueError(f"{label} must be an integer")
    try:
        return int(token, 0)
    except ValueError:
        # Base-10 fallback keeps JSON strings such as "08" unambiguous.
        if token.isdecimal():
            return int(token, 10)
        raise ValueError(f"{label} must be an integer") from None


def _parse_address(value: Any) -> int:
    address = _parse_int(value, "address_7bit")
    if not 0x08 <= address <= 0x77:
        raise ValueError("address_7bit must be a non-reserved 7-bit I2C address (0x08..0x77)")
    return address


def _non_empty_string(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


class _SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class RegisterDefinition(_SchemaModel):
    """One register address and its optional access metadata."""

    name: str
    offset: int
    access: str = "RW"
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_offset_alias(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        has_offset = "offset" in normalized
        has_address = "address" in normalized
        if has_offset and has_address:
            raise ValueError("register must use only one of offset or address")
        if has_address:
            normalized["offset"] = normalized.pop("address")
        return normalized

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _non_empty_string(value, "register name")

    @field_validator("offset", mode="before")
    @classmethod
    def _validate_offset(cls, value: Any) -> int:
        offset = _parse_int(value, "register offset")
        if not 0 <= offset <= 0xFFFF:
            raise ValueError("register offset must be between 0 and 0xFFFF")
        return offset

    @field_validator("access")
    @classmethod
    def _validate_access(cls, value: str) -> str:
        access = _non_empty_string(value, "register access").upper()
        if access not in _REGISTER_ACCESSES:
            allowed = ", ".join(sorted(_REGISTER_ACCESSES))
            raise ValueError(f"register access {access!r} is unsupported; choose one of: {allowed}")
        return access


class CommandDefinition(_SchemaModel):
    """One command code and its optional description."""

    name: str
    code: int
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_code_alias(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        has_code = "code" in normalized
        has_command_code = "command_code" in normalized
        if has_code and has_command_code:
            raise ValueError("command must use only one of code or command_code")
        if has_command_code:
            normalized["code"] = normalized.pop("command_code")
        return normalized

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _non_empty_string(value, "command name")

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code(cls, value: Any) -> int:
        code = _parse_int(value, "command code")
        if not 0 <= code <= 0xFFFF:
            raise ValueError("command code must be between 0 and 0xFFFF")
        return code


class I2CDeviceProfile(_SchemaModel):
    """An I2C peripheral, excluding mux channel topology."""

    address_7bit: int
    name: str
    category: str
    protocol: str
    compatible: str
    register_width: int
    registers: list[RegisterDefinition] = Field(default_factory=list)
    commands: list[CommandDefinition] = Field(default_factory=list)

    _compatible_pattern: ClassVar[re.Pattern[str]] = _COMPATIBLE_RE

    @field_validator("address_7bit", mode="before")
    @classmethod
    def _validate_address(cls, value: Any) -> int:
        return _parse_address(value)

    @field_validator("register_width", mode="before")
    @classmethod
    def _validate_register_width(cls, value: Any) -> int:
        width = _parse_int(value, "register_width")
        if width not in (8, 16):
            raise ValueError("register_width must be 8 or 16 bits")
        return width

    @field_validator("name", "category", "protocol")
    @classmethod
    def _validate_text_field(cls, value: str, info: Any) -> str:
        return _non_empty_string(value, info.field_name)

    @field_validator("compatible")
    @classmethod
    def _validate_compatible(cls, value: str) -> str:
        compatible = _non_empty_string(value, "compatible")
        if not cls._compatible_pattern.fullmatch(compatible):
            raise ValueError("compatible must be an explicit 'vendor,device' string")
        return compatible

    @model_validator(mode="after")
    def _validate_definitions(self) -> Self:
        max_offset = (1 << self.register_width) - 1
        register_names: set[str] = set()
        register_offsets: set[int] = set()
        for register in self.registers:
            name_key = register.name.casefold()
            if name_key in register_names:
                raise ValueError(f"duplicate register name: {register.name}")
            if register.offset in register_offsets:
                raise ValueError(f"duplicate register offset: 0x{register.offset:X}")
            if register.offset > max_offset:
                raise ValueError(
                    f"register {register.name!r} offset 0x{register.offset:X} exceeds "
                    f"{self.register_width}-bit register address width"
                )
            register_names.add(name_key)
            register_offsets.add(register.offset)

        command_names: set[str] = set()
        command_codes: set[int] = set()
        for command in self.commands:
            name_key = command.name.casefold()
            if name_key in command_names:
                raise ValueError(f"duplicate command name: {command.name}")
            if command.code in command_codes:
                raise ValueError(f"duplicate command code: 0x{command.code:X}")
            command_names.add(name_key)
            command_codes.add(command.code)
        return self


class MuxChannel(_SchemaModel):
    """One downstream channel of an I2C mux."""

    channel: int
    downstream_bus_num: int | None = None
    devices: list[I2CDeviceProfile] = Field(default_factory=list)

    @field_validator("channel", mode="before")
    @classmethod
    def _validate_channel(cls, value: Any) -> int:
        channel = _parse_int(value, "channel")
        if not 0 <= channel <= 7:
            raise ValueError("channel must be between 0 and 7")
        return channel

    @field_validator("downstream_bus_num", mode="before")
    @classmethod
    def _validate_downstream_bus_num(cls, value: Any) -> int | None:
        if value is None:
            return None
        bus_num = _parse_int(value, "downstream_bus_num")
        if not 0 <= bus_num <= 0xFFFF:
            raise ValueError("downstream_bus_num must be between 0 and 65535")
        return bus_num

    @model_validator(mode="after")
    def _validate_device_addresses(self) -> Self:
        seen: set[int] = set()
        for device in self.devices:
            if device.address_7bit in seen:
                raise ValueError(
                    f"duplicate I2C address 0x{device.address_7bit:02X} on MUX channel {self.channel}"
                )
            seen.add(device.address_7bit)
        return self


class I2CMuxProfile(I2CDeviceProfile):
    """A mux on a parent bus and its populated downstream channels."""

    channels: list[MuxChannel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_channels(self) -> Self:
        seen: set[int] = set()
        for channel in self.channels:
            if channel.channel in seen:
                raise ValueError(f"duplicate MUX channel {channel.channel}")
            seen.add(channel.channel)
        return self


class I2CBusProfile(_SchemaModel):
    """One physical I2C controller and its direct/muxed devices."""

    bus_num: int
    speed_mode: str
    devices: list[I2CDeviceProfile] = Field(default_factory=list)
    muxes: list[I2CMuxProfile] = Field(default_factory=list)

    @field_validator("bus_num", mode="before")
    @classmethod
    def _validate_bus_num(cls, value: Any) -> int:
        bus_num = _parse_int(value, "bus_num")
        if not 0 <= bus_num <= 0xFFFF:
            raise ValueError("bus_num must be between 0 and 65535")
        return bus_num

    @field_validator("speed_mode")
    @classmethod
    def _validate_speed_mode(cls, value: str) -> str:
        speed_mode = _non_empty_string(value, "speed_mode").lower().replace(" ", "_")
        speed_mode = _SPEED_MODE_ALIASES.get(speed_mode, speed_mode)
        if speed_mode not in _SPEED_MODES:
            allowed = ", ".join(sorted(_SPEED_MODES))
            raise ValueError(f"speed_mode {speed_mode!r} is unsupported; choose one of: {allowed}")
        return speed_mode

    @model_validator(mode="after")
    def _validate_parent_addresses(self) -> Self:
        seen: set[int] = set()
        for device in self.devices:
            if device.address_7bit in seen:
                raise ValueError(
                    f"duplicate I2C address 0x{device.address_7bit:02X} on bus {self.bus_num}"
                )
            seen.add(device.address_7bit)
        for mux in self.muxes:
            if mux.address_7bit in seen:
                raise ValueError(
                    f"duplicate I2C address 0x{mux.address_7bit:02X} on bus {self.bus_num}"
                )
            seen.add(mux.address_7bit)
        return self


class BoardProfile(_SchemaModel):
    """Validated board-level I2C topology."""

    board_name: str
    version: str
    i2c_buses: list[I2CBusProfile] = Field(min_length=1)

    @field_validator("board_name", "version")
    @classmethod
    def _validate_identity(cls, value: str, info: Any) -> str:
        return _non_empty_string(value, info.field_name)

    @model_validator(mode="after")
    def _validate_bus_numbers(self) -> Self:
        seen: set[int] = set()
        for bus in self.i2c_buses:
            if bus.bus_num in seen:
                raise ValueError(f"duplicate bus_num: {bus.bus_num}")
            seen.add(bus.bus_num)
        downstream_seen: set[int] = set()
        for bus in self.i2c_buses:
            for mux in bus.muxes:
                for channel in mux.channels:
                    if channel.downstream_bus_num is not None:
                        if (
                            channel.downstream_bus_num in seen
                            or channel.downstream_bus_num in downstream_seen
                        ):
                            raise ValueError(
                                f"duplicate downstream_bus_num: {channel.downstream_bus_num}"
                            )
                        downstream_seen.add(channel.downstream_bus_num)
        return self

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Self:
        """Validate a parsed YAML/JSON mapping and normalize its values."""

        if not isinstance(value, Mapping):
            raise SchemaError("board profile root must be a mapping/object")
        try:
            return cls.model_validate(value)
        except ValidationError as exc:
            raise _schema_error_from_validation(exc) from exc

    @classmethod
    def from_text(cls, text: str, *, format: Literal["yaml", "yml", "json"] | None = None) -> Self:
        """Parse and validate YAML or JSON text."""

        if not isinstance(text, str):
            raise SchemaError("board profile content must be text")
        selected_format = (
            _normalize_format(format) if format is not None else _detect_text_format(text)
        )
        try:
            data = (
                json.loads(text, object_pairs_hook=_reject_duplicate_json_pairs)
                if selected_format == "json"
                else yaml.load(text, Loader=_UniqueKeyLoader)
            )
        except _DuplicateKeyError as exc:
            raise SchemaError(f"JSON duplicate key: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SchemaError(
                f"JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        except yaml.YAMLError as exc:
            raise SchemaError(f"YAML syntax error: {exc}") from exc
        return cls.from_mapping(data)

    @classmethod
    def from_yaml(cls, source: str | Path) -> Self:
        return cls.from_text(_read_source_text(source), format="yaml")

    @classmethod
    def from_json(cls, source: str | Path) -> Self:
        return cls.from_text(_read_source_text(source), format="json")

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        file_path = Path(path)
        if file_path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            raise SchemaError("board profile file extension must be .yaml, .yml, or .json")
        return cls.from_text(
            _read_source_text(file_path),
            format="json" if file_path.suffix.lower() == ".json" else "yaml",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-compatible normalized mapping."""

        return self.model_dump(mode="python")

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


def _normalize_format(format: str) -> Literal["yaml", "json"]:
    if not isinstance(format, str):
        raise SchemaError("profile format must be yaml or json")
    normalized = format.lower().lstrip(".")
    if normalized == "yml":
        normalized = "yaml"
    if normalized not in {"yaml", "json"}:
        raise SchemaError("profile format must be yaml or json")
    return normalized  # type: ignore[return-value]


def _detect_text_format(text: str) -> Literal["yaml", "json"]:
    first = text.lstrip()[:1]
    return "json" if first in {"{", "["} else "yaml"


def _read_source_text(source: str | Path) -> str:
    if isinstance(source, Path):
        try:
            return source.read_text(encoding="utf-8")
        except OSError as exc:
            raise SchemaError(f"unable to read board profile {source}: {exc}") from exc
    if not isinstance(source, str):
        raise SchemaError("board profile source must be text or a filesystem path")
    candidate = Path(source)
    try:
        is_file = "\n" not in source and "\r" not in source and candidate.is_file()
    except OSError:
        is_file = False
    if is_file:
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            raise SchemaError(f"unable to read board profile {candidate}: {exc}") from exc
    return source


def _schema_error_from_validation(exc: ValidationError) -> SchemaError:
    errors = exc.errors(include_url=False)
    details: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        details.append(f"{location}: {error['msg']}")
    message = "board profile schema validation failed: " + "; ".join(details)
    return SchemaError(message, errors=errors)


def load_board_profile(
    source: Mapping[str, Any] | str | Path, *, format: str | None = None
) -> BoardProfile:
    """Load a Board Profile mapping, text document, or YAML/JSON file."""

    if isinstance(source, Mapping):
        return BoardProfile.from_mapping(source)
    if isinstance(source, Path):
        if format is None:
            return BoardProfile.from_file(source)
        return BoardProfile.from_text(_read_source_text(source), format=_normalize_format(format))
    if not isinstance(source, str):
        raise SchemaError("board profile source must be a mapping, text, or filesystem path")
    if format is not None:
        return BoardProfile.from_text(_read_source_text(source), format=_normalize_format(format))
    candidate = Path(source)
    try:
        is_file = "\n" not in source and "\r" not in source and candidate.is_file()
    except OSError:
        is_file = False
    if is_file:
        return BoardProfile.from_file(candidate)
    return BoardProfile.from_text(source)


# Short aliases make the schema pleasant to use without hiding the explicit
# I2C names in the model definitions above.
DeviceProfile = I2CDeviceProfile
MuxProfile = I2CMuxProfile
BusProfile = I2CBusProfile


__all__ = [
    "BoardProfile",
    "BoardProfileError",
    "BoardProfileSchemaError",
    "BusProfile",
    "CommandDefinition",
    "DeviceProfile",
    "I2CBusProfile",
    "I2CDeviceProfile",
    "I2CMuxProfile",
    "MuxChannel",
    "MuxProfile",
    "RegisterDefinition",
    "SchemaError",
    "load_board_profile",
]
