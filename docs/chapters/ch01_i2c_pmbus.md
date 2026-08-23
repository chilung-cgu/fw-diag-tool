# 第一章：I2C / PMBus 協定診斷與波形判讀

## 這個頁面在做什麼？

I2C 是嵌入式系統中最常見的通訊匯流排，連接 EEPROM、溫度感測器、電源管理 IC、GPIO 擴充器等。
當 I2C 通訊失敗時，光看程式碼的回傳值（如 `-EIO`）通常無法定位發生在哪一筆交易。
邏輯分析儀資料可以補上 address、方向、data、ACK/NACK 與時間關係，但能判斷的範圍取決於你匯出的是 analyzer CSV、raw digital edge，還是 analog capture。

> [!IMPORTANT]
> Analyzer CSV 中的 decoded bytes 可以用來重建「協定示意圖」，但示意圖不是實際 SCL/SDA capture。只有輸入包含可靠 edge 或 duration 時，工具才能把 clock frequency、jitter 或 tHIGH/tLOW 標成量測值。完整差異請先讀[能力與限制](../LIMITATIONS.md)。

## 怎麼操作？

1. 進入 GUI 第 1 頁 **「📊 I2C / PMBus 診斷與波形檢視」**。
2. 點擊 **「載入內建測試波形」** 或上傳自己的 Saleae CSV。
3. 先確認輸入類型與 Data Quality 提示，再看頂部 KPI。
4. 依序查看「封包交易列表」、「異常診斷」、「時序與健康圖表」。
5. 最後才用「協定示意圖」把選中的 transaction 對回 START、Address、Data 與 ACK/NACK。

## 怎麼看懂 KPI 卡片？

| KPI | 白話解釋 | 怎麼判讀？ |
|---|---|---|
| **總傳輸次數** | Parser 重建出的 transaction 數 | 先檢查是否有 truncated row、缺少 START/STOP 或 capture window 太短 |
| **異常事件數** | 命中目前已實作診斷規則的數量 | 0 只代表沒有命中支援規則，不等於硬體與韌體完全正常 |
| **平均時鐘頻率** | 由輸入中的可靠 timing 計算的 SCL 速度 | 沒有 edge/duration 時應顯示 unavailable；不得從預設波形速度推回量測值 |
| **時鐘抖動 (Jitter)** | 多個有效頻率樣本的變異 | 必須同時查看樣本數、capture 設定與分布；不能只靠一個百分比判斷 ISR 或電氣原因 |

## 怎麼看懂數位波形圖？

切換到 **「📈 數位方波與協定軌」** 分頁，選擇任一筆交易。若輸入是 decoded/analyzer CSV，這裡顯示的是依交易內容重建的示意圖：

- 上方彩色區塊 = 協定階段標註
- 中間青色線 = SDA（資料線）
- 下方黃色線 = SCL（時鐘線）

**怎麼讀波形？**

| 波形特徵 | 白話解釋 | 排查方向 |
|---|---|---|
| SCL 高電平時 SDA 從高變低 | START 條件 | 正常的通訊起始 |
| SCL 高電平時 SDA 保持穩定 | 資料取樣點 | 此時的 SDA 就是該 bit 的值 |
| 第 9 個 Clock Pulse SDA 為低電平 | ACK（確認） | Receiver 接受前一個 byte |
| 第 9 個 Clock Pulse SDA 為高電平 | NACK（未確認） | 要先分辨發送端與位置；read 最後一個 byte 可由 controller 正常 NACK 結束讀取 |
| SCL LOW period 明顯延長 | 可能是 Clock Stretching | 只有 raw edge/timing 能量到實際延長；timeout 門檻依協定與系統設定判斷 |
| SCL 高電平時 SDA 從低變高 | STOP 條件 | 正常的通訊結束 |

## 測試資料

使用 `examples/data/i2c_golden.csv` 進行第一輪操作。這是一份小型 synthetic decoded trace，用來熟悉 GUI，不足以代表真實頻率分布或完整裝置行為。

看到 `0x70`、`0x50`、`0x48` 或 `0x20` 時，先把它當成 address。相同 address 可能對應多種 IC；必須再結合 schematic、board profile、command sequence 或 datasheet 才能確認裝置身份。
