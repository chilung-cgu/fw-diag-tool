# 功能總覽與快速入門教學（Dashboard & Quick Start）

## 這個頁面在做什麼？

**Firmware Diagnostic Toolkit (fw-diag-tool)** 是一套專為韌體、嵌入式系統與伺服器 BMC 工程師打造的離線訊號、協定與崩潰轉儲診斷分析套件。在整合了 16 個強大的 GUI 頁面後，工程師需要一個中央控制台以宏觀掌握所有可用模組、理解工具的能力邊界，並依據眼前的故障現象快速定位最適合的診斷工具。

**功能總覽與快速入門（Dashboard）** 作為整個套件的首頁與導覽中樞，提供：

- **工具能力邊界聲明**：確立離線分析定位，避免將軟體解碼誤判為實體硬體控制。
- **3 步快速上手指引**：從資料擷取、模組切換到報告產生的標準作業路徑。
- **常見工作場景推薦**：依據硬韌體故障徵狀（如 I2C NACK、Kernel Panic、AER 錯誤等）引導至對應頁面。
- **四大功能模組卡片總覽**：統整協定分析、系統診斷、代碼產生與實驗學習等 16 大頁面之功能、支援格式與適用場景。

---

## 怎麼操作？

進入 GUI 側邊欄 **「總覽」** 區塊的 **「🏠 功能總覽與快速入門」** 頁面。

### 1. 閱讀工具能力邊界聲明

頁面頂部常駐標示工具邊界：
- 本工具主要分析已擷取的追蹤記錄（Trace）、日誌（Log）與暫存器傾印（Dump），**不會主動連線或控制實體硬體**。
- 圖表與診斷報告能有效縮小除錯範圍，但**無法取代示波器實體量測、晶片規格書（Datasheet）及目標板上的實體驗證**。

### 2. 展開快速入門與場景導覽

點擊展開 **「🚀 第一次使用？快速入門指引與場景導覽」**：

1. **3 步快速上手流程**：
   - **Step 1 準備擷取資料**：從邏輯分析儀（如 Saleae）、串列埠終端（如 minicom/picocom）或系統日誌（dmesg/lspci）匯出 CSV、TXT 或十六進位資料。
   - **Step 2 切換至對應功能頁面**：於左側導覽列選擇目標協定或工具。
   - **Step 3 載入資料並檢視報告**：直接上傳檔案、貼上文字，或點擊「載入範例」體驗自動化診斷與下載 Markdown 報告。
2. **依故障場景定位**：
   - I2C / PMBus 通訊失敗、NACK、時鐘延展或死鎖 -> 前往 **📊 I2C/PMBus 診斷** 或 **⚖️ 雙波形差分**。
   - 系統當機、Linux Kernel Panic 或 ARM HardFault -> 前往 **📟 UART Crash**。
   - 伺服器 BMC / IPMI / PLDM 封包分析與 Checksum 驗證 -> 前往 **🌐 MCTP/IPMB**。
   - PCIe 裝置無法識別、Link 降速或 AER 錯誤回報 -> 前往 **🚀 PCIe AER**。
   - Flash 讀寫異常、WREN 遺漏或 256B 跨頁覆蓋 -> 前往 **⚡ SPI Flash** 或 **🧪 虛擬設備模擬器**。
   - 撰寫 Linux 裝置樹、解析暫存器或產生 C 驅動巨集 -> 前往 **🌲 Device Tree**、**🎛 暫存器解碼** 或 **🛠 C Header 產生器**。
   - 新人培訓、故障模式排查練習或學習除錯方法論 -> 前往 **🏆 Fault Arena**、**📚 除錯 SOP**、**🔍 I2C 晶片資料庫** 或 **🎲 協定解析器 Fuzz 測試**。

### 3. 瀏覽四大模組卡片

下方以結構化卡片展示所有模組的詳細說明、支援格式與適用場景，點擊左側側邊欄即可隨時跳轉至目標功能。

---

## GUI 會顯示哪些輸出？

## Release history：累積歷史與使用方式

Dashboard 的「Release history」區塊讀取套件內建的 release-notes manifest，預設以三張卡片顯示最新版本（目前包含 `v1.7.0`）。這是方便快速掌握近期變更的摘要；三卡片不代表任何特定目標板卡已經收到或套用更新。

### 先看三張摘要卡片

每張卡片會顯示版本、日期、雙語摘要與 highlights。摘要卡片提供快速定位線索，不是即時更新狀態，也不是對硬體執行結果的證明。

### 展開完整累積歷史

若要查閱較舊版本，展開同一區塊的完整歷史控制項，從版本選單選取任一 manifest 版本。選取後會顯示該版本的摘要與 highlights；清單順序依語意版本由新到舊排列。

### 切換語系

使用側邊欄的全域語系選擇器，在 `zh-TW` 與 `en-US` 間切換。Release history 的標題、按鈕、摘要與 highlight 文字會跟隨目前語系；若翻譯欄位不可用，系統依序回退到繁體中文，再回退到英文。

### CTA 與文件路徑 caption

- Highlight 有對應 GUI 頁面時，卡片會提供 page CTA。點擊 CTA 只會開啟工具內已註冊的頁面，協助你載入資料並進行離線分析。
- 沒有 GUI 頁面、但有文件來源時，卡片會以純文字 caption 顯示文件路徑。這個路徑是查閱說明的索引，不是可執行連結，也不表示該功能已在目標系統部署。

Manifest 是隨套件封裝的本地 release metadata，不是會連線抓取新版本的 live update service。要確認最新版本或目標板卡的實際更新狀態，仍須查核正式發布紀錄、部署流程與板端證據。

若 manifest 遺失或格式驗證失敗，Release history 會顯示在地化的 unavailable 警告並停止該區塊渲染；Dashboard 其餘導覽、場景推薦與功能卡片仍可繼續使用。若 manifest 有效但沒有目前執行版本，則顯示版本提醒並繼續渲染可用的累積歷史。這些 fallback 只表示版本資料狀態，不代表目標板卡更新失敗。

頁面將整個套件的 16 大頁面劃分為四大核心模組群組，呈現完整的資訊架構：

### 16 大 GUI 頁面全功能對照總表

| 模組分類 | GUI 頁面名稱 | 支援輸入格式 | 核心功能與適用場景 | 對應教學章節 |
|---|---|---|---|---|
| **總覽** | 🏠 功能總覽與快速入門 | 無需輸入 | 套件全局架構導覽、快速上手指引與場景定位 | [ch16_dashboard.md](ch16_dashboard.md) |
| **協定分析與波形** | 📊 I2C / PMBus 診斷與波形檢視 | Saleae Decoded CSV、Raw Digital CSV (100k/400k)、Text Trace、.fwsession.json | I2C/SMBus/PMBus 通訊異常、NACK、時鐘延展、死鎖診斷 | [ch01_i2c_pmbus.md](ch01_i2c_pmbus.md) |
| **協定分析與波形** | 🎨 I2C 封包模擬器與驅動產生 | 自訂 7-bit 位址、暫存器位移、讀寫長度、Payload | 產生 i2ctransfer CLI 命令與 Linux Kernel i2c_msg / C 驅動範本 | [ch02_packet_builder.md](ch02_packet_builder.md) |
| **協定分析與波形** | ⚖️ 雙波形差分對比檢視 | 兩個 Saleae Decoded CSV（Golden vs Failing） | A/B 板卡比對、找出首次通訊分歧點（Timing、NACK 差異） | [ch03_waveform_diff.md](ch03_waveform_diff.md) |
| **進階分析** | 🔗 跨協定時間線關聯分析 | I2C CSV、SPI CSV、UART 日誌（多協定輸入） | 跨協定時間軸對齊、全域異常標記與異常叢集（Cluster）偵測 | [ch17_correlation.md](ch17_correlation.md) |
| **系統協定診斷** | 📟 UART 崩潰轉儲與 HardFault 分析 | 文字日誌 (.txt / .log)、Linux dmesg / Call Trace、ARM 暫存器傾印 | 解析 Kernel Panic / Oops / NULL Pointer 及 ARM Cortex-M HardFault | [ch04_uart_crash.md](ch04_uart_crash.md) |
| **系統協定診斷** | 🌐 MCTP／IPMB 伺服器管理協定解析 | 十六進位位元組字串 (Hex Bytes) | BMC 管理協定除錯、MCTP (DSP0236/PLDM/SPDM) 與 IPMB 兩段校驗 | [ch05_mctp_ipmb.md](ch05_mctp_ipmb.md) |
| **系統協定診斷** | 🚀 PCIe 設定空間與 AER 診斷 | lspci -xxxx / -vvv 傾印、Linux dmesg AER 錯誤日誌 | PCIe 裝置識別、Link 降速 (Gen4 -> Gen1)、Correctable/Fatal AER 診斷 | [ch07_pcie_aer.md](ch07_pcie_aer.md) |
| **系統協定診斷** | ⚡ SPI Flash 協定診斷 | 邏輯分析儀 SPI Decoded CSV (需含 Time, MOSI, MISO, CS) | SPI NOR Flash 讀寫異常、JEDEC ID 故障、WREN 遺漏、256B 跨頁回繞 | [ch08_spi_flash.md](ch08_spi_flash.md) |
| **產生器與硬體工具** | 🌲 Device Tree 產生器 | YAML 格式匯流排與拓撲定義 | Linux 系統移植與 BSP 開發、產生 OpenBMC / Linux I2C DTS 節點 | [ch06_dts_generator.md](ch06_dts_generator.md) |
| **產生器與硬體工具** | 🎛 暫存器 Bitfield 解碼器 | 十六進位暫存器數值、內建/自訂 YAML Register Map | 硬體狀態暫存器欄位即時拆解、PMBus / PCIe 錯誤暫存器查閱 | [ch09_register_codegen.md](ch09_register_codegen.md) |
| **產生器與硬體工具** | 🛠 C Register 巨集產生器 | YAML 暫存器與欄位定義檔 | 自動產生標準 C 語言 #define 位移、遮罩與讀改寫 (RMW) 巨集 | [ch09_register_codegen.md](ch09_register_codegen.md) |
| **實驗室與學習** | 🏆 初階 Firmware 實戰除錯實驗室 | 內建 20 個經典案例一鍵載入 | 初階工程師除錯實戰培訓（涵蓋 I2C、SPI、PCIe、UART、MCTP/IPMB） | [ch10_fault_arena.md](ch10_fault_arena.md) |
| **實驗室與學習** | 📚 韌體除錯指南與 SOP | 互動式知識庫（無需輸入） | 建立 L1 (物理) 到 L7 (應用) 分層除錯心智模型與證據詞彙框架 | [ch12_sop.md](ch12_sop.md) |
| **實驗室與學習** | 🔍 I2C 晶片資料庫瀏覽器 | 7-bit 位址或關鍵字 | 7-bit 位址反向查詢、0x00~0x7F 全空間熱力圖與資深工程師排查指引 | [ch13_chip_db.md](ch13_chip_db.md) |
| **實驗室與學習** | 🧪 虛擬設備模擬器實驗室 | 互動式模擬（無需硬體） | 模擬 LM75 溫度、W25Q128 Flash、24C64 EEPROM（Page Rollover / ACK Poll） | [ch14_emulator.md](ch14_emulator.md) |
| **實驗室與學習** | 🎲 協定解析器 Fuzz 測試 | 隨機種子與規模控制 | 對 5 大協定解析器進行 Robustness 壓力測試與未預期崩潰防禦評估 | [ch15_fuzz_lab.md](ch15_fuzz_lab.md) |

---

## 證據等級邊界（Evidence Level & Limitations）

本節同時是 Dashboard release history 的 **證據邊界（evidence boundary）**：累積歷史（cumulative history）只描述已封裝的版本資訊，不能取代目標硬體的量測、刷寫紀錄或驗證結果。

- **工作流程導航指引（Workflow Orientation Guide）**：Dashboard 本身為索引與導航工具，不代表對特定目標板卡之分析結果。
- **場景推薦為經驗規則**：推薦起始頁面是基於常見故障模式之最佳實踐，實際問題可能跨越多個層級（例如：UART 回報 Kernel Panic 可能是底層 I2C 電源軌電壓驟降所引發）。
- **遵循 L1 ~ L7 分層除錯心智模型**：任何軟體分析結論均應對照 [韌體除錯指南與 SOP](ch12_sop.md)，依序收集物理層（L1 示波器）、電氣/協定層（L2 邏輯分析儀）、驅動層（L4 dmesg）等證據進行交叉驗證。

---

## 實際場景範例

### 場景 1：新進工程師 3 分鐘快速上手

**情境**：剛加入團隊的 Junior 韌體工程師第一次使用 fw-diag-tool，面對眾多頁面不知從何著手。
**操作步驟**：
1. 進入首頁 Dashboard，展開「3 步快速上手流程」，理解資料準備與分析流程。
2. 在「常見工作場景推薦」中，點擊建議前往 **🏆 Fault Arena** 載入 Case 01（Address NACK）體驗自動化報告。
3. 切換至 **🧪 虛擬設備模擬器**，在純軟體環境中體驗 EEPROM 跨頁覆蓋與 SPI Flash WREN 機制，迅速建立底層硬體心智模型。

### 場景 2：伺服器開機無畫面之多模組聯合排查

**情境**：伺服器主機板開機無畫面（No Display / No Boot），工程師需要多維度定位問題。
**排查路徑**：
1. **檢視 UART 日誌**：從串列埠抓取開機 Log，放入 **📟 UART Crash** 分析，發現停在 PCIe 列舉階段。
2. **分析 PCIe 錯誤**：讀取 BMC 轉儲之 lspci -xxxx，放入 **🚀 PCIe AER** 診斷，發現 GPU 裝置發生 Malformed TLP (Fatal) 且 Link 降為 Gen1 x1。
3. **查核 I2C 電源狀態**：使用邏輯分析儀擷取 GPU VR 電源晶片通訊，放入 **📊 I2C/PMBus 診斷**，發現 VR 在開機瞬間觸發 VIN_UV_FAULT（輸入欠壓警報）。
4. **確認根因**：藉由 Dashboard 指引之三大模組串聯分析，迅速定位根本原因為電源供應模組欠壓，而非 GPU 晶片損壞。
