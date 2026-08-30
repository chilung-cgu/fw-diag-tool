# I2C / SMBus / PMBus 晶片資料庫瀏覽器（Chip Database Browser）

## 這個頁面在做什麼？

在韌體開發與硬體除錯過程中，工程師常透過 `i2cdetect` 或邏輯分析儀掃描 I2C 匯流排，但僅能取得 `0x50`、`0x48` 或 `0x58` 等 7-bit 十六進位位址。要確認該位址對應哪一顆晶片、是否為規範保留位址、是否存在多裝置位址衝突，通常需要反覆翻閱數十份晶片規格書（Datasheet）。

**I2C 晶片資料庫瀏覽器（Chip Database Browser）** 提供整合式的離線週邊晶片目錄、7-bit 位址反向查詢、0x00 ~ 0x7F 全定址空間分佈地圖，以及資深韌體工程師的實戰排查指南。本頁面專門解決以下痛點：

- 快速將 I2C 掃描位址反向對應至具體晶片型號（如 EEPROM、溫度感測器、電源監控晶片、PMBus VR、GPIO 擴展器等）。
- 自動換算 7-bit 位址與 8-bit Read/Write 位址，避免驅動程式位移錯誤。
- 診斷多個裝置掛載於同一匯流排上的位址衝突風險（Address Conflict）。
- 標示 I2C / SMBus 規範中的特殊保留位址（如 General Call、CBUS、High-Speed Master Code、10-bit 前綴、SMBus ARA）。

---

## 怎麼操作？

進入 GUI 側邊欄 **「實驗室與學習」** 區塊的 **「🔍 I2C 晶片資料庫瀏覽器」** 頁面。該頁面由四大功能區塊組成：

### 1. 完整晶片目錄清單（Chip Catalog）

1. **關鍵字搜尋**：在「搜尋晶片」文字框中輸入晶片型號、功能關鍵字或位址（例如 `EEPROM`、`LM75`、`INA219`、`0x50`、`PMBus`）。
2. **多條件篩選**：
   - **設備類別（Category）**：可勾選 EEPROM / Memory、Temperature Sensor、Power Monitor、PMBus Power Management、GPIO Expander、Real-Time Clock (RTC)、I2C Switch / Mux 等。
   - **通訊協定（Protocol）**：可篩選 I2C、SMBus、PMBus、EEPROM 等協定。
3. **檢視清單**：下方表格即時呈現匹配晶片的型號、類別、協定、典型通訊速度（如 100 kHz、400 kHz、1000 kHz）、7-bit 位址範圍、預設暫存器位移長度與功能說明。

### 2. 7-bit I2C 位址反向查詢與衝突診斷（Address Lookup）

1. 在輸入框中輸入欲查詢的 7-bit 位址（支援 `0x50`、`0x48` 等十六進位或十進位整數 `80`）。
2. 系統即時顯示四項關鍵指標：
   - **7-bit 位址**（例如 `0x50 (80)`）
   - **8-bit 寫入位址（Write）**（例如 `0xA0`，即 `addr << 1`）
   - **8-bit 讀取位址（Read）**（例如 `0xA1`，即 `(addr << 1) | 1`）
   - **匹配已知晶片數**
3. 若位址對應多款晶片，系統會跳出黃色衝突警報並列出所有匹配晶片的詳細參數與暫存器定義。

### 3. 0x00 ~ 0x7F 全位址空間分佈地圖（Address Map）

- 檢視 8x16 二維互動式熱力圖：橫軸為低 4 位元（`+0x0` ~ `+0xF`），縱軸為高 3 位元（`0x00` ~ `0x70`）。
- 滑鼠懸停於任一方格上方，可即時檢視該位址的十進位數值、類別狀態、匹配晶片名稱與規範保留說明。
- 展開下方圖例可對照各設備類別的色彩配置。

### 4. 晶片詳情規格卡片與韌體工程實戰指南

1. 從下拉選單選擇特定晶片型號（如 `AT24Cxx / 24LCxx EEPROM`、`LM75 / TMP75`、`INA219 / INA226` 等）。
2. 檢視左側基礎規格與右側暫存器參數表（Extra Info）。
3. 閱讀下方「資深韌體工程師實戰指引」，掌握該晶片的底層陷阱（如 Page Rollover、ACK Polling、二補數換算、BANK 分頁等）。

---

## GUI 會顯示哪些輸出？

頁面固定呈現四大區段的輸出資訊：

| 畫面區段 | 顯示內容 | 正確讀法與重點 |
|---|---|---|
| 晶片目錄表格（Catalog Table） | 晶片型號、類別、協定、速度、位址範圍、暫存器位移、規格說明 | 快速確認週邊晶片之預設通訊參數與支援頻率 |
| 位址轉換與衝突指示（Address Lookup Metrics） | 7-bit / 8-bit 讀寫位址、衝突警告橫幅、匹配晶片清單展開器 | 確保驅動程式位址設定正確，評估同一 Bus 上的硬體定址衝突 |
| 8x16 位址空間分佈地圖（Address Map） | 128 個 7-bit 位址的分類著色熱力圖、統計指標（保留/涵蓋/衝突位址數） | 宏觀審視系統 I2C 架構佈局，避開保留區與高密度衝突區 |
| 晶片規格與實戰指引（Specifications & Insights） | 暫存器參數表格（如 page_size_bytes、write_cycle_ms）、排查要點 | 針對具體晶片掌握韌體驅動撰寫細節與邊界保護 |

### 7-bit vs 8-bit 位址換算速查

在 Linux 驅動或 Arduino/OpenBMC 中，I2C API 均要求傳入 7-bit 位址（`0x00` ~ `0x7F`）；但在邏輯分析儀波形、8051 或部分 MCU 暫存器中，則常看到 8-bit 位址。換算關係如下：

- **7-bit 位址**：`A6 A5 A4 A3 A2 A1 A0`（例如 `0x50`，二進位 `1010000`）
- **8-bit 寫入位址 (Write)**：`(0x50 << 1) | 0 = 0xA0`（二進位 `10100000`）
- **8-bit 讀取位址 (Read)**：`(0x50 << 1) | 1 = 0xA1`（二進位 `10100001`）

### 標準 I2C 規範保留位址

| 7-bit 位址 | 規範定義用途 | 韌體工程注意事項 |
|---|---|---|
| `0x00` | General Call（廣播呼叫）/ START Byte | 廣播位址；發送 `0x00 0x06` 可觸發相容晶片執行軟體重置（Software Reset） |
| `0x01` | CBUS 相容模式（CBUS Compatibility） | 保留給舊式 CBUS 協定，一般 I2C 裝置嚴禁使用 |
| `0x02` ~ `0x03` | 保留給不同匯流排格式與未來擴充 | 保留位址，不可指派給從屬裝置 |
| `0x04` ~ `0x07` | 高速主控碼（High-Speed Master Code 0000 1XX） | 主控端用於切換至 3.4 MHz 高速模式（Hs-mode）的代碼 |
| `0x0C` | SMBus Alert Response Address (ARA) | 共享中斷線（SMBALERT#）之硬體仲裁回應位址 |
| `0x78` ~ `0x7B` | 10-bit 從屬定址前綴碼（1111 0XX） | 用於 10-bit 定址模式的第一個位元組 |
| `0x7C` ~ `0x7F` | 裝置識別碼 / 保留供未來擴充（1111 1XX） | 用於讀取 Device ID 或保留擴充，自定義裝置不可佔用 |

### 常見晶片底層特性與除錯要點摘要

1. **AT24Cxx 系列 EEPROM**：
   - **Page Rollover**：單次連續寫入不可跨越 Page 邊界（24C02 為 8/16B，24C64 為 32B，24C256 為 64B），否則超出部分會回繞覆蓋該頁開頭。
   - **tWR 寫入週期**：內部快閃抹寫需約 5.0 ms，期間發送 I2C 請求會收到 NACK；應使用 ACK Polling 代替死等 `sleep(5ms)`。
2. **LM75 / TMP75 溫度感測器**：
   - **暫存器指針**：只有 1 個 Pointer Register；讀取前需先 Write 1 Byte 設定指針（`0x00` 為 TEMP，`0x01` 為 CONFIG）。
   - **12-bit 解析度**：溫度換算公式為 `(raw >> 4) * 0.0625 °C`，最高位為符號位（二補數）。
   - **Hysteresis 遲滯**：TOS 預設 80 °C 觸發警報，需降至 THYST（75 °C）以下才解除。
3. **INA219 / INA226 電流/功率監控**：
   - **校準暫存器**：必須先依分流電阻（Shunt Resistor）數值寫入 Calibration 暫存器（`0x05`），晶片內部才會自動計算電流與功率。
4. **PCF8574 GPIO 擴展器**：
   - **無暫存器位移**：直接對 I2C 位址寫入 1 Byte 即更新輸出，讀取 1 Byte 即獲取輸入。
   - **準雙向（Quasi-bidirectional）**：欲作為輸入腳位時，必須先對該 bit 寫入 1（High-Z 弱上拉）。
5. **MCP23017 GPIO 擴展器**：
   - **IOCON.BANK 陷阱**：BANK=0 時 Port A 與 Port B 暫存器交錯排列；BANK=1 時分為兩組獨立區塊。若驅動與晶片設定不一致將導致暫存器位移全部錯位。
6. **PCA9548A I2C 多工器（Mux）**：
   - **衝突隔離**：當匯流排有多顆相同位址晶片時，透過 Mux 將其分佈於不同下游 Channel（寫入 1 Byte 控制字元切換通道）。

---

## 證據等級邊界（Evidence Level & Limitations）

使用本資料庫與查詢工具時，請理解其資訊來源與驗證邊界：

- **靜態規格資料庫（Specification / Catalog Reference）**：資料庫收錄的晶片資訊為常見晶片規格書之典型定義，非目標板卡的動態讀取結果。
- **不能直接證明實體硬體型號**：當反向查詢 `0x50` 顯示 `AT24Cxx EEPROM` 與 `DDC EDID` 時，不代表實體電路板上必定是這兩款晶片之一，亦可能是特殊 ASIC 或掛載於該位址的其他自定義元件。
- **不能證明電氣特性正常**：資料庫顯示晶片支援 400 kHz，不保證實體電路板上的 Pull-up 電阻、線路負載電容或訊號完整性（SI）能穩定運行於 400 kHz。
- **衝突警報為靜態邏輯判斷**：若板卡上透過 PCA9548A 等多工器或不同實體 I2C Channel 分流，相同的 7-bit 位址在不同子通道上並存屬於合法架構，不會引發實體衝突。

---

## 實際場景範例

### 場景 1：I2C 匯流排位址衝突排查

**現象**：主機板上同時掛載了一顆系統設定 EEPROM（位址 `0x50`）與一組 HDMI 介面的 DDC EDID EEPROM（位址固定為 `0x50`），開機時 I2C 讀取偶發性出現資料校驗錯誤與 ACK 混亂。  
**排查與處置**：
1. 在資料庫瀏覽器中查詢 `0x50`，系統提示「偵測到位址衝突風險」，同時匹配 `AT24Cxx / 24LCxx EEPROM` 與 `DDC / EDID Display EEPROM`。
2. 檢查硬體原理圖，確認兩顆晶片掛在同一個 I2C Controller 下。
3. 處置方案：將 EEPROM 的硬體位址腳位 A0 接高電位（VCC），將 EEPROM 位址變更為 `0x51`；或在兩者之間加入 PCA9548A Mux 進行通道隔離。

### 場景 2：8-bit 位址誤填導致 I2C NACK

**現象**：Junior 工程師撰寫 Linux I2C 驅動時，參考晶片 Datasheet 首頁標示「Slave Address: 0x90 (Write) / 0x91 (Read)」，在 Device Tree 中填入 `reg = <0x90>;`，結果核心載入時出現 `i2c transfer failed: -ENXIO (No such device or address)`。  
**排查與處置**：
1. 在本頁面輸入 `0x90`，工具立即提示錯誤：`7-bit I2C 位址範圍必須介於 0x00 至 0x7F 之間；若輸入的是 8-bit 位址含 R/W bit，右移 1 位元後為 0x48`。
2. 工程師將 Device Tree 的 `reg` 修正為 `0x48`，驅動程式隨即順利 Probe 並完成通訊。

