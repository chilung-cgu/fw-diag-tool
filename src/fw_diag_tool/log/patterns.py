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
]
