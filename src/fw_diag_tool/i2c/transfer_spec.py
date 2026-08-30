"""Canonical, validated I2C transfer descriptions.

The packet builder and code generators consume this model instead of each
re-interpreting UI fields independently.  A read byte is intentionally kept
as an ``UnknownByte`` marker: a transfer description knows how many bytes the
controller should receive, but it cannot know their values before a device or
capture supplies them.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fw_diag_tool.errors import ResourceLimitError

MIN_I2C_ADDRESS = 0x08
MAX_I2C_ADDRESS = 0x77
MAX_BUS_NUMBER = 0xFFFF
MAX_READ_LENGTH = 0xFF
DEFAULT_CLOCK_KHZ = 100.0
DEFAULT_TIMEOUT_MS = 25.0
DEFAULT_MAX_PAYLOAD_BYTES = 4096
DEFAULT_MAX_WAVEFORM_POINTS = 100_000


class I2CTransferOperation(str, Enum):
    """Logical transfer shapes supported by the packet builder."""

    REGISTER_WRITE = "register_write"
    COMBINED_REGISTER_READ = "combined_register_read"
    DIRECT_WRITE = "direct_write"
    DIRECT_READ = "direct_read"

    @classmethod
    def coerce(cls, value: I2CTransferOperation | str) -> I2CTransferOperation:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("operation must be an I2CTransferOperation or string")
        token = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "register_write": cls.REGISTER_WRITE,
            "write_register": cls.REGISTER_WRITE,
            "reg_write": cls.REGISTER_WRITE,
            "write": cls.REGISTER_WRITE,
            "combined_register_read": cls.COMBINED_REGISTER_READ,
            "register_read": cls.COMBINED_REGISTER_READ,
            "read_register": cls.COMBINED_REGISTER_READ,
            "combined_read": cls.COMBINED_REGISTER_READ,
            "read": cls.COMBINED_REGISTER_READ,
            "direct_write": cls.DIRECT_WRITE,
            "raw_write": cls.DIRECT_WRITE,
            "direct_read": cls.DIRECT_READ,
            "raw_read": cls.DIRECT_READ,
        }
        try:
            return aliases[token]
        except KeyError as exc:
            allowed = ", ".join(operation.value for operation in cls)
            raise ValueError(f"operation must be one of: {allowed}") from exc


class Endianness(str, Enum):
    """Register-byte order.  Payload data bytes are never reordered."""

    BIG = "big"
    LITTLE = "little"

    @classmethod
    def coerce(cls, value: Endianness | str) -> Endianness:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("endianness must be Endianness.BIG or Endianness.LITTLE")
        token = value.strip().lower().replace("-", "_")
        if token in {"big", "be", "msb", "msb_first"}:
            return cls.BIG
        if token in {"little", "le", "lsb", "lsb_first"}:
            return cls.LITTLE
        raise ValueError("endianness must be 'big' or 'little'")


class UnknownByte(str, Enum):
    """A read-byte placeholder whose value is not known from the spec."""

    PLACEHOLDER = "Unknown"


UNKNOWN_BYTE = UnknownByte.PLACEHOLDER
CanonicalByte = int | UnknownByte


class TransferDirection(str, Enum):
    """Direction of an individual bus segment."""

    WRITE = "write"
    READ = "read"


@dataclass(frozen=True)
class I2CTransferSegment:
    """One address phase and its payload in the canonical transfer."""

    direction: TransferDirection
    bytes: tuple[CanonicalByte, ...]
    repeated_start: bool = False
    final_controller_nack: bool = False

    @property
    def data_bytes(self) -> tuple[CanonicalByte, ...]:
        return self.bytes

    @property
    def canonical_bytes(self) -> tuple[CanonicalByte, ...]:
        return self.bytes

    @property
    def is_read(self) -> bool:
        return self.direction == TransferDirection.READ

    @property
    def is_write(self) -> bool:
        return self.direction == TransferDirection.WRITE


def _coerce_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _coerce_bytes(name: str, values: Iterable[int] | None) -> tuple[int, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an iterable of byte values")
    try:
        values_tuple = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable of byte values") from exc
    result: list[int] = []
    for index, value in enumerate(values_tuple):
        result.append(_coerce_int(f"{name}[{index}]", value, 0, 0xFF))
    return tuple(result)


@dataclass(frozen=True, init=False)
class I2CTransferSpec:
    """Validated canonical representation of one I2C operation.

    ``address_7bit`` and ``bus`` are canonical names.  Common legacy names
    (``addr_7bit``, ``bus_num``, and ``reg_offset``) are accepted as keyword
    aliases so callers can migrate without constructing a second model.
    """

    address_7bit: int
    bus: int
    operation: I2CTransferOperation
    register: int | None
    register_width: int
    endianness: Endianness
    data_bytes: tuple[int, ...]
    read_length: int | None
    expected_read_data: tuple[int, ...]
    clock_khz: float
    timeout_ms: float
    max_payload_bytes: int
    max_waveform_points: int

    def __init__(
        self,
        address_7bit: int | None = None,
        operation: I2CTransferOperation | str = I2CTransferOperation.REGISTER_WRITE,
        register: int | None = None,
        register_width: int = 8,
        endianness: Endianness | str = Endianness.BIG,
        data_bytes: Iterable[int] | None = None,
        read_length: int | None = None,
        expected_read_data: Iterable[int] | None = None,
        bus: int = 1,
        clock_khz: float = DEFAULT_CLOCK_KHZ,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_waveform_points: int = DEFAULT_MAX_WAVEFORM_POINTS,
        *,
        address: int | None = None,
        addr_7bit: int | None = None,
        bus_num: int | None = None,
        reg_offset: int | None = None,
        register_offset: int | None = None,
        register_value: int | None = None,
        expected_read_bytes: Iterable[int] | None = None,
        clock: float | None = None,
        clock_frequency_khz: float | None = None,
        timeout: float | None = None,
        payload_limit: int | None = None,
        waveform_point_limit: int | None = None,
    ) -> None:
        resolved_address = _resolve_alias(
            "address_7bit", address_7bit, ("address", address), ("addr_7bit", addr_7bit)
        )
        resolved_bus = _resolve_alias("bus", bus, ("bus_num", bus_num))
        resolved_register = _resolve_alias(
            "register",
            register,
            ("reg_offset", reg_offset),
            ("register_offset", register_offset),
            ("register_value", register_value),
            allow_none=True,
        )
        resolved_clock = _resolve_alias(
            "clock_khz", clock_khz, ("clock", clock), ("clock_frequency_khz", clock_frequency_khz)
        )
        resolved_timeout = _resolve_alias("timeout_ms", timeout_ms, ("timeout", timeout))
        resolved_payload_limit = _resolve_alias(
            "max_payload_bytes", max_payload_bytes, ("payload_limit", payload_limit)
        )
        resolved_waveform_limit = _resolve_alias(
            "max_waveform_points",
            max_waveform_points,
            ("waveform_point_limit", waveform_point_limit),
        )

        object.__setattr__(
            self,
            "address_7bit",
            _coerce_int("address_7bit", resolved_address, MIN_I2C_ADDRESS, MAX_I2C_ADDRESS),
        )
        object.__setattr__(self, "bus", _coerce_int("bus", resolved_bus, 0, MAX_BUS_NUMBER))
        object.__setattr__(self, "operation", I2CTransferOperation.coerce(operation))
        object.__setattr__(
            self, "register_width", _coerce_int("register_width", register_width, 8, 16)
        )
        if register_width not in (8, 16):
            raise ValueError("register_width must be 8 or 16 bits")
        object.__setattr__(self, "endianness", Endianness.coerce(endianness))
        object.__setattr__(self, "register", resolved_register)
        object.__setattr__(self, "data_bytes", _coerce_bytes("data_bytes", data_bytes))
        object.__setattr__(self, "read_length", read_length)
        expected_data = expected_read_data
        if expected_read_bytes is not None:
            expected_tuple = tuple(expected_data) if expected_data is not None else None
            expected_alias_tuple = tuple(expected_read_bytes)
            if expected_tuple is not None and expected_tuple != expected_alias_tuple:
                raise ValueError("expected_read_data conflicts with expected_read_bytes")
            expected_data = expected_alias_tuple if expected_tuple is None else expected_tuple
        object.__setattr__(
            self, "expected_read_data", _coerce_bytes("expected_read_data", expected_data)
        )
        object.__setattr__(
            self, "clock_khz", _coerce_real("clock_khz", resolved_clock, 1.0, 1000.0)
        )
        object.__setattr__(
            self, "timeout_ms", _coerce_real("timeout_ms", resolved_timeout, 0.001, 60_000.0)
        )
        object.__setattr__(
            self,
            "max_payload_bytes",
            _coerce_int("max_payload_bytes", resolved_payload_limit, 1, 1_000_000),
        )
        object.__setattr__(
            self,
            "max_waveform_points",
            _coerce_int("max_waveform_points", resolved_waveform_limit, 1, 10_000_000),
        )
        self.validate()

    @property
    def bus_num(self) -> int:
        return self.bus

    @property
    def addr_7bit(self) -> int:
        return self.address_7bit

    @property
    def reg_offset(self) -> int | None:
        return self.register

    @property
    def reg_width(self) -> int:
        return self.register_width

    @property
    def endian(self) -> Endianness:
        return self.endianness

    @property
    def register_bytes(self) -> tuple[int, ...]:
        if self.register is None:
            return ()
        if self.register_width == 8:
            return (self.register,)
        high = (self.register >> 8) & 0xFF
        low = self.register & 0xFF
        return (high, low) if self.endianness == Endianness.BIG else (low, high)

    @property
    def payload_bytes(self) -> int:
        return sum(len(segment.bytes) for segment in self.segments)

    @property
    def payload_length(self) -> int:
        return self.payload_bytes

    @property
    def read_placeholder_bytes(self) -> tuple[UnknownByte, ...]:
        return tuple(UNKNOWN_BYTE for _ in range(self.read_length or 0))

    @property
    def expected_read_bytes(self) -> tuple[int, ...]:
        return self.expected_read_data

    @property
    def segments(self) -> tuple[I2CTransferSegment, ...]:
        operation = self.operation
        if operation == I2CTransferOperation.REGISTER_WRITE:
            return (
                I2CTransferSegment(TransferDirection.WRITE, self.register_bytes + self.data_bytes),
            )
        if operation == I2CTransferOperation.COMBINED_REGISTER_READ:
            return (
                I2CTransferSegment(TransferDirection.WRITE, self.register_bytes),
                I2CTransferSegment(
                    TransferDirection.READ,
                    self.read_placeholder_bytes,
                    repeated_start=True,
                    final_controller_nack=True,
                ),
            )
        if operation == I2CTransferOperation.DIRECT_WRITE:
            return (I2CTransferSegment(TransferDirection.WRITE, self.data_bytes),)
        return (
            I2CTransferSegment(
                TransferDirection.READ,
                self.read_placeholder_bytes,
                final_controller_nack=True,
            ),
        )

    @property
    def canonical_bytes(self) -> tuple[CanonicalByte, ...]:
        """Flatten payload bytes, retaining ``Unknown`` for reads."""

        return tuple(byte for segment in self.segments for byte in segment.bytes)

    @property
    def canonical_byte_values(self) -> tuple[int | None, ...]:
        """Numeric view where unknown read bytes are represented by ``None``."""

        return tuple(
            None if isinstance(byte, UnknownByte) else byte for byte in self.canonical_bytes
        )

    @property
    def estimated_waveform_points(self) -> int:
        """Upper-bound digital samples rendered by the canonical waveform."""

        # Two initial idle points, up to four points for every START/Sr, 27
        # points per address/payload byte (8 data clocks + ACK clock), and four
        # STOP points.  This intentionally errs high if a renderer adds a
        # boundary.
        byte_count = sum(1 + len(segment.bytes) for segment in self.segments)
        return 2 + (4 * len(self.segments)) + (27 * byte_count) + 4

    @property
    def waveform_point_count(self) -> int:
        return self.estimated_waveform_points

    def validate(self) -> None:
        """Validate operation-specific invariants before any rendering."""

        if self.register is not None:
            _coerce_int("register", self.register, 0, (1 << self.register_width) - 1)
        if self.read_length is not None:
            _coerce_int("read_length", self.read_length, 1, MAX_READ_LENGTH)

        register_operation = self.operation in {
            I2CTransferOperation.REGISTER_WRITE,
            I2CTransferOperation.COMBINED_REGISTER_READ,
        }
        read_operation = self.operation in {
            I2CTransferOperation.COMBINED_REGISTER_READ,
            I2CTransferOperation.DIRECT_READ,
        }
        if register_operation and self.register is None:
            raise ValueError(f"{self.operation.value} requires a register")
        if not register_operation and self.register is not None:
            raise ValueError(f"{self.operation.value} does not accept a register")
        if read_operation:
            if self.read_length is None:
                raise ValueError(f"{self.operation.value} requires read_length")
            if self.data_bytes:
                raise ValueError(f"{self.operation.value} does not accept data_bytes")
            if self.expected_read_data and len(self.expected_read_data) != self.read_length:
                raise ValueError("expected_read_data length must equal read_length")
        elif self.expected_read_data:
            raise ValueError("expected_read_data is only valid for read operations")
        elif self.read_length is not None:
            raise ValueError("read_length is only valid for read operations")
        if not read_operation and not self.data_bytes:
            raise ValueError(f"{self.operation.value} requires at least one data byte")

        if self.payload_bytes > self.max_payload_bytes:
            raise ResourceLimitError(
                f"I2C transfer payload has {self.payload_bytes} bytes; limit is {self.max_payload_bytes}",
                resource="i2c_transfer_payload",
                limit=self.max_payload_bytes,
                observed=self.payload_bytes,
            )
        estimated = self.estimated_waveform_points
        if estimated > self.max_waveform_points:
            raise ResourceLimitError(
                f"I2C waveform requires {estimated} points; limit is {self.max_waveform_points}",
                resource="i2c_waveform_points",
                limit=self.max_waveform_points,
                observed=estimated,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address_7bit": self.address_7bit,
            "bus": self.bus,
            "operation": self.operation.value,
            "register": self.register,
            "register_width": self.register_width,
            "endianness": self.endianness.value,
            "data_bytes": list(self.data_bytes),
            "read_length": self.read_length,
            "expected_read_data": list(self.expected_read_data),
            "clock_khz": self.clock_khz,
            "timeout_ms": self.timeout_ms,
            "max_payload_bytes": self.max_payload_bytes,
            "max_waveform_points": self.max_waveform_points,
            "canonical_bytes": [
                byte.value if isinstance(byte, UnknownByte) else byte
                for byte in self.canonical_bytes
            ],
        }


def _resolve_alias(
    name: str, primary: Any, *aliases: tuple[str, Any], allow_none: bool = False
) -> Any:
    resolved = primary
    for alias_name, alias_value in aliases:
        if alias_value is None:
            continue
        if resolved is not None and resolved != alias_value:
            # Defaults are intentionally treated as unset when an alias is
            # supplied; explicit conflicting values remain an error.
            defaults = {
                "bus": 1,
                "clock_khz": DEFAULT_CLOCK_KHZ,
                "timeout_ms": DEFAULT_TIMEOUT_MS,
                "max_payload_bytes": DEFAULT_MAX_PAYLOAD_BYTES,
                "max_waveform_points": DEFAULT_MAX_WAVEFORM_POINTS,
            }
            if name in defaults and resolved == defaults[name]:
                resolved = alias_value
            else:
                raise ValueError(f"{name} conflicts with {alias_name}")
        else:
            resolved = alias_value
    if resolved is None and not allow_none:
        raise TypeError(f"{name} is required")
    return resolved


def _coerce_real(name: str, value: Any, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


# Short names are useful to callers while the explicit names remain discoverable.
TransferOperation = I2CTransferOperation
Operation = I2CTransferOperation
I2CEndianness = Endianness
I2COperation = I2CTransferOperation


__all__ = [
    "DEFAULT_CLOCK_KHZ",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "DEFAULT_MAX_WAVEFORM_POINTS",
    "DEFAULT_TIMEOUT_MS",
    "MAX_I2C_ADDRESS",
    "MAX_READ_LENGTH",
    "MIN_I2C_ADDRESS",
    "UNKNOWN_BYTE",
    "CanonicalByte",
    "Endianness",
    "I2CEndianness",
    "I2COperation",
    "I2CTransferOperation",
    "I2CTransferSegment",
    "I2CTransferSpec",
    "Operation",
    "TransferDirection",
    "TransferOperation",
    "UnknownByte",
]
