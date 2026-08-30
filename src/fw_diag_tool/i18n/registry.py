from __future__ import annotations

import copy
from typing import Any


class TranslationRegistry:
    """集中式翻譯登錄表，支援多語言與 domain 分區。"""

    def __init__(self, default_locale: str = "zh-TW") -> None:
        self._default_locale: str = default_locale
        self._current_locale: str = default_locale
        # _catalog[domain][key][locale] = translation string
        self._catalog: dict[str, dict[str, dict[str, str]]] = {}

    def register(self, domain: str, key: str, translations: dict[str, str]) -> None:
        """註冊一個翻譯詞條。"""
        if domain not in self._catalog:
            self._catalog[domain] = {}
        if key not in self._catalog[domain]:
            self._catalog[domain][key] = {}
        self._catalog[domain][key].update(translations)

    def register_domain(self, domain: str, entries: dict[str, dict[str, str]]) -> None:
        """批次註冊整個 domain 的翻譯詞條。"""
        for key, translations in entries.items():
            self.register(domain, key, translations)

    def t(
        self,
        key: str,
        *,
        locale: str | None = None,
        domain: str = "common",
        **kwargs: Any,
    ) -> str:
        """取得翻譯字串，支援 format 變數與 fallback 行為。"""
        target_locale = locale if locale is not None else self._current_locale
        domain_dict = self._catalog.get(domain, {})
        key_dict = domain_dict.get(key)

        template: str
        if key_dict is not None:
            if target_locale in key_dict:
                template = key_dict[target_locale]
            elif self._default_locale in key_dict:
                template = key_dict[self._default_locale]
            elif key_dict:
                # Fallback to any available locale translation
                template = next(iter(key_dict.values()))
            else:
                template = key
        else:
            template = key

        if kwargs:
            try:
                return template.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return template
        return template

    def get_locale(self) -> str:
        """取得當前 locale。"""
        return self._current_locale

    def set_locale(self, locale: str) -> None:
        """設定當前 locale。"""
        self._current_locale = locale

    def list_domains(self) -> list[str]:
        """列出已註冊的 domain。"""
        return sorted(self._catalog.keys())

    def list_keys(self, domain: str) -> list[str]:
        """列出某 domain 下所有 key。"""
        return sorted(self._catalog.get(domain, {}).keys())

    def export_catalog(self) -> dict[str, dict[str, dict[str, str]]]:
        """匯出完整翻譯目錄（供文件或 QA 使用）。"""
        return copy.deepcopy(self._catalog)


_GLOBAL_REGISTRY: TranslationRegistry | None = None


def get_global_registry() -> TranslationRegistry:
    """取得全域 TranslationRegistry 單例實例。"""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = create_default_registry()
    return _GLOBAL_REGISTRY


def set_global_registry(registry: TranslationRegistry) -> None:
    """設定全域 TranslationRegistry 單例實例。"""
    global _GLOBAL_REGISTRY
    _GLOBAL_REGISTRY = registry


def t(
    key: str,
    *,
    locale: str | None = None,
    domain: str = "common",
    **kwargs: Any,
) -> str:
    """使用全域登錄表取得翻譯字串。"""
    return get_global_registry().t(key, locale=locale, domain=domain, **kwargs)


def create_default_registry() -> TranslationRegistry:
    """建立並初始化包含所有預設 domain 與相容橋接的 TranslationRegistry。"""
    from fw_diag_tool.i18n.compat import bridge_i2c_localization
    from fw_diag_tool.i18n.domains import register_all_domains

    registry = TranslationRegistry(default_locale="zh-TW")
    register_all_domains(registry)
    bridge_i2c_localization(registry)
    return registry


__all__ = [
    "TranslationRegistry",
    "create_default_registry",
    "get_global_registry",
    "set_global_registry",
    "t",
]
