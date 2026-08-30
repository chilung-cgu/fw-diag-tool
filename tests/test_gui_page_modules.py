"""Parametrized import tests for all GUI page modules.

Each module must expose a callable render function.
"""

from __future__ import annotations

import importlib

import pytest

PAGE_MODULES = [
    "fw_diag_tool.gui.pages.board_profile_ui",
    "fw_diag_tool.gui.pages.i2c_diagnosis",
    "fw_diag_tool.gui.pages.i2c_builder_ui",
    "fw_diag_tool.gui.pages.waveform_diff_ui",
    "fw_diag_tool.gui.pages.uart_ui",
    "fw_diag_tool.gui.pages.mctp_ui",
    "fw_diag_tool.gui.pages.pcie_ui",
    "fw_diag_tool.gui.pages.spi_ui",
    "fw_diag_tool.gui.pages.dts_ui",
    "fw_diag_tool.gui.pages.register_ui",
    "fw_diag_tool.gui.pages.codegen_ui",
    "fw_diag_tool.gui.pages.fault_arena_ui",
    "fw_diag_tool.gui.pages.sop_ui",
    "fw_diag_tool.gui.pages.emulator_ui",
    "fw_diag_tool.gui.pages.chip_db_ui",
    "fw_diag_tool.gui.pages.fuzz_lab_ui",
    "fw_diag_tool.gui.pages.tutorial_ui",
    "fw_diag_tool.gui.pages.dashboard_ui",
]


@pytest.mark.parametrize("module_path", PAGE_MODULES)
def test_page_module_importable(module_path: str) -> None:
    mod = importlib.import_module(module_path)
    assert hasattr(mod, "render"), f"{module_path} must export render()"
    assert callable(mod.render), f"{module_path}.render must be callable"


def test_app_entry_importable() -> None:
    """The main app module must import without errors."""
    mod = importlib.import_module("fw_diag_tool.gui.app")
    assert mod is not None
