"""韌體訊號與協定診斷套件 — 偏好設定（Settings & Preferences）頁面。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from fw_diag_tool.gui.notifications import show_success_toast
from fw_diag_tool.gui.shared import get_translator, render_page_footer
from fw_diag_tool.i18n import t


def _tr(key: str, fallback: str, **kwargs: Any) -> str:
    translated = t(key, domain="gui", **kwargs)
    return fallback if translated == key else translated


# ---------------------------------------------------------------------------
# Default configuration constants
# ---------------------------------------------------------------------------

DEFAULT_I2C_TIMEOUT_MS: float = 25.0
DEFAULT_LOCALE: str = "zh-TW"
DEFAULT_THEME: str = "暗色 (Dark)"
DEFAULT_MAX_ROWS: int = 250_000
DEFAULT_SPI_PAGE_SIZE: int = 256

LANGUAGE_OPTIONS: tuple[str, ...] = ("zh-TW", "en-US")
THEME_OPTIONS: tuple[str, ...] = (
    "暗色 (Dark)",
    "亮色 (Light)",
    "高對比度 (High Contrast)",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "i2c_timeout_ms": DEFAULT_I2C_TIMEOUT_MS,
    "locale": DEFAULT_LOCALE,
    "theme": DEFAULT_THEME,
    "max_rows": DEFAULT_MAX_ROWS,
    "spi_page_size": DEFAULT_SPI_PAGE_SIZE,
}


def get_current_settings() -> dict[str, Any]:
    """取得當前 session_state 中設定值，若無則返回預設值。"""
    i2c_timeout = float(st.session_state.get("settings_i2c_timeout", DEFAULT_I2C_TIMEOUT_MS))
    locale = str(st.session_state.get("locale", DEFAULT_LOCALE))
    theme = str(st.session_state.get("settings_theme", DEFAULT_THEME))
    max_rows = int(st.session_state.get("settings_max_rows", DEFAULT_MAX_ROWS))
    spi_page_size = int(st.session_state.get("settings_spi_page_size", DEFAULT_SPI_PAGE_SIZE))

    return {
        "i2c_timeout_ms": i2c_timeout,
        "locale": locale,
        "theme": theme,
        "max_rows": max_rows,
        "spi_page_size": spi_page_size,
    }


def apply_settings(
    *,
    i2c_timeout_ms: float,
    locale: str,
    theme: str,
    max_rows: int,
    spi_page_size: int,
) -> None:
    """儲存設定至 session_state 並同步全域狀態。"""
    st.session_state["settings_i2c_timeout"] = float(i2c_timeout_ms)
    st.session_state["i2c_smbus_timeout"] = float(i2c_timeout_ms)
    st.session_state["locale"] = locale
    st.session_state["settings_theme"] = theme

    # 同步內部 theme 關鍵字
    if "暗色" in theme or "Dark" in theme:
        st.session_state["theme"] = "dark"
    elif "亮色" in theme or "Light" in theme:
        st.session_state["theme"] = "light"
    elif "高對比" in theme or "High Contrast" in theme:
        st.session_state["theme"] = "high_contrast"

    st.session_state["settings_max_rows"] = int(max_rows)
    st.session_state["settings_spi_page_size"] = int(spi_page_size)

    # 同步翻譯登錄表
    get_translator().set_locale(locale)


def reset_settings() -> None:
    """恢復所有設定為預設值。"""
    apply_settings(
        i2c_timeout_ms=DEFAULT_I2C_TIMEOUT_MS,
        locale=DEFAULT_LOCALE,
        theme=DEFAULT_THEME,
        max_rows=DEFAULT_MAX_ROWS,
        spi_page_size=DEFAULT_SPI_PAGE_SIZE,
    )


def render() -> None:
    """偏好設定（Settings & Preferences）頁面入口。"""
    st.header(_tr("title_settings", "偏好設定（Settings & Preferences）"))
    st.caption(_tr("settings_caption", "自訂全域協定分析逾時、介面語系、視覺主題與資料載入上限。"))

    current = get_current_settings()

    # 1. I2C 預設 Timeout (ms)
    i2c_timeout = st.number_input(
        _tr("settings_i2c_timeout", "I2C 預設 Timeout (ms)"),
        min_value=1.0,
        max_value=1000.0,
        value=float(current["i2c_timeout_ms"]),
        step=1.0,
        format="%.1f",
        help=_tr("settings_i2c_timeout_help", "I2C / SMBus 交易超時判定門檻（毫秒）。"),
    )

    # 2. 預設語言
    locale_opts = list(LANGUAGE_OPTIONS)
    locale_idx = locale_opts.index(current["locale"]) if current["locale"] in locale_opts else 0
    selected_locale = st.selectbox(
        t("language_selector_label", domain="gui"),
        options=locale_opts,
        index=locale_idx,
        help=_tr("settings_language_help", "系統介面顯示語言。"),
    )

    # 3. 預設主題
    theme_opts = list(THEME_OPTIONS)
    theme_idx = theme_opts.index(current["theme"]) if current["theme"] in theme_opts else 0
    selected_theme = st.selectbox(
        _tr("settings_theme", "預設主題"),
        options=theme_opts,
        index=theme_idx,
        help=_tr("settings_theme_help", "UI 外觀配色主題。"),
    )

    # 4. 分析資料列數上限
    max_rows = st.number_input(
        _tr("settings_max_rows", "分析資料列數上限"),
        min_value=1,
        max_value=10_000_000,
        value=int(current["max_rows"]),
        step=10_000,
        help=_tr("settings_max_rows_help", "單次匯入分析之最大 CSV / 交易資料列數限制。"),
    )

    # 5. SPI 預設 Page Size
    spi_page_size = st.number_input(
        _tr("settings_spi_page_size", "SPI 預設 Page Size"),
        min_value=1,
        max_value=65536,
        value=int(current["spi_page_size"]),
        step=256,
        help=_tr(
            "settings_spi_page_size_help", "SPI NOR Flash Page Program 預設緩衝區大小（位元組）。"
        ),
    )

    # 按鈕列
    col_apply, col_reset, _ = st.columns([1, 1, 3])
    with col_apply:
        apply_label = _tr("btn_apply", "套用設定")
        if st.button(apply_label, type="primary", key="btn_apply_settings"):
            apply_settings(
                i2c_timeout_ms=float(i2c_timeout),
                locale=str(selected_locale),
                theme=str(selected_theme),
                max_rows=int(max_rows),
                spi_page_size=int(spi_page_size),
            )
            show_success_toast(_tr("settings_applied_toast", "設定已成功套用！"))

    with col_reset:
        reset_label = _tr("settings_reset_button", "重設為預設值")
        if st.button(reset_label, key="btn_reset_settings"):
            reset_settings()
            show_success_toast(_tr("settings_reset_toast", "已重設為預設設定！"))

    # 生效設定摘要
    st.divider()
    st.subheader(_tr("settings_active_summary", "目前生效設定摘要"))
    active = get_current_settings()

    sum_col1, sum_col2, sum_col3, sum_col4, sum_col5 = st.columns(5)
    with sum_col1:
        st.metric(
            _tr("settings_metric_i2c_timeout", "I2C Timeout"), f"{active['i2c_timeout_ms']:.1f} ms"
        )
    with sum_col2:
        st.metric(_tr("settings_metric_locale", "語言"), str(active["locale"]))
    with sum_col3:
        st.metric(_tr("settings_metric_theme", "主題"), str(active["theme"]))
    with sum_col4:
        st.metric(_tr("settings_metric_max_rows", "資料上限"), f"{active['max_rows']:,} 列")
    with sum_col5:
        st.metric(_tr("settings_metric_spi_page", "SPI Page"), f"{active['spi_page_size']} B")

    render_page_footer()


__all__ = [
    "DEFAULT_I2C_TIMEOUT_MS",
    "DEFAULT_LOCALE",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_SETTINGS",
    "DEFAULT_SPI_PAGE_SIZE",
    "DEFAULT_THEME",
    "LANGUAGE_OPTIONS",
    "THEME_OPTIONS",
    "apply_settings",
    "get_current_settings",
    "render",
    "reset_settings",
]
