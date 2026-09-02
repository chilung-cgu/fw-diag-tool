"""Pattern library and regex definitions for system log parsing and diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.log.models import Subsystem


@dataclass(frozen=True)
class LogPattern:
    """Rule mapping log signatures to structured subsystem events."""

    id: str
    subsystem: Subsystem
    severity: Severity
    regex: re.Pattern[str]
    extract_fields: list[str] = field(default_factory=list)
    triage_hint: str = ""
    description: str = ""


PATTERN_LIBRARY: list[LogPattern] = [
    LogPattern(
        id="I2C_DW_TX_ABORT",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=re.compile(
            r"i2c_dw_handle_tx_abort|i2c_designware.*:\s*(?:tx abort|abort)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "extra"],
        triage_hint="Check slave responsiveness, NACK on address/data, or bus arbitration loss",
        description="DesignWare I2C controller reported a TX abort condition.",
    ),
    LogPattern(
        id="I2C_TRANSFER_TIMEOUT",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=re.compile(
            r"i2c.*:\s*(?:controller timed out|transfer timed out|timeout waiting for bus|timeout waiting for|timeout)",
            re.IGNORECASE,
        ),
        extract_fields=["bus", "errno_code"],
        triage_hint="Check SCL/SDA bus pull-up voltage, power rail, or slave clock stretching",
        description="I2C transaction timed out waiting for bus or hardware completion.",
    ),
    LogPattern(
        id="I2C_SLAVE_ENXIO",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        regex=re.compile(
            r"i2c.*:\s*.*(?:No such device or address|-ENXIO|nack from subdevice)",
            re.IGNORECASE,
        ),
        extract_fields=["bus", "address", "errno_code"],
        triage_hint="Device at target address did not acknowledge (NACK). Check device power, address jumper, or mux channel.",
        description="I2C slave address was not acknowledged (-ENXIO / NACK).",
    ),
    LogPattern(
        id="I2C_BUS_RECOVERY",
        subsystem=Subsystem.I2C,
        severity=Severity.WARNING,
        regex=re.compile(
            r"i2c.*:\s*.*(?:bus recovery|recovering bus|recovery failed)",
            re.IGNORECASE,
        ),
        extract_fields=["bus", "errno_code"],
        triage_hint="I2C bus was stuck (SDA held low) and triggered GPIO clock pulsing recovery.",
        description="Kernel attempted I2C bus recovery due to a stuck bus condition.",
    ),
    LogPattern(
        id="I2C_LOST_ARBITRATION",
        subsystem=Subsystem.I2C,
        severity=Severity.WARNING,
        regex=re.compile(
            r"i2c.*:\s*.*(?:lost arbitration|arbitration lost)",
            re.IGNORECASE,
        ),
        extract_fields=["bus"],
        triage_hint="Multi-master contention detected or electrical noise corrupted SCL/SDA levels.",
        description="I2C master lost arbitration to another master or noise on the bus.",
    ),
    LogPattern(
        id="HWMON_PROBE_FAIL",
        subsystem=Subsystem.HWMON,
        severity=Severity.ERROR,
        regex=re.compile(
            r"(?:hwmon|pmbus|tmp\d+|adm\d+|max\d+|lm\d+|ina\d+|tps\d+|nct\d+).*: probe of .* failed with error (-?\d+)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="Check I2C communication to the sensor chip, device tree configuration, and sensor power rails.",
        description="Hardware monitoring / sensor driver probe failed during device binding.",
    ),
    LogPattern(
        id="HWMON_READ_FAIL",
        subsystem=Subsystem.HWMON,
        severity=Severity.WARNING,
        regex=re.compile(
            r"hwmon.*:\s*(?:Failed to read|error reading sensor|read error)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="Sensor read failed over I2C/SMBus/PMBus. Verify bus traffic integrity.",
        description="Hwmon subsystem encountered an error reading sensor attributes.",
    ),
    LogPattern(
        id="PCIE_AER_ERROR",
        subsystem=Subsystem.PCIE,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:pcieport|pci|aer).*:.*AER:\s*(?:Correctable|Uncorrectable|Multiple)\s*error received",
            re.IGNORECASE,
        ),
        extract_fields=["bdf", "severity"],
        triage_hint="Inspect PCIe lane signal integrity, RefClk jitter, and AER status registers.",
        description="PCIe Advanced Error Reporting (AER) captured link or protocol anomaly.",
    ),
    LogPattern(
        id="PCIE_LINK_DOWN",
        subsystem=Subsystem.PCIE,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"pcieport.*:\s*(?:.*Link Down|link down|Data Link Layer Link Degraded)",
            re.IGNORECASE,
        ),
        extract_fields=["bdf"],
        triage_hint="PCIe link dropped. Check slot power, clock, PERST# signal, or endpoint crash.",
        description="PCIe physical or data link state transitioned to down.",
    ),
    LogPattern(
        id="PCIE_BUS_ERROR",
        subsystem=Subsystem.PCIE,
        severity=Severity.ERROR,
        regex=re.compile(
            r"pcieport.*:\s*PCIe Bus Error:\s*severity=",
            re.IGNORECASE,
        ),
        extract_fields=["bdf", "severity"],
        triage_hint="Check PCIe TLP packet integrity, bad DLLP counters, and transmitter eye.",
        description="PCIe bus error reported by root port or bridge.",
    ),
    LogPattern(
        id="THERMAL_ZONE_TRIP",
        subsystem=Subsystem.THERMAL,
        severity=Severity.WARNING,
        regex=re.compile(
            r"thermal thermal_zone\d+:\s*(?:critical temperature|trip point \d+ reached|temperature \d+ reaches threshold)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Thermal threshold exceeded. Inspect fan curves, heatsink contact, and ambient temperature.",
        description="Thermal zone tripped an alert or critical temperature limit.",
    ),
    LogPattern(
        id="THERMAL_CRITICAL",
        subsystem=Subsystem.THERMAL,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:thermal|cpu|coretemp).*:.*(?:critical thermal condition|shutting down due to thermal|throttling active)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Emergency thermal condition active. Verify thermal throttling response and emergency shutdown.",
        description="System reached critical thermal condition requiring aggressive throttling or shutdown.",
    ),
    LogPattern(
        id="POWER_SUPPLY_FAULT",
        subsystem=Subsystem.POWER,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:power_supply|pmbus|psu).*:.*(?:fault detected|power supply failure|voltage out of range|power good lost)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "extra"],
        triage_hint="PSU / VRM reported fault status. Check PMBus STATUS_WORD and input/output rails.",
        description="Power supply or voltage regulator reported hardware fault.",
    ),
    LogPattern(
        id="WATCHDOG_TIMEOUT",
        subsystem=Subsystem.WATCHDOG,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:watchdog|wdt).*:.*(?:watchdog timeout|Watchdog timer expired|ping failed|system reset pending|system will reset)",
            re.IGNORECASE,
        ),
        extract_fields=["driver"],
        triage_hint="System watchdog expired. Identify hung daemon, kernel deadlock, or high-priority loop.",
        description="Hardware or software watchdog timer timed out without kick.",
    ),
    LogPattern(
        id="GPIO_REQUEST_FAIL",
        subsystem=Subsystem.GPIO,
        severity=Severity.ERROR,
        regex=re.compile(
            r"(?:gpio|gpiolib).*:.*(?:failed to request GPIO|cannot get GPIO|error requesting gpio)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="GPIO line contention or invalid pinmux definition in Device Tree.",
        description="Failed to request or configure GPIO line.",
    ),
    LogPattern(
        id="DBUS_SENSOR_UNAVAILABLE",
        subsystem=Subsystem.HWMON,
        severity=Severity.WARNING,
        regex=re.compile(
            r"(?:psusensor|adcsensor|fansensor|hwmontempsensor|nvmesensor).*:.*(?:Sensor .* not available|Failed to read sensor|Device does not exist)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "extra"],
        triage_hint="OpenBMC sensor daemon cannot reach hwmon node. Verify chassis power state and I2C connection.",
        description="OpenBMC dbus-sensor daemon reported sensor unavailable.",
    ),
    LogPattern(
        id="ENTITY_MANAGER_NO_MATCH",
        subsystem=Subsystem.GENERAL,
        severity=Severity.WARNING,
        regex=re.compile(
            r"entity-manager.*:\s*(?:Probe failed|Configuration not found|no matching configuration)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="FruDevice or Entity-Manager probe condition did not match FRU EEPROM or device address.",
        description="OpenBMC Entity-Manager probe failed or found no matching configuration.",
    ),
    LogPattern(
        id="PHOSPHOR_STATE_TRANSITION",
        subsystem=Subsystem.POWER,
        severity=Severity.INFO,
        regex=re.compile(
            r"(?:phosphor-state-manager|xyz\.openbmc_project\.State).*:.*(?:State transition|CurrentPowerState|Chassis power state changed to)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="Normal or fault-driven power state transition in OpenBMC state manager.",
        description="OpenBMC chassis or host power state transition event.",
    ),
    LogPattern(
        id="SPI_NOR_TIMEOUT",
        subsystem=Subsystem.SPI,
        severity=Severity.ERROR,
        regex=re.compile(
            r"(?:spi-nor|spi_nor|m25p80|spi\d+).*:.*(?:timeout waiting for|erase timed out|write timed out|SPI transfer failed)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="SPI flash chip not responding to status poll (WIP bit). Check SPI frequency, flash power, and WP# pin.",
        description="SPI NOR flash memory command or transfer timed out.",
    ),
    LogPattern(
        id="MCTP_ROUTE_FAIL",
        subsystem=Subsystem.MCTP,
        severity=Severity.WARNING,
        regex=re.compile(
            r"(?:mctp|mctpd).*:.*(?:failed to route|no route to|MCTP packet dropped|route error)",
            re.IGNORECASE,
        ),
        extract_fields=["extra"],
        triage_hint="MCTP endpoint unreachable over SMBus/I3C/PCIe VDM. Check endpoint EID assignment.",
        description="MCTP routing failure or packet drop to destination EID.",
    ),
    LogPattern(
        id="USB_DEVICE_OVER_CURRENT",
        subsystem=Subsystem.USB,
        severity=Severity.ERROR,
        regex=re.compile(
            r"usb.*:\s*(?:over-current condition|overcurrent|device not accepting address|unable to enumerate USB device)",
            re.IGNORECASE,
        ),
        extract_fields=["driver", "errno_code"],
        triage_hint="USB port VBUS overcurrent trip or D+/D- signal integrity failure.",
        description="USB host controller reported over-current or enumeration failure.",
    ),
    LogPattern(
        id="MEMORY_ECC_ERROR",
        subsystem=Subsystem.GENERAL,
        severity=Severity.CRITICAL,
        regex=re.compile(
            r"(?:edac|mce|ecc).*:.*(?:ECC error|correctable error|uncorrectable error|Memory Error)",
            re.IGNORECASE,
        ),
        extract_fields=["extra", "severity"],
        triage_hint="DRAM or SRAM ECC error detected. Check DIMM seating, voltage, and SPD configuration.",
        description="Hardware memory ECC or MCE error event reported by EDAC.",
    ),
    # --- OpenBMC Application-Layer Patterns ---
    LogPattern(
        id="OOM_CGROUP_LIMIT",
        subsystem=Subsystem.MEMORY,
        severity=Severity.CRITICAL,
        regex=re.compile(r"Memory cgroup out of memory:\s*Killed process", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="A cgroup memory limit was hit. Run cat /sys/fs/cgroup/memory/*/memory.limit_in_bytes and systemctl status to find which service exceeded its quota.",
        description="Linux cgroup OOM killed a process that exceeded its memory budget.",
    ),
    LogPattern(
        id="OOM_KILLER_INVOKED",
        subsystem=Subsystem.MEMORY,
        severity=Severity.CRITICAL,
        regex=re.compile(r"Out of memory:\s*Killed process", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="Check RSS of top BMC daemons: busctl tree --no-pager | wc -l and top -b -n1 | head -20. Review cgroup memory limits in /sys/fs/cgroup/.",
        description="Linux OOM Killer terminated a process due to memory exhaustion.",
    ),
    LogPattern(
        id="DBUS_BROKER_MAX_BYTES",
        subsystem=Subsystem.DBUS,
        severity=Severity.ERROR,
        regex=re.compile(r"dbus-broker.*:\s*.*(?:reached max-bytes|dropping message|max-bytes limit)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="D-Bus broker is dropping messages. Run busctl --no-pager list to identify saturated connections, then journalctl -u dbus-broker -n 50.",
        description="dbus-broker dropped a message because the listener reached its max-bytes quota.",
    ),
    LogPattern(
        id="DBUS_BROKER_QUOTA",
        subsystem=Subsystem.DBUS,
        severity=Severity.ERROR,
        regex=re.compile(r"dbus-broker.*:\s*(?:Peer.*is being disconnected|sent too many messages|exceeded its quota)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="A D-Bus peer flooded the bus and was disconnected. Identify the offending service with busctl monitor.",
        description="dbus-broker disconnected a peer that exceeded its message quota.",
    ),
    LogPattern(
        id="PHOSPHOR_HWMON_CRASH",
        subsystem=Subsystem.HWMON,
        severity=Severity.CRITICAL,
        regex=re.compile(r"phosphor-hwmon.*:\s*(?:Caught signal|Segmentation fault|Aborted|core dumped|SIGABRT|SIGSEGV)", re.IGNORECASE),
        extract_fields=["driver", "extra"],
        triage_hint="phosphor-hwmon crashed. Check coredump: coredumpctl list and coredumpctl info. Verify hwmon sysfs nodes under /sys/class/hwmon/.",
        description="OpenBMC phosphor-hwmon daemon crashed with a fatal signal.",
    ),
    LogPattern(
        id="IPMID_TIMEOUT",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(r"ipmid.*:\s*(?:Timed out|timeout|command timed out|no response from host)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="ipmid timed out. Check host power state: busctl get-property xyz.openbmc_project.State.Host /xyz/openbmc_project/state/host0 xyz.openbmc_project.State.Host CurrentHostState.",
        description="OpenBMC ipmid timed out waiting for a host IPMI response.",
    ),
    LogPattern(
        id="SYSTEMD_SERVICE_FAILED",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(r"systemd\[\d*\]:\s*\S+\.service:\s*(?:Main process exited.*status=|Failed with result|entered failed state)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="A systemd service failed. Run systemctl status <service> and journalctl -u <service> --no-pager -n 30.",
        description="A systemd service unit entered a failed state.",
    ),
    LogPattern(
        id="JOURNAL_DISK_FULL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(r"systemd-journald.*:\s*(?:Failed to write entry|No space left on device|Vacuuming done|Suppressed .* messages)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="Journal cannot write because the filesystem is full. Check df -h /var/log/journal and consider journalctl --vacuum-size=50M.",
        description="systemd-journald failed to persist entries due to disk space exhaustion.",
    ),
    LogPattern(
        id="KERNEL_RCU_STALL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.CRITICAL,
        regex=re.compile(r"rcu:.*(?:self-detected stall|rcu_.*stall|detected stalls on CPUs)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="Kernel RCU stall: CPU stuck in a non-preemptible section. Check for long interrupt-disabled paths or infinite loops in kernel modules.",
        description="Kernel RCU subsystem detected a stall.",
    ),
    LogPattern(
        id="KERNEL_SOFT_LOCKUP",
        subsystem=Subsystem.WATCHDOG,
        severity=Severity.CRITICAL,
        regex=re.compile(r"(?:watchdog|kernel):.*(?:BUG: soft lockup|soft lockup - CPU#?\d+ stuck)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="A CPU was stuck in kernel mode without scheduling. Check dmesg for the full stack trace and look for spinlock contention.",
        description="Kernel soft lockup watchdog fired.",
    ),
    LogPattern(
        id="MTD_ERASE_FAILURE",
        subsystem=Subsystem.SPI,
        severity=Severity.ERROR,
        regex=re.compile(r"mtd\s*mtd\d+:\s*(?:Erase.*failed|erase failed|write.*failed|read.*failed)", re.IGNORECASE),
        extract_fields=["driver", "errno_code"],
        triage_hint="Flash erase/write failed. Check cat /proc/mtd, verify SPI bus connectivity, and inspect flash wear level or write-protect jumper.",
        description="MTD flash erase or write operation failed.",
    ),
    LogPattern(
        id="EMMC_IO_ERROR",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(r"mmcblk\d+:\s*(?:error|timed out|retrying|I/O error|failed to send)", re.IGNORECASE),
        extract_fields=["errno_code"],
        triage_hint="eMMC I/O error. Check dmesg | grep mmc for voltage/speed negotiation issues.",
        description="eMMC block device reported an I/O error or command timeout.",
    ),
    LogPattern(
        id="NFSROOT_MOUNT_FAIL",
        subsystem=Subsystem.GENERAL,
        severity=Severity.ERROR,
        regex=re.compile(r"NFS:.*(?:mount.*failed|No route to host|Connection refused|mount request)", re.IGNORECASE),
        extract_fields=["extra"],
        triage_hint="NFS mount failed. Check network connectivity with ping <nfs-server>, verify NFS exports, and confirm firewall rules allow port 2049.",
        description="NFS root or mount operation failed.",
    ),
]
