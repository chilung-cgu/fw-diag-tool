"""SPI / QSPI Flash Protocol Diagnostics Module."""

from .chip_db import (
    SPI_FLASH_DB,
    SPIFlashChip,
    list_manufacturers,
    lookup_by_jedec,
    lookup_by_part_number,
)
from .engine import SPIDiagnosticEngine
from .models import SPIDiagnosticIssue, SPIReport, SPITransaction
from .raw_capture import RawSPIDecodeResult, RawSPITransition, parse_raw_spi_csv
from .reporter import SPIReporter
from .statistics import SPIStatistics, compute_spi_statistics

__all__ = [
    "SPI_FLASH_DB",
    "RawSPIDecodeResult",
    "RawSPITransition",
    "SPIDiagnosticEngine",
    "SPIDiagnosticIssue",
    "SPIFlashChip",
    "SPIReport",
    "SPIReporter",
    "SPIStatistics",
    "SPITransaction",
    "compute_spi_statistics",
    "list_manufacturers",
    "lookup_by_jedec",
    "lookup_by_part_number",
    "parse_raw_spi_csv",
]
