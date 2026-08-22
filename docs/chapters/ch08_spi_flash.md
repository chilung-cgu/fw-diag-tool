# 第八章：SPI / QSPI NOR Flash 協定診斷

## 這個頁面在做什麼？

SPI NOR Flash 是伺服器與嵌入式系統中儲存 BIOS/UEFI 韌體的核心元件。
當 BIOS 刷新失敗、開機讀取錯誤或韌體損毀時，你需要用邏輯分析儀抓取 SPI 匯流排上的通訊，
分析 Flash 晶片是否正確回應指令。

## 怎麼操作？

1. 進入 GUI 第 8 頁 **「⚡ SPI Flash 協定診斷」**。
2. 上傳 Saleae Logic 2 匯出的 SPI CSV 檔案（包含 MOSI, MISO, Enable 欄位）。
3. 工具自動解析所有交易並顯示診斷報告。

## 怎麼看懂輸出結果？

### 頂部 4 大 KPI 指標

| 指標 | 意義 | 白話解釋 |
|---|---|---|
| 總傳輸次數 | 抓到幾筆完整的 SPI 交易 | 每次 CS 拉低到拉高算一筆 |
| 讀取次數 | Read Data (0x03) 或 Fast Read (0x0B) 的次數 | BIOS 開機時會大量讀取 |
| Page Program 寫入 | Page Program (0x02) 的次數 | 刷新 BIOS 時會出現 |
| 異常事件 | 偵測到的協定違規數量 | 越少越好，0 表示完全合規 |

### 識別晶片型號

工具會自動解析 JEDEC ID (0x9F) 指令的回應：

| JEDEC ID | 晶片型號 | 容量 |
|---|---|---|
| EF 40 18 | Winbond W25Q128 | 128 Mbit / 16 MB |
| C2 20 17 | Macronix MX25L64 | 64 Mbit / 8 MB |
| 20 BA 18 | Micron N25Q128 | 128 Mbit / 16 MB |

### 常見異常與排查

| 異常代碼 | 白話解釋 | Root Cause |
|---|---|---|
| **SPI_WRITE_NO_WREN** | 發送了 Page Program 但沒有先發送 0x06 WREN | 韌體忘記呼叫 spi_flash_write_enable() |
| **SPI_PAGE_PROGRAM_WRAP** | 寫入位址跨越 256-byte Page 邊界 | EEPROM 內部位址指標會 Wrap 回 Page 開頭，覆蓋資料！ |
| **SPI_TRUNCATED_TX** | CS# 提前拉高，指令不完整 | CS# 線路雜訊或 DMA 長度配置錯誤 |
| **SPI_JEDEC_LINE_FAULT** | JEDEC ID 讀回全 0xFF 或全 0x00 | 0xFF = MISO 浮接/未上電；0x00 = MISO 對地短路 |

## 測試資料

使用 `examples/data/spi_w25q128_sample.csv` 進行演練，
該檔案包含 JEDEC ID 讀取、WREN、Page Program 與 Read Data 的完整流程。