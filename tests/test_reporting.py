from __future__ import annotations

import json

from fw_diag_tool.reporting.batch import build_batch_manifest
from fw_diag_tool.reporting.sarif import build_sarif_report


def test_build_sarif_report_structure():
    findings: list[dict[str, str | int]] = [
        {
            "code": "I2C_ADDR_NACK",
            "message": "Address NACK detected",
            "severity": "ERROR",
            "file": "trace.csv",
            "line": 3,
        },
        {"code": "SPI_WEL_STATE_UNKNOWN", "message": "WEL state unknown", "severity": "WARNING"},
    ]
    text = build_sarif_report("fw-diag-tool", "1.1.0", findings)
    data = json.loads(text)

    assert data["version"] == "2.1.0"
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["tool"]["driver"]["name"] == "fw-diag-tool"
    assert len(run["results"]) == 2
    assert run["results"][0]["level"] == "error"
    assert run["results"][1]["level"] == "warning"


def test_build_batch_manifest_counts():
    entries: list[dict[str, str | int]] = [
        {"file": "a.csv", "protocol": "i2c", "status": "success", "findings_count": 2},
        {"file": "b.csv", "protocol": "spi", "status": "warning", "findings_count": 1},
        {"file": "c.csv", "protocol": "mctp", "status": "error"},
    ]
    text = build_batch_manifest(entries)
    data = json.loads(text)
    assert data["total"] == 3
    assert data["passed"] == 1
    assert data["failed"] == 1
