"""Log differential comparison engine and structured diff models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fw_diag_tool.log.models import LogReport


@dataclass(frozen=True)
class LogDiffResult:
    """Structured result of differential comparison between baseline and candidate log reports."""

    baseline_event_count: int = 0
    candidate_event_count: int = 0
    event_count_delta: int = 0
    new_incidents: list[str] = field(default_factory=list)
    resolved_incidents: list[str] = field(default_factory=list)
    common_incidents: list[str] = field(default_factory=list)
    new_event_patterns: list[str] = field(default_factory=list)
    resolved_event_patterns: list[str] = field(default_factory=list)
    summary: str = ""
    is_identical: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert diff result to dictionary."""
        return {
            "baseline_event_count": self.baseline_event_count,
            "candidate_event_count": self.candidate_event_count,
            "event_count_delta": self.event_count_delta,
            "new_incidents": self.new_incidents,
            "resolved_incidents": self.resolved_incidents,
            "common_incidents": self.common_incidents,
            "new_event_patterns": self.new_event_patterns,
            "resolved_event_patterns": self.resolved_event_patterns,
            "summary": self.summary,
            "is_identical": self.is_identical,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize diff result as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class LogDiffEngine:
    """Differential comparison engine for comparing diagnostic log reports."""

    @classmethod
    def compare(cls, baseline: LogReport, candidate: LogReport) -> LogDiffResult:
        """Compare baseline and candidate LogReport objects and compute differences.

        Args:
            baseline: LogReport representing the baseline state.
            candidate: LogReport representing the candidate/new state.

        Returns:
            LogDiffResult summarizing added, resolved, and common incidents/patterns.
        """
        base_titles = {inc.title for inc in baseline.incidents if inc.title}
        cand_titles = {inc.title for inc in candidate.incidents if inc.title}

        new_incidents = sorted(cand_titles - base_titles)
        resolved_incidents = sorted(base_titles - cand_titles)
        common_incidents = sorted(base_titles & cand_titles)

        base_patterns = {ev.pattern_id for ev in baseline.events if ev.pattern_id}
        cand_patterns = {ev.pattern_id for ev in candidate.events if ev.pattern_id}

        new_event_patterns = sorted(cand_patterns - base_patterns)
        resolved_event_patterns = sorted(base_patterns - cand_patterns)

        baseline_event_count = len(baseline.events)
        candidate_event_count = len(candidate.events)
        event_count_delta = candidate_event_count - baseline_event_count

        is_identical = (
            not new_incidents
            and not resolved_incidents
            and not new_event_patterns
            and not resolved_event_patterns
        )

        if is_identical:
            summary = "Log reports are identical in detected events and incidents."
        else:
            parts: list[str] = []
            if new_incidents:
                parts.append(f"{len(new_incidents)} new incident(s)")
            if resolved_incidents:
                parts.append(f"{len(resolved_incidents)} resolved incident(s)")
            if new_event_patterns:
                parts.append(f"{len(new_event_patterns)} new pattern(s)")
            if resolved_event_patterns:
                parts.append(f"{len(resolved_event_patterns)} resolved pattern(s)")

            delta_sign = f"+{event_count_delta}" if event_count_delta > 0 else f"{event_count_delta}"
            parts.append(f"event count delta: {delta_sign}")
            summary = "; ".join(parts)

        return LogDiffResult(
            baseline_event_count=baseline_event_count,
            candidate_event_count=candidate_event_count,
            event_count_delta=event_count_delta,
            new_incidents=new_incidents,
            resolved_incidents=resolved_incidents,
            common_incidents=common_incidents,
            new_event_patterns=new_event_patterns,
            resolved_event_patterns=resolved_event_patterns,
            summary=summary,
            is_identical=is_identical,
        )
