"""SPI Before/After Analysis and Diff Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import SPIReport

# Type alias for compatibility with SPIAnalysisReport naming
SPIAnalysisReport = SPIReport


@dataclass
class SPIDiffResult:
    new_anomalies: list[str] = field(default_factory=list)
    resolved_anomalies: list[str] = field(default_factory=list)
    common_anomalies: list[str] = field(default_factory=list)
    transaction_count_delta: int = 0
    summary: str = ""
    baseline_detected_chip: str | None = None
    candidate_detected_chip: str | None = None
    chip_changed: bool = False

    @property
    def is_identical(self) -> bool:
        """Return True if there are no differences in anomalies, count, or chip."""
        return (
            len(self.new_anomalies) == 0
            and len(self.resolved_anomalies) == 0
            and self.transaction_count_delta == 0
            and not self.chip_changed
        )


class SPIDiffEngine:
    """Compares baseline vs candidate SPI analysis reports."""

    @classmethod
    def compare(
        cls,
        baseline_report: SPIReport,
        candidate_report: SPIReport,
    ) -> SPIDiffResult:
        if not isinstance(baseline_report, SPIReport) or not isinstance(
            candidate_report, SPIReport
        ):
            raise TypeError("baseline_report and candidate_report must be SPIReport instances")

        b_anomalies = {a.title for a in baseline_report.anomalies}
        c_anomalies = {a.title for a in candidate_report.anomalies}

        new_anomalies = sorted(c_anomalies - b_anomalies)
        resolved_anomalies = sorted(b_anomalies - c_anomalies)
        common_anomalies = sorted(b_anomalies & c_anomalies)

        b_tx_count = baseline_report.summary.total_transactions
        c_tx_count = candidate_report.summary.total_transactions
        tx_delta = c_tx_count - b_tx_count

        b_chip = baseline_report.summary.detected_flash_chip
        c_chip = candidate_report.summary.detected_flash_chip
        chip_changed = b_chip != c_chip

        if not new_anomalies and not resolved_anomalies and tx_delta == 0 and not chip_changed:
            summary = "Baseline 與 Candidate SPI 報告完全一致，未發現新增或修復的異常。"
        else:
            parts = [
                f"交易數變化 {tx_delta:+d}（{b_tx_count} -> {c_tx_count}）",
                f"新增 {len(new_anomalies)} 項異常",
                f"修復 {len(resolved_anomalies)} 項異常",
            ]
            if chip_changed:
                parts.append(f"晶片型號由 {b_chip or '未識別'} 變更為 {c_chip or '未識別'}")
            summary = f"SPI 對比結果：{'，'.join(parts)}。"

        return SPIDiffResult(
            new_anomalies=new_anomalies,
            resolved_anomalies=resolved_anomalies,
            common_anomalies=common_anomalies,
            transaction_count_delta=tx_delta,
            summary=summary,
            baseline_detected_chip=b_chip,
            candidate_detected_chip=c_chip,
            chip_changed=chip_changed,
        )

