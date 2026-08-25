# I2C / SMBus / PMBus 協定分析與數位波形檢視

## 1. 本章導讀與學習目標

I2C（Inter-Integrated Circuit）及其衍生協定 SMBus、PMBus 是現代伺服器、BMC（Baseboard Management Controller）與嵌入式主機板上最重要的通訊匯流排，負責連接 EEPROM、溫度感測器、電壓監控 IC、電源供應器（PSU）與 GPIO 擴充晶片。

當通訊發生錯誤時，軟體層往往只能拿到模糊的作業系統錯誤碼（如 Linux 的 `-EIO` 或 `-ETIMEDOUT`），無法直接得知問題發生在 Master 發送位址、Slave 內部忙碌回傳 NACK、SCL 被拉低延展（Clock Stretching）、抑或是匯流排被未知的雜訊鎖死。

本頁面 **「📊 I2C / SMBus / PMBus 診斷與波形檢視」** 是專為軟韌體工程師打造的協定分析工作站：
- **新手工程師**：可透過互動式數位波形與協定軌道，直觀建立 START、7-bit Address、R/W 方向、ACK/NACK、Data Byte、STOP 條件在微秒（µs）時間軸上的心智模型。
- **資深工程師**：可匯入邏輯分析儀（Logic Analyzer）或文字 trace，一鍵進行異常診斷（NACK 判別、SMBus 25ms 逾時、EEPROM 跨頁覆蓋、MUX 通道衝突）、設備健康評等與產生標準化 Markdown 診斷報告。

> **核心證據原則（重要）：**
> 
> 分析前請先分清資料來源：
> 1. **Decoded Table（解碼表格）**：包含已由 Analyzer 解出的 Address/Data/ACK，用於重建「協定示意波形」與執行語意分析；**不能**用來證明實測類比電壓、訊號上升時間（Rise Time）或線路雜訊。
> 2. **Raw Digital Transition（實測數位邊緣）**：每列包含精確微秒時間與 SCL/SDA 的 0/1 狀態，工具會自行解碼並計算「實測時脈頻率（kHz）」與「時鐘延展時間」。
> 完整邊界說明請參閱 [能力與限制](../LIMITATIONS.md)。

---

## 2. 支援的輸入資料格式與範例檔案

為方便快速上手與工作比對，專案在 `examples/data/` 目錄下提供了多種格式的標準範例檔案：

### 格式 1：Analyzer Decoded CSV (Aggregate / Per-Byte)
邏輯分析儀（如 Saleae Logic）匯出的解碼表格。

- **檔案 1：`examples/data/i2c_golden.csv`（Aggregate Decoded 範例）**
  每列為一筆完整交易，包含單一總結 ACK/NACK：
  ```csv
  Time,Packet ID,Address,Read/Write,Data,ACK/NACK
  0.001000,0,0x70,Write,0x04,ACK
  0.002000,1,0x50,Write,0x00 0x10,ACK
  0.003000,2,0x50,Read,0xAA 0xBB 0xCC 0xDD,ACK
  0.004000,3,0x48,Write,0x00,ACK
  0.005000,4,0x48,Read,0x19 0x00,ACK
  ```

- **檔案 2：`examples/data/i2c_split_decoded.csv`（Per-Byte Decoded 範例）**
  每列為單一 Byte（Address Byte 或 Data Byte），包含各 Byte 獨立的 ACK/NACK：
  ```csv
  Time,Packet ID,Address,Read/Write,Data,ACK/NACK
  0.001000,0,0x70,Write,,ACK
  0.002000,0,,Write,0x02,ACK
  0.003000,1,0x48,Write,,ACK
  0.004000,1,,Write,0x00,ACK
  0.005000,2,0x48,Read,,ACK
  0.006000,2,,Read,0x19,ACK
  0.007000,2,,Read,0x80,NACK
  ```

### 格式 2：Raw Digital Transition CSV (Time, SCL, SDA)
邏輯分析儀擷取的原始數位方波邊緣（0 與 1 切換）。

- **檔案 3：`examples/data/i2c_raw_100khz.csv`（100 kHz 實測數位波形）**
  ```csv
  Time [s],SCL,SDA
  0.000000,1,1
  0.000005,1,0
  0.000010,0,0
  0.000011,0,1
  0.000015,1,1
  ```
  - 時間單位為秒（嚴格遞增）。
  - SCL 與 SDA 僅能為 `0` 或 `1`。
  - 同一微秒時間點不可同時切換 SCL 與 SDA（符合物理取樣原則）。

### 格式 3：Saleae Text Trace
- **檔案 4：`examples/data/i2c_text_trace.log`**
  ```text
  [0.001000] S 0x48 W A 0x00 A P
  [0.002000] S 0x48 R A 0x19 A 0x80 N P
  ```

### 選填擴充：Board Profile (YAML)
- **檔案 5：`examples/data/board_yv4.yaml`**
  包含硬體主機板的 I2C 拓撲定義（如 PCA9548A MUX 通道、PMBus 電壓調節器位址），貼入頁面的 Board Profile 展開區即可啟用自訂裝置名稱與 PMBus 語意解析。

---

## 3. Step-by-Step 實戰導引：匯入 `i2c_golden.csv`

請跟著以下步驟在 GUI 進行第一次操作與觀察：

```
[步驟 1] 進入第 1 頁 -> [步驟 2] 點擊「載入內建測試波形」 -> [步驟 3] 檢視頂部 KPI 與資料限制 -> [步驟 4] 依序瀏覽 5 大分頁
```

### 步驟 1：確認輸入模式
1. 開啟 GUI，在左側選單選擇 **「📊 I2C / PMBus 診斷與波形檢視」**。
2. 確認 **輸入資料型態** 單選按鈕為 `Saleae Analyzer table / text trace`。

### 步驟 2：載入資料
點擊右側按鈕 **「載入內建測試波形」**（或上傳 `examples/data/i2c_golden.csv`）。

### 步驟 3：觀察頂部 4 大 KPI 卡片

| KPI 項目 | 畫面顯示數值 | 深度原理解析與觀察重點 |
|---|---|---|
| **總傳輸次數** | `5` | 工具成功自 CSV 重建出 5 筆獨立的 I2C Transaction（ID #1 ~ #5）。 |
| **異常事件數** | `0`（綠色） | 未命中目前支援的時序或協定異常規則（如無 Address NACK、無逾時等）。 |
| **平均時鐘頻率** | `不可用` (Unavailable) | **為什麼不是 100 kHz？** 因為 `i2c_golden.csv` 是 Analyzer 匯出的摘要表格，每筆交易只有一個開始時間戳記，沒有每個 bit/byte 的實際 duration 或 SCL edge。本工具遵循嚴格的證據契約：**沒有實測資料就不臆測數值**，不假裝測到了時脈。 |
| **時鐘抖動 (Jitter)** | `不可用` (Unavailable) | 缺乏時脈樣本時，絕不顯示 `0%` 這種易引發誤解的假數據。 |

### 步驟 4：觀察「⚠ 資料證據與限制」面板
若輸入資料並非完整實測波形，頂部會出現警示展開面板：
- `I2C_ACK_AGGREGATE_UNATTRIBUTABLE`：一列包含多個 Byte 但僅有一個總結 ACK。工具會安全地將各 Byte 的 ACK 保留為未知，避免將未確認的 Payload 貿然視為有效命令。
- `I2C_TIMING_UNAVAILABLE`：提示當前檔案未提供 SCL edge 或 bitrate，若需量測頻率請改用 Raw Digital CSV。

---

## 4. 五大功能區塊（Tabs）深度教學與輸出理解

在 KPI 卡片下方，工具將分析結果拆解為 5 大專用分頁，以下逐一教您如何閱讀與操作：

### 4.1 📈 數位方波與協定軌 (Waveform)

**功能定位**：直觀呈現 SCL 時鐘、SDA 資料方波，並在最上方疊加彩色協定解碼軌道。

```
┌─────────────────────────────────────────────────────────────┐
│ [Protocol Track]  START | 0x50 (W) | ACK | Reg:0x00 | ACK  │
├─────────────────────────────────────────────────────────────┤
│ [SDA Line]        ¯¯¯_______________/¯¯¯¯¯_______________ │
├─────────────────────────────────────────────────────────────┤
│ [SCL Line]        _/_/_/_/_/_/_/_/_/_/_/_/_/_  │
└─────────────────────────────────────────────────────────────┘
```

- **操作方式**：
  1. 透過下拉選單 **「選擇要檢視波形的交易」**，可切換 Tx #1 到 #5。
  2. 支援 Plotly 互動式操作：可用滑鼠滾輪放大（Zoom In）、拖曳平移（Pan）、雙擊重設視圖。
  3. 將滑鼠游標懸停在上方彩色方塊上，會彈出 Tooltip 顯示該階段的起始時間、持續微秒與詳細二進位數值（如 `Byte: 0x50 (binary: 01010000)`）。
- **色彩與協定標籤對照**：
  - 🟢 **START / Sr**（翡翠綠）：起始條件（SCL 為 High 時 SDA 產生下降邊緣）。
  - 🔵 **ADDRESS**（電光藍）：7-bit Slave 位址加上 1-bit R/W 方向（如 `0x50 (W)` 或 `0x48 (R)`）。
  - 🟢 **ACK**（春綠色）：第 9 個時脈週期 SDA 為 Low，表示接收端確認接收。
  - 🔴 **NACK**（珊瑚紅）：第 9 個時脈週期 SDA 為 High，表示未確認（或 Read 正常終止）。
  - 🟣 **DATA / Reg**（皇家紫）：傳輸的資料 Byte 或暫存器位移（Register Offset）。
  - 🟠 **STRETCH**（琥珀橘）：Slave 拉低 SCL 進行時脈延展。
  - 🌸 **STOP**（亮粉紅）：停止條件（SCL 為 High 時 SDA 產生上升邊緣）。
- **資深判讀技巧**：
  - 在 Decoded CSV 模式下，圖形上方會提示 **「Reconstructed」**（協定重建波形，以標準 100 kHz 示意時序繪製）；若切換為 Raw Digital CSV，則會顯示 **「Measured Raw Digital」**（真正來自邏輯分析儀取樣的 0/1 邊緣）。

---

### 4.2 🚨 異常診斷 (Anomalies)

**功能定位**：自動比對嵌入式與伺服器常見的 I2C/SMBus 硬韌體故障模式，提供具體的原因假說與排查清單。

- **正常狀態**：若無異常，顯示 `🎉 未偵測到任何 I2C/SMBus 時序與通訊異常！`。
- **異常狀態（以故障檔案為例）**：當匯入包含異常的檔案（如 `examples/data/i2c_failing_nack.csv`）時，會展開詳細的診斷卡片：
  1. **嚴重度與代碼**：如 `[ERROR] #1: I2C_DATA_NACK - Slave Data NACK on 0x50`。
  2. **現象描述 (Description)**：清楚說明在哪一筆交易、哪一個 Byte 發生未預期的 NACK。
  3. **可能原因假說 (Hypotheses)**：
     - *假設 1*：EEPROM 正在進行內部 Page Write Cycle（tWR 典型需 5~10ms），內部狀態機忙碌中拒絕寫入。
     - *假設 2*：寫入超出晶片合法暫存器範圍。
  4. **排查行動清單 (Actionable Advice)**：
     - ✔ 在寫入下一筆資料前，加入 Acknowledge Polling 檢查。
     - ✔ 使用示波器量測晶片 VDD 電源是否在寫入瞬間產生 Voltage Dip。

---

### 4.3 📊 匯流排時序與健康圖表 (Timing & Health Charts)

**功能定位**：從統計與巨觀角度評估匯流排負載與各 Slave 設備的通訊健康度。

包含三大核心視覺化：

1. **匯流排物理層健康評等表 (Device Health Grade Table)**：
   - 彙整所有出現的 Slave 位址（如 `0x70`、`0x50`、`0x48`）。
   - 計算各設備的 `Total Transactions`、`NACK Count` 與 `Success Rate`。
   - 給出健康等級評等：
     - **Grade A**：成功率 100%，無異常 Stretch。
     - **Grade B**：成功率 ≥ 95% 或存在輕微重試/延展。
     - **Grade D**：成功率 50%~80%，存在高頻率 NACK。
     - **Grade F**：成功率 < 50% 或 Clock Stretch ≥ 5 次，代表嚴重故障。
2. **時脈頻率分佈直方圖 (SCL Clock Frequency Distribution)**：
   - 統計匯流排所有 Byte 的 SCL 頻率分佈（kHz）。
   - 當資料提供可靠 timing 時，可觀察頻率是否集中在 100 kHz 或 400 kHz，以及時鐘抖動率（Jitter %）。
3. **匯流排交易時間軸與設備地圖 (Bus Transaction Timeline & Active Device Map)**：
   - X 軸為時間軸（秒），Y 軸為被存取的 Slave 設備名稱/位址。
   - 圓點顏色代表交易狀態（綠色 ACK、紅色 ADDR NAK、橘色 DATA NAK、藍色 READ END NAK、灰色 ACK UNKNOWN）。
   - 圓點大小代表該筆交易佔用匯流排的持續時間（Duration）。
   - 可一眼看出是否有頻繁存取特定裝置、連續 Retry 或通訊斷續現象。

---

### 4.4 📜 封包交易列表 (Packet Transaction Table)

**功能定位**：結構化的資料表格，提供所有交易的完整二進位與語意解讀。

在匯入 `i2c_golden.csv` 後，表格呈現如下 5 筆交易：

| ID | Time (s) | Address | Direction | ACK | Topology | Bytes | Data | Semantic Meaning |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.001000 | 0x70 | WRITE | NONE | - | 1 | [0x04] | I2C MUX 0x70 Channel Switch -> [2] |
| 2 | 0.002000 | 0x50 | WRITE | NONE | - | 2 | [0x00, 0x10] | EEPROM write pointer / offset |
| 3 | 0.003000 | 0x50 | READ | NONE | - | 4 | [0xAA, 0xBB, 0xCC, 0xDD] | EEPROM Data Readback |
| 4 | 0.004000 | 0x48 | WRITE | NONE | - | 1 | [0x00] | LM75 Temp Register Pointer |
| 5 | 0.005000 | 0x48 | READ | NONE | - | 2 | [0x19, 0x00] | LM75 Raw Temperature Data |

- **ID**：交易序號。
- **Topology**：若前面有 PCA9548A MUX 切換（如 Tx #1 切換到 Ch2），後續交易會自動標記 `MUX[2]` 下游拓撲。
- **Semantic Meaning**：工具內建晶片特徵庫（LM75、EEPROM 24C 系列、PMBus VR），能自動辨識位址並翻譯暫存器指令。

---

### 4.5 📝 Markdown 診斷報告 (Diagnostic Report)

**功能定位**：自動生成符合資深工程師報告規範的標準 Markdown 檔，並支援下載 Session 以便未來重現。

- **畫面輸出**：即時排版精美的診斷報告，包含：
  - 匯流排時序與健康統計表。
  - 識別到的周邊晶片清單與分類。
  - 完整的交易明細與異常事件清單。
- **操作按鈕**：
  1. **「下載 Markdown 報告」**：儲存為 `i2c_report.md`，可直接貼入 PR（Pull Request）、Bug 追蹤系統（Jira/GitHub Issues）或工作週報。
  2. **「下載可重現 Session」**：儲存為 `i2c_analysis.fwsession.json`。Session 包含分析設定、演算法版本與原始輸入檔案的 SHA-256 雜湊值；符合企業資安規範（不夾帶機密原始波形），後續可隨時重新載入並驗證分析結果。

---

## 5. 進階實戰對照實驗

為了深刻體會本工具的強大之處，建議進行以下兩組對照練習：

### 練習 A：使用 `examples/data/i2c_split_decoded.csv` 觀察真實溫度解碼
1. 在第 1 頁上傳 `examples/data/i2c_split_decoded.csv`。
2. 切換至 **「📜 封包交易列表」**：
   - 觀察 Tx #3（0x48 READ）：語意欄位顯示 **`Temperature = 25.50 °C (LM75/TMP102, raw 0x1980)`**。
   - 這是因為 per-byte 模式下確認了 `0x19 0x80` 均被正常接收，工具成功執行了二進位浮點溫度換算！

### 練習 B：使用 `examples/data/i2c_raw_100khz.csv` 觀察實測時脈
1. 將 **輸入資料型態** 切換為 **`Raw digital transition (Time, SCL, SDA)`**。
2. 上傳 `examples/data/i2c_raw_100khz.csv`。
3. 觀察頂部 KPI 卡片：
   - **平均時鐘頻率** 成功計算並顯示為 **`100.0 kHz`**！
   - **資料限制** 面板顯示 0 筆限制，代表這是最高證據等級的實測數位波形。
4. 切換至 **「📈 數位方波與協定軌」**：
   - 觀察真實的 45 個時鐘與資料切換邊緣，體驗與示波器一致的數位訊號視野。

