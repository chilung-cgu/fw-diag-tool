## 附錄 A：圖表與證據判讀指南 (Chart Interpretation Guide)

### A.0 看圖前先確認資料來源

圖表只能呈現輸入中存在的資訊。先確認頁面顯示的 evidence level 與有效樣本數：

- `Measured`：由輸入的 edge、duration 或值直接計算。
- `Inferred`：由多個觀察值推論，仍有其他可能解釋。
- `Reconstructed`：依 decoded transaction 畫出的示意資料。
- `Unavailable`：輸入不足，不能計算。

如果圖表沒有標示來源、樣本數或資料品質，先不要把視覺上精準的數字當成硬體量測。

### A.1 SCL Clock Frequency Distribution（時脈頻率分佈直方圖）

**這張圖在做什麼？**

統計具有可靠 timing 的 I2C byte frequency（kHz）。若輸入沒有 raw edge、duration 或 analyzer 提供的 bitrate，這張圖應顯示 unavailable，而不是套用預設頻率。

**X 軸（SCL Clock Frequency in kHz）**：

- 100 kHz = Standard-mode（標準模式）
- 400 kHz = Fast-mode（快速模式）
- 1000 kHz = Fast-mode Plus

**Y 軸（count）**：落在該頻率區間的有效樣本數。樣本數過少時，點圖或原始值表比 histogram 更容易判讀。

**怎麼判讀？**

| 圖形特徵 | 意義 | 排查方向 |
|---|---|---|
| **單一數值或窄峰** | 有效樣本接近相同值 | 先確認樣本數與輸入 timing 是否真實；一個 synthetic/default duration 也會產生假窄峰 |
| **多峰分散** | Capture 中存在多組 period | 可能是不同階段、不同 controller、stretch、解析邊界或資料混合；回到對應 transaction 驗證 |
| **寬廣散佈** | Frequency sample 變異較大 | 先排除 timestamp 精度、sample rate、glitch 與 parser 問題，再考慮 firmware scheduling 或硬體因素 |
| **低於預期設定** | 量到的 period 與設定值不符 | 對照 controller 設定與 raw edge；digital frequency 本身不能直接證明 pull-up 或 capacitance 是原因 |

> 新手提示：只看到一根柱子不代表一定正常。先看它包含幾個獨立樣本，以及這些樣本是否真的來自量測 timing。

---

### A.2 Bus Transaction Timeline & Active Device Map（匯流排交易時間軸與設備地圖）

**這張圖在做什麼？**

以時間軸（X 軸）為基準，將每一筆 I2C 交易按「哪個 Slave 被存取（Y 軸）」與「成功/失敗（顏色）」繪製成散點圖。

**X 軸（Start Time in seconds）**：交易的起始時間。

**Y 軸（Device）**：被存取的 Slave 設備名稱。

**圓點大小**：交易持續時間（Duration in ms），越大表示該筆交易佔用匯流排越久。

**圓點顏色**：

- 綠色 **ACK**：交易成功完成，Slave 正常回應。
- 橘色 **DATA NAK**：Address 有 ACK，但後續出現非預期 data NACK。Controller 在 read 最後一個 byte 用 NACK 結束讀取屬於正常流程，應另行分類。
- 紅色 **ADDR NAK**：Slave 沒有回應 Address（完全沒有 ACK）。
- 藍色 **READ END NAK**：Read 的最後一個 data byte 由 controller 發出 NACK，通常是正常的讀取終止。
- 灰色 **ACK UNKNOWN**：來源沒有 ACK/NACK 欄位；這不是成功，也不應列入失敗率分母。

**怎麼判讀？**

| 觀察重點 | 意義 | 排查方向 |
|---|---|---|
| **全部綠色** | 已支援欄位中沒有 unexpected NACK | 仍要檢查 capture 完整性、timing 與未支援語意 |
| **某個位址出現橘色/紅色點** | 該 transaction 有需要確認的 ACK/NACK | 先確認 NACK 位置與發送端，再檢查 address、供電、reset、busy 與流程 |
| **某個時間點突然出現紅色** | 該時刻的 transaction 發生 address NACK | 與 power/reset/log 時間軸交叉比對；不能只由散點圖斷言 ESD 或瞬斷 |
| **同一設備連續多次 ACK** | 韌體在連續讀寫該設備 | 正常行為，如連續讀取 EEPROM |
| **同一設備連續多次 NACK** | 韌體在重試（Retry Loop） | 檢查驅動程式是否有無限重試邏輯 |

> 新手提示：把滑鼠游標懸停在圓點上，會顯示該筆交易的詳細資訊（Transaction ID、方向、資料長度、持續時間）。

---

### A.3 匯流排物理層健康評等（Device Health Grade Table）

**這張表在做什麼？**
依目前可觀察的 transaction 事件產生啟發式評分。它是排序排查優先級的摘要，不是「匯流排物理層」或晶片良率的正式分數。

**評分欄位說明**：

| 欄位 | 意義 |
|---|---|
| **Slave Address** | 該設備的 7-bit I2C 位址（如 0x50） |
| **Device Name** | Address 對應的候選裝置或使用者 board profile；只有 address 時不能確認精確型號 |
| **Category** | 設備類別（如 EEPROM/Memory、Temperature Sensor、PMBus） |
| **Total Transactions** | 該設備被存取的總次數 |
| **NACK Count** | 非預期 address/data NACK 的 transaction 數；正常 read-final NACK 不應列入 |
| **Success Rate** | 依目前支援規則計算的 transaction 成功比例，不是完整系統成功率 |
| **Clock Stretches** | 該設備拉低 SCL 的次數（Clock Stretching） |
| **Health Grade** | 綜合評等：A/B/D/F |

**Health Grade 評分標準**：

| 等級 | 條件 | 白話解釋 |
|---|---|---|
| **A** | 支援規則內沒有觀察到失敗事件 | 目前資料沒有顯示問題；不是完整健康保證 |
| **B** | 少量 warning、stretch 或 retry | 回到 transaction 與系統門檻確認是否符合裝置規格 |
| **D** | 多筆 unexpected NACK 或成功比例偏低 | 提高排查優先級，但仍需驗證 capture 與使用情境 |
| **F** | 大量失敗或嚴重 timeout/hang evidence | 需要立即調查；不能只由等級判定晶片損壞 |

> 新手提示：A/B 只表示目前資料沒有命中高嚴重度規則。D/F 表示先看該位址的 transaction、資料品質與同步 log，不是直接更換晶片。

---

### A.4 異常診斷面板（Anomalies Tab）判讀

**這個分頁在做什麼？**
列出目前規則偵測到的 I2C/SMBus 協定或時序 finding，並提供可能原因與驗證清單。工具輸出的原因是 hypothesis，不是已經證明的 root cause。

**常見異常代碼說明**：

| 異常代碼 | 白話解釋 | 排查優先順序 |
|---|---|---|
| **I2C_ADDR_NACK** | Target address 沒有 ACK | 1.確認 address/direction 2.對照 power/reset/MUX 3.檢查 7-bit/8-bit 表示法 |
| **I2C_DATA_NACK** | Write data 或非終止用途的 data byte 未 ACK | 1.確認發送端與 protocol 2.檢查 busy/command/register/length |
| **I2C_CLOCK_STRETCH_TIMEOUT** | 量到的 SCL LOW 超過設定門檻 | 1.確認 raw timing 與門檻來源 2.檢查 target/controller log；未確認前不要直接執行 recovery write |
| **I2C_BUS_HANG_NO_STOP** | Capture 中沒有看到預期 STOP | 1.確認 capture 是否截斷 2.檢查 controller state 與 bus level |
| **I2C_EEPROM_PAGE_ROLLOVER** | EEPROM 寫入跨頁覆蓋 | 1.以 Page Size 分段寫入 |
| **I2C_MUX_MULTI_CHANNEL** | MUX 同時開啟多通道 | 1.關閉其他通道 2.檢查位址衝突 |
