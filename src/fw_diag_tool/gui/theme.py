from __future__ import annotations

import streamlit as st

_CUSTOM_CSS = """
<style>
/* 卡片式容器增強 */
div[data-testid="stExpander"] {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-bottom: 0.5rem;
}

/* Metric 卡片視覺 */
div[data-testid="stMetric"] {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1rem;
}

/* 表格頭部強調 */
thead tr th {
    background-color: #1e293b !important;
    color: #0ea5e9 !important;
    font-weight: 600;
}

/* Success/Error/Warning 框增強 */
div[data-testid="stAlert"] {
    border-radius: 8px;
}

/* Code block 微調 */
pre {
    border-radius: 8px !important;
}

/* Tab 選項增強 */
button[data-baseweb="tab"] {
    font-weight: 500;
}

/* Sidebar 標題 */
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #0ea5e9;
}

/* Download button 強調 */
button[kind="secondary"] {
    border-color: #0ea5e9 !important;
}
</style>
"""


def inject_custom_theme() -> None:
    """注入自訂 CSS 主題增強。在 app.py 的 set_page_config 之後呼叫。"""
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


def render_metric_card(
    label: str,
    value: str | float,
    delta: str | None = None,
    help_text: str | None = None,
) -> None:
    """顯示帶有主題樣式的 metric 卡片。"""
    st.metric(label=label, value=value, delta=delta, help=help_text)


__all__ = ["inject_custom_theme", "render_metric_card"]
