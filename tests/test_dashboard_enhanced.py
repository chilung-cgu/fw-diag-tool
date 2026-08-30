from __future__ import annotations

import fw_diag_tool.gui.shared as shared_module
from fw_diag_tool.gui.pages import correlation_ui, dashboard_ui
from fw_diag_tool.gui.shared import render_page_footer


def test_render_page_footer_exists_and_importable():
    assert callable(render_page_footer)
    assert "render_page_footer" in shared_module.__all__
    assert hasattr(shared_module, "render_page_footer")


def test_render_page_footer_executes_without_error():
    # Calling render_page_footer should not raise uncaught runtime exceptions
    render_page_footer()


def test_dashboard_ui_exports_render():
    assert hasattr(dashboard_ui, "render")
    assert callable(dashboard_ui.render)
    assert "render" in dashboard_ui.__all__


def test_dashboard_ui_render_executes_without_error():
    # Calling dashboard_ui.render should execute all components without uncaught exceptions
    dashboard_ui.render()


def test_dashboard_ui_example_counter():
    count = dashboard_ui._get_example_data_count()
    assert isinstance(count, int)
    assert count > 0


def test_dashboard_ui_quick_link_renderer():
    dashboard_ui._render_quick_link("i2c-diagnosis", "📊 I2C 診斷")
    dashboard_ui._render_quick_link("nonexistent-page", "🔗 測試連結")


def test_correlation_ui_render_executes_without_error():
    # Verify correlation_ui executes and includes footer
    correlation_ui.render()
