# 附錄 A：I2C 圖表、status、threshold 與 evidence 判讀

本附錄是 GUI 第 1 頁圖表的唯一詳細定義。第 1 章只保留操作摘要；本檔負責 axes、單位、status、threshold、issue code 與 evidence semantics。任何圖表結論都必須先回到原始輸入欄位與 sample count。

## A.0 Evidence labels：先決定數字能不能回答問題

| Label | 來源 | 可以回答 | 不能回答 |
|---|---|---|---|
| **Measured** | raw digital transition 的 `Time [s]`, `SCL`, `SDA`，或來源明確提供的 duration/bitrate | digital edge、SCL period/frequency、clock stretch duration | 類比電壓、rise/fall、overshoot、ringing、pull-up 品質。 |
| **Source-provided** | analyzer row 的 `Duration` 或 `Bit Rate` | 來源欄位所支持的 byte timing；顯示 sample count | 來源沒有提供的 edge/analog meaning。 |
| **Reconstructed** | decoded address/data/ACK 重建的協定圖 | START、address、data、ACK slot、STOP 的協定關係 | 真實線路時間、電壓或 device response。 |
| **Inferred** | 多個觀察值的關聯 | 排查順序或候選解釋 | 唯一 root cause。 |
| **Hypothesis** | reporter 的可能原因文字 | 下一個應驗證的方向 | 已證明的硬體/韌體故障。 |
| **Unavailable / Unknown** | 欄位缺失、aggregate attribution 不明、capture 截斷 | 明確指出證據缺口 | 不能當成 `0`、ACK、正常或 pass。 |

**Aggregate ACK contract**：一列多個 data byte 只有一個 ACK/NACK 時，工具保留 `I2C_ACK_AGGREGATE_UNATTRIBUTABLE`、ACK unknown，並 withheld per-byte semantic。這也是 `i2c_golden.csv` 與 `i2c_failing_nack.csv` 不產 protocol issue 的原因；它們不是 per-byte failure proof。

**Timing units**：`Duration`／`duration_s` 一律是秒；`Bit Rate`／`bit_rate`／`bitrate`／`frequency` 建議使用 kHz。為相容部分 analyzer export，數值大於 `10000` 會被視為 Hz 並轉成 kHz；同一檔案不要混用單位。`Duration` 是整個 byte 的時間，只能支援 frequency estimate；aggregate（一列多 byte）不會把單一 `Duration` 猜分給各 byte，請拆成 per-byte rows 或提供 `Bit Rate`。若 aggregate row 只有一個 `Bit Rate`，解析器會把同一來源值帶到展開的 address/data slots，`Samples: N` 代表展開 slot 數，不代表原始 row 數；需要可追溯的每筆樣本時請拆成 per-byte rows。沒有 SCL-low/edge evidence 時，不可把 `Duration` 當成 clock stretch。若來源明確輸出 `Clock Stretch [s]`／`clock_stretch_s`，工具才會把該欄位標記為 source-backed stretch。

**Read-final NACK contract**：Read 的最後一個 data byte 由 controller 發 NACK 再 STOP，是正常 termination。它在 timeline 顯示 `READ END NAK`，不產 `I2C_DATA_NACK`，也不降低 health success rate。

**Raw STOP overlay**：raw digital capture 的 STOP 若位於最後一個 transition，沒有下一個 edge 可形成實際寬度；GUI 會畫一個小的 display-only marker，並在 annotation details 標示這不是量到的 STOP duration。

## A.1 SCL Clock Frequency Distribution

**X 軸：** `SCL Clock Frequency (kHz)`；由 source-provided bitrate、byte duration 或 raw digital SCL period 計算。`100 kHz`、`400 kHz` 是常見模式標記，不是工具替硬體指定的設定。

**Y 軸：** `count`，落在該 bin 的有效 frequency samples 數。標題應同時顯示平均值、jitter 與 `Samples: N`；`N=0` 時顯示 `unavailable` 與「No source-provided bitrate or byte-duration evidence」，不可畫一根假 0 kHz 柱。

**判讀規則：**

- 窄峰只表示目前樣本接近，不表示 signal integrity 正常。
- 多峰或寬散佈先檢查 sample rate、timestamp precision、mixed controller/transaction 與 parser 邊界，再討論 firmware scheduling。
- Jitter 超過 anomaly detector 的 **35%** threshold 且平均頻率 >0 時，issue code 是 `I2C_HIGH_CLOCK_JITTER`。這是 timing finding，不是 pull-up 或 ISR root-cause proof。
- decoded aggregate 沒有 per-byte timing 時，frequency 與 jitter 都是 `Unavailable`；不要拿交易開始時間差除以 byte 數。

## A.2 Bus Transaction Timeline & Active Device Map

**X 軸：** `Start Time (s)`，單位是秒。timestamp 缺失時圖標題會標 `timestamps unavailable`；只有部分 transaction 有 timestamp 時標 `partial timestamps`。

**Y 軸：** `Device`，優先使用 board profile/name；否則以 `0xNN` 7-bit address 顯示。Address candidate 不是已確認型號。

**點大小：** `Duration (ms)`，只有 transaction timestamp 與 duration evidence 可用時才啟用；沒有 duration 時不要從 row 間距臆測 bus occupancy。

**Status：**

| Status | 條件 | 意義 |
|---|---|---|
| `ACK` | address/data ACK 可歸屬，沒有 unexpected NACK | 目前已提供欄位內的協定觀察。 |
| `ADDR NAK` | address byte NACK | `I2C_ADDR_NACK` 的協定 finding；先查 address、power/reset、MUX。 |
| `DATA NAK` | address ACK，write 或非終止 data byte NACK | `I2C_DATA_NACK`；Read-final NACK 不在此類。 |
| `READ END NAK` | Read 最後一個 byte 是 controller NACK | 正常 termination；不列為 failure。 |
| `ACK UNKNOWN` | ACK 欄位缺失或 aggregate 無法歸屬 | 不是成功，不列入 success-rate 分母。 |
| `EVIDENCE INCOMPLETE` | address/direction 缺失 | 只顯示保留的資料，不做 device/failure 推論。 |

時間軸可幫助把 transaction 對回 driver log、power/reset 或 MUX 操作；它不能單獨證明 ESD、電壓瞬斷或晶片損壞。

## A.3 Device Health Summary：排查排序，不是 physical grade

這張表以目前 transaction evidence 產生 heuristic summary。欄位定義如下：

| 欄位 | 單位／計算 | 邊界 |
|---|---|---|
| `Slave Address` | 7-bit hex | 只代表 bus address。 |
| `Device Name` / `Category` | board profile 或 address candidate | candidate 不等於確切型號。 |
| `Total Transactions` | 筆 | 只計入可對應該 address 的交易。 |
| `NACK Count` | 筆 | address NACK + unexpected data NACK；Read-final NACK 排除。 |
| `Unknown ACK Count` | 筆 | ACK missing/aggregate unknown；不當成成功或失敗。 |
| `Success Rate` | `(known_tx - nack_count) / known_tx × 100%` | `known_tx=0` 顯示 `N/A`。 |
| `Clock Stretches` | 次數 | 只來自來源 timing evidence。 |
| `Health Grade` | A/B/D/F 或 `N/A (ACK unavailable)` | 只供排查優先順序，**不是 physical health grade、電氣 pass/fail、良率或 RMA 判定**。 |

目前實作 threshold：

| Grade | 條件 | 解讀 |
|---|---|---|
| `A (Excellent)` | known evidence 中沒有 NACK/notice | 目前資料未命中支援的 failure rule；不是完整健康保證。 |
| `B (Minor Jitter / Retries)` | success <95%，或有至少一次 stretch | 先回到 transaction 與 timing threshold。 |
| `D (High NACK Rate)` | success <80% | 高優先排查，但仍需 raw/driver/power evidence。 |
| `F (Critical Fault)` | success <50%，或 stretch count ≥5 | 嚴重 finding；不能只由 grade 宣稱晶片故障。 |

## A.4 Anomalies tab：issue code 與 threshold

以下是目前程式實際產出的主要 canonical code；顯示時請以 `issues[].code` 原值為準。

| Issue code | 觸發條件 | evidence / 下一步 |
|---|---|---|
| `I2C_ADDR_NACK` | address ACK 明確為 NACK，且不是已確認的 EEPROM ACK polling | 查 7-bit/8-bit address、power/reset、address strapping、MUX；不要把後續 data 當 accepted semantic。 |
| `I2C_DATA_NACK` | Write 或非終止 data byte NACK，address 已 ACK | 查 register/command、write protect、busy、length、PEC；Read-final NACK 不適用。 |
| `I2C_SMBUS_TIMEOUT` | measured/source stretch duration **≥ 設定 SMBus timeout**；GUI 預設 25 ms | 這是 timing threshold finding；與 controller/target log 對照後再做 bus recovery。 |
| `I2C_LONG_CLOCK_STRETCH` | stretch duration **> 0.1 ms（100 µs）** 且未達 timeout | Noticeable timing finding；不是自動 bus hang 或硬體故障。 |
| `I2C_MISSING_STOP` | transaction 結束沒有 STOP，且不是正常 repeated-start 邊界 | 可能是截斷、controller abort 或 bus-state 問題；用 raw edge、9-clock recovery log、reset/power evidence 區分。 |
| `I2C_EEPROM_ACK_POLL` | EEPROM address NACK 且後續在 polling window 內成功 ACK | INFO/expected behavior，不能與一般 address NACK 混為一談。 |
| `I2C_PREMATURE_READ_NACK` | Read 在預期最後 byte 前由 controller NACK | 查 read length/FIFO；最後一 byte 的 NACK 不觸發此 code。 |
| `I2C_HIGH_CLOCK_JITTER` | frequency jitter >35% 且有有效頻率樣本 | 先查 capture/sample/timestamp，再查 driver scheduling；不直接等同 analog noise。 |

Data quality code 不是 protocol issue。常見例子：`I2C_SOURCE_EMPTY`、`I2C_SOURCE_NO_TRANSACTIONS`、`I2C_TIMING_UNAVAILABLE`、`I2C_TIMING_AGGREGATE_UNATTRIBUTABLE`、`I2C_ACK_UNAVAILABLE`、`I2C_ACK_AGGREGATE_UNATTRIBUTABLE`、`I2C_RESERVED_ADDRESS_CANDIDATE`、`I2C_PMBUS_PAYLOAD_TRUNCATED`、`I2C_EEPROM_PROFILE_UNAVAILABLE`、`I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS`。它們應顯示在 quality panel/report，提醒哪些結論被 withheld；有 events 但沒有 logical transaction 時，不能顯示成 clean。

## A.5 最小 evidence self-check

看到任何圖表或 status 時，固定回答：

1. X/Y 軸的欄位與單位是什麼？
2. `Samples: N`、timestamp count、unknown ACK count 在哪裡？
3. 這個值是 Measured、Source-provided、Reconstructed、Inferred、Hypothesis，還是 Unavailable？
4. NACK 是 address、write data、premature read，還是 normal read termination？
5. 下一個能區分假說的 raw capture、driver log、datasheet 或 board profile 證據是什麼？

沒有答案時，報告應保留 `Unavailable`/`Unknown`，而不是用顏色、grade 或漂亮的理想波形補足證據。
