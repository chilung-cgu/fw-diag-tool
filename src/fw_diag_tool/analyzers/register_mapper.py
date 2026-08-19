from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class BitField:
    name: str
    bit_range: str  # e.g. "31:24", "15", "0"
    description: str = ""
    access: str = "RW"  # RO, RW, WO, W1C, RsvdP, etc.
    values: dict[int, str] = field(default_factory=dict)
    warning_values: list[int] = field(default_factory=list)

    @property
    def high_bit(self) -> int:
        if ":" in self.bit_range:
            return int(self.bit_range.split(":")[0])
        return int(self.bit_range)

    @property
    def low_bit(self) -> int:
        if ":" in self.bit_range:
            return int(self.bit_range.split(":")[1])
        return int(self.bit_range)

    @property
    def bit_mask(self) -> int:
        length = self.high_bit - self.low_bit + 1
        return ((1 << length) - 1) << self.low_bit

    def extract_value(self, reg_val: int) -> int:
        return (reg_val & self.bit_mask) >> self.low_bit


@dataclass
class RegisterDef:
    name: str
    offset: int
    size: int = 32  # 8, 16, 32
    reset_val: int = 0
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
        regs = data.get("registers", [])
        for r in regs:
            offset = r.get("offset")
            if isinstance(offset, str):
                offset = int(offset, 0)
            
            fields = []
            for f in r.get("fields", []):
                val_map = {}
                for k, v in f.get("values", {}).items():
                    val_map[int(str(k), 0)] = str(v)
                
                warns = [int(str(w), 0) for w in f.get("warning_values", [])]
                
                fields.append(BitField(
                    name=f["name"],
                    bit_range=str(f["bits"]),
                    description=f.get("description", ""),
                    access=f.get("access", "RW"),
                    values=val_map,
                    warning_values=warns
                ))
            
            reg_def = RegisterDef(
                name=r["name"],
                offset=offset,
                size=r.get("size", 32),
                reset_val=int(str(r.get("reset", 0)), 0) if r.get("reset") is not None else 0,
                description=r.get("description", ""),
                fields=fields
            )
            self.registers[offset] = reg_def
            self.name_map[reg_def.name.lower()] = reg_def

    def decode_register(self, offset_or_name: Any, value: int) -> DecodedRegisterResult:
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
            offset = offset_or_name if isinstance(offset_or_name, int) else (int(offset_or_name, 0) if str(offset_or_name).startswith("0x") else 0)
            return DecodedRegisterResult(
                reg_name=str(offset_or_name),
                offset=offset,
                raw_val=value,
                hex_val=f"0x{value:08X}",
                description="Unknown / Custom Register",
                fields=[],
                unmapped_bits=value
            )

        decoded_fields = []
        covered_mask = 0
        for f in reg_def.fields:
            f_val = f.extract_value(value)
            covered_mask |= f.bit_mask
            meaning = f.values.get(f_val, f"Raw value: {f_val}")
            is_warning = f_val in f.warning_values
            warning_msg = f"Warning: Field '{f.name}' has abnormal value {f_val}" if is_warning else ""
            
            decoded_fields.append(DecodedFieldResult(
                name=f.name,
                bit_range=f.bit_range,
                raw_val=f_val,
                hex_val=f"0x{f_val:X}",
                meaning=meaning,
                access=f.access,
                is_warning=is_warning,
                warning_msg=warning_msg
            ))

        unmapped = value & (~covered_mask)
        return DecodedRegisterResult(
            reg_name=reg_def.name,
            offset=reg_def.offset,
            raw_val=value,
            hex_val=f"0x{value:08X}",
            description=reg_def.description,
            fields=decoded_fields,
            unmapped_bits=unmapped
        )
