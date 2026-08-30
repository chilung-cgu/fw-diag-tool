from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fw_diag_tool.i18n.registry import TranslationRegistry

GUI_TRANSLATIONS: dict[str, dict[str, str]] = {
    # Buttons & Actions
    "btn_analyze": {"zh-TW": "開始分析", "en-US": "Analyze"},
    "btn_reset": {"zh-TW": "重設", "en-US": "Reset"},
    "btn_export": {"zh-TW": "匯出報告", "en-US": "Export Report"},
    "btn_copy": {"zh-TW": "複製內容", "en-US": "Copy Content"},
    "btn_download_csv": {"zh-TW": "下載 CSV", "en-US": "Download CSV"},
    "btn_download_json": {"zh-TW": "下載 JSON", "en-US": "Download JSON"},
    # Titles & Headings
    "title_app": {
        "zh-TW": "韌體協定診斷工具箱",
        "en-US": "Firmware Protocol Diagnostic Suite",
    },
    "sidebar_navigation": {"zh-TW": "導覽與模式選擇", "en-US": "Navigation & Mode Selection"},
    "tab_transactions": {"zh-TW": "📜 封包交易列表", "en-US": "📜 Transactions"},
    "tab_waveform": {"zh-TW": "📈 數位方波與協定軌", "en-US": "📈 Waveform"},
    "tab_anomalies": {"zh-TW": "🚨 異常診斷", "en-US": "🚨 Anomalies"},
    "tab_timing": {"zh-TW": "📊 匯流排時序與健康圖表", "en-US": "📊 Bus Timing & Health"},
    "tab_report": {"zh-TW": "📝 診斷報告", "en-US": "📝 Diagnostic Report"},
    "fault_arena_title": {"zh-TW": "故障演練場", "en-US": "Fault Arena"},
    # Spinners
    "spinner_analyzing": {"zh-TW": "正在分析中…", "en-US": "Analyzing..."},
    "spinner_i2c": {"zh-TW": "正在解析 I2C 輸入資料…", "en-US": "Parsing I2C input data..."},
    "spinner_spi": {"zh-TW": "正在解析 SPI 輸入資料…", "en-US": "Parsing SPI input data..."},
    "spinner_pcie": {"zh-TW": "正在解析 PCIe 輸入資料…", "en-US": "Parsing PCIe input data..."},
    "spinner_uart": {"zh-TW": "正在解析 UART 記錄…", "en-US": "Parsing UART logs..."},
    "spinner_mctp": {"zh-TW": "正在解析 MCTP/IPMB 輸入…", "en-US": "Parsing MCTP/IPMB input..."},
    # UI Labels & Prompts
    "guide_expander_label": {
        "zh-TW": "📖 點擊展開本功能詳細實戰教學手冊",
        "en-US": "📖 Click to expand detailed practical guide",
    },
    "upload_label": {"zh-TW": "請上傳檔案或貼上內容", "en-US": "Upload file or paste content"},
    "select_preset_label": {"zh-TW": "選擇示範範例", "en-US": "Select Preset Example"},
    # Error Messages
    "error_file_empty": {
        "zh-TW": "輸入檔案內容為空，無法進行分析。",
        "en-US": "Input content is empty, cannot proceed with analysis.",
    },
    "error_invalid_hex": {
        "zh-TW": "十六進位輸入無效：無法解析成正確位元組序列。",
        "en-US": "Invalid hex input: cannot parse into valid byte sequence.",
    },
    "error_page_size_positive": {
        "zh-TW": "頁面大小必須是正整數。",
        "en-US": "Page size must be a positive integer.",
    },
    "error_i2c_address_range": {
        "zh-TW": "從裝置 7-bit 位址必須介於 0x08～0x77。",
        "en-US": "Slave 7-bit address must be between 0x08 and 0x77.",
    },
    "error_payload_size_limit": {
        "zh-TW": "{field} 有 {actual} 個位元組，超過 {limit} 個位元組上限。",
        "en-US": "{field} has {actual} bytes, exceeding the limit of {limit} bytes.",
    },
}


def register_gui_domain(registry: TranslationRegistry) -> None:
    """將 GUI 介面詞條註冊至 registry 的 'gui' domain。"""
    registry.register_domain("gui", GUI_TRANSLATIONS)


__all__ = ["GUI_TRANSLATIONS", "register_gui_domain"]
