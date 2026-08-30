"""Tests for Settings & Preferences GUI page module."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
import streamlit as st

from fw_diag_tool.gui.pages.settings_ui import (
    DEFAULT_I2C_TIMEOUT_MS,
    DEFAULT_LOCALE,
    DEFAULT_MAX_ROWS,
    DEFAULT_SETTINGS,
    DEFAULT_SPI_PAGE_SIZE,
    DEFAULT_THEME,
    LANGUAGE_OPTIONS,
    THEME_OPTIONS,
    apply_settings,
    get_current_settings,
    render,
    reset_settings,
)


def test_render_is_importable_and_callable() -> None:
    """測試 render 函式可被 import 且為 callable。"""
    mod = importlib.import_module("fw_diag_tool.gui.pages.settings_ui")
    assert hasattr(mod, "render")
    assert callable(mod.render)


def test_module_all_contains_render() -> None:
    """測試模組有 __all__ 且包含 'render'。"""
    mod = importlib.import_module("fw_diag_tool.gui.pages.settings_ui")
    assert hasattr(mod, "__all__")
    assert "render" in mod.__all__


def test_default_constants_and_settings() -> None:
    """測試預設設定值與常數數值符合規格要求。"""
    assert DEFAULT_I2C_TIMEOUT_MS == 25.0
    assert DEFAULT_LOCALE == "zh-TW"
    assert DEFAULT_THEME == "暗色 (Dark)"
    assert DEFAULT_MAX_ROWS == 250_000
    assert DEFAULT_SPI_PAGE_SIZE == 256

    assert "zh-TW" in LANGUAGE_OPTIONS
    assert "en-US" in LANGUAGE_OPTIONS

    assert "暗色 (Dark)" in THEME_OPTIONS
    assert "亮色 (Light)" in THEME_OPTIONS
    assert "高對比度 (High Contrast)" in THEME_OPTIONS

    assert DEFAULT_SETTINGS["i2c_timeout_ms"] == 25.0
    assert DEFAULT_SETTINGS["locale"] == "zh-TW"
    assert DEFAULT_SETTINGS["theme"] == "暗色 (Dark)"
    assert DEFAULT_SETTINGS["max_rows"] == 250_000
    assert DEFAULT_SETTINGS["spi_page_size"] == 256


def test_get_current_settings_fallback_to_defaults() -> None:
    """當 session_state 為空時，get_current_settings 應回傳預設值。"""
    # 清空可能存在的 session_state keys
    for key in (
        "settings_i2c_timeout",
        "locale",
        "settings_theme",
        "settings_max_rows",
        "settings_spi_page_size",
    ):
        st.session_state.pop(key, None)

    settings = get_current_settings()
    assert settings["i2c_timeout_ms"] == 25.0
    assert settings["locale"] == "zh-TW"
    assert settings["theme"] == "暗色 (Dark)"
    assert settings["max_rows"] == 250_000
    assert settings["spi_page_size"] == 256


def test_apply_and_reset_settings() -> None:
    """測試 apply_settings 寫入與 reset_settings 重設狀態。"""
    apply_settings(
        i2c_timeout_ms=50.0,
        locale="en-US",
        theme="亮色 (Light)",
        max_rows=100_000,
        spi_page_size=512,
    )

    applied = get_current_settings()
    assert applied["i2c_timeout_ms"] == 50.0
    assert applied["locale"] == "en-US"
    assert applied["theme"] == "亮色 (Light)"
    assert applied["max_rows"] == 100_000
    assert applied["spi_page_size"] == 512
    assert st.session_state.get("theme") == "light"
    assert st.session_state.get("i2c_smbus_timeout") == 50.0

    # 重設為預設值
    reset_settings()
    reset_data = get_current_settings()
    assert reset_data["i2c_timeout_ms"] == 25.0
    assert reset_data["locale"] == "zh-TW"
    assert reset_data["theme"] == "暗色 (Dark)"
    assert reset_data["max_rows"] == 250_000
    assert reset_data["spi_page_size"] == 256
    assert st.session_state.get("theme") == "dark"


def test_render_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試 render() 流程能完整執行。"""
    monkeypatch.setattr(st, "button", MagicMock(return_value=False))
    monkeypatch.setattr(st, "toast", MagicMock())

    render()
