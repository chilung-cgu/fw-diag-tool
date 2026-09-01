from __future__ import annotations

from streamlit.testing.v1 import AppTest

import fw_diag_tool.gui.shared as shared_module
from fw_diag_tool.gui import route_registry
from fw_diag_tool.gui.pages import correlation_ui, dashboard_ui
from fw_diag_tool.gui.shared import render_page_footer


def _page_links(app):
    links = []

    def visit(node):
        if getattr(node, "type", None) == "page_link":
            links.append(node)
        children = getattr(node, "children", {})
        for child in children.values() if hasattr(children, "values") else ():
            visit(child)

    visit(app._tree)
    return links


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
    dashboard_ui._render_quick_link("i2c-diagnosis", "I2C 診斷")
    dashboard_ui._render_quick_link("nonexistent-page", "🔗 測試連結")


def test_quick_link_uses_registered_page_in_runtime_context():
    app = AppTest.from_string(
        """
import streamlit as st
from fw_diag_tool.gui.pages.dashboard_ui import _render_quick_link
from fw_diag_tool.gui.route_registry import register_pages, resolve_page

def dashboard():
    _render_quick_link("i2c-diagnosis", "I2C 診斷")
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
    assert page_link.proto.label == "I2C 診斷"
    target_page = route_registry.resolve_page("i2c-diagnosis")
    assert target_page is not None
    assert page_link.proto.page_script_hash == target_page._script_hash
    assert app.caption[0].value == "🔗 Unknown"


def test_dashboard_runtime_quick_launch_matrix_uses_real_page_metadata():
    app = AppTest.from_string(
        """
import streamlit as st
from fw_diag_tool.gui.pages import dashboard_ui
from fw_diag_tool.gui.route_registry import register_pages

def placeholder():
    st.write("placeholder")

pages = {"": [
    st.Page(dashboard_ui.render, title="Dashboard", url_path="dashboard"),
    st.Page(placeholder, title="I2C", url_path="i2c-diagnosis"),
    st.Page(placeholder, title="Diff", url_path="waveform-diff"),
    st.Page(placeholder, title="PCIe", url_path="pcie"),
    st.Page(placeholder, title="UART", url_path="uart"),
    st.Page(placeholder, title="SPI", url_path="spi"),
    st.Page(placeholder, title="Fault Arena", url_path="fault-arena"),
    st.Page(placeholder, title="Session Compare", url_path="session-compare"),
    st.Page(placeholder, title="Session Analytics", url_path="session-analytics"),
]}
register_pages(pages)
st.navigation(pages, position="hidden").run()
"""
    ).run()

    assert not app.exception
    links = _page_links(app)
    labels = {link.proto.label for link in links}
    assert labels >= {
        "I2C 診斷",
        "雙波形差分",
        "PCIe AER",
        "UART Crash",
        "SPI Flash",
        "Fault Arena",
    }
    route_labels = {
        "I2C 診斷": "i2c-diagnosis",
        "雙波形差分": "waveform-diff",
        "PCIe AER": "pcie",
        "UART Crash": "uart",
        "SPI Flash": "spi",
        "Fault Arena": "fault-arena",
    }
    for label, url_path in route_labels.items():
        link = next(item for item in links if item.proto.label == label)
        page = route_registry.resolve_page(url_path)
        assert page is not None
        assert link.proto.page_script_hash == page._script_hash


def test_release_card_and_quick_import_links_resolve_registered_routes():
    app = AppTest.from_string(
        '''
import streamlit as st
from types import SimpleNamespace
from fw_diag_tool.gui.pages import dashboard_ui
from fw_diag_tool.gui.route_registry import register_pages
from fw_diag_tool.release_notes import ReleaseHighlight, ReleaseNote

def placeholder():
    st.write("placeholder")

class Manager:
    def list_sessions(self):
        return [{"name": "Demo", "filename": "demo.json", "path": "/tmp/demo", "created_at": "today"}]
    def load_document(self, _path):
        return SimpleNamespace(name="Demo", tool_version="1.0", created_at="today", report={}, notes="")

dashboard_ui.SessionManager = Manager
pages = {"": [
    st.Page(placeholder, title="Diff", url_path="waveform-diff"),
    st.Page(placeholder, title="Session Compare", url_path="session-compare"),
    st.Page(placeholder, title="Session Analytics", url_path="session-analytics"),
    st.Page(placeholder, title="I2C", url_path="i2c-diagnosis"),
]}
register_pages(pages)
dashboard_ui._render_release_card(ReleaseNote(
    version="9.9.9", date="2026-09-01", source_ref="CHANGELOG.md#9.9.9",
    summary={"zh-TW": "摘要", "en-US": "Summary"},
    highlights=(ReleaseHighlight(
        id="demo", category="ux", protocols=("I2C",),
        title={"zh-TW": "標題", "en-US": "Title"},
        summary={"zh-TW": "說明", "en-US": "Details"},
        page="waveform-diff", doc=None,
    ),),
), "zh-TW")
dashboard_ui._render_quick_import()
'''
    ).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    links = _page_links(app)
    labels = {link.proto.label for link in links}
    assert "開啟功能頁面" in labels
    assert {"前往 Session 比對", "前往 Session 趨勢分析", "前往 I2C 診斷"} <= labels
    route_labels = {
        "開啟功能頁面": "waveform-diff",
        "前往 Session 比對": "session-compare",
        "前往 Session 趨勢分析": "session-analytics",
        "前往 I2C 診斷": "i2c-diagnosis",
    }
    for label, url_path in route_labels.items():
        link = next(item for item in links if item.proto.label == label)
        page = route_registry.resolve_page(url_path)
        assert page is not None
        assert link.proto.page_script_hash == page._script_hash


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
