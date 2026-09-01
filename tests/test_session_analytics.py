"""Tests for multi-session trend analytics engine."""

from __future__ import annotations

from fw_diag_tool.session.analytics import (
    SessionTrendPoint,
    SessionTrendReport,
    analyze_session_trends,
    compute_health_score,
)


def _make_session(
    name: str = "s1",
    protocol: str = "i2c",
    anomaly_count: int = 5,
    transactions: int = 100,
    status: str = "warning",
    created_at: str = "2026-01-01",
) -> dict:
    return {
        "name": name,
        "created_at": created_at,
        "config": {"protocol": protocol},
        "report": {
            "total_transactions": transactions,
            "anomaly_count": anomaly_count,
            "status": status,
        },
    }


class TestAnalyzeSessionTrends:
    """Core trend analysis tests."""

    def test_empty_sessions(self) -> None:
        report = analyze_session_trends([])
        assert isinstance(report, SessionTrendReport)
        assert report.points == []
        assert report.anomaly_trend == "stable"
        assert "No session data" in report.summary

    def test_single_session(self) -> None:
        report = analyze_session_trends([_make_session()])
        assert len(report.points) == 1
        assert report.anomaly_trend == "stable"
        assert report.points[0].session_name == "s1"

    def test_improving_trend(self) -> None:
        sessions = [
            _make_session(name="s1", anomaly_count=10, created_at="2026-01-01"),
            _make_session(name="s2", anomaly_count=5, created_at="2026-01-02"),
            _make_session(name="s3", anomaly_count=2, created_at="2026-01-03"),
        ]
        report = analyze_session_trends(sessions)
        assert report.anomaly_trend == "improving"
        assert "reduction" in report.summary.lower() or "decreased" in report.summary.lower()

    def test_degrading_trend(self) -> None:
        sessions = [
            _make_session(name="s1", anomaly_count=1, created_at="2026-01-01"),
            _make_session(name="s2", anomaly_count=5, created_at="2026-01-02"),
            _make_session(name="s3", anomaly_count=12, created_at="2026-01-03"),
        ]
        report = analyze_session_trends(sessions)
        assert report.anomaly_trend == "degrading"
        assert "increase" in report.summary.lower()

    def test_stable_trend(self) -> None:
        sessions = [
            _make_session(name="s1", anomaly_count=3, created_at="2026-01-01"),
            _make_session(name="s2", anomaly_count=3, created_at="2026-01-02"),
        ]
        report = analyze_session_trends(sessions)
        assert report.anomaly_trend == "stable"

    def test_zero_anomalies_maintained(self) -> None:
        sessions = [
            _make_session(name="s1", anomaly_count=0, created_at="2026-01-01"),
            _make_session(name="s2", anomaly_count=0, created_at="2026-01-02"),
        ]
        report = analyze_session_trends(sessions)
        assert report.anomaly_trend == "stable"
        assert "zero anomalies" in report.summary.lower()

    def test_sorts_by_created_at(self) -> None:
        sessions = [
            _make_session(name="later", anomaly_count=1, created_at="2026-02-01"),
            _make_session(name="earlier", anomaly_count=10, created_at="2026-01-01"),
        ]
        report = analyze_session_trends(sessions)
        assert report.points[0].session_name == "earlier"
        assert report.points[1].session_name == "later"

    def test_protocol_extraction(self) -> None:
        sessions = [
            _make_session(protocol="spi"),
            _make_session(protocol="i2c"),
        ]
        report = analyze_session_trends(sessions)
        protocols = {p.protocol for p in report.points}
        assert protocols == {"spi", "i2c"}

    def test_fallback_name_from_index(self) -> None:
        session = {"report": {"anomaly_count": 0}, "config": {}}
        report = analyze_session_trends([session])
        assert report.points[0].session_name == "Session #1"

    def test_anomaly_list_counting(self) -> None:
        session = {
            "name": "list-test",
            "created_at": "2026-01-01",
            "config": {"protocol": "i2c"},
            "report": {
                "anomalies": [{"type": "nack"}, {"type": "timeout"}, {"type": "arb-lost"}],
            },
        }
        report = analyze_session_trends([session])
        assert report.points[0].anomaly_count == 3

    def test_transaction_list_counting(self) -> None:
        session = {
            "name": "txn-test",
            "created_at": "2026-01-01",
            "config": {"protocol": "spi"},
            "report": {
                "transactions": [{"op": "read"}, {"op": "write"}],
            },
        }
        report = analyze_session_trends([session])
        assert report.points[0].total_transactions == 2

    def test_summary_includes_protocol(self) -> None:
        sessions = [_make_session(protocol="pcie")]
        report = analyze_session_trends(sessions)
        assert "pcie" in report.summary.lower()


class TestSessionTrendPoint:
    """Data class sanity tests."""

    def test_frozen(self) -> None:
        p = SessionTrendPoint(
            session_name="x",
            created_at="2026-01-01",
            protocol="i2c",
            total_transactions=10,
            anomaly_count=2,
            status="warning",
        )
        try:
            p.session_name = "y"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestHealthScore:
    """Health score calculation tests."""

    def test_zero_transactions_returns_perfect_score(self) -> None:
        point = SessionTrendPoint("empty", "2026-01-01", "i2c", 0, 4, "warning")
        assert compute_health_score(point) == 100.0

    def test_no_anomalies_returns_perfect_score(self) -> None:
        point = SessionTrendPoint("clean", "2026-01-01", "i2c", 100, 0, "success")
        assert compute_health_score(point) == 100.0

    def test_anomaly_ratio_uses_multiplier(self) -> None:
        point = SessionTrendPoint("mixed", "2026-01-01", "i2c", 100, 5, "warning")
        assert compute_health_score(point) == 75.0

    def test_score_is_clamped_at_zero(self) -> None:
        point = SessionTrendPoint("bad", "2026-01-01", "i2c", 10, 3, "error")
        assert compute_health_score(point) == 0.0


def test_session_analytics_sample_sessions_generator() -> None:
    from fw_diag_tool.gui.pages.session_analytics_ui import _get_sample_trend_sessions

    samples = _get_sample_trend_sessions()
    assert len(samples) >= 3
    assert all("report" in s and "config" in s for s in samples)


def test_session_analytics_sample_trend_analysis() -> None:
    from fw_diag_tool.gui.pages.session_analytics_ui import (
        _build_trend_summary_markdown,
        _comparison_dataframe,
        _get_sample_trend_sessions,
    )

    samples = _get_sample_trend_sessions()
    report = analyze_session_trends(samples)
    assert report.anomaly_trend == "improving"
    assert len(report.points) == 3

    df = _comparison_dataframe(report)
    assert len(df) == 3
    assert list(df["Anomalies"]) == [8, 3, 0]

    md = _build_trend_summary_markdown(report)
    assert "# Session Trend Summary" in md
    assert "Stage 1 - Initial Bringup" in md
    assert "Stage 3 - Final Sign-off" in md
