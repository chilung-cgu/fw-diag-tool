"""Tests for Batch Analysis GUI page."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from fw_diag_tool.gui.pages import batch_ui
from fw_diag_tool.gui.pages.batch_ui import (
    build_batch_dataframe,
    create_reports_zip,
    render,
)
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES


@dataclass
class DummyUploadedFile:
    name: str
    content: bytes
    reported_size: int | None = None

    @property
    def size(self) -> int:
        return self.reported_size if self.reported_size is not None else len(self.content)

    def getvalue(self) -> bytes:
        return self.content


def test_batch_ui_imports_and_all_attribute() -> None:
    """測試 render 函式可被 import 且 __all__ 包含 'render'。"""
    assert callable(render)
    assert hasattr(batch_ui, "__all__")
    assert "render" in batch_ui.__all__


def test_build_batch_dataframe_formats_columns_and_statuses() -> None:
    """測試 build_batch_dataframe 正確解析並格式化狀態與欄位。"""
    entries = [
        {
            "filename": "i2c_trace.csv",
            "protocol": "i2c",
            "status": "success",
            "findings_count": 0,
        },
        {
            "filename": "spi_dump.csv",
            "protocol": "spi",
            "status": "warning",
            "findings_count": 2,
        },
        {
            "filename": "uart_crash.log",
            "protocol": "uart",
            "status": "error",
            "findings_count": 1,
        },
        {
            "file": "/path/to/pcie_aer.txt",
            "protocol": "pcie",
            "status": "custom_status",
            "findings": [{"code": "ERR_1"}],
        },
    ]

    df = build_batch_dataframe(entries)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "檔名（Filename）",
        "協定（Protocol）",
        "狀態（Status）",
        "問題數（Findings）",
    ]

    rows = df.to_dict(orient="records")
    assert rows[0]["檔名（Filename）"] == "i2c_trace.csv"
    assert rows[0]["協定（Protocol）"] == "I2C"
    assert rows[0]["狀態（Status）"] == "✔ 成功 (Success)"
    assert rows[0]["問題數（Findings）"] == 0

    assert rows[1]["檔名（Filename）"] == "spi_dump.csv"
    assert rows[1]["協定（Protocol）"] == "SPI"
    assert rows[1]["狀態（Status）"] == "⚠ 警告 (Warning)"
    assert rows[1]["問題數（Findings）"] == 2

    assert rows[2]["檔名（Filename）"] == "uart_crash.log"
    assert rows[2]["協定（Protocol）"] == "UART"
    assert rows[2]["狀態（Status）"] == "✖ 錯誤 (Error)"
    assert rows[2]["問題數（Findings）"] == 1

    assert rows[3]["檔名（Filename）"] == "pcie_aer.txt"
    assert rows[3]["協定（Protocol）"] == "PCIE"
    assert rows[3]["狀態（Status）"] == "custom_status"
    assert rows[3]["問題數（Findings）"] == 1


def test_create_reports_zip_compresses_directory_files(tmp_path: Path) -> None:
    """測試 create_reports_zip 能將目錄結構完整壓縮為有效 ZIP。"""
    report_md = tmp_path / "i2c_report.md"
    report_md.write_text("# I2C Report", encoding="utf-8")
    report_html = tmp_path / "i2c_report.html"
    report_html.write_text("<html>Report</html>", encoding="utf-8")
    manifest = tmp_path / "batch_manifest.json"
    manifest.write_text('{"total": 1}', encoding="utf-8")

    zip_bytes = create_reports_zip(tmp_path)
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "i2c_report.md" in namelist
        assert "i2c_report.html" in namelist
        assert "batch_manifest.json" in namelist
        assert zf.read("i2c_report.md").decode("utf-8") == "# I2C Report"


def test_render_empty_upload_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """整合測試：未上傳任何檔案時點擊按鈕應顯示警告。"""
    mock_warning = MagicMock()
    mock_button = MagicMock(return_value=True)
    mock_file_uploader = MagicMock(return_value=[])

    monkeypatch.setattr(batch_ui.st, "warning", mock_warning)
    monkeypatch.setattr(batch_ui.st, "button", mock_button)
    monkeypatch.setattr(batch_ui.st, "file_uploader", mock_file_uploader)
    monkeypatch.setattr(batch_ui.st, "selectbox", MagicMock(return_value="auto"))

    render()

    mock_warning.assert_called_once()
    assert "請先上傳至少一個檔案" in mock_warning.call_args[0][0]


def test_render_successful_batch_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """整合測試：多檔案批次分析成功並呈現表格、指標與下載按鈕。"""
    dummy_files = [
        DummyUploadedFile(
            name="i2c_test.csv",
            content=b"Time [s],Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,0,0x50,0x00,Write,ACK\n",
        ),
        DummyUploadedFile(
            name="uart_test.log",
            content=b"Kernel panic - not syncing: Fatal exception\n",
        ),
    ]

    mock_dataframe = MagicMock()
    mock_download_button = MagicMock()
    mock_columns = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock(), MagicMock()])
    mock_error = MagicMock()

    monkeypatch.setattr(batch_ui.st, "button", MagicMock(return_value=True))
    monkeypatch.setattr(batch_ui.st, "file_uploader", MagicMock(return_value=dummy_files))
    monkeypatch.setattr(batch_ui.st, "selectbox", MagicMock(return_value="auto"))
    monkeypatch.setattr(batch_ui.st, "dataframe", mock_dataframe)
    monkeypatch.setattr(batch_ui.st, "columns", mock_columns)
    monkeypatch.setattr(batch_ui.st, "download_button", mock_download_button)
    monkeypatch.setattr(batch_ui.st, "error", mock_error)

    render()

    mock_dataframe.assert_called_once()
    df_arg = mock_dataframe.call_args[0][0]
    assert isinstance(df_arg, pd.DataFrame)
    assert len(df_arg) == 2

    mock_download_button.assert_called_once()
    dl_kwargs = mock_download_button.call_args[1]
    assert dl_kwargs["file_name"] == "batch_analysis_reports.zip"
    assert dl_kwargs["mime"] == "application/zip"


def test_render_file_exceeds_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """整合測試：上傳檔案超過大小限制時應拋出並捕捉錯誤。"""
    oversized_file = DummyUploadedFile(
        name="huge.csv",
        content=b"large data",
        reported_size=MAX_UPLOAD_BYTES + 1024,
    )

    mock_error = MagicMock()
    monkeypatch.setattr(batch_ui.st, "button", MagicMock(return_value=True))
    monkeypatch.setattr(batch_ui.st, "file_uploader", MagicMock(return_value=[oversized_file]))
    monkeypatch.setattr(batch_ui.st, "selectbox", MagicMock(return_value="auto"))
    monkeypatch.setattr(batch_ui.st, "error", mock_error)

    render()

    mock_error.assert_called_once()
    assert "超過 20 MiB 上限" in mock_error.call_args[0][0]


def test_render_analysis_exception_handled(monkeypatch: pytest.MonkeyPatch) -> None:
    """整合測試：batch_analyze_directory 發生例外時應優雅顯示錯誤。"""
    dummy_files = [DummyUploadedFile(name="sample.csv", content=b"dummy")]

    mock_error = MagicMock()
    monkeypatch.setattr(batch_ui.st, "button", MagicMock(return_value=True))
    monkeypatch.setattr(batch_ui.st, "file_uploader", MagicMock(return_value=dummy_files))
    monkeypatch.setattr(batch_ui.st, "selectbox", MagicMock(return_value="auto"))
    monkeypatch.setattr(
        batch_ui,
        "batch_analyze_directory",
        MagicMock(side_effect=RuntimeError("Simulated engine failure")),
    )
    monkeypatch.setattr(batch_ui.st, "error", mock_error)

    render()

    mock_error.assert_called_once()
    assert "Simulated engine failure" in mock_error.call_args[0][0]
