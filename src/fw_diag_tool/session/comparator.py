"""Pairwise comparison of firmware diagnostic sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionComparison:
    """Comparison result for a baseline and candidate session."""

    baseline_name: str
    candidate_name: str
    metric_deltas: dict[str, Any]
    verdict: str
    summary: str


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report", payload)
    return report if isinstance(report, dict) else {}


def _metric(report: dict[str, Any], keys: tuple[str, ...], list_key: str) -> int:
    value = 0
    for key in keys:
        candidate = report.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            value = candidate
            break
    if value == 0:
        values = report.get(list_key)
        if isinstance(values, list):
            value = len(values)
    return value


def _name(payload: dict[str, Any], fallback: str) -> str:
    value = payload.get("name")
    return str(value) if value else fallback


def _protocol(payload: dict[str, Any], report: dict[str, Any]) -> str:
    config = payload.get("config", {})
    if isinstance(config, dict):
        value = config.get("protocol")
        if value is not None:
            return str(value)
    value = report.get("protocol")
    return str(value) if value is not None else "unknown"


def compare_sessions(baseline: dict[str, Any], candidate: dict[str, Any]) -> SessionComparison:
    """Compare anomaly, transaction, and protocol metrics between sessions."""
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise TypeError("baseline and candidate must be mappings")

    baseline_report = _report(baseline)
    candidate_report = _report(candidate)
    baseline_anomalies = _metric(baseline_report, ("anomaly_count", "anomalies_count"), "anomalies")
    candidate_anomalies = _metric(candidate_report, ("anomaly_count", "anomalies_count"), "anomalies")
    baseline_transactions = _metric(
        baseline_report,
        ("total_transactions", "transaction_count", "transactions"),
        "transactions",
    )
    candidate_transactions = _metric(
        candidate_report,
        ("total_transactions", "transaction_count", "transactions"),
        "transactions",
    )
    baseline_protocol = _protocol(baseline, baseline_report)
    candidate_protocol = _protocol(candidate, candidate_report)

    anomaly_delta = candidate_anomalies - baseline_anomalies
    if anomaly_delta < 0:
        verdict = "improved"
    elif anomaly_delta > 0:
        verdict = "degraded"
    else:
        verdict = "unchanged"

    metric_deltas: dict[str, Any] = {
        "anomaly_count": anomaly_delta,
        "total_transactions": candidate_transactions - baseline_transactions,
        "protocol": {
            "baseline": baseline_protocol,
            "candidate": candidate_protocol,
            "changed": baseline_protocol != candidate_protocol,
        },
    }
    summary = (
        f"Session comparison: {verdict}. "
        f"Anomaly count {baseline_anomalies} -> {candidate_anomalies} ({anomaly_delta:+d}); "
        f"total transactions {baseline_transactions} -> {candidate_transactions} "
        f"({metric_deltas['total_transactions']:+d}); "
        f"protocol {baseline_protocol} -> {candidate_protocol}."
    )
    return SessionComparison(
        baseline_name=_name(baseline, "Baseline"),
        candidate_name=_name(candidate, "Candidate"),
        metric_deltas=metric_deltas,
        verdict=verdict,
        summary=summary,
    )


__all__ = ["SessionComparison", "compare_sessions"]
