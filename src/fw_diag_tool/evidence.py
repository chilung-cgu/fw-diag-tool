from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceLevel(str, Enum):
    MEASURED = "Measured"
    INFERRED = "Inferred"
    RECONSTRUCTED = "Reconstructed"
    UNAVAILABLE = "Unavailable"


@dataclass(frozen=True)
class EvidenceMetric:
    """A typed metric with explicit provenance and availability information."""

    value: float | None
    sample_count: int = 0
    source: str = ""
    level: EvidenceLevel = EvidenceLevel.UNAVAILABLE
    unit: str = ""
    availability_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def measured(
        cls,
        value: float,
        *,
        sample_count: int,
        source: str,
        unit: str = "",
        **extra: Any,
    ) -> EvidenceMetric:
        return cls(
            value=value,
            sample_count=sample_count,
            source=source,
            level=EvidenceLevel.MEASURED,
            unit=unit,
            extra=dict(extra),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        reason: str,
        source: str = "",
        unit: str = "",
    ) -> EvidenceMetric:
        return cls(
            value=None,
            source=source,
            level=EvidenceLevel.UNAVAILABLE,
            unit=unit,
            availability_reason=reason,
        )

    @property
    def is_available(self) -> bool:
        return self.value is not None and self.level != EvidenceLevel.UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "value": self.value,
            "sample_count": self.sample_count,
            "source": self.source,
            "level": self.level.value,
        }
        if self.unit:
            result["unit"] = self.unit
        if self.availability_reason is not None:
            result["availability_reason"] = self.availability_reason
        if self.extra:
            result.update(self.extra)
        return result


__all__ = ["EvidenceLevel", "EvidenceMetric"]
