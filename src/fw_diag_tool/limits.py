"""Shared resource limits for bounded diagnostic analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisLimits:
    """Upper bounds applied at analysis input and result boundaries."""

    max_upload_bytes: int = 20 * 1024 * 1024
    max_text_bytes: int = 2 * 1024 * 1024
    max_records: int = 50_000
    max_transitions: int = 50_000
    max_transactions: int = 25_000
    max_findings: int = 5_000
    max_render_rows: int = 2_000
    max_session_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_upload_bytes", self.max_upload_bytes),
            ("max_text_bytes", self.max_text_bytes),
            ("max_records", self.max_records),
            ("max_transitions", self.max_transitions),
            ("max_transactions", self.max_transactions),
            ("max_findings", self.max_findings),
            ("max_render_rows", self.max_render_rows),
            ("max_session_bytes", self.max_session_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_ANALYSIS_LIMITS = AnalysisLimits()


def coerce_limits(limits: AnalysisLimits | None) -> AnalysisLimits:
    if limits is None:
        return DEFAULT_ANALYSIS_LIMITS
    if not isinstance(limits, AnalysisLimits):
        raise TypeError("limits must be an AnalysisLimits instance or None")
    return limits


__all__ = ["DEFAULT_ANALYSIS_LIMITS", "AnalysisLimits", "coerce_limits"]
