"""Tests for extended Fault Arena fixtures (cases 21-30)."""

from __future__ import annotations

import pytest

from fw_diag_tool.fault_arena import FIXTURE_CASES, FaultArenaFixtures
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser

EXTENDED_CASE_IDS = [f"{i:02d}" for i in range(21, 31)]


def test_fixture_cases_exported_and_contains_30_entries():
    assert len(FIXTURE_CASES) == 30
    assert [c.case_id for c in FIXTURE_CASES] == [f"{i:02d}" for i in range(1, 31)]


@pytest.mark.parametrize("case_id", EXTENDED_CASE_IDS)
def test_extended_cases_builder_returns_nonempty_string(case_id: str):
    case = FaultArenaFixtures.get_case(case_id)
    content = case.builder()
    assert isinstance(content, str)
    assert len(content.strip()) > 0
    assert content == FaultArenaFixtures.generate(case_id)


def test_case_21_i2c_multi_master_arbitration_loss():
    content = FaultArenaFixtures.generate("21")
    report = I2CDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 2
    assert any(tx.address_7bit == 0x50 for tx in report.transactions)
    assert any(tx.address_7bit == 0x48 for tx in report.transactions)


def test_case_22_spi_jedec_id_read_failure():
    content = FaultArenaFixtures.generate("22")
    report = SPIDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) == 1
    assert any(issue.code == "SPI_JEDEC_LINE_FAULT" for issue in report.issues)


def test_case_23_uart_watchdog_reset_loop():
    content = FaultArenaFixtures.generate("23")
    report = UARTCrashParser.parse_log_text(content)
    assert report.raw_log_lines > 0
    assert "Watchdog" in content or "watchdog" in content


def test_case_24_pmbus_status_word_multiple_faults():
    content = FaultArenaFixtures.generate("24")
    report = I2CDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 1
    # Check that STATUS_WORD was decoded with multiple fault flags
    status_txs = [
        tx for tx in report.transactions if tx.command_name == "STATUS_WORD" and tx.decoded_values
    ]
    assert len(status_txs) >= 1
    flags = status_txs[-1].decoded_values.get("status_flags", [])
    assert any("VIN_UV" in f for f in flags)
    assert any("IOUT_OC" in f for f in flags)
    assert any("TEMPERATURE" in f for f in flags)


def test_case_25_spi_write_protect_violation():
    content = FaultArenaFixtures.generate("25")
    report = SPIDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 2
    opcodes = [tx.opcode_name for tx in report.transactions]
    assert any("Write Enable" in op for op in opcodes)
    assert any("Page Program" in op for op in opcodes)
    assert any("Read Status Register-1" in op for op in opcodes)


def test_case_26_pcie_aer_correctable_error_storm():
    content = FaultArenaFixtures.generate("26")
    cfg = PCIeAnalyzer().parse_config_dump(content)
    assert cfg.bdf is not None
    assert cfg.aer_analysis is not None
    assert cfg.aer_analysis.active_corr_count >= 2
    corr_codes = {
        e.short_code for e in cfg.aer_analysis.corr_errors if e.is_active and not e.is_masked
    }
    assert "BadTLP" in corr_codes
    assert "ReplayTimeout" in corr_codes


def test_case_27_i2c_eeprom_write_without_twr():
    content = FaultArenaFixtures.generate("27")
    report = I2CDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 2
    assert any(issue.code == "I2C_ADDR_NACK" for issue in report.issues)


def test_case_28_uart_framing_error_break():
    content = FaultArenaFixtures.generate("28")
    report = UARTCrashParser.parse_log_text(content)
    assert report.raw_log_lines > 0
    assert "framing error" in content.lower()


def test_case_29_i2c_10bit_addressing():
    content = FaultArenaFixtures.generate("29")
    report = I2CDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 1
    assert any(tx.address_7bit == 0x78 for tx in report.transactions)


def test_case_30_spi_dual_quad_mode_mismatch():
    content = FaultArenaFixtures.generate("30")
    report = SPIDiagnosticEngine().analyze_csv_content(content)
    assert len(report.transactions) >= 1
