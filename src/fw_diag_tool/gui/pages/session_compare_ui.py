"""Session A/B 對比分析頁面（Session Comparison UI）。

提供兩個診斷工作階段（.fwsession.json）的指標差異比對、
異常消長判定、協定一致性檢查與 Markdown 報告匯出功能。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from fw_diag_tool.gui.shared import render_guide_expander, render_page_footer
from fw_diag_tool.i18n import t
from fw_diag_tool.session.comparator import SessionComparison, compare_sessions


def _extract_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report", payload)
    return report if isinstance(report, dict) else {}


def _extract_metric(report: dict[str, Any], keys: tuple[str, ...], list_key: str) -> int:
    value = 0
    for key in keys:
        candidate = report.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            value = candidate
            break
    if value == 0:
        values = report.get(list_key)
        if isinstance(values, list):
            value = len(values)
    return value


def _extract_protocol(payload: dict[str, Any], report: dict[str, Any]) -> str:
    config = payload.get("config", {})
    if isinstance(config, dict):
        value = config.get("protocol")
        if value is not None:
            return str(value)
    value = report.get("protocol")
    return str(value) if value is not None else "unknown"


def _parse_session_payload(raw: Any, default_name: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = dict(raw)
    elif isinstance(raw, (bytes, bytearray)):
        payload = json.loads(raw.decode("utf-8"))
    elif isinstance(raw, str):
        payload = json.loads(raw)
    else:
        raise TypeError("Session payload must be dict, str, or bytes")
    if not isinstance(payload, dict):
        raise TypeError("Parsed session payload must be a JSON object")
    if "name" not in payload:
        payload["name"] = default_name
    return payload


def build_comparison_dataframe(
    comparison: SessionComparison,
    baseline_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
) -> pd.DataFrame:
    """建構指標對比 DataFrame。"""
    b_rep = _extract_report(baseline_payload)
    c_rep = _extract_report(candidate_payload)

    b_anomalies = _extract_metric(b_rep, ("anomaly_count", "anomalies_count"), "anomalies")
    c_anomalies = _extract_metric(c_rep, ("anomaly_count", "anomalies_count"), "anomalies")
    b_tx = _extract_metric(b_rep, ("total_transactions", "transaction_count", "transactions"), "transactions")
    c_tx = _extract_metric(c_rep, ("total_transactions", "transaction_count", "transactions"), "transactions")

    proto_info = comparison.metric_deltas.get("protocol", {})
    b_proto = proto_info.get("baseline", _extract_protocol(baseline_payload, b_rep))
    c_proto = proto_info.get("candidate", _extract_protocol(candidate_payload, c_rep))
    proto_changed = proto_info.get("changed", b_proto != c_proto)

    anom_delta = comparison.metric_deltas.get("anomaly_count", c_anomalies - b_anomalies)
    tx_delta = comparison.metric_deltas.get("total_transactions", c_tx - b_tx)

    rows = [
        {
            "指標 / 項目（Metric）": "異常總數（Anomaly Count）",
            "Baseline（基準）": str(b_anomalies),
            "Candidate（待測）": str(c_anomalies),
            "差異（Delta）": f"{anom_delta:+d}",
        },
        {
            "指標 / 項目（Metric）": "交易總數（Total Transactions）",
            "Baseline（基準）": str(b_tx),
            "Candidate（待測）": str(c_tx),
            "差異（Delta）": f"{tx_delta:+d}",
        },
        {
            "指標 / 項目（Metric）": "協定（Protocol）",
            "Baseline（基準）": str(b_proto),
            "Candidate（待測）": str(c_proto),
            "差異（Delta）": "變更（Changed）" if proto_changed else "一致（Same）",
        },
    ]
    return pd.DataFrame(rows)


def format_session_comparison_markdown(
    comparison: SessionComparison,
    baseline_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
) -> str:
    """產出 Markdown 格式之 Session 對比報告。"""
    df = build_comparison_dataframe(comparison, baseline_payload, candidate_payload)
    headers = list(df.columns)
    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in df.to_dict(orient="records"):
        table_lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")

    lines = [
        "# Session A/B 對比報告（Session Comparison Report）",
        "",
        f"- **Baseline（基準）**: {comparison.baseline_name}",
        f"- **Candidate（待測）**: {comparison.candidate_name}",
        f"- **判定結果（Verdict）**: {comparison.verdict}",
        "",
        "## 指標差異對比（Metric Deltas）",
        "",
        *table_lines,
        "",
        "## 分析摘要（Summary）",
        "",
        comparison.summary,
        "",
    ]
    return "\n".join(lines)


def get_sample_sessions() -> tuple[dict[str, Any], dict[str, Any]]:
    """回傳示範用 Baseline 與 Candidate Session 資料。"""
    baseline = {
        "name": "I2C Baseline (Golden/Before)",
        "config": {"protocol": "i2c"},
        "report": {
            "protocol": "i2c",
            "anomaly_count": 4,
            "total_transactions": 20,
            "anomalies": ["Address NACK on 0x3A", "Clock Stretching > 25ms"],
        },
    }
    candidate = {
        "name": "I2C Candidate (Fixed/After)",
        "config": {"protocol": "i2c"},
        "report": {
            "protocol": "i2c",
            "anomaly_count": 0,
            "total_transactions": 24,
            "anomalies": [],
        },
    }
    return baseline, candidate


def render() -> None:
    """Render the Session A/B comparison page."""
    st.header(t("title_session_compare", domain="gui", default="Session A/B 對比分析（Session Comparison）"))
    st.caption(
        "上傳或載入兩個診斷工作階段（.fwsession.json）檔案，對比異常數量、交易總數與協定一致性，"
        "快速評估修復效果與回歸風險。"
    )

    render_guide_expander(
        "chapters/ch18_session_analytics.md",
        label="📖 點擊展開：Session A/B 對比分析使用指南",
        fallback_title="📖 Session A/B 對比分析使用指南",
        fallback_body=(
            "### 使用場景\n\n"
            "在韌體除錯或修復驗證過程中，對比修復前（Baseline）與修復後（Candidate）的診斷 Session，"
            "確認異常是否已消除，或是否存在新增的次生問題。\n\n"
            "### 判定標準\n\n"
            "- **改善（Improved）**：待測 Session 異常數量少於基準 Session。\n"
            "- **退化（Degraded）**：待測 Session 異常數量多於基準 Session。\n"
            "- **持平（Unchanged）**：異常數量相同。"
        ),
    )

    sample_col, _ = st.columns([2, 1])
    with sample_col:
        if st.button(
            "📋 載入範例 Session A/B 資料",
            key="session_compare_load_sample_btn",
            help="載入內建的 Baseline 與 Candidate 示範資料",
        ):
            sample_b, sample_c = get_sample_sessions()
            st.session_state["session_compare_baseline_payload"] = sample_b
            st.session_state["session_compare_candidate_payload"] = sample_c
            st.session_state["session_compare_sample_active"] = True
            st.rerun()

    st.subheader("📂 上傳 Session 檔案")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Baseline（基準 Session）**")
        baseline_file = st.file_uploader(
            "上傳 Baseline .fwsession.json",
            type=["json"],
            key="session_compare_baseline_upload",
            label_visibility="collapsed",
        )
    with col2:
        st.markdown("**Candidate（待測 Session）**")
        candidate_file = st.file_uploader(
            "上傳 Candidate .fwsession.json",
            type=["json"],
            key="session_compare_candidate_upload",
            label_visibility="collapsed",
        )

    baseline_payload = None
    candidate_payload = None

    if baseline_file is not None:
        try:
            baseline_payload = _parse_session_payload(
                baseline_file.getvalue(),
                default_name=baseline_file.name.replace(".fwsession.json", "").replace(".json", ""),
            )
        except Exception as exc:
            st.error(f"無法解析 Baseline Session：{exc}")

    if candidate_file is not None:
        try:
            candidate_payload = _parse_session_payload(
                candidate_file.getvalue(),
                default_name=candidate_file.name.replace(".fwsession.json", "").replace(".json", ""),
            )
        except Exception as exc:
            st.error(f"無法解析 Candidate Session：{exc}")

    if baseline_payload is None and st.session_state.get("session_compare_sample_active"):
        baseline_payload = st.session_state.get("session_compare_baseline_payload")
    if candidate_payload is None and st.session_state.get("session_compare_sample_active"):
        candidate_payload = st.session_state.get("session_compare_candidate_payload")

    if baseline_payload is None or candidate_payload is None:
        st.info("👆 請同時提供 Baseline 與 Candidate 兩份 Session 檔案以啟動 A/B 對比。")
        render_page_footer()
        return

    st.divider()
    st.subheader("🔍 對比分析結果")

    try:
        comparison = compare_sessions(baseline_payload, candidate_payload)
    except Exception as exc:
        st.error(f"執行 Session 對比失敗：{exc}")
        render_page_footer()
        return

    verdict = comparison.verdict
    anomaly_delta = comparison.metric_deltas.get("anomaly_count", 0)
    tx_delta = comparison.metric_deltas.get("total_transactions", 0)
    proto_info = comparison.metric_deltas.get("protocol", {})
    proto_changed = proto_info.get("changed", False)
    baseline_proto = proto_info.get("baseline", "unknown")
    candidate_proto = proto_info.get("candidate", "unknown")

    c_rep = _extract_report(candidate_payload)
    c_anomalies = _extract_metric(c_rep, ("anomaly_count", "anomalies_count"), "anomalies")
    c_tx = _extract_metric(c_rep, ("total_transactions", "transaction_count", "transactions"), "transactions")

    if verdict == "improved":
        st.success(f"🎉 **判定結果：改善（Improved）** — 待測版本異常減少 {abs(anomaly_delta)} 項")
    elif verdict == "degraded":
        st.error(f"🚨 **判定結果：退化（Degraded）** — 待測版本異常增加 {abs(anomaly_delta)} 項")
    else:
        st.info("ℹ️ **判定結果：持平（Unchanged）** — 兩版本異常數量一致")

    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.metric(
            "異常總數（Anomaly Count）",
            f"{c_anomalies}",
            delta=f"{anomaly_delta:+d}",
            delta_color="inverse",
        )
    with m_col2:
        st.metric(
            "交易總數（Total Transactions）",
            f"{c_tx}",
            delta=f"{tx_delta:+d}",
        )
    with m_col3:
        if proto_changed:
            st.metric(
                "協定（Protocol）",
                candidate_proto,
                delta=f"變更自 {baseline_proto}",
                delta_color="inverse",
            )
        else:
            st.metric(
                "協定（Protocol）",
                candidate_proto,
                delta="一致（Same）",
                delta_color="off",
            )

    if proto_changed:
        st.warning(
            f"⚠️ **協定變更警告**：Baseline 協定為 `{baseline_proto}`，"
            f"Candidate 協定為 `{candidate_proto}`。跨協定對比請注意指標定義差異。"
        )
    else:
        st.caption(f"協定比對：兩版本協定皆為 `{candidate_proto}`。")

    st.markdown(f"**分析摘要**：{comparison.summary}")

    st.subheader("📊 詳細指標對比表")
    df = build_comparison_dataframe(comparison, baseline_payload, candidate_payload)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("⬇️ 匯出對比報告")
    md_content = format_session_comparison_markdown(
        comparison, baseline_payload, candidate_payload
    )
    st.download_button(
        "下載 Markdown 對比報告",
        data=md_content,
        file_name="session_comparison_report.md",
        mime="text/markdown",
        key="session_compare_download_md_btn",
    )

    render_page_footer()


__all__ = [
    "build_comparison_dataframe",
    "format_session_comparison_markdown",
    "get_sample_sessions",
    "render",
]
