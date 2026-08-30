"""Tests for dashboard health check panel."""

from __future__ import annotations

import platform


def test_check_dependency_importable() -> None:
    """_check_dependency is importable from dashboard_ui."""
    from fw_diag_tool.gui.pages.dashboard_ui import _check_dependency

    assert callable(_check_dependency)


def test_check_core_dep_streamlit() -> None:
    """Core dependency streamlit should be detected as installed."""
    from fw_diag_tool.gui.pages.dashboard_ui import _check_dependency

    ok, version = _check_dependency("streamlit")
    assert ok is True
    assert version != "未安裝"


def test_check_missing_dep() -> None:
    """A non-existent package should return (False, '未安裝')."""
    from fw_diag_tool.gui.pages.dashboard_ui import _check_dependency

    ok, version = _check_dependency("this_package_does_not_exist_xyz_123")
    assert ok is False
    assert version == "未安裝"


def test_check_python_version_sufficient() -> None:
    """Current Python should be >= 3.10 (project requirement)."""
    py_ver = platform.python_version()
    parts = tuple(int(x) for x in py_ver.split(".")[:2])
    assert parts >= (3, 10)


def test_render_health_check_importable() -> None:
    """_render_health_check is importable from dashboard_ui."""
    from fw_diag_tool.gui.pages.dashboard_ui import _render_health_check

    assert callable(_render_health_check)


def test_check_optional_dep_fpdf2() -> None:
    """fpdf2 detection works regardless of installation status."""
    from fw_diag_tool.gui.pages.dashboard_ui import _check_dependency

    ok, version = _check_dependency("fpdf2")
    # fpdf2 may or may not be installed, but function must not raise
    assert isinstance(ok, bool)
    assert isinstance(version, str)
