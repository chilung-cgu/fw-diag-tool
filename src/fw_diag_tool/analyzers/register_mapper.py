import re
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class BitField:
    name: str
    bit_range: str
    description: str = ""
    access: str = "RW"
    values: dict[int, str] = field(default_factory=dict)
    warning_values: list[int] = field(default_factory=list)

    def _parse_bits(self) -> tuple[int, int]:
        cleaned = re.sub(r"[\[\]\s]", "", str(self.bit_range))
        if not re.fullmatch(r"\d+(?::\d+)?", cleaned):
            raise ValueError(f"invalid bit range: {self.bit_range!r}")
        if ":" in cleaned:
            parts = [int(p) for p in cleaned.split(":")]
            return max(parts), min(parts)
        val = int(cleaned)
        return val, val

    @property
    def high_bit(self) -> int:
        return self._parse_bits()[0]

    @property
    def low_bit(self) -> int:
        return self._parse_bits()[1]

    @property
    def bit_mask(self) -> int:
        high, low = self._parse_bits()
        length = max(1, high - low + 1)
        return ((1 << length) - 1) << low

    def extract_value(self, reg_val: int) -> int:
        return (reg_val & self.bit_mask) >> self.low_bit


@dataclass
class RegisterDef:
    name: str
    offset: int
    size: int = 32
    reset_val: int | None = None
    description: str = ""
    fields: list[BitField] = field(default_factory=list)


@dataclass
class DecodedFieldResult:
    name: str
    bit_range: str
    raw_val: int
    hex_val: str
    meaning: str
    access: str
    is_warning: bool = False
    warning_msg: str = ""


@dataclass
class DecodedRegisterResult:
    reg_name: str
    offset: int
    raw_val: int
    hex_val: str
    description: str
    fields: list[DecodedFieldResult] = field(default_factory=list)
    unmapped_bits: int = 0


class RegisterMapCatalog:
    def __init__(self):
        self.registers: dict[int, RegisterDef] = {}
        self.name_map: dict[str, RegisterDef] = {}

    def load_from_yaml(self, yaml_content: str):
        data = yaml.safe_load(yaml_content)
        if not data:
            return
        if not isinstance(data, dict):
            raise TypeError("register map root must be a mapping")
        regs = data.get("registers", [])
        if not isinstance(regs, list):
            raise TypeError("registers must be a list")
        for r in regs:
            if not isinstance(r, dict):
                raise TypeError("each register must be a mapping")
            offset = r.get("offset")
            if isinstance(offset, str):
                offset = int(offset, 0)
            fields = []
            raw_fields = r.get("fields", [])
            if not isinstance(raw_fields, list):
                raise TypeError(f"register {r.get('name', '<unnamed>')} fields must be a list")
            for f in raw_fields:
                if not isinstance(f, dict):
                    raise TypeError("each register field must be a mapping")
                val_map = {}
                raw_values = f.get("values", {})
                if not isinstance(raw_values, dict):
                    raise TypeError(f"field {f.get('name', '<unnamed>')} values must be a mapping")
                for k, v in raw_values.items():
                    val_map[int(str(k), 0)] = str(v)
                raw_warnings = f.get("warning_values", [])
                if not isinstance(raw_warnings, list):
                    raise TypeError(
                        f"field {f.get('name', '<unnamed>')} warning_values must be a list"
                    )
                warns = [int(str(w), 0) for w in raw_warnings]
                fields.append(
                    BitField(
                        name=f["name"],
                        bit_range=str(f["bits"]),
                        description=f.get("description", ""),
                        access=f.get("access", "RW"),
                        values=val_map,
                        warning_values=warns,
                    )
                )
            raw_size = r.get("size", 32)
            raw_reset = r.get("reset")
            reg_def = RegisterDef(
                name=r["name"],
                offset=offset,
                size=int(str(raw_size), 0),
                reset_val=int(str(raw_reset), 0) if raw_reset is not None else None,
                description=r.get("description", ""),
                fields=fields,
            )
            if offset in self.registers:
                raise ValueError(f"duplicate register offset: 0x{offset:X}")
            name_key = reg_def.name.lower()
            if name_key in self.name_map:
                raise ValueError(f"duplicate register name: {reg_def.name}")
            self.registers[offset] = reg_def
            self.name_map[name_key] = reg_def

    def decode_register(self, offset_or_name: Any, value: int) -> DecodedRegisterResult:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("register value must be an integer")
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError("register value must be between 0 and 0xFFFFFFFF")
        reg_def = None
        if isinstance(offset_or_name, int):
            reg_def = self.registers.get(offset_or_name)
        elif isinstance(offset_or_name, str):
            if offset_or_name.startswith("0x") or offset_or_name.isdigit():
                offset = int(offset_or_name, 0)
                reg_def = self.registers.get(offset)
            else:
                reg_def = self.name_map.get(offset_or_name.lower())
        if not reg_def:
            offset = (
                offset_or_name
                if isinstance(offset_or_name, int)
                else (int(offset_or_name, 0) if str(offset_or_name).startswith("0x") else 0)
            )
            return DecodedRegisterResult(
                reg_name=str(offset_or_name),
                offset=offset,
                raw_val=value,
                hex_val=f"0x{value:08X}",
                description="Unknown / Custom Register",
                fields=[],
                unmapped_bits=value,
            )
        if value >= (1 << reg_def.size):
            raise ValueError(
                f"value 0x{value:X} exceeds {reg_def.size}-bit register {reg_def.name}"
            )
        decoded_fields = []
        covered_mask = 0
        for f in reg_def.fields:
            f_val = f.extract_value(value)
            covered_mask |= f.bit_mask
            meaning = f.values.get(f_val, f"Raw value: {f_val}")
            is_warning = f_val in f.warning_values
            warning_msg = (
                f"Warning: Field '{f.name}' has abnormal value {f_val}" if is_warning else ""
            )
            decoded_fields.append(
                DecodedFieldResult(
                    name=f.name,
                    bit_range=f.bit_range,
                    raw_val=f_val,
                    hex_val=f"0x{f_val:X}",
                    meaning=meaning,
                    access=f.access,
                    is_warning=is_warning,
                    warning_msg=warning_msg,
                )
            )
        unmapped = value & (~covered_mask)
        return DecodedRegisterResult(
            reg_name=reg_def.name,
            offset=reg_def.offset,
            raw_val=value,
            hex_val=f"0x{value:08X}",
            description=reg_def.description,
            fields=decoded_fields,
            unmapped_bits=unmapped,
        )
