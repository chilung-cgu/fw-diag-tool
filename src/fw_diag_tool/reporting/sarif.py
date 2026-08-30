from __future__ import annotations

import json
from typing import Any

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)


def build_sarif_report(
    tool_name: str,
    tool_version: str,
    findings: list[dict[str, Any]],
) -> str:
    """Build a SARIF 2.1.0 JSON report from diagnostic findings.

    Each finding must contain: code, message, severity, and optionally file/line.
    """
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    severity_map = {
        "CRITICAL": "error",
        "ERROR": "error",
        "WARNING": "warning",
        "INFO": "note",
    }
    for f in findings:
        code = f.get("code", "UNKNOWN")
        rules[code] = {"id": code, "shortDescription": {"text": f.get("title", code)}}
        result: dict[str, Any] = {
            "ruleId": code,
            "level": severity_map.get(f.get("severity", "WARNING"), "warning"),
            "message": {"text": f.get("message", "")},
        }
        if f.get("file"):
            loc = {"physicalLocation": {"artifactLocation": {"uri": f["file"]}}}
            if f.get("line"):
                loc["physicalLocation"]["region"] = {"startLine": f["line"]}
            result["locations"] = [loc]
        results.append(result)

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "version": tool_version,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, ensure_ascii=False) + "\n"


__all__ = ["build_sarif_report"]
