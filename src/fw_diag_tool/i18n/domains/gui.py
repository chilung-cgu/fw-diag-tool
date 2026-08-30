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
    "csv_download_btn": {"zh-TW": "📥 下載 CSV", "en-US": "📥 Download CSV"},
    "csv_download_tooltip": {
        "zh-TW": "將分析結果匯出為 CSV 格式檔案",
        "en-US": "Export analysis results as a CSV file",
    },
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
    "title_batch_analysis": {
        "zh-TW": "批次分析",
        "en-US": "Batch Analysis",
    },
    "title_unified_report": {
        "zh-TW": "統一多協定報告",
        "en-US": "Unified Multi-Protocol Report",
    },
    "title_unified_report_full": {
        "zh-TW": "統一多協定診斷報告產生器",
        "en-US": "Unified Multi-Protocol Diagnostic Report Generator",
    },
    "desc_unified_report": {
        "zh-TW": "整合 I2C、SPI、UART、PCIe、MCTP 等多協定診斷結果，計算整體健康分數與簽核檢查清單，產出標準化 Markdown 與 HTML 報告。",
        "en-US": "Aggregate I2C, SPI, UART, PCIe, MCTP diagnostics, compute overall health score and sign-off checklist, and export standardized Markdown and HTML reports.",
    },
    "tab_multi_upload": {
        "zh-TW": "批次多檔上傳",
        "en-US": "Multi-File Upload",
    },
    "tab_dedicated_upload": {
        "zh-TW": "各協定獨立上傳",
        "en-US": "Per-Protocol Upload",
    },
    "tab_sample_presets": {
        "zh-TW": "載入範例資料",
        "en-US": "Preset Examples",
    },
    "lbl_multi_upload_title": {
        "zh-TW": "批次多協定日誌／擷取檔上傳",
        "en-US": "Multi-Protocol Log / Capture File Upload",
    },
    "lbl_multi_upload_desc": {
        "zh-TW": "上傳多個檔案（支援 .csv, .log, .txt, .hex），系統將自動識別協定類型",
        "en-US": "Upload multiple files (.csv, .log, .txt, .hex), auto-detecting protocol type",
    },
    "lbl_dedicated_upload_title": {
        "zh-TW": "指定協定專用上傳區",
        "en-US": "Dedicated Per-Protocol Upload Area",
    },
    "lbl_sample_title": {
        "zh-TW": "快速載入多協定範例資料進行體驗",
        "en-US": "Quickly load multi-protocol sample datasets",
    },
    "lbl_sample_select": {
        "zh-TW": "選擇要納入統一報告的範例協定",
        "en-US": "Select sample protocols to include in report",
    },
    "btn_generate_unified_report": {
        "zh-TW": "🚀 產生統一多協定報告",
        "en-US": "🚀 Generate Unified Multi-Protocol Report",
    },
    "msg_no_files_uploaded": {
        "zh-TW": "請先上傳檔案或載入範例資料再產生報告。",
        "en-US": "Please upload files or load sample datasets before generating report.",
    },
    "msg_generating_report": {
        "zh-TW": "正在平行分析各協定數據並編制統一報告…",
        "en-US": "Analyzing protocol datasets and building unified report...",
    },
    "msg_report_ready": {
        "zh-TW": "統一多協定診斷報告已成功產生！",
        "en-US": "Unified multi-protocol diagnostic report generated successfully!",
    },
    "lbl_report_dashboard_title": {
        "zh-TW": "診斷報告總覽",
        "en-US": "Diagnostic Executive Overview",
    },
    "lbl_health_score": {
        "zh-TW": "整體健康分數",
        "en-US": "Overall Health Score",
    },
    "lbl_overall_status": {
        "zh-TW": "整體狀態",
        "en-US": "Overall Status",
    },
    "lbl_protocol_count": {
        "zh-TW": "納入協定數",
        "en-US": "Protocol Count",
    },
    "lbl_total_anomalies": {
        "zh-TW": "累計異常數",
        "en-US": "Total Anomalies",
    },
    "lbl_export_section": {
        "zh-TW": "匯出與下載報告",
        "en-US": "Export & Downloads",
    },
    "btn_download_unified_md": {
        "zh-TW": "⬇️ 下載 Markdown 報告",
        "en-US": "⬇️ Download Markdown Report",
    },
    "btn_download_unified_html": {
        "zh-TW": "⬇️ 下載 HTML 報告",
        "en-US": "⬇️ Download HTML Report",
    },
    "lbl_report_preview": {
        "zh-TW": "報告內容即時預覽",
        "en-US": "Live Report Preview",
    },
    "tab_rendered_md": {
        "zh-TW": "視覺化排版",
        "en-US": "Rendered View",
    },
    "tab_raw_md": {
        "zh-TW": "原始 Markdown",
        "en-US": "Raw Markdown",
    },
    "title_settings": {
        "zh-TW": "偏好設定",
        "en-US": "Settings & Preferences",
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
        "zh-TW": "📢 最近更新紀錄 (What's New in v1.5.0)",
        "en-US": "📢 What's New in v1.5.0",
    },
    "whats_new_expander": {
        "zh-TW": "🎉 檢視 v1.5.0 重點更新項目",
        "en-US": "🎉 View Key Updates in v1.5.0",
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
    "protocol_diff_download_json_report": {
        "zh-TW": "下載 JSON 差異報告",
        "en-US": "Download JSON Diff Report",
    },
    # Batch Analysis
    "batch_analysis_caption": {
        "zh-TW": "批次上傳多個韌體追蹤或日誌檔案（支援 .csv, .log, .txt, .hex），自動或指定協定進行平行診斷並產生綜合報告與 ZIP 封裝。",
        "en-US": "Batch upload multiple firmware trace or log files (.csv, .log, .txt, .hex supported) for parallel automated or protocol-specific diagnosis, consolidated reports, and ZIP packaging.",
    },
    "batch_protocol_select_label": {
        "zh-TW": "協定選擇（Protocol Selection）",
        "en-US": "Protocol Selection",
    },
    "batch_proto_auto": {
        "zh-TW": "自動偵測（Auto Detect）",
        "en-US": "Auto Detect",
    },
    "batch_uploader_label": {
        "zh-TW": "上傳多個檔案（支援 .csv, .log, .txt, .hex）",
        "en-US": "Upload multiple files (.csv, .log, .txt, .hex supported)",
    },
    "batch_btn_start": {
        "zh-TW": "開始批次分析",
        "en-US": "Start Batch Analysis",
    },
    "batch_empty_warning": {
        "zh-TW": "請先上傳至少一個檔案再進行批次分析。",
        "en-US": "Please upload at least one file before running batch analysis.",
    },
    "batch_no_files_analyzed": {
        "zh-TW": "未找到符合指定協定或格式的檔案可進行分析。",
        "en-US": "No files matching the specified protocol or format were found for analysis.",
    },
    "batch_metric_total": {
        "zh-TW": "總檔案數",
        "en-US": "Total Files",
    },
    "batch_metric_success": {
        "zh-TW": "成功",
        "en-US": "Success",
    },
    "batch_metric_warning": {
        "zh-TW": "警告",
        "en-US": "Warning",
    },
    "batch_metric_error": {
        "zh-TW": "錯誤",
        "en-US": "Error",
    },
    "batch_download_zip_btn": {
        "zh-TW": "📦 下載全部報告 ZIP（Download All Reports ZIP）",
        "en-US": "📦 Download All Reports ZIP",
    },
    # Settings & Preferences
    "settings_caption": {
        "zh-TW": "自訂全域協定分析逾時、介面語系、視覺主題與資料載入上限。",
        "en-US": "Customize global protocol analysis timeout, UI locale, visual theme, and data load limits.",
    },
    "settings_i2c_timeout": {
        "zh-TW": "I2C 預設 Timeout (ms)",
        "en-US": "Default I2C Timeout (ms)",
    },
    "settings_i2c_timeout_help": {
        "zh-TW": "I2C / SMBus 交易超時判定門檻（毫秒）。",
        "en-US": "I2C / SMBus transaction timeout threshold in milliseconds.",
    },
    "settings_language_help": {
        "zh-TW": "系統介面顯示語言。",
        "en-US": "System UI display language.",
    },
    "settings_theme": {
        "zh-TW": "預設主題",
        "en-US": "Default Theme",
    },
    "settings_theme_help": {
        "zh-TW": "UI 外觀配色主題。",
        "en-US": "UI appearance color theme.",
    },
    "settings_max_rows": {
        "zh-TW": "分析資料列數上限",
        "en-US": "Max Analysis Data Rows",
    },
    "settings_max_rows_help": {
        "zh-TW": "單次匯入分析之最大 CSV / 交易資料列數限制。",
        "en-US": "Maximum row limit for a single CSV / transaction import.",
    },
    "settings_spi_page_size": {
        "zh-TW": "SPI 預設 Page Size",
        "en-US": "Default SPI Page Size",
    },
    "settings_spi_page_size_help": {
        "zh-TW": "SPI NOR Flash Page Program 預設緩衝區大小（位元組）。",
        "en-US": "Default SPI NOR Flash Page Program buffer size in bytes.",
    },
    "settings_reset_button": {
        "zh-TW": "重設為預設值",
        "en-US": "Reset to Defaults",
    },
    "settings_applied_toast": {
        "zh-TW": "設定已成功套用！",
        "en-US": "Settings applied successfully!",
    },
    "settings_reset_toast": {
        "zh-TW": "已重設為預設設定！",
        "en-US": "Reset to default settings!",
    },
    "settings_active_summary": {
        "zh-TW": "目前生效設定摘要",
        "en-US": "Active Settings Summary",
    },
    "settings_metric_i2c_timeout": {
        "zh-TW": "I2C Timeout",
        "en-US": "I2C Timeout",
    },
    "settings_metric_locale": {
        "zh-TW": "語言",
        "en-US": "Language",
    },
    "settings_metric_theme": {
        "zh-TW": "主題",
        "en-US": "Theme",
    },
    "settings_metric_max_rows": {
        "zh-TW": "資料上限",
        "en-US": "Data Limit",
    },
    "settings_metric_spi_page": {
        "zh-TW": "SPI Page",
        "en-US": "SPI Page",
    },
    # Protocol Diff (PCIe, MCTP, I2C, SPI, UART)
    "diff_metric_new_aer": {
        "zh-TW": "新增 AER 錯誤",
        "en-US": "New AER Errors",
    },
    "diff_metric_resolved_aer": {
        "zh-TW": "已解決 AER 錯誤",
        "en-US": "Resolved AER Errors",
    },
    "diff_metric_common_aer": {
        "zh-TW": "共同 AER 錯誤",
        "en-US": "Common AER Errors",
    },
    "diff_metric_link_degradation": {
        "zh-TW": "Link 降級",
        "en-US": "Link Degradation",
    },
    "diff_metric_new_errors": {
        "zh-TW": "新增錯誤",
        "en-US": "New Errors",
    },
    "diff_metric_resolved_errors": {
        "zh-TW": "已解決錯誤",
        "en-US": "Resolved Errors",
    },
    "diff_metric_common_errors": {
        "zh-TW": "共同錯誤",
        "en-US": "Common Errors",
    },
    "diff_metric_message_count_delta": {
        "zh-TW": "訊息數變化",
        "en-US": "Message Count Delta",
    },
    "diff_metric_new_anomalies": {
        "zh-TW": "新增異常",
        "en-US": "New Anomalies",
    },
    "diff_metric_resolved_anomalies": {
        "zh-TW": "已解決異常",
        "en-US": "Resolved Anomalies",
    },
    "diff_metric_common_anomalies": {
        "zh-TW": "共同異常",
        "en-US": "Common Anomalies",
    },
    "diff_metric_tx_count_delta": {
        "zh-TW": "交易數變化",
        "en-US": "Transaction Count Delta",
    },
    "diff_metric_new_symbols": {
        "zh-TW": "新增符號",
        "en-US": "New Symbols",
    },
    "diff_metric_resolved_symbols": {
        "zh-TW": "已解決符號",
        "en-US": "Resolved Symbols",
    },
    "diff_metric_common_symbols": {
        "zh-TW": "共同符號",
        "en-US": "Common Symbols",
    },
    "diff_metric_fault_address": {
        "zh-TW": "故障位址",
        "en-US": "Fault Address",
    },
    "diff_status_changed": {
        "zh-TW": "變更",
        "en-US": "Changed",
    },
    "diff_status_identical": {
        "zh-TW": "相同",
        "en-US": "Identical",
    },
    "diff_section_new": {
        "zh-TW": "新增項目（New）",
        "en-US": "New Items",
    },
    "diff_section_resolved": {
        "zh-TW": "已解決項目（Resolved）",
        "en-US": "Resolved Items",
    },
    "diff_section_common": {
        "zh-TW": "共同項目（Common）",
        "en-US": "Common Items",
    },
    "diff_section_address_changes": {
        "zh-TW": "位址變更（Address Changes）",
        "en-US": "Address Changes",
    },
    "diff_section_none": {
        "zh-TW": "無",
        "en-US": "None",
    },
    "diff_uploader_file_label": {
        "zh-TW": "上傳 {role} 檔案",
        "en-US": "Upload {role} file",
    },
    "diff_pasted_text_label": {
        "zh-TW": "或貼上內容",
        "en-US": "Or paste content",
    },
    "diff_summary_label": {
        "zh-TW": "分析摘要",
        "en-US": "Analysis Summary",
    },
}


def register_gui_domain(registry: TranslationRegistry) -> None:
    """將 GUI 介面詞條註冊至 registry 的 'gui' domain。"""
    registry.register_domain("gui", GUI_TRANSLATIONS)


__all__ = ["GUI_TRANSLATIONS", "register_gui_domain"]
