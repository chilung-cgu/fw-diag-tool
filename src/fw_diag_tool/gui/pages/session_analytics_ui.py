"""Multi-Session Trend Analysis Dashboard."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.gui.theme import get_plotly_template
from fw_diag_tool.session.analytics import (
    SessionTrendReport,
    analyze_session_trends,
    compute_health_score,
)


def _load_sessions(uploaded_files: list[Any]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for f in uploaded_files:
        try:
            content = f.read().decode("utf-8")
            payload = json.loads(content)
            if isinstance(payload, dict):
                if "name" not in payload:
                    payload["name"] = f.name.replace(".fwsession.json", "").replace(".json", "")
                sessions.append(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            st.warning(f"Unable to parse: {f.name}")
    return sessions


def _render_metrics(report: SessionTrendReport) -> None:
    if not report.points:
        return
    col1, col2, col3, col4 = st.columns(4)
    total_sessions = len(report.points)
    latest = report.points[-1]
    earliest = report.points[0]
    anomaly_delta = latest.anomaly_count - earliest.anomaly_count
    delta_str = f"{anomaly_delta:+d}" if total_sessions > 1 else None
    with col1:
        st.metric("Sessions", total_sessions)
    with col2:
        st.metric("Latest Anomalies", latest.anomaly_count, delta=delta_str, delta_color="inverse")
    with col3:
        trend_labels = {"improving": "Improving", "stable": "Stable", "degrading": "Degrading"}
        st.metric("Trend", trend_labels.get(report.anomaly_trend, report.anomaly_trend))
    with col4:
        st.metric("Health Score", f"{compute_health_score(latest):.1f}")


def _render_trend_chart(report: SessionTrendReport) -> None:
    if len(report.points) < 2:
        st.info("Upload at least 2 sessions to see trend charts.")
        return
    fig = go.Figure()
    names = [p.session_name for p in report.points]
    anomalies = [p.anomaly_count for p in report.points]
    transactions = [p.total_transactions for p in report.points]
    health_scores = [compute_health_score(p) for p in report.points]
    fig.add_trace(
        go.Scatter(
            x=names,
            y=anomalies,
            mode="lines+markers",
            name="Anomalies",
            marker={"size": 10, "color": "#ef4444"},
            line={"width": 3, "color": "#ef4444"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=names,
            y=transactions,
            mode="lines+markers",
            name="Transactions",
            marker={"size": 8, "color": "#0ea5e9"},
            line={"width": 2, "color": "#0ea5e9", "dash": "dot"},
            yaxis="y2",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=names,
            y=health_scores,
            mode="lines+markers",
            name="Health Score",
            marker={"size": 8, "color": "#22c55e"},
            line={"width": 2, "color": "#22c55e"},
        )
    )
    fig.update_layout(
        template=get_plotly_template(),
        title="Session Trend",
        xaxis_title="Session",
        yaxis={"title": "Anomaly Count", "side": "left"},
        yaxis2={"title": "Transaction Count", "side": "right", "overlaying": "y"},
        height=400,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    st.plotly_chart(fig, use_container_width=True)


def _comparison_dataframe(report: SessionTrendReport) -> pd.DataFrame:
    rows = [
        {
            "Session": p.session_name,
            "Created": p.created_at,
            "Protocol": p.protocol,
            "Transactions": p.total_transactions,
            "Anomalies": p.anomaly_count,
            "Status": p.status,
        }
        for p in report.points
    ]
    return pd.DataFrame(rows)


def _render_comparison_table(report: SessionTrendReport) -> None:
    if not report.points:
        return
    st.dataframe(_comparison_dataframe(report), use_container_width=True, hide_index=True)


def _build_trend_summary_markdown(report: SessionTrendReport) -> str:
    lines = ["# Session Trend Summary", "", report.summary]
    if report.points:
        lines.extend(["", "## Session Comparison", ""])
        headers = ["Session", "Created", "Protocol", "Transactions", "Anomalies", "Status"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for point in report.points:
            values = [
                point.session_name,
                point.created_at,
                point.protocol,
                str(point.total_transactions),
                str(point.anomaly_count),
                point.status,
            ]
            lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def render() -> None:
    """Render the Multi-Session Trend Analysis page."""
    st.header("Multi-Session Trend Analysis")
    st.markdown(
        "Upload multiple session files to compare key metrics, "
        "visualize anomaly trends, and track debugging progress over time."
    )
    uploaded = st.file_uploader(
        "Upload Session Files",
        type=["json"],
        accept_multiple_files=True,
        help="Select 2+ .fwsession.json files for trend analysis.",
    )
    if not uploaded:
        st.info("Drag and drop your .fwsession.json files here.")
        return
    sessions = _load_sessions(uploaded)
    if not sessions:
        st.error("No valid session files found.")
        return
    protocols = sorted(
        {
            s.get("config", {}).get("protocol", s.get("report", {}).get("protocol", "unknown"))
            for s in sessions
        }
    )
    if len(protocols) > 1:
        selected = st.multiselect("Filter by Protocol", protocols, default=protocols)
        sessions = [
            s
            for s in sessions
            if s.get("config", {}).get("protocol", s.get("report", {}).get("protocol", "unknown"))
            in selected
        ]
    report = analyze_session_trends(sessions)
    _render_metrics(report)
    _render_trend_chart(report)
    st.subheader("Session Comparison")
    _render_comparison_table(report)
    st.subheader("Analysis Summary")
    if report.anomaly_trend == "improving":
        st.success(report.summary)
    elif report.anomaly_trend == "degrading":
        st.warning(report.summary)
    else:
        st.info(report.summary)

    st.subheader("Export")
    export_col1, export_col2 = st.columns(2)
    comparison_csv = _comparison_dataframe(report).to_csv(index=False)
    trend_summary_md = _build_trend_summary_markdown(report)
    with export_col1:
        st.download_button(
            "Download Comparison CSV",
            data=comparison_csv,
            file_name="session_comparison.csv",
            mime="text/csv",
            key="session_analytics_download_csv",
        )
    with export_col2:
        st.download_button(
            "Download Trend Summary Markdown",
            data=trend_summary_md,
            file_name="session_trend_summary.md",
            mime="text/markdown",
            key="session_analytics_download_markdown",
        )

    render_page_footer()
