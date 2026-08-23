from __future__ import annotations

from typing import Any


class VirtualEEPROM24C64:
    """Simulates a 24C64 (8KB / 64Kbit) I2C Serial EEPROM with Page Write behavior."""

    def __init__(self, addr_7bit: int = 0x50, page_size: int = 32, capacity: int = 8192):
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("page_size must be a positive integer")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if capacity % page_size:
            raise ValueError("capacity must be an exact multiple of page_size")
        self.addr = addr_7bit
        self.page_size = page_size
        self.capacity = capacity
        self.memory: bytearray = bytearray(capacity)
        self.write_cycle_ms: float = 5.0
        self.is_busy: bool = False
        self.last_write_offset: int | None = None

    def read(self, offset: int, length: int = 1) -> bytes:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise ValueError("length must be a non-negative integer")
        if offset + length > self.capacity:
            raise ValueError(f"Read out of range: offset=0x{offset:04X} len={length}")
        return bytes(self.memory[offset : offset + length])

    def write(self, data_bytes: list[int], preferred_address_bytes: int = 1) -> dict[str, Any]:
        if not isinstance(data_bytes, list):
            raise TypeError("data_bytes must be a list of integers")
        for index, value in enumerate(data_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                raise ValueError(f"data_bytes[{index}] must be an integer in range 0..0xFF")
        if (
            isinstance(preferred_address_bytes, bool)
            or not isinstance(preferred_address_bytes, int)
            or preferred_address_bytes not in (1, 2)
        ):
            raise ValueError("preferred_address_bytes must be 1 or 2")
        if not data_bytes:
            return {"type": "Address Probe", "summary": "Empty write probe"}

        if preferred_address_bytes == 2:
            if len(data_bytes) < 2:
                raise ValueError("two-byte EEPROM address requires at least two data bytes")
            offset = (data_bytes[0] << 8) | data_bytes[1]
            payload = data_bytes[2:]
        else:
            offset = data_bytes[0]
            payload = data_bytes[1:]

        if offset >= self.capacity:
            raise ValueError(f"Write address out of range: offset=0x{offset:04X}")

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
            self.memory[wrapped_offset] = val
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
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise ValueError("start must be a non-negative integer")
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise ValueError("length must be a non-negative integer")
        if start + length > self.capacity:
            raise ValueError(f"Dump out of range: start=0x{start:04X} len={length}")
        lines = []
        for row in range(0, length, 16):
            hex_str = " ".join(
                f"{self.memory[start + row + i]:02X}" for i in range(min(16, length - row))
            )
            lines.append(f"0x{start + row:04X}: {hex_str}")
        return "\n".join(lines)
