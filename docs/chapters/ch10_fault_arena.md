# 初階韌體（Firmware）20 大實戰故障演練場（Fault Arena）

## 這個頁面在做什麼？

這是一個互動式學習庫，收錄 20 個合成（synthetic）故障情境，題材涵蓋伺服器與嵌入式系統。
每個案例都可重現「現象、可能假設、驗證步驟」的關係；資料不是實際公司的擷取檔（capture），
情境文字中的可能原因也不保證是唯一根因（root cause）。請把它當成練習觀察與設計下一個測試的起點。

## 怎麼操作？

1. 進入 GUI 第 11 頁 **「🏆 初階 Firmware 實戰除錯實驗室（Fault Arena）」**。
2. 從下拉選單選擇任一個案例；案例名稱中的 `Case NN` 是固定識別碼，請保留在紀錄中。
3. 按 **「🚀 載入此案例模擬資料並自動分析」** 後，先查看合成輸入，再閱讀報告與排查 SOP。
4. 將案例中的假設和真實板卡的 schematic、datasheet、register、log 及量測結果分開記錄。

## GUI 會顯示哪些輸出？

按下按鈕後，頁面固定依序呈現三段內容；它們的證據等級不同，不要混在一起解讀：

| 畫面區段 | 內容 | 正確讀法 |
|---|---|---|
| 案例合成測試資料（Synthetic Test Data） | `📄 檢視案例合成測試資料` 展開器中的 CSV、文字或 Hex 內容 | 這是 parser 實際收到的輸入；先確認格式、封包邊界與案例編號 |
| 自動診斷分析結果（Automated Diagnostic Result） | 依案例類型產生的 I2C、SPI、PCIe、UART 或 MCTP/IPMB Markdown 報告 | 先讀摘要、異常代碼／旗標與資料限制，再把假設列為待驗證方向 |
| 標準排查流程與根因診斷（SOP & Root Cause） | 故障現象（Observed symptom）、練習假設（Hypothesis）、區分測試（Discriminating test） | 這是教學提示，不是由合成資料證明的 root cause |

分析完成後可按 **「下載案例 Markdown 診斷報告」**，檔名為 `fault_arena_case_NN.md`。GUI
不會把案例原始輸入自動寫入 `examples/data/`；若要保存，請從合成資料展開器另行複製，並把
`Case NN`、選取的案例與報告檔名一起記錄。

案例由 `src/fw_diag_tool/fault_arena/fixtures.py` 在執行期產生，並直接送到對應 parser；
因此不要把 `case01_address_nack.csv` 等 fixture 名稱當成已存在於 `examples/data/` 的檔案路徑。

## 20 大案例分類總覽

### I2C／SMBus 類別（Case 01~05）

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 01 | 位址 NACK（Address NACK） | Slave 未上電、A0A1A2 浮接，或混用 7-bit／8-bit 位址 | 量測 VCC，查位址腳位與 bus 設定 |
| Case 02 | 資料 NACK（Data NACK） | EEPROM 內部 tWR 寫入週期忙碌 | 等待 5 ms 或使用 ACK Polling |
| Case 03 | 時鐘延展（Clock Stretching）超過 25 ms（Clock Stretching > 25ms） | Slave MCU 卡在中斷處理 | 執行 SCL 9-Clock Reset，並保留 reset log |
| Case 04 | EEPROM 頁面回繞（Page Rollover） | 寫入跨頁後覆蓋同一頁的既有資料 | 依 datasheet 的 Page Size 分段寫入 |
| Case 05 | MUX 多通道衝突（MUX conflict） | PCA9548A 同時開啟多個下游通道 | 切換為 1-hot 模式並確認每個 channel |

### PMBus／PCIe 類別（Case 06~10）

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 06 | VOUT_TRIM 負值顯示錯誤（VOUT_TRIM signed decode） | Linear16 有號補碼未處理 | 使用 `signed=True` 解碼，並對照 `READ_VOUT` 與 profile |
| Case 07 | PCIe Gen4 降為 Gen1（Link degradation） | 金手指髒污或 SI 劣化 | 檢查金手指與 REFCLK，再看 Link status |
| Case 08 | 完成逾時（Completion Timeout） | 目標設備 AXI 狀態機死鎖 | 檢查 CTO 設定、Requester／Completer 與 kernel log |
| Case 09 | 格式錯誤 TLP（Malformed TLP） | 封包長度超過 MPS | 檢查 Max Payload Size 與 TLP header |
| Case 10 | 毒化 TLP（Poisoned TLP） | 上游記憶體 ECC 錯誤 | 排查 DRAM ECC、poison 產生端與資料路徑 |

### SPI Flash 類別（Case 11~14）

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 11 | 頁面寫入（Page Program）無效（Page Program rejected） | 擷取範圍內未觀察到 0x06 WREN 或 status-read，WEL 狀態未知 | 擴大 capture window，確認 0x06 WREN／RDSR（0x05）與 WEL=1；預期 `SPI_WEL_STATE_UNKNOWN` |
| Case 12 | 資料覆蓋（頁面緩衝區回繞；Page Buffer Wrap-Around） | 256B Page Buffer Wrap-Around | 依 page size 計算 chunk 大小 |
| Case 13 | JEDEC 全 0xFF（JEDEC all 0xFF） | MISO 浮接或 Flash 未上電 | 量測 VCC，檢查 CS#、MISO 與供電 |
| Case 14 | JEDEC 全 0x00（JEDEC all 0x00） | MISO 對地短路或匯流排被箝位 | 檢查走線短路、箝位與 CS# |

### Crash Dump 類別（Case 15~18）

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 15 | 核心 NULL 指標（Kernel NULL Pointer） | `kzalloc` 失敗未檢查 | 使用 `addr2line -e vmlinux` 對照 RIP 與 symbols |
| Case 16 | 除以零（DIVBYZERO） | 分母為 0 | 加入 `if (denom == 0)` 防護並遵循錯誤契約 |
| Case 17 | 未對齊存取（UNALIGNED） | `uint32_t*` 存取奇數位址 | 改用 `memcpy` 或符合專案規範的 packed 存取 |
| Case 18 | 非精確匯流排錯誤（IMPRECISERR） | 周邊時鐘未開就寫暫存器 | 依 MCU 能力評估 Write Buffer 設定並保留 fault frame |

### 伺服器管理協定類別（Case 19~20）

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 19 | PLDM 封包順序錯亂（PLDM sequence error） | `PktSeq` 未正確管理 | 檢查 `SOM`／`EOM`／`Seq` 與重組順序 |
| Case 20 | IPMB 校驗碼失敗（Checksum FAIL） | 資料損毀或位址錯誤 | 檢查 `(sum+chk)&0xFF==0` 並重新計算兩段 checksum |

> **說明：**
>
> 表中的「練習假設」只是第一個要驗證的方向。實際工作應保留替代假設，並以 schematic、datasheet、register、log 與量測結果逐一排除。

> **Case 11 的證據邊界：**
>
> `SPI_WEL_STATE_UNKNOWN` 表示本次 capture 沒有足夠的 WREN／status-read 證據，無法證明 Page Program
> 當下的 WEL latch 狀態；它不是「一定沒有送出 WREN」。`SPI_WRITE_NO_WREN` 只適用於 Status Register
> 寫入時，且先前已明確觀察到 WEL=0、又沒有 0x06（WREN）或 0x50（Volatile WREN）的情況。
