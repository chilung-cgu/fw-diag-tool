from __future__ import annotations

from pathlib import Path

from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.limits import AnalysisLimits, coerce_limits

from .anomaly import SPIAnomalyDetector
from .models import (
    SPIDataQualityIssue,
    SPIOpcode,
    SPIReport,
    SPIReportSummary,
)
from .parser import SPIParser


class SPIDiagnosticEngine:
    def __init__(self, max_page_size: int = 256, *, limits: AnalysisLimits | None = None):
        self.limits = coerce_limits(limits)
        if (
            isinstance(max_page_size, bool)
            or not isinstance(max_page_size, int)
            or max_page_size <= 0
        ):
            raise ValueError("max_page_size must be a positive integer")
        self.parser = SPIParser()
        self.anomaly_detector = SPIAnomalyDetector(max_page_size=max_page_size, limits=self.limits)
        self.max_page_size = max_page_size

    def analyze_csv_content(self, csv_text: str) -> SPIReport:
        if not isinstance(csv_text, str):
            raise TypeError("csv_text must be a string")
        transactions = self.parser.parse_csv_content(
            csv_text, page_size=self.max_page_size, limits=self.limits
        )
        anomalies = self.anomaly_detector.analyze(transactions)
        if len(anomalies) > self.limits.max_findings:
            raise ResourceLimitError(
                f"SPI findings exceed the {self.limits.max_findings}-finding safety limit",
                resource="findings",
                limit=self.limits.max_findings,
                observed=len(anomalies),
            )
        meaningful_lines = [
            line
            for line in csv_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        data_quality_issues: list[SPIDataQualityIssue] = []
        if len(meaningful_lines) <= 1:
            data_quality_issues.append(
                SPIDataQualityIssue(
                    code="SPI_SOURCE_EMPTY",
                    message=(
                        "The capture has no data rows after removing the header/comments; "
                        "no SPI protocol conclusion can be established."
                    ),
                )
            )
        elif not transactions:
            data_quality_issues.append(
                SPIDataQualityIssue(
                    code="SPI_NO_TRANSACTIONS",
                    message=(
                        "Input rows were present but no CS-framed SPI transaction was decoded; "
                        "check chip-select polarity and capture framing."
                    ),
                )
            )
        incomplete_count = sum(
            bool(tx.decoded_details.get("capture_incomplete")) for tx in transactions
        )
        if incomplete_count:
            data_quality_issues.append(
                SPIDataQualityIssue(
                    code="SPI_CS_UNTERMINATED",
                    message=(
                        "The capture ended while CS was still asserted; the final transaction may be truncated."
                    ),
                    count=incomplete_count,
                )
            )
        response_truncated_count = sum(
            bool(tx.decoded_details.get("response_truncated")) for tx in transactions
        )
        if response_truncated_count:
            data_quality_issues.append(
                SPIDataQualityIssue(
                    code="SPI_RESPONSE_TRUNCATED",
                    message=(
                        "One or more SPI commands ended before the minimum response or payload "
                        "bytes required for a trustworthy decode were captured."
                    ),
                    count=response_truncated_count,
                )
            )
        response_overlong_count = sum(
            bool(tx.decoded_details.get("response_overlong")) for tx in transactions
        )
        if response_overlong_count:
            data_quality_issues.append(
                SPIDataQualityIssue(
                    code="SPI_RESPONSE_OVERLONG",
                    message=(
                        "One or more fixed-width SPI commands carried more bytes than the "
                        "decoder contract permits; the extra status payload was not treated "
                        "as a trustworthy register write."
                    ),
                    count=response_overlong_count,
                )
            )

        read_count = 0
        write_count = 0
        erase_count = 0
        status_count = 0
        detected_chip = None

        for tx in transactions:
            op = tx.opcode
            if op is None:
                continue
            if tx.decoded_details.get("response_truncated") or tx.decoded_details.get(
                "response_overlong"
            ):
                # Keep malformed fixed-width frames visible in the transaction
                # table and data-quality panel, but do not count them as
                # accepted read/write/erase operations.
                continue
            if op in (
                SPIOpcode.READ_DATA,
                SPIOpcode.FAST_READ,
                SPIOpcode.FAST_READ_DUAL_OUT,
                SPIOpcode.FAST_READ_QUAD_OUT,
            ):
                read_count += 1
            elif op in (SPIOpcode.PAGE_PROGRAM, SPIOpcode.QUAD_PAGE_PROGRAM):
                write_count += 1
            elif op in (
                SPIOpcode.SECTOR_ERASE_4K,
                SPIOpcode.BLOCK_ERASE_32K,
                SPIOpcode.BLOCK_ERASE_64K,
                SPIOpcode.CHIP_ERASE,
                SPIOpcode.CHIP_ERASE_ALT,
            ):
                erase_count += 1
            elif op in (
                SPIOpcode.READ_STATUS_REG_1,
                SPIOpcode.READ_STATUS_REG_2,
                SPIOpcode.READ_STATUS_REG_3,
            ):
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
            anomalies=anomalies,
            data_quality_issues=data_quality_issues,
        )

    def analyze_csv_file(self, file_path: str | Path) -> SPIReport:
        p = Path(file_path)
        size = p.stat().st_size
        if size > self.limits.max_upload_bytes:
            raise ResourceLimitError(
                f"SPI CSV input exceeds the {self.limits.max_upload_bytes}-byte safety limit",
                resource="SPI CSV input",
                limit=self.limits.max_upload_bytes,
                observed=size,
            )
        content = p.read_text(encoding="utf-8")
        return self.analyze_csv_content(content)
