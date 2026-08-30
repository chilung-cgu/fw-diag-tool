"""Test that toast notifications are integrated into analysis pages."""

from __future__ import annotations

import importlib

import pytest

ANALYSIS_PAGES = [
    "fw_diag_tool.gui.pages.i2c_diagnosis",
    "fw_diag_tool.gui.pages.spi_ui",
    "fw_diag_tool.gui.pages.pcie_ui",
    "fw_diag_tool.gui.pages.uart_ui",
    "fw_diag_tool.gui.pages.mctp_ui",
]


@pytest.mark.parametrize("module_name", ANALYSIS_PAGES)
def test_analysis_page_imports_toast(module_name: str) -> None:
    """每個分析頁面都必須匯入 toast 通知函式。"""
    mod = importlib.import_module(module_name)
    source_file = mod.__file__
    assert source_file is not None
    with open(source_file, encoding="utf-8") as fh:
        source = fh.read()
    assert "show_success_toast" in source or "show_error_toast" in source, (
        f"{module_name} 應匯入 toast 通知函式"
    )


@pytest.mark.parametrize("module_name", ANALYSIS_PAGES)
def test_analysis_page_calls_toast_on_success(module_name: str) -> None:
    """每個分析頁面的原始碼應包含 show_success_toast 呼叫。"""
    mod = importlib.import_module(module_name)
    assert mod.__file__ is not None
    with open(mod.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "show_success_toast" in source


@pytest.mark.parametrize("module_name", ANALYSIS_PAGES)
def test_analysis_page_calls_toast_on_error(module_name: str) -> None:
    """每個分析頁面的原始碼應包含 show_error_toast 呼叫。"""
    mod = importlib.import_module(module_name)
    assert mod.__file__ is not None
    with open(mod.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "show_error_toast" in source
