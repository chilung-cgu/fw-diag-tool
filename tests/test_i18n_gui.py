from __future__ import annotations

import pytest
import streamlit as st

from fw_diag_tool.gui.shared import get_translator, render_language_selector
from fw_diag_tool.i18n import (
    TranslationRegistry,
    create_default_registry,
    get_global_registry,
)
from fw_diag_tool.i18n.domains.gui import GUI_TRANSLATIONS, register_gui_domain


def test_translation_registry_locale_support() -> None:
    """測試 TranslationRegistry 能正確支援並回傳 zh-TW 與 en-US。"""
    registry = TranslationRegistry(default_locale="zh-TW")
    register_gui_domain(registry)

    # 預設 zh-TW
    assert registry.get_locale() == "zh-TW"
    assert registry.t("btn_analyze", domain="gui") == "開始分析"
    assert registry.t("btn_analyze", locale="en-US", domain="gui") == "Analyze"

    # 切換至 en-US
    registry.set_locale("en-US")
    assert registry.get_locale() == "en-US"
    assert registry.t("btn_analyze", domain="gui") == "Analyze"
    assert registry.t("btn_analyze", locale="zh-TW", domain="gui") == "開始分析"


def test_get_translator_singleton() -> None:
    """測試 get_translator() 回傳同一個全域單例。"""
    translator1 = get_translator()
    translator2 = get_translator()
    global_reg = get_global_registry()

    assert translator1 is translator2
    assert translator1 is global_reg
    assert isinstance(translator1, TranslationRegistry)


def test_gui_domain_translations_completeness() -> None:
    """測試 gui domain 至少有 30 個詞條，且所有 key 在 zh-TW 和 en-US 都有對應翻譯。"""
    registry = create_default_registry()

    # 驗證詞條總數至少 30 個
    assert len(GUI_TRANSLATIONS) >= 30, (
        f"Expected >= 30 GUI translations, got {len(GUI_TRANSLATIONS)}"
    )

    # 驗證所有 key 在兩個語系都有完整非空翻譯
    for key, trans_map in GUI_TRANSLATIONS.items():
        assert "zh-TW" in trans_map, f"Key '{key}' missing zh-TW translation"
        assert "en-US" in trans_map, f"Key '{key}' missing en-US translation"
        assert trans_map["zh-TW"].strip(), f"Key '{key}' has empty zh-TW translation"
        assert trans_map["en-US"].strip(), f"Key '{key}' has empty en-US translation"

        # 透過 registry 查詢驗證
        res_zh = registry.t(key, locale="zh-TW", domain="gui")
        res_en = registry.t(key, locale="en-US", domain="gui")
        assert res_zh == trans_map["zh-TW"]
        assert res_en == trans_map["en-US"]


def test_required_gui_strings_present() -> None:
    """測試需求指定的常用 GUI 字串（頁面標題、共用按鈕、共用提示、共用標籤）皆已註冊。"""
    registry = create_default_registry()

    # 頁面標題
    assert (
        registry.t("title_i2c_diagnosis", locale="zh-TW", domain="gui")
        == "I2C / PMBus 診斷與波形檢視"
    )
    assert (
        registry.t("title_i2c_diagnosis", locale="en-US", domain="gui")
        == "I2C / PMBus Waveform Diagnosis"
    )

    # 共用按鈕
    assert registry.t("btn_load_example", locale="zh-TW", domain="gui") == "📋 載入範例"
    assert registry.t("btn_load_example", locale="en-US", domain="gui") == "📋 Load Example"
    assert registry.t("btn_download_report", locale="zh-TW", domain="gui") == "⬇️ 下載報告"
    assert registry.t("btn_download_report", locale="en-US", domain="gui") == "⬇️ Download Report"
    assert registry.t("btn_save_session", locale="zh-TW", domain="gui") == "💾 儲存分析 Session"
    assert (
        registry.t("btn_save_session", locale="en-US", domain="gui") == "💾 Save Analysis Session"
    )

    # 共用提示
    assert registry.t("please_upload_file", locale="zh-TW", domain="gui") == "請上傳檔案"
    assert registry.t("please_upload_file", locale="en-US", domain="gui") == "Please upload a file"
    assert registry.t("upload_label", locale="zh-TW", domain="gui") == "請上傳檔案或貼上內容"
    assert (
        registry.t("upload_label", locale="en-US", domain="gui") == "Upload file or paste content"
    )

    # 共用欄位標籤
    assert registry.t("analysis_results", locale="zh-TW", domain="gui") == "分析結果"
    assert registry.t("analysis_results", locale="en-US", domain="gui") == "Analysis Results"
    assert registry.t("system_dashboard", locale="zh-TW", domain="gui") == "📊 系統狀態儀表板"
    assert (
        registry.t("system_dashboard", locale="en-US", domain="gui") == "📊 System Status Dashboard"
    )


def test_render_language_selector_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試 render_language_selector() 的 session_state 與 registry 同步行為。"""
    # 模擬 clean session state
    st.session_state.clear()

    # 執行 render_language_selector，預設應為 zh-TW
    selected = render_language_selector()
    assert selected == "zh-TW"
    assert st.session_state["locale"] == "zh-TW"
    assert get_translator().get_locale() == "zh-TW"

    # 模擬使用者在 session state 切換至 en-US
    st.session_state["locale"] = "en-US"
    selected_en = render_language_selector()
    assert selected_en == "en-US"
    assert get_translator().get_locale() == "en-US"
