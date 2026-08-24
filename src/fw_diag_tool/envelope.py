from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    _TOOL_VERSION = version("fw-diag-tool")
except PackageNotFoundError:
    _TOOL_VERSION = "0+unknown"


@dataclass
class DiagnosticReportEnvelope:
    """Standard diagnostic report envelope format for CI and batch pipelines."""

    schema_version: str = "1.0"
    tool_version: str = _TOOL_VERSION
    created_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    protocol: str = ""
    status: str = "success"  # "success", "warning", "error", "partial"
    input_sha256: str | None = None
    findings_count: int = 0
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    data_quality_issues: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "created_at": self.created_at,
            "protocol": self.protocol,
            "status": self.status,
            "input_sha256": self.input_sha256,
            "findings_count": self.findings_count,
            "anomalies": self.anomalies,
            "data_quality_issues": self.data_quality_issues,
            "payload": self.payload,
            "notes": self.notes,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"


__all__ = ["DiagnosticReportEnvelope"]
