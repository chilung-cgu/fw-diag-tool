"""批次分析（Batch Analysis）GUI 頁面。

支援多檔案上傳、自動/手動指定協定分析、綜合結果檢視與 ZIP 報告打包下載。
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES
from fw_diag_tool.i18n import t
from fw_diag_tool.reporting.batch import batch_analyze_directory

MAX_UPLOAD_MIB = max(1, MAX_UPLOAD_BYTES // (1024 * 1024))
_PROTOCOL_CHOICES = ["auto", "i2c", "spi", "uart", "pcie"]


def _tr(key: str, fallback: str, **kwargs: Any) -> str:
    translated = t(key, domain="gui", **kwargs)
    return fallback if translated == key else translated


def build_batch_dataframe(entries: list[dict[str, Any]]) -> pd.DataFrame:
    """將批次分析結果 entries 整理為 Streamlit 可呈現的 DataFrame。"""
    rows: list[dict[str, Any]] = []
    for entry in entries:
        filename = entry.get("filename") or Path(entry.get("file", "")).name
        protocol = str(entry.get("protocol", "")).upper()
        status_raw = entry.get("status", "unknown")
        if status_raw == "success":
            status_display = "✔ 成功 (Success)"
        elif status_raw == "warning":
            status_display = "⚠ 警告 (Warning)"
        elif status_raw == "error":
            status_display = "✖ 錯誤 (Error)"
        else:
            status_display = str(status_raw)

        findings_count = entry.get("findings_count", len(entry.get("findings", [])))
        rows.append(
            {
                "檔名（Filename）": filename,
                "協定（Protocol）": protocol,
                "狀態（Status）": status_display,
                "問題數（Findings）": findings_count,
            }
        )
    return pd.DataFrame(rows)


def create_reports_zip(output_dir: Path | str) -> bytes:
    """將 output_dir 內的所有報告檔案打包為 ZIP bytes。"""
    out_p = Path(output_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(out_p.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(out_p))
    return buffer.getvalue()


def render() -> None:
    """Streamlit 批次分析頁面渲染入口。"""
    st.header(_tr("title_batch_analysis", "批次分析（Batch Analysis）"))
    st.caption(
        _tr(
            "batch_analysis_caption",
            "批次上傳多個韌體追蹤或日誌檔案（支援 .csv, .log, .txt, .hex），"
            "自動或指定協定進行平行診斷並產生綜合報告與 ZIP 封裝。",
        )
    )

    protocol_choice = st.selectbox(
        _tr("batch_protocol_select_label", "協定選擇（Protocol Selection）"),
        options=_PROTOCOL_CHOICES,
        format_func=lambda val: {
            "auto": _tr("batch_proto_auto", "自動偵測（Auto Detect）"),
            "i2c": "I2C / PMBus",
            "spi": "SPI Flash",
            "uart": "UART Crash Dump",
            "pcie": "PCIe Config / AER",
        }.get(val, str(val)),
        key="batch_protocol_mode",
    )

    uploaded_files = st.file_uploader(
        _tr("batch_uploader_label", "上傳多個檔案（支援 .csv, .log, .txt, .hex）"),
        type=["csv", "log", "txt", "hex"],
        accept_multiple_files=True,
        max_upload_size=MAX_UPLOAD_MIB,
        key="batch_files_uploader",
    )

    if st.button(_tr("batch_btn_start", "開始批次分析"), key="batch_btn_analyze"):
        if not uploaded_files:
            st.warning(_tr("batch_empty_warning", "請先上傳至少一個檔案再進行批次分析。"))
            render_page_footer()
            return

        protocols = None if protocol_choice == "auto" else [protocol_choice]

        try:
            with tempfile.TemporaryDirectory() as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                input_dir = temp_dir / "inputs"
                output_dir = temp_dir / "outputs"
                input_dir.mkdir(parents=True, exist_ok=True)
                output_dir.mkdir(parents=True, exist_ok=True)

                for uploaded in uploaded_files:
                    if uploaded.size > MAX_UPLOAD_BYTES:
                        raise ValueError(
                            f"檔案 {uploaded.name} 超過 20 MiB 上限；請先裁切 trace 再分析"
                        )
                    file_path = input_dir / Path(uploaded.name).name
                    file_path.write_bytes(uploaded.getvalue())

                entries = batch_analyze_directory(
                    directory=input_dir,
                    protocols=protocols,
                    output_dir=output_dir,
                    formats=["markdown", "html", "sarif"],
                )

                if not entries:
                    st.warning(
                        _tr(
                            "batch_no_files_analyzed",
                            "未找到符合指定協定或格式的檔案可進行分析。",
                        )
                    )
                    render_page_footer()
                    return

                total_count = len(entries)
                success_count = sum(1 for e in entries if e.get("status") == "success")
                warning_count = sum(1 for e in entries if e.get("status") == "warning")
                error_count = sum(1 for e in entries if e.get("status") == "error")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(_tr("batch_metric_total", "總檔案數"), total_count)
                c2.metric(_tr("batch_metric_success", "成功"), success_count)
                c3.metric(_tr("batch_metric_warning", "警告"), warning_count)
                c4.metric(_tr("batch_metric_error", "錯誤"), error_count)

                df = build_batch_dataframe(entries)
                st.dataframe(df, use_container_width=True, hide_index=True)

                if error_count > 0:
                    st.error(f"批次分析完成：共 {total_count} 個檔案，其中 {error_count} 個出現錯誤。")
                elif warning_count > 0:
                    st.warning(f"批次分析完成：共 {total_count} 個檔案，其中 {warning_count} 個有警告異常。")
                else:
                    st.success(f"批次分析完成：全部 {total_count} 個檔案分析成功且無異常！")

                zip_bytes = create_reports_zip(output_dir)
                st.download_button(
                    label=_tr(
                        "batch_download_zip_btn",
                        "📦 下載全部報告 ZIP（Download All Reports ZIP）",
                    ),
                    data=zip_bytes,
                    file_name="batch_analysis_reports.zip",
                    mime="application/zip",
                    key="batch_download_zip",
                )

        except Exception as exc:
            st.error(f"批次分析失敗：{exc}")

    render_page_footer()


__all__ = ["build_batch_dataframe", "create_reports_zip", "render"]
