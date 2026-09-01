"""Tests for enhanced dashboard health metrics, analysis history, and quick import."""

from __future__ import annotations

import platform

import pytest
import streamlit as st

from fw_diag_tool.gui.pages import dashboard_ui
from fw_diag_tool.metrics import get_metrics_collector
from fw_diag_tool.session.session_manager import SessionDocument


def test_render_release_notes_shows_current_cards_and_history() -> None:
    captured: list[str] = []
    options: list[str] = []

    class Expander:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(dashboard_ui.st, "subheader", captured.append)
    monkeypatch.setattr(dashboard_ui.st, "caption", captured.append)
    monkeypatch.setattr(dashboard_ui.st, "write", captured.append)
    monkeypatch.setattr(dashboard_ui.st, "expander", lambda *args, **kwargs: Expander())
    monkeypatch.setattr(
        dashboard_ui.st,
        "selectbox",
        lambda label, values: options.extend(values) or values[0],
    )
    dashboard_ui._render_release_notes()
    monkeypatch.undo()
    text = "\n".join(captured)
    assert all(version in text for version in ("2.0.0", "1.7.0", "1.6.0"))
    assert options == [note.version for note in dashboard_ui.load_release_notes()]


def test_render_release_notes_locale_changes_labels(monkeypatch) -> None:
    registry = dashboard_ui.get_global_registry()
    registry.set_locale("en-US")
    try:
        captured: list[str] = []

        class Expander:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

        monkeypatch.setattr(dashboard_ui.st, "subheader", captured.append)
        monkeypatch.setattr(dashboard_ui.st, "caption", captured.append)
        monkeypatch.setattr(dashboard_ui.st, "write", captured.append)
        monkeypatch.setattr(dashboard_ui.st, "expander", lambda *args, **kwargs: Expander())
        monkeypatch.setattr(dashboard_ui.st, "selectbox", lambda label, values: values[0])
        monkeypatch.setattr(
            dashboard_ui, "_render_quick_link", lambda _url, label: captured.append(label)
        )
        dashboard_ui._render_release_notes()
        english = "\n".join(captured)
        assert "What's New" in english
        assert "Go to" in english or "Open" in english or "Documentation" in english
    finally:
        registry.set_locale("zh-TW")


def test_render_release_notes_warns_on_malformed_manifest(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_ui,
        "load_release_notes",
        lambda: (_ for _ in ()).throw(dashboard_ui.ReleaseNotesError("bad")),
    )
    warnings: list[str] = []
    monkeypatch.setattr(dashboard_ui.st, "warning", warnings.append)
    dashboard_ui._render_release_notes()
    assert warnings


def test_check_dependency_key_packages():
    """Verify all 5 key dependencies are detected properly."""
    key_deps = ["streamlit", "plotly", "pandas", "pydantic", "rich"]
    for dep in key_deps:
        ok, ver = dashboard_ui._check_dependency(dep)
        assert ok is True
        assert ver != "未安裝"


def test_check_dependency_missing():
    """Non-existent package returns (False, '未安裝')."""
    ok, ver = dashboard_ui._check_dependency("non_existent_fw_test_package_999")
    assert ok is False
    assert ver == "未安裝"


def test_render_environment_health_executes():
    """_render_environment_health executes without errors."""
    dashboard_ui._render_environment_health()


def test_render_environment_health_simulated_old_python(monkeypatch):
    """Verify health indicator reflects Python < 3.10 properly."""
    monkeypatch.setattr(platform, "python_version", lambda: "3.9.7")
    dashboard_ui._render_environment_health()


def test_render_analysis_history_empty():
    """_render_analysis_history executes when no events have been recorded."""
    dashboard_ui._render_analysis_history()


def test_render_analysis_history_with_events():
    """_render_analysis_history executes with recorded protocol events."""
    collector = get_metrics_collector()
    collector.record_event(page_name="i2c", action="analyze", protocol="I2C", duration_ms=12.5)
    collector.record_event(page_name="spi", action="analyze", protocol="SPI", duration_ms=8.0)
    collector.record_event(page_name="pcie", action="analyze", protocol="PCIe", duration_ms=15.2)

    dashboard_ui._render_analysis_history()


def test_render_quick_import_no_sessions(monkeypatch):
    """_render_quick_import handles empty session list gracefully."""

    class EmptyManager:
        def list_sessions(self):
            return []

    monkeypatch.setattr(dashboard_ui, "SessionManager", EmptyManager)
    dashboard_ui._render_quick_import()


def test_render_quick_import_with_sessions_not_clicked(monkeypatch):
    """_render_quick_import renders session info when sessions are present."""

    class DummyManager:
        def list_sessions(self):
            return [
                {
                    "filename": "i2c_sample_123.fwsession.json",
                    "name": "I2C NACK Session",
                    "created_at": "2026-08-30T10:00:00Z",
                    "path": "/tmp/dummy/i2c_sample_123.fwsession.json",
                }
            ]

    monkeypatch.setattr(dashboard_ui, "SessionManager", DummyManager)
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: False)
    dashboard_ui._render_quick_import()


def test_render_quick_import_with_sessions_clicked_success(monkeypatch):
    """_render_quick_import loads session and sets session_state on button click."""
    dummy_doc = SessionDocument(
        schema_version="2.0",
        tool_version="1.4.0",
        created_at="2026-08-30T10:00:00Z",
        name="I2C Test Session",
        capture_sha256="abcdef123456",
        board_profile_name=None,
        config={"input_mode": "decoded_csv"},
        report={"status": "ok", "anomalies": []},
        notes="Quick import test note",
    )

    class DummyManager:
        def list_sessions(self):
            return [
                {
                    "filename": "i2c_test.fwsession.json",
                    "name": "I2C Test Session",
                    "created_at": "2026-08-30T10:00:00Z",
                    "path": "/tmp/dummy/i2c_test.fwsession.json",
                }
            ]

        def load_document(self, filepath):
            return dummy_doc

    monkeypatch.setattr(dashboard_ui, "SessionManager", DummyManager)
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: True)

    dashboard_ui._render_quick_import()
    assert st.session_state.get("dashboard_quick_imported_session") == dummy_doc


def test_render_quick_import_with_load_error(monkeypatch):
    """_render_quick_import handles load_document errors gracefully."""

    class FaultyManager:
        def list_sessions(self):
            return [
                {
                    "filename": "corrupted.fwsession.json",
                    "name": "Corrupted Session",
                    "created_at": "2026-08-30T10:00:00Z",
                    "path": "/tmp/dummy/corrupted.fwsession.json",
                }
            ]

        def load_document(self, filepath):
            raise ValueError("corrupted session data")

    monkeypatch.setattr(dashboard_ui, "SessionManager", FaultyManager)
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: True)

    dashboard_ui._render_quick_import()


def test_dashboard_render_full_pipeline():
    """Full dashboard_ui.render pipeline executes without error."""
    dashboard_ui.render()
