"""I2C Before/After analysis and diff engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import I2CAnalysisReport, I2CTransaction


@dataclass(frozen=True)
class I2CDiffResult:
    """Structured differences between two I2C analysis reports."""

    baseline_transaction_count: int = 0
    candidate_transaction_count: int = 0
    transaction_count_delta: int = 0
    new_anomalies: list[str] = field(default_factory=list)
    resolved_anomalies: list[str] = field(default_factory=list)
    common_anomalies: list[str] = field(default_factory=list)
    address_changes: list[str] = field(default_factory=list)
    summary: str = ""
    is_identical: bool = False


class I2CDiffEngine:
    """Compare baseline and candidate I2C analysis reports."""

    @staticmethod
    def _address_label(transaction: I2CTransaction | None) -> str:
        if transaction is None:
            return "不存在"
        if not getattr(transaction, "address_available", True):
            return "未知位址"
        address = getattr(transaction, "address_7bit", None)
        if not isinstance(address, int) or isinstance(address, bool):
            return "未知位址"
        return f"0x{address:02X}"

    @classmethod
    def _address_changes(
        cls,
        baseline_report: I2CAnalysisReport,
        candidate_report: I2CAnalysisReport,
    ) -> list[str]:
        baseline_transactions = baseline_report.transactions
        candidate_transactions = candidate_report.transactions
        changes: list[str] = []
        for index in range(max(len(baseline_transactions), len(candidate_transactions))):
            baseline_tx = baseline_transactions[index] if index < len(baseline_transactions) else None
            candidate_tx = (
                candidate_transactions[index] if index < len(candidate_transactions) else None
            )
            baseline_address = cls._address_label(baseline_tx)
            candidate_address = cls._address_label(candidate_tx)
            if baseline_address != candidate_address:
                changes.append(
                    f"交易 #{index + 1}: {baseline_address} -> {candidate_address}"
                )
        return changes

    @classmethod
    def compare(
        cls,
        baseline_report: I2CAnalysisReport,
        candidate_report: I2CAnalysisReport,
    ) -> I2CDiffResult:
        """Compare two I2C analysis reports and return a frozen result."""
        if not isinstance(baseline_report, I2CAnalysisReport) or not isinstance(
            candidate_report, I2CAnalysisReport
        ):
            raise TypeError(
                "baseline_report and candidate_report must be I2CAnalysisReport instances"
            )

        baseline_anomalies = {issue.title for issue in baseline_report.issues}
        candidate_anomalies = {issue.title for issue in candidate_report.issues}
        new_anomalies = sorted(candidate_anomalies - baseline_anomalies)
        resolved_anomalies = sorted(baseline_anomalies - candidate_anomalies)
        common_anomalies = sorted(baseline_anomalies & candidate_anomalies)

        baseline_count = baseline_report.total_transactions
        candidate_count = candidate_report.total_transactions
        transaction_delta = candidate_count - baseline_count
        address_changes = cls._address_changes(baseline_report, candidate_report)
        identical = (
            transaction_delta == 0
            and not new_anomalies
            and not resolved_anomalies
            and not address_changes
        )

        if identical:
            summary = "Baseline 與 Candidate I2C 報告完全一致，未發現新增、修復或位址變更。"
        else:
            parts = [
                f"交易數變化 {transaction_delta:+d}（{baseline_count} -> {candidate_count}）",
                f"新增 {len(new_anomalies)} 項異常",
                f"修復 {len(resolved_anomalies)} 項異常",
                f"位址變更 {len(address_changes)} 項",
            ]
            summary = f"I2C 對比結果：{'，'.join(parts)}。"

        return I2CDiffResult(
            baseline_transaction_count=baseline_count,
            candidate_transaction_count=candidate_count,
            transaction_count_delta=transaction_delta,
            new_anomalies=new_anomalies,
            resolved_anomalies=resolved_anomalies,
            common_anomalies=common_anomalies,
            address_changes=address_changes,
            summary=summary,
            is_identical=identical,
        )


__all__ = ["I2CDiffEngine", "I2CDiffResult"]
