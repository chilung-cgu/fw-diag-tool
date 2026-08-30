"""Tests for the I2C Before/After diff engine."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.i2c.diff import I2CDiffEngine, I2CDiffResult
from fw_diag_tool.i2c.models import (
    AckType,
    I2CAnalysisReport,
    I2CDiagnosticIssue,
    I2CDirection,
    I2CTransaction,
    Severity,
    TimingStatistics,
)


def _transaction(address: int, index: int = 1, *, available: bool = True) -> I2CTransaction:
    return I2CTransaction(
        id=index,
        start_time=float(index),
        end_time=float(index) + 0.001,
        address_7bit=address,
        address_8bit=(address << 1),
        direction=I2CDirection.WRITE,
        address_ack=AckType.ACK,
        address_available=available,
    )


def _issue(title: str, code: str = "I2C_TEST") -> I2CDiagnosticIssue:
    return I2CDiagnosticIssue(
        code=code,
        title=title,
        severity=Severity.WARNING,
        category="Protocol",
        description=title,
        root_cause_analysis="test",
        actionable_advice=["test"],
    )


def _report(
    addresses: list[int],
    anomaly_titles: list[str] | None = None,
    *,
    unavailable_indices: set[int] | None = None,
    total_transactions: int | None = None,
) -> I2CAnalysisReport:
    unavailable_indices = unavailable_indices or set()
    transactions = [
        _transaction(address, index + 1, available=index not in unavailable_indices)
        for index, address in enumerate(addresses)
    ]
    return I2CAnalysisReport(
        total_events=len(transactions),
        total_transactions=(
            len(transactions) if total_transactions is None else total_transactions
        ),
        total_duration_s=0.0,
        devices_detected={},
        transactions=transactions,
        timing_stats=TimingStatistics(),
        issues=[_issue(title) for title in (anomaly_titles or [])],
    )


def test_i2c_diff_identical() -> None:
    result = I2CDiffEngine.compare(_report([0x50, 0x58], ["Address NACK"]), _report([0x50, 0x58], ["Address NACK"]))

    assert isinstance(result, I2CDiffResult)
    assert result.is_identical is True
    assert result.baseline_transaction_count == 2
    assert result.candidate_transaction_count == 2
    assert result.transaction_count_delta == 0
    assert result.new_anomalies == []
    assert result.resolved_anomalies == []
    assert result.common_anomalies == ["Address NACK"]
    assert result.address_changes == []
    assert "完全一致" in result.summary


def test_i2c_diff_anomaly_sets_are_sorted() -> None:
    result = I2CDiffEngine.compare(
        _report([0x50], ["Clock Stretch", "Address NACK"]),
        _report([0x50], ["Clock Stretch", "Data NACK"]),
    )

    assert result.new_anomalies == ["Data NACK"]
    assert result.resolved_anomalies == ["Address NACK"]
    assert result.common_anomalies == ["Clock Stretch"]
    assert result.is_identical is False


def test_i2c_diff_transaction_count_delta() -> None:
    result = I2CDiffEngine.compare(_report([0x50]), _report([0x50, 0x58, 0x20]))

    assert result.baseline_transaction_count == 1
    assert result.candidate_transaction_count == 3
    assert result.transaction_count_delta == 2
    assert "交易數變化 +2" in result.summary


def test_i2c_diff_address_change_by_transaction_position() -> None:
    result = I2CDiffEngine.compare(_report([0x50, 0x58]), _report([0x50, 0x5A]))

    assert result.address_changes == ["交易 #2: 0x58 -> 0x5A"]
    assert result.is_identical is False


def test_i2c_diff_added_transaction_address_is_reported() -> None:
    result = I2CDiffEngine.compare(_report([0x50]), _report([0x50, 0x58]))

    assert result.address_changes == ["交易 #2: 不存在 -> 0x58"]


def test_i2c_diff_removed_transaction_address_is_reported() -> None:
    result = I2CDiffEngine.compare(_report([0x50, 0x58]), _report([0x50]))

    assert result.address_changes == ["交易 #2: 0x58 -> 不存在"]


def test_i2c_diff_unavailable_address_is_explicit() -> None:
    result = I2CDiffEngine.compare(
        _report([0x50], unavailable_indices={0}),
        _report([0x50]),
    )

    assert result.address_changes == ["交易 #1: 未知位址 -> 0x50"]


def test_i2c_diff_type_error() -> None:
    with pytest.raises(TypeError, match="I2CAnalysisReport"):
        I2CDiffEngine.compare("invalid", _report([]))  # type: ignore[arg-type]


def test_i2c_diff_result_is_frozen() -> None:
    result = I2CDiffEngine.compare(_report([]), _report([]))

    with pytest.raises(FrozenInstanceError):
        result.summary = "changed"  # type: ignore[misc]

