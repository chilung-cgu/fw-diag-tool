"""Test that all new GUI page modules can be imported and expose render()."""

from __future__ import annotations

import importlib

import pytest

NEW_MODULES = [
    "fw_diag_tool.gui.pages.emulator_ui",
    "fw_diag_tool.gui.pages.chip_db_ui",
    "fw_diag_tool.gui.pages.fuzz_lab_ui",
    "fw_diag_tool.gui.pages.dashboard_ui",
]


@pytest.mark.parametrize("module_name", NEW_MODULES)
def test_module_imports(module_name: str) -> None:
    """Verify each new GUI page module is importable and exposes a callable render function."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "render"), f"{module_name} must export render()"
    assert callable(mod.render), f"{module_name}.render must be callable"
