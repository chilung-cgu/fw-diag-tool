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
    "btn_download_html": {"zh-TW": "下載 HTML 報告", "en-US": "Download HTML Report"},
    "btn_download_sarif": {"zh-TW": "下載 SARIF 報告", "en-US": "Download SARIF Report"},
    "btn_download_report": {"zh-TW": "⬇️ 下載報告", "en-US": "⬇️ Download Report"},
    "btn_load_example": {"zh-TW": "📋 載入範例", "en-US": "📋 Load Example"},
    "btn_load_preset": {"zh-TW": "載入預設範例", "en-US": "Load Preset Example"},
    "btn_save_session": {"zh-TW": "💾 儲存分析 Session", "en-US": "💾 Save Analysis Session"},
    "btn_apply": {"zh-TW": "套用設定", "en-US": "Apply Settings"},
    "btn_clear": {"zh-TW": "清除", "en-US": "Clear"},
    # Titles & Headings
    "title_app": {
        "zh-TW": "韌體協定診斷工具箱",
        "en-US": "Firmware Protocol Diagnostic Suite",
    },
    "title_app_full": {
        "zh-TW": "韌體訊號與協定診斷套件",
        "en-US": "Firmware Signal & Protocol Diagnostic Suite",
    },
    "title_dashboard": {
        "zh-TW": "韌體訊號與協定診斷套件 — 總覽",
        "en-US": "Firmware Signal & Protocol Diagnostic Suite — Overview",
    },
    "title_i2c_diagnosis": {
        "zh-TW": "I2C / PMBus 診斷與波形檢視",
        "en-US": "I2C / PMBus Waveform Diagnosis",
    },
    "title_i2c_diagnosis_full": {
        "zh-TW": "I2C / SMBus / PMBus 協定分析與數位波形檢視",
        "en-US": "I2C / SMBus / PMBus Protocol Analysis & Digital Waveform Viewer",
    },
    "title_i2c_builder": {
        "zh-TW": "I2C 封包模擬器與驅動產生",
        "en-US": "I2C Packet Simulator & Driver Generator",
    },
    "title_waveform_diff": {
        "zh-TW": "雙波形對比檢視",
        "en-US": "Dual Waveform Diff Viewer",
    },
    "title_correlation": {
        "zh-TW": "跨協定時間線關聯分析",
        "en-US": "Cross-Protocol Timeline Correlation",
    },
    "title_session_analytics": {
        "zh-TW": "多工作階段趨勢分析",
        "en-US": "Multi-Session Trend Analysis",
    },
    "title_overview": {
        "zh-TW": "功能總覽與快速入門",
        "en-US": "Feature Overview & Quick Start",
    },
    "title_uart": {
        "zh-TW": "UART 崩潰轉儲與 HardFault 分析",
        "en-US": "UART Crash Dump & HardFault Analysis",
    },
    "title_mctp": {
        "zh-TW": "MCTP／IPMB 伺服器管理協定解析",
        "en-US": "MCTP / IPMB Server Management Protocol Parser",
    },
    "title_pcie": {
        "zh-TW": "PCIe 設定空間與 AER 診斷",
        "en-US": "PCIe Config Space & AER Diagnosis",
    },
    "title_spi": {
        "zh-TW": "SPI Flash 協定診斷",
        "en-US": "SPI Flash Protocol Diagnosis",
    },
    "title_board_profile": {
        "zh-TW": "Board Profile 視覺化編輯器",
        "en-US": "Board Profile Visual Editor",
    },
    "title_dts": {
        "zh-TW": "Device Tree 產生器",
        "en-US": "Device Tree Generator",
    },
    "title_register": {
        "zh-TW": "暫存器 Bitfield 解碼器",
        "en-US": "Register Bitfield Decoder",
    },
    "title_codegen": {
        "zh-TW": "C Register 巨集產生器",
        "en-US": "C Register Macro Generator",
    },
    "title_tutorial": {
        "zh-TW": "互動式教學導覽",
        "en-US": "Interactive Tutorial Guide",
    },
    "title_fault_arena": {
        "zh-TW": "Firmware 實戰除錯實驗室",
        "en-US": "Firmware Debugging Lab",
    },
    "title_sop": {
        "zh-TW": "韌體除錯指南與 SOP",
        "en-US": "Firmware Debug SOP & Guide",
    },
    "title_chip_db": {
        "zh-TW": "I2C 晶片資料庫瀏覽器",
        "en-US": "I2C Chip Database Browser",
    },
    "title_emulator": {
        "zh-TW": "虛擬設備模擬器實驗室",
        "en-US": "Virtual Device Emulator Lab",
    },
    "title_fuzz_lab": {
        "zh-TW": "協定解析器 Fuzz 測試",
        "en-US": "Protocol Parser Fuzzing Lab",
    },
    # Navigation Categories
    "nav_category_protocols": {"zh-TW": "協定分析與波形", "en-US": "Protocol Analysis & Waveforms"},
    "nav_category_advanced": {"zh-TW": "進階分析", "en-US": "Advanced Analysis"},
    "nav_category_overview": {"zh-TW": "總覽", "en-US": "Overview"},
    "nav_category_system": {"zh-TW": "系統協定診斷", "en-US": "System Protocol Diagnosis"},
    "nav_category_tools": {"zh-TW": "產生器與硬體工具", "en-US": "Generators & Hardware Tools"},
    "nav_category_labs": {"zh-TW": "實驗室與學習", "en-US": "Labs & Learning"},
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
    "guide_expander_i2c": {
        "zh-TW": "📖 點擊展開：I2C/PMBus 波形診斷手冊",
        "en-US": "📖 Click to expand: I2C/PMBus Waveform Diagnosis Manual",
    },
    "guide_expander_appendix": {
        "zh-TW": "📊 點擊展開：附錄 A 圖表與數據判讀指南",
        "en-US": "📊 Click to expand: Appendix A Chart & Data Interpretation Guide",
    },
    "upload_label": {"zh-TW": "請上傳檔案或貼上內容", "en-US": "Upload file or paste content"},
    "please_upload_file": {"zh-TW": "請上傳檔案", "en-US": "Please upload a file"},
    "select_input_source": {"zh-TW": "請選擇輸入來源", "en-US": "Please select input source"},
    "select_preset_label": {"zh-TW": "選擇示範範例", "en-US": "Select Preset Example"},
    "analysis_results": {"zh-TW": "分析結果", "en-US": "Analysis Results"},
    "system_dashboard": {"zh-TW": "📊 系統狀態儀表板", "en-US": "📊 System Status Dashboard"},
    "quick_launch": {"zh-TW": "⚡ 常用診斷快速啟動", "en-US": "⚡ Quick Diagnostic Launch"},
    "tool_version_runtime": {"zh-TW": "工具版本 / 執行環境", "en-US": "Tool Version / Runtime"},
    "installed_modules_protocols": {
        "zh-TW": "已安裝功能模組 / 支援協定",
        "en-US": "Installed Modules / Supported Protocols",
    },
    "scenarios_example_files": {
        "zh-TW": "實戰情境 / 範例檔案",
        "en-US": "Scenarios / Example Files",
    },
    "load_reproducible_session": {
        "zh-TW": "載入可重現 Session（需另行提供原始 capture 才能重播）",
        "en-US": "Load Reproducible Session (original capture required for replay)",
    },
    "session_management": {"zh-TW": "💾 Session 管理", "en-US": "💾 Session Management"},
    "module_overview": {"zh-TW": "🛠 功能模組總覽", "en-US": "🛠 Feature Modules Overview"},
    "whats_new_title": {
        "zh-TW": "📢 最近更新紀錄 (What's New in v1.2.0)",
        "en-US": "📢 What's New in v1.2.0",
    },
    "whats_new_expander": {
        "zh-TW": "🎉 檢視 v1.2.0 重點更新項目",
        "en-US": "🎉 View Key Updates in v1.2.0",
    },
    "language_selector_label": {
        "zh-TW": "🌐 語言 / Language",
        "en-US": "🌐 Language / 語言",
    },
    # Quick Launch Buttons
    "quick_link_i2c": {"zh-TW": "📊 I2C 診斷", "en-US": "📊 I2C Diagnosis"},
    "quick_link_diff": {"zh-TW": "⚖️ 雙波形差分", "en-US": "⚖️ Waveform Diff"},
    "quick_link_pcie": {"zh-TW": "🚀 PCIe AER", "en-US": "🚀 PCIe AER"},
    "quick_link_uart": {"zh-TW": "📟 UART Crash", "en-US": "📟 UART Crash"},
    "quick_link_spi": {"zh-TW": "⚡ SPI Flash", "en-US": "⚡ SPI Flash"},
    "quick_link_fault_arena": {"zh-TW": "🏆 Fault Arena", "en-US": "🏆 Fault Arena"},
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
    "title_session_compare": {
        "zh-TW": "Session A/B 對比分析",
        "en-US": "Session A/B Comparison",
    },
    "title_protocol_diff": {
        "zh-TW": "協定 A/B 對比分析",
        "en-US": "Protocol A/B Diff",
    },
    "protocol_diff_select_protocol": {
        "zh-TW": "選擇協定",
        "en-US": "Select Protocol",
    },
    "protocol_diff_baseline": {
        "zh-TW": "Baseline（基準）",
        "en-US": "Baseline",
    },
    "protocol_diff_candidate": {
        "zh-TW": "Candidate（待測）",
        "en-US": "Candidate",
    },
    "protocol_diff_download_report": {
        "zh-TW": "下載 Markdown 對比報告",
        "en-US": "Download Markdown Diff Report",
    },
}


def register_gui_domain(registry: TranslationRegistry) -> None:
    """將 GUI 介面詞條註冊至 registry 的 'gui' domain。"""
    registry.register_domain("gui", GUI_TRANSLATIONS)


__all__ = ["GUI_TRANSLATIONS", "register_gui_domain"]
