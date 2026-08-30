from __future__ import annotations

from typing import Any

import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.reporting.sarif import build_sarif_report


def render_sarif_download(
    findings: list[dict[str, Any]],
    *,
    protocol: str,
    filename_prefix: str = "fw_diag",
) -> None:
    """在 GUI 頁面底部顯示 SARIF 下載按鈕。"""
    if not findings:
        return
    sarif_json = build_sarif_report(
        tool_name=f"fw-diag-tool ({protocol})",
        tool_version=__version__,
        findings=findings,
    )
    st.download_button(
        f"📥 下載 SARIF 報告（{protocol}）",
        data=sarif_json,
        file_name=f"{filename_prefix}_{protocol.lower()}.sarif.json",
        mime="application/json",
        key=f"sarif_download_{protocol.lower()}",
    )


__all__ = ["render_sarif_download"]
