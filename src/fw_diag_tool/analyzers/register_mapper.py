import re
from dataclasses import dataclass, field
from typing import Any

import yaml

# Keep the schema deliberately small until each access mode has an explicit
# code-generation contract.  Treating an unknown token as RW is unsafe: a
# typo can generate a read-modify-write sequence for a side-effect register.
VALID_FIELD_ACCESS = frozenset({"RO", "RW", "W1C"})


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
            if max(parts) > 63:
                raise ValueError(f"bit position {max(parts)} exceeds supported 64-bit width")
            return max(parts), min(parts)
        val = int(cleaned)
        if val > 63:
            raise ValueError(f"bit position {val} exceeds supported 64-bit width")
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
    offset: int | None
    raw_val: int
    hex_val: str
    description: str
    fields: list[DecodedFieldResult] = field(default_factory=list)
    unmapped_bits: int = 0


class RegisterMapCatalog:
    def __init__(self):
        self.registers: dict[int, RegisterDef] = {}
        self.name_map: dict[str, RegisterDef] = {}

    @staticmethod
    def _parse_int(value: Any, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError(f"{label} must be an integer")
        if isinstance(value, int):
            return value
        token = value.strip()
        try:
            return int(token, 0)
        except ValueError:
            # YAML/CLI users often write zero-padded decimal offsets such as
            # "010"; base-10 is unambiguous after the base-0 attempt fails.
            if token.isdigit():
                return int(token, 10)
            raise ValueError(f"{label} is not a valid integer") from None

    def load_from_yaml(self, yaml_content: str) -> None:
        if not isinstance(yaml_content, str):
            raise TypeError("register map YAML must be text")
        data = yaml.safe_load(yaml_content)
        if data is None:
            raise ValueError("register map must contain at least one register")
        if not isinstance(data, dict):
            raise TypeError("register map root must be a mapping")
        if "registers" not in data:
            raise ValueError("register map must contain at least one register")
        regs = data["registers"]
        if not isinstance(regs, list):
            raise TypeError("registers must be a list")
        if not regs:
            raise ValueError("register map must contain at least one register")

        # Stage all changes so a malformed later register cannot leave a
        # partially loaded catalog behind.
        staged_registers = dict(self.registers)
        staged_name_map = dict(self.name_map)
        for register_index, r in enumerate(regs):
            if not isinstance(r, dict):
                raise TypeError("each register must be a mapping")
            register_name = r.get("name")
            if not isinstance(register_name, str) or not register_name.strip():
                raise TypeError(f"register {register_index} name must be a non-empty string")
            offset = self._parse_int(r.get("offset"), f"register {register_name!r} offset")
            if offset < 0 or offset > 0xFFFFFFFF:
                raise ValueError(
                    f"register {register_name!r} offset must be between 0 and 0xFFFFFFFF"
                )
            fields: list[BitField] = []
            raw_fields = r.get("fields", [])
            if not isinstance(raw_fields, list):
                raise TypeError(f"register {register_name!r} fields must be a list")
            for field_index, f in enumerate(raw_fields):
                if not isinstance(f, dict):
                    raise TypeError("each register field must be a mapping")
                field_name = f.get("name")
                if not isinstance(field_name, str) or not field_name.strip():
                    raise TypeError(
                        f"register {register_name!r} field {field_index} name must be a non-empty string"
                    )
                if "bits" not in f:
                    raise ValueError(f"field {field_name!r} bits must be provided")
                access = f.get("access", "RW")
                if not isinstance(access, str):
                    raise TypeError(f"field {field_name!r} access must be a string")
                access = access.strip().upper()
                if access not in VALID_FIELD_ACCESS:
                    allowed = ", ".join(sorted(VALID_FIELD_ACCESS))
                    raise ValueError(
                        f"field {field_name!r} access {access!r} is unsupported; choose one of: {allowed}"
                    )
                val_map: dict[int, str] = {}
                raw_values = f.get("values", {})
                if not isinstance(raw_values, dict):
                    raise TypeError(f"field {field_name!r} values must be a mapping")
                for k, v in raw_values.items():
                    val_map[self._parse_int(k, f"field {field_name!r} enum value")] = str(v)
                raw_warnings = f.get("warning_values", [])
                if not isinstance(raw_warnings, list):
                    raise TypeError(f"field {field_name!r} warning_values must be a list")
                warns = [
                    self._parse_int(w, f"field {field_name!r} warning value") for w in raw_warnings
                ]
                fields.append(
                    BitField(
                        name=field_name,
                        bit_range=str(f["bits"]),
                        description=str(f.get("description", "")),
                        access=access,
                        values=val_map,
                        warning_values=warns,
                    )
                )
            raw_size = r.get("size", 32)
            raw_reset = r.get("reset")
            size = self._parse_int(raw_size, f"register {register_name!r} size")
            reset_val = (
                self._parse_int(raw_reset, f"register {register_name!r} reset")
                if raw_reset is not None
                else None
            )
            reg_def = RegisterDef(
                name=register_name,
                offset=offset,
                size=size,
                reset_val=reset_val,
                description=str(r.get("description", "")),
                fields=fields,
            )
            if offset in staged_registers:
                raise ValueError(f"duplicate register offset: 0x{offset:X}")
            name_key = register_name.lower()
            if name_key in staged_name_map:
                raise ValueError(f"duplicate register name: {reg_def.name}")
            staged_registers[offset] = reg_def
            staged_name_map[name_key] = reg_def

        self.registers = staged_registers
        self.name_map = staged_name_map

    def decode_register(self, offset_or_name: Any, value: int) -> DecodedRegisterResult:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("register value must be an integer")
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError("register value must be between 0 and 0xFFFFFFFF")
        reg_def = None
        if isinstance(offset_or_name, bool):
            raise TypeError("register offset/name must not be boolean")
        if isinstance(offset_or_name, int):
            if not 0 <= offset_or_name <= 0xFFFFFFFF:
                raise ValueError("register offset must be between 0 and 0xFFFFFFFF")
            reg_def = self.registers.get(offset_or_name)
        elif isinstance(offset_or_name, str):
            token = offset_or_name.strip()
            is_numeric = token.lower().startswith("0x") or token.lstrip("+-").isdigit()
            if is_numeric:
                offset = self._parse_int(token, "register offset")
                if offset < 0 or offset > 0xFFFFFFFF:
                    raise ValueError("register offset must be between 0 and 0xFFFFFFFF")
                reg_def = self.registers.get(offset)
            else:
                reg_def = self.name_map.get(token.lower())
        else:
            raise TypeError("register offset/name must be an integer offset or string name")
        if not reg_def:
            if isinstance(offset_or_name, int):
                unknown_offset: int | None = offset_or_name
            elif isinstance(offset_or_name, str) and is_numeric:
                unknown_offset = self._parse_int(offset_or_name, "register offset")
            else:
                # A symbolic name that is not in the catalog has no
                # evidence-backed numeric offset.  Returning 0 here made a
                # typo look like register 0x00 in reports and GUI output.
                unknown_offset = None
            return DecodedRegisterResult(
                reg_name=str(offset_or_name),
                offset=unknown_offset,
                raw_val=value,
                hex_val=f"0x{value:08X}",
                description="Unknown / Custom Register",
                fields=[],
                unmapped_bits=value,
            )
        if isinstance(reg_def.size, bool) or reg_def.size not in (8, 16, 32):
            raise ValueError(
                f"register {reg_def.name!r} size must be 8, 16, or 32 bits before decoding"
            )
        if value >= (1 << reg_def.size):
            raise ValueError(
                f"value 0x{value:X} exceeds {reg_def.size}-bit register {reg_def.name}"
            )
        decoded_fields = []
        covered_mask = 0
        for f in reg_def.fields:
            high, low = f.high_bit, f.low_bit
            if low < 0 or high >= reg_def.size:
                raise ValueError(
                    f"field {reg_def.name}.{f.name} bits exceed {reg_def.size}-bit register width"
                )
            if f.bit_mask & covered_mask:
                raise ValueError(f"field {reg_def.name}.{f.name} overlaps another field")
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
