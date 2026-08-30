from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.evidence import EvidenceLevel
from fw_diag_tool.spi.models import (
    SPIOpcode,
    SPIReport,
    SPIReportSummary,
    SPITransaction,
)
from fw_diag_tool.spi.statistics import SPIStatistics, compute_spi_statistics


def _make_tx(
    index: int,
    opcode: int | None,
    opcode_name: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
    duration_us: float = 0.0,
    mosi_bytes: list[int] | None = None,
    miso_bytes: list[int] | None = None,
    details: dict | None = None,
) -> SPITransaction:
    mosi = [opcode] if opcode is not None else []
    if mosi_bytes is not None:
        mosi = mosi_bytes
    miso = [0x00] * len(mosi) if miso_bytes is None else miso_bytes
    return SPITransaction(
        index=index,
        start_time=start_time,
        end_time=end_time,
        duration_us=duration_us,
        mosi_bytes=mosi,
        miso_bytes=miso,
        opcode=opcode,
        opcode_name=opcode_name,
        decoded_details=details or {},
    )


def test_empty_report() -> None:
    report = SPIReport(summary=SPIReportSummary(), transactions=[])
    stats = compute_spi_statistics(report)

    assert stats.command_distribution == {}
    assert stats.total_bytes_transferred == 0
    assert stats.throughput_bytes_per_sec is None
    assert stats.avg_command_latency_us is None
    assert stats.busy_poll_count == 0
    assert stats.avg_busy_wait_us is None
    assert stats.page_program_stats is not None
    assert stats.page_program_stats.level == EvidenceLevel.UNAVAILABLE


def test_single_read_command() -> None:
    tx = _make_tx(
        index=1,
        opcode=SPIOpcode.READ_DATA,
        opcode_name="Read Data (0x03)",
        start_time=0.001,
        end_time=0.002,
        duration_us=1000.0,
        mosi_bytes=[0x03, 0x00, 0x00, 0x00, 0x00],
        miso_bytes=[0x00, 0x00, 0x00, 0x00, 0xAA],
    )
    report = SPIReport(summary=SPIReportSummary(total_transactions=1, read_count=1), transactions=[tx])
    stats = compute_spi_statistics(report)

    assert stats.command_distribution == {"Read Data (0x03)": 1}
    assert stats.total_bytes_transferred == 5
    assert stats.busy_poll_count == 0
    assert stats.avg_command_latency_us == pytest.approx(1000.0)
    assert stats.throughput_bytes_per_sec == pytest.approx(5 / 0.001)
    assert stats.avg_busy_wait_us is None


def test_mixed_commands_frequency() -> None:
    txs = [
        _make_tx(1, SPIOpcode.WRITE_ENABLE, "Write Enable / WREN (0x06)", start_time=0.0, end_time=0.0001, duration_us=100.0),
        _make_tx(2, SPIOpcode.PAGE_PROGRAM, "Page Program (0x02)", start_time=0.0002, end_time=0.0012, duration_us=1000.0, mosi_bytes=[0x02, 0x00, 0x00, 0x00, 0x11, 0x22]),
        _make_tx(3, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", start_time=0.0013, end_time=0.0014, duration_us=100.0, details={"busy": True}),
        _make_tx(4, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", start_time=0.0015, end_time=0.0016, duration_us=100.0, details={"busy": False}),
        _make_tx(5, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=0.0017, end_time=0.0027, duration_us=1000.0),
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=5), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.command_distribution["Write Enable / WREN (0x06)"] == 1
    assert stats.command_distribution["Page Program (0x02)"] == 1
    assert stats.command_distribution["Read Status Register-1 (0x05)"] == 2
    assert stats.command_distribution["Read Data (0x03)"] == 1
    assert stats.busy_poll_count == 2


def test_throughput_with_timestamps() -> None:
    # Total duration = 0.010 s, total bytes = 100
    tx1 = _make_tx(1, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=0.000, end_time=0.005, duration_us=5000.0, mosi_bytes=[0] * 50)
    tx2 = _make_tx(2, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=0.005, end_time=0.010, duration_us=5000.0, mosi_bytes=[0] * 50)
    report = SPIReport(summary=SPIReportSummary(total_transactions=2), transactions=[tx1, tx2])
    stats = compute_spi_statistics(report)

    assert stats.total_bytes_transferred == 100
    assert stats.throughput_bytes_per_sec == pytest.approx(100 / 0.010)


def test_throughput_without_timestamps() -> None:
    tx1 = _make_tx(1, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=0.0, end_time=0.0, duration_us=0.0, mosi_bytes=[0x03, 0x00])
    tx2 = _make_tx(2, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=0.0, end_time=0.0, duration_us=0.0, mosi_bytes=[0x03, 0x00])
    report = SPIReport(summary=SPIReportSummary(total_transactions=2), transactions=[tx1, tx2])
    stats = compute_spi_statistics(report)

    assert stats.total_bytes_transferred == 4
    assert stats.throughput_bytes_per_sec is None
    assert stats.avg_command_latency_us is None


def test_busy_poll_count() -> None:
    txs = [
        _make_tx(1, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", details={"busy": True}),
        _make_tx(2, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", details={"busy": True}),
        _make_tx(3, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", details={"busy": False}),
        _make_tx(4, SPIOpcode.READ_STATUS_REG_2, "Read Status Register-2 (0x35)"),
        _make_tx(5, SPIOpcode.READ_DATA, "Read Data (0x03)"),
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=5), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.busy_poll_count == 4


def test_avg_busy_wait_with_program() -> None:
    # Page Program ends at t=0.001000 s
    # RDSR 1 (busy=1) at t=0.001100 .. 0.001200
    # RDSR 2 (busy=0) at t=0.001300 .. 0.001400 s
    # Wait time = (0.001400 - 0.001000) * 1e6 = 400.0 µs
    txs = [
        _make_tx(1, SPIOpcode.PAGE_PROGRAM, "Page Program (0x02)", start_time=0.0005, end_time=0.0010, duration_us=500.0),
        _make_tx(2, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", start_time=0.0011, end_time=0.0012, duration_us=100.0, details={"busy": True}),
        _make_tx(3, SPIOpcode.READ_STATUS_REG_1, "Read Status Register-1 (0x05)", start_time=0.0013, end_time=0.0014, duration_us=100.0, details={"busy": False}),
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=3), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.avg_busy_wait_us == pytest.approx(400.0)


def test_avg_command_latency() -> None:
    txs = [
        _make_tx(1, SPIOpcode.READ_DATA, "Read Data (0x03)", duration_us=120.0),
        _make_tx(2, SPIOpcode.FAST_READ, "Fast Read (0x0B)", duration_us=80.0),
        _make_tx(3, SPIOpcode.WRITE_ENABLE, "Write Enable / WREN (0x06)", duration_us=40.0),
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=3), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.avg_command_latency_us == pytest.approx((120.0 + 80.0 + 40.0) / 3)


def test_page_program_stats() -> None:
    txs = [
        _make_tx(1, SPIOpcode.PAGE_PROGRAM, "Page Program (0x02)", duration_us=800.0),
        _make_tx(2, SPIOpcode.QUAD_PAGE_PROGRAM, "Quad Page Program (0x32)", duration_us=600.0),
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=2), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.page_program_stats is not None
    assert stats.page_program_stats.level == EvidenceLevel.MEASURED
    assert stats.page_program_stats.value == pytest.approx(700.0)
    assert stats.page_program_stats.sample_count == 2


def test_edge_case_all_same_command() -> None:
    txs = [
        _make_tx(i, SPIOpcode.READ_DATA, "Read Data (0x03)", start_time=i * 0.001, end_time=i * 0.001 + 0.0005, duration_us=500.0, mosi_bytes=[0x03, 0x00, 0x00, 0x00])
        for i in range(1, 11)
    ]
    report = SPIReport(summary=SPIReportSummary(total_transactions=10), transactions=txs)
    stats = compute_spi_statistics(report)

    assert stats.command_distribution == {"Read Data (0x03)": 10}
    assert stats.total_bytes_transferred == 40
    assert stats.busy_poll_count == 0
    assert stats.avg_busy_wait_us is None
    assert stats.avg_command_latency_us == pytest.approx(500.0)


def test_edge_case_single_command_no_duration() -> None:
    tx = _make_tx(1, SPIOpcode.CHIP_ERASE, "Chip Erase (0xC7)", start_time=0.0, end_time=0.0, duration_us=0.0, mosi_bytes=[0xC7])
    report = SPIReport(summary=SPIReportSummary(total_transactions=1), transactions=[tx])
    stats = compute_spi_statistics(report)

    assert stats.command_distribution == {"Chip Erase (0xC7)": 1}
    assert stats.total_bytes_transferred == 1
    assert stats.throughput_bytes_per_sec is None
    assert stats.avg_command_latency_us is None
    assert stats.busy_poll_count == 0


def test_to_dict_serialization() -> None:
    stats = SPIStatistics(
        command_distribution={"Read Data (0x03)": 5},
        total_bytes_transferred=25,
        throughput_bytes_per_sec=2500.0,
        avg_command_latency_us=50.0,
        busy_poll_count=0,
        avg_busy_wait_us=None,
    )
    d = stats.to_dict()
    assert d["command_distribution"] == {"Read Data (0x03)": 5}
    assert d["total_bytes_transferred"] == 25
    assert d["throughput_bytes_per_sec"] == 2500.0
    assert d["avg_command_latency_us"] == 50.0
    assert d["busy_poll_count"] == 0
    assert d["avg_busy_wait_us"] is None


def test_frozen_immutability() -> None:
    stats = SPIStatistics(
        command_distribution={},
        total_bytes_transferred=0,
        throughput_bytes_per_sec=None,
        avg_command_latency_us=None,
        busy_poll_count=0,
        avg_busy_wait_us=None,
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        stats.total_bytes_transferred = 100  # type: ignore[misc]
