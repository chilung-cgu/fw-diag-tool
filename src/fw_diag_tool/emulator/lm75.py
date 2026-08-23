from __future__ import annotations

import math
from typing import Any


class VirtualLM75:
    # Simulates an LM75 / TMP102 I2C Temperature Sensor

    def __init__(self, addr_7bit: int = 0x48):
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        self.addr = addr_7bit
        self.temperature_c = 25.0
        self.config_reg: int = 0x00
        self.thyst_raw: int = 0x4B00
        self.tos_raw: int = 0x5000
        self.last_cmd: int | None = None

    def write(self, data_bytes: list[int]) -> dict[str, Any]:
        if not isinstance(data_bytes, list):
            raise TypeError("data_bytes must be a list of integers")
        for index, value in enumerate(data_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                raise ValueError(f"data_bytes[{index}] must be an integer in range 0..0xFF")
        if not data_bytes:
            return {"type": "Address Probe", "summary": "LM75 Address Probe"}
        ptr_reg = data_bytes[0]
        if ptr_reg not in (0x00, 0x01, 0x02, 0x03):
            raise ValueError(f"unsupported LM75 register pointer: 0x{ptr_reg:02X}")
        self.last_cmd = ptr_reg
        ptr_names = {0x00: "TEMP", 0x01: "CONFIG", 0x02: "THYST", 0x03: "TOS"}
        name = ptr_names.get(ptr_reg, f"REG_0x{ptr_reg:02X}")
        if len(data_bytes) > 1 and ptr_reg == 0x01:
            self.config_reg = data_bytes[1]
        return {
            "type": "Set Register Pointer",
            "register": name,
            "summary": f"Set pointer to {name} (0x{ptr_reg:02X})",
        }

    def read(self, num_bytes: int = 2) -> bytes:
        if isinstance(num_bytes, bool) or not isinstance(num_bytes, int) or num_bytes < 0:
            raise ValueError("num_bytes must be a non-negative integer")
        ptr = self.last_cmd or 0x00
        if ptr == 0x00:
            raw_12bit = int(self.temperature_c / 0.0625) & 0xFFF
            raw_16bit = raw_12bit << 4
            raw = bytes([(raw_16bit >> 8) & 0xFF, raw_16bit & 0xFF])
        elif ptr == 0x01:
            raw = bytes([self.config_reg])
        elif ptr == 0x02:
            raw = bytes([(self.thyst_raw >> 8) & 0xFF, self.thyst_raw & 0xFF])
        elif ptr == 0x03:
            raw = bytes([(self.tos_raw >> 8) & 0xFF, self.tos_raw & 0xFF])
        else:  # pragma: no cover - pointer is validated by write()
            raise ValueError(f"unsupported LM75 register pointer: 0x{ptr:02X}")
        if num_bytes > len(raw):
            raise ValueError(
                f"read requests {num_bytes} byte(s), but register provides {len(raw)} byte(s)"
            )
        return raw[:num_bytes]

    def set_temperature(self, temp_c: float) -> None:
        if isinstance(temp_c, bool) or not isinstance(temp_c, (int, float)):
            raise TypeError("temp_c must be a finite numeric value")
        if not math.isfinite(float(temp_c)) or not -128.0 <= temp_c < 128.0:
            raise ValueError("temp_c must be finite and representable by the 12-bit sensor model")
        self.temperature_c = temp_c
