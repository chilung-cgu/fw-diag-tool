# I2C / SMBus / PMBus：第 1 頁任務導向實驗室

本章專門指引 GUI 第 1 頁 **「📊 I2C / PMBus 診斷與波形檢視」**。核心目標是將邏輯分析儀匯出的 capture 轉換為具備可追溯證據的工程觀察：先確認輸入格式契約（Input Contract），再深入解讀五個分頁（Tabs），最後匯出診斷報告與可重現 Session。圖表軸線、顏色、門檻值（Threshold）與異常代碼（Issue Code）的嚴格定義集中於[附錄 A：圖表與證據判讀](appendix_chart_guide.md)。

## 1. 兩分鐘完成第一次分析

先在專案根目錄啟動 GUI：

```bash
uv run fw-diag gui
```

1. 選左側第 1 頁，在「教學範例」先選 `套件解碼分析器（18 筆）`，輸入模式會是 `解碼分析器 CSV（decoded_csv）`。
2. 按 **載入內建測試波形**；要練習 raw 或 text，改選對應範例後再按同一按鈕。
3. 先讀「資料證據與限制」，再看 KPI；不要把綠色狀態當成硬體已驗證。
4. 依序開啟封包交易列表、數位方波與協定軌、異常診斷、匯流排時序與健康圖表、Markdown 診斷報告五個分頁（tabs）；先選交易，波形才會聚焦同一筆。
5. 另用本章的 raw digital fixture 重跑一次，確認哪些數字是 measured、哪些仍是 unavailable。

內建按鈕載入的是套件資源 `builtin:saleae_normal_pmbus_eeprom.csv`，不是 `examples/data/i2c_golden.csv`。目前可驗證的結果是 **18 transactions、53 physical events、0 protocol issues**。資料品質仍會列出：

- `I2C_EEPROM_PROFILE_UNAVAILABLE`：0x50 的 EEPROM 寬度/page profile 未指定。
- `I2C_PMBUS_PAYLOAD_TRUNCATED`：一個 PMBus command 缺少規格所需 response bytes，該語意不完整。
- `I2C_TIMING_UNAVAILABLE`：沒有每 byte duration/bitrate，因此平均 clock 與 jitter 顯示 `不可用`。

這些是輸入證據的狀態，不是「18 筆都通過硬體測試」的宣告。

## 2. 三種輸入契約：欄位、單位與可回答的問題

先在檔案來源上做分類。工具不會把缺少的欄位補成 0、ACK 或預設頻率。

### 契約 A：解碼分析器 CSV（Decoded Analyzer CSV；aggregate 或 per-byte）

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

### 契約 B：原始數位轉態 CSV（Raw digital transition CSV）

```csv
Time [s],SCL,SDA
0.000000,1,1
0.000005,1,0
0.000010,0,0
```

上面 3 行只展示欄位名稱與 `0/1` 值域，**刻意不是可完成解碼的 capture**；它沒有完整的 9-bit byte、ACK 與 STOP。要直接執行分析，請使用完整的 `examples/data/i2c_raw_100khz.csv`（或 GUI 的 `原始數位量測（100 kHz、1 筆）` 範例）。

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

## 3. 真實 Fixture 實戰解析：以 i2c_golden.csv 為例

### 3.1 匯入 i2c_golden.csv 的 Step-by-Step 操作與關鍵觀察

當你在 GUI 選擇 `解碼分析器 CSV（decoded_csv）` 並上傳 `examples/data/i2c_golden.csv` 後，請依以下步驟進行觀察與學習：

**步驟 1：檢視上方 KPI 摘要與資料證據面板**
- **總傳輸次數（Total Transactions）**：顯示 `5` 筆交易。
- **已證實協定異常（Protocol Anomalies）**：顯示 `0` 筆。
- **平均時鐘頻率（Average SCL Clock）與抖動（Jitter）**：均顯示 `不可用 (Unavailable)`。
- **展開「⚠ 資料證據與限制（Data Quality Limitations）」**：
  - 工具會明確標註 `I2C_ACK_AGGREGATE_UNATTRIBUTABLE` 與 `I2C_ACK_UNAVAILABLE`。
  - 若 CSV 含有單一 `Duration` 欄位，會標記 `I2C_TIMING_AGGREGATE_UNATTRIBUTABLE`。
  - **核心觀念**：為什麼沒有異常卻顯示資料品質警告？因為 `i2c_golden.csv` 屬於 **Aggregate 格式**（單一列包含多個 Data Bytes，卻只有一個整體 ACK 欄位）。工具無法百分之百確定 ACK 是從機（Slave）對 Address 回應、還是對 Data 回應，因此不會憑空臆測，而是客觀保留 Unknown 狀態並保留交易形貌。

**步驟 2：切換至 📜 封包交易列表（Transactions）**
- 核對 5 筆交易：包含 0x58（PMBus）、0x50（EEPROM）、0x48（溫度感測器）與 0x20（GPIO 擴展晶片）。
- 觀察 `整體狀態 (Overall Status)` 欄位均標記為 `ACK UNKNOWN`。這體現了嚴謹工程態度：來源未給每位元組 ACK 歸屬前，不將它草率標為綠色 PASS。

**步驟 3：切換至 📈 數位方波與協定軌（Waveform）**
- 選擇 Tx #1（0x58 Write），觀察上方波形狀態標示為 **Reconstructed（協定層重建波形）**。
- SCL/SDA 是根據協定狀態機以理想 100 kHz 時序繪製，包含 START、Address (0xB0)、Data 與 STOP。
- 注意波形上的 ACK Slot 標示為 `UNKNOWN`，這正是忠實反映了 Aggregate 輸入的證據邊界。

**步驟 4：切換至 🚨 異常診斷（Anomalies）**
- 頁面顯示「未偵測到任何 I2C/SMBus 時序與通訊異常」。
- 請記住：這代表在現有欄位證據下「未命中違規規則」，但因資料品質受限，資深工程師不會以此宣稱實體晶片已 100% 驗證通過。

**步驟 5：切換至 📊 匯流排時序與健康圖表（Bus Timing & Health）**
- **時鐘頻率分佈圖**：顯示 `Unavailable`（無 per-byte bitrate/duration 證據），不畫出假 0 kHz 柱狀圖。
- **交易時間軸分佈圖**：若有 Time 欄位，會依時間戳記繪製 5 筆散佈點，狀態顏色為灰色 `ACK UNKNOWN`。
- **裝置健康評等表（Device Health Summary）**：Health Grade 顯示 `N/A (ACK unavailable)`，成功率顯示 `N/A`，避免將未知誤導為滿分 A。

**步驟 6：切換至 📝 Markdown 診斷報告（Markdown Report）**
- 預覽自動產生的繁體中文報告，包含完整詮釋資料、交易明細與資料品質限制，可點擊「下載 Markdown 報告」或「下載可重現 Session」。

### 3.2 Aggregate Golden 限制對比：`i2c_golden.csv`

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
溫度 = 25.50 °C（LM75/TMP102，原始值 0x1980）
```

最後一個 read byte 的 `NACK` 是 controller 的正常讀取終止，因此不產 `I2C_DATA_NACK`。0x50 的 EEPROM profile 未指定時，報告會保留 read bytes、但對 write offset/page semantic 顯示 profile unavailable。

### 3.4 Raw digital：`i2c_raw_100khz.csv`

這個 fixture 有 **46 行（header 加 45 筆 transition samples）**。切換到 `原始數位 CSV（raw_digital；Time、SCL、SDA）` 後上傳它，預期：

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

## 4. 五大功能分頁（Tabs）：細項使用與輸出判讀教學

### 4.1 `📜 封包交易列表（Transactions）`

**【如何使用】**：
1. 上傳檔案後，直接在列表中按交易序號（ID）瀏覽所有解析完成的封包。
2. 搭配上方下拉選單 `目前交易`，可讓下一個 Waveform 分頁同步聚焦於特定封包。

**【欄位意義與輸出判讀】**：
- **時間（s；Time）**：交易開始時間戳記；若檔案無時間欄位則顯示 `不可用`。
- **從裝置位址（Address）**：7-bit 十六進位位址（如 `0x58`）。保留位址會顯示警示。
- **讀寫方向（Direction）**：`WRITE` 或 `READ`；方向不明時顯示 `UNKNOWN`。
- **位址應答（Address ACK）**：從裝置對位址的應答（`ACK` 或 `NACK`）。
- **整體狀態（Overall Status）**：整筆交易的綜合健康狀態（`ACK`、`ADDR NAK`、`DATA NAK`、`READ END NAK`、`ACK UNKNOWN`、`NO STOP`、`ABORTED`、`EVIDENCE INCOMPLETE`）。
- **解碼語意（Semantic Meaning）**：自動解碼的工程資料（如 PMBus 電壓 `READ_VIN 讀取值 = 32.0 V`、溫度 `25.50 °C`）。若資料品質不足則標註 `withheld`（保留不猜測）。

### 4.2 `📈 數位方波與協定軌（Waveform）`

**【如何使用】**：
1. 先在上方下拉選單選取欲聚焦的交易（例如 Tx #1）。
2. 放大（Zoom in）檢視 START 條件、Address 位元、ACK Slot、Data 位元與 STOP 條件。

**【輸出判讀與證據層級】**：
- **確認波形類型標籤**：
  - 若顯示 **Measured Raw Digital**：代表來自實測 SCL/SDA 0/1 取樣點，可觀察邊緣時序與 Clock Stretching。注意：raw capture 最後的 STOP 若無後續 transition，僅為 **display-only marker**，非實測寬度。
  - 若顯示 **Reconstructed**：代表根據解碼資料重建的理想時序模型，非真實類比電壓波形，不能拿來推論 Pull-up 電阻或上升時間（Rise time）。
- **Read 終止識別**：讀取交易最後一個位元組由主控端（Controller）送出 NACK（標示為 Controller NACK），隨後發送 STOP，這是標準正常終止，切勿誤判為硬體異常。

### 4.3 `🚨 異常診斷（Anomalies）`

**【如何使用】**：
1. 檢視系統過濾後的前 50 筆異常事件，展開卡片查看細節。
2. 依序閱讀「現象描述」、「可能原因假設」與「排查行動清單」。

**【輸出判讀】**：
- **嚴格區分 Issue Code**：如 `I2C_ADDR_NACK`（從機不存在/未上電）、`I2C_DATA_NACK`（寫入被拒）、`I2C_MISSING_STOP`（通訊中斷/匯流排鎖死）、`I2C_LONG_CLOCK_STRETCH`（從機處理延遲 >100 µs）、`I2C_SMBUS_TIMEOUT`（延長逾時 ≥25 ms）。
- **原因非定論**：報告中的原因文字為「待驗證假說（Hypotheses）」，非已證明的單一根因。必須搭配排查清單以示波器、Driver 日誌進一步區分。

### 4.4 `📊 匯流排時序與健康圖表（Bus Timing & Health）`

**【如何使用】**：
1. 觀察左側「時鐘頻率分佈直方圖 (Frequency Distribution)」。
2. 觀察右側「交易時序與裝置活動時間軸 (Timeline)」。
3. 檢視下方「裝置健康評等表 (Device Health Summary)」。

**【輸出判讀】**：
- **頻率散布 (Frequency Spread / Jitter)**：以 `(max-min)/avg` 計算樣本散布度。若大於 35% 會列為高抖動。
- **裝置健康評等 (Health Grade)**：計算公式為 `成功率 = (有效交易 - NACK數) / 有效交易`。A 為優秀、B 為輕微重試/延遲、D 為高 NACK 率、F 為嚴重故障、N/A 為 ACK 證據不足。**特別強調：此評等純為除錯排查優先順序之啟發式摘要，絕非晶片良率或實體電氣品質的通過宣告。**

### 4.5 `📝 Markdown 診斷報告（Markdown Report）`

**【如何使用】**：
1. 在畫面直接閱讀產出的結構化 Markdown 診斷報告。
2. 點擊「下載 Markdown 報告」匯出 `i2c_report.md` 作為專案除錯紀錄。
3. 點擊「下載可重現 Session」匯出 `i2c_analysis.fwsession.json`。注意：Session 檔保存了分析設定與輸入檔案的 SHA-256 雜湊值，**不包含原始 capture 內容**；重新載入時必須搭配同一原始檔案驗證 SHA 相符才能重現。

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
