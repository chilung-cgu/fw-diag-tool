# 第一章：I2C / PMBus 協定診斷與波形判讀

## 這個頁面在做什麼？

I2C 是嵌入式系統中最常見的通訊匯流排，連接 EEPROM、溫度感測器、電源管理 IC、GPIO 擴充器等。
當 I2C 通訊失敗時，光看程式碼的回傳值（如 `-EIO`）通常無法定位發生在哪一筆交易。
邏輯分析儀資料可以補上 address、方向、data、ACK/NACK 與時間關係，但能判斷的範圍取決於你匯出的是 analyzer CSV、raw digital edge，還是 analog capture。

> [!IMPORTANT]
> Analyzer CSV 中的 decoded bytes 可以用來重建「協定示意圖」，但示意圖不是實際 SCL/SDA capture。只有輸入包含可靠 edge 或 duration 時，工具才能把 clock frequency、jitter 或 tHIGH/tLOW 標成量測值。完整差異請先讀[能力與限制](../LIMITATIONS.md)。

## 怎麼操作？

1. 進入 GUI 第 1 頁 **「📊 I2C / PMBus 診斷與波形檢視」**。
2. 在 **輸入資料型態** 先選正確模式：
   - `Saleae Analyzer table / text trace`：已有 decoded address/data/ACK 的表格；可以做交易、語意、NACK 與候選裝置分析，但沒有 raw edge 就不代表實測波形。
   - `Raw digital transition (Time, SCL, SDA)`：每列是邏輯分析儀的數位 transition；工具會驗證欄位與時間，直接 decode START/STOP、bit、ACK/NACK、tHIGH/tLOW 與 clock stretch。
3. 點擊 **「載入內建測試波形」** 或上傳自己的 CSV。
4. 先確認輸入類型與 **資料證據與限制** 提示，再看頂部 KPI。
5. 依序查看「封包交易列表」、「異常診斷」、「時序與健康圖表」。
6. 最後才用「協定示意圖」把選中的 transaction 對回 START、Address、Data 與 ACK/NACK。

### Raw digital CSV 最小格式

```csv
Time [s],SCL,SDA
0.000000,1,1
0.000002,1,0
0.000007,0,0
```

欄位名稱可以是 `Time [s]`、`SCL`、`SDA`，或在 CLI 明確指定 `--time-column`、`--scl-column`、`--sda-column`。時間必須 finite、非負且嚴格遞增；SCL/SDA 只能填 `0` 或 `1`。若同一 transition 同時改變 SCL 與 SDA，工具會停止並要求重新匯出，以免猜錯 sampling 順序。

CLI 等價操作：

```bash
fw-diag i2c analyze capture_raw.csv --raw-digital \
  --md raw_i2c_report.md
```

## 怎麼看懂 KPI 卡片？

| KPI | 白話解釋 | 怎麼判讀？ |
|---|---|---|
| **總傳輸次數** | Parser 重建出的 transaction 數 | 先檢查是否有 truncated row、缺少 START/STOP 或 capture window 太短 |
| **異常事件數** | 命中目前已實作診斷規則的數量 | 0 只代表沒有命中支援規則，不等於硬體與韌體完全正常 |
| **平均時鐘頻率** | 由輸入中的可靠 timing 計算的 SCL 速度 | 沒有 edge/duration 時應顯示 unavailable；不得從預設波形速度推回量測值 |
| **時鐘抖動 (Jitter)** | 多個有效頻率樣本的變異 | 必須同時查看樣本數、capture 設定與分布；不能只靠一個百分比判斷 ISR 或電氣原因 |

## 怎麼看懂數位波形圖？

切換到 **「📈 數位方波與協定軌」** 分頁，選擇任一筆交易。

- Raw digital 模式：圖上的 SCL/SDA 來自 capture 的實際 digital 0/1 transition，協定標註是由同一份資料 decode。
- Analyzer table 模式：圖是依 decoded transaction **重建的示意圖**，不是實際 SCL/SDA capture；沒有 raw edge 時不應用它判斷電氣品質。

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

### 先解讀證據，而不是先解讀顏色

- **Measured raw digital**：可以討論 transition 時間、tHIGH/tLOW、digital clock stretch。
- **Reconstructed**：只能用來學習 byte/ACK/START/STOP 的協定關係；工具會以 100 kHz 產生示意時間軸，這不是量測結果。
- **Unavailable / ACK UNKNOWN**：來源沒有欄位，不能當成 0 kHz、0% jitter 或成功 ACK；先補 capture 或確認 analyzer export 欄位。

## 測試資料

使用 `examples/data/i2c_golden.csv` 進行第一輪操作。這是一份小型 synthetic decoded trace，用來熟悉 GUI，不足以代表真實頻率分布或完整裝置行為。

若公司 Logic Analyzer 能匯出 raw digital transition，請另存一份只含 `Time [s]`、`SCL`、`SDA` 的 CSV，再選 Raw digital 模式；這才是本專案目前能直接呈現的「實測數位波形」。示波器的類比電壓、rise/fall、overshoot 與 ringing 不在此模式的量測範圍內。

看到 `0x70`、`0x50`、`0x48` 或 `0x20` 時，先把它當成 address。相同 address 可能對應多種 IC；必須再結合 schematic、board profile、command sequence 或 datasheet 才能確認裝置身份。

## 常見「證據限制」不是協定異常

| 品質代碼／現象 | 先怎麼理解 |
|---|---|
| `I2C_SOURCE_EMPTY` | 空檔、只有 header 或只有註解；這不是「全部交易正常」，而是沒有足夠資料分析。 |
| `I2C_ACK_UNAVAILABLE` / `I2C_TIMING_UNAVAILABLE` | 來源沒有 ACK 或 per-byte timing；工具不能把未知補成 ACK、0 kHz 或 0% jitter。 |
| `I2C_ACK_AGGREGATE_UNATTRIBUTABLE` | 一列包含多個 byte 卻只有一個 ACK/NACK；每個 byte 的 ACK 歸屬不明，語意會保守處理。 |
| `I2C_ADDRESS_NACK_SEMANTIC_UNAVAILABLE` / `I2C_DATA_NACK_SEMANTIC_UNAVAILABLE` | target 未接受 address/data，後面的 EEPROM/PMBus 語意不能當成已成功執行。 |
| `I2C_EEPROM_ACK_POLL` | 只有在前一筆已 ACK 的 EEPROM write、短時間內的 NACK probe、以及後續成功 ACK 都被觀察到時，才會標成合理 polling；孤立或過晚的 NACK 仍是一般 address NACK。 |

看到這些代碼時，先讀品質面板，再決定要補 raw capture、擴大時間窗，或回到 datasheet／driver log；不要把它們和 root-cause finding 混為一談。
