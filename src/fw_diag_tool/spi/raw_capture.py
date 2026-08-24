from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from fw_diag_tool.errors import InputFormatError, ResourceLimitError
from fw_diag_tool.limits import AnalysisLimits, coerce_limits
from fw_diag_tool.spi.models import OPCODE_NAMES, SPITransaction


@dataclass(frozen=True)
class RawSPITransition:
    timestamp: float
    sclk: int
    cs: int
    mosi: int
    miso: int


@dataclass
class RawSPIDecodeResult:
    transactions: list[SPITransaction]
    total_transitions: int
    cpol: int = 0
    cpha: int = 0


def parse_raw_spi_csv(
    content: str | bytes,
    *,
    cpol: int = 0,
    cpha: int = 0,
    limits: AnalysisLimits | None = None,
) -> RawSPIDecodeResult:
    """Decode raw digital SPI transitions (Time, SCLK, CS, MOSI, MISO) into SPITransactions."""
    limits = coerce_limits(limits)
    if isinstance(content, bytes):
        if len(content) > limits.max_upload_bytes:
            raise ResourceLimitError(
                "raw SPI capture exceeds upload limit",
                resource="upload",
                limit=limits.max_upload_bytes,
            )
        text = content.decode("utf-8-sig")
    else:
        text = content.lstrip("\ufeff")

    reader = csv.reader(io.StringIO(text.strip()))
    header = next(reader, None)
    if not header:
        return RawSPIDecodeResult(transactions=[], total_transitions=0, cpol=cpol, cpha=cpha)

    col_map = {col.strip().lower(): idx for idx, col in enumerate(header)}

    def find_col(*aliases: str) -> int | None:
        for a in aliases:
            if a in col_map:
                return col_map[a]
        return None

    time_idx = find_col("time", "time [s]", "timestamp")
    sclk_idx = find_col("sclk", "clk", "clock")
    cs_idx = find_col("cs", "cs#", "enable", "ss")
    mosi_idx = find_col("mosi", "tx", "di", "din", "si")
    miso_idx = find_col("miso", "rx", "do", "dout", "so")

    if (
        time_idx is None
        or sclk_idx is None
        or cs_idx is None
        or mosi_idx is None
        or miso_idx is None
    ):
        raise InputFormatError("Raw SPI CSV requires Time, SCLK, CS, MOSI, and MISO columns")

    transitions: list[RawSPITransition] = []
    max_idx = max(time_idx, sclk_idx, cs_idx, mosi_idx, miso_idx)
    for row in reader:
        if not row or len(row) <= max_idx:
            continue
        try:
            t = float(row[time_idx])
            sclk = int(row[sclk_idx]) & 1
            cs = int(row[cs_idx]) & 1
            mosi = int(row[mosi_idx]) & 1
            miso = int(row[miso_idx]) & 1
            transitions.append(RawSPITransition(t, sclk, cs, mosi, miso))
            if len(transitions) > limits.max_transitions:
                raise ResourceLimitError(
                    "transitions exceeded limit",
                    resource="transitions",
                    limit=limits.max_transitions,
                )
        except (ValueError, IndexError):
            continue

    transactions: list[SPITransaction] = []
    in_tx = False
    tx_start_t = 0.0
    mosi_bytes: list[int] = []
    miso_bytes: list[int] = []
    cur_mosi_bits = 0
    cur_miso_bits = 0
    bit_count = 0
    last_sclk = cpol

    sample_rising = cpol == cpha

    for tr in transitions:
        if tr.cs == 0:
            if not in_tx:
                in_tx = True
                tx_start_t = tr.timestamp
                mosi_bytes = []
                miso_bytes = []
                cur_mosi_bits = 0
                cur_miso_bits = 0
                bit_count = 0
                last_sclk = tr.sclk
                continue

            is_edge = tr.sclk != last_sclk
            is_sample_edge = (
                (tr.sclk == 1 and last_sclk == 0)
                if sample_rising
                else (tr.sclk == 0 and last_sclk == 1)
            )
            last_sclk = tr.sclk

            if is_edge and is_sample_edge:
                cur_mosi_bits = (cur_mosi_bits << 1) | tr.mosi
                cur_miso_bits = (cur_miso_bits << 1) | tr.miso
                bit_count += 1
                if bit_count == 8:
                    mosi_bytes.append(cur_mosi_bits & 0xFF)
                    miso_bytes.append(cur_miso_bits & 0xFF)
                    cur_mosi_bits = 0
                    cur_miso_bits = 0
                    bit_count = 0
        else:
            if in_tx:
                in_tx = False
                if mosi_bytes:
                    opcode = mosi_bytes[0]
                    name = OPCODE_NAMES.get(opcode, f"Unknown Opcode (0x{opcode:02X})")
                    transactions.append(
                        SPITransaction(
                            index=len(transactions) + 1,
                            start_time=tx_start_t,
                            end_time=tr.timestamp,
                            duration_us=max(0.0, (tr.timestamp - tx_start_t) * 1_000_000),
                            mosi_bytes=mosi_bytes,
                            miso_bytes=miso_bytes,
                            opcode=opcode,
                            opcode_name=name,
                            address=None,
                            data_payload_len=max(0, len(mosi_bytes) - 1),
                        )
                    )

    return RawSPIDecodeResult(
        transactions=transactions,
        total_transitions=len(transitions),
        cpol=cpol,
        cpha=cpha,
    )


__all__ = ["RawSPIDecodeResult", "RawSPITransition", "parse_raw_spi_csv"]
