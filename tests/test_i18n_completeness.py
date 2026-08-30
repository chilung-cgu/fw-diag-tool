"""i18n 完整性與缺失鍵值自動化稽核測試。

使用 Python AST 靜態分析掃描原始碼中的所有 t() 與 _tr() 呼叫，
確保所有被引用的翻譯 key 皆已在對應 domain 註冊，且具備完整的 zh-TW 與 en-US 翻譯。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from fw_diag_tool.i18n import TranslationRegistry, create_default_registry
from fw_diag_tool.i18n.domains.common import COMMON_TRANSLATIONS
from fw_diag_tool.i18n.domains.gui import GUI_TRANSLATIONS


class TCallVisitor(ast.NodeVisitor):
    """AST 訪客，專門抽取 t() 與 _tr() 呼叫中的 key 與 domain。"""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.extracted_keys: list[dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("t", "_tr") and node.args:
            first_arg = node.args[0]
            domain = "gui" if func_name == "_tr" else "common"
            for kw in node.keywords:
                if (
                    kw.arg == "domain"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    domain = kw.value.value

            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                self.extracted_keys.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "key": first_arg.value,
                        "domain": domain,
                    }
                )
            elif isinstance(first_arg, ast.JoinedStr):
                # 處理 f-string 如 f"protocol_diff_{role}"
                raw_repr = ast.unparse(first_arg)
                if "protocol_diff_" in raw_repr and "role" in raw_repr:
                    for r in ("baseline", "candidate"):
                        self.extracted_keys.append(
                            {
                                "file": self.filename,
                                "line": node.lineno,
                                "key": f"protocol_diff_{r}",
                                "domain": domain,
                            }
                        )

        self.generic_visit(node)


def _collect_all_gui_t_calls() -> list[dict[str, Any]]:
    """收集 src/fw_diag_tool/gui 下所有 Python 檔案中的 t() 與 _tr() 呼叫。"""
    repo_root = Path(__file__).resolve().parent.parent
    gui_dir = repo_root / "src" / "fw_diag_tool" / "gui"
    py_files = sorted(gui_dir.rglob("*.py"))

    all_calls: list[dict[str, Any]] = []
    for fpath in py_files:
        with open(fpath, "r", encoding="utf-8") as fp:
            tree = ast.parse(fp.read(), filename=str(fpath))
            visitor = TCallVisitor(str(fpath.relative_to(repo_root)))
            visitor.visit(tree)
            all_calls.extend(visitor.extracted_keys)
    return all_calls


@pytest.fixture(scope="module")
def default_registry() -> TranslationRegistry:
    """初始化並提供全域預設註冊表。"""
    return create_default_registry()


def test_all_gui_t_calls_have_registered_translations(
    default_registry: TranslationRegistry,
) -> None:
    """自動掃描所有 GUI 頁面與模組中的 t() 呼叫，驗證翻譯 key 皆已註冊且有 zh-TW/en-US。"""
    calls = _collect_all_gui_t_calls()
    assert len(calls) > 0, "No t() calls detected in GUI files; scanner might be malfunctioning"

    missing_keys: list[str] = []
    for call in calls:
        domain = call["domain"]
        key = call["key"]
        file_line = f"{call['file']}:{call['line']}"

        # 1. 驗證該 domain 與 key 是否已註冊
        domain_keys = default_registry.list_keys(domain)
        if key not in domain_keys:
            missing_keys.append(f"[{file_line}] Domain '{domain}' missing key: '{key}'")
            continue

        # 2. 驗證 zh-TW 與 en-US 翻譯是否齊全且非空
        zh_res = default_registry.t(key, locale="zh-TW", domain=domain)
        en_res = default_registry.t(key, locale="en-US", domain=domain)

        if not zh_res or zh_res == key:
            missing_keys.append(
                f"[{file_line}] Key '{key}' has empty or untranslated zh-TW in domain '{domain}'"
            )
        if not en_res or en_res == key:
            missing_keys.append(
                f"[{file_line}] Key '{key}' has empty or untranslated en-US in domain '{domain}'"
            )

    assert not missing_keys, (
        f"Found {len(missing_keys)} missing or incomplete i18n keys:\n" + "\n".join(missing_keys)
    )


def test_gui_translations_completeness_and_parity() -> None:
    """驗證 GUI_TRANSLATIONS 中所有 key 在 zh-TW 和 en-US 都有完整定義。"""
    assert len(GUI_TRANSLATIONS) >= 60, (
        f"Expected >= 60 GUI translations, got {len(GUI_TRANSLATIONS)}"
    )

    for key, trans_map in GUI_TRANSLATIONS.items():
        assert "zh-TW" in trans_map, f"GUI key '{key}' missing zh-TW"
        assert "en-US" in trans_map, f"GUI key '{key}' missing en-US"
        assert trans_map["zh-TW"].strip(), f"GUI key '{key}' has empty zh-TW"
        assert trans_map["en-US"].strip(), f"GUI key '{key}' has empty en-US"


def test_common_translations_completeness_and_parity() -> None:
    """驗證 COMMON_TRANSLATIONS 中所有 key 在 zh-TW 和 en-US 都有完整定義。"""
    assert len(COMMON_TRANSLATIONS) >= 20, (
        f"Expected >= 20 COMMON translations, got {len(COMMON_TRANSLATIONS)}"
    )

    for key, trans_map in COMMON_TRANSLATIONS.items():
        assert "zh-TW" in trans_map, f"COMMON key '{key}' missing zh-TW"
        assert "en-US" in trans_map, f"COMMON key '{key}' missing en-US"
        assert trans_map["zh-TW"].strip(), f"COMMON key '{key}' has empty zh-TW"
        assert trans_map["en-US"].strip(), f"COMMON key '{key}' has empty en-US"


def test_batch_ui_translations(default_registry: TranslationRegistry) -> None:
    """針對 batch_ui 所需的新增翻譯 key 進行專項覆蓋檢查。"""
    batch_keys = [
        "title_batch_analysis",
        "batch_analysis_caption",
        "batch_protocol_select_label",
        "batch_proto_auto",
        "batch_uploader_label",
        "batch_btn_start",
        "batch_empty_warning",
        "batch_no_files_analyzed",
        "batch_metric_total",
        "batch_metric_success",
        "batch_metric_warning",
        "batch_metric_error",
        "batch_download_zip_btn",
    ]
    for key in batch_keys:
        zh_val = default_registry.t(key, locale="zh-TW", domain="gui")
        en_val = default_registry.t(key, locale="en-US", domain="gui")
        assert zh_val != key, f"Batch key '{key}' missing zh-TW translation"
        assert en_val != key, f"Batch key '{key}' missing en-US translation"


def test_settings_ui_translations(default_registry: TranslationRegistry) -> None:
    """針對 settings_ui 所需的新增翻譯 key 進行專項覆蓋檢查。"""
    settings_keys = [
        "title_settings",
        "settings_caption",
        "settings_i2c_timeout",
        "settings_i2c_timeout_help",
        "language_selector_label",
        "settings_language_help",
        "settings_theme",
        "settings_theme_help",
        "settings_max_rows",
        "settings_max_rows_help",
        "settings_spi_page_size",
        "settings_spi_page_size_help",
        "btn_apply",
        "btn_reset",
        "settings_reset_button",
        "settings_applied_toast",
        "settings_reset_toast",
        "settings_active_summary",
        "settings_metric_i2c_timeout",
        "settings_metric_locale",
        "settings_metric_theme",
        "settings_metric_max_rows",
        "settings_metric_spi_page",
    ]
    for key in settings_keys:
        zh_val = default_registry.t(key, locale="zh-TW", domain="gui")
        en_val = default_registry.t(key, locale="en-US", domain="gui")
        assert zh_val != key, f"Settings key '{key}' missing zh-TW translation"
        assert en_val != key, f"Settings key '{key}' missing en-US translation"


def test_protocol_diff_ui_translations_including_pcie_mctp(
    default_registry: TranslationRegistry,
) -> None:
    """針對 protocol_diff_ui（包含 PCIe/MCTP 擴展與各協定 metrics/sections）進行專項覆蓋檢查。"""
    diff_keys = [
        "title_protocol_diff",
        "protocol_diff_select_protocol",
        "protocol_diff_baseline",
        "protocol_diff_candidate",
        "protocol_diff_download_report",
        "protocol_diff_download_json_report",
        "diff_metric_new_aer",
        "diff_metric_resolved_aer",
        "diff_metric_common_aer",
        "diff_metric_link_degradation",
        "diff_metric_new_errors",
        "diff_metric_resolved_errors",
        "diff_metric_common_errors",
        "diff_metric_message_count_delta",
        "diff_metric_new_anomalies",
        "diff_metric_resolved_anomalies",
        "diff_metric_common_anomalies",
        "diff_metric_tx_count_delta",
        "diff_metric_new_symbols",
        "diff_metric_resolved_symbols",
        "diff_metric_common_symbols",
        "diff_metric_fault_address",
        "diff_status_changed",
        "diff_status_identical",
        "diff_section_new",
        "diff_section_resolved",
        "diff_section_common",
        "diff_section_address_changes",
        "diff_section_none",
        "diff_uploader_file_label",
        "diff_pasted_text_label",
        "diff_summary_label",
    ]
    for key in diff_keys:
        zh_val = default_registry.t(key, locale="zh-TW", domain="gui")
        en_val = default_registry.t(key, locale="en-US", domain="gui")
        assert zh_val != key, f"Protocol diff key '{key}' missing zh-TW translation"
        assert en_val != key, f"Protocol diff key '{key}' missing en-US translation"
