"""Performance benchmark test suite for core diagnostic engines and parsers.

This module uses pytest-benchmark to evaluate the throughput and latency of:
1. I2CDiagnosticEngine.analyze_csv_content
2. SPIDiagnosticEngine.analyze_csv_content
3. UARTCrashParser.parse_log_text
4. ServerMgmtParser.parse_hex_dump
5. PCIeAnalyzer.parse_config_dump
6. load_board_profile
"""

from __future__ import annotations

import pytest

from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser


def _generate_i2c_csv() -> str:
    """Generate a 50~100 line decoded I2C CSV for benchmarking."""
    rows = ["Time [s],Packet ID,Address,Data,Read/Write,ACK/NAK"]
    time_offset = 0.000100
    # 15 packets * 5 rows each = 75 rows total (within 50~100 range)
    for pkt_idx in range(15):
        pkt_id = pkt_idx * 2
        rows.append(f"{time_offset:.6f},{pkt_id},0x50,,Write,ACK")
        time_offset += 0.000025
        rows.append(f"{time_offset:.6f},{pkt_id},,0x00,Write,ACK")
        time_offset += 0.000025
        rows.append(f"{time_offset:.6f},{pkt_id},,0x42,Write,ACK")
        time_offset += 0.000025
        rows.append(f"{time_offset:.6f},{pkt_id + 1},0x50,,Read,ACK")
        time_offset += 0.000025
        rows.append(f"{time_offset:.6f},{pkt_id + 1},,0xAB,Read,ACK")
        time_offset += 0.000200
    return "\n".join(rows)


def _generate_spi_csv() -> str:
    """Generate a 30~50 line SPI CSV for benchmarking."""
    rows = ["Time [s],MOSI,MISO,Enable"]
    time_offset = 0.000100
    # 8 transfer bursts * 5 rows each = 40 rows total (within 30~50 range)
    for _ in range(8):
        rows.append(f"{time_offset:.6f},0x03,0x00,0")
        time_offset += 0.000050
        rows.append(f"{time_offset:.6f},0x00,0x00,0")
        time_offset += 0.000050
        rows.append(f"{time_offset:.6f},0x10,0x00,0")
        time_offset += 0.000050
        rows.append(f"{time_offset:.6f},0x00,0x42,0")
        time_offset += 0.000050
        rows.append(f"{time_offset:.6f},0x00,0x00,1")
        time_offset += 0.000100
    return "\n".join(rows)


def _generate_uart_panic_log() -> str:
    """Generate a kernel panic log with call trace for benchmarking."""
    lines = [
        "[  123.456789] Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)",
        "[  123.456790] CPU: 0 PID: 1 Comm: swapper/0 Not tainted 6.6.0-arm64 #1",
        "[  123.456791] Hardware name: OpenBMC Yosemite V4 (DT)",
        "[  123.456792] Call Trace:",
    ]
    for idx in range(20):
        lines.append(f"[  123.456{800 + idx:03d}]  dump_stack_lvl+0x48/0x60")
        lines.append(f"[  123.456{825 + idx:03d}]  panic+0x310/0x358")
        lines.append(f"[  123.456{850 + idx:03d}]  mount_root+0x1a/0x1c")
        lines.append(f"[  123.456{875 + idx:03d}]  prepare_namespace+0x136/0x165")
    return "\n".join(lines)


def _generate_mctp_hex_dump() -> str:
    """Generate MCTP and IPMB hex dumps for benchmarking."""
    lines = []
    for _ in range(25):
        lines.append("01 00 08 C8 00 01 80 01 00 00 00 00 00 00 00 01")
        lines.append("01 08 00 C0 01 00 02 01 00")
        lines.append("81 1C 63 20 20 01 00 BF")
    return "\n".join(lines)


def _generate_pcie_lspci_dump() -> str:
    """Generate lspci config space dump for benchmarking."""
    return (
        "0000:01:00.0 Processing accelerators: Xilinx Corporation Device 7024\n"
        "00: ee 10 24 70 06 00 10 00 01 00 80 12 10 00 00 00\n"
        "10: 0c 00 00 f0 00 00 00 00 00 00 00 00 00 00 00 00\n"
        "20: 00 00 00 00 00 00 00 00 00 00 00 00 ee 10 24 70\n"
        "30: 00 00 00 00 40 00 00 00 00 00 00 00 0b 01 00 00\n"
        "40: 10 00 02 00 00 00 00 00 00 00 00 00 04 01 00 00\n"
        "50: 00 00 81 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
        "100: 01 00 01 00 00 00 04 00 00 00 00 00 00 00 04 00\n"
        "110: 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00\n"
        "120: 01 00 00 00 0f 00 00 01 00 00 00 fe 00 00 00 00"
    )


def _generate_board_yaml() -> str:
    """Generate board profile YAML for benchmarking."""
    return """board_name: OpenBMC-Server-YV4
version: "1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: fast-mode-plus
    devices:
      - address_7bit: 0x20
        name: board-gpio-expander
        category: GPIO Expander
        protocol: I2C
        compatible: nxp,pca9555
        register_width: 8
        registers:
          - name: input_port_0
            offset: 0x00
            access: RO
          - name: output_port_0
            offset: 0x02
            access: RW
          - name: config_port_0
            offset: 0x06
            access: RW
      - address_7bit: 0x50
        name: baseboard-fru-eeprom
        category: EEPROM
        protocol: EEPROM
        compatible: atmel,24c64
        register_width: 16
        registers:
          - name: fru_header
            offset: 0x0000
            access: RO
    muxes:
      - address_7bit: 0x70
        name: main-i2c-mux
        category: I2C Multiplexer
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        channels:
          - channel: 0
            devices:
              - address_7bit: 0x48
                name: inlet-temp-sensor
                category: Temperature Sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
          - channel: 1
            devices:
              - address_7bit: 0x48
                name: outlet-temp-sensor
                category: Temperature Sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
          - channel: 2
            devices:
              - address_7bit: 0x58
                name: core-voltage-regulator
                category: PMBus Power Controller
                protocol: PMBus
                compatible: infineon,xdpe12284
                register_width: 8
                commands:
                  - name: READ_VIN
                    code: 0x88
                  - name: READ_VOUT
                    code: 0x8B
                  - name: READ_IOUT
                    code: 0x8C
                  - name: READ_TEMPERATURE_1
                    code: 0x8D
          - channel: 3
            devices:
              - address_7bit: 0x40
                name: main-power-monitor
                category: Power Monitor
                protocol: I2C
                compatible: ti,ina226
                register_width: 8
                registers:
                  - name: bus_voltage
                    offset: 0x02
                    access: RO
                  - name: shunt_voltage
                    offset: 0x01
                    access: RO
  - bus_num: 2
    speed_mode: standard-mode
    devices:
      - address_7bit: 0x50
        name: fru-backup
        category: EEPROM
        protocol: EEPROM
        compatible: atmel,24c64
        register_width: 16
        registers:
          - name: fru_header
            offset: 0x0000
            access: RO
"""


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_i2c_engine(benchmark) -> None:
    """Benchmark I2CDiagnosticEngine.analyze_csv_content."""
    csv_text = _generate_i2c_csv()
    engine = I2CDiagnosticEngine()
    report = benchmark.pedantic(
        engine.analyze_csv_content,
        args=(csv_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert report is not None
    assert len(report.transactions) > 0


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_spi_engine(benchmark) -> None:
    """Benchmark SPIDiagnosticEngine.analyze_csv_content."""
    csv_text = _generate_spi_csv()
    engine = SPIDiagnosticEngine()
    report = benchmark.pedantic(
        engine.analyze_csv_content,
        args=(csv_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert report is not None
    assert len(report.transactions) > 0


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_uart_parser(benchmark) -> None:
    """Benchmark UARTCrashParser.parse_log_text."""
    log_text = _generate_uart_panic_log()
    report = benchmark.pedantic(
        UARTCrashParser.parse_log_text,
        args=(log_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert report is not None
    assert report.kernel_panic is not None


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_mctp_parser(benchmark) -> None:
    """Benchmark ServerMgmtParser.parse_hex_dump."""
    hex_text = _generate_mctp_hex_dump()
    report = benchmark.pedantic(
        ServerMgmtParser.parse_hex_dump,
        args=(hex_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert report is not None
    assert len(report.mctp_packets) > 0


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_pcie_parser(benchmark) -> None:
    """Benchmark PCIeAnalyzer.parse_config_dump."""
    config_text = _generate_pcie_lspci_dump()
    result = benchmark.pedantic(
        PCIeAnalyzer.parse_config_dump,
        args=(config_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert result is not None
    assert result.vendor_id == 0x10EE


@pytest.mark.benchmark(group="protocol-engines")
def test_benchmark_board_profile(benchmark) -> None:
    """Benchmark load_board_profile with YAML string."""
    yaml_text = _generate_board_yaml()
    profile = benchmark.pedantic(
        load_board_profile,
        args=(yaml_text,),
        rounds=10,
        warmup_rounds=2,
    )
    assert profile is not None
    assert profile.board_name == "OpenBMC-Server-YV4"
