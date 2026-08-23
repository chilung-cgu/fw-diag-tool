# 第十章：Junior FW 20 大實戰故障演練場 (Fault Arena)

## 這個頁面在做什麼？

這是一個互動式學習庫，收錄 20 個 synthetic 故障情境，題材涵蓋伺服器與嵌入式系統。
目前案例用於練習「現象、可能假設、驗證步驟」的關係，不是實際公司 capture，也不保證情境文字中的可能原因就是唯一 root cause。

## 怎麼操作？

1. 進入 GUI 第 11 頁 **「🏆 Junior FW 實戰除錯實驗室 (Fault Arena)」**。
2. 從下拉選單選擇任一個案例。
3. 頁面顯示故障情境說明與排查 SOP。

## 20 大案例分類總覽

### I2C / SMBus 類 (Case 01~05)

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 01 | Address NACK | Slave 未上電 / A0A1A2 浮接 / 7-bit vs 8-bit 搞混 | 量 VCC, 查位址腳位 |
| Case 02 | Data NACK | EEPROM 內部 tWR 寫入週期忙碌 | 等 5ms 或 ACK Polling |
| Case 03 | Clock Stretching > 25ms | Slave MCU 當機在中斷中 | SCL 9-Clock Reset |
| Case 04 | EEPROM Page Rollover | 寫入跨頁覆蓋 | 以 Page Size 分段寫入 |
| Case 05 | MUX 多通道衝突 | PCA9548A 同時開啟多通道 | 1-hot 模式切換 |

### PMBus / PCIe 類 (Case 06~10)

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 06 | VOUT_TRIM 顯示 127V | Linear16 有號補碼未處理 | signed=True |
| Case 07 | PCIe Gen4 降為 Gen1 | 金手指髒污 / SI 劣化 | 檢查金手指, REFCLK |
| Case 08 | Completion Timeout | 目標設備 AXI 狀態機死鎖 | 檢查 CTO 設定 |
| Case 09 | Malformed TLP | 封包長度超過 MPS | 檢查 Max Payload Size |
| Case 10 | Poisoned TLP | 上游記憶體 ECC 錯誤 | 排查 DRAM ECC |

### SPI Flash 類 (Case 11~14)

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 11 | Page Program 無效 | 未發送 0x06 WREN | 檢查 WEL bit |
| Case 12 | 資料覆蓋 | 256B Page Buffer Wrap-Around | 計算 chunk 大小 |
| Case 13 | JEDEC 全 0xFF | MISO 浮接 / 未上電 | 量 VCC, 檢查 CS# |
| Case 14 | JEDEC 全 0x00 | MISO 對地短路 | 檢查走線短路 |

### Crash Dump 類 (Case 15~18)

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 15 | Kernel NULL Pointer | kzalloc 失敗未檢查 | addr2line -e vmlinux |
| Case 16 | DIVBYZERO | 分母為 0 | 加 if(denom==0) 防護 |
| Case 17 | UNALIGNED | uint32_t* 存取奇數位址 | 改用 memcpy |
| Case 18 | IMPRECISERR | 周邊時鐘未開就寫暫存器 | 開啟 Write Buffer 抓精確行號 |

### 伺服器管理協定類 (Case 19~20)

| 案例 | 故障現象 | 練習假設 | 排查關鍵字 |
|---|---|---|---|
| Case 19 | PLDM 封包順序錯亂 | PktSeq 未正確管理 | 檢查 SOM/EOM/Seq |
| Case 20 | IPMB Checksum FAIL | 資料損毀或位址錯誤 | 檢查 (sum+chk)&0xFF==0 |

> [!NOTE]
> 表中的「練習假設」只是第一個要驗證的方向。實際工作應保留替代假設，並以 schematic、datasheet、register、log 與量測結果逐一排除。
