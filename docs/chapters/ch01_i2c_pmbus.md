# I2C / SMBus / PMBus：第 1 頁任務導向實驗室

本章只處理 GUI 第 1 頁 **「📊 I2C / PMBus 診斷與波形檢視」**。目標是把一份 capture 變成可追溯的觀察：先確認輸入契約，再看五個 tabs，最後保存報告與 session。圖表軸、顏色、threshold 與 issue code 的完整定義集中在[附錄 A：圖表與證據判讀](appendix_chart_guide.md)。

## 1. 兩分鐘完成第一次分析

先在專案根目錄啟動 GUI：

```bash
uv run fw-diag gui
```

1. 選左側第 1 頁，在「教學範例」先選 `Packaged decoded analyzer（18 筆）`，輸入模式會是 `Decoded Analyzer CSV`。
2. 按 **載入內建測試波形**；要練習 raw 或 text，改選對應範例後再按同一按鈕。
3. 先讀「資料證據與限制」，再看 KPI；不要把綠色狀態當成硬體已驗證。
4. 依序開啟封包交易列表、Waveform、Anomalies、匯流排時序與健康圖表、Markdown 診斷報告五個 tabs；先選交易，Waveform 才會聚焦同一筆。
5. 另用本章的 raw digital fixture 重跑一次，確認哪些數字是 measured、哪些仍是 unavailable。

內建按鈕載入的是套件資源 `builtin:saleae_normal_pmbus_eeprom.csv`，不是 `examples/data/i2c_golden.csv`。目前可驗證的結果是 **18 transactions、53 physical events、0 protocol issues**。資料品質仍會列出：

- `I2C_EEPROM_PROFILE_UNAVAILABLE`：0x50 的 EEPROM 寬度/page profile 未指定。
- `I2C_PMBUS_PAYLOAD_TRUNCATED`：一個 PMBus command 缺少規格所需 response bytes，該語意不完整。
- `I2C_TIMING_UNAVAILABLE`：沒有每 byte duration/bitrate，因此平均 clock 與 jitter 顯示 `不可用`。

這些是輸入證據的狀態，不是「18 筆都通過硬體測試」的宣告。

## 2. 三種輸入契約：欄位、單位與可回答的問題

先在檔案來源上做分類。工具不會把缺少的欄位補成 0、ACK 或預設頻率。

### 契約 A：Decoded Analyzer CSV（aggregate 或 per-byte）

| 欄位 | 單位／值域 | 契約與限制 |
|---|---|---|
| `Time [s]` 或 `Time` | 秒，finite、非負；可缺省 | 只有來源含 timestamp 才能畫交易時間軸；交易時間差不是 SCL period。 |
| `Address` | 一般 7-bit `0x08`～`0x77`；也接受 8-bit wire address | 8-bit 位址會正規化為 7-bit。保留 `0x00`～`0x07`、`0x78`～`0x7F` 供 forensic inspection，但會列 `I2C_RESERVED_ADDRESS_CANDIDATE`，不當成正常裝置身份；Packet Builder 會拒絕這些位址。仍須對照 datasheet/board profile。 |
| `Read/Write` | `Read`/`Write`（或 `R`/`W`） | 沒有方向時，方向相依語意與 anomaly attribution 會保留為 unknown。 |
| `Data` | 每 byte 0～255；可用空白或逗號分隔 | **Per-byte** 每列一個 byte，ACK/NAK 可歸屬；**aggregate** 一列多 byte 只有一個 ACK/NAK，會 withheld。 |
| `ACK/NACK` 或 `ACK/NAK` | `ACK`、`NACK`/`NAK` | aggregate ACK 不會猜是哪個 byte；unknown 不列入成功率分母。 |
| `Duration`／`Bit Rate`（選填） | `Duration` 單位為秒；`Bit Rate`／`bitrate`／`frequency` 通常填 kHz；相容規則是數值 `>10000` 視為 Hz 後轉成 kHz | 只有來源提供的 timing 才能計算 frequency；交易 timestamp 不可拿來臆測 clock。`Duration` 是整個 byte 的來源時間，**不能單獨證明 clock stretch**；若 analyzer 明確提供 SCL-low hold，另用 `Clock Stretch [s]`（秒）。aggregate（一列多 byte）不會把單一 `Duration` 猜分給各 byte；要取得 per-byte frequency samples，請拆成 per-byte rows，或使用 `Bit Rate`。若 aggregate row 只有一個 `Bit Rate`，解析器會把同一來源值帶到展開的 address/data slots，`Samples: N` 代表展開 slot 數，不代表原始 row 數；需要可追溯的每筆樣本時請拆成 per-byte rows。請先把 Saleae 的 μs 轉成秒，並避免混用單位。 |

最小 per-byte 範例：

```csv
Time [s],Packet ID,Address,Data,Read/Write,ACK/NAK
0.001000,0,0x58,,Write,ACK
0.001025,0,,0x88,Write,ACK
```

**資源邊界**：GUI 仍會先依 `AnalysisLimits` 限制輸入（records 50,000、raw transitions 50,000）；選取的 decoded transaction 另有 100,000 個理想 waveform points 上限。超過時，交易列表、異常、時序與報告仍可用，只有該筆重建波形會顯示「略過繪圖」並保留限制原因，不會把大型輸入一次展開到瀏覽器。

### 契約 B：Raw digital transition CSV

```csv
Time [s],SCL,SDA
0.000000,1,1
0.000005,1,0
0.000010,0,0
```

上面 3 行只展示欄位名稱與 `0/1` 值域，**刻意不是可完成解碼的 capture**；它沒有完整的 9-bit byte、ACK 與 STOP。要直接執行分析，請使用完整的 `examples/data/i2c_raw_100khz.csv`（或 GUI 的 `Raw digital measured 100 kHz（1 筆）` 範例）。

| 欄位 | 單位／值域 | 工具能回答什麼 |
|---|---|---|
| `Time [s]` | 秒；finite、非負、嚴格遞增 | transition 的時間差、SCL period、frequency、digital clock stretch。 |
| `SCL`、`SDA` | 邏輯值 `0` 或 `1` | START/Repeated START、byte、ACK/NACK、STOP 的 digital decode。 |

每一行是保留的 level/transition sample；同一時間同時改變 SCL 與 SDA 會被拒絕，因為 sampling 順序無法判定。這個契約仍然**不能**量類比電壓、rise/fall time、overshoot、ringing 或 pull-up 品質。

### 契約 C：Saleae-style text trace

時間以秒表示；`S`/`Sr`/`P` 是 START、Repeated START、STOP，`A`/`N` 是 ACK/NACK：

```text
[0.001000] S 0x48 W A 0x00 A P
[0.002000] S 0x48 R A 0x19 A 0x80 N P
```

文字 trace 可以表達協定事件與缺少 STOP；它沒有 raw SCL/SDA edge，所以 frequency、digital stretch 與類比量測仍是 `Unavailable`。若省略 `P`，請把它當成待驗證的 bus-state evidence，不要直接寫成硬體已鎖死。

只有 `S`/`P` 等 framing、沒有完整 address/data 的輸入，會保留 physical events 但產生 `I2C_SOURCE_NO_TRANSACTIONS`；這是「沒有可分析交易」而不是通訊正常。

## 3. 真實 fixture 實驗與預期輸出

### 3.1 Aggregate golden：`i2c_golden.csv`

上傳 `examples/data/i2c_golden.csv` 後，預期是 **5 transactions、0 protocol issues**，但資料品質面板會指出 aggregate ACK 的限制：

- 一列含多個 data byte，唯一 ACK/NACK 無法歸屬到 address 或哪個 data byte。
- `I2C_ACK_AGGREGATE_UNATTRIBUTABLE` 與 `I2C_ACK_UNAVAILABLE` 會保留這個 unknown；PMBus/EEPROM payload semantic 會 withheld。
- 若 aggregate row 另帶一個 `Duration`，會標記 `I2C_TIMING_AGGREGATE_UNATTRIBUTABLE`；工具保留來源值，但不把它猜分成 per-byte frequency sample。
- `I2C_TIMING_UNAVAILABLE` 會使 frequency/jitter 顯示 `不可用`。

即使貼上 Board Profile，aggregate ACK row 仍可能只顯示 `Unknown Device (0xNN)`；這是因為來源沒有足夠的 per-byte evidence，工具不會用 profile 名稱掩蓋 attribution 缺口。要練習 profile 驅動的裝置名稱與 register/PMBus semantic，請改用 `i2c_split_decoded.csv`。

這是「有 transaction shape、沒有 per-byte ACK attribution」的練習，不是 golden hardware proof。

### 3.2 `i2c_failing_nack.csv`：為什麼不會產 issue

此檔案把 aggregate row 的 summary ACK 改成 NACK，但仍然沒有 per-byte attribution。預期仍是 **5 transactions、0 issues**，且同樣顯示 aggregate/ACK unknown 品質限制。它不能證明 slave 發生 data NACK；若要測試真正的 address/data NACK，改用本章的 per-byte fixtures。

### 3.3 Per-byte split：`i2c_split_decoded.csv`

上傳 `examples/data/i2c_split_decoded.csv`，預期 **5 transactions**。0x48 的 read 會顯示：

```text
Temperature = 25.50 °C (LM75/TMP102, raw 0x1980)
```

最後一個 read byte 的 `NACK` 是 controller 的正常讀取終止，因此不產 `I2C_DATA_NACK`。0x50 的 EEPROM profile 未指定時，報告會保留 read bytes、但對 write offset/page semantic 顯示 profile unavailable。

### 3.4 Raw digital：`i2c_raw_100khz.csv`

這個 fixture 有 **46 行（header 加 45 筆 transition samples）**。切換到 `Raw digital transition (Time, SCL, SDA)` 後上傳它，預期：

- average SCL frequency 約 **100.0 kHz**，frequency sample count > 0。
- quality panel **不會顯示資料品質 issue**；這只表示這份 raw CSV 通過 schema/timing 契約。
- 圖是 measured digital 0/1 capture，不是類比電壓量測；仍需示波器或其他 analog evidence 才能回答 rise time。

### 3.5 可執行 anomaly fixtures

以下檔案都可直接用 `I2CDiagnosticEngine` 或 CLI `fw-diag i2c analyze` 分析；text trace 請加 `--text-trace`、raw 請加 `--raw-digital`。expected code 是 report 的 `issues[].code`，不是自由文字：

| Fixture | 輸入形態 | 預期 issue code | 關鍵觀察 |
|---|---|---|---|
| `examples/data/i2c_address_nack.csv` | per-byte decoded CSV | `I2C_ADDR_NACK` | address byte NACK；不可當作 address 已存在。 |
| `examples/data/i2c_data_nack.csv` | per-byte decoded CSV | `I2C_DATA_NACK` | address ACK 後，write data byte NACK。 |
| `examples/data/i2c_missing_stop.csv` | event CSV（`Type` 欄） | `I2C_MISSING_STOP` | 沒有 STOP；capture 截斷與真正 bus hang 仍要用 raw/driver evidence 區分。 |
| `examples/data/i2c_clock_stretch.csv` | decoded CSV + `Duration`／`Clock Stretch [s]`（秒） | `I2C_LONG_CLOCK_STRETCH`、`I2C_SMBUS_TIMEOUT` | `Duration` 支援 byte frequency；只有明確的 `Clock Stretch [s]` 才會計入 stretch。>100 µs 是 noticeable stretch；達到 GUI 預設 25 ms 才是 SMBus timeout。 |

若要測試缺少 STOP 的 raw physical state，請另保存 raw capture；decoded event CSV 只能表達「解析到的事件沒有 STOP」。

## 4. 五個 tabs：每頁先做什麼

### 4.1 `📈 數位方波與協定軌 (Waveform)`

選一筆 transaction，確認畫面標示是 `Reconstructed` 還是 `Measured Raw Digital`。Decoded CSV 的方波是協定重建；raw digital 才來自 SCL/SDA 0/1 samples。Aggregate row 即使 ACK 歸屬不明，已知的 data bytes 仍會保留在協定軌上，對應的 ACK slot 標成 `UNKNOWN`，不會被當成成功。Raw capture 最後的 STOP 若沒有下一個 edge，圖上的小寬度只是 **display-only marker**，不是量到的 STOP duration。Read 最後的 controller NACK 在協定軌上是正常終止，不等於 anomaly。圖表軸與 status 的詳細定義請看[附錄 A](appendix_chart_guide.md)。

### 4.2 `🚨 異常診斷 (Anomalies)`

先記錄 `severity`、`issue code`、transaction/address 與 evidence，再閱讀 hypotheses。`I2C_ADDR_NACK`、`I2C_DATA_NACK`、`I2C_MISSING_STOP`、`I2C_LONG_CLOCK_STRETCH`、`I2C_SMBUS_TIMEOUT` 代表不同觀察；原因文字是待驗證假說，不是 root-cause proof。Read-final NACK 不會被列為 `I2C_DATA_NACK`。

### 4.3 `📊 匯流排時序與健康圖表`

先看 frequency sample count、evidence label 與 timestamp availability，再看 histogram/timeline。報告中的 **Frequency Spread (peak-to-peak)** 是 `(max-min)/avg` 的樣本散布；舊欄位名 **Clock Frequency Jitter** 目前只是相容別名，不是嚴格定義的 cycle-to-cycle jitter。表格的 Health Grade 是目前 transaction evidence 的排查排序摘要，**不是 physical health grade、電氣 pass/fail 或晶片良率**。Timeline 的 `NO STOP` 與 `ABORTED` 分別代表缺少 STOP 與 transport abort；完整 axes/status/threshold 規則放在[附錄 A](appendix_chart_guide.md)。

### 4.4 `📜 封包交易列表`

逐列核對 transaction ID、Time (s)、7-bit address、R/W、address ACK、bytes/data 與 semantic summary。JSON report 中每筆交易另有 canonical `status` 欄位；GUI timeline 使用同一判定來源。`ACK UNKNOWN`、`NO STOP`、`ABORTED`、`n/a` 與 `semantic withheld` 要原樣保留；不要把空欄位改讀成 ACK 或裝置型號。

### 4.5 `📝 Markdown 診斷報告`

下載 `i2c_report.md` 作為觀察紀錄；它包含輸入中實際提供的事件、timing、quality 與 hypotheses，不會把 reconstructed waveform 寫成 physical measurement。另可下載 `i2c_analysis.fwsession.json`：session 保存 report/config 與 input SHA-256，**不包含原始 capture**。沒有原始檔且 SHA 不相符時，不能宣稱可重現分析。

## 5. Board Profile、報告與 session

在 **Board Profile（選填）** 展開區貼上 `examples/data/board_yv4.yaml`，再重新分析。它可提供 bus 1、PCA9548A channel、0x20/0x48/0x50/0x58 的名稱、category、register width 與 PMBus command mapping，讓報告更容易對照 schematic。Profile 是使用者提供的拓撲/命名輸入；它不會把 address candidate 變成已量測的晶片身份，也不會替缺失的 ACK、timing 或 power evidence 背書。

目前 decoded/raw input contract 沒有保存 bus number；若 profile 在不同 bus 對同一 7-bit address 有不同裝置，工具會列出 `I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS` 並 withheld device-specific semantic，不會任意挑第一個 bus。單純在 CSV 加上未被契約支援的 `Bus` 欄位不會消除歧義；請改用只保留唯一 address mapping 的 profile，或在匯入前按 bus 分檔並分別分析。

建議保存下列三件事：

1. 原始 capture（不可只保存 Markdown）。
2. 匯入檔名、input mode、SMBus timeout、board profile 版本。
3. Markdown report、session JSON 與 SHA-256；若重跑結果不同，先比對 capture/profile/tool version。

## 6. 資深工程師 workflow 與 self-check

資深 review 可以用這條單線流程：

1. **定義輸入**：標記 decoded aggregate、decoded per-byte、raw digital 或 text trace，並記下單位。
2. **保存證據**：先保存原始檔與 SHA，再分析；不要只貼 GUI screenshot。
3. **找第一個可驗證差異**：address NACK、data NACK、missing STOP、stretch 或 semantic truncation，分別回到 driver log、board profile、datasheet 或 raw edge。
4. **寫假說與區分測試**：每一個 hypothesis 都要有下一個能使它失敗的量測；報告中的原因文字不等於已證明根因。
5. **控制寫入風險**：任何 i2c-tools/driver write 前重新核對 bus、7-bit address、register width/endian、data 與裝置 power/reset 狀態。

離開第 1 頁前，逐項自問：

- 我能說出這份輸入的欄位與單位嗎？
- ACK/NACK 是 per-byte 可歸屬，還是 aggregate unknown？
- 這個 NACK 是 slave rejection，還是 read-final controller termination？
- Frequency、stretch、timeline 的 evidence level 與 sample count 在哪裡？
- Health Grade 是否被誤讀成 physical grade？
- Report/session 是否仍保留原始檔、SHA 與未驗證限制？

若任何一題答不出來，先停在「待確認」，不要把報告升級成硬體根因結論。

## 7. 規格與證據邊界參考

協定名詞與 timing threshold 應以目標平台採用的正式版本為準；本工具的報告只呈現輸入中實際可觀察的 evidence：

- [NXP UM10204 I2C-bus specification and user manual Rev. 7.0 (2021-10-01)](https://www.nxp.com/docs/en/user-guide/UM10204.pdf)：START/STOP、ACK、Repeated START 與 I2C timing 定義。
- [SMBus Specification v3.3.1 (2024-10-20)](https://www.smbus.org/specs/SMBus_3_3_1_20241020.pdf)：SMBus timeout 等規範語境；實際門檻仍由 GUI 設定與來源 timing evidence 決定。
- [PMBus current specifications](https://pmbus.org/current-specifications/)：PMBus command、data format 與 revision 來源；address candidate 或缺少 payload 時不應自行補語意。

這些規格連結可以定義「應該如何」，但不能把 decoded table、ideal waveform 或 synthetic fixture 變成目標板的實測證據。
