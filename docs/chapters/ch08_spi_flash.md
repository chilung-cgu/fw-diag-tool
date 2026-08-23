# 第八章：SPI NOR Flash 協定診斷

## 這個頁面在做什麼？

SPI NOR Flash 是伺服器與嵌入式系統中儲存 BIOS/UEFI 韌體的核心元件。
當 BIOS 刷新失敗、開機讀取錯誤或韌體損毀時，你需要用邏輯分析儀抓取 SPI 匯流排上的通訊，
分析 Flash 晶片是否正確回應指令。

## 怎麼操作？

1. 進入 GUI 第 8 頁 **「⚡ SPI Flash 協定診斷」**。
2. 上傳 Saleae Logic 2 匯出的 SPI CSV 檔案（包含 MOSI, MISO, Enable 欄位）。
3. 工具自動解析所有交易並顯示診斷報告。

若時間欄位不是有限的非負數、時間倒退、MOSI/MISO 不是 `0..255`（或 `0x00..0xFF`），
或 CS/Enable 不是 active-low 的 `0/low/false/asserted` 或 inactive 的
`1/high/true/deasserted`，工具會拒絕該檔案；這比把錯誤 byte 靜默截斷後繼續分析更安全。
請先修正 analyzer export 或欄位 mapping，再重新上傳。

## 怎麼看懂輸出結果？

### 頂部 4 大 KPI 指標

| 指標 | 意義 | 白話解釋 |
|---|---|---|
| 總傳輸次數 | 抓到幾筆完整的 SPI 交易 | 每次 CS 拉低到拉高算一筆 |
| 讀取次數 | Read Data (0x03) 或 Fast Read (0x0B) 的次數 | BIOS 開機時會大量讀取 |
| Page Program 寫入 | Page Program (0x02) 的次數 | 刷新 BIOS 時會出現 |
| 異常事件 | 目前規則偵測到的問題數量 | 0 只表示沒有命中已支援規則，不等於完整合規 |

### 識別晶片型號

工具會自動解析 JEDEC ID (0x9F) 指令的回應：

| JEDEC ID | 晶片型號 | 容量 |
|---|---|---|
| EF 40 18 | Winbond W25Q128 | 128 Mbit / 16 MB |
| C2 20 17 | Macronix MX25L64 | 64 Mbit / 8 MB |
| 20 BA 18 | Micron N25Q128 | 128 Mbit / 16 MB |

### 常見異常與排查

| 異常代碼 | 白話解釋 | 優先確認項目 |
|---|---|---|
| **SPI_WRITE_NO_WREN** | Page Program 前沒有觀察到 0x06 WREN | 確認 capture window、WEL 狀態與驅動流程 |
| **SPI_PAGE_PROGRAM_WRAP** | 寫入範圍可能跨越裝置 page boundary | 依該 flash datasheet 的 page size 與 wrap 行為分段 |
| **SPI_TRUNCATED_TX** | 已解碼交易缺少預期欄位 | 確認 analyzer 設定、CS#、capture window、DMA/transfer length |
| **SPI_JEDEC_LINE_FAULT** | JEDEC 回應為全 0xFF 或全 0x00 | 可能是 mode/CS#/供電/MISO/裝置狀態或 analyzer mapping；需要其他量測區分 |

> [!IMPORTANT]
> 目前輸入是 analyzer 已解碼的 SPI CSV；沒有 raw SCLK/MOSI/MISO/CS edge 時，工具不能驗證實際 CPOL/CPHA timing 或 signal integrity。

## 測試資料

使用 `examples/data/spi_w25q128_sample.csv` 進行演練，
該檔案包含 JEDEC ID 讀取、WREN、Page Program 與 Read Data 的完整流程。
