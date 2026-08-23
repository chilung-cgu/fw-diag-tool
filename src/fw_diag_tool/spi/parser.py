"""SPI Logic Analyzer Trace Parser and JEDEC Command Decoder."""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Any

from .models import (
    OPCODE_NAMES,
    FlashStatusRegister1,
    SPIOpcode,
    SPITransaction,
)

JEDEC_DATABASE: dict[tuple[int, int, int], str] = {
    (0xEF, 0x40, 0x15): "Winbond W25Q16 (16 Mbit / 2 MB)",
    (0xEF, 0x40, 0x16): "Winbond W25Q32 (32 Mbit / 4 MB)",
    (0xEF, 0x40, 0x17): "Winbond W25Q64 (64 Mbit / 8 MB)",
    (0xEF, 0x40, 0x18): "Winbond W25Q128 (128 Mbit / 16 MB)",
    (0xEF, 0x40, 0x19): "Winbond W25Q256 (256 Mbit / 32 MB)",
    (0xEF, 0x70, 0x19): "Winbond W25Q256JV DTR (256 Mbit)",
    (0xC2, 0x20, 0x17): "Macronix MX25L64 (64 Mbit / 8 MB)",
    (0xC2, 0x20, 0x18): "Macronix MX25L128 (128 Mbit / 16 MB)",
    (0xC2, 0x20, 0x19): "Macronix MX25L256 (256 Mbit / 32 MB)",
    (0xC2, 0x20, 0x1A): "Macronix MX25L512 (512 Mbit / 64 MB)",
    (0x20, 0xBA, 0x18): "Micron N25Q128 (128 Mbit / 16 MB)",
    (0x20, 0xBA, 0x19): "Micron N25Q256 (256 Mbit / 32 MB)",
    (0x20, 0xBA, 0x20): "Micron MT25QL512 (512 Mbit / 64 MB)",
    (0xC8, 0x40, 0x17): "GigaDevice GD25Q64 (64 Mbit / 8 MB)",
    (0xC8, 0x40, 0x18): "GigaDevice GD25Q128 (128 Mbit / 16 MB)",
    (0xC8, 0x40, 0x19): "GigaDevice GD25Q256 (256 Mbit / 32 MB)",
}


class SPIParser:
    @staticmethod
    def parse_hex_byte(val: Any) -> int | None:
        if val is None:
            return None
        if isinstance(val, int):
            return val if 0 <= val <= 0xFF else None
        s = str(val).strip()
        if not s or s.lower() in ("-", "none", "null"):
            return None
        if s.startswith(("0x", "0X")):
            try:
                parsed = int(s, 16)
            except ValueError:
                return None
            return parsed if 0 <= parsed <= 0xFF else None
        try:
            parsed = int(s, 16) if len(s) == 2 and re.match(r"^[0-9a-fA-F]{2}$", s) else int(s, 10)
        except ValueError:
            return None
        return parsed if 0 <= parsed <= 0xFF else None

    @classmethod
    def _parse_byte_cell(cls, value: Any, row_number: int, column_name: str) -> int | None:
        text = "" if value is None else str(value).strip()
        if not text or text.lower() in {"-", "none", "null"}:
            return None
        parsed = cls.parse_hex_byte(value)
        if parsed is None:
            raise ValueError(
                f"invalid {column_name} byte at CSV row {row_number}: {text!r}; expected 0..255 or 0x00..0xFF"
            )
        return parsed

    @classmethod
    def parse_csv_content(cls, csv_text: str, page_size: int = 256) -> list[SPITransaction]:
        if not isinstance(csv_text, str):
            raise TypeError("csv_text must be a string")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("page_size must be a positive integer")
        reader = csv.reader(io.StringIO(csv_text.strip()))
        rows = [r for r in reader if r and not r[0].strip().startswith("#")]
        if not rows:
            return []

        header = [h.strip().lower() for h in rows[0]]
        # Find column indices
        t_idx = -1
        mosi_idx = -1
        miso_idx = -1
        cs_idx = -1

        for i, col in enumerate(header):
            if "time" in col or "start" in col:
                t_idx = i
            elif "mosi" in col or "tx" in col or "din" in col or "si" in col:
                mosi_idx = i
            elif "miso" in col or "rx" in col or "dout" in col or "so" in col:
                miso_idx = i
            elif "enable" in col or "cs" in col or "ss" in col or "select" in col:
                cs_idx = i

        # Fallback if standard Saleae format
        if t_idx == -1:
            t_idx = 0
        if mosi_idx == -1 and len(header) > 1:
            mosi_idx = 1
        if miso_idx == -1 and len(header) > 2:
            miso_idx = 2
        if mosi_idx < 0 or miso_idx < 0:
            raise ValueError("SPI CSV must provide MOSI and MISO columns")
        if cs_idx < 0:
            raise ValueError(
                "SPI CSV must provide a CS/Enable column so transactions can be framed safely"
            )

        transactions: list[SPITransaction] = []
        cur_mosi: list[int] = []
        cur_miso: list[int] = []
        t_start = 0.0
        t_end = 0.0
        in_tx = False

        data_rows = rows[1:]
        previous_timestamp: float | None = None
        for row_number, row in enumerate(data_rows, start=2):
            if not row or len(row) <= max(t_idx, mosi_idx, miso_idx):
                raise ValueError(
                    f"CSV row {row_number} is missing a required time/MOSI/MISO column"
                )
            try:
                timestamp = float(row[t_idx])
            except ValueError:
                raise ValueError(
                    f"invalid timestamp at CSV row {row_number}: {row[t_idx]!r}"
                ) from None
            if not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError(
                    f"timestamp at CSV row {row_number} must be finite and non-negative"
                )
            if previous_timestamp is not None and timestamp < previous_timestamp:
                raise ValueError(f"timestamps decrease at CSV row {row_number}")
            previous_timestamp = timestamp

            mosi_val = cls._parse_byte_cell(row[mosi_idx], row_number, "MOSI")
            miso_val = cls._parse_byte_cell(row[miso_idx], row_number, "MISO")
            if mosi_val is None or miso_val is None:
                raise ValueError(
                    f"CSV row {row_number} must provide both MOSI and MISO bytes; "
                    "empty channel data is incomplete evidence"
                )

            # Check CS state if column present
            cs_state = (
                str(row[cs_idx]).strip().lower() if (cs_idx != -1 and cs_idx < len(row)) else None
            )
            if cs_state is None or cs_state in ("0", "low", "false", "asserted"):
                cs_asserted = True
            elif cs_state in ("1", "high", "true", "deasserted"):
                cs_asserted = False
            else:
                raise ValueError(f"invalid chip-select state at CSV row {row_number}: {cs_state!r}")

            if cs_asserted:
                if not in_tx:
                    in_tx = True
                    t_start = timestamp
                    cur_mosi = []
                    cur_miso = []
                t_end = timestamp
                if mosi_val is not None:
                    cur_mosi.append(mosi_val)
                if miso_val is not None:
                    cur_miso.append(miso_val)
            else:
                if in_tx:
                    in_tx = False
                    if cur_mosi or cur_miso:
                        tx = cls.decode_single_transaction(
                            len(transactions) + 1,
                            t_start,
                            t_end,
                            cur_mosi,
                            cur_miso,
                            page_size=page_size,
                        )
                        transactions.append(tx)
                    cur_mosi = []
                    cur_miso = []

        if in_tx and (cur_mosi or cur_miso):
            tx = cls.decode_single_transaction(
                len(transactions) + 1,
                t_start,
                t_end,
                cur_mosi,
                cur_miso,
                page_size=page_size,
            )
            tx.decoded_details["capture_incomplete"] = True
            transactions.append(tx)

        return transactions

    @classmethod
    def decode_single_transaction(
        cls,
        index: int,
        start_time: float,
        end_time: float,
        mosi: list[int],
        miso: list[int],
        page_size: int = 256,
    ) -> SPITransaction:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("page_size must be a positive integer")
        if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
            raise ValueError("index must be a positive integer")
        for name, value in (("start_time", start_time), ("end_time", end_time)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite and non-negative")
            if value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if end_time < start_time:
            raise ValueError("end_time must not precede start_time")
        for name, values in (("mosi", mosi), ("miso", miso)):
            if not isinstance(values, list) or not values:
                raise ValueError(f"{name} must be a non-empty list of bytes")
            for byte_index, value in enumerate(values):
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                    raise ValueError(f"{name}[{byte_index}] must be an integer in range 0..0xFF")
        dur_us = max(0.0, (end_time - start_time) * 1_000_000.0)
        opcode = mosi[0] if mosi else None
        opcode_name = (
            OPCODE_NAMES.get(opcode, f"Unknown Opcode (0x{opcode:02X})")
            if opcode is not None
            else "No Data"
        )

        address = None
        details: dict[str, Any] = {}
        payload_len = 0

        if opcode is not None:
            # 1. JEDEC ID (0x9F)
            if opcode == SPIOpcode.JEDEC_ID:
                if len(miso) >= 4:
                    mfr_id = miso[1]
                    mem_type = miso[2]
                    cap_id = miso[3]
                    chip_name = JEDEC_DATABASE.get(
                        (mfr_id, mem_type, cap_id), "Unknown Manufacturer / Model"
                    )
                    details["mfr_id"] = f"0x{mfr_id:02X}"
                    details["mem_type"] = f"0x{mem_type:02X}"
                    details["capacity_id"] = f"0x{cap_id:02X}"
                    details["identified_chip"] = chip_name

            # 2. Read Commands (0x03, 0x0B)
            elif opcode in (SPIOpcode.READ_DATA, SPIOpcode.FAST_READ):
                addr_len = 3
                dummy_len = 1 if opcode == SPIOpcode.FAST_READ else 0
                if len(mosi) >= 1 + addr_len:
                    address = (mosi[1] << 16) | (mosi[2] << 8) | mosi[3]
                    data_offset = 1 + addr_len + dummy_len
                    payload_len = max(0, len(miso) - data_offset)
                    details["read_address"] = f"0x{address:06X}"
                    details["read_bytes"] = payload_len

            # 3. Page Program (0x02, 0x32)
            elif opcode in (SPIOpcode.PAGE_PROGRAM, SPIOpcode.QUAD_PAGE_PROGRAM):
                if len(mosi) >= 4:
                    address = (mosi[1] << 16) | (mosi[2] << 8) | mosi[3]
                    payload_len = max(0, len(mosi) - 4)
                    details["program_address"] = f"0x{address:06X}"
                    details["program_bytes"] = payload_len
                    details["page_start_offset"] = address % page_size
                    # Detect page-buffer wrap hazard
                    if (address % page_size) + payload_len > page_size:
                        details["page_wrap_hazard"] = True
                    details["page_size"] = page_size

            # 4. Erase Commands (0x20, 0x52, 0xD8, 0xC7)
            elif opcode in (
                SPIOpcode.SECTOR_ERASE_4K,
                SPIOpcode.BLOCK_ERASE_32K,
                SPIOpcode.BLOCK_ERASE_64K,
            ):
                if len(mosi) >= 4:
                    address = (mosi[1] << 16) | (mosi[2] << 8) | mosi[3]
                    details["erase_address"] = f"0x{address:06X}"

            # 5. Read Status Register 1 (0x05)
            elif opcode == SPIOpcode.READ_STATUS_REG_1 and len(miso) >= 2:
                sr1 = FlashStatusRegister1.decode(miso[1])
                details["sr1_raw"] = f"0x{sr1.raw_val:02X}"
                details["busy"] = sr1.busy
                details["wel"] = sr1.wel
                details["block_protect"] = (sr1.bp2 << 2) | (sr1.bp1 << 1) | sr1.bp0

        return SPITransaction(
            index=index,
            start_time=start_time,
            end_time=end_time,
            duration_us=dur_us,
            mosi_bytes=mosi,
            miso_bytes=miso,
            opcode=opcode,
            opcode_name=opcode_name,
            address=address,
            data_payload_len=payload_len,
            decoded_details=details,
        )
