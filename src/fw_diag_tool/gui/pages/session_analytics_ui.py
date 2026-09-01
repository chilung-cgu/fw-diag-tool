"""Multi-Session Trend Analysis Dashboard."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.gui.theme import get_plotly_template
from fw_diag_tool.i18n import t
from fw_diag_tool.session.analytics import (
    SessionTrendReport,
    analyze_session_trends,
    compute_health_score,
)


def _get_sample_trend_sessions() -> list[dict[str, Any]]:
    """Return 3 sample session payloads representing distinct bring-up stages."""
    return [
        {
            "name": "Stage 1 - Initial Bringup",
            "created_at": "2026-08-20T10:00:00Z",
            "config": {"protocol": "i2c"},
            "report": {
                "protocol": "i2c",
                "total_transactions": 120,
                "anomaly_count": 8,
                "status": "error",
                "anomalies": [
                    {"type": "I2C_ADDR_NACK", "desc": "Address NACK on 0x3A"},
                    {"type": "I2C_SMBUS_TIMEOUT", "desc": "Clock Stretching > 25ms"},
                ],
            },
        },
        {
            "name": "Stage 2 - Firmware Patch",
            "created_at": "2026-08-25T14:30:00Z",
            "config": {"protocol": "i2c"},
            "report": {
                "protocol": "i2c",
                "total_transactions": 150,
                "anomaly_count": 3,
                "status": "warning",
                "anomalies": [
                    {"type": "I2C_DATA_NACK", "desc": "Data byte NACK at byte 2"},
                ],
            },
        },
        {
            "name": "Stage 3 - Final Sign-off",
            "created_at": "2026-08-30T09:15:00Z",
            "config": {"protocol": "i2c"},
            "report": {
                "protocol": "i2c",
                "total_transactions": 200,
                "anomaly_count": 0,
                "status": "success",
                "anomalies": [],
            },
        },
    ]


get_sample_trend_sessions = _get_sample_trend_sessions


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
        st.metric(
            t(
                "session_analytics_metric_sessions",
                domain="gui",
                default="工作階段總數（Sessions）",
            ),
            total_sessions,
        )
    with col2:
        st.metric(
            t(
                "session_analytics_metric_anomalies",
                domain="gui",
                default="最新異常數（Latest Anomalies）",
            ),
            latest.anomaly_count,
            delta=delta_str,
            delta_color="inverse",
        )
    with col3:
        trend_labels = {
            "improving": t(
                "session_analytics_trend_improving", domain="gui", default="改善中 (Improving)"
            ),
            "stable": t("session_analytics_trend_stable", domain="gui", default="持平 (Stable)"),
            "degrading": t(
                "session_analytics_trend_degrading", domain="gui", default="退化中 (Degrading)"
            ),
        }
        st.metric(
            t("session_analytics_metric_trend", domain="gui", default="趨勢判定（Trend）"),
            trend_labels.get(report.anomaly_trend, report.anomaly_trend),
        )
    with col4:
        st.metric(
            t(
                "session_analytics_metric_health",
                domain="gui",
                default="健康度評分（Health Score）",
            ),
            f"{compute_health_score(latest):.1f}",
        )


def _render_trend_chart(report: SessionTrendReport) -> None:
    if len(report.points) < 2:
        st.info(
            t(
                "session_analytics_chart_min_sessions",
                domain="gui",
                default="上傳至少 2 個工作階段以檢視趨勢圖表。",
            )
        )
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
            name=t(
                "session_analytics_chart_trace_anomalies",
                domain="gui",
                default="異常數（Anomalies）",
            ),
            marker={"size": 10, "color": "#ef4444"},
            line={"width": 3, "color": "#ef4444"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=names,
            y=transactions,
            mode="lines+markers",
            name=t(
                "session_analytics_chart_trace_tx", domain="gui", default="交易數（Transactions）"
            ),
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
            name=t(
                "session_analytics_chart_trace_health",
                domain="gui",
                default="健康度分數（Health Score）",
            ),
            marker={"size": 8, "color": "#22c55e"},
            line={"width": 2, "color": "#22c55e"},
        )
    )
    fig.update_layout(
        template=get_plotly_template(),
        title=t(
            "session_analytics_chart_title",
            domain="gui",
            default="Session 趨勢圖表（Session Trend）",
        ),
        xaxis_title=t("session_analytics_chart_xaxis", domain="gui", default="工作階段（Session）"),
        yaxis={
            "title": t(
                "session_analytics_chart_yaxis_anomalies",
                domain="gui",
                default="異常數量（Anomaly Count）",
            ),
            "side": "left",
        },
        yaxis2={
            "title": t(
                "session_analytics_chart_yaxis_tx",
                domain="gui",
                default="交易數量（Transaction Count）",
            ),
            "side": "right",
            "overlaying": "y",
        },
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
    st.header(
        t(
            "title_session_analytics",
            domain="gui",
            default="多工作階段趨勢分析（Multi-Session Trend Analysis）",
        )
    )
    st.markdown(
        t(
            "session_analytics_desc",
            domain="gui",
            default=(
                "上傳多個診斷工作階段（.fwsession.json）檔案以比對關鍵指標、"
                "視覺化異常趨勢，並追蹤隨時間變化的除錯進度。"
            ),
        )
    )

    demo_active = st.session_state.get("session_analytics_demo_active", False)
    btn_col1, btn_col2 = st.columns([2, 1])
    with btn_col1:
        if st.button(
            t("session_analytics_load_demo", domain="gui", default="🚀 載入示範趨勢 Session"),
            key="session_analytics_load_demo_btn",
            help="載入內建的 3 個除錯階段示範趨勢資料",
        ):
            st.session_state["session_analytics_demo_active"] = True
            st.rerun()
    with btn_col2:
        if demo_active and st.button(
            t("session_analytics_clear_demo", domain="gui", default="🔄 清除示範資料"),
            key="session_analytics_clear_demo_btn",
        ):
            st.session_state["session_analytics_demo_active"] = False
            st.rerun()

    uploaded = st.file_uploader(
        t("session_analytics_upload_label", domain="gui", default="上傳 Session 檔案"),
        type=["json"],
        accept_multiple_files=True,
        help=t(
            "session_analytics_upload_help",
            domain="gui",
            default="選取 2 個以上 .fwsession.json 檔案進行趨勢分析。",
        ),
    )

    sessions: list[dict[str, Any]] = []
    if uploaded:
        sessions = _load_sessions(uploaded)
        if not sessions:
            st.error(
                t("session_analytics_no_valid", domain="gui", default="未找到有效的 Session 檔案。")
            )
            render_page_footer()
            return
    elif demo_active:
        sessions = _get_sample_trend_sessions()
    else:
        st.info(
            t(
                "session_analytics_empty_info",
                domain="gui",
                default="請拖放或選取 .fwsession.json 檔案，或點擊上方按鈕載入示範資料。",
            )
        )
        render_page_footer()
        return

    protocols = sorted(
        {
            s.get("config", {}).get("protocol", s.get("report", {}).get("protocol", "unknown"))
            for s in sessions
        }
    )
    if len(protocols) > 1:
        selected = st.multiselect(
            t("session_analytics_filter_proto", domain="gui", default="依協定篩選"),
            protocols,
            default=protocols,
        )
        sessions = [
            s
            for s in sessions
            if s.get("config", {}).get("protocol", s.get("report", {}).get("protocol", "unknown"))
            in selected
        ]

    report = analyze_session_trends(sessions)
    _render_metrics(report)
    _render_trend_chart(report)
    st.subheader(
        t(
            "session_analytics_sub_comparison",
            domain="gui",
            default="工作階段對比（Session Comparison）",
        )
    )
    _render_comparison_table(report)
    st.subheader(
        t("session_analytics_sub_summary", domain="gui", default="趨勢分析摘要（Analysis Summary）")
    )
    if report.anomaly_trend == "improving":
        st.success(report.summary)
    elif report.anomaly_trend == "degrading":
        st.warning(report.summary)
    else:
        st.info(report.summary)

    st.subheader(t("session_analytics_sub_export", domain="gui", default="匯出（Export）"))
    export_col1, export_col2 = st.columns(2)
    comparison_csv = _comparison_dataframe(report).to_csv(index=False)
    trend_summary_md = _build_trend_summary_markdown(report)
    with export_col1:
        st.download_button(
            t("session_analytics_btn_download_csv", domain="gui", default="📥 下載對比 CSV"),
            data=comparison_csv,
            file_name="session_comparison.csv",
            mime="text/csv",
            key="session_analytics_download_csv",
        )
    with export_col2:
        st.download_button(
            t(
                "session_analytics_btn_download_md",
                domain="gui",
                default="⬇️ 下載趨勢摘要 Markdown",
            ),
            data=trend_summary_md,
            file_name="session_trend_summary.md",
            mime="text/markdown",
            key="session_analytics_download_markdown",
        )

    render_page_footer()


__all__ = [
    "_get_sample_trend_sessions",
    "get_sample_trend_sessions",
    "render",
]
