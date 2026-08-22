## 附錄 A：圖表判讀完全指南 (Chart Interpretation Guide)

### A.1 SCL Clock Frequency Distribution（時脈頻率分佈直方圖）

**這張圖在做什麼？**
統計每一個 I2C Byte 傳輸的實際 SCL 時脈頻率（kHz），並以直方圖呈現分佈情況。

**X 軸（SCL Clock Frequency in kHz）**：
- 100 kHz = Standard-mode（標準模式）
- 400 kHz = Fast-mode（快速模式）
- 1000 kHz = Fast-mode Plus

**Y 軸（count）**：出現在該頻率區間的 Byte 傳輸次數。

**怎麼判讀？**

| 圖形特徵 | 意義 | 排查方向 |
|---|---|---|
| **單一窄峰**（如全部集中在 360 kHz）| 匯流排時脈穩定，Master 固定頻率運作 | 正常，無需處理 |
| **多峰分散**（如 100k 和 400k 同時出現）| 不同 Master 或 Clock Stretching 導致頻率變異 | 檢查 Clock Stretching 或多 Master 衝突 |
| **寬廣散佈**（Jitter > 35%）| 時脈不穩定，可能為 ISR 搶佔或硬體電容過大 | 檢查中斷服務常式延遲、上拉電阻值 |
| **頻率遠低於設定值**（如設定 400k 但實測 100k）| 匯流排負載過重或 Master 降速 | 檢查上拉電阻是否過大 (>4.7kOhm) 或總線電容 >400pF |

> 新手提示：如果你只看到一根柱子，這是正常的！表示所有 Byte 都以相同頻率傳輸，匯流排時序非常穩定。

---

### A.2 Bus Transaction Timeline & Active Device Map（匯流排交易時間軸與設備地圖）

**這張圖在做什麼？**
以時間軸（X 軸）為基準，將每一筆 I2C 交易按「哪個 Slave 被存取（Y 軸）」與「成功/失敗（顏色）」繪製成散點圖。

**X 軸（Start Time in seconds）**：交易的起始時間。
**Y 軸（Device）**：被存取的 Slave 設備名稱。
**圓點大小**：交易持續時間（Duration in ms），越大表示該筆交易佔用匯流排越久。
**圓點顏色**：
- 綠色 **ACK**：交易成功完成，Slave 正常回應。
- 橘色 **DATA NAK**：Address 有 ACK 但資料傳輸中被 NACK。
- 紅色 **ADDR NAK**：Slave 沒有回應 Address（完全沒有 ACK）。

**怎麼判讀？**

| 觀察重點 | 意義 | 排查方向 |
|---|---|---|
| **全部綠色** | 所有交易成功，匯流排健康 | 正常 |
| **某個設備出現橘色/紅色點** | 該設備通訊異常 | 檢查該設備供電、位址設定或是否忙碌中 |
| **某個時間點突然出現紅色** | 匯流排在該時刻發生故障 | 檢查該時間點附近是否有電源瞬斷或 ESD 干擾 |
| **同一設備連續多次 ACK** | 韌體在連續讀寫該設備 | 正常行為，如連續讀取 EEPROM |
| **同一設備連續多次 NACK** | 韌體在重試（Retry Loop） | 檢查驅動程式是否有無限重試邏輯 |

> 新手提示：把滑鼠游標懸停在圓點上，會顯示該筆交易的詳細資訊（Transaction ID、方向、資料長度、持續時間）。

---

### A.3 匯流排物理層健康評等（Device Health Grade Table）

**這張表在做什麼？**
對匯流排上每一個 Slave 設備進行自動化健康評分，類似學校的 A/B/C/D/F 成績。

**評分欄位說明**：

| 欄位 | 意義 |
|---|---|
| **Slave Address** | 該設備的 7-bit I2C 位址（如 0x50） |
| **Device Name** | 根據位址自動識別的晶片型號（如 AT24Cxx EEPROM） |
| **Category** | 設備類別（如 EEPROM/Memory、Temperature Sensor、PMBus） |
| **Total Transactions** | 該設備被存取的總次數 |
| **NACK Count** | 該設備發出 NACK 的次數（越多越不健康） |
| **Success Rate** | 成功率 = (Total - NACK) / Total x 100% |
| **Clock Stretches** | 該設備拉低 SCL 的次數（Clock Stretching） |
| **Health Grade** | 綜合評等：A/B/D/F |

**Health Grade 評分標準**：

| 等級 | 條件 | 白話解釋 |
|---|---|---|
| **A (Excellent)** | 成功率 >= 95% 且無 Clock Stretch | 完美！所有通訊都正常。 |
| **B (Minor Jitter)** | 成功率 >= 95% 但有 Clock Stretch，或成功率 80~95% | 偶爾有延遲或重試，但功能正常。 |
| **D (High NACK Rate)** | 成功率 < 80% | 超過 20% 的通訊失敗，需要排查！ |
| **F (Critical Fault)** | 成功率 < 50% 或 Clock Stretch >= 5 次 | 嚴重故障，該設備可能已損壞或未正確連接。 |

> 新手提示：如果你的測試資料中所有設備都是 A 或 B，表示硬體和韌體都正常。如果有 D 或 F，優先檢查該設備的供電與焊接。

---

### A.4 異常診斷面板（Anomalies Tab）判讀

**這個分頁在做什麼？**
列出所有自動偵測到的 I2C/SMBus 協定違規與時序異常，並提供 Root Cause 分析與排查行動清單。

**常見異常代碼說明**：

| 異常代碼 | 白話解釋 | 排查優先順序 |
|---|---|---|
| **I2C_ADDR_NACK** | Slave 沒有回應位址 | 1.量VCC 2.查A0/A1/A2腳位 3.檢查7-bit vs 8-bit |
| **I2C_DATA_NACK** | Slave 在資料階段 NACK | 1.EEPROM tWR 忙碌 2.Register Offset 越界 |
| **I2C_CLOCK_STRETCH_TIMEOUT** | Slave 拉低 SCL > 25ms | 1.Slave MCU 當機 2.執行 SCL 9-Clock Reset |
| **I2C_BUS_HANG_NO_STOP** | 匯流排未收到 STOP 條件 | 1.Master 韌體異常退出 2.發送 STOP 恢復 |
| **I2C_EEPROM_PAGE_ROLLOVER** | EEPROM 寫入跨頁覆蓋 | 1.以 Page Size 分段寫入 |
| **I2C_MUX_MULTI_CHANNEL** | MUX 同時開啟多通道 | 1.關閉其他通道 2.檢查位址衝突 |