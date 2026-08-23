"""I2C Serial EEPROM Protocol & Page Write Rollover Analyzer.

Analyzes 24Cxx series EEPROM read/write sequences (24C02 to 24C1024),
detects 1-byte vs 2-byte word addressing, tracks random and sequential reads,
and detects critical Page Boundary Wrap-Around write hazards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EEPROMProfile:
    """EEPROM chip specification."""

    model: str
    capacity_kbits: int
    address_bytes: int  # 1 or 2
    page_size_bytes: int
    t_wr_max_ms: float = 5.0


EEPROM_MODELS: dict[str, EEPROMProfile] = {
    "24C02": EEPROMProfile("24C02", 2, 1, 8, 5.0),
    "24C04": EEPROMProfile("24C04", 4, 1, 16, 5.0),
    "24C08": EEPROMProfile("24C08", 8, 1, 16, 5.0),
    "24C16": EEPROMProfile("24C16", 16, 1, 16, 5.0),
    "24C32": EEPROMProfile("24C32", 32, 2, 32, 5.0),
    "24C64": EEPROMProfile("24C64", 64, 2, 32, 5.0),
    "24C128": EEPROMProfile("24C128", 128, 2, 64, 5.0),
    "24C256": EEPROMProfile("24C256", 256, 2, 64, 5.0),
    "24C512": EEPROMProfile("24C512", 512, 2, 128, 5.0),
    "24M01": EEPROMProfile("24M01", 1024, 2, 256, 5.0),
}


def decode_eeprom_write(
    data_bytes: list[int], preferred_address_bytes: int = 1, page_size: int = 16
) -> dict[str, Any]:
    """Decode an EEPROM write sequence, detecting word offset and page boundary hazard.

    Args:
        data_bytes: Payload bytes transmitted following slave address byte.
        preferred_address_bytes: 1 for 24C01-24C16, 2 for 24C32-24C512.
        page_size: Page size in bytes for boundary check.
    """
    if not data_bytes:
        return {
            "type": "Write Polling / Address Probe",
            "summary": "Write Polling probe (0 payload bytes)",
        }

    # Determine offset length: if user specified or data implies 2-byte
    addr_bytes_len = preferred_address_bytes
    if len(data_bytes) == 1:
        addr_bytes_len = 1
        offset = data_bytes[0]
        payload = []
    elif addr_bytes_len == 2 and len(data_bytes) >= 2:
        offset = (data_bytes[0] << 8) | data_bytes[1]
        payload = data_bytes[2:]
    else:
        offset = data_bytes[0]
        payload = data_bytes[1:]

    payload_len = len(payload)

    # Check Page Boundary Rollover
    # If start offset + payload length crosses the page boundary, the EEPROM hardware counter wraps!
    safe_page_size = max(1, page_size)
    offset_in_page = offset % safe_page_size
    page_start = (offset // safe_page_size) * safe_page_size
    rollover_hazard = False
    rollover_details = ""

    if payload_len > (safe_page_size - offset_in_page):
        rollover_hazard = True
        overflow_count = payload_len - (safe_page_size - offset_in_page)
        rollover_details = (
            f"Page rollover hazard: Write started at offset 0x{offset:04X} (page base 0x{page_start:04X}, "
            f"page size {safe_page_size}B). Payload length {payload_len}B exceeds remaining {safe_page_size - offset_in_page}B "
            f"in this page. {overflow_count} byte(s) will WRAP AROUND and overwrite offset 0x{page_start:04X}!"
        )

    write_type = (
        "Byte Write"
        if payload_len == 1
        else (
            f"Page Write ({payload_len} bytes)" if payload_len > 1 else "Dummy Write / Address Set"
        )
    )

    summary = f"EEPROM {write_type} at Offset 0x{offset:04X}"
    if payload:
        preview = " ".join(f"{b:02X}" for b in payload[:8]) + ("..." if len(payload) > 8 else "")
        summary += f": [{preview}]"

    return {
        "type": write_type,
        "offset": offset,
        "offset_hex": f"0x{offset:04X}",
        "address_bytes": addr_bytes_len,
        "payload_len": payload_len,
        "payload": [f"0x{b:02X}" for b in payload],
        "summary": summary,
        "page_size": safe_page_size,
        "rollover_hazard": rollover_hazard,
        "rollover_details": rollover_details,
    }


def decode_eeprom_read(
    data_bytes: list[int], last_known_offset: int | None = None
) -> dict[str, Any]:
    """Decode an EEPROM read transaction."""
    payload_len = len(data_bytes)
    if payload_len == 0:
        return {"type": "Read Probe", "summary": "Empty Read"}

    read_type = (
        "Current Address Read (1 byte)"
        if payload_len == 1
        else f"Sequential Read ({payload_len} bytes)"
    )
    summary = f"EEPROM {read_type}"
    if last_known_offset is not None:
        summary += f" from 0x{last_known_offset:04X}"

    preview = " ".join(f"{b:02X}" for b in data_bytes[:8]) + ("..." if len(data_bytes) > 8 else "")
    summary += f": [{preview}]"

    return {
        "type": read_type,
        "payload_len": payload_len,
        "start_offset": last_known_offset,
        "start_offset_hex": f"0x{last_known_offset:04X}"
        if last_known_offset is not None
        else "Unknown",
        "data_bytes": [f"0x{b:02X}" for b in data_bytes],
        "summary": summary,
    }
