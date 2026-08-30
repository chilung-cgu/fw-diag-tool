from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fw_diag_tool.i18n.registry import TranslationRegistry


def bridge_i2c_localization(registry: TranslationRegistry) -> None:
    """將既有 I2C localization 詞條批次註冊到 registry。

    提供向後相容橋接，讓既有 i2c/localization.py 定義之對照表自動進入集中式登錄表。
    """
    from fw_diag_tool.i2c.localization import (
        DATA_QUALITY_ZH,
        DEVICE_CATEGORY_ZH,
        EVIDENCE_ZH,
        HEALTH_GRADE_ZH,
        INPUT_FORMAT_ZH,
        PLATFORM_ZH,
        PRESET_ZH,
        SEVERITY_ZH,
        SPEED_MODE_ZH,
        TRANSACTION_STATUS_ZH,
    )

    sources: dict[str, dict[str, str]] = {
        "i2c.input_format": INPUT_FORMAT_ZH,
        "i2c.evidence": EVIDENCE_ZH,
        "i2c.severity": SEVERITY_ZH,
        "i2c.platform": PLATFORM_ZH,
        "i2c.preset": PRESET_ZH,
        "i2c.status": TRANSACTION_STATUS_ZH,
        "i2c.speed_mode": SPEED_MODE_ZH,
        "i2c.device_category": DEVICE_CATEGORY_ZH,
        "i2c.data_quality": DATA_QUALITY_ZH,
        "i2c.health_grade": HEALTH_GRADE_ZH,
    }

    for domain_name, table in sources.items():
        for key, zh_text in table.items():
            translations = {"zh-TW": zh_text, "en-US": key}
            # 註冊於特定子 domain (如 i2c.input_format)
            registry.register(domain_name, key, translations)
            # 同時註冊於通用 i2c domain
            registry.register("i2c", key, translations)


__all__ = ["bridge_i2c_localization"]
