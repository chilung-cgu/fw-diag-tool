from __future__ import annotations

from pathlib import Path

from .anomaly import SPIAnomalyDetector
from .models import (
    SPIOpcode,
    SPIReport,
    SPIReportSummary,
)
from .parser import SPIParser


class SPIDiagnosticEngine:
    def __init__(self, max_page_size: int = 256):
        self.parser = SPIParser()
        self.anomaly_detector = SPIAnomalyDetector(max_page_size=max_page_size)

    def analyze_csv_content(self, csv_text: str) -> SPIReport:
        transactions = self.parser.parse_csv_content(csv_text)
        anomalies = self.anomaly_detector.analyze(transactions)

        read_count = 0
        write_count = 0
        erase_count = 0
        status_count = 0
        detected_chip = None

        for tx in transactions:
            op = tx.opcode
            if op is None:
                continue
            if op in (SPIOpcode.READ_DATA, SPIOpcode.FAST_READ, SPIOpcode.FAST_READ_DUAL_OUT, SPIOpcode.FAST_READ_QUAD_OUT):
                read_count += 1
            elif op in (SPIOpcode.PAGE_PROGRAM, SPIOpcode.QUAD_PAGE_PROGRAM):
                write_count += 1
            elif op in (SPIOpcode.SECTOR_ERASE_4K, SPIOpcode.BLOCK_ERASE_32K, SPIOpcode.BLOCK_ERASE_64K, SPIOpcode.CHIP_ERASE):
                erase_count += 1
            elif op in (SPIOpcode.READ_STATUS_REG_1, SPIOpcode.READ_STATUS_REG_2, SPIOpcode.READ_STATUS_REG_3):
                status_count += 1
            elif op == SPIOpcode.JEDEC_ID and not detected_chip:
                chip_name = tx.decoded_details.get("identified_chip")
                if chip_name and chip_name != "Unknown Manufacturer / Model":
                    detected_chip = chip_name

        summary = SPIReportSummary(
            total_transactions=len(transactions),
            read_count=read_count,
            write_count=write_count,
            erase_count=erase_count,
            status_poll_count=status_count,
            anomaly_count=len(anomalies),
            detected_flash_chip=detected_chip,
        )

        return SPIReport(
            summary=summary,
            transactions=transactions,
            anomalies=anomalies
        )

    def analyze_csv_file(self, file_path: str | Path) -> SPIReport:
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        return self.analyze_csv_content(content)
