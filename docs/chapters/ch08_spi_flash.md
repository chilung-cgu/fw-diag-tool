# SPI NOR Flash 協定診斷（SPI NOR Flash Protocol Diagnostics）

## 這個頁面在做什麼？

SPI NOR Flash 是伺服器與嵌入式系統中儲存 BIOS/UEFI 韌體的核心元件。當 BIOS 刷新失敗、
開機讀取錯誤或韌體損毀時，可用邏輯分析儀擷取 SPI 匯流排通訊，分析 Flash 晶片是否正確回應
指令。這一頁只處理解碼後的交易；沒有 raw edge 時，不會把理想的 opcode 序列當成電氣量測。

## 怎麼操作？

1. 進入 GUI 第 8 頁 **「⚡ SPI Flash 協定診斷」**。
2. 上傳 Saleae Logic 2 匯出的 SPI CSV 檔案（包含 `MOSI`、`MISO`、`Enable` 欄位）。
3. 工具會解析所有交易並顯示診斷報告；若輸入欄位不明確，parser 會在邊界拒絕檔案。

### 先確認 CSV 位元組格式（CSV byte format）

- `0x20`、`0X9F` 是明確的十六進位表示。
- 全部由數字組成的裸 token（例如 `20`）按十進位解析，避免把十進位 20 靜默當成 `0x20`；需要十六進位時請加 `0x`。
- 含 `A`～`F` 的裸 token（例如 `AA`）可作為常見 analyzer 匯出的十六進位 byte。
- CSV 必須提供明確且唯一的 `Time`、`MOSI`、`MISO`、`CS/Enable` 欄位；每列都要有兩邊 byte，
  且 CS active-low 的 frame 邊界完整。

若時間欄位不是有限的非負數、時間倒退、MOSI/MISO 不是 `0..255`（或 `0x00..0xFF`），
或 CS/Enable 不是 active-low 的 `0/low/false/asserted` 或 inactive 的
`1/high/true/deasserted`，工具會拒絕檔案；這比把錯誤 byte 靜默截斷後繼續分析更安全。
請先修正 analyzer export 或欄位 mapping，再重新上傳。

## 怎麼看懂輸出結果？

### 頂部 4 大 KPI 指標（Key Performance Indicators）

| 指標 | 意義 | 白話解釋 |
|---|---|---|
| 總傳輸次數（Total Transactions） | 擷取到的完整 SPI 交易筆數 | 每次 CS 從低電位拉回高電位算一筆 |
| 讀取次數（Read Count） | Read Data（0x03）或 Fast Read（0x0B）的次數 | BIOS 開機時通常會大量讀取 |
| Page Program 寫入（Page Program Writes） | Page Program（0x02）的次數 | 刷新 BIOS 時可能出現 |
| 異常事件（Anomalies） | 目前規則偵測到的問題數量 | 0 只表示沒有命中已支援規則，不等於完整合規 |

### 識別晶片型號

工具會自動解析 JEDEC ID（0x9F）指令的回應：

| JEDEC ID | 晶片型號 | 容量 |
|---|---|---|
| EF 40 18 | Winbond W25Q128 | 128 Mbit / 16 MB |
| C2 20 17 | Macronix MX25L64 | 64 Mbit / 8 MB |
| 20 BA 18 | Micron N25Q128 | 128 Mbit / 16 MB |

### 常見異常與排查（Anomalies and Triage）

| 異常代碼 | 白話解釋 | 優先確認項目 |
|---|---|---|
| **WEL 狀態未知（SPI_WEL_STATE_UNKNOWN）** | Page Program 前沒有在本次 capture 觀察到 WREN 或 status-read；因此無法證明當下 WEL latch 狀態 | 擴大 capture window，確認 0x06 WREN、RDSR（0x05）與 WEL=1；不要把「沒看到」寫成「一定沒送」 |
| **Page Program 回繞風險（SPI_PAGE_PROGRAM_WRAP）** | 寫入範圍可能跨越裝置 page boundary | 依該 Flash datasheet 的 page size 與 wrap 行為分段 |
| **交易截斷（SPI_TRUNCATED_TX）** | 已解碼交易缺少預期欄位 | 確認 analyzer 設定、CS#、capture window、DMA/transfer length |
| **JEDEC 線路故障（SPI_JEDEC_LINE_FAULT）** | JEDEC 回應為全 0xFF 或全 0x00 | 可能是 mode／CS#／供電／MISO／裝置狀態或 analyzer mapping；需要其他量測區分 |
| **回應截斷（SPI_RESPONSE_TRUNCATED）** | command 尚未取得最低必要 bytes | 擴大 capture window，確認 CS、DMA transfer length 與 command phase |
| **回應過長（SPI_RESPONSE_OVERLONG）** | 固定寬度 command 收到額外 bytes | 檢查 CS/frame segmentation、analyzer protocol decoder 與 command 定義 |

`SPI_WRITE_NO_WREN` 的適用條件是：只有在 **Status Register 寫入** 時，且先前已明確觀察到
`WEL=0`、又沒有 `0x06`（WREN）或 `0x50`（Volatile WREN）。Page Program 之前若只是沒有
WREN／status-read 證據，WEL 是 unknown，應列 `SPI_WEL_STATE_UNKNOWN`；不能直接判定 WREN 未送出。

`SPI_RESPONSE_TRUNCATED` 或 `SPI_RESPONSE_OVERLONG` 出現時，相關 command 的語意應視為證據不足；
不要只因報告仍列出 opcode 就當成完整硬體操作。

> **重要：**
>
> 目前輸入是 analyzer 已解碼的 SPI CSV；沒有 raw SCLK/MOSI/MISO/CS edge 時，工具不能驗證實際
> CPOL/CPHA timing 或 signal integrity。這個限制也適用於 Case 11 的 WEL 判讀。

## 測試資料

使用 `examples/data/spi_w25q128_sample.csv` 進行演練；該檔案包含 JEDEC ID 讀取、WREN、
Page Program 與 Read Data 的完整流程。若要重現 Case 11，請使用 Fault Arena 產生的擷取資料，
並以 `SPI_WEL_STATE_UNKNOWN` 的證據邊界解讀結果。
