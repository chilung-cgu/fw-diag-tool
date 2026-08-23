"""Synthetic Fault Arena case fixtures.

Each fixture is a synthetic training artifact, not a real company capture.
The generated content is aligned with the tool's own parsers so every case
can be fed straight into the matching analyzer for hands-on practice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureCase:
    case_id: str
    title: str
    kind: str
    filename: str
    builder: Callable[[], str]


def _i2c_csv(rows: list[str], *, with_duration: bool = False) -> str:
    header = "Time [s],Packet ID,Address,Data,Read/Write,ACK/NAK"
    if with_duration:
        header += ",Duration"
    return header + "\n" + "\n".join(rows) + "\n"


def _spi_csv(rows: list[str]) -> str:
    header = "Time [s],MOSI,MISO,Enable"
    return header + "\n" + "\n".join(rows) + "\n"


def case_01_address_nack() -> str:
    return _i2c_csv(
        [
            "0.000100,0,0x3A,,Write,NAK",
            "0.000500,1,0x3A,,Write,NAK",
            "0.001000,2,0x50,,Write,ACK",
            "0.001025,2,,0x00,Write,ACK",
            "0.001050,2,,0x42,Write,ACK",
        ]
    )


def case_02_eeprom_data_nack() -> str:
    # Address is ACKed, then the slave rejects a write while its internal
    # tWR page-program cycle is still busy.
    return _i2c_csv(
        [
            "0.000000,0,0x50,,Write,ACK",
            "0.000025,0,,0x00,Write,ACK",
            "0.000050,0,,0x12,Write,ACK",
            "0.006000,1,0x50,,Write,ACK",
            "0.006025,1,,0x34,Write,NACK",
        ]
    )


def case_03_clock_stretching() -> str:
    return _i2c_csv(
        [
            "0.000000,0,0x58,,Write,ACK,",
            "0.000025,0,,0x88,Write,ACK,",
            "0.000050,1,0x58,,Read,ACK,",
            "0.000075,1,,0x00,Read,ACK,0.030000",
            "0.030075,1,,0xE2,Read,NACK,",
        ],
        with_duration=True,
    )


def case_04_eeprom_page_rollover() -> str:
    # 24C02: 8-byte pages; a 4-byte write issued at offset 0x06 silently
    # wraps to 0x00 of the SAME page instead of continuing to the next page.
    return _i2c_csv(
        [
            "0.000000,0,0x50,,Write,ACK",
            "0.000025,0,,0x1E,Write,ACK",
            "0.000050,0,,0xAA,Write,ACK",
            "0.000075,0,,0xBB,Write,ACK",
            "0.000100,0,,0xCC,Write,ACK",
            "0.000125,0,,0xDD,Write,ACK",
            "0.010000,1,0x2A,,Write,NAK",
            "0.011000,1,0x2A,,Write,NAK",
        ]
    )


def case_05_mux_conflict() -> str:
    # PCA9548A control byte 0x07 opens channels 0..2 simultaneously.
    return _i2c_csv(
        [
            "0.000000,0,0x70,,Write,ACK",
            "0.000025,0,,0x07,Write,ACK",
            "0.001000,1,0x48,,Write,ACK",
            "0.001025,1,,0x00,Write,ACK",
            "0.002000,2,0x49,,Write,NACK",
        ]
    )


def case_06_pmbus_vout_trim() -> str:
    # VOUT_TRIM (0x22) = 0xFF80.  With Linear16 two's-complement handling the
    # trim word is negative (-128); decoding it as unsigned yields the classic
    # ~127x over-report.  A READ_VOUT (0x8B) response follows so the report
    # shows both the misconfigured trim and its measured consequence
    # (READ_VOUT = 12.0 V with the default Linear16 exponent -9).
    return _i2c_csv(
        [
            "0.000000,0,0x58,,Write,ACK",
            "0.000025,0,,0x22,Write,ACK",
            "0.000050,0,,0x80,Write,ACK",
            "0.000075,0,,0xFF,Write,ACK",
            "0.001000,2,0x58,,Read,ACK",
            "0.001025,3,0x58,,Write,ACK",
            "0.001050,3,,0x8B,Write,ACK",
            "0.001075,4,0x58,,Read,ACK",
            "0.001100,4,,0x00,Read,ACK",
            "0.001125,4,,0x18,Read,NACK",
        ]
    )


def _pcie_config_space(*, degraded_link: bool, aer_status: int) -> bytes:
    import struct

    cfg = bytearray(0x100)
    cfg[0x00:0x04] = struct.pack("<HH", 0x10EE, 0x7024)
    cfg[0x06] = 0x10  # status: capabilities list present
    cfg[0x08] = 0x02  # revision
    cfg[0x09] = 0x00  # programming interface
    cfg[0x0A] = 0x00  # subclass: host bridge
    cfg[0x0B] = 0x06  # base class: bridge device
    cfg[0x0E] = 0x01  # header type 1 (PCI-to-PCI bridge)
    cfg[0x34] = 0x40  # capability pointer -> PCIe cap at 0x40

    # Standard capability list: PCIe capability (ID 0x10) at 0x40.
    link_cap = (1 << 0) | (16 << 4)  # max Gen1, x16
    link_sta = (1 << 0) | (1 << 4) if degraded_link else (1 << 0) | (16 << 4)
    cfg[0x40] = 0x10
    cfg[0x41] = 0x00
    cfg[0x42:0x44] = struct.pack("<H", (1 << 4) | 1)  # endpoint, cap version 1
    # Device control/status live at ptr+8 (0x48); link cap sits at ptr+12
    # (0x4C) and link control/status follow at ptr+16 (0x50).
    cfg[0x48:0x4A] = struct.pack("<H", 0x0040)  # device control
    cfg[0x4A:0x4C] = struct.pack("<H", 0x0000)  # device status
    cfg[0x4C:0x50] = struct.pack("<I", link_cap)
    cfg[0x50] = 0x00  # link control (low byte)
    cfg[0x51] = 0x00  # link control (high byte)
    cfg[0x52:0x54] = struct.pack("<H", link_sta)  # link status at ptr+16

    # Extended capability list starting at 0x100: AER (ID 0x0001), last entry.
    aer = bytearray(0x40)
    aer[0x00:0x04] = struct.pack("<I", 0x0001 | (1 << 20))  # cap id 1, next = 0
    aer[0x04:0x08] = struct.pack("<I", aer_status)
    aer[0x0C:0x10] = struct.pack("<I", aer_status)  # severity mirrors status
    cfg.extend(aer)
    return bytes(cfg)


def case_07_pcie_link_degradation() -> str:
    cfg = _pcie_config_space(
        degraded_link=True,
        aer_status=0,
    )
    lines = [
        f"{offset:02x}: " + " ".join(f"{b:02x}" for b in chunk) for offset, chunk in _chunks(cfg)
    ]
    return "0000:01:00.0 PCI bridge: Synthetic Device 7024\n" + "\n".join(lines) + "\n"


def case_08_pcie_completion_timeout() -> str:
    cfg = _pcie_config_space(degraded_link=False, aer_status=1 << 14)
    lines = [
        f"{offset:02x}: " + " ".join(f"{b:02x}" for b in chunk) for offset, chunk in _chunks(cfg)
    ]
    return "0000:02:00.0 Processing accelerators: Synthetic Device 7024\n" + "\n".join(lines) + "\n"


def case_09_pcie_malformed_tlp() -> str:
    cfg = _pcie_config_space(degraded_link=False, aer_status=1 << 18)
    lines = [
        f"{offset:02x}: " + " ".join(f"{b:02x}" for b in chunk) for offset, chunk in _chunks(cfg)
    ]
    return "0000:03:00.0 Processing accelerators: Synthetic Device 7024\n" + "\n".join(lines) + "\n"


def case_10_pcie_poisoned_tlp() -> str:
    cfg = _pcie_config_space(degraded_link=False, aer_status=1 << 12)
    lines = [
        f"{offset:02x}: " + " ".join(f"{b:02x}" for b in chunk) for offset, chunk in _chunks(cfg)
    ]
    return "0000:04:00.0 Memory controller: Synthetic Device 7024\n" + "\n".join(lines) + "\n"


def _chunks(data: bytes, size: int = 16):
    for start in range(0, len(data), size):
        yield start, data[start : start + size]


def case_11_spi_missing_wren() -> str:
    # Page Program (0x02) is issued without a preceding 0x06 WREN command.
    return _spi_csv(
        [
            "0.0001,0x02,0x00,0",
            "0.0002,0x00,0x00,0",
            "0.0003,0x10,0x00,0",
            "0.0004,0x55,0x00,0",
            "0.0005,0xAA,0x00,0",
            "0.0006,0x00,0x00,1",
        ]
    )


def case_12_spi_page_wraparound() -> str:
    # A 6-byte write starts at offset 0xFE inside a 256-byte page; the last
    # two bytes wrap back to 0x00/0x01 of the same page.
    return _spi_csv(
        [
            "0.0001,0x06,0x00,0",
            "0.0002,0x00,0x00,1",
            "0.0010,0x02,0x00,0",
            "0.0011,0x00,0x00,0",
            "0.0012,0xFE,0x00,0",
            "0.0013,0x11,0x00,0",
            "0.0014,0x22,0x00,0",
            "0.0015,0x33,0x00,0",
            "0.0016,0x44,0x00,0",
            "0.0017,0x55,0x00,0",
            "0.0018,0x66,0x00,0",
            "0.0019,0x00,0x00,1",
        ]
    )


def case_13_spi_jedec_all_ff() -> str:
    return _spi_csv(
        [
            "0.0001,0x9F,0x00,0",
            "0.0002,0x00,0xFF,0",
            "0.0003,0x00,0xFF,0",
            "0.0004,0x00,0xFF,0",
            "0.0005,0x00,0x00,1",
        ]
    )


def case_14_spi_jedec_all_00() -> str:
    return _spi_csv(
        [
            "0.0001,0x9F,0x00,0",
            "0.0002,0x00,0x00,0",
            "0.0003,0x00,0x00,0",
            "0.0004,0x00,0x00,0",
            "0.0005,0x00,0x00,1",
        ]
    )


def case_15_kernel_null_pointer() -> str:
    return (
        "[  124.582910] BUG: unable to handle page fault for address: 0000000000000010\n"
        "[  124.582912] #PF: supervisor read access in kernel mode\n"
        "[  124.582914] #PF: error_code(0x0000) - not-present page\n"
        "[  124.582919] CPU: 4 PID: 1234 Comm: kworker/u16:2\n"
        "[  124.582921] RIP: 0010:probe_driver+0x38/0x120 [demo_drv]\n"
        "[  124.582926] RAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000\n"
        "[  124.582932] RBP: ffff888102347d98 R08: 0000000000000000 R09: 0000000000000001\n"
        "[  124.582936] CR2: 0000000000000010 CR3: 0000000104520000 CR4: 0000000000750ee0\n"
        "[  124.582938] Call Trace:\n"
        "[  124.582940]  <TASK>\n"
        "[  124.582942]  demo_irq_handler+0x8c/0x100 [demo_drv]\n"
        "[  124.582946]  </TASK>\n"
        "[  124.582950] Kernel panic - not syncing: Fatal exception in interrupt\n"
    )


def case_16_divbyzero() -> str:
    return (
        "================ HARDFAULT STACK DUMP ===============\n"
        "Exception: HardFault triggered on ARM Cortex-M4\n"
        "HFSR:  0x40000000 (FORCED - Escalation of Configurable Fault)\n"
        "CFSR:  0x02000000 (UFSR.DIVBYZERO - Division by zero trapped)\n"
        "BFAR:  0x00000000 (Invalid - BFARVALID not set)\n"
        "MMFAR: 0x00000000\n"
        "Stacked R0:  0x00000000\n"
        "Stacked R1:  0x0000000A\n"
        "Stacked R2:  0x20001000\n"
        "Stacked R3:  0x00000000\n"
        "Stacked R12: 0x00000000\n"
        "Stacked LR:  0x08000457 (Return Address / Function Caller)\n"
        "Stacked PC:  0x08001234 (Faulting Instruction Address)\n"
        "Stacked xPSR: 0x61000000 (Default Thumb state)\n"
        "======================================================\n"
    )


def case_17_unaligned_access() -> str:
    return (
        "================ HARDFAULT STACK DUMP ===============\n"
        "Exception: HardFault triggered on ARM Cortex-M4\n"
        "HFSR:  0x40000000 (FORCED - Escalation of Configurable Fault)\n"
        "CFSR:  0x01000000 (UFSR.UNALIGNED - Unaligned memory access trapped)\n"
        "BFAR:  0x20001001 (Fault Address Valid)\n"
        "MMFAR: 0x00000000\n"
        "Stacked R0:  0x20001000\n"
        "Stacked R1:  0x00000001\n"
        "Stacked R2:  0x00000004\n"
        "Stacked R3:  0x20001001\n"
        "Stacked R12: 0x00000000\n"
        "Stacked LR:  0x08000489 (Return Address / Function Caller)\n"
        "Stacked PC:  0x08001278 (Faulting Instruction Address)\n"
        "Stacked xPSR: 0x61000000 (Default Thumb state)\n"
        "======================================================\n"
    )


def case_18_imprecise_bus_fault() -> str:
    return (
        "================ HARDFAULT STACK DUMP ===============\n"
        "Exception: HardFault triggered on ARM Cortex-M4\n"
        "HFSR:  0x40000000 (FORCED - Escalation of Configurable Fault)\n"
        "CFSR:  0x00000400 (BFSR.IMPRECISERR - Imprecise data bus error)\n"
        "BFAR:  0x00000000 (Invalid - BFARVALID not set)\n"
        "MMFAR: 0x00000000\n"
        "Stacked R0:  0x40023800\n"
        "Stacked R1:  0x00000001\n"
        "Stacked R2:  0x00000000\n"
        "Stacked R3:  0x40023800\n"
        "Stacked R12: 0x00000000\n"
        "Stacked LR:  0x080004A1 (Return Address / Function Caller)\n"
        "Stacked PC:  0x08001290 (Faulting Instruction Address)\n"
        "Stacked xPSR: 0x61000000 (Default Thumb state)\n"
        "======================================================\n"
    )


def case_19_mctp_sequence() -> str:
    # Two single-packet MCTP/PLDM messages: seq 0 (hdr_flags 0xC0) then seq 2
    # (hdr_flags 0xE0 = SOM|EOM|seq=2), so the second packet is out of
    # sequence (expected 1).
    return (
        "# MCTP PLDM sensor read request (SOM/EOM, seq 0)\n"
        "01 08 00 C0 01 80 02 01 00\n"
        "# MCTP PLDM sensor read response with wrong sequence (seq 2)\n"
        "01 08 00 E0 01 80 02 01 00\n"
    )


def case_20_ipmb_checksum() -> str:
    # Valid request followed by a response whose checksum-1 is corrupted
    # (0x63 -> 0x64), so (rs_addr + netfn + chk1) no longer sums to 0x00.
    return (
        "# IPMB Request: BMC (0x20) -> Satellite (0x81) Get Device ID\n"
        "81 18 67 20 00 01 DF\n"
        "# IPMB Response with corrupted checksum-1 (0x64 instead of 0x63)\n"
        "20 1C 64 81 00 01 00 00 3F\n"
    )


_CASES: list[FixtureCase] = [
    FixtureCase("01", "I2C Address NACK", "i2c", "case01_address_nack.csv", case_01_address_nack),
    FixtureCase(
        "02", "I2C EEPROM Data NACK", "i2c", "case02_eeprom_data_nack.csv", case_02_eeprom_data_nack
    ),
    FixtureCase(
        "03",
        "I2C Clock Stretching > 25 ms",
        "i2c",
        "case03_clock_stretching.csv",
        case_03_clock_stretching,
    ),
    FixtureCase(
        "04",
        "EEPROM Page Rollover",
        "i2c",
        "case04_eeprom_page_rollover.csv",
        case_04_eeprom_page_rollover,
    ),
    FixtureCase(
        "05",
        "I2C MUX Multi-Channel Conflict",
        "i2c",
        "case05_mux_conflict.csv",
        case_05_mux_conflict,
    ),
    FixtureCase(
        "06",
        "PMBus VOUT_TRIM Two's-Complement",
        "i2c",
        "case06_pmbus_vout_trim.csv",
        case_06_pmbus_vout_trim,
    ),
    FixtureCase(
        "07",
        "PCIe Gen4 -> Gen1 Degradation",
        "pcie",
        "case07_pcie_link_degradation.txt",
        case_07_pcie_link_degradation,
    ),
    FixtureCase(
        "08",
        "PCIe Completion Timeout",
        "pcie",
        "case08_pcie_completion_timeout.txt",
        case_08_pcie_completion_timeout,
    ),
    FixtureCase(
        "09",
        "PCIe Malformed TLP",
        "pcie",
        "case09_pcie_malformed_tlp.txt",
        case_09_pcie_malformed_tlp,
    ),
    FixtureCase(
        "10", "PCIe Poisoned TLP", "pcie", "case10_pcie_poisoned_tlp.txt", case_10_pcie_poisoned_tlp
    ),
    FixtureCase(
        "11",
        "SPI Page Program Missing WREN",
        "spi",
        "case11_spi_missing_wren.csv",
        case_11_spi_missing_wren,
    ),
    FixtureCase(
        "12",
        "SPI 256B Page Wrap-Around",
        "spi",
        "case12_spi_page_wraparound.csv",
        case_12_spi_page_wraparound,
    ),
    FixtureCase(
        "13", "SPI JEDEC All 0xFF", "spi", "case13_spi_jedec_all_ff.csv", case_13_spi_jedec_all_ff
    ),
    FixtureCase(
        "14", "SPI JEDEC All 0x00", "spi", "case14_spi_jedec_all_00.csv", case_14_spi_jedec_all_00
    ),
    FixtureCase(
        "15",
        "Kernel NULL Pointer Panic",
        "uart",
        "case15_kernel_null_pointer.log",
        case_15_kernel_null_pointer,
    ),
    FixtureCase(
        "16", "Cortex-M DIVBYZERO HardFault", "uart", "case16_divbyzero.log", case_16_divbyzero
    ),
    FixtureCase(
        "17",
        "Cortex-M UNALIGNED HardFault",
        "uart",
        "case17_unaligned.log",
        case_17_unaligned_access,
    ),
    FixtureCase(
        "18",
        "Cortex-M IMPRECISERR HardFault",
        "uart",
        "case18_imprecise_bus_fault.log",
        case_18_imprecise_bus_fault,
    ),
    FixtureCase(
        "19", "MCTP PLDM Sequence Error", "mctp", "case19_mctp_sequence.hex", case_19_mctp_sequence
    ),
    FixtureCase(
        "20", "IPMB Checksum FAIL", "mctp", "case20_ipmb_checksum.hex", case_20_ipmb_checksum
    ),
]


class FaultArenaFixtures:
    """Registry and generator for the 20 Fault Arena cases."""

    @staticmethod
    def list_cases() -> list[FixtureCase]:
        return list(_CASES)

    @staticmethod
    def get_case(case_id: str) -> FixtureCase:
        normalized = str(case_id).strip()
        normalized = normalized.removeprefix("Case ")
        normalized = normalized.zfill(2)
        for case in _CASES:
            if case.case_id == normalized:
                return case
        raise KeyError(f"unknown Fault Arena case: {case_id!r}")

    @staticmethod
    def generate(case_id: str) -> str:
        return FaultArenaFixtures.get_case(case_id).builder()

    @staticmethod
    def generate_all() -> dict[str, str]:
        return {case.case_id: case.builder() for case in _CASES}

    @staticmethod
    def write_all(directory) -> list:
        from pathlib import Path

        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for case in _CASES:
            path = out_dir / case.filename
            path.write_text(case.builder(), encoding="utf-8")
            written.append(path)
        return written
