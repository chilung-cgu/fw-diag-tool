import pytest

from fw_diag_tool.fuzz.fuzzer import FuzzingGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser


def test_fuzz_i2c_parser_never_crashes():
    """Fuzz the I2C CSV parser with random malformed inputs to ensure no unhandled exceptions."""
    for seed in range(100):
        csv_data = FuzzingGenerator.fuzz_i2c_csv(seed=seed, num_rows=20)
        engine = I2CDiagnosticEngine()
        # Should never raise an unhandled exception
        try:
            report = engine.analyze_csv_content(csv_data)
            assert report is not None
            assert report.total_transactions >= 0
        except Exception as e:
            pytest.fail(f"Parser crashed on seed={seed}: {e}")


def test_fuzz_uart_log_never_crashes():
    """Fuzz the UART crash parser with random inputs."""
    for seed in range(50):
        log_text = FuzzingGenerator.fuzz_uart_log(seed=seed)
        try:
            report = UARTCrashParser.parse_log_text(log_text)
            assert report is not None
        except Exception as e:
            pytest.fail(f"UART Parser crashed on seed={seed}: {e}")


def test_fuzz_spi_parser_never_crashes():
    from fw_diag_tool.spi.engine import SPIDiagnosticEngine

    for seed in range(50):
        csv_data = FuzzingGenerator.fuzz_spi_csv(seed=seed, num_rows=20)
        try:
            report = SPIDiagnosticEngine().analyze_csv_content(csv_data)
            assert report is not None
        except ValueError:
            # Expected handled input validation error
            pass
        except Exception as e:
            pytest.fail(f"SPI Parser crashed on seed={seed}: {e}")


def test_fuzz_pcie_parser_never_crashes():
    from fw_diag_tool.pcie.parser import PCIeAnalyzer

    for seed in range(50):
        lspci_text = FuzzingGenerator.fuzz_pcie_lspci(seed=seed)
        try:
            configs = PCIeAnalyzer.parse_multi_lspci_text(lspci_text)
            assert isinstance(configs, list)
        except Exception as e:
            pytest.fail(f"PCIe Parser crashed on seed={seed}: {e}")
