"""Unit and GUI tests for the Interactive Tutorial (tutorial_ui) page."""

from __future__ import annotations

import importlib

from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.pages.tutorial_ui import (
    DEFAULT_BOARD_PROFILE_YAML,
    DEFAULT_UART_PANIC_LOG,
    LEARNING_PATHS,
    STEP_RENDERERS,
    TUTORIAL_STEPS,
)


def tutorial_render() -> None:
    from fw_diag_tool.gui.pages.tutorial_ui import render

    render()


def test_tutorial_module_import_and_render_callable() -> None:
    """Test that tutorial_ui is importable and exposes a callable render function."""
    mod = importlib.import_module("fw_diag_tool.gui.pages.tutorial_ui")
    assert hasattr(mod, "render")
    assert callable(mod.render)
    assert "render" in mod.__all__


def test_tutorial_step_data_structures() -> None:
    """Test structure and completeness of TUTORIAL_STEPS and LEARNING_PATHS."""
    assert len(TUTORIAL_STEPS) >= 6
    step_ids = [step["id"] for step in TUTORIAL_STEPS]
    assert step_ids == [1, 2, 3, 4, 5, 6]

    for step in TUTORIAL_STEPS:
        assert "id" in step
        assert "title" in step
        assert "short_title" in step
        assert "summary" in step
        assert "badge" in step
        assert len(step["summary"]) > 20
        assert step["id"] in STEP_RENDERERS
        assert callable(STEP_RENDERERS[step["id"]])

    assert "🟢 零基礎入門" in LEARNING_PATHS
    assert "🟡 已有硬體經驗" in LEARNING_PATHS
    assert "🔴 進階使用" in LEARNING_PATHS

    for path_info in LEARNING_PATHS.values():
        assert "desc" in path_info
        assert "steps" in path_info
        assert len(path_info["steps"]) > 0
        for sid in path_info["steps"]:
            assert sid in step_ids


def test_default_assets_validity() -> None:
    """Verify default YAML and log snippets parse without error."""
    from fw_diag_tool.board_profile import load_board_profile
    from fw_diag_tool.uart.parser import UARTCrashParser

    profile = load_board_profile(DEFAULT_BOARD_PROFILE_YAML)
    assert profile.board_name == "demo-carrier-board"
    assert len(profile.i2c_buses) == 1
    assert len(profile.i2c_buses[0].devices) == 2

    rep = UARTCrashParser.parse_log_text(DEFAULT_UART_PANIC_LOG)
    assert rep.kernel_panic is not None
    assert (
        rep.kernel_panic.faulting_func is not None
        and "nvme_pci_complete_rq" in rep.kernel_panic.faulting_func
    )


def test_apptest_tutorial_ui_renders_default() -> None:
    """Test initial render of the interactive tutorial page via AppTest."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    assert not at.exception
    assert any("互動式教學導覽" in str(item.value) for item in at.header)
    assert any("學習路徑選擇" in str(item.label) for item in at.radio)
    assert len(at.get("progress")) == 1
    assert at.get("progress")[0].value == 0


def test_apptest_tutorial_ui_step1_interaction() -> None:
    """Test clicking Step 1 interactive button and verifying decoding results."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step1 = next(b for b in at.button if b.key == "btn_run_step_1")
    btn_step1.click().run()

    assert not at.exception
    assert any("總傳輸次數" in str(m.label) for m in at.metric)
    assert any(m.value == "18 筆" for m in at.metric)
    assert any("成功解析 I2C 交易序列" in str(s.value) for s in at.success)


def test_apptest_tutorial_ui_step2_interaction() -> None:
    """Test clicking Step 2 interactive button for NACK anomaly detection."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step2 = next(b for b in at.button if b.key == "btn_run_step_2")
    btn_step2.click().run()

    assert not at.exception
    assert any("偵測到" in str(e.value) and "異常" in str(e.value) for e in at.error)


def test_apptest_tutorial_ui_step3_interaction() -> None:
    """Test clicking Step 3 interactive button for Waveform reconstruction."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step3 = next(b for b in at.button if b.key == "btn_run_step_3")
    btn_step3.click().run()

    assert not at.exception
    assert any("波形顏色標記說明" in str(c.value) for c in at.caption)


def test_apptest_tutorial_ui_step4_interaction() -> None:
    """Test clicking Step 4 interactive button for SPI Flash sequence."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step4 = next(b for b in at.button if b.key == "btn_run_step_4")
    btn_step4.click().run()

    assert not at.exception
    assert any(m.label == "總傳輸次數" and m.value == "4 次" for m in at.metric)
    assert any("Winbond W25Q128" in str(m.value) for m in at.metric)


def test_apptest_tutorial_ui_step5_interaction() -> None:
    """Test clicking Step 5 interactive button for UART crash parsing."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step5 = next(b for b in at.button if b.key == "btn_run_step_5")
    btn_step5.click().run()

    assert not at.exception
    assert any("核心崩潰原因" in str(e.value) for e in at.error)
    assert any("nvme_pci_complete_rq" in str(s.value) for s in at.success)


def test_apptest_tutorial_ui_step6_interaction() -> None:
    """Test clicking Step 6 interactive button for Board Profile validation."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()
    btn_step6 = next(b for b in at.button if b.key == "btn_run_step_6")
    btn_step6.click().run()

    assert not at.exception
    assert any("Board Profile 格式正確" in str(s.value) for s in at.success)


def test_apptest_tutorial_ui_progress_and_completion() -> None:
    """Test marking steps as complete, updating progress, and resetting."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()

    # Mark Step 1 done
    mark_done_1 = next(b for b in at.button if b.key == "btn_mark_done_1")
    mark_done_1.click().run()

    assert not at.exception
    assert 1 in at.session_state["tutorial_completed_steps"]
    assert at.get("progress")[0].value == int(1 / 6 * 100)

    # Mark remaining steps in beginner path (2, 3, 4, 5, 6)
    for sid in [2, 3, 4, 5, 6]:
        btn = next(b for b in at.button if b.key == f"btn_mark_done_{sid}")
        btn.click().run()

    assert not at.exception
    assert at.get("progress")[0].value == 100
    assert any("恭喜！你已完成此學習路徑的所有步驟" in str(s.value) for s in at.success)

    # Test Reset button
    reset_btn = next(b for b in at.button if b.key == "btn_reset_tutorial_progress")
    reset_btn.click().run()

    assert not at.exception
    assert len(at.session_state["tutorial_completed_steps"]) == 0
    assert at.get("progress")[0].value == 0


def test_apptest_tutorial_ui_path_switching() -> None:
    """Test switching learning paths filters steps accordingly."""
    at = AppTest.from_function(tutorial_render, default_timeout=15).run()

    # Default path has 6 steps (Step 1 to 6)
    assert any(b.key == "btn_mark_done_1" for b in at.button)

    # Switch to Advanced Path (Steps 4, 5, 6)
    at.radio(key="tutorial_learning_path_radio").set_value("🔴 進階使用").run()
    assert not at.exception
    assert at.get("progress")[0].value == 0
    assert not any(b.key == "btn_mark_done_1" for b in at.button)
    assert any(b.key == "btn_mark_done_4" for b in at.button)
    assert any(b.key == "btn_mark_done_6" for b in at.button)
