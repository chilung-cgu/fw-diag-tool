"""Tests for pairwise session comparison."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.session.comparator import SessionComparison, compare_sessions


def _session(
    name: str = "baseline",
    protocol: str = "i2c",
    anomalies: int = 4,
    transactions: int = 20,
) -> dict:
    return {
        "name": name,
        "config": {"protocol": protocol},
        "report": {
            "anomaly_count": anomalies,
            "total_transactions": transactions,
        },
    }


def test_compare_sessions_returns_frozen_result() -> None:
    result = compare_sessions(_session(), _session(name="candidate"))
    assert isinstance(result, SessionComparison)
    with pytest.raises(AttributeError):
        result.verdict = "degraded"  # type: ignore[misc]


def test_extracts_names_and_numeric_deltas() -> None:
    result = compare_sessions(
        _session(anomalies=8, transactions=10), _session(name="v2", anomalies=3, transactions=17)
    )
    assert result.baseline_name == "baseline"
    assert result.candidate_name == "v2"
    assert result.metric_deltas["anomaly_count"] == -5
    assert result.metric_deltas["total_transactions"] == 7


def test_protocol_delta_reports_values_and_change() -> None:
    result = compare_sessions(_session(), _session(name="v2", protocol="spi"))
    protocol = result.metric_deltas["protocol"]
    assert protocol == {"baseline": "i2c", "candidate": "spi", "changed": True}


def test_same_protocol_is_not_marked_changed() -> None:
    result = compare_sessions(_session(), _session(name="v2"))
    assert result.metric_deltas["protocol"]["changed"] is False


def test_lower_anomaly_count_is_improved() -> None:
    result = compare_sessions(_session(anomalies=4), _session(name="v2", anomalies=1))
    assert result.verdict == "improved"
    assert "improv" in result.summary.lower()


def test_higher_anomaly_count_is_degraded() -> None:
    result = compare_sessions(_session(anomalies=1), _session(name="v2", anomalies=5))
    assert result.verdict == "degraded"
    assert "degrad" in result.summary.lower()


def test_equal_anomaly_count_is_unchanged() -> None:
    result = compare_sessions(_session(anomalies=2), _session(name="v2", anomalies=2))
    assert result.verdict == "unchanged"


def test_supports_list_fallbacks_and_report_protocol() -> None:
    baseline = {"name": "old", "report": {"anomalies": [1, 2], "transactions": [1]}}
    candidate = {
        "name": "new",
        "report": {"anomalies": [1], "transactions": [1, 2], "protocol": "uart"},
    }
    result = compare_sessions(baseline, candidate)
    assert result.metric_deltas["anomaly_count"] == -1
    assert result.metric_deltas["total_transactions"] == 1
    assert result.metric_deltas["protocol"]["candidate"] == "uart"


def test_missing_metrics_default_to_zero_and_unknown_protocol() -> None:
    result = compare_sessions({}, {})
    assert result.metric_deltas["anomaly_count"] == 0
    assert result.metric_deltas["total_transactions"] == 0
    assert result.metric_deltas["protocol"]["baseline"] == "unknown"


def test_rejects_non_mapping_payloads() -> None:
    with pytest.raises(TypeError):
        compare_sessions([], {})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compare_sessions({}, [])  # type: ignore[arg-type]


def test_cli_renders_comparison_and_exports_reports(tmp_path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "comparison.md"
    json_path = tmp_path / "comparison.json"
    baseline_path.write_text('{"name":"old","report":{"anomaly_count":3,"total_transactions":10}}')
    candidate_path.write_text('{"name":"new","report":{"anomaly_count":1,"total_transactions":12}}')

    result = CliRunner().invoke(
        app,
        [
            "compare",
            str(baseline_path),
            str(candidate_path),
            "--md",
            str(markdown_path),
            "--json",
            str(json_path),
        ],
    )
    assert result.exit_code == 0
    assert "Session Comparison" in result.output
    assert markdown_path.exists()
    assert '"verdict": "improved"' in json_path.read_text()


def test_cli_rejects_missing_session_file(tmp_path) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text("{}")
    result = CliRunner().invoke(app, ["compare", str(existing), str(tmp_path / "missing.json")])
    assert result.exit_code == 1
    assert "Both files must exist" in result.output
