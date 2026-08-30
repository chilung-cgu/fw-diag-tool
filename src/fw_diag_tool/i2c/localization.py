"""I2C / SMBus / PMBus zh-TW localization and display formatting helpers.

Provides consistent Traditional Chinese presentation across GUI, Terminal UI,
and Markdown diagnostic reports while preserving machine tokens, protocol codes,
hex values, and standard engineering keywords.
"""

from __future__ import annotations

import re

from fw_diag_tool.i2c.models import I2CDirection, I2CSpeedMode
from fw_diag_tool.i2c.status import TransactionStatus

INPUT_FORMAT_ZH: dict[str, str] = {
    "decoded_csv": "解碼分析器 CSV（decoded_csv）",
    "raw_digital": "原始數位 CSV（raw_digital；Time、SCL、SDA）",
    "text_trace": "文字追蹤記錄（text_trace；S/Sr/P、0xNN）",
    "Saleae Analyzer table / text trace": "Saleae 解碼表／文字追蹤記錄",
}

EVIDENCE_ZH: dict[str, str] = {
    "measured": "實測（Measured）",
    "source_provided": "來源提供（Source-provided）",
    "reconstructed": "協定重建（Reconstructed）",
    "inferred": "推論（Inferred）",
    "hypothesis": "假設（Hypothesis）",
    "unavailable": "不可用（Unavailable）",
    "unknown": "未知（Unknown）",
}

SEVERITY_ZH: dict[str, str] = {
    "CRITICAL": "嚴重",
    "ERROR": "錯誤",
    "WARNING": "警告",
    "INFO": "資訊",
}

PLATFORM_ZH: dict[str, str] = {
    "Linux Userspace (i2c-dev)": "Linux 使用者空間（i2c-dev）",
    "OpenBMC / Linux CLI (i2c-tools)": "OpenBMC／Linux 命令列（i2c-tools）",
    "STM32 HAL C Driver": "STM32 HAL C 驅動程式",
    "Arduino / Wire.h": "Arduino／Wire.h 程式碼",
}

PRESET_ZH: dict[str, str] = {
    "EEPROM：8-bit register write": "EEPROM：8-bit 暫存器寫入（register write）",
    "Temperature sensor：combined register read": "溫度感測器：複合暫存器讀取（combined register read）",
    "Sensor：direct read": "感測器：直接讀取（direct read）",
    "Device：direct write": "裝置：直接寫入（direct write）",
    "EEPROM：16-bit little-endian register write": "EEPROM：16-bit 小端序暫存器寫入（little-endian register write）",
}

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
    I2CSpeedMode.STANDARD_100K.value: "標準模式（Standard-mode，100 kHz）",
    I2CSpeedMode.FAST_400K.value: "快速模式（Fast-mode，400 kHz）",
    I2CSpeedMode.FAST_PLUS_1M.value: "超快速模式（Fast-mode Plus，1 MHz）",
    I2CSpeedMode.HIGH_SPEED_3M4.value: "高速模式（High-speed mode，3.4 MHz）",
    I2CSpeedMode.UNKNOWN.value: "自訂／未知速率（Custom / Unknown Speed）",
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
    "Direction unavailable": "方向不可用",
}

DATA_QUALITY_ZH: dict[str, str] = {
    "I2C_SOURCE_EMPTY": "輸入檔案內容為空，無法進行分析。",
    "I2C_SOURCE_NO_TRANSACTIONS": "輸入檔案未包含任何可解析的 I2C/SMBus 交易事件。",
    "I2C_UNKNOWN_EVENT_TYPE": "發現未知的事件類型欄位，已自動忽略或降級處理。",
    "I2C_SOURCE_PARSE_ERROR": "來源檔案解析時發生格式錯誤，部分欄位可能遺失。",
    "I2C_ACK_AGGREGATE_UNATTRIBUTABLE": "匯入的解碼 CSV 屬於彙總格式（Aggregate；單一列含多個資料位元組但僅有一個整體 ACK 欄位），無法歸屬每位元組的 ACK/NACK，因此保留語意解碼。",
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
    "I2C_EEPROM_ADDRESS_TRUNCATED": "EEPROM 寫入需要 2 個位元組的位移位址，但捕捉資料僅有 1 個位元組，已保留位移與資料解碼。",
    "I2C_EEPROM_ADDRESS_OUT_OF_RANGE": "EEPROM 寫入位移或資料長度超過配置之記憶體容量上限，已保留解碼。",
    "I2C_PMBUS_PAYLOAD_TRUNCATED": "PMBus 指令回應位元組數小於標準規格長度，已保留狀態與遙測數據解碼。",
    "I2C_PMBUS_BLOCK_COUNT_MISMATCH": "PMBus Block Read 回傳的 Byte Count 與實際捕捉的 Payload 長度不符。",
    "I2C_PMBUS_BLOCK_COUNT_INVALID": "PMBus Block Read 長度超過 SMBus/PMBus 規範上限（32 個位元組）。",
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


def localize_input_format(value: object) -> str:
    """Return the user-facing name for an I2C input format."""
    raw = getattr(value, "value", value)
    text = str(raw)
    return INPUT_FORMAT_ZH.get(text, text)


def localize_evidence(value: object) -> str:
    """Return a Chinese-first evidence label while retaining the source token."""
    raw = getattr(value, "value", value)
    text = str(raw)
    return EVIDENCE_ZH.get(text, text)


def localize_severity(value: object) -> str:
    """Return a Chinese severity label while retaining unknown values."""
    raw = getattr(value, "value", value)
    text = str(raw)
    return f"{SEVERITY_ZH[text]}（{text}）" if text in SEVERITY_ZH else text


def localize_platform(value: str) -> str:
    """Return a Chinese-first code-generation platform label."""
    return PLATFORM_ZH.get(value, value)


def localize_preset(value: str) -> str:
    """Return a Chinese-first label for a builder teaching preset."""
    return PRESET_ZH.get(value, value)


def localize_ack(value: object) -> str:
    """Return a readable ACK/NACK label for table and report display."""
    raw = getattr(value, "value", value)
    text = "" if raw is None else str(raw).upper()
    if text == "ACK":
        return "ACK（正常應答）"
    if text in {"NACK", "NAK"}:
        return "NACK（非應答）"
    return "未知（未提供 ACK/NACK）"


def localize_category(category: str | None) -> str:
    """Return zh-TW peripheral category."""
    if not category:
        return "一般 I2C 週邊裝置"
    text = str(category)
    suffix = "（候選不唯一）"
    if text.endswith(" (ambiguous candidates)"):
        text = text[: -len(" (ambiguous candidates)")]
        return f"{DEVICE_CATEGORY_ZH.get(text, text)}{suffix}"
    return DEVICE_CATEGORY_ZH.get(text, text)


def localize_device_name(name: str | None) -> str:
    """Translate descriptive device identity text while preserving model names."""
    if not name:
        return "未知裝置"
    text = str(name)
    replacements = (
        ("Possible devices (", "可能裝置（"),
        ("Possible Device (", "可能裝置（"),
        (" candidates)", " 個候選）"),
        ("Possible: ", "可能裝置："),
        ("Unknown Device", "未知裝置"),
        ("Ambiguous Board Profile", "板級設定檔不唯一"),
        ("Board Profile", "板級設定檔"),
        ("High-Accuracy Temp Sensor", "高精度溫度感測器"),
        ("Temperature Sensor", "溫度感測器"),
        ("Power Controller", "電源控制器"),
        ("PMBus PSU", "PMBus 電源供應器"),
        ("Display EEPROM", "顯示器 EEPROM"),
        ("GPIO Expander", "GPIO 擴充晶片"),
        ("Quasi-bidirectional", "準雙向"),
        ("Direction unavailable", "方向不可用"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def localize_issue_category(category: str | None) -> str:
    """Translate the slash-separated diagnostic category for display."""
    if not category:
        return "未分類"
    replacements = {
        "Protocol": "協定",
        "Addressing": "位址",
        "SlaveRejection": "從裝置拒絕",
        "BusState": "匯流排狀態",
        "Semantic": "語意",
        "Timing": "時序",
        "Physical": "實體層",
        "Performance": "效能",
        "Topology": "拓撲",
        "MUX": "多工器",
        "Hardware": "硬體",
        "Data": "資料",
    }
    return "／".join(replacements.get(part, part) for part in str(category).split("/"))


def localize_explanatory_text(text: str | None) -> str:
    """Translate known analyzer prose without changing protocol identifiers."""
    if not text:
        return text or ""
    value = str(text)
    # Translate complete sentences first.  Deliberately avoid unbounded
    # replacements such as ``expected`` -> ``預期``: they corrupt identifiers
    # like ``unexpected`` and leave grammatically broken English fragments.
    exact_replacements = {
        "ACK attribution unavailable; semantic decoding withheld": "ACK 歸屬未知；保留語意解碼",
        "Address unavailable; semantic decoding withheld": "位址不可用；保留語意解碼",
        "Read/write direction unavailable; semantic decoding withheld": "讀寫方向不可用；保留語意解碼",
        "Source field invalid; semantic decoding withheld": "來源欄位無效；保留語意解碼",
        "Data byte unavailable; semantic decoding withheld": "資料位元組不可用；保留語意解碼",
        "Address NACK with subsequent data; semantic decoding withheld": "位址 NACK 但後續仍有資料；保留語意解碼",
        "Address NACK; semantic decoding withheld": "位址 NACK；保留語意解碼",
        "Address NACK; target did not acknowledge the address; semantic decoding withheld": "位址 NACK；目標從裝置未回應位址；保留語意解碼",
        "Data NACK; semantic decoding withheld": "資料 NACK；保留語意解碼",
        "Unexpected data NACK; payload was not fully accepted; semantic decoding withheld": "資料 NACK；Payload 未完整接受；保留語意解碼",
        "Incomplete transaction payload; semantic decoding withheld": "傳輸 Payload 不完整；保留語意解碼",
        "Board profile maps this address to multiple buses/devices; bus context is unavailable, so semantic decoding was withheld": "Board Profile 將此位址對應到多個匯流排／裝置；缺少匯流排上下文，因此保留語意解碼",
        "PMBus Quick Command / Address Probe": "PMBus 快速指令／位址探測",
        "EEPROM Write Polling / Address Probe": "EEPROM 寫入輪詢／位址探測",
        "Temperature Sensor Address Probe": "溫度感測器位址探測",
        "INA2xx Address Probe": "INA2xx 功率感測器位址探測",
        "GPIO Expander Address Probe": "GPIO 擴充晶片位址探測",
        "Bus Hang / Clock line held low indefinitely": "匯流排掛起／時鐘線永久維持低電位",
        "All Clean": "無狀態旗標",
        "No Data / Quick Cmd": "無資料／快速指令",
        "Comm Normal": "通訊正常",
        "Temperature data unavailable": "溫度資料不可用",
        "EEPROM write not decoded: address width/page size unavailable; select an explicit EEPROM profile": "EEPROM 寫入未解碼：位址寬度／分頁大小不可用；請選擇明確的 EEPROM Profile",
        "EEPROM write has 1 address byte; 2-byte offset is unavailable": "EEPROM 寫入只有 1 個位址位元組；2 位元組位移不可用",
        "Empty Read": "空的讀取",
        "Write Polling probe (0 payload bytes)": "寫入輪詢探測（Payload 為 0 位元組）",
        "No source-provided bitrate or byte-duration evidence": "沒有來源提供的位元率或位元組持續時間證據",
        "No frequency samples": "沒有頻率樣本",
        "timestamps unavailable": "時間戳記不可用",
        "partial timestamps": "部分時間戳記",
        "No transactions to display": "沒有可顯示的交易",
    }
    for source, target in exact_replacements.items():
        value = value.replace(source, target)

    # PMBus status flags are machine tokens followed by explanatory English
    # prose.  Keep each flag token intact, but make the explanation readable
    # in the GUI tables and Markdown report.
    status_flag_replacements = (
        ("BUSY (Device busy / unable to respond)", "BUSY（裝置忙碌／無法回應）"),
        ("OFF (Unit is NOT providing power to output)", "OFF（裝置目前未向輸出供電）"),
        ("VOUT_OV (Output Over-Voltage Fault)", "VOUT_OV（輸出過電壓故障）"),
        ("IOUT_OC (Output Over-Current Fault)", "IOUT_OC（輸出過電流故障）"),
        ("VIN_UV (Input Under-Voltage Fault)", "VIN_UV（輸入欠電壓故障）"),
        ("TEMPERATURE (Thermal Fault or Warning)", "TEMPERATURE（熱故障或警告）"),
        ("CML (Comm/Memory/Logic Error)", "CML（通訊／記憶體／邏輯錯誤）"),
        ("OTHER_FAULT (Unspecified secondary fault)", "OTHER_FAULT（未指定的次要故障）"),
        (
            "VOUT_FAULT_WARN (Output Voltage Fault or Warning)",
            "VOUT_FAULT_WARN（輸出電壓故障或警告）",
        ),
        (
            "IOUT_POUT_FAULT_WARN (Output Current or Power Fault/Warning)",
            "IOUT_POUT_FAULT_WARN（輸出電流或功率故障／警告）",
        ),
        (
            "INPUT_FAULT_WARN (Input Voltage/Current/Power Fault/Warning)",
            "INPUT_FAULT_WARN（輸入電壓／電流／功率故障或警告）",
        ),
        (
            "MFR_SPECIFIC (Manufacturer Specific Fault/Warning)",
            "MFR_SPECIFIC（製造商專屬故障／警告）",
        ),
        (
            "POWER_GOOD# (Power Good Signal is NEGATED / Inactive)",
            "POWER_GOOD#（Power Good 訊號未有效／非啟用）",
        ),
        ("FAN_FAULT_WARN (Fan or Airflow Fault/Warning)", "FAN_FAULT_WARN（風扇或氣流故障／警告）"),
        (
            "STATUS_OTHER_SET (Bit in STATUS_OTHER is set)",
            "STATUS_OTHER_SET（STATUS_OTHER 中有位元被設為 1）",
        ),
        ("UNKNOWN_FAULT (Unknown fault occurred)", "UNKNOWN_FAULT（發生未知故障）"),
        (
            "INVALID_COMMAND (Master sent invalid or unsupported command code)",
            "INVALID_COMMAND（主機送出無效或不支援的指令碼）",
        ),
        (
            "INVALID_DATA (Master sent invalid or out-of-range data payload)",
            "INVALID_DATA（主機送出無效或超出範圍的資料 Payload）",
        ),
        (
            "PEC_FAILED (Packet Error Check checksum mismatch)",
            "PEC_FAILED（Packet Error Check 校驗碼不一致）",
        ),
        (
            "MEMORY_FAULT (Internal NVM / Flash / RAM fault detected)",
            "MEMORY_FAULT（偵測到內部 NVM／Flash／RAM 故障）",
        ),
        (
            "PROCESSOR_FAULT (Internal core / MCU processor fault)",
            "PROCESSOR_FAULT（內部核心／MCU 處理器故障）",
        ),
        ("COMM_FAULT (Other communication fault)", "COMM_FAULT（其他通訊故障）"),
        (
            "OTHER_MEM_LOGIC (Other memory or logic fault)",
            "OTHER_MEM_LOGIC（其他記憶體或邏輯故障）",
        ),
    )
    for source, target in status_flag_replacements:
        value = value.replace(source, target)

    # Structured semantic summaries and issue descriptions.
    value = re.sub(
        r"Temperature = ([+-]?[0-9.]+) °C \(LM75/TMP102, raw (0x[0-9A-Fa-f]+)\)",
        r"溫度 = \1 °C（LM75/TMP102，原始值 \2）",
        value,
    )
    value = re.sub(
        r"Temperature = ([+-]?[0-9.]+) °C \(8-bit MSB\)",
        r"溫度 = \1 °C（8-bit MSB）",
        value,
    )
    value = re.sub(
        r"Temperature response contains (\d+) byte\(s\); expected one 16-bit register",
        r"溫度回應包含 \1 個位元組；預期一個 16 位元暫存器",
        value,
    )
    value = re.sub(
        r"Sensor response contains (\d+) byte\(s\); expected one 16-bit register",
        r"感測器回應包含 \1 個位元組；預期一個 16 位元暫存器",
        value,
    )
    value = re.sub(
        r"(READ_[A-Z0-9_]+) command selected; response bytes are not present in this write phase",
        r"已選取 \1 指令；此寫入階段沒有回應位元組",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+) command selected; response bytes are not present in this write phase",
        r"已選取 \1 指令；此寫入階段沒有回應位元組",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+) is read-only; (\d+) write payload byte\(s\) are not valid command-selection evidence",
        r"\1 為唯讀；寫入 Payload 含 \2 個位元組，不是有效的指令選取證據",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+) does not define a read response",
        r"\1 未定義讀取回應",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+): received (\d+) byte\(s\), expected (\d+); extra payload bytes were not decoded",
        r"\1：收到 \2 個位元組，預期 \3；多出的 Payload 位元組未解碼",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+): insufficient data \(received (\d+) byte\(s\), expected (\d+)\)",
        r"\1：資料不足（已收到 \2 個位元組，預期 \3）",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+): missing PMBus block count byte",
        r"\1：缺少 PMBus Block Read 的 Byte Count 位元組",
        value,
    )
    value = re.sub(
        r"Custom PMBus Cmd (0x[0-9A-Fa-f]+):\s*",
        r"自訂 PMBus 指令 \1：",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+): block count (\d+) exceeds the PMBus/SMBus 32-byte limit",
        r"\1：Block Read 的 Byte Count \2 超過 PMBus／SMBus 32 位元組上限",
        value,
    )
    value = re.sub(
        r"([A-Z][A-Z0-9_]+): block count mismatch \(declared (\d+), received (\d+)\)",
        r"\1：Block Read 的 Byte Count 不一致（宣告 \2，收到 \3）",
        value,
    )
    value = re.sub(r"(READ_[A-Z0-9_]+) = ", r"\1 讀取值 = ", value)
    value = re.sub(r"\b(PAGE) = Rail (\d+)", r"\1（頁面） = 電源軌 \2", value)
    value = re.sub(
        r"\b(OPERATION) = ([^,]+), (Margin High|Margin Low|Nominal) \((0x[0-9A-Fa-f]+)\)",
        lambda match: (
            f"{match.group(1)}（操作） = {match.group(2).strip()}，"
            f"{ {'Margin High': 'Margin High（高裕量', 'Margin Low': 'Margin Low（低裕量', 'Nominal': 'Nominal（標稱'}[match.group(3)] }"
            f"，{match.group(4)}）"
        ),
        value,
    )
    value = re.sub(r"\b(VOUT_MODE) =", r"\1（輸出電壓模式） =", value)
    value = re.sub(r"\bWrite (\d+) byte\(s\):", r"寫入 \1 個位元組：", value)
    value = re.sub(r"\bRead (\d+) byte\(s\):", r"讀取 \1 個位元組：", value)
    value = re.sub(r"\bWrite (\d+) bytes:", r"寫入 \1 個位元組：", value)
    value = re.sub(r"\bRead (\d+) bytes:", r"讀取 \1 個位元組：", value)
    value = re.sub(
        r"STATUS_WORD: insufficient data \(received (\d+) bytes, expected (\d+)\)",
        r"STATUS_WORD：資料不足（已收到 \1 個位元組，預期 \2）",
        value,
    )
    value = re.sub(
        r"STATUS_WORD: insufficient data \(received (\d+) byte\(s\), expected (\d+)\)",
        r"STATUS_WORD：資料不足（已收到 \1 個位元組，預期 \2）",
        value,
    )
    value = re.sub(
        r"STATUS_WORD: 資料不足 \(已收到 (\d+) 個位元組，預期 (\d+)\)",
        r"STATUS_WORD：資料不足（已收到 \1 個位元組，預期 \2）",
        value,
    )
    value = re.sub(
        r"EEPROM Sequential Read \((\d+) bytes\):",
        r"EEPROM 循序讀取（\1 個位元組）：",
        value,
    )
    value = re.sub(
        r"EEPROM (Byte Write|Page Write \(\d+ bytes\)|Dummy Write / Address Set) at Offset",
        lambda match: (
            "EEPROM "
            + {
                "Byte Write": "單位元組寫入",
                "Dummy Write / Address Set": "虛擬寫入／設定位址",
            }.get(
                match.group(1),
                re.sub(r"Page Write \((\d+) bytes\)", r"分頁寫入（\1 個位元組）", match.group(1)),
            )
            + "，位移"
        ),
        value,
    )
    value = re.sub(
        r"EEPROM write exceeds the configured (\d+)-byte capacity at offset",
        r"EEPROM 寫入超過設定的 \1 位元組容量，位移",
        value,
    )
    value = re.sub(
        r"\b(STATUS_BYTE|STATUS_WORD|STATUS_CML)=",
        lambda match: {
            "STATUS_BYTE": "STATUS_BYTE（狀態位元組）=",
            "STATUS_WORD": "STATUS_WORD（狀態字）=",
            "STATUS_CML": "STATUS_CML（通訊／記憶體／邏輯狀態）=",
        }[match.group(1)],
        value,
    )
    value = value.replace("OK / 無狀態旗標", "OK／無狀態旗標")
    value = value.replace("OK / 通訊正常", "OK／通訊正常")
    value = value.replace(" (無資料／快速指令)", "（無資料／快速指令）")
    value = re.sub(r"\bBUS_VOLTAGE =", "匯流排電壓（BUS_VOLTAGE） =", value)
    value = re.sub(r"\bSHUNT_VOLTAGE =", "分流電壓（SHUNT_VOLTAGE） =", value)
    value = re.sub(r"\bCONFIGURATION =", "設定暫存器（CONFIGURATION） =", value)
    register_labels = {
        "POWER": "功率",
        "CURRENT": "電流",
        "CALIBRATION": "校正",
        "MASK_ENABLE": "遮罩／啟用",
        "ALERT_LIMIT": "警報門檻",
    }
    value = re.sub(
        r"\b(POWER|CURRENT|CALIBRATION|MASK_ENABLE|ALERT_LIMIT) =",
        lambda match: f"{register_labels[match.group(1)]}（{match.group(1)}） =",
        value,
    )
    value = re.sub(r"\b(REG_0x[0-9A-Fa-f]+):", r"暫存器 \1：", value)
    write_protect_labels = {
        "Entire memory protected": "整個記憶體已保護",
        "Protect all except PAGE/OPERATION": "除 PAGE／OPERATION 外全部保護",
        "Protect all except PAGE/OPERATION/ON_OFF": "除 PAGE／OPERATION／ON_OFF 外全部保護",
        "Unprotected": "未啟用保護",
    }
    value = re.sub(
        r"\bWRITE_PROTECT = (0x[0-9A-Fa-f]+) \((Entire memory protected|Protect all except PAGE/OPERATION/ON_OFF|Protect all except PAGE/OPERATION|Unprotected)\)",
        lambda match: (
            f"WRITE_PROTECT（寫入保護） = {match.group(1)}（{write_protect_labels[match.group(2)]}）"
        ),
        value,
    )
    value = re.sub(
        r"(CONFIG_DIR_PORT_[0-9]+|OUTPUT_PORT_[0-9]+|INPUT_PORT_[0-9]+) =",
        lambda match: f"{match.group(1)}（GPIO 暫存器） =",
        value,
    )
    value = re.sub(
        r"I2C MUX (0x[0-9A-Fa-f]+) Channel Switch -> (\[[^]]+\])(?: \(aggregate ACK; per-byte attribution unavailable\))?",
        lambda match: (
            f"I2C 多工器 {match.group(1)} 通道切換 -> {match.group(2)}"
            + ("（彙總 ACK；未提供逐位元組歸屬）" if "aggregate ACK" in match.group(0) else "")
        ),
        value,
    )
    value = re.sub(
        r"Set Register Pointer to ([\w_]+) \((0x[0-9A-Fa-f]+)\)",
        r"設定暫存器指標為 \1（\2）",
        value,
    )
    value = re.sub(r"Read Register (0x[0-9A-Fa-f]+):", r"讀取暫存器 \1：", value)

    # Short phrases that are safe when bounded by word boundaries.  They are
    # intentionally last so they cannot interfere with the structured regexes.
    bounded_replacements = (
        (r"\bexpected bytes\b", "預期位元組"),
        (r"\binsufficient data\b", "資料不足"),
        (r"\breceived\b", "已收到"),
        (r"\bexpected\b", "預期"),
        (r"\bpointer set\b", "已設定指標"),
        (r"\bresponse contains\b", "回應包含"),
        (r"\bSensor response contains\b", "感測器回應包含"),
        (r"\bbyte\(s\)\b", "個位元組"),
        (r"\bbytes\b", "個位元組"),
        (r"\bPage rollover hazard\b", "分頁回繞風險"),
        (r"\bWrite started at\b", "寫入起點為"),
        (r"\bpage base\b", "分頁起點"),
        (r"\bpage size\b", "分頁大小"),
        (r"\bPayload length\b", "Payload 長度"),
        (r"\bexceeds remaining\b", "超過剩餘空間"),
        (r"\bwill WRAP AROUND and overwrite\b", "會回繞並覆寫"),
        (r"\bCurrent Address Read\b", "目前位址讀取"),
        (r"\bSequential Read\b", "循序讀取"),
        (r"\bSlave device\b", "從裝置"),
        (r"\bSlave at\b", "位於"),
        (r"\bMaster issued\b", "主機送出"),
        (r"\bMaster MCU\b", "主機 MCU"),
        (r"\bdid NOT acknowledge its address\b", "未對位址回應 ACK"),
        (r"\backnowledged address but sent\b", "已回應位址但送出"),
        (r"\bheld SCL low\b", "將 SCL 拉低"),
        (r"\bduring byte transfer\b", "於位元組傳輸期間"),
        (r"\bviolating SMBus 3\.0 tTIMEOUT limit\b", "違反 SMBus 3.0 tTIMEOUT 門檻"),
        (r"\bended abruptly without a valid STOP condition\b", "在沒有有效 STOP 條件下突然結束"),
        (r"\bObserved SCL clock frequency fluctuates between\b", "觀察到 SCL 時鐘頻率在"),
        (r"\bAverage:\s*", "平均："),
        (
            r"\bcommand selected; response bytes are not present in this write phase\b",
            "已選取指令；此寫入階段沒有回應位元組",
        ),
    )
    for pattern, target in bounded_replacements:
        value = re.sub(pattern, target, value)
    return value


def localize_issue_title(code: str, title: str | None) -> str:
    """Return a Chinese-first diagnostic title while retaining issue code context."""
    value = str(title or code)
    patterns = {
        "I2C_EEPROM_ACK_POLL": (
            r"EEPROM Write Polling NACK on (0x[0-9A-Fa-f]+)",
            r"EEPROM 寫入輪詢 NACK（位址 \1）",
        ),
        "I2C_ADDR_NACK": (r"Address NACK on (0x[0-9A-Fa-f]+) \(([^)]+)\)", r"位址 NACK（\1，\2）"),
        "I2C_PREMATURE_READ_NACK": (
            r"Premature Master Read NACK on Byte (.+)",
            r"主機讀取過早送出 NACK（第 \1）",
        ),
        "I2C_DATA_NACK": (
            r"Slave Data NACK on Byte (\d+) \((0x[0-9A-Fa-f]+)\) at (0x[0-9A-Fa-f]+)",
            r"從裝置資料 NACK（第 \1 個位元組，\2，位址 \3）",
        ),
        "I2C_MISSING_STOP": (
            r"Missing STOP Condition / Bus Hang on Transaction #(.+)",
            r"缺少 STOP 條件／匯流排可能掛起（交易 #\1）",
        ),
        "I2C_EEPROM_PAGE_ROLLOVER": (
            r"EEPROM Page Boundary Wrap-Around Hazard on (0x[0-9A-Fa-f]+)",
            r"EEPROM 分頁邊界回繞風險（\1）",
        ),
        "I2C_SMBUS_TIMEOUT": (
            r"SMBus Clock Stretching Timeout \((.+)\)",
            r"SMBus 時鐘延展逾時（\1）",
        ),
        "I2C_LONG_CLOCK_STRETCH": (
            r"Noticeable Clock Stretching \((.+)\) on (0x[0-9A-Fa-f]+)",
            r"時鐘延展時間偏長（\1，位址 \2）",
        ),
        "I2C_HIGH_CLOCK_JITTER": (
            r"High Clock Frequency Jitter \((.+)\)",
            r"SCL 時鐘頻率抖動偏高（\1）",
        ),
        "I2C_MUX_MULTI_CHANNEL": (
            r"Multiple MUX Channels Enabled Simultaneously \((0x[0-9A-Fa-f]+)\) @ Tx #(.+)",
            r"同時啟用多個多工器通道（\1，交易 #\2）",
        ),
    }
    pattern = patterns.get(code)
    if pattern:
        return re.sub(pattern[0], pattern[1], value)
    return localize_explanatory_text(value)


def localize_issue_description(description: str | None) -> str:
    """Translate diagnostic symptom prose while preserving measured values."""
    raw = str(description or "")
    patterns = (
        (
            r"Slave device at 7-bit address (0x[0-9A-Fa-f]+) \(8-bit (0x[0-9A-Fa-f]+)\) did NOT acknowledge its address\.",
            r"7-bit 位址 \1（8-bit \2）的從裝置未回應位址 ACK。",
        ),
        (
            r"Slave at (0x[0-9A-Fa-f]+) returned NACK to address byte during write polling\. This is normal behavior while the EEPROM is executing its internal tWR write cycle \(~5ms\)\.",
            r"位於 \1 的從裝置在寫入輪詢期間對位址位元組回覆 NACK。EEPROM 執行內部 tWR 寫入週期（約 5 ms）時，這是正常現象。",
        ),
        (
            r"Master issued NACK on byte index (\d+) before completing intended multi-byte read\.",
            r"主機在完成預期的多位元組讀取前，於第 \1 個位元組送出 NACK。",
        ),
        (
            r"Slave acknowledged address but sent NACK on data byte (0x[0-9A-Fa-f]+) \(offset/byte position (\d+)\)\.",
            r"從裝置已回應位址，但在資料位元組 \1（位移／位元組位置 \2）回覆 NACK。",
        ),
        (
            r"Transaction #(\d+) to (0x[0-9A-Fa-f]+) ended abruptly without a valid STOP condition\.",
            r"交易 #\1（目標位址 \2）在沒有有效 STOP 條件下突然結束。",
        ),
        (
            r"Slave at (0x[0-9A-Fa-f]+) held SCL low for ([0-9.]+) ms, violating SMBus 3\.0 tTIMEOUT limit \(([0-9.]+) ms\)\.",
            r"位於 \1 的從裝置將 SCL 拉低 \2 ms，違反 SMBus 3.0 tTIMEOUT 門檻（\3 ms）。",
        ),
        (
            r"Slave held SCL low for ([0-9.]+) µs during byte transfer\.",
            r"從裝置在位元組傳輸期間將 SCL 拉低 \1 µs。",
        ),
        (
            r"Observed SCL clock frequency fluctuates between ([0-9.]+) kHz and ([0-9.]+) kHz \(Average: ([0-9.]+) kHz\)\.",
            r"觀察到 SCL 時鐘頻率在 \1 kHz 到 \2 kHz 之間變動（平均：\3 kHz）。",
        ),
    )
    for pattern, replacement in patterns:
        matched = re.fullmatch(pattern, raw)
        if matched:
            return re.sub(pattern, replacement, raw)
    mux_match = re.fullmatch(
        r"I2C Mux at (0x[0-9A-Fa-f]+) was configured with control byte "
        r"(0x[0-9A-Fa-f]+), enabling channels (\[[^]]+\]) simultaneously\.",
        raw,
    )
    if mux_match:
        return (
            f"位於 {mux_match.group(1)} 的 I2C 多工器控制位元組為 {mux_match.group(2)}，"
            f"同時啟用通道 {mux_match.group(3)}。"
        )
    return localize_explanatory_text(raw)


def localize_issue_root_cause(root_cause: str | None) -> str:
    """Translate known root-cause checklist prose for the UI/report."""
    value = str(root_cause or "")
    exact = {
        "EEPROM hardware disables its I2C receiver during high-voltage page programming. Firmware is probing the device until ACK is returned, signaling write completion.": "EEPROM 在高電壓分頁寫入期間會停用 I2C 接收器。韌體持續探測裝置，直到收到 ACK 以確認寫入完成。",
        "Master I2C controller receive FIFO aborted transfer early, or firmware read buffer length was configured shorter than expected.": "主機 I2C 控制器的接收 FIFO 過早中止傳輸，或韌體讀取緩衝區長度設定小於預期。",
        "Slave requires significant processing time or is executing an internal ADC conversion / Flash write.": "從裝置需要較長處理時間，或正在執行內部 ADC 轉換／Flash 寫入。",
        "Slave MCU firmware entered a deadlock, long blocking interrupt routine, or hardware lockup, holding SCL low indefinitely. SMBus-compliant masters and slaves will reset their interfaces.": "從裝置 MCU 韌體進入死結、長時間阻塞的中斷服務常式，或硬體鎖死，導致 SCL 持續維持低電位。符合 SMBus 的主機與從裝置會重設介面。",
        "EEPROM internal address counter increments within the current page boundary. When writing past the end of a page, the address wraps to the start of the SAME page, silently corrupting previously written bytes at the page base instead of advancing to the next page!": "EEPROM 內部位址計數器只在目前分頁邊界內遞增。寫入超過分頁尾端時，位址會回繞到同一分頁起點，悄悄覆寫原有資料，而不是前進到下一頁。",
    }
    if value in exact:
        return exact[value]
    replacements = (
        (
            "1. Slave is unpowered or in Deep Sleep / Reset state.",
            "1. 從裝置未上電，或處於 Deep Sleep／Reset 狀態。",
        ),
        (
            "2. 7-bit vs 8-bit addressing bug in firmware (e.g. passing 0x50 as 8-bit address instead of shifting left, or vice versa).",
            "2. 韌體混用 7-bit 與 8-bit 位址（例如把 0x50 當成 8-bit 位址傳入，未左移，或反向處理）。",
        ),
        (
            "3. Hardware address strapping resistors (ADDR/A0/A1/A2 pins) do not match software address.",
            "3. 硬體位址設定電阻（ADDR／A0／A1／A2 腳位）與軟體位址不一致。",
        ),
        (
            "4. Upstream I2C Switch/Mux (e.g. PCA9548A) channel is closed or disabled.",
            "4. 上游 I2C Switch／Mux（例如 PCA9548A）通道關閉或停用。",
        ),
        (
            "5. Open-drain bus lines missing pull-up resistors or damaged pull-up circuit.",
            "5. Open-drain 匯流排線路缺少上拉電阻，或上拉電路損壞。",
        ),
        (
            "1. Invalid or unsupported register address / command code.",
            "1. 暫存器位址／指令碼無效或不受支援。",
        ),
        ("2. Attempt to write to a Read-Only register.", "2. 嘗試寫入唯讀暫存器。"),
        (
            "3. Slave internal buffer/FIFO full or chip busy processing previous task.",
            "3. 從裝置內部 buffer／FIFO 已滿，或晶片忙於處理前一項工作。",
        ),
        (
            "4. Write protection active (e.g. EEPROM WP pin pulled high, PMBus WRITE_PROTECT active).",
            "4. 寫入保護啟用（例如 EEPROM WP 腳位拉高，或 PMBus WRITE_PROTECT 啟用）。",
        ),
        (
            "5. Packet Error Check (PEC) checksum byte was incorrect.",
            "5. Packet Error Check（PEC）校驗位元組不正確。",
        ),
        (
            "1. Master MCU crashed, hit a watchdog reset, or I2C peripheral encountered an error interrupt midway.",
            "1. 主機 MCU 當機、觸發 watchdog reset，或 I2C 週邊在傳輸中途遇到錯誤中斷。",
        ),
        (
            "2. Bus Stuck Low: Slave was outputting a '0' bit on SDA when Master aborted, leaving Slave holding SDA low.",
            "2. Bus Stuck Low：主機中止時從裝置正在 SDA 輸出 0，導致從裝置持續拉低 SDA。",
        ),
        (
            "3. Physical line noise or clock glitch corrupted the transaction state machine.",
            "3. 實體線路雜訊或時鐘 glitch 破壞交易狀態機。",
        ),
        (
            "1. Software bit-banging I2C driver interrupted by high-priority RTOS interrupts / ISRs.",
            "1. 軟體模擬 I2C 驅動程式（Software bit-banging driver）被高優先權 RTOS 中斷／ISR 打斷。",
        ),
        (
            "2. Excessive bus capacitance (>400pF) causing slow rise times (t_r) and trigger threshold delay.",
            "2. 匯流排電容過大（>400 pF），造成上升時間（t_r）變慢與觸發門檻延遲。",
        ),
        (
            "3. Pull-up resistors too large (e.g. 10kΩ on Fast-mode 400kHz).",
            "3. 上拉電阻過大（例如 Fast-mode 400 kHz 使用 10 kΩ）。",
        ),
        (
            "Enabling multiple downstream MUX channels simultaneously can cause address collisions "
            + "and excessive bus capacitance (> 400pF).",
            "同時啟用多個下游 MUX 通道可能造成位址碰撞與匯流排電容過大（> 400 pF）。",
        ),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return value


def localize_issue_advice(advice: str | None) -> str:
    """Translate English fragments in an actionable advice item."""
    value = str(advice or "")
    replacements = (
        (
            "No bug if subsequent polling transactions succeed with ACK within 5ms to 10ms.",
            "若後續輪詢交易在 5～10 ms 內以 ACK 成功，這不是錯誤。",
        ),
        (
            "If polling loops exceed 10ms without ACK, verify write voltage and EEPROM WP pin.",
            "若輪詢超過 10 ms 仍沒有 ACK，請確認寫入電壓與 EEPROM WP 腳位。",
        ),
        ("【Pin Strapping】", "【腳位設定】"),
        ("【Bus Recovery】", "【匯流排復原】"),
        ("【Slave Reset】", "【從裝置重設】"),
        ("Slave", "從裝置"),
        ("Master", "主機"),
        ("Bus Recovery", "匯流排復原"),
        ("Power Cycle", "電源循環"),
        ("Clock Pulse", "時鐘脈波"),
        ("Command", "指令"),
        ("Channel", "通道"),
        ("Polling", "輪詢"),
        ("Bus Stuck Low", "匯流排卡低（Bus Stuck Low）"),
        ("Slave 晶片", "從裝置晶片"),
        ("Slave 端", "從裝置端"),
        ("Master 端", "主機端"),
        (
            "Ensure only 1 downstream channel is enabled unless broadcast write is intended.",
            "除非刻意進行 broadcast write，否則請只啟用 1 個下游通道。",
        ),
        (
            "Verify identical slave addresses on different channels do not respond concurrently.",
            "確認不同通道上的相同從裝置位址不會同時回應。",
        ),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    value = re.sub(r"從裝置\s+端", "從裝置端", value)
    value = re.sub(r"主機\s+端", "主機端", value)
    value = re.sub(
        r"(?<![A-Za-z])\s+(從裝置|主機|匯流排|輪詢|時鐘|指令|通道)",
        r"\1",
        value,
    )
    value = (
        value.replace("量測 從裝置 晶片", "量測從裝置晶片")
        .replace("從裝置 晶片", "從裝置晶片")
        .replace("從裝置 的", "從裝置的")
        .replace("從裝置 仍", "從裝置仍")
        .replace("從裝置 拉低", "從裝置拉低")
        .replace("從裝置 是否", "從裝置是否")
        .replace("從裝置 韌體排查", "從裝置韌體排查")
        .replace("輪詢 或", "輪詢或")
        .replace("執行 電源循環", "執行電源循環")
        .replace("下 指令", "下指令")
        .replace("下指令 開啟", "下指令開啟")
        .replace("對應 通道", "對應通道")
    )
    return value


def localize_waveform_label(label: str | None) -> str:
    """Translate waveform annotation labels while retaining hex/protocol tokens."""
    value = str(label or "")
    value = re.sub(r"^Stretch ([0-9.]+)ms$", r"時鐘延展 \1 ms", value)
    value = re.sub(r"^Expected (0x[0-9A-Fa-f]+)$", r"預期 \1", value)
    value = value.replace("Unknown", "未知值")
    value = value.replace("Reg:", "暫存器：")
    return value


def localize_waveform_detail(detail: str | None) -> str:
    """Translate waveform hover details; SCL/SDA and ACK tokens remain intact."""
    value = str(detail or "")
    replacements = (
        (
            "I2C Repeated START (SDA falling edge while SCL is High)",
            "I2C Repeated START（SCL 為 High 時 SDA 下降緣）",
        ),
        (
            "I2C Start Condition (SDA falling edge while SCL is High)",
            "I2C START 條件（SCL 為 High 時 SDA 下降緣）",
        ),
        (
            "I2C Stop Condition (SDA rising edge while SCL is High)",
            "I2C STOP 條件（SCL 為 High 時 SDA 上升緣）",
        ),
        ("Address byte:", "位址位元組："),
        ("Byte:", "資料位元組："),
        ("binary:", "二進位："),
        ("Acknowledge bit: 0 (ACK)", "應答位元：0（ACK）"),
        ("Not-Acknowledge bit: 1 (NACK)", "非應答位元：1（NACK）"),
        (
            "ACK/NACK was not present in the source trace; SDA level is reconstructed as high.",
            "來源追蹤記錄未提供 ACK/NACK；SDA 電位以 High 重建。",
        ),
        ("Slave SCL Clock Stretching:", "從裝置 SCL 時鐘延展："),
        (
            "Unknown read byte placeholder; value is not measured",
            "未知的讀取位元組佔位符；尚未量測實際值",
        ),
        (
            "Expected/assumed read byte; not measured from a device or capture",
            "預期／假設的讀取位元組；不是裝置或 capture 的量測值",
        ),
        (
            "Controller NACK terminates the final read byte",
            "Controller NACK 結束最後一個讀取位元組",
        ),
        ("Slave ACK", "從裝置 ACK"),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return value


def localize_status(status: str | TransactionStatus) -> str:
    """Return zh-TW readable status string with original token preserved."""
    val = status.value if isinstance(status, TransactionStatus) else str(status)
    return TRANSACTION_STATUS_ZH.get(val, val)


def localize_speed_mode(mode: str | I2CSpeedMode) -> str:
    """Return zh-TW readable speed mode description."""
    val = mode.value if isinstance(mode, I2CSpeedMode) else str(mode)
    return SPEED_MODE_ZH.get(val, val)


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
    return localize_explanatory_text(summary)


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
