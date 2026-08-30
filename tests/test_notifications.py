from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fw_diag_tool.gui import notifications


def test_show_toast_uses_streamlit_toast(monkeypatch: pytest.MonkeyPatch) -> None:
    toast = MagicMock()
    monkeypatch.setattr(notifications.st, "toast", toast)

    notifications.show_toast("完成", icon="🎉")

    toast.assert_called_once_with("完成", icon="🎉")


def test_show_toast_defaults_to_information_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    toast = MagicMock()
    monkeypatch.setattr(notifications.st, "toast", toast)

    notifications.show_toast("開始")

    toast.assert_called_once_with("開始", icon="ℹ️")


def test_show_success_toast_uses_check_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    toast = MagicMock()
    monkeypatch.setattr(notifications.st, "toast", toast)

    notifications.show_success_toast("分析完成")

    toast.assert_called_once_with("分析完成", icon="✅")


def test_show_error_toast_uses_cross_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    toast = MagicMock()
    monkeypatch.setattr(notifications.st, "toast", toast)

    notifications.show_error_toast("分析失敗")

    toast.assert_called_once_with("分析失敗", icon="❌")


def test_analysis_progress_completes_status(monkeypatch: pytest.MonkeyPatch) -> None:
    status = MagicMock()
    status.__enter__.return_value = status
    status_factory = MagicMock(return_value=status)
    monkeypatch.setattr(notifications.st, "status", status_factory)

    with notifications.analysis_progress("I2C", ["解析", "分析", "產生報告"]):
        pass

    status_factory.assert_called_once_with("I2C：解析 → 分析 → 產生報告", expanded=True)
    status.update.assert_called_once_with(label="I2C：分析完成", state="complete")
    status.__exit__.assert_called_once_with(None, None, None)


def test_analysis_progress_marks_error_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    status = MagicMock()
    status.__enter__.return_value = status
    status_factory = MagicMock(return_value=status)
    monkeypatch.setattr(notifications.st, "status", status_factory)

    with (
        pytest.raises(RuntimeError, match="boom"),
        notifications.analysis_progress("SPI", ["解析"]),
    ):
        raise RuntimeError("boom")

    status.update.assert_called_once_with(label="SPI：分析失敗", state="error")
    status.__exit__.assert_called_once()


def test_analysis_progress_yields_status_container(monkeypatch: pytest.MonkeyPatch) -> None:
    status = MagicMock()
    status.__enter__.return_value = status
    monkeypatch.setattr(notifications.st, "status", MagicMock(return_value=status))

    with notifications.analysis_progress("UART", ["解析"]) as current_status:
        assert current_status is status


def test_analysis_progress_handles_empty_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    status = MagicMock()
    status.__enter__.return_value = status
    status_factory = MagicMock(return_value=status)
    monkeypatch.setattr(notifications.st, "status", status_factory)

    with notifications.analysis_progress("PCIe", []):
        pass

    status_factory.assert_called_once_with("PCIe：分析進度", expanded=True)
