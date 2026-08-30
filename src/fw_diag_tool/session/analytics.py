"""Multi-session trend analytics for firmware diagnostic reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionTrendPoint:
    """Key metrics snapshot from a single diagnostic session."""

    session_name: str
    created_at: str
    protocol: str
    total_transactions: int
    anomaly_count: int
    status: str  # "success" / "warning" / "error"


@dataclass(frozen=True)
class SessionTrendReport:
    """Trend analysis across multiple diagnostic sessions."""

    points: list[SessionTrendPoint]
    anomaly_trend: str  # "improving" / "stable" / "degrading"
    summary: str


def compute_health_score(point: SessionTrendPoint) -> float:
    """Compute a 0-100 health score from a session trend point."""
    if point.total_transactions == 0:
        return 100.0
    return max(
        0.0,
        100.0 - (point.anomaly_count / point.total_transactions) * 100.0 * 5,
    )


def _extract_trend_point(payload: dict[str, Any], index: int) -> SessionTrendPoint:
    """Extract a SessionTrendPoint from a session payload dict."""
    report = payload.get("report", {})
    config = payload.get("config", {})

    name = payload.get("name") or f"Session #{index + 1}"
    created_at = payload.get("created_at", "unknown")
    protocol = config.get("protocol", report.get("protocol", "unknown"))

    transactions = 0
    for key in ("total_transactions", "transaction_count", "transactions"):
        val = report.get(key)
        if isinstance(val, int):
            transactions = val
            break
    if transactions == 0:
        txn_list = report.get("transactions")
        if isinstance(txn_list, list):
            transactions = len(txn_list)

    anomaly_count = 0
    for key in ("anomaly_count", "anomalies_count"):
        val = report.get(key)
        if isinstance(val, int):
            anomaly_count = val
            break
    if anomaly_count == 0:
        anomalies = report.get("anomalies")
        if isinstance(anomalies, list):
            anomaly_count = len(anomalies)

    status = report.get("status", "success")
    if not isinstance(status, str):
        status = "success"
    if status not in ("success", "warning", "error"):
        if anomaly_count > 0:
            status = "warning"
        else:
            status = "success"

    return SessionTrendPoint(
        session_name=str(name),
        created_at=str(created_at),
        protocol=str(protocol),
        total_transactions=transactions,
        anomaly_count=anomaly_count,
        status=status,
    )


def _determine_trend(points: list[SessionTrendPoint]) -> str:
    """Determine anomaly trend from the last 3 sessions."""
    if len(points) < 2:
        return "stable"

    recent = points[-3:] if len(points) >= 3 else points
    counts = [p.anomaly_count for p in recent]

    if all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1)):
        if counts[0] > counts[-1]:
            return "improving"
        return "stable"
    if all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1)):
        if counts[-1] > counts[0]:
            return "degrading"
        return "stable"
    return "stable"


def _build_summary(points: list[SessionTrendPoint], trend: str) -> str:
    """Generate a natural-language trend summary."""
    if not points:
        return "No session data available for analysis."

    total_sessions = len(points)
    total_anomalies = sum(p.anomaly_count for p in points)
    total_transactions = sum(p.total_transactions for p in points)
    protocols = sorted({p.protocol for p in points if p.protocol != "unknown"})

    trend_labels = {
        "improving": "improving",
        "stable": "stable",
        "degrading": "degrading",
    }
    trend_label = trend_labels.get(trend, trend)

    parts = [
        f"Analyzed {total_sessions} sessions",
    ]
    if protocols:
        parts.append(f"protocols: {', '.join(protocols)}")
    parts.append(
        f"total transactions {total_transactions:,}, total anomalies {total_anomalies:,}"
    )
    parts.append(f"trend: {trend_label}")

    if total_sessions >= 2:
        first = points[0].anomaly_count
        last = points[-1].anomaly_count
        if first > 0:
            delta_pct = ((last - first) / first) * 100
            if delta_pct < 0:
                parts.append(
                    f"anomalies decreased from {first} to {last} ({abs(delta_pct):.0f}% reduction)"
                )
            elif delta_pct > 0:
                parts.append(
                    f"anomalies increased from {first} to {last} ({delta_pct:.0f}% increase)"
                )
            else:
                parts.append(f"anomalies unchanged at {first}")
        else:
            if last > 0:
                parts.append(f"anomalies increased from 0 to {last}")
            else:
                parts.append("zero anomalies maintained")

    return ". ".join(parts) + "."


def analyze_session_trends(sessions: list[dict[str, Any]]) -> SessionTrendReport:
    """Analyze trends across multiple session payloads."""
    points: list[SessionTrendPoint] = []
    for i, payload in enumerate(sessions):
        points.append(_extract_trend_point(payload, i))

    def _sort_key(p: SessionTrendPoint) -> str:
        return p.created_at if p.created_at != "unknown" else ""

    points.sort(key=_sort_key)
    trend = _determine_trend(points)
    summary = _build_summary(points, trend)

    return SessionTrendReport(points=points, anomaly_trend=trend, summary=summary)


__all__ = [
    "SessionTrendPoint",
    "SessionTrendReport",
    "analyze_session_trends",
    "compute_health_score",
]
