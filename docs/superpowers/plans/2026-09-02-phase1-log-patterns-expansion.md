# Phase 1: OpenBMC Log Pattern Library Expansion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the system log pattern library from 22 to 35+ patterns, covering OpenBMC application-layer failures (OOM Killer, D-Bus broker saturation, phosphor-hwmon crashes, ipmid timeouts) with precise triage hints and actionable next-step commands.

**Architecture:** Add new `LogPattern` entries to the existing `patterns.py` library, add new `Subsystem.DBUS` and `Subsystem.MEMORY` enum members to `models.py`, update the `_RELATED_TOOL_PAGES` map in `parser.py`, and write tests that exercise each new pattern against realistic log lines.

**Tech Stack:** Python 3.10+, dataclasses, re (regex), pytest

**Spec:** This plan is self-contained; no separate spec doc. The design was approved during brainstorming on 2026-09-02.

## Global Constraints

- Python >= 3.10 (use `from __future__ import annotations`)
- All imports use existing project conventions (no new dependencies)
- Pattern IDs use SCREAMING_SNAKE_CASE (e.g. `OOM_KILLER_INVOKED`)
- Each pattern must have: `id`, `subsystem`, `severity`, `regex`, `extract_fields`, `triage_hint`, `description`
- `triage_hint` must include at least one concrete command or file path the engineer can run/check
- Tests must use realistic log line strings, not abstract patterns
- Run `uv run pytest tests/test_log_parser.py tests/test_log_models.py -v` after each task
- Run `uv run ruff check src/fw_diag_tool/log/` after each task
- Run `uv run mypy src/fw_diag_tool/log/` after each task

---

### Task 1: Add DBUS and MEMORY Subsystem Enum Members

**Files:**
- Modify: `src/fw_diag_tool/log/models.py` (the `Subsystem` enum, around line 20)
- Test: `tests/test_log_models.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `Subsystem.DBUS` (value `"dbus"`) and `Subsystem.MEMORY` (value `"memory"`) enum members, used by Task 2's new patterns

- [x] **Step 1: Write the failing test**

Add to `tests/test_log_models.py`:

```python
def test_subsystem_has_dbus_and_memory() -> None:
    """New subsystem enum members for D-Bus and memory/OOM patterns."""
    from fw_diag_tool.log.models import Subsystem

    assert Subsystem.DBUS == "dbus"
    assert Subsystem.DBUS.value == "dbus"
    assert Subsystem.MEMORY == "memory"
    assert Subsystem.MEMORY.value == "memory"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_models.py::test_subsystem_has_dbus_and_memory -v`
Expected: FAIL with `AttributeError: DBUS`

- [x] **Step 3: Add the enum members**

In `src/fw_diag_tool/log/models.py`, inside the `Subsystem` class (after `USB = "usb"` and before `GENERAL = "general"`), add:

```python
    DBUS = "dbus"
    MEMORY = "memory"
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_log_models.py::test_subsystem_has_dbus_and_memory -v`
Expected: PASS

- [x] **Step 5: Run full model tests and linters**

Run: `uv run pytest tests/test_log_models.py -v && uv run ruff check src/fw_diag_tool/log/ && uv run mypy src/fw_diag_tool/log/`
Expected: All pass, no errors

- [x] **Step 6: Commit**

```bash
git add src/fw_diag_tool/log/models.py tests/test_log_models.py
git commit -m "feat(log): add DBUS and MEMORY subsystem enum members"
```

---

### Task 2: Add 13 New OpenBMC-Specific Log Patterns

**Files:**
- Modify: `src/fw_diag_tool/log/patterns.py` (append to `PATTERN_LIBRARY` list)
- Test: `tests/test_log_parser.py`

**Interfaces:**
- Consumes: `Subsystem.DBUS` and `Subsystem.MEMORY` from Task 1; `LogPattern` dataclass, `Severity` enum
- Produces: 13 new `LogPattern` objects in `PATTERN_LIBRARY`, consumed by `LogParser._extract_events()`

Below are all 13 patterns to append to the `PATTERN_LIBRARY` list at the end of `patterns.py`. Add each one inside the existing list.

- [x] **Step 1: Write the failing tests**

Add the following test functions to `tests/test_log_parser.py`. Each test feeds a realistic log line to `LogParser.parse_log_text()` and asserts the expected pattern is matched:

```python
from fw_diag_tool.log.models import Subsystem
from fw_diag_tool.log.parser import LogParser


def test_pattern_oom_killer_invoked() -> None:
    log = "[  120.5] Out of memory: Killed process 1234 (phosphor-hwmon) total-vm:65536kB"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "OOM_KILLER_INVOKED"
    assert report.events[0].subsystem == Subsystem.MEMORY


def test_pattern_oom_cgroup_limit() -> None:
    log = "[  130.0] Memory cgroup out of memory: Killed process 567 (ipmid)"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "OOM_CGROUP_LIMIT"


def test_pattern_dbus_broker_max_bytes() -> None:
    log = "Sep 01 12:00:00 bmc dbus-broker[100]: Listener 0x1a reached max-bytes; dropping message"
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 1
    assert report.events[0].pattern_id == "DBUS_BROKER_MAX_BYTES"
    assert report.events[0].subsystem == Subsystem.DBUS


def test_pattern_dbus_broker_quota_exceeded() -> None:
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_log_parser.py -k "test_pattern_oom or test_pattern_dbus or test_pattern_phosphor or test_pattern_ipmid or test_pattern_systemd_service or test_pattern_journal or test_pattern_kernel_rcu or test_pattern_kernel_soft or test_pattern_mtd or test_pattern_emmc or test_pattern_nfsroot" -v`
Expected: All 13 tests FAIL

- [x] **Step 3: Add all 13 patterns to `patterns.py`**

Append these entries to the `PATTERN_LIBRARY` list in `src/fw_diag_tool/log/patterns.py`, right before the closing `]`. Remember the imports for `Subsystem` are already at the top of `patterns.py`:

```python
    # --- OpenBMC Application-Layer Patterns ---
    LogPattern(
        id="OOM_KILLER_INVOKED",
        subsystem=Subsystem.MEMORY,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"Out of memory:\s*Killed process",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Check RSS of top BMC daemons: busctl tree --no-pager | wc -l and top -b -n1 | head -20. Review cgroup memory limits in /sys/fs/cgroup/.",
        description="Linux OOM Killer terminated a process due to memory exhaustion.",
    ),
    LogPattern(
        id="OOM_CGROUP_LIMIT",
        subsystem=Subsystem.MEMORY,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"Memory cgroup out of memory:\s*Killed process",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="A cgroup memory limit was hit. Run cat /sys/fs/cgroup/memory/*/memory.limit_in_bytes and systemctl status <unit> to find which service exceeded its quota.",
        description="Linux cgroup OOM killed a process that exceeded its memory budget.",
    ),
    LogPattern(
        id="DBUS_BROKER_MAX_BYTES",
        subsystem=Subsystem.DBUS,
        severity=Severity.ERROR,
        regex=re.compile(
            r"dbus-broker.*:\s*(?:reached max-bytes|dropping message|max-bytes limit)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="D-Bus broker is dropping messages. Run busctl --no-pager list to identify saturated connections, then journalctl -u dbus-broker -n 50.",
        description="dbus-broker dropped a message because the listener reached its max-bytes quota.",
    ),
    LogPattern(
        id="DBUS_BROKER_QUOTA",
        subsystem=Subsystem.DBUS,
        severity=Severity.ERROR,
        regex=re.compile(
            r"dbus-broker.*:\s*(?:Peer.*is being disconnected|sent too many messages|exceeded its quota)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="A D-Bus peer flooded the bus and was disconnected. Identify the offending service with busctl monitor and check for hot loops in sensor polling daemons.",
        description="dbus-broker disconnected a peer that exceeded its message quota.",
    ),
    LogPattern(
        id="PHOSPHOR_HWMON_CRASH",
        subsystem=Subsystem.HWMON,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"phosphor-hwmon.*:\s*(?:Caught signal|Segmentation fault|Aborted|core dumped|SIGABRT|SIGSEGV)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "extra"],
        triage_hint="phosphor-hwmon crashed. Check coredump: coredumpctl list and coredumpctl info. Verify hwmon sysfs nodes under /sys/class/hwmon/ are still accessible.",
        description="OpenBMC phosphor-hwmon daemon crashed with a fatal signal.",
    ),
    LogPattern(
        id="IPMID_TIMEOUT",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(
            r"ipmid.*:\s*(?:Timed out|timeout|command timed out|no response from host)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="ipmid timed out. Check host power state: busctl get-property xyz.openbmc_project.State.Host /xyz/openbmc_project/state/host0 xyz.openbmc_project.State.Host CurrentHostState. Verify KCS/BT interface in /dev/.",
        description="OpenBMC ipmid timed out waiting for a host IPMI response.",
    ),
    LogPattern(
        id="SYSTEMD_SERVICE_FAILED",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(
            r"systemd\[\d*\]:\s*\S+\.service:\s*(?:Main process exited.*status=|Failed with result|entered failed state)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="A systemd service failed. Run systemctl status <service> and journalctl -u <service> --no-pager -n 30 to see the root cause.",
        description="A systemd service unit entered a failed state.",
    ),
    LogPattern(
        id="JOURNAL_DISK_FULL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(
            r"systemd-journald.*:\s*(?:Failed to write entry|No space left on device|Vacuuming done|Suppressed .* messages)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Journal cannot write because the filesystem is full. Check df -h /var/log/journal and consider journalctl --vacuum-size=50M.",
        description="systemd-journald failed to persist entries due to disk space exhaustion.",
    ),
    LogPattern(
        id="KERNEL_RCU_STALL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"rcu:.*(?:self-detected stall|rcu_.*stall|detected stalls on CPUs)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Kernel RCU stall: CPU stuck in a non-preemptible section. Check for long interrupt-disabled paths, heavy IRQ load, or an infinite loop in a kernel module.",
        description="Kernel RCU subsystem detected a stall (CPU stuck in a non-preemptible section).",
    ),
    LogPattern(
        id="KERNEL_SOFT_LOCKUP",
        subsystem=Subsystem.WATCHDOG,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:watchdog|kernel):.*(?:BUG: soft lockup|soft lockup - CPU#?\d+ stuck)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="A CPU was stuck in kernel mode without scheduling. Check dmesg for the full stack trace and look for spinlock contention or interrupt storms.",
        description="Kernel soft lockup watchdog fired because a CPU did not schedule for too long.",
    ),
    LogPattern(
        id="MTD_ERASE_FAILURE",
        subsystem=Subsystem.SPI,
        severity=Severity.ERROR,
        regex=re.compile(
            r"mtd\s*mtd\d+:\s*(?:Erase.*failed|erase failed|write.*failed|read.*failed)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="Flash erase/write failed. Check cat /proc/mtd, verify SPI bus connectivity, and inspect flash wear level or write-protect jumper.",
        description="MTD flash erase or write operation failed on an SPI/NOR partition.",
    ),
    LogPattern(
        id="EMMC_IO_ERROR",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(
            r"mmcblk\d+:\s*(?:error|timed out|retrying|I/O error|failed to send)",
            re.IGNORECASE,
        ),
        extract_fields=["errno_code"],
        triage_hint="eMMC I/O error. Check dmesg | grep mmc for voltage/speed negotiation issues. On BMC, verify eMMC health with mmc extcsd read /dev/mmcblk0.",
        description="eMMC block device reported an I/O error or command timeout.",
    ),
    LogPattern(
        id="NFSROOT_MOUNT_FAIL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(
            r"NFS:.*(?:mount.*failed|No route to host|Connection refused|mount request)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="NFS mount failed. Check network connectivity with ping <nfs-server>, verify NFS exports, and confirm firewall rules allow port 2049.",
        description="NFS root or mount operation failed due to network or server unavailability.",
    ),
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_log_parser.py -k "test_pattern_oom or test_pattern_dbus or test_pattern_phosphor or test_pattern_ipmid or test_pattern_systemd_service or test_pattern_journal or test_pattern_kernel_rcu or test_pattern_kernel_soft or test_pattern_mtd or test_pattern_emmc or test_pattern_nfsroot" -v`
Expected: All 13 tests PASS

- [x] **Step 5: Run full test suite and linters**

Run: `uv run pytest tests/test_log_parser.py tests/test_log_models.py tests/test_log_diff.py -v && uv run ruff check src/fw_diag_tool/log/ && uv run mypy src/fw_diag_tool/log/`
Expected: All pass

- [x] **Step 6: Commit**

```bash
git add src/fw_diag_tool/log/patterns.py tests/test_log_parser.py
git commit -m "feat(log): add 13 OpenBMC application-layer log patterns"
```

---

### Task 3: Update parser.py Related Tool Pages Map and Incident Hypothesis Expansion

**Files:**
- Modify: `src/fw_diag_tool/log/parser.py` (the `_RELATED_TOOL_PAGES` dict and `_correlate_incidents` method)
- Test: `tests/test_log_parser.py`

**Interfaces:**
- Consumes: `Subsystem.DBUS`, `Subsystem.MEMORY` from Task 1; new patterns from Task 2
- Produces: Updated `_RELATED_TOOL_PAGES` map with new subsystem entries; enhanced hypothesis strings in incident correlation

- [x] **Step 1: Write the failing tests**

Add to `tests/test_log_parser.py`:

```python
def test_incident_hypothesis_oom_plus_hwmon() -> None:
    """OOM killing phosphor-hwmon should generate a specific hypothesis."""
    log = (
        "[  120.0] Out of memory: Killed process 800 (phosphor-hwmon) total-vm:65536kB\n"
        "[  120.1] phosphor-hwmon[800]: Caught signal 11 (Segmentation fault)\n"
    )
    report = LogParser.parse_log_text(log)
    assert report.summary.total_incidents >= 1
    hypotheses = [inc.root_cause_hypothesis for inc in report.incidents]
    assert any("OOM" in h or "memory" in h.lower() for h in hypotheses)


def test_incident_hypothesis_dbus_saturation() -> None:
    """D-Bus broker saturation should produce a D-Bus related hypothesis."""
    log = (
        "Sep 01 12:00:00 bmc dbus-broker[100]: Listener 0x1a reached max-bytes; dropping message\n"
        "Sep 01 12:00:01 bmc dbus-broker[100]: Peer :1.50 is being disconnected as it sent too many messages\n"
    )
    report = LogParser.parse_log_text(log)
    assert report.summary.total_incidents >= 1
    hypotheses = [inc.root_cause_hypothesis for inc in report.incidents]
    assert any("D-Bus" in h or "dbus" in h.lower() for h in hypotheses)


def test_related_tool_pages_new_subsystems() -> None:
    """New subsystems should have related_tool_page entries."""
    from fw_diag_tool.log.parser import _RELATED_TOOL_PAGES
    from fw_diag_tool.log.models import Subsystem

    assert Subsystem.DBUS in _RELATED_TOOL_PAGES
    assert Subsystem.MEMORY in _RELATED_TOOL_PAGES

---

## Completion Record (2026-09-02)

- Implementation evidence: `fe2b545` adds the DBUS/MEMORY subsystems, 13 OpenBMC patterns, related-page mapping, incident hypotheses, and regression tests; `8f91183` adds the subsequent negative-control hardening.
- Fresh final evidence: `uv run pytest` completed with 1518 passed; `uv run ruff check .`, `uv run mypy src/`, and `uv run mkdocs build --strict` all exited zero.
- Evidence boundary: the red-phase commands listed in the task steps belong to the historical implementation sequence and were not replayed by reverting the committed tree. No live OpenBMC log stream was used in this local acceptance.
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_log_parser.py::test_incident_hypothesis_oom_plus_hwmon tests/test_log_parser.py::test_incident_hypothesis_dbus_saturation tests/test_log_parser.py::test_related_tool_pages_new_subsystems -v`
Expected: FAIL

- [x] **Step 3: Update `parser.py`**

In `src/fw_diag_tool/log/parser.py`:

**3a.** Add to the `_RELATED_TOOL_PAGES` dict (after the existing entries):

```python
    Subsystem.DBUS: "log-analyzer",
    Subsystem.MEMORY: "log-analyzer",
```

**3b.** In the `_correlate_incidents` method, add new hypothesis branches. Find the existing hypothesis chain (the `if/elif` block checking `pattern_ids`). Before the final `else` branch, add:

```python
            elif "OOM_KILLER_INVOKED" in pattern_ids or "OOM_CGROUP_LIMIT" in pattern_ids:
                hypothesis = "OOM Killer terminated a process; memory pressure or cgroup limit exceeded"
            elif "DBUS_BROKER_MAX_BYTES" in pattern_ids or "DBUS_BROKER_QUOTA" in pattern_ids:
                hypothesis = "D-Bus broker message saturation; a daemon is flooding the system bus"
            elif "KERNEL_RCU_STALL" in pattern_ids or "KERNEL_SOFT_LOCKUP" in pattern_ids:
                hypothesis = "Kernel scheduling stall; CPU stuck in non-preemptible context"
            elif "SYSTEMD_SERVICE_FAILED" in pattern_ids:
                hypothesis = "One or more systemd services entered a failed state"
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_log_parser.py::test_incident_hypothesis_oom_plus_hwmon tests/test_log_parser.py::test_incident_hypothesis_dbus_saturation tests/test_log_parser.py::test_related_tool_pages_new_subsystems -v`
Expected: PASS

- [x] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v && uv run ruff check . && uv run mypy src/`
Expected: All pass (1422+ tests)

- [x] **Step 6: Commit**

```bash
git add src/fw_diag_tool/log/parser.py tests/test_log_parser.py
git commit -m "feat(log): expand incident hypotheses and related tool pages for new subsystems"
```
