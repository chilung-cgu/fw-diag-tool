from __future__ import annotations

import contextlib
import dataclasses
import json
from typing import Any

import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.gui.guide_resources import load_guide_text, prepare_guide_markdown
from fw_diag_tool.gui.localization_maps import (
    _FAULT_ARENA_CASES_ZH,
    _PCIE_INPUT_ERROR_ZH,
    _REGISTER_DESCRIPTION_ZH,
    _REGISTER_MEANING_ZH,
    _localize_gui_error,
    _localize_mctp_error,
    _localize_pcie_input_error,
    _localize_register_description,
    _localize_register_meaning,
)
from fw_diag_tool.gui.page_index import (
    PAGE_INDEX,
    render_breadcrumb,
    render_global_search,
    render_keyboard_shortcuts,
)
from fw_diag_tool.gui.pages.i2c_page import analyze_i2c as analyze_i2c_controller
from fw_diag_tool.gui.theme import get_current_theme, get_plotly_template
from fw_diag_tool.i2c.input import I2CInputFormat
from fw_diag_tool.i18n import TranslationRegistry, get_global_registry
from fw_diag_tool.limits import AnalysisLimits
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine

DEFAULT_I2C_TIMEOUT_MS = 25.0

# GUI uses fixed safe limits independent of CLI overrides.
GUI_ANALYSIS_LIMITS = AnalysisLimits()
MAX_PACKET_HEX_CHARS = 64 * 1024


def _reset_i2c_session_state() -> None:
    st.session_state["i2c_input_format"] = I2CInputFormat.DECODED_CSV.value
    st.session_state["i2c_smbus_timeout"] = DEFAULT_I2C_TIMEOUT_MS
    st.session_state["i2c_board_profile_yaml"] = ""
    # A session upload supersedes any previously selected teaching sample.
    # Leaving the sample active would analyze the old decoded bytes using the
    # restored raw/text mode when the session is uploaded without its capture.
    st.session_state["i2c_sample_active"] = False
    st.session_state.pop("i2c_sample_content", None)
    st.session_state.pop("i2c_sample_key", None)
    st.session_state.pop("i2c_loaded_session_identity", None)


@st.cache_data(show_spinner="正在解析 I2C 輸入資料…")
def analyze_i2c_input(
    csv_content: str,
    input_mode: str,
    smbus_timeout_ms: float,
    board_profile_yaml: str | None = None,
) -> tuple[Any, Any]:
    profile = load_board_profile(board_profile_yaml) if board_profile_yaml else None
    return analyze_i2c_controller(
        csv_content,
        input_mode=input_mode,
        input_format=None,
        smbus_timeout_ms=smbus_timeout_ms,
        board_profile=profile,
        limits=GUI_ANALYSIS_LIMITS,
    )


@st.cache_data(show_spinner="正在解析 SPI 輸入資料…")
def analyze_spi_input(csv_content: str, max_page_size: int = 256) -> Any:
    return SPIDiagnosticEngine(max_page_size=max_page_size).analyze_csv_content(csv_content)


@st.cache_data(show_spinner="正在解析 PCIe 輸入資料…")
def analyze_pcie_input(text: str) -> list[Any]:
    stripped = text.strip()
    if "PCIe Bus Error:" in stripped or (
        "AER:" in stripped
        and "lspci" not in stripped.lower()
        and not any(line.strip().startswith("00:") for line in stripped.splitlines())
    ):
        return PCIeAnalyzer.parse_dmesg_aer(stripped)
    devices = PCIeAnalyzer.parse_multi_lspci_text(stripped)
    if not devices:
        bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(stripped)
        devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
    return devices


@st.cache_data(show_spinner="正在解析 MCTP/IPMB 輸入資料…")
def analyze_mctp_input(
    text: str,
    protocol_mode: str = "auto",
) -> Any:
    return ServerMgmtParser.parse_hex_input(text, protocol_mode=protocol_mode)


def render_html_download(
    markdown_report: str,
    protocol: str = "I2C",
    filename_prefix: str = "fw_diag",
    title: str | None = None,
) -> None:
    """在 GUI 頁面顯示 HTML 報告下載按鈕。"""
    if not markdown_report:
        return
    from fw_diag_tool.reporting.html_report import convert_markdown_to_html

    html_content = convert_markdown_to_html(
        markdown_report,
        title=title or f"韌體診斷報告（{protocol} Diagnostic Report）",
        theme=get_current_theme(),
    )
    file_name = (
        f"{filename_prefix}.html"
        if filename_prefix.endswith(".html")
        else (
            f"{filename_prefix}.html"
            if protocol.lower() in filename_prefix.lower()
            else f"{filename_prefix}_{protocol.lower()}.html"
        )
    )
    st.download_button(
        f"下載 HTML 報告（{protocol}）",
        data=html_content,
        file_name=file_name,
        mime="text/html",
        key=f"html_download_{protocol.lower()}",
    )


def render_pdf_download(
    markdown_report: str = "",
    protocol: str = "I2C",
    filename_prefix: str = "fw_diag",
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """在 GUI 頁面顯示 PDF 報告下載按鈕。若 fpdf2 未安裝則顯示提示訊息。"""
    actual_title = title
    actual_md = markdown_report
    actual_meta = metadata
    actual_protocol = protocol

    if "markdown_content" in kwargs:
        actual_md = kwargs["markdown_content"]
        if "title" in kwargs:
            actual_title = kwargs["title"]
        elif markdown_report and not ("\n" in markdown_report or len(markdown_report) > 100):
            actual_title = markdown_report
        if "metadata" in kwargs:
            actual_meta = kwargs["metadata"]
    elif "\n" in protocol or (len(protocol) > 100 and "\n" not in markdown_report):
        actual_title = markdown_report
        actual_md = protocol
        if isinstance(filename_prefix, dict):
            actual_meta = filename_prefix
            filename_prefix = "fw_diag"
        actual_protocol = "Report"

    if not actual_md:
        return

    from fw_diag_tool.reporting.pdf_report import build_pdf_report, is_fpdf_available

    if not is_fpdf_available():
        st.info("PDF 匯出需安裝 pdf 額外套件：`pip install fw-diag-tool[pdf]`")
        return

    try:
        report_title = actual_title or f"韌體診斷報告（{actual_protocol} Diagnostic Report）"
        pdf_bytes = build_pdf_report(
            title=report_title,
            markdown_content=actual_md,
            metadata=actual_meta,
        )
        clean_proto = actual_protocol.lower()
        file_name = (
            f"{filename_prefix}.pdf"
            if filename_prefix.endswith(".pdf")
            else (
                f"{filename_prefix}.pdf"
                if clean_proto in filename_prefix.lower()
                else f"{filename_prefix}_{clean_proto}.pdf"
            )
        )
        clean_key_prefix = filename_prefix.replace(".", "_").replace("-", "_")
        st.download_button(
            f"下載 PDF 報告（{actual_protocol}）",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            key=f"pdf_download_{clean_proto}_{clean_key_prefix}",
        )
    except Exception as exc:
        st.warning(f"PDF 報告產生失敗：{exc}")


def render_guide_expander(
    chapter_rel_path: str,
    label: str = "📖 點擊展開本功能詳細實戰教學手冊",
    fallback_title: str | None = None,
    fallback_body: str | None = None,
) -> None:
    markdown = load_guide_text(chapter_rel_path)
    if markdown is not None:
        with st.expander(label, expanded=False):
            st.markdown(prepare_guide_markdown(markdown, chapter_rel_path))
    elif fallback_body is not None:
        with st.expander(fallback_title or label, expanded=False):
            st.markdown(fallback_body)


def render_page_footer() -> None:
    """在頁面底部顯示統一的 footer 資訊。"""
    st.divider()
    st.caption(
        f"fw-diag-tool v{__version__} • "
        "專為韌體與嵌入式系統工程師打造的離線診斷分析套件 • "
        "[GitHub](https://github.com/chilung-cgu/fw-diag-tool)"
    )


def render_session_controls(
    protocol: str,
    report_data: dict[str, Any] | None,
    config_data: dict[str, Any] | None = None,
    *,
    key_prefix: str | None = None,
    include_uploader: bool = True,
) -> dict[str, Any] | None:
    """通用 session 存讀控件。

    Args:
        protocol: 協定名稱 (如 "spi", "uart")
        report_data: 分析報告 dict
        config_data: 設定 dict
        key_prefix: 自訂 widget key 前綴 (避免同一頁面 key 重複)
        include_uploader: 是否包含 session 上傳元件 (若頁面已有自訂 session 上傳可設為 False)

    Returns:
        如果載入了 session，回傳 report dict；否則 None。
    """
    from fw_diag_tool.session.session_manager import SessionManager

    loaded_report: dict[str, Any] | None = None
    proto = (key_prefix or protocol).lower()

    with st.expander("💾 Session 管理", expanded=False):
        if include_uploader:
            session_upload = st.file_uploader(
                "載入可重現 Session（.fwsession.json）",
                type=["json"],
                max_upload_size=SessionManager.MAX_SESSION_BYTES // (1024 * 1024),
                key=f"{proto}_session_upload",
            )
            if session_upload is not None:
                try:
                    session_doc = SessionManager.deserialize_session(session_upload.getvalue())
                    loaded_report = session_doc.report
                    st.info(
                        f"已載入 Session：{session_doc.name or f'{protocol.upper()} Analysis'}｜"
                        f"工具版本：{session_doc.tool_version}"
                    )
                    with st.expander("檢視 Session 報告摘要", expanded=False):
                        st.json(loaded_report, expanded=False)
                except (TypeError, ValueError) as exc:
                    st.error(f"無法載入 Session：{_localize_gui_error(exc, domain='session')}")

        if report_data is not None:
            if include_uploader:
                st.divider()
            try:
                data_dict: dict[str, Any]
                if hasattr(report_data, "to_dict") and callable(report_data.to_dict):
                    data_dict = report_data.to_dict()
                elif dataclasses.is_dataclass(report_data) and not isinstance(report_data, type):
                    data_dict = dataclasses.asdict(report_data)
                elif isinstance(report_data, dict):
                    data_dict = report_data
                else:
                    data_dict = dict(report_data)

                data_dict.setdefault("protocol", protocol.upper())
                if "anomaly_count" not in data_dict:
                    summary_field = data_dict.get("summary")
                    if isinstance(summary_field, dict) and "anomaly_count" in summary_field:
                        data_dict["anomaly_count"] = summary_field["anomaly_count"]
                    elif "anomalies" in data_dict and isinstance(data_dict["anomalies"], list):
                        data_dict["anomaly_count"] = len(data_dict["anomalies"])
                    elif "events" in data_dict and isinstance(data_dict["events"], list):
                        data_dict["anomaly_count"] = len(data_dict["events"])
                    elif "devices" in data_dict and isinstance(data_dict["devices"], list):
                        data_dict["anomaly_count"] = sum(
                            len(d.get("findings", []))
                            for d in data_dict["devices"]
                            if isinstance(d, dict)
                        )
                    elif "errors" in data_dict and isinstance(data_dict["errors"], list):
                        data_dict["anomaly_count"] = len(data_dict["errors"])
                if "summary" not in data_dict:
                    data_dict["summary"] = data_dict.get(
                        "summary_title", f"{protocol.upper()} Analysis"
                    )

                payload = SessionManager.build_payload(
                    name=f"{protocol.upper()} Analysis",
                    data=data_dict,
                    config=config_data if config_data is not None else {},
                )
                session_json = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
                st.download_button(
                    "💾 儲存分析 Session",
                    data=session_json,
                    file_name=f"{proto}_analysis.fwsession.json",
                    mime="application/json",
                    key=f"{proto}_download_session",
                )
            except (TypeError, ValueError) as exc:
                st.error(f"無法建構 Session：{exc}")

    return loaded_report


def get_translator() -> TranslationRegistry:
    """取得全域 TranslationRegistry 單例，並與 session_state 語言同步（若可用）。"""
    registry = get_global_registry()
    with contextlib.suppress(Exception):
        if hasattr(st, "session_state") and "locale" in st.session_state:
            registry.set_locale(st.session_state["locale"])
    return registry


def render_language_selector() -> str:
    """在 sidebar 渲染語系選擇器，並同步至 session_state 與 TranslationRegistry。"""
    if "locale" not in st.session_state:
        st.session_state["locale"] = "zh-TW"

    options = ["zh-TW", "en-US"]
    labels = {"zh-TW": "🇹🇼 繁體中文 (zh-TW)", "en-US": "🇺🇸 English (en-US)"}

    current_locale = st.session_state.get("locale", "zh-TW")
    current_index = options.index(current_locale) if current_locale in options else 0

    selected_locale = st.sidebar.selectbox(
        "🌐 語言 / Language",
        options=options,
        index=current_index,
        format_func=lambda code: labels.get(code, code),
        key="gui_locale_selector",
    )

    if selected_locale != st.session_state["locale"]:
        st.session_state["locale"] = selected_locale

    translator = get_translator()
    translator.set_locale(selected_locale)
    return selected_locale


__all__ = [
    "DEFAULT_I2C_TIMEOUT_MS",
    "GUI_ANALYSIS_LIMITS",
    "MAX_PACKET_HEX_CHARS",
    "PAGE_INDEX",
    "_FAULT_ARENA_CASES_ZH",
    "_PCIE_INPUT_ERROR_ZH",
    "_REGISTER_DESCRIPTION_ZH",
    "_REGISTER_MEANING_ZH",
    "_localize_gui_error",
    "_localize_mctp_error",
    "_localize_pcie_input_error",
    "_localize_register_description",
    "_localize_register_meaning",
    "_reset_i2c_session_state",
    "analyze_i2c_input",
    "analyze_mctp_input",
    "analyze_pcie_input",
    "analyze_spi_input",
    "get_plotly_template",
    "get_translator",
    "render_breadcrumb",
    "render_global_search",
    "render_guide_expander",
    "render_html_download",
    "render_keyboard_shortcuts",
    "render_language_selector",
    "render_page_footer",
    "render_pdf_download",
    "render_session_controls",
]
