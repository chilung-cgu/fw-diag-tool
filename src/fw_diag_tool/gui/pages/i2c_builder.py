from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fw_diag_tool import __version__
from fw_diag_tool.i2c.transfer_spec import I2CTransferOperation

MAX_BUILDER_DATA_BYTES = 4096
MAX_BUILDER_WAVEFORM_POINTS = 100_000


def max_write_data_bytes(*, register_operation: bool, register_width: int) -> int:
    """Return the GUI data limit that fits the canonical waveform budget."""

    register_bytes = 0
    if register_operation:
        register_bytes = 1 if register_width == 8 else 2
    # I2CTransferSpec.estimated_waveform_points uses 10 + 27 *
    # (1 + register_bytes + data_bytes) for a one-segment write.
    max_segment_bytes = (MAX_BUILDER_WAVEFORM_POINTS - 10) // 27
    waveform_limit = max_segment_bytes - 1 - register_bytes
    return max(1, min(MAX_BUILDER_DATA_BYTES, waveform_limit))


@dataclass(frozen=True)
class I2CBuilderPreset:
    operation: I2CTransferOperation
    address: str
    register: str
    register_width: int
    endianness: str
    write_data: str
    read_length: int
    expected_read_data: str = ""
    bus: int = 1
    clock_khz: float = 100.0
    timeout_ms: float = 25.0


I2C_BUILDER_PRESETS: dict[str, I2CBuilderPreset] = {
    "EEPROM：8-bit register write": I2CBuilderPreset(
        operation=I2CTransferOperation.REGISTER_WRITE,
        address="0x50",
        register="0x10",
        register_width=8,
        endianness="big",
        write_data="0xAA 0xBB",
        read_length=2,
    ),
    "Temperature sensor：combined register read": I2CBuilderPreset(
        operation=I2CTransferOperation.COMBINED_REGISTER_READ,
        address="0x48",
        register="0x00",
        register_width=8,
        endianness="big",
        write_data="",
        read_length=2,
    ),
    "Sensor：direct read": I2CBuilderPreset(
        operation=I2CTransferOperation.DIRECT_READ,
        address="0x40",
        register="",
        register_width=8,
        endianness="big",
        write_data="",
        read_length=2,
    ),
    "Device：direct write": I2CBuilderPreset(
        operation=I2CTransferOperation.DIRECT_WRITE,
        address="0x40",
        register="",
        register_width=8,
        endianness="big",
        write_data="0x01 0x02",
        read_length=2,
    ),
    "EEPROM：16-bit little-endian register write": I2CBuilderPreset(
        operation=I2CTransferOperation.REGISTER_WRITE,
        address="0x50",
        register="0x1234",
        register_width=16,
        endianness="little",
        write_data="0xAA",
        read_length=2,
    ),
}


def parse_hex_integer(value: str, *, label: str) -> int:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    token = value.strip()
    if not token:
        raise ValueError(f"{label} is required")
    try:
        return int(token, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer such as 0x50") from exc


def parse_hex_bytes(
    value: str,
    *,
    label: str,
    required: bool = False,
    max_bytes: int = MAX_BUILDER_DATA_BYTES,
) -> tuple[int, ...]:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    tokens = [token for token in re.split(r"[\s,]+", value.strip()) if token]
    if required and not tokens:
        raise ValueError(f"{label} requires at least one byte")
    if len(tokens) > max_bytes:
        raise ValueError(f"{label} has {len(tokens)} bytes; limit is {max_bytes}")
    parsed: list[int] = []
    for index, token in enumerate(tokens):
        try:
            byte = int(token, 16)
        except ValueError as exc:
            raise ValueError(f"{label} byte #{index + 1} is not an integer: {token!r}") from exc
        if not 0 <= byte <= 0xFF:
            raise ValueError(f"{label} byte #{index + 1} must be between 0x00 and 0xFF")
        parsed.append(byte)
    return tuple(parsed)


def preset_widget_state(preset: I2CBuilderPreset) -> dict[str, Any]:
    return {
        "i2c_builder_operation": preset.operation.value,
        "i2c_builder_address": preset.address,
        "i2c_builder_register": preset.register,
        "i2c_builder_register_width": preset.register_width,
        "i2c_builder_endianness": preset.endianness,
        "i2c_builder_write_data": preset.write_data,
        "i2c_builder_read_length": preset.read_length,
        "i2c_builder_expected_read_data": preset.expected_read_data,
        "i2c_builder_bus": preset.bus,
        "i2c_builder_clock_khz": preset.clock_khz,
        "i2c_builder_timeout_ms": preset.timeout_ms,
    }


def build_i2c_bundle(
    spec: Any,
    snippets: Mapping[str, str],
) -> tuple[bytes, str, str]:
    """Return a deterministic ZIP, bundle SHA-256, and canonical spec SHA-256."""

    if not hasattr(spec, "to_dict"):
        raise TypeError("spec must provide to_dict()")
    if not isinstance(snippets, Mapping) or not snippets:
        raise ValueError("snippets must be a non-empty mapping")
    spec_json = json.dumps(
        spec.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"
    spec_sha256 = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
    files: dict[str, str] = {
        "transfer_spec.json": spec_json,
        "SAFETY.txt": (
            "Generated templates are not proof that a target device accepts this transfer.\n"
            "Before hardware access, verify the adapter/bus, 7-bit address, register map,\n"
            "device power state, kernel-driver ownership, timeout, and write side effects.\n"
            "The GUI does not execute these commands.\n"
        ),
    }
    used_names: set[str] = set()
    for platform, source in sorted(snippets.items()):
        if not isinstance(platform, str) or not isinstance(source, str):
            raise TypeError("snippet names and source must be strings")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", platform).strip("._") or "snippet"
        if "CLI" in platform:
            suffix = ".sh"
        elif "Arduino" in platform:
            # Wire.h snippets are C++, not C; preserving the language in the
            # bundle filename prevents an editor/build system from selecting
            # the wrong parser or compiler by default.
            suffix = ".cpp"
        else:
            suffix = ".c"
        filename = f"{stem}{suffix}"
        counter = 2
        while filename in used_names:
            filename = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(filename)
        files[f"snippets/{filename}"] = source.rstrip() + "\n"
    manifest = {
        "tool_version": __version__,
        "spec_sha256": spec_sha256,
        "files": {
            path: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for path, content in sorted(files.items())
        },
    }
    files["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    bundle = output.getvalue()
    return bundle, hashlib.sha256(bundle).hexdigest(), spec_sha256


__all__ = [
    "I2C_BUILDER_PRESETS",
    "MAX_BUILDER_DATA_BYTES",
    "MAX_BUILDER_WAVEFORM_POINTS",
    "I2CBuilderPreset",
    "build_i2c_bundle",
    "max_write_data_bytes",
    "parse_hex_bytes",
    "parse_hex_integer",
    "preset_widget_state",
]
