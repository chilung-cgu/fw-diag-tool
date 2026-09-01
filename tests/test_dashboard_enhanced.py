from __future__ import annotations

from streamlit.testing.v1 import AppTest

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


def test_quick_link_uses_registered_page_in_runtime_context():
    app = AppTest.from_string(
        """
import streamlit as st
from fw_diag_tool.gui.pages.dashboard_ui import _render_quick_link
from fw_diag_tool.gui.route_registry import register_pages, resolve_page

def dashboard():
    _render_quick_link("i2c-diagnosis", "📊 I2C 診斷")
    _render_quick_link("unknown-page", "🔗 Unknown")

def diagnosis():
    st.write("diagnosis")

pages = {"": [
    st.Page(dashboard, title="Dashboard", url_path="dashboard"),
    st.Page(diagnosis, title="I2C 診斷", url_path="i2c-diagnosis"),
]}
register_pages(pages)
st.navigation(pages).run()
"""
    ).run()

    assert not app.exception
    page_link = app._tree.children[0].children[0]
    assert page_link.type == "page_link"
    assert page_link.proto.label == "📊 I2C 診斷"
    assert page_link.proto.page_script_hash == route_registry.resolve_page("i2c-diagnosis")._script_hash
    assert app.caption[0].value == "🔗 Unknown"


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
