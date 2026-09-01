from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fw_diag_tool.evidence import EvidenceMetric
from fw_diag_tool.spi.models import SPIOpcode, SPIReport, SPITransaction

_ARRAY_WRITE_OR_ERASE_OPCODES = {
    SPIOpcode.PAGE_PROGRAM,
    SPIOpcode.QUAD_PAGE_PROGRAM,
    SPIOpcode.SECTOR_ERASE_4K,
    SPIOpcode.BLOCK_ERASE_32K,
    SPIOpcode.BLOCK_ERASE_64K,
    SPIOpcode.CHIP_ERASE,
    SPIOpcode.CHIP_ERASE_ALT,
}

_STATUS_READ_OPCODES = {
    SPIOpcode.READ_STATUS_REG_1,
    SPIOpcode.READ_STATUS_REG_2,
    SPIOpcode.READ_STATUS_REG_3,
}


@dataclass(frozen=True)
class SPIStatistics:
    """Statistical summary of SPI / QSPI Flash transactions."""

    command_distribution: dict[str, int]
    total_bytes_transferred: int
    throughput_bytes_per_sec: float | None
    avg_command_latency_us: float | None
    busy_poll_count: int
    avg_busy_wait_us: float | None
    page_program_stats: EvidenceMetric | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "command_distribution": dict(self.command_distribution),
            "total_bytes_transferred": self.total_bytes_transferred,
            "throughput_bytes_per_sec": self.throughput_bytes_per_sec,
            "avg_command_latency_us": self.avg_command_latency_us,
            "busy_poll_count": self.busy_poll_count,
            "avg_busy_wait_us": self.avg_busy_wait_us,
        }
        if self.page_program_stats is not None:
            res["page_program_stats"] = self.page_program_stats.to_dict()
        return res


def _is_busy_poll_tx(tx: SPITransaction) -> bool:
    if tx.opcode in _STATUS_READ_OPCODES:
        return True
    if tx.decoded_details.get("busy") is not None:
        return True
    return bool(tx.opcode == 0x05 or (tx.opcode_name and "Read Status" in tx.opcode_name))


def _is_valid_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def compute_spi_statistics(report: SPIReport) -> SPIStatistics:
    """Compute statistical metrics across all transactions in an SPI report."""
    transactions = report.transactions
    if not transactions:
        return SPIStatistics(
            command_distribution={},
            total_bytes_transferred=0,
            throughput_bytes_per_sec=None,
            avg_command_latency_us=None,
            busy_poll_count=0,
            avg_busy_wait_us=None,
            page_program_stats=EvidenceMetric.unavailable(
                reason="No transactions in SPI report",
                source="SPI trace",
                unit="µs",
            ),
        )

    # 1. Command Distribution & Total Bytes
    command_distribution: dict[str, int] = {}
    total_bytes = 0
    page_program_txs: list[SPITransaction] = []

    for tx in transactions:
        op_name = tx.opcode_name if tx.opcode_name else "Unknown Opcode"
        command_distribution[op_name] = command_distribution.get(op_name, 0) + 1
        tx_byte_len = max(len(tx.mosi_bytes), len(tx.miso_bytes))
        total_bytes += tx_byte_len

        if tx.opcode in (SPIOpcode.PAGE_PROGRAM, SPIOpcode.QUAD_PAGE_PROGRAM):
            page_program_txs.append(tx)

    # 2. Timing and Throughput
    valid_starts = [tx.start_time for tx in transactions if _is_valid_number(tx.start_time)]
    valid_ends = [tx.end_time for tx in transactions if _is_valid_number(tx.end_time)]
    valid_durations = [tx.duration_us for tx in transactions if _is_valid_number(tx.duration_us)]

    has_timestamps = bool(
        valid_starts
        and valid_ends
        and (
            any(d > 0.0 for d in valid_durations)
            or any(s > 0.0 for s in valid_starts)
            or any(e > 0.0 for e in valid_ends)
        )
    )

    throughput_bytes_per_sec: float | None = None
    avg_command_latency_us: float | None = None

    if has_timestamps:
        min_start = min(valid_starts)
        max_end = max(valid_ends)
        duration_s = max_end - min_start
        if duration_s > 0:
            throughput_bytes_per_sec = total_bytes / duration_s
        elif len(transactions) == 1 and valid_durations and valid_durations[0] > 0:
            throughput_bytes_per_sec = total_bytes / (valid_durations[0] / 1e6)

        if valid_durations:
            avg_command_latency_us = sum(valid_durations) / len(transactions)

    # 3. Busy Poll Count & Busy Wait Duration
    busy_poll_count = sum(1 for tx in transactions if _is_busy_poll_tx(tx))

    busy_wait_durations_us: list[float] = []
    i = 0
    n = len(transactions)
    while i < n:
        tx = transactions[i]
        # Case A: Write/Erase command followed by status polling
        if tx.opcode in _ARRAY_WRITE_OR_ERASE_OPCODES and _is_valid_number(tx.end_time):
            write_end_time = tx.end_time
            j = i + 1
            saw_busy_true = False
            last_poll_tx: SPITransaction | None = None
            while j < n and _is_busy_poll_tx(transactions[j]):
                poll_tx = transactions[j]
                last_poll_tx = poll_tx
                busy_val = poll_tx.decoded_details.get("busy")
                if busy_val is True:
                    saw_busy_true = True
                elif busy_val is False and saw_busy_true and _is_valid_number(poll_tx.end_time):
                    # Completed busy wait cycle
                    wait_us = (poll_tx.end_time - write_end_time) * 1e6
                    if wait_us >= 0:
                        busy_wait_durations_us.append(wait_us)
                    break
                j += 1
            else:
                # Loop ended without encountering busy=False after busy=True
                if (
                    saw_busy_true
                    and last_poll_tx is not None
                    and _is_valid_number(last_poll_tx.end_time)
                ):
                    wait_us = (last_poll_tx.end_time - write_end_time) * 1e6
                    if wait_us >= 0:
                        busy_wait_durations_us.append(wait_us)
            i = j
            continue

        # Case B: Standalone sequence of status polls starting with busy=True
        busy_val = tx.decoded_details.get("busy")
        if _is_busy_poll_tx(tx) and busy_val is True and _is_valid_number(tx.start_time):
            start_poll_time = tx.start_time
            j = i + 1
            last_poll_tx = tx
            while j < n and _is_busy_poll_tx(transactions[j]):
                poll_tx = transactions[j]
                last_poll_tx = poll_tx
                b_val = poll_tx.decoded_details.get("busy")
                if b_val is False and _is_valid_number(poll_tx.end_time):
                    wait_us = (poll_tx.end_time - start_poll_time) * 1e6
                    if wait_us >= 0:
                        busy_wait_durations_us.append(wait_us)
                    break
                j += 1
            else:
                if _is_valid_number(last_poll_tx.end_time):
                    wait_us = (last_poll_tx.end_time - start_poll_time) * 1e6
                    if wait_us > 0:
                        busy_wait_durations_us.append(wait_us)
            i = j
            continue

        i += 1

    avg_busy_wait_us: float | None = None
    if busy_wait_durations_us:
        avg_busy_wait_us = sum(busy_wait_durations_us) / len(busy_wait_durations_us)

    # 4. Page Program Stats (EvidenceMetric)
    if page_program_txs:
        pp_durations = [t.duration_us for t in page_program_txs if t.duration_us > 0]
        if pp_durations:
            avg_pp_latency = sum(pp_durations) / len(pp_durations)
            page_program_stats = EvidenceMetric.measured(
                value=avg_pp_latency,
                sample_count=len(page_program_txs),
                source="SPI trace",
                unit="µs",
                count=len(page_program_txs),
            )
        else:
            page_program_stats = EvidenceMetric.measured(
                value=float(len(page_program_txs)),
                sample_count=len(page_program_txs),
                source="SPI trace",
                unit="count",
                count=len(page_program_txs),
            )
    else:
        page_program_stats = EvidenceMetric.unavailable(
            reason="No Page Program commands observed in trace",
            source="SPI trace",
            unit="µs",
        )

    return SPIStatistics(
        command_distribution=command_distribution,
        total_bytes_transferred=total_bytes,
        throughput_bytes_per_sec=throughput_bytes_per_sec,
        avg_command_latency_us=avg_command_latency_us,
        busy_poll_count=busy_poll_count,
        avg_busy_wait_us=avg_busy_wait_us,
        page_program_stats=page_program_stats,
    )
