"""I2C / SMBus / PMBus zh-TW localization and display formatting helpers.

Provides consistent Traditional Chinese presentation across GUI, Terminal UI,
and Markdown diagnostic reports while preserving machine tokens, protocol codes,
hex values, and standard engineering keywords.
"""

from __future__ import annotations

import re

from fw_diag_tool.i2c.models import I2CDirection, I2CSpeedMode
from fw_diag_tool.i2c.status import TransactionStatus

TRANSACTION_STATUS_ZH: dict[str, str] = {
    TransactionStatus.ACK.value: "ACK（正常應答）",
    TransactionStatus.ADDR_NAK.value: "ADDR NAK（位址無應答）",
    TransactionStatus.DATA_NAK.value: "DATA NAK（資料無應答/被拒絕）",
    TransactionStatus.READ_END_NAK.value: "READ END NAK（主機讀取結束 NACK）",
    TransactionStatus.ACK_UNKNOWN.value: "ACK UNKNOWN（ACK 證據未知/未提供）",
    TransactionStatus.EVIDENCE_INCOMPLETE.value: "EVIDENCE INCOMPLETE（來源證據不完整）",
    TransactionStatus.NO_STOP.value: "NO STOP（缺少 STOP 條件/匯流排鎖定）",
    TransactionStatus.ABORTED.value: "ABORTED（傳輸異常中斷）",
}

SPEED_MODE_ZH: dict[str, str] = {
    I2CSpeedMode.STANDARD_100K.value: "Standard-mode（標準模式 100 kHz）",
    I2CSpeedMode.FAST_400K.value: "Fast-mode（快速模式 400 kHz）",
    I2CSpeedMode.FAST_PLUS_1M.value: "Fast-mode Plus（超快速模式 1 MHz）",
    I2CSpeedMode.HIGH_SPEED_3M4.value: "High-speed mode（高速模式 3.4 MHz）",
    I2CSpeedMode.UNKNOWN.value: "Custom / Unknown Speed（自訂 / 未知速率）",
}

DEVICE_CATEGORY_ZH: dict[str, str] = {
    "General I2C Peripheral": "一般 I2C 週邊裝置",
    "I2C Multiplexer (PCA9548A/PCA9546)": "I2C 多工器 (PCA9548A/PCA9546)",
    "EEPROM": "EEPROM 記憶體",
    "Temperature Sensor": "溫度感測器",
    "Power Monitor / INA2xx": "電壓電流與功率監控晶片 (INA2xx)",
    "PMBus Power Controller": "PMBus 數位電源控制器",
    "PMBus Power Supply": "PMBus 伺服器電源供應器 (PSU)",
    "GPIO Expander": "GPIO 擴充晶片",
    "Real-Time Clock (RTC)": "即時時鐘 (RTC)",
    "Display / OLED Controller": "顯示器 / OLED 控制器",
    "Special Address / System": "特殊保留位址 / 系統廣播",
}

DATA_QUALITY_ZH: dict[str, str] = {
    "I2C_SOURCE_EMPTY": "輸入檔案內容為空，無法進行分析。",
    "I2C_SOURCE_NO_TRANSACTIONS": "輸入檔案未包含任何可解析的 I2C/SMBus 交易事件。",
    "I2C_UNKNOWN_EVENT_TYPE": "發現未知的事件類型欄位，已自動忽略或降級處理。",
    "I2C_SOURCE_PARSE_ERROR": "來源檔案解析時發生格式錯誤，部分欄位可能遺失。",
    "I2C_ACK_AGGREGATE_UNATTRIBUTABLE": "匯入的 Decoded CSV 屬於 Aggregate 彙總格式（單一列含多個資料 Byte 但僅有一個整體 ACK 欄位），無法歸屬每位元組的 ACK/NACK，因此保留語意解碼。",
    "I2C_TIMING_AGGREGATE_UNATTRIBUTABLE": "匯入的彙總格式未提供每位元組的持續時間或傳輸速率，無法精確歸屬單一位元組時序。",
    "I2C_ADDRESS_UNAVAILABLE": "來源列缺少有效的 7-bit/8-bit 位址欄位，無法確認目標從裝置。",
    "I2C_DIRECTION_UNAVAILABLE": "來源列缺少 Read/Write 傳輸方向欄位，語意解碼已保留。",
    "I2C_DATA_UNAVAILABLE": "來源列標記為資料傳輸但未提供實際 Payload 內容。",
    "I2C_TIMESTAMP_UNAVAILABLE": "來源資料缺少時間戳記 (Timestamp)，時序與間隔時間相關量測不可用。",
    "I2C_TIMESTAMP_OUT_OF_ORDER": "來源時間戳記出現倒退現象，時序時間軸與持續時間可能不可靠。",
    "I2C_ACK_UNAVAILABLE": "來源缺少 ACK/NACK 狀態數據，無法判定通訊成功率。",
    "I2C_TIMING_UNAVAILABLE": "未提供每位元組持續時間或傳輸速率證據，SCL 時鐘頻率不可用。",
    "I2C_TIMING_PARTIAL": "僅部分協定事件包含時序或位元率證據，統計數據僅代表已知樣本。",
    "I2C_EEPROM_PROFILE_UNAVAILABLE": "目標位址存在多種可能裝置（如 EEPROM），在未指定明確 Board Profile 或位址寬度前，保留 Offset/分頁解碼。",
    "I2C_EEPROM_ADDRESS_TRUNCATED": "EEPROM 寫入需要 2-byte 位移位址，但捕捉資料僅有 1-byte，已保留位移與資料解碼。",
    "I2C_EEPROM_ADDRESS_OUT_OF_RANGE": "EEPROM 寫入位移或資料長度超過配置之記憶體容量上限，已保留解碼。",
    "I2C_PMBUS_PAYLOAD_TRUNCATED": "PMBus 指令回應位元組數小於標準規格長度，已保留狀態與遙測數據解碼。",
    "I2C_PMBUS_BLOCK_COUNT_MISMATCH": "PMBus Block Read 回傳的 Byte Count 與實際捕捉的 Payload 長度不符。",
    "I2C_PMBUS_BLOCK_COUNT_INVALID": "PMBus Block Read 長度超過 SMBus/PMBus 規範上限 (32 bytes)。",
    "I2C_PMBUS_PAYLOAD_OVERLONG": "PMBus 固定長度指令包含多餘的 Payload 位元組，已保留解碼。",
    "I2C_PMBUS_PHASE_MISMATCH": "PMBus Payload 出現於指令定義不允許之傳輸方向，已保留語意解碼。",
    "I2C_SENSOR_PAYLOAD_TRUNCATED": "感測器暫存器回應長度不足，無法組成完整物理讀值。",
    "I2C_SENSOR_PAYLOAD_OVERLONG": "感測器暫存器回應長度超過固定暫存器寬度，已保留解碼。",
    "I2C_ADDRESS_NACK_DATA_PRESENT": "從裝置在位址階段回覆 NACK 後仍捕捉到後續資料位元組，已保留語意解碼。",
    "I2C_ADDRESS_NACK_SEMANTIC_UNAVAILABLE": "位址階段已發生 NACK，從裝置未成功選取，已保留語意解碼。",
    "I2C_DATA_NACK_SEMANTIC_UNAVAILABLE": "資料階段已發生 NACK，暫存器寫入/讀取被拒絕，已保留語意解碼。",
    "I2C_SEMANTIC_EVIDENCE_INCOMPLETE": "協定事件不完整（如缺少必要暫存器位移或長度），已保留語意解碼。",
    "I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS": "同一個 7-bit 位址在 Board Profile 中對應多個可能晶片，未指定確切 Profile 前保留專屬解碼。",
    "I2C_RESERVED_ADDRESS_CANDIDATE": "位址屬於 I2C 規範保留位址 (0x00~0x07 或 0x78~0x7F)，僅供鑑識檢視，不視為一般從裝置。",
}

HEALTH_GRADE_ZH: dict[str, str] = {
    "A (Excellent)": "A（優良：通訊完全正常）",
    "B (Minor Jitter / Retries)": "B（良好：輕微時鐘抖動或少量重試）",
    "D (High NACK Rate)": "D（警告：高 NACK 失敗率）",
    "F (Critical Fault)": "F（嚴重：頻繁通訊失敗或嚴重逾時）",
    "N/A (ACK unavailable)": "N/A（ACK 證據不可用，不進行評等）",
}


def localize_status(status: str | TransactionStatus) -> str:
    """Return zh-TW readable status string with original token preserved."""
    val = status.value if isinstance(status, TransactionStatus) else str(status)
    return TRANSACTION_STATUS_ZH.get(val, val)


def localize_speed_mode(mode: str | I2CSpeedMode) -> str:
    """Return zh-TW readable speed mode description."""
    val = mode.value if isinstance(mode, I2CSpeedMode) else str(mode)
    return SPEED_MODE_ZH.get(val, val)


def localize_category(category: str | None) -> str:
    """Return zh-TW peripheral category."""
    if not category:
        return "一般 I2C 週邊裝置"
    return DEVICE_CATEGORY_ZH.get(category, category)


def localize_health_grade(grade: str) -> str:
    """Return zh-TW health grade with explanatory hint."""
    return HEALTH_GRADE_ZH.get(grade, grade)


def localize_quality_message(code: str, fallback_message: str = "") -> str:
    """Return zh-TW explanation for a data quality limitation code."""
    return DATA_QUALITY_ZH.get(code, fallback_message or code)


def localize_direction(direction: str | I2CDirection | None) -> str:
    """Return zh-TW read/write direction label."""
    if direction is None:
        return "UNKNOWN（未知）"
    val = direction.value if isinstance(direction, I2CDirection) else str(direction)
    if val.upper() == "WRITE":
        return "WRITE（寫入）"
    if val.upper() == "READ":
        return "READ（讀取）"
    return f"{val}（未知）"


def localize_semantic_summary(summary: str | None) -> str:
    """Convert engine semantic summary phrases into clean zh-TW."""
    if not summary or summary == "-":
        return "-"
    s = summary
    s = s.replace(
        "ACK attribution unavailable; semantic decoding withheld", "ACK 歸屬未知；保留語意解碼"
    )
    s = s.replace("Address unavailable; semantic decoding withheld", "位址不可用；保留語意解碼")
    s = s.replace(
        "Read/write direction unavailable; semantic decoding withheld",
        "讀寫方向不可用；保留語意解碼",
    )
    s = s.replace("Source field invalid; semantic decoding withheld", "來源欄位無效；保留語意解碼")
    s = s.replace(
        "Data byte unavailable; semantic decoding withheld", "資料位元組不可用；保留語意解碼"
    )
    s = s.replace(
        "Address NACK with subsequent data; semantic decoding withheld",
        "位址 NACK 但後續仍有資料；保留語意解碼",
    )
    s = s.replace("Address NACK; semantic decoding withheld", "位址 NACK；保留語意解碼")
    s = s.replace("Data NACK; semantic decoding withheld", "資料 NACK；保留語意解碼")
    s = s.replace(
        "Incomplete transaction payload; semantic decoding withheld", "不完整傳輸資料；保留語意解碼"
    )
    s = s.replace(
        "PMBus Quick Command / Address Probe", "PMBus 快速指令 / 位址探測 (Address Probe)"
    )
    s = s.replace(
        "EEPROM Write Polling / Address Probe", "EEPROM 寫入輪詢 (ACK Polling) / 位址探測"
    )
    s = s.replace("Temperature Sensor Address Probe", "溫度感測器位址探測 (Address Probe)")
    s = s.replace("INA2xx Address Probe", "INA2xx 功率感測器位址探測 (Address Probe)")
    s = s.replace("GPIO Expander Address Probe", "GPIO 擴充晶片位址探測 (Address Probe)")
    s = s.replace(
        "Bus Hang / Clock line held low indefinitely", "匯流排掛起 (Bus Hang) / SCL 被永久拉低"
    )
    s = re.sub(
        r"I2C MUX (0x[0-9A-Fa-f]+) Channel Switch -> \[([0-9, ]+)\] \(aggregate ACK; per-byte attribution unavailable\)",
        r"I2C 多工器 \1 通道切換 -> [\2] (Aggregate ACK；未提供單 Byte 歸屬)",
        s,
    )
    s = re.sub(
        r"I2C MUX (0x[0-9A-Fa-f]+) Channel Switch -> \[([0-9, ]+)\]",
        r"I2C 多工器 \1 通道切換 -> [\2]",
        s,
    )
    s = re.sub(
        r"Set Register Pointer to ([\w_]+) \((0x[0-9A-Fa-f]+)\)",
        r"設定暫存器指標為 \1 (\2)",
        s,
    )
    s = re.sub(
        r"Read Register (0x[0-9A-Fa-f]+):",
        r"讀取暫存器 \1：",
        s,
    )
    s = re.sub(
        r"^Write (\d+) byte\(s\):",
        r"寫入 \1 個位元組：",
        s,
    )
    s = re.sub(
        r"^Read (\d+) byte\(s\):",
        r"讀取 \1 個位元組：",
        s,
    )
    return s


def format_summary_text_zh(
    total_events: int,
    total_transactions: int,
    device_count: int,
    issue_count: int,
) -> str:
    """Generate zh-TW executive summary string for report headers."""
    return (
        f"共分析 {total_events} 筆實體事件，歸納為 {total_transactions} 筆邏輯交易，"
        f"涵蓋 {device_count} 個從裝置。共偵測出 {issue_count} 筆協定診斷異常。"
    )
