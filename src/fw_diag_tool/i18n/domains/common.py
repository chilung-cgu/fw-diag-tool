from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fw_diag_tool.i18n.registry import TranslationRegistry

COMMON_TRANSLATIONS: dict[str, dict[str, str]] = {
    # Severity
    "CRITICAL": {"zh-TW": "嚴重", "en-US": "CRITICAL"},
    "ERROR": {"zh-TW": "錯誤", "en-US": "ERROR"},
    "WARNING": {"zh-TW": "警告", "en-US": "WARNING"},
    "INFO": {"zh-TW": "資訊", "en-US": "INFO"},
    # General Status
    "OK": {"zh-TW": "正常（OK）", "en-US": "OK"},
    "Normal": {"zh-TW": "正常（Normal）", "en-US": "Normal"},
    "Ready": {"zh-TW": "就緒（Ready）", "en-US": "Ready"},
    "Busy": {"zh-TW": "忙碌（Busy）", "en-US": "Busy"},
    "PASS": {"zh-TW": "通過", "en-US": "PASS"},
    "FAIL": {"zh-TW": "失敗", "en-US": "FAIL"},
    "TIMEOUT": {"zh-TW": "逾時", "en-US": "TIMEOUT"},
    # Direction
    "READ": {"zh-TW": "讀取（READ）", "en-US": "READ"},
    "WRITE": {"zh-TW": "寫入（WRITE）", "en-US": "WRITE"},
    "Read": {"zh-TW": "讀取（Read）", "en-US": "Read"},
    "Write": {"zh-TW": "寫入（Write）", "en-US": "Write"},
    # ACK / NACK
    "ACK": {"zh-TW": "ACK（正常應答）", "en-US": "ACK"},
    "NACK": {"zh-TW": "NACK（未應答）", "en-US": "NACK"},
    "ACK (Normal)": {"zh-TW": "ACK（正常應答）", "en-US": "ACK (Normal)"},
    "Address NACK": {"zh-TW": "位址 NACK（未應答）", "en-US": "Address NACK"},
    "Data NACK": {"zh-TW": "資料 NACK（未應答）", "en-US": "Data NACK"},
    # Evidence Level
    "measured": {"zh-TW": "實測（Measured）", "en-US": "Measured"},
    "source_provided": {"zh-TW": "來源提供（Source-provided）", "en-US": "Source-provided"},
    "reconstructed": {"zh-TW": "協定重建（Reconstructed）", "en-US": "Reconstructed"},
    "inferred": {"zh-TW": "推論（Inferred）", "en-US": "Inferred"},
    "hypothesis": {"zh-TW": "假設（Hypothesis）", "en-US": "Hypothesis"},
    "unavailable": {"zh-TW": "不可用（Unavailable）", "en-US": "Unavailable"},
    "unknown": {"zh-TW": "未知（Unknown）", "en-US": "Unknown"},
    # Health Grade
    "A (Excellent)": {"zh-TW": "A（優良：通訊完全正常）", "en-US": "A (Excellent: Fully Operational)"},
    "B (Good)": {"zh-TW": "B（良好：偶發輕微異常）", "en-US": "B (Good: Minor Anomalies)"},
    "C (Fair)": {"zh-TW": "C（普通：存在多項警示）", "en-US": "C (Fair: Multiple Warnings)"},
    "D (Poor)": {"zh-TW": "D（不良：嚴重錯誤頻發）", "en-US": "D (Poor: Frequent Errors)"},
    "F (Critical)": {"zh-TW": "F（失效：通訊中斷或協定失敗）", "en-US": "F (Critical: Protocol Failure)"},
    # Register States
    "Unit On": {"zh-TW": "裝置開啟（Unit On）", "en-US": "Unit On"},
    "Unit Off": {"zh-TW": "裝置關閉（Unit Off）", "en-US": "Unit Off"},
    "Unit is Outputting Power": {
        "zh-TW": "裝置正在輸出電力（Unit is Outputting Power）",
        "en-US": "Unit is Outputting Power",
    },
    "Unit is Off": {"zh-TW": "裝置已關閉（Unit is Off）", "en-US": "Unit is Off"},
    "Vout Overvoltage Fault": {
        "zh-TW": "輸出過電壓故障（Vout Overvoltage Fault）",
        "en-US": "Vout Overvoltage Fault",
    },
    "Iout Overcurrent Fault": {
        "zh-TW": "輸出過電流故障（Iout Overcurrent Fault）",
        "en-US": "Iout Overcurrent Fault",
    },
    "Vin Undervoltage Fault": {
        "zh-TW": "輸入欠電壓故障（Vin Undervoltage Fault）",
        "en-US": "Vin Undervoltage Fault",
    },
    "Overtemperature Alarm": {
        "zh-TW": "過溫警報（Overtemperature Alarm）",
        "en-US": "Overtemperature Alarm",
    },
    "CML Error": {
        "zh-TW": "CML 通訊／記憶體／邏輯錯誤（CML Error）",
        "en-US": "CML Error",
    },
}


def register_common_domain(registry: TranslationRegistry) -> None:
    """將共用通用詞條註冊至 registry 的 'common' domain。"""
    registry.register_domain("common", COMMON_TRANSLATIONS)


__all__ = ["COMMON_TRANSLATIONS", "register_common_domain"]
