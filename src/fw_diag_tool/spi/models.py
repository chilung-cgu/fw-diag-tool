"""SPI / QSPI Flash Data Models and Diagnostic Dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SPISeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SPIOpcode(int, Enum):
    # Identification
    JEDEC_ID = 0x9F
    DEVICE_ID = 0x90
    UNIQUE_ID = 0x4B
    SFDP = 0x5A

    # Read
    READ_DATA = 0x03
    FAST_READ = 0x0B
    FAST_READ_DUAL_OUT = 0x3B
    FAST_READ_QUAD_OUT = 0x6B

    # Write / Program
    WRITE_ENABLE = 0x06
    WRITE_DISABLE = 0x04
    VOLATILE_SR_WRITE_ENABLE = 0x50
    PAGE_PROGRAM = 0x02
    QUAD_PAGE_PROGRAM = 0x32

    # Erase
    SECTOR_ERASE_4K = 0x20
    BLOCK_ERASE_32K = 0x52
    BLOCK_ERASE_64K = 0xD8
    CHIP_ERASE = 0xC7
    CHIP_ERASE_ALT = 0x60

    # Status / Config Registers
    READ_STATUS_REG_1 = 0x05
    WRITE_STATUS_REG_1 = 0x01
    READ_STATUS_REG_2 = 0x35
    WRITE_STATUS_REG_2 = 0x31
    READ_STATUS_REG_3 = 0x15
    WRITE_STATUS_REG_3 = 0x11

    # Power / Reset
    DEEP_POWER_DOWN = 0xB9
    RELEASE_POWER_DOWN = 0xAB
    ENABLE_RESET = 0x66
    RESET_DEVICE = 0x99


OPCODE_NAMES: dict[int, str] = {
    0x9F: "Read JEDEC ID (0x9F)",
    0x90: "Read Device ID (0x90)",
    0x4B: "Read Unique ID (0x4B)",
    0x5A: "Read SFDP Register (0x5A)",
    0x03: "Read Data (0x03)",
    0x0B: "Fast Read (0x0B)",
    0x3B: "Fast Read Dual Output (0x3B)",
    0x6B: "Fast Read Quad Output (0x6B)",
    0x06: "Write Enable / WREN (0x06)",
    0x04: "Write Disable / WRDI (0x04)",
    0x50: "Volatile SR Write Enable (0x50)",
    0x02: "Page Program (0x02)",
    0x32: "Quad Page Program (0x32)",
    0x20: "Sector Erase 4KB (0x20)",
    0x52: "Block Erase 32KB (0x52)",
    0xD8: "Block Erase 64KB (0xD8)",
    0xC7: "Chip Erase (0xC7)",
    0x60: "Chip Erase Alternate (0x60)",
    0x05: "Read Status Register-1 (0x05)",
    0x01: "Write Status Register-1 (0x01)",
    0x35: "Read Status Register-2 (0x35)",
    0x31: "Write Status Register-2 (0x31)",
    0x15: "Read Status Register-3 (0x15)",
    0x11: "Write Status Register-3 (0x11)",
    0xB9: "Deep Power-Down (0xB9)",
    0xAB: "Release Deep Power-Down (0xAB)",
    0x66: "Enable Reset (0x66)",
    0x99: "Reset Device (0x99)",
}


@dataclass
class FlashStatusRegister1:
    raw_val: int
    busy: bool  # Bit 0: 1 = Erase/Write in progress
    wel: bool  # Bit 1: 1 = Write Enable Latch set
    bp0: bool  # Bit 2: Block Protect 0
    bp1: bool  # Bit 3: Block Protect 1
    bp2: bool  # Bit 4: Block Protect 2
    tb: bool  # Bit 5: Top/Bottom Protect
    sec: bool  # Bit 6: Sector/Block Protect
    srp0: bool  # Bit 7: Status Register Protect 0

    @classmethod
    def decode(cls, val: int) -> FlashStatusRegister1:
        return cls(
            raw_val=val,
            busy=bool(val & (1 << 0)),
            wel=bool(val & (1 << 1)),
            bp0=bool(val & (1 << 2)),
            bp1=bool(val & (1 << 3)),
            bp2=bool(val & (1 << 4)),
            tb=bool(val & (1 << 5)),
            sec=bool(val & (1 << 6)),
            srp0=bool(val & (1 << 7)),
        )


@dataclass
class SPITransaction:
    index: int
    start_time: float
    end_time: float
    duration_us: float
    mosi_bytes: list[int]
    miso_bytes: list[int]
    opcode: int | None = None
    opcode_name: str = "Unknown Opcode"
    address: int | None = None
    data_payload_len: int = 0
    decoded_details: dict[str, Any] = field(default_factory=dict)
    wel_state_before: bool | None = None
    busy_state_after: bool | None = None


@dataclass
class SPIDiagnosticIssue:
    code: str
    title: str
    severity: SPISeverity
    timestamp: float
    transaction_id: int
    description: str
    root_cause_guide: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SPIReportSummary:
    total_transactions: int = 0
    read_count: int = 0
    write_count: int = 0
    erase_count: int = 0
    status_poll_count: int = 0
    anomaly_count: int = 0
    detected_flash_chip: str | None = None


@dataclass
class SPIDataQualityIssue:
    code: str
    message: str
    count: int = 1


@dataclass
class SPIReport:
    summary: SPIReportSummary
    transactions: list[SPITransaction] = field(default_factory=list)
    anomalies: list[SPIDiagnosticIssue] = field(default_factory=list)
    data_quality_issues: list[SPIDataQualityIssue] = field(default_factory=list)
