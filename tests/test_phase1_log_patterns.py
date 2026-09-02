"""Tests for Phase 1: expanded OpenBMC log patterns."""
from __future__ import annotations

import pytest

from fw_diag_tool.log.models import Subsystem
from fw_diag_tool.log.parser import LogParser


def test_pattern_oom_killer() -> None:
    log = "[  120.5] Out of memory: Killed process 1234 (phosphor-hwmon) total-vm:65536kB"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "OOM_KILLER_INVOKED"
    assert report.events[0].subsystem == Subsystem.MEMORY


def test_pattern_oom_cgroup() -> None:
    log = "[  130.0] Memory cgroup out of memory: Killed process 567 (ipmid)"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "OOM_CGROUP_LIMIT"


def test_pattern_dbus_max_bytes() -> None:
    log = "Sep 01 12:00:00 bmc dbus-broker[100]: Listener 0x1a reached max-bytes; dropping message"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "DBUS_BROKER_MAX_BYTES"
    assert report.events[0].subsystem == Subsystem.DBUS


def test_pattern_dbus_quota() -> None:
    log = "Sep 01 12:00:01 bmc dbus-broker[100]: Peer :1.50 is being disconnected as it sent too many messages"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "DBUS_BROKER_QUOTA"


def test_pattern_phosphor_hwmon_crash() -> None:
    log = "[  200.0] phosphor-hwmon[800]: Caught signal 11 (Segmentation fault)"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "PHOSPHOR_HWMON_CRASH"


def test_pattern_ipmid_timeout() -> None:
    log = "Sep 02 01:00:00 bmc ipmid[200]: Timed out waiting for response from host"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "IPMID_TIMEOUT"


def test_pattern_systemd_service_failed() -> None:
    log = "Sep 02 01:00:01 bmc systemd[1]: xyz.openbmc_project.psusensor.service: Main process exited, code=exited, status=1/FAILURE"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "SYSTEMD_SERVICE_FAILED"


def test_pattern_journal_disk_full() -> None:
    log = "Sep 02 02:00:00 bmc systemd-journald[50]: Failed to write entry (28 items, 920 bytes), ignoring: No space left on device"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "JOURNAL_DISK_FULL"


def test_pattern_kernel_rcu_stall() -> None:
    log = "[  300.0] rcu: INFO: rcu_preempt self-detected stall on CPU"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "KERNEL_RCU_STALL"


def test_pattern_kernel_soft_lockup() -> None:
    log = "[  400.0] watchdog: BUG: soft lockup - CPU#0 stuck for 22s! [kworker/0:1:42]"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "KERNEL_SOFT_LOCKUP"


def test_pattern_mtd_erase_failure() -> None:
    log = "[  500.0] mtd mtd5: Erase of region [0x000000, 0x010000] failed"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "MTD_ERASE_FAILURE"


def test_pattern_emmc_io_error() -> None:
    log = "[  600.0] mmcblk0: error -110 sending status command, retrying"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "EMMC_IO_ERROR"


def test_pattern_nfsroot_mount_fail() -> None:
    log = "[  700.0] NFS: nfs_mount_common: mount request: No route to host"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "NFSROOT_MOUNT_FAIL"


@pytest.mark.parametrize(
    "log",
    [
        "Sep 02 01:00:00 bmc ipmid[200]: Host command timeout configured to 30 seconds",
        "Sep 02 01:00:01 bmc systemd[1]: demo.service: Main process exited, code=exited, status=0/SUCCESS",
        "Sep 02 02:00:00 bmc systemd-journald[50]: Vacuuming done, freed 16.0M of archived journals",
        "Sep 02 02:00:01 bmc systemd-journald[50]: Suppressed 12 messages from demo.service",
        "[ 600.0] mmcblk0: retrying command after retune",
        "[ 700.0] NFS: sending mount request for 192.0.2.10:/srv/root",
    ],
)
def test_expanded_patterns_ignore_normal_status_lines(log: str) -> None:
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 0


def test_incident_hypothesis_oom() -> None:
    log = "[  120.0] Out of memory: Killed process 800 (phosphor-hwmon) total-vm:65536kB\n[  120.1] phosphor-hwmon[800]: Caught signal 11 (Segmentation fault)\n"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_incidents >= 1
    hypotheses = [inc.root_cause_hypothesis for inc in report.incidents]
    assert any("OOM" in h or "memory" in h.lower() for h in hypotheses)


def test_incident_hypothesis_dbus() -> None:
    log = "Sep 01 12:00:00 bmc dbus-broker[100]: Listener 0x1a reached max-bytes; dropping message\nSep 01 12:00:01 bmc dbus-broker[100]: Peer :1.50 is being disconnected as it sent too many messages\n"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_incidents >= 1
    hypotheses = [inc.root_cause_hypothesis for inc in report.incidents]
    assert any("D-Bus" in h or "dbus" in h.lower() for h in hypotheses)


def test_related_tool_pages_new_subsystems() -> None:
    from fw_diag_tool.log.parser import _RELATED_TOOL_PAGES
    assert Subsystem.DBUS in _RELATED_TOOL_PAGES
    assert Subsystem.MEMORY in _RELATED_TOOL_PAGES
