from __future__ import annotations

from fw_diag_tool.i18n import (
    TranslationRegistry,
    bridge_i2c_localization,
    create_default_registry,
    get_global_registry,
    set_global_registry,
    t,
)
from fw_diag_tool.i18n.domains.common import register_common_domain
from fw_diag_tool.i18n.domains.gui import register_gui_domain


def test_register_and_t_basic() -> None:
    registry = TranslationRegistry(default_locale="zh-TW")
    registry.register(
        domain="common",
        key="hello",
        translations={"zh-TW": "你好", "en-US": "Hello"},
    )
    assert registry.t("hello", domain="common") == "你好"
    assert registry.t("hello", locale="en-US", domain="common") == "Hello"
    assert registry.t("hello", locale="zh-TW", domain="common") == "你好"


def test_locale_switch() -> None:
    registry = TranslationRegistry(default_locale="zh-TW")
    registry.register(
        domain="common",
        key="status_ok",
        translations={"zh-TW": "正常", "en-US": "Normal"},
    )

    assert registry.get_locale() == "zh-TW"
    assert registry.t("status_ok") == "正常"

    registry.set_locale("en-US")
    assert registry.get_locale() == "en-US"
    assert registry.t("status_ok") == "Normal"

    # Explicit locale overrides current locale
    assert registry.t("status_ok", locale="zh-TW") == "正常"


def test_domain_partitioning() -> None:
    registry = TranslationRegistry()
    registry.register("gui", "btn_save", {"zh-TW": "儲存", "en-US": "Save"})
    registry.register("cli", "btn_save", {"zh-TW": "CLI 儲存", "en-US": "CLI Save"})

    assert registry.t("btn_save", domain="gui") == "儲存"
    assert registry.t("btn_save", domain="cli") == "CLI 儲存"
    # Default domain is "common", where btn_save does not exist -> fallback to key
    assert registry.t("btn_save") == "btn_save"


def test_format_variable_substitution() -> None:
    registry = TranslationRegistry()
    registry.register(
        "common",
        "welcome_user",
        {
            "zh-TW": "歡迎，{name}！您有 {count} 個待處理項目。",
            "en-US": "Welcome, {name}! You have {count} items.",
        },
    )

    res_zh = registry.t("welcome_user", name="Alice", count=3)
    assert res_zh == "歡迎，Alice！您有 3 個待處理項目。"

    res_en = registry.t("welcome_user", locale="en-US", name="Bob", count=5)
    assert res_en == "Welcome, Bob! You have 5 items."

    # Missing format keys should not raise unhandled exception, falls back gracefully
    res_err = registry.t("welcome_user", invalid_param=123)
    assert "{name}" in res_err


def test_fallback_behavior() -> None:
    registry = TranslationRegistry(default_locale="zh-TW")

    # 1. Non-existent key returns key itself
    assert registry.t("non_existent_key") == "non_existent_key"
    assert registry.t("non_existent_key", domain="random_domain") == "non_existent_key"

    # 2. Key exists only in zh-TW, requesting fr-FR falls back to default_locale (zh-TW)
    registry.register("common", "only_zh", {"zh-TW": "只有中文"})
    assert registry.t("only_zh", locale="fr-FR") == "只有中文"

    # 3. Key exists only in en-US (default is zh-TW), requesting ja-JP falls back to en-US
    registry.register("common", "only_en", {"en-US": "English Only"})
    assert registry.t("only_en", locale="ja-JP") == "English Only"


def test_export_catalog() -> None:
    registry = TranslationRegistry()
    registry.register("test_dom", "k1", {"zh-TW": "值1", "en-US": "val1"})

    catalog = registry.export_catalog()
    assert "test_dom" in catalog
    assert catalog["test_dom"]["k1"] == {"zh-TW": "值1", "en-US": "val1"}

    # Modifying exported catalog does not mutate internal catalog
    catalog["test_dom"]["k1"]["zh-TW"] = "已修改"
    assert registry.t("k1", domain="test_dom") == "值1"


def test_list_domains_and_keys() -> None:
    registry = TranslationRegistry()
    registry.register("b_domain", "key_b", {"zh-TW": "B"})
    registry.register("a_domain", "key_a2", {"zh-TW": "A2"})
    registry.register("a_domain", "key_a1", {"zh-TW": "A1"})

    assert registry.list_domains() == ["a_domain", "b_domain"]
    assert registry.list_keys("a_domain") == ["key_a1", "key_a2"]
    assert registry.list_keys("b_domain") == ["key_b"]
    assert registry.list_keys("unknown_domain") == []


def test_register_common_domain() -> None:
    registry = TranslationRegistry()
    register_common_domain(registry)

    assert "common" in registry.list_domains()
    assert registry.t("CRITICAL", domain="common") == "嚴重"
    assert registry.t("CRITICAL", locale="en-US", domain="common") == "CRITICAL"
    assert registry.t("measured", domain="common") == "實測（Measured）"
    assert registry.t("A (Excellent)", domain="common") == "A（優良：通訊完全正常）"


def test_register_gui_domain() -> None:
    registry = TranslationRegistry()
    register_gui_domain(registry)

    assert "gui" in registry.list_domains()
    assert registry.t("btn_analyze", domain="gui") == "開始分析"
    assert registry.t("btn_analyze", locale="en-US", domain="gui") == "Analyze"
    assert registry.t("title_app", domain="gui") == "韌體協定診斷工具箱"
    assert registry.t("error_file_empty", domain="gui") == "輸入檔案內容為空，無法進行分析。"


def test_bridge_i2c_localization() -> None:
    registry = TranslationRegistry()
    bridge_i2c_localization(registry)

    # Check subdomains and i2c domain
    assert "i2c.input_format" in registry.list_domains()
    assert "i2c" in registry.list_domains()

    assert registry.t("decoded_csv", domain="i2c.input_format") == "解碼分析器 CSV（decoded_csv）"
    assert registry.t("decoded_csv", domain="i2c") == "解碼分析器 CSV（decoded_csv）"
    assert registry.t("decoded_csv", locale="en-US", domain="i2c") == "decoded_csv"
    assert (
        registry.t("I2C_SOURCE_EMPTY", domain="i2c.data_quality")
        == "輸入檔案內容為空，無法進行分析。"
    )


def test_create_default_registry() -> None:
    registry = create_default_registry()
    assert "common" in registry.list_domains()
    assert "gui" in registry.list_domains()
    assert "i2c" in registry.list_domains()

    assert registry.t("OK") == "正常（OK）"
    assert registry.t("btn_analyze", domain="gui") == "開始分析"
    assert registry.t("decoded_csv", domain="i2c") == "解碼分析器 CSV（decoded_csv）"


def test_global_registry_helpers() -> None:
    original = get_global_registry()
    custom = TranslationRegistry(default_locale="en-US")
    custom.register("common", "test_key", {"en-US": "Test Value", "zh-TW": "測試值"})

    try:
        set_global_registry(custom)
        assert get_global_registry() is custom
        assert t("test_key") == "Test Value"
        assert t("test_key", locale="zh-TW") == "測試值"
    finally:
        set_global_registry(original)
