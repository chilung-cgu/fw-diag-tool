from __future__ import annotations

from dataclasses import FrozenInstanceError
from io import StringIO

import pytest
from rich.console import Console

from fw_diag_tool.uart.models import CrashType, UARTReport
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter
from fw_diag_tool.uart.timing import UARTTimingAnalysis, analyze_uart_timing


def test_empty_log_timing():
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="Empty Log",
        raw_log_lines=0,
    )
    timing = analyze_uart_timing(report, "")
    assert timing.line_count == 0
    assert timing.timestamp_coverage == 0.0
    assert timing.total_log_duration_s is None
    assert timing.crash_to_reset_interval_s is None
    assert timing.boot_phase_durations == {
        "bootloader": None,
        "kernel": None,
        "userspace": None,
    }


def test_no_timestamps_timing():
    raw_text = "Booting device...\nInitializing hardware...\nSystem ready.\n"
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 3
    assert timing.timestamp_coverage == 0.0
    assert timing.total_log_duration_s is None
    assert timing.crash_to_reset_interval_s is None
    assert timing.boot_phase_durations["bootloader"] is None
    assert timing.boot_phase_durations["kernel"] is None
    assert timing.boot_phase_durations["userspace"] is None


def test_dmesg_timestamps():
    raw_text = (
        "[    0.000000] Linux version 6.6.0-generic\n"
        "[    1.234567] devtmpfs: mounted\n"
        "[    4.567890] Freeing unused kernel memory\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 3
    assert timing.timestamp_coverage == 1.0
    assert timing.total_log_duration_s == pytest.approx(4.56789, abs=1e-4)
    assert timing.boot_phase_durations["kernel"] == pytest.approx(4.56789, abs=1e-4)


def test_single_timestamp_line():
    raw_text = "[    1.500000] Single log event\n"
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 1
    assert timing.timestamp_coverage == 1.0
    assert timing.total_log_duration_s == 0.0


def test_boot_phase_detection_full():
    raw_text = (
        "[ 0.100000] U-Boot 2024.01 (Jan 01 2024)\n"
        "[ 0.500000] DRAM: 1 GiB\n"
        "[ 0.900000] Starting kernel ...\n"
        "[ 1.000000] Linux version 6.6.0\n"
        "[ 2.500000] devtmpfs: mounted\n"
        "[ 4.000000] systemd[1]: Reached target Basic System\n"
        "[ 6.500000] login:\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 7
    assert timing.timestamp_coverage == 1.0
    assert timing.total_log_duration_s == pytest.approx(6.4, abs=1e-4)

    durations = timing.boot_phase_durations
    assert durations["bootloader"] == pytest.approx(0.9, abs=1e-4)  # 1.0 - 0.1
    assert durations["kernel"] == pytest.approx(3.0, abs=1e-4)      # 4.0 - 1.0
    assert durations["userspace"] == pytest.approx(2.5, abs=1e-4)   # 6.5 - 4.0


def test_boot_phase_detection_kernel_only():
    raw_text = (
        "[ 0.000000] Linux version 6.6.0\n"
        "[ 1.200000] Calibrating delay loop...\n"
        "[ 2.800000] Freeing unused kernel memory\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.boot_phase_durations["bootloader"] is None
    assert timing.boot_phase_durations["kernel"] == pytest.approx(2.8, abs=1e-4)
    assert timing.boot_phase_durations["userspace"] is None


def test_boot_phase_detection_kernel_and_userspace():
    raw_text = (
        "[ 0.000000] Linux version 6.6.0\n"
        "[ 2.000000] Freeing unused kernel memory\n"
        "[ 3.000000] Run /init as init process\n"
        "[ 7.000000] login:\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.boot_phase_durations["bootloader"] is None
    assert timing.boot_phase_durations["kernel"] == pytest.approx(3.0, abs=1e-4)
    assert timing.boot_phase_durations["userspace"] == pytest.approx(4.0, abs=1e-4)


def test_crash_to_reset_interval_kernel_panic():
    raw_text = (
        "[ 10.000000] BUG: unable to handle page fault for address: 0000000000000010\n"
        "[ 10.000100] RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\n"
        "[ 10.000200] Kernel panic - not syncing: Fatal exception\n"
        "[ 15.000000] Rebooting in 5 seconds..\n"
        "[ 20.000000] Restarting system\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.crash_to_reset_interval_s == pytest.approx(10.0, abs=1e-4)


def test_crash_to_reset_interval_hardfault():
    raw_text = (
        "[ 00:00:01.000 ] System initialized\n"
        "[ 00:00:03.500 ] HardFault Exception Occurred!\n"
        "HFSR: 0x40000000\n"
        "CFSR: 0x02000000\n"
        "[ 00:00:06.000 ] System reset\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.crash_to_reset_interval_s == pytest.approx(2.5, abs=1e-4)


def test_crash_without_reset():
    raw_text = (
        "[ 10.000000] Kernel panic - not syncing: Fatal exception\n"
        "[ 10.000100] Call Trace:\n"
        "[ 10.000200]  nvme_poll+0x44/0x180\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.crash_to_reset_interval_s is None


def test_mixed_timestamp_formats():
    raw_text = (
        "[ 1000 ms ] System startup\n"
        "[Jan  1 00:00:05] Service init\n"
        "[2026-08-30 12:00:10] Sensor ready\n"
        "[12:00:15.500] Operational\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 4
    assert timing.timestamp_coverage == 1.0
    assert timing.total_log_duration_s is not None


def test_timestamp_coverage_calculation():
    lines = [
        "[ 1.0 ] line 1",
        "line without timestamp 2",
        "[ 2.0 ] line 3",
        "line without timestamp 4",
        "line without timestamp 5",
        "[ 3.0 ] line 6",
        "line without timestamp 7",
        "line without timestamp 8",
        "[ 4.0 ] line 9",
        "line without timestamp 10",
    ]
    raw_text = "\n".join(lines)
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    assert timing.line_count == 10
    assert timing.timestamp_coverage == pytest.approx(0.4, abs=1e-4)


def test_reporter_markdown_integration_with_timing():
    raw_text = (
        "[ 0.000000] Linux version 6.6.0\n"
        "[ 1.000000] BUG: unable to handle page fault for address: 0000000000000010\n"
        "[ 1.000100] RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\n"
        "[ 3.000000] Restarting system\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    md = UARTReporter.to_markdown(report, timing=timing)

    assert "## UART 時序分析" in md
    assert "**總記錄時間（Total Log Duration）**" in md
    assert "**時間戳覆蓋率（Timestamp Coverage）**" in md
    assert "**開機階段耗時（Boot Phase Durations）**" in md
    assert "**崩潰至重置間隔（Crash-to-Reset Interval）**" in md
    assert "3.000 秒" in md


def test_reporter_terminal_integration_with_timing():
    raw_text = (
        "[ 0.000000] Linux version 6.6.0\n"
        "[ 1.000000] BUG: unable to handle page fault for address: 0000000000000010\n"
        "[ 1.000100] RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\n"
    )
    report = UARTCrashParser.parse_log_text(raw_text)
    timing = analyze_uart_timing(report, raw_text)
    buf = StringIO()
    UARTReporter.render_terminal(report, console=Console(file=buf), timing=timing)
    output = buf.getvalue()
    assert "UART 時序分析摘要" in output
    assert "總記錄時間" in output
    assert "時間戳覆蓋率" in output


def test_frozen_dataclass_immutability():
    timing = UARTTimingAnalysis(
        boot_phase_durations={"bootloader": None, "kernel": None, "userspace": None},
        crash_to_reset_interval_s=None,
        total_log_duration_s=None,
        line_count=0,
        timestamp_coverage=0.0,
    )
    with pytest.raises(FrozenInstanceError):
        timing.line_count = 10  # type: ignore[misc]
