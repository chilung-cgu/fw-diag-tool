"""Tests for SARIF report generation and GUI export helpers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fw_diag_tool.gui.sarif_export import render_sarif_download
from fw_diag_tool.reporting.sarif import build_sarif_report


def test_build_sarif_report_empty_findings() -> None:
    """Empty findings list should produce a valid SARIF report with 0 results."""
    sarif_str = build_sarif_report(
        tool_name="fw-diag-tool",
        tool_version="1.1.1",
        findings=[],
    )
    data = json.loads(sarif_str)
    assert data["version"] == "2.1.0"
    assert data["$schema"].startswith("https://")
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["tool"]["driver"]["name"] == "fw-diag-tool"
    assert run["tool"]["driver"]["version"] == "1.1.1"
    assert run["tool"]["driver"]["rules"] == []
    assert run["results"] == []


def test_build_sarif_report_severity_mapping() -> None:
    """Verify severity mapping across CRITICAL, ERROR, WARNING, INFO, and fallback."""
    findings: list[dict[str, Any]] = [
        {"code": "ERR_CRIT", "message": "Fatal bus lock", "severity": "CRITICAL"},
        {"code": "ERR_STD", "message": "Parity error", "severity": "ERROR"},
        {"code": "WARN_STRETCH", "message": "Clock stretching", "severity": "WARNING"},
        {"code": "INFO_ADDR", "message": "Address seen", "severity": "INFO"},
        {"code": "CUSTOM_SEV", "message": "Unknown severity", "severity": "UNKNOWN_VAL"},
    ]
    sarif_str = build_sarif_report("fw-diag-tool", "1.1.1", findings)
    data = json.loads(sarif_str)
    results = data["runs"][0]["results"]
    assert len(results) == 5
    assert results[0]["level"] == "error"
    assert results[1]["level"] == "error"
    assert results[2]["level"] == "warning"
    assert results[3]["level"] == "note"
    assert results[4]["level"] == "warning"  # fallback default


def test_build_sarif_report_locations_and_rules() -> None:
    """Verify location reporting (file and line) and rule shortDescription."""
    findings: list[dict[str, Any]] = [
        {
            "code": "I2C_ADDR_NACK",
            "title": "I2C Address NACK Condition",
            "message": "Slave did not acknowledge address byte",
            "severity": "ERROR",
            "file": "capture.csv",
            "line": 42,
        },
        {
            "code": "SPI_MODE_MISMATCH",
            "message": "CPOL/CPHA configuration mismatch",
            "severity": "WARNING",
            "file": "spi_trace.bin",
        },
    ]
    sarif_str = build_sarif_report("fw-diag-tool", "1.1.1", findings)
    data = json.loads(sarif_str)
    run = data["runs"][0]

    rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    assert "I2C_ADDR_NACK" in rules
    assert rules["I2C_ADDR_NACK"]["shortDescription"]["text"] == "I2C Address NACK Condition"
    assert rules["SPI_MODE_MISMATCH"]["shortDescription"]["text"] == "SPI_MODE_MISMATCH"

    results = run["results"]
    assert len(results) == 2
    assert (
        results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "capture.csv"
    )
    assert results[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 42
    assert (
        results[1]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "spi_trace.bin"
    )
    assert "region" not in results[1]["locations"][0]["physicalLocation"]


def test_render_sarif_download_empty_noop() -> None:
    """render_sarif_download should do nothing if findings is empty."""
    # Should return cleanly without error
    render_sarif_download([], protocol="I2C")


def test_render_sarif_download_invokes_streamlit(monkeypatch: pytest.MonkeyPatch) -> None:
    """render_sarif_download should call st.download_button with expected arguments."""
    download_calls: list[dict[str, Any]] = []

    def mock_download_button(label: str, data: str, file_name: str, mime: str, key: str) -> None:
        download_calls.append(
            {
                "label": label,
                "data": data,
                "file_name": file_name,
                "mime": mime,
                "key": key,
            }
        )

    import streamlit as st

    monkeypatch.setattr(st, "download_button", mock_download_button)

    findings: list[dict[str, Any]] = [
        {"code": "I2C_TIMEOUT", "message": "Bus timeout", "severity": "ERROR"}
    ]
    render_sarif_download(findings, protocol="I2C", filename_prefix="diag")

    assert len(download_calls) == 1
    call = download_calls[0]
    assert "I2C" in call["label"]
    assert call["file_name"] == "diag_i2c.sarif.json"
    assert call["mime"] == "application/json"
    assert call["key"] == "sarif_download_i2c"
    parsed = json.loads(call["data"])
    assert parsed["version"] == "2.1.0"
    assert len(parsed["runs"][0]["results"]) == 1
