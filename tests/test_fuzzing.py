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
