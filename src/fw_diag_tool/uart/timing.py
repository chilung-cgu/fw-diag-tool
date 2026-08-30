"""UART Serial Boot & Crash Timing Analysis Module.

Extracts timestamps from dmesg, syslog, ISO-8601, time-of-day, and millisecond
formats to compute log duration, timestamp coverage, boot phase durations
(bootloader, kernel, userspace), and crash-to-reset intervals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from fw_diag_tool.uart.models import CrashType, UARTReport

_BOOTLOADER_KEYWORDS = (
    "u-boot",
    "spl:",
    "bootrom",
    "tf-a",
    "bl1:",
    "bl2:",
    "bl31:",
    "bl33:",
    "uefi",
    "coreboot",
    "hit any key to stop autoboot",
    "starting kernel",
    "booting linux",
    "loading kernel",
    "dram:",
    "nand:",
    "mmc:",
)

_KERNEL_KEYWORDS = (
    "linux version",
    "booting linux on physical cpu",
    "kernel command line:",
    "calibrating delay loop",
    "printk:",
    "devtmpfs: mounted",
    "initcall",
    "freeing unused kernel memory",
    "kernel panic",
    "oops:",
    "bug: unable to handle",
    "unable to handle kernel",
    "internal error:",
    "synchronous external abort",
    "call trace:",
    "hardfault",
)

_USERSPACE_KEYWORDS = (
    "run /init as init process",
    "starting init:",
    "init started:",
    "systemd[1]:",
    "systemd 2",
    "welcome to",
    "login:",
    "reached target basic system",
    "reached target multi-user system",
    "starting system message bus",
    "starting openssh",
    "rc.local",
    "/etc/rc",
)

_CRASH_KEYWORDS = (
    "kernel panic",
    "bug: unable to handle",
    "oops:",
    "hardfault",
    "watchdog timeout",
    "watchdog reset",
    "internal error:",
    "unable to handle kernel",
    "synchronous external abort",
    "fatal exception",
    "wdt timeout",
)

_RESET_KEYWORDS = (
    "restarting system",
    "machine restart",
    "system reset",
    "resetting cpu",
    "watchdog reset",
    "emergency sync",
    "reboot: restarting system",
    "rebooting...",
    "powering off",
)


@dataclass(frozen=True)
class UARTTimingAnalysis:
    boot_phase_durations: dict[str, float | None]
    crash_to_reset_interval_s: float | None
    total_log_duration_s: float | None
    line_count: int
    timestamp_coverage: float


def _parse_line_timestamp(line: str) -> float | None:
    """Extract timestamp in seconds from a single log line."""
    # 1. dmesg relative seconds [   1.234567] or [12.345678] or [ 0.000000 ]
    m_dmesg = re.search(r"\[\s*(\d+(?:\.\d+)?)\s*\]", line)
    if m_dmesg:
        val = m_dmesg.group(1)
        if "." in val or re.match(r"^\s*\[\s*\d+\s*\]", line):
            try:
                return float(val)
            except ValueError:
                pass

    # 2. Milliseconds format [ 1234 ms ] or [1234ms]
    m_ms = re.search(r"\[\s*(\d+(?:\.\d+)?)\s*ms\s*\]", line, re.IGNORECASE)
    if m_ms:
        try:
            return float(m_ms.group(1)) / 1000.0
        except ValueError:
            pass

    # 3. ISO timestamp [2026-08-30 12:00:00.123] or 2026-08-30T12:00:00.123456Z
    m_iso = re.search(
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z)?)", line
    )
    if m_iso:
        try:
            dt_str = m_iso.group(1).replace("Z", "").replace(" ", "T")
            dt = datetime.fromisoformat(dt_str)
            return dt.timestamp()
        except ValueError:
            pass

    # 4. Syslog format [Jan  1 12:00:00] or Jan  1 12:00:00.123
    m_syslog = re.search(
        r"(?:^|\[\s*)([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
        line,
    )
    if m_syslog:
        try:
            ts_str = m_syslog.group(1)
            fmt = "%b %d %H:%M:%S.%f" if "." in ts_str else "%b %d %H:%M:%S"
            dt = datetime.strptime(f"{ts_str} +0000", f"{fmt} %z")
            dt = dt.replace(year=2026)
            return dt.timestamp()
        except ValueError:
            pass

    # 5. Time-of-day [12:00:00.123] or [12:00:00]
    m_tod = re.search(r"\[\s*(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*\]", line)
    if m_tod:
        parts = m_tod.group(1).split(":")
        try:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except (ValueError, IndexError):
            pass

    return None


def analyze_uart_timing(report: UARTReport, raw_text: str) -> UARTTimingAnalysis:
    """Analyze timing information from raw UART serial / crash log text."""
    lines = raw_text.splitlines()
    line_count = len(lines)

    if line_count == 0:
        return UARTTimingAnalysis(
            boot_phase_durations={
                "bootloader": None,
                "kernel": None,
                "userspace": None,
            },
            crash_to_reset_interval_s=None,
            total_log_duration_s=None,
            line_count=0,
            timestamp_coverage=0.0,
        )

    parsed_lines: list[tuple[int, float, str]] = []
    for idx, line in enumerate(lines):
        ts = _parse_line_timestamp(line)
        if ts is not None:
            parsed_lines.append((idx, ts, line))

    timestamp_coverage = round(len(parsed_lines) / line_count, 4)

    if len(parsed_lines) >= 2:
        total_duration = round(parsed_lines[-1][1] - parsed_lines[0][1], 6)
        if total_duration < 0:
            total_duration = round(
                max(ts for _, ts, _ in parsed_lines)
                - min(ts for _, ts, _ in parsed_lines),
                6,
            )
    elif len(parsed_lines) == 1:
        total_duration = 0.0
    else:
        total_duration = None

    # Boot phase detection
    bootloader_timestamps: list[float] = []
    kernel_timestamps: list[float] = []
    userspace_timestamps: list[float] = []

    # Classify timestamped lines by keywords
    for _, ts, text in parsed_lines:
        t_low = text.lower()
        if any(kw in t_low for kw in _USERSPACE_KEYWORDS):
            userspace_timestamps.append(ts)
        elif any(kw in t_low for kw in _BOOTLOADER_KEYWORDS):
            bootloader_timestamps.append(ts)
        elif any(kw in t_low for kw in _KERNEL_KEYWORDS):
            kernel_timestamps.append(ts)

    # Phase durations
    bootloader_dur: float | None = None
    kernel_dur: float | None = None
    userspace_dur: float | None = None

    # Determine phase boundaries
    if bootloader_timestamps:
        t_bl_start = bootloader_timestamps[0]
        if kernel_timestamps and kernel_timestamps[0] >= t_bl_start:
            bootloader_dur = round(kernel_timestamps[0] - t_bl_start, 6)
        elif len(bootloader_timestamps) >= 2:
            bootloader_dur = round(
                bootloader_timestamps[-1] - bootloader_timestamps[0], 6
            )
        else:
            bootloader_dur = 0.0

    if kernel_timestamps:
        t_k_start = kernel_timestamps[0]
        if userspace_timestamps and userspace_timestamps[0] >= t_k_start:
            kernel_dur = round(userspace_timestamps[0] - t_k_start, 6)
        elif len(kernel_timestamps) >= 2:
            kernel_dur = round(kernel_timestamps[-1] - kernel_timestamps[0], 6)
        else:
            kernel_dur = 0.0
    elif report.kernel_panic is not None and len(parsed_lines) >= 2:
        kernel_dur = round(parsed_lines[-1][1] - parsed_lines[0][1], 6)

    if userspace_timestamps:
        t_u_start = userspace_timestamps[0]
        t_last = parsed_lines[-1][1]
        if t_last >= t_u_start:
            userspace_dur = round(t_last - t_u_start, 6)
        elif len(userspace_timestamps) >= 2:
            userspace_dur = round(
                userspace_timestamps[-1] - userspace_timestamps[0], 6
            )
        else:
            userspace_dur = 0.0

    boot_phase_durations: dict[str, float | None] = {
        "bootloader": bootloader_dur,
        "kernel": kernel_dur,
        "userspace": userspace_dur,
    }

    # Crash-to-reset interval
    crash_to_reset_interval: float | None = None
    is_crash = (
        report.crash_type
        in (
            CrashType.KERNEL_PANIC,
            CrashType.ARM_HARDFAULT,
            CrashType.WATCHDOG_RESET,
        )
        or any(
            any(kw in line.lower() for kw in _CRASH_KEYWORDS) for line in lines
        )
    )

    if is_crash and parsed_lines:
        crash_ts: float | None = None
        crash_line_idx: int = -1

        for idx, ts, text in parsed_lines:
            t_low = text.lower()
            if any(kw in t_low for kw in _CRASH_KEYWORDS):
                crash_ts = ts
                crash_line_idx = idx
                break

        # Fallback: find line index in raw lines if timestamp wasn't directly on crash line
        if crash_ts is None:
            for idx, line in enumerate(lines):
                if any(kw in line.lower() for kw in _CRASH_KEYWORDS):
                    crash_line_idx = idx
                    break
            if crash_line_idx >= 0:
                for idx, ts, _ in parsed_lines:
                    if idx >= crash_line_idx:
                        crash_ts = ts
                        break
                if crash_ts is None:
                    crash_ts = parsed_lines[0][1]

        if crash_ts is not None and crash_line_idx >= 0:
            for idx, ts, text in parsed_lines:
                if idx > crash_line_idx:
                    t_low = text.lower()
                    if any(kw in t_low for kw in _RESET_KEYWORDS) and ts >= crash_ts:
                        crash_to_reset_interval = round(ts - crash_ts, 6)
                        break

    return UARTTimingAnalysis(
        boot_phase_durations=boot_phase_durations,
        crash_to_reset_interval_s=crash_to_reset_interval,
        total_log_duration_s=total_duration,
        line_count=line_count,
        timestamp_coverage=timestamp_coverage,
    )
