from __future__ import annotations

from typing import Any


class VirtualEEPROM24C64:
    """Simulates a 24C64 (8KB / 64Kbit) I2C Serial EEPROM with Page Write behavior."""

    def __init__(self, addr_7bit: int = 0x50, page_size: int = 32, capacity: int = 8192):
        self.addr = addr_7bit
        self.page_size = page_size
        self.capacity = capacity
        self.memory: bytearray = bytearray(capacity)
        self.write_cycle_ms: float = 5.0
        self.is_busy: bool = False
        self.last_write_offset: int | None = None

    def read(self, offset: int, length: int = 1) -> bytes:
        if offset < 0 or offset + length > self.capacity:
            raise ValueError(f"Read out of range: offset=0x{offset:04X} len={length}")
        return bytes(self.memory[offset : offset + length])

    def write(self, data_bytes: list[int], preferred_address_bytes: int = 1) -> dict[str, Any]:
        if not data_bytes:
            return {"type": "Address Probe", "summary": "Empty write probe"}

        if preferred_address_bytes == 2 and len(data_bytes) >= 2:
            offset = (data_bytes[0] << 8) | data_bytes[1]
            payload = data_bytes[2:]
        else:
            offset = data_bytes[0]
            payload = data_bytes[1:]

        if not payload:
            self.last_write_offset = offset
            return {
                "type": "Set Address Pointer",
                "offset": offset,
                "summary": f"Set pointer to 0x{offset:04X}",
            }

        # Simulate Page Rollover behavior
        page_start = (offset // self.page_size) * self.page_size
        offset_in_page = offset % self.page_size
        rollover_hazard = False

        for idx, val in enumerate(payload):
            # EEPROM address wraps within the same page boundary!
            wrapped_offset = page_start + ((offset_in_page + idx) % self.page_size)
            if wrapped_offset >= self.capacity:
                break
            self.memory[wrapped_offset] = val & 0xFF
            if offset_in_page + idx >= self.page_size:
                rollover_hazard = True

        self.is_busy = True
        self.last_write_offset = offset + len(payload)

        summary = f"Virtual EEPROM Write {len(payload)}B at 0x{offset:04X}"
        if rollover_hazard:
            summary += " ⚠️ [Page Boundary Rollover Detected!]"

        return {
            "type": "Page Write",
            "offset": offset,
            "payload_len": len(payload),
            "page_size": self.page_size,
            "rollover_hazard": rollover_hazard,
            "summary": summary,
            "is_busy": True,
            "t_wr_ms": self.write_cycle_ms,
        }

    def ack_polling(self) -> bool:
        """Simulates ACK polling - returns True when internal write cycle is done."""
        self.is_busy = False
        return True

    def dump_memory(self, start: int = 0, length: int = 256) -> str:
        lines = []
        for row in range(0, length, 16):
            hex_str = " ".join(
                f"{self.memory[start + row + i]:02X}" for i in range(min(16, length - row))
            )
            lines.append(f"0x{start + row:04X}: {hex_str}")
        return "\n".join(lines)
