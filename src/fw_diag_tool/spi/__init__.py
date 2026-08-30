"""SPI / QSPI Flash Protocol Diagnostics Module."""

from .engine import SPIDiagnosticEngine
from .models import SPIDiagnosticIssue, SPIReport, SPITransaction
from .raw_capture import RawSPIDecodeResult, RawSPITransition, parse_raw_spi_csv
from .reporter import SPIReporter
from .statistics import SPIStatistics, compute_spi_statistics

__all__ = [
    "RawSPIDecodeResult",
    "RawSPITransition",
    "SPIDiagnosticEngine",
    "SPIDiagnosticIssue",
    "SPIReport",
    "SPIReporter",
    "SPIStatistics",
    "SPITransaction",
    "compute_spi_statistics",
    "parse_raw_spi_csv",
]
