from __future__ import annotations

import re
from pathlib import Path

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog


class CHeaderGenerator:
    # Generates C register definitions and bitfield RMW macros

    def __init__(self, catalog: RegisterMapCatalog | None = None):
        self.catalog = catalog or RegisterMapCatalog()

    @classmethod
    def from_yaml_file(cls, yaml_path: str | Path) -> CHeaderGenerator:
        p = Path(yaml_path)
        gen = cls()
        gen.catalog.load_from_yaml(p.read_text(encoding="utf-8"))
        return gen

    @classmethod
    def from_yaml_str(cls, yaml_content: str) -> CHeaderGenerator:
        gen = cls()
        gen.catalog.load_from_yaml(yaml_content)
        return gen

    @staticmethod
    def _sanitize_name(name: str) -> str:
        s = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
        return s.upper()

    @classmethod
    def _require_identifier(cls, kind: str, name: str) -> str:
        if not isinstance(name, str):
            raise TypeError(f"{kind} must be a string")
        sanitized = cls._sanitize_name(name)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", sanitized):
            raise ValueError(f"{kind} must produce a C identifier beginning with a letter")
        return sanitized

    @staticmethod
    def _escape_c_comment(value: object) -> str:
        """Keep untrusted descriptions inside one C block comment."""
        text = str(value).replace("\r", " ").replace("\n", " ")
        return text.replace("/*", "/ *").replace("*/", "* /")

    def _validate_catalog(self) -> None:
        register_names: set[str] = set()
        for offset, reg in self.catalog.registers.items():
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError(f"register {reg.name!r} has an invalid offset")
            if isinstance(reg.size, bool) or reg.size not in (8, 16, 32):
                raise ValueError(f"register {reg.name!r} size must be 8, 16, or 32 bits")
            if reg.reset_val is not None:
                if isinstance(reg.reset_val, bool) or not isinstance(reg.reset_val, int):
                    raise ValueError(f"register {reg.name!r} reset value must be an integer")
                if not 0 <= reg.reset_val < (1 << reg.size):
                    raise ValueError(f"register {reg.name!r} reset value exceeds its width")

            register_name = self._require_identifier("register name", reg.name)
            if register_name in register_names:
                raise ValueError(f"duplicate generated register name: {register_name}")
            register_names.add(register_name)

            used_mask = 0
            field_names: set[str] = set()
            for field in reg.fields:
                field_name = self._require_identifier(f"field in register {reg.name!r}", field.name)
                if field_name in field_names:
                    raise ValueError(
                        f"duplicate generated field name {field_name!r} in register {reg.name!r}"
                    )
                field_names.add(field_name)

                high, low = field.high_bit, field.low_bit
                if low < 0 or high >= reg.size:
                    raise ValueError(
                        f"field {reg.name}.{field.name} bits exceed {reg.size}-bit register width"
                    )
                if field.bit_mask & used_mask:
                    raise ValueError(f"field {reg.name}.{field.name} overlaps another field")
                used_mask |= field.bit_mask

                max_value = (1 << (high - low + 1)) - 1
                if any(value < 0 or value > max_value for value in field.values):
                    raise ValueError(
                        f"field {reg.name}.{field.name} enum value exceeds field width"
                    )
                if any(value < 0 or value > max_value for value in field.warning_values):
                    raise ValueError(
                        f"field {reg.name}.{field.name} warning value exceeds field width"
                    )

                value_labels: set[str] = set()
                for meaning in field.values.values():
                    label = self._require_identifier(
                        f"field {reg.name}.{field.name} enum label", meaning
                    )
                    if label in value_labels:
                        raise ValueError(
                            f"field {reg.name}.{field.name} has duplicate generated enum labels"
                        )
                    value_labels.add(label)

    def generate_header(self, module_name: str = "CHIP_REGS") -> str:
        module_identifier = self._require_identifier("module_name", module_name)
        self._validate_catalog()
        guard_name = f"{module_identifier}_H"
        lines: list[str] = [
            "/**",
            f" * @file {module_identifier.lower()}.h",
            " * @brief Auto-generated Hardware Register Bitfield Definitions & RMW Macros",
            " * @generated by fw-diag-tool (Firmware Diagnostic Toolkit)",
            " * @note Do NOT edit manually unless necessary.",
            " */",
            "",
            f"#ifndef {guard_name}",
            f"#define {guard_name}",
            "",
            "#include <stdint.h>",
            "",
            "/* ========================================================================= */",
            "/*                      REGISTER OFFSETS & MASKS                             */",
            "/* ========================================================================= */",
            "",
        ]

        for offset, reg in sorted(self.catalog.registers.items()):
            r_name = self._sanitize_name(reg.name)
            desc_comment = (
                f" /* {self._escape_c_comment(reg.description)} */" if reg.description else ""
            )
            lines.append(f"/* Register: {r_name} (0x{reg.offset:04X}){desc_comment} */")
            lines.append(f"#define REG_{r_name}_OFFSET              (0x{reg.offset:04X}U)")
            if reg.reset_val is not None:
                lines.append(f"#define REG_{r_name}_RESET               (0x{reg.reset_val:08X}U)")
            lines.append("")

            for f in reg.fields:
                f_name = self._sanitize_name(f.name)
                pos = f.low_bit
                mask = f.bit_mask
                lines.append(f"#define REG_{r_name}_{f_name}_POS        ({pos}U)")
                lines.append(f"#define REG_{r_name}_{f_name}_MSK        (0x{mask:08X}U)")
                lines.append(
                    f"#define REG_{r_name}_{f_name}_GET(val)   (((val) & REG_{r_name}_{f_name}_MSK) >> REG_{r_name}_{f_name}_POS)"
                )
                if f.access.strip().upper() != "RO":
                    lines.append(
                        f"#define REG_{r_name}_{f_name}_SET(reg, val) (((reg) & ~REG_{r_name}_{f_name}_MSK) | (((uint32_t)(val) << REG_{r_name}_{f_name}_POS) & REG_{r_name}_{f_name}_MSK))"
                    )

                if f.values:
                    lines.append(f"/* Values for {r_name}.{f_name} */")
                    for val_int, val_meaning in sorted(f.values.items()):
                        v_label = self._sanitize_name(val_meaning)
                        lines.append(f"#define VAL_{r_name}_{f_name}_{v_label} ({val_int}U)")
                lines.append("")

            lines.append(
                "/* ------------------------------------------------------------------------- */"
            )
            lines.append("")

        lines.append(f"#endif /* {guard_name} */")
        lines.append("")
        return "\n".join(lines)
