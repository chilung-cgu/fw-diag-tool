"""Collect and export in-memory dashboard usage events."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class UsageEvent:
    """One user action recorded by the dashboard."""

    timestamp: str
    page_name: str
    action: str
    protocol: str | None = None
    duration_ms: float | None = None


class MetricsCollector:
    """Store usage events for the current process only."""

    _CSV_FIELDS = ("timestamp", "page_name", "action", "protocol", "duration_ms")

    def __init__(self) -> None:
        self._events: list[UsageEvent] = []

    def record_event(
        self,
        page_name: str,
        action: str,
        protocol: str | None = None,
        duration_ms: float | None = None,
    ) -> UsageEvent:
        """Record an action and return the immutable event created for it."""
        event = UsageEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            page_name=page_name,
            action=action,
            protocol=protocol,
            duration_ms=float(duration_ms) if duration_ms is not None else None,
        )
        self._events.append(event)
        return event

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Return usage counts grouped by page and protocol."""
        page_usage = Counter(event.page_name for event in self._events)
        protocol_usage = Counter(
            event.protocol for event in self._events if event.protocol is not None
        )
        return {
            "page_usage": dict(page_usage),
            "protocol_usage": dict(protocol_usage),
        }

    def get_recent_events(self, n: int = 20) -> list[UsageEvent]:
        """Return up to ``n`` most recently recorded events."""
        if n <= 0:
            return []
        return self._events[-n:]

    def export_csv(self) -> str:
        """Export all recorded events as a UTF-8-compatible CSV string."""
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=self._CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {
                "timestamp": event.timestamp,
                "page_name": event.page_name,
                "action": event.action,
                "protocol": event.protocol or "",
                "duration_ms": event.duration_ms if event.duration_ms is not None else "",
            }
            for event in self._events
        )
        return output.getvalue()


_METRICS_COLLECTOR = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Return the process-wide usage metrics collector."""
    return _METRICS_COLLECTOR


__all__ = ["MetricsCollector", "UsageEvent", "get_metrics_collector"]
