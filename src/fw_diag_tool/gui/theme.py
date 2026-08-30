from __future__ import annotations

from typing import Literal

import streamlit as st

DARK_THEME = """
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

LIGHT_THEME = """
<style>
/* 亮色主題全局與主背景 */
.stApp {
    background-color: #ffffff;
    color: #1e293b;
}

/* 卡片式容器增強 */
div[data-testid="stExpander"] {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    background-color: #ffffff;
}

/* Metric 卡片視覺 */
div[data-testid="stMetric"] {
    background-color: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 1rem;
    color: #1e293b;
}

/* 表格頭部強調 */
thead tr th {
    background-color: #f1f5f9 !important;
    color: #0369a1 !important;
    font-weight: 600;
}

/* Success/Error/Warning 框增強 */
div[data-testid="stAlert"] {
    border-radius: 8px;
}

/* Code block 微調 */
pre {
    border-radius: 8px !important;
    background-color: #f1f5f9 !important;
}

/* Tab 選項增強 */
button[data-baseweb="tab"] {
    font-weight: 500;
    color: #1e293b;
}

/* Sidebar 標題與樣式 */
section[data-testid="stSidebar"] {
    background-color: #f8fafc;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #0369a1;
}

/* Download button 強調 */
button[kind="secondary"] {
    border-color: #0369a1 !important;
    color: #0369a1 !important;
}
</style>
"""

HIGH_CONTRAST_THEME = """
<style>
/* 高對比度主題：黑底白字與高飽和度色彩，符合 WCAG 讀取需求 */
:root {
    --hc-background: #000000;
    --hc-surface: #000000;
    --hc-text: #ffffff;
    --hc-accent: #00ffff;
    --hc-secondary-accent: #ffff00;
    --hc-alert: #ff00ff;
}

.stApp,
section[data-testid="stSidebar"] {
    background-color: var(--hc-background) !important;
    color: var(--hc-text) !important;
}

/* 卡片式容器增強 */
div[data-testid="stExpander"],
div[data-testid="stMetric"] {
    background-color: var(--hc-surface) !important;
    border: 3px solid var(--hc-text) !important;
    border-radius: 0;
}

div[data-testid="stMetric"] {
    padding: 1rem;
}

/* 表格頭部強調 */
thead tr th {
    background-color: var(--hc-surface) !important;
    color: var(--hc-secondary-accent) !important;
    border: 2px solid var(--hc-text) !important;
    font-weight: 700;
}

tbody tr td {
    border: 1px solid var(--hc-text) !important;
    color: var(--hc-text) !important;
}

/* 狀態框、程式碼區塊與分頁 */
div[data-testid="stAlert"],
pre,
button[data-baseweb="tab"],
button[kind="secondary"] {
    border: 3px solid var(--hc-text) !important;
}

div[data-testid="stAlert"] {
    border-radius: 0;
}

pre {
    border-radius: 0 !important;
    background-color: var(--hc-surface) !important;
    color: var(--hc-text) !important;
}

button[data-baseweb="tab"] {
    color: var(--hc-accent) !important;
    font-weight: 700;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--hc-accent) !important;
}

button[kind="secondary"] {
    color: var(--hc-accent) !important;
}

a,
button:focus,
input:focus,
textarea:focus,
select:focus {
    outline: 3px solid var(--hc-secondary-accent) !important;
    outline-offset: 2px;
}
</style>
"""

# 向後相容別名
_CUSTOM_CSS = DARK_THEME
THEME_SESSION_KEY = "theme"


def get_current_theme() -> str:
    """取得當前主題設定，預設為 ``dark``。"""
    theme = st.session_state.get(THEME_SESSION_KEY, "dark")
    if isinstance(theme, str):
        normalized = theme.strip().lower()
        if normalized in ("light", "亮色", "亮色 (light)"):
            return "light"
        if normalized in (
            "high_contrast",
            "high-contrast",
            "high contrast",
            "高對比",
            "高對比度",
            "高對比 (high contrast)",
            "高對比度 (high contrast)",
        ):
            return "high_contrast"
    return "dark"


def render_theme_toggle() -> str:
    """在 sidebar 顯示主題切換開關，並同步更新 session_state['theme']。"""
    current = get_current_theme()
    options = ["暗色 (Dark)", "亮色 (Light)", "高對比度 (High Contrast)"]
    index = {"dark": 0, "light": 1, "high_contrast": 2}[current]
    selected = st.sidebar.radio(
        "外觀主題",
        options=options,
        index=index,
        horizontal=True,
        key="theme_toggle_widget",
    )
    normalized_selected = selected.strip().lower()
    if "high contrast" in normalized_selected or "高對比" in selected:
        theme_value = "high_contrast"
    elif "light" in normalized_selected or "亮色" in selected:
        theme_value = "light"
    else:
        theme_value = "dark"
    st.session_state[THEME_SESSION_KEY] = theme_value
    return theme_value


def get_plotly_template() -> Literal["plotly_dark", "plotly_white"]:
    """根據當前主題回傳對應的 Plotly template 名稱。"""
    return "plotly_white" if get_current_theme() == "light" else "plotly_dark"


def inject_custom_theme() -> None:
    """根據當前主題注入自訂 CSS 主題增強。在 app.py 的 set_page_config 之後呼叫。"""
    theme = get_current_theme()
    css = {
        "dark": DARK_THEME,
        "light": LIGHT_THEME,
        "high_contrast": HIGH_CONTRAST_THEME,
    }[theme]
    st.markdown(css, unsafe_allow_html=True)


def render_metric_card(
    label: str,
    value: str | float,
    delta: str | None = None,
    help_text: str | None = None,
) -> None:
    """顯示帶有主題樣式的 metric 卡片。"""
    st.metric(label=label, value=value, delta=delta, help=help_text)


__all__ = [
    "DARK_THEME",
    "HIGH_CONTRAST_THEME",
    "LIGHT_THEME",
    "_CUSTOM_CSS",
    "get_current_theme",
    "get_plotly_template",
    "inject_custom_theme",
    "render_metric_card",
    "render_theme_toggle",
]
