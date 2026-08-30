# Firmware Diagnostic Suite (`fw_diag_tool`)

專為 **Junior 韌體 / 嵌入式 / 硬體工程師** 設計的本機診斷與學習工具，目標平台為 macOS 與 Linux。
目前版本 **v1.4.0**，提供 I2C/PMBus、PCIe AER、SPI Flash、UART Crash Dump、MCTP/IPMB 五大協定分析，以及協定示意圖、全協定差分引擎（Diff Engine）、目錄級批次分析（Batch Analysis）、偏好設定（Settings）、無障礙輔助與 26 個 synthetic 練習情境。各模組的輸入能力與限制請先閱讀 [能力與限制](docs/LIMITATIONS.md)。

👉 **完整新人圖文教學指南**：請參閱 [docs/index.md](docs/index.md)；若不知道某個 GUI 頁面或圖表怎麼讀，先看 [26+ 個 GUI 頁面的閱讀地圖](docs/chapters/appendix_gui_reading_guide.md)。
> 📂 **各章節詳細文件**：[ch01 I2C波形](docs/chapters/ch01_i2c_pmbus.md) | [ch02 封包/驅動產生](docs/chapters/ch02_packet_builder.md) | [ch03 Waveform Diff](docs/chapters/ch03_waveform_diff.md) | [ch04 UART Crash](docs/chapters/ch04_uart_crash.md) | [ch05 MCTP/IPMB](docs/chapters/ch05_mctp_ipmb.md) | [ch06 Device Tree](docs/chapters/ch06_dts_generator.md) | [ch07 PCIe AER](docs/chapters/ch07_pcie_aer.md) | [ch08 SPI Flash](docs/chapters/ch08_spi_flash.md) | [ch09 Register/Codegen](docs/chapters/ch09_register_codegen.md) | [ch10 Fault Arena](docs/chapters/ch10_fault_arena.md) | [ch11 Board Profile](docs/chapters/ch11_board_profile.md) | [ch12 SOP](docs/chapters/ch12_sop.md) | [ch13 晶片資料庫](docs/chapters/ch13_chip_db.md) | [ch14 模擬器](docs/chapters/ch14_emulator.md) | [ch15 Fuzz Lab](docs/chapters/ch15_fuzz_lab.md) | [ch16 Dashboard](docs/chapters/ch16_dashboard.md) | [ch17 關聯分析](docs/chapters/ch17_correlation.md) | [ch18 Session 趨勢](docs/chapters/ch18_session_analytics.md) | [ch19 PDF 匯出](docs/chapters/ch19_pdf_export.md) | [ch20 協定 Diff](docs/chapters/ch20_protocol_diff.md) | [ch21 Session 比對](docs/chapters/ch21_session_compare.md) | [ch22 批次分析](docs/chapters/ch22_batch_analysis.md) | [ch23 偏好設定](docs/chapters/ch23_settings.md) | [附錄A 圖表判讀](docs/chapters/appendix_chart_guide.md)

**專案連結**：[Source](https://github.com/chilung-cgu/fw-diag-tool) | [Documentation](https://github.com/chilung-cgu/fw-diag-tool#readme) | [Issues](https://github.com/chilung-cgu/fw-diag-tool/issues) | [Changelog](https://github.com/chilung-cgu/fw-diag-tool/blob/main/CHANGELOG.md)

---

## ✨ v1.4.0 版本亮點（Highlights）

- **五大協定 Diff 引擎全面就緒**：擴展 PCIe Diff（AER 錯誤差分、Link 降級偵測、Vendor/Device 異動）與 MCTP/IPMB Diff（訊框計數 Delta、錯誤分類比對），與既有 I2C、SPI、UART 構成涵蓋 5 大核心協定的 A/B Trace 差分比對能力。
- **目錄級多檔案批次分析（Batch Analysis）**：支援一次上傳多個檔案或指定目錄，自動識別協定類型並平行診斷，產出匯總統計與一鍵下載 ZIP 報告包（含 Markdown、HTML、SARIF）。
- **視覺化偏好設定（Settings & Preferences GUI）**：提供 I2C Timeout、UI 語系（繁體中文 / 英文）、主題切換、表格資料列數上限、SPI Page Size 等全域即時配置。
- **無障礙體驗與導覽優化（Accessibility & Navigation）**：新增鍵盤無障礙 Skip-to-content 快速跳轉連結、全域搜尋（Ctrl+K / Cmd+K）、麵包屑導航與 26 大頁面流暢切換。
- **HTML/PDF 報告強化**：HTML 報告新增目錄錨點（TOC Anchor Slugs）、折疊式詳細區塊（Collapsible Details）與列印友善 CSS；支援全流程中英雙語 i18n。

---

## 🚀 快速啟動 Web 視覺化工作站

```bash
# 1. 先在 clone 出來的專案根目錄同步鎖定環境 (Python 3.10+)
uv sync --all-extras

# 2. 啟動 Web 視覺化工作站 (macOS / Linux 一鍵啟動)
uv run fw-diag gui
```
*(瀏覽器將自動開啟 `http://127.0.0.1:8501`，支援滑鼠滾輪縮放波形、檔案拖放與互動分析)*

若環境沒有 `uv`，可改用 Python 3.10+ 的內建虛擬環境與 pip：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
fw-diag gui
```

---

## 📊 GUI 功能矩陣（26 個頁面能力總覽）

| 頁面 | 分析 | 報告匯出 | Session | Diff | i18n |
|---|---|---|---|---|---|
| **I2C / PMBus 診斷** | ✅ | MD, HTML, SARIF, PDF, JSON | ✅ | ✅ | ✅ |
| **I2C 封包模擬器** | ✅ | C, C++, DTSI, CLI 腳本 | ✅ | ❌ | ✅ |
| **雙波形差分 (Waveform Diff)** | ✅ | MD | ✅ | ✅ | ✅ |
| **協定 A/B 對比 (Protocol Diff)** | ✅ | MD, ZIP | ❌ | ✅ | ✅ |
| **批次分析 (Batch Analysis)** | ✅ | MD, HTML, SARIF, ZIP | ❌ | ❌ | ✅ |
| **跨協定時間線關聯分析** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **多工作階段趨勢分析** | ✅ | MD, JSON | ✅ | ❌ | ✅ |
| **Session A/B 對比** | ✅ | MD, JSON | ✅ | ✅ | ✅ |
| **功能總覽與儀表板 (Dashboard)** | ✅ | MD, HTML, PDF, ZIP | ✅ | ❌ | ✅ |
| **UART 崩潰轉儲分析** | ✅ | MD, JSON | ✅ | ✅ | ✅ |
| **MCTP / IPMB 伺服器協定解析** | ✅ | MD, JSON | ✅ | ✅ | ✅ |
| **PCIe 設定與 AER 診斷** | ✅ | MD, SARIF, JSON | ✅ | ✅ | ✅ |
| **SPI Flash 協定診斷** | ✅ | MD, HTML, SARIF, PDF, JSON | ✅ | ✅ | ✅ |
| **偏好設定 (Settings)** | ❌ | ❌ | ✅ | ❌ | ✅ |
| **Board Profile 拓撲編輯器** | ✅ | YAML, JSON | ✅ | ✅ | ✅ |
| **Device Tree 產生器** | ✅ | DTS, DTSI | ❌ | ❌ | ✅ |
| **晶片暫存器 Bitfield 解碼器** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **C 語言暫存器巨集產生器** | ✅ | C Header (.h) | ❌ | ❌ | ✅ |
| **互動式教學導覽** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **實戰故障實驗室 (Fault Arena)** | ✅ | MD | ❌ | ❌ | ✅ |
| **韌體除錯指南與 SOP** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **I2C 晶片資料庫瀏覽器** | ✅ | ❌ | ❌ | ✅ | ✅ |
| **虛擬設備模擬器實驗室** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **協定解析器 Fuzz 實驗室** | ✅ | MD, JSON, ZIP | ✅ | ❌ | ✅ |
| **附錄 A 圖表與證據判讀指南** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **PDF 報告匯出模組** | ✅ | PDF | ❌ | ❌ | ✅ |

---

## 🌟 核心功能模組一覽

| 功能模組 | 協定 / 功能 | 核心特色與排查重點 |
|---|---|---|
| **1. I2C / PMBus 診斷與波形檢視** | I2C, SMBus, PMBus | Analyzer table 做協定診斷；Raw digital `Time/SCL/SDA` CSV 可量測 digital edge、tHIGH/tLOW 與頻率；兩者都明確標示證據限制。 |
| **2. I2C 封包模擬與驅動產生** | C/C++/CLI template generation | 輸入 Slave Addr 與暫存器即時「造波形」，並產出 Linux `i2c-dev` C、OpenBMC/Linux CLI、STM32 HAL C 與 Arduino/Wire C++ 模板。 |
| **3. 雙波形差分對比 (Waveform Diff)** | A/B 測試比對 | 逐筆比較 Golden 與 Failing 的已解碼交易，找出第一筆協定差異並繪製重建示意圖。 |
| **4. 協定 A/B 對比 (Protocol Diff)** | I2C, SPI, UART, PCIe, MCTP | 全面擴展 5 大協定 A/B Trace 比對，精確計算 KPI 指標差異、異常演變與分歧點排查提示。 |
| **5. UART Crash & HardFault 分析** | Linux Panic, ARM Cortex-M | 自動拆解 Kernel Panic (RIP/CR2/Call Trace) 與 ARM HardFault (HFSR/CFSR/DIVBYZERO/UNALIGNED)。 |
| **6. MCTP / IPMB 伺服器協定解析** | MCTP, PLDM, SPDM, IPMB | 解析基本 MCTP/IPMB header 與 checksum，並辨識目前已支援的 PLDM/SPDM message type；尚非完整 conformance decoder。 |
| **7. PCIe Config & AER 診斷** | PCIe Config, AER | 解析目前支援的 Config Space、Capability、AER 與 Link 資訊；不分析 PCIe 高速電氣波形或 LTSSM。 |
| **8. SPI Flash 協定診斷** | SPI NOR Flash | 解析已解碼的 SPI CSV、JEDEC opcode 與基本 WREN/erase/program 序列，並列出可能異常原因；輸入格式與 CS/response 證據不足會明示限制。 |
| **9. 晶片暫存器 Bitfield 解碼器** | Hardware Registers | 支援 PMBus / PCIe 定義，輸入 Raw Hex 即時展開 Bit 欄位與異常警報。 |
| **10. C 語言 Register 巨集產生器** | MISRA-oriented CodeGen | 從 YAML 產出 Position、Mask 與 `REG_..._GET` / `REG_..._SET` 巨集；仍須依專案 compiler、coding standard 與靜態分析器驗證。 |
| **11. 26 大實戰故障實驗室 (Fault Arena)** | Junior FW 演練 | 內建 26 個 synthetic 故障情境，用來練習從症狀建立假設與排查順序；不是實際公司 capture。 |
| **12. 韌體除錯指南 & SOP** | L1~L7 心智模型 | 整合硬體電氣訊號、協定層封包與驅動狀態機之標準排查 SOP。 |
| **13. Board Profile 拓撲編輯器** | YAML / JSON topology | 表單式拓撲定義、I2C 位址衝突偵測、保留位址警告、MUX/匯流排/晶片視覺化配置。 |
| **14. 互動式教學導覽** | Step-by-step Guided | 3 學習路徑（入門/已有經驗/進階）、6 步互動教學、進度追蹤。 |
| **15. 跨協定時間線關聯分析** | I2C + SPI + UART | 多協定時間線對齊、Plotly 暗色主題圖表、跨協定異常叢集偵測。 |
| **16. 目錄級批次分析 (Batch Analysis)** | All protocols | 自動辨識目錄下所有 trace/log 協定類型，平行執行診斷並一鍵打包匯出 ZIP。 |
| **17. 虛擬設備模擬器** | INA219, PCA9548A, LM75, EEPROM, SPI Flash | 模擬常見韌體開發設備，附 GUI 互動實驗分頁。 |
| **18. 視覺化偏好設定 (Settings)** | User Preferences | 即時調整 I2C Timeout、UI 語言、主題風格、表格列數上限與 SPI Page Size。 |
| **19. 無障礙與鍵盤快速鍵** | Accessibility | 支援 Skip-to-content 快速跳轉、Ctrl+K / Cmd+K 全域搜尋、Ctrl+/ 側邊欄切換。 |

---

## 🛠 常用 CLI 命令列指令速查（全協定支援）

```bash
# 1. I2C / PMBus 協定診斷與差分比對
fw-diag i2c analyze examples/data/i2c_golden.csv --md i2c_report.md
fw-diag i2c diff examples/data/i2c_golden.csv examples/data/i2c_failing_nack.csv

# 1b. I2C 實測 Raw Digital 波形診斷（Time/SCL/SDA 數位邊緣量測）
fw-diag i2c analyze capture_raw.csv --raw-digital --md raw_i2c_report.md

# 2. SPI Flash 協定診斷與差分比對
fw-diag spi analyze examples/data/spi_w25q128_sample.csv --md spi_report.md
fw-diag spi diff examples/data/spi_baseline.csv examples/data/spi_candidate.csv

# 3. UART Serial Crash Dump 診斷與差分比對 (Linux Panic / ARM HardFault)
fw-diag uart analyze examples/data/kernel_panic_nvme.log --md crash_report.md
fw-diag uart analyze examples/data/arm_hardfault_stm32.log
fw-diag uart diff examples/data/panic_v1.log examples/data/panic_v2.log

# 4. MCTP / IPMB 伺服器管理協定解析與差分比對
fw-diag mctp analyze examples/data/mctp_pldm_sample.hex
fw-diag mctp diff examples/data/mctp_baseline.hex examples/data/mctp_candidate.hex

# 5. PCIe Config Space、AER 錯誤與差分比對 (支援 Link 降級與 4DW TLP 拆解)
fw-diag pcie analyze examples/data/pcie_aer_lspci.txt --md pcie_report.md
fw-diag pcie diff examples/data/pcie_gen4.txt examples/data/pcie_degraded.txt

# 6. 目錄級多檔案批次平行分析（自動偵測協定、匯出多格式報告）
fw-diag batch /path/to/captures/ -o ./batch_reports/ --format all

# 7. 診斷工作階段比對（Session A/B Compare）
fw-diag compare session_golden.fwsession.json session_target.fwsession.json

# 8. 硬體與晶片暫存器 Bitfield 解碼
fw-diag reg decode 0x1878 --protocol pmbus --cmd STATUS_WORD

# 9. 自動產出 Linux Device Tree (.dts) 原始碼
fw-diag gen dts --bus 1 --mux 0x70 --out i2c_bus1.dtsi

# 10. 產生 C 語言暫存器標頭檔與 RMW 巨集
fw-diag gen c-header src/fw_diag_tool/data/pmbus_standard.yaml --out pmbus_regs.h --name PMBUS_REGS

# 11. 執行協定解析器 Fuzzing 穩健性壓力測試
fw-diag fuzz --seeds 50

# 12. 環境健康檢查與系統資訊
fw-diag doctor
fw-diag check
fw-diag info
```

---

## 🧪 測試與代碼品質驗證

執行目前的單元與整合測試；精確數量以當次輸出為準：

```bash
# 執行完整測試套件
uv run pytest -v

# 執行程式碼排版與靜態語法檢查
uv run ruff check .

# 執行型別檢查
uv run mypy src/

# 執行文件建置檢查
uv run mkdocs build --strict
```
