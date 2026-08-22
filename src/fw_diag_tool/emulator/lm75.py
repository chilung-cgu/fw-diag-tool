from __future__ import annotations

from typing import Any


class VirtualLM75:
    # Simulates an LM75 / TMP102 I2C Temperature Sensor

    def __init__(self, addr_7bit: int = 0x48):
        self.addr = addr_7bit
        self.temperature_c = 25.0
        self.config_reg: int = 0x00
        self.thyst_raw: int = 0x4B00
        self.tos_raw: int = 0x5000
        self.last_cmd: int | None = None

    def write(self, data_bytes: list[int]) -> dict[str, Any]:
        if not data_bytes:
            return {"type": "Address Probe", "summary": "LM75 Address Probe"}
        ptr_reg = data_bytes[0]
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
        ptr = self.last_cmd or 0x00
        if ptr == 0x00:
            raw_12bit = int(self.temperature_c / 0.0625) & 0xFFF
            raw_16bit = raw_12bit << 4
            return bytes([(raw_16bit >> 8) & 0xFF, raw_16bit & 0xFF])
        elif ptr == 0x01:
            return bytes([self.config_reg])
        elif ptr == 0x02:
            return bytes([(self.thyst_raw >> 8) & 0xFF, self.thyst_raw & 0xFF])
        elif ptr == 0x03:
            return bytes([(self.tos_raw >> 8) & 0xFF, self.tos_raw & 0xFF])
        return b"\x00\x00"

    def set_temperature(self, temp_c: float) -> None:
        self.temperature_c = temp_c
