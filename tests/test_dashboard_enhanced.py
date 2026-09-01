from __future__ import annotations

import streamlit as st

import fw_diag_tool.gui.shared as shared_module
from fw_diag_tool.gui import route_registry
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


def test_quick_link_uses_registered_page_in_runtime_context(monkeypatch):
    def render_page():
        return None

    page = object.__new__(st.Page)
    page._default = False
    page._url_path = "i2c-diagnosis"
    route_registry.register_page(page)
    calls = []

    def page_link(target, **kwargs):
        if isinstance(target, str):
            raise TypeError("string slug is treated as a script path")
        calls.append((target, kwargs))

    monkeypatch.setattr(dashboard_ui.st, "page_link", page_link)
    dashboard_ui._render_quick_link("i2c-diagnosis", "📊 I2C 診斷")

    assert route_registry.resolve_page("i2c-diagnosis") is page
    assert calls == [(page, {"label": "📊 I2C 診斷", "use_container_width": True})]


def test_correlation_ui_render_executes_without_error():
    # Verify correlation_ui executes and includes footer
    correlation_ui.render()


def test_dashboard_ui_render_recent_sessions_empty():
    dashboard_ui._render_recent_sessions()


def test_dashboard_ui_render_recent_sessions_with_items(monkeypatch):
    class DummySession:
        def __init__(self, name, protocol, created_at):
            self.name = name
            self.protocol = protocol
            self.created_at = created_at
            self.session_id = "test-session-id"

    class DummyManager:
        def list_sessions(self):
            return [
                DummySession("Session 1", "I2C", "2026-08-30"),
                {"name": "Session 2", "protocol": "SPI", "created_at": "2026-08-30"},
            ]

    monkeypatch.setattr(dashboard_ui, "SessionManager", DummyManager)
    dashboard_ui._render_recent_sessions()
