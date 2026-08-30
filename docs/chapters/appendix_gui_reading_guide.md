# 附錄 B：17 個 GUI 頁面的閱讀地圖

這份附錄只回答「我現在在哪一頁、先放什麼、不能證明什麼、下一步去哪裡」。每一節都有該頁的直接章節連結；I2C 圖表細節請跳到[附錄 A：圖表與證據判讀](appendix_chart_guide.md)，不要在這張地圖重複定義 axes 或 thresholds。

## 文件分工（避免同一規則散落多處）

| 文件 | Canonical ownership | 這裡只保留 |
|---|---|---|
| [ch01 I2C/SMBus/PMBus](ch01_i2c_pmbus.md) | 第 1 頁輸入契約、fixture、五個 tabs 的操作流程與預期輸出 | 具體 workflow 與下一步 |
| [附錄 A 圖表判讀](appendix_chart_guide.md) | frequency/timeline/health/anomaly 的軸、threshold、status 與 evidence 規則 | 第 1 頁連結 |
| [ch02 Packet Builder](ch02_packet_builder.md) | 第 2 頁 canonical transfer、ideal waveform、四種模板與安全 gate | 第 2 頁欄位摘要 |
| 本附錄 B | 17 個 GUI 頁面的導航與跨頁證據邊界 | 每頁入口、不能直接證明、下一步 |

## 第一次導覽

1. 在專案根目錄執行 `uv run fw-diag gui`，開啟 `http://127.0.0.1:8501`。
2. 先選一頁，讀該頁章節的輸入契約與限制，再按 GUI 的分析按鈕。
3. 把「下一步」欄位當成導航，不把頁面摘要當成 root-cause 結論。

## 一頁一頁定位

### 1. [I2C / SMBus / PMBus 診斷與波形檢視](ch01_i2c_pmbus.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| decoded CSV/text、per-byte fixture 或 raw digital `Time [s],SCL,SDA` | input contract、quality panel、transaction count、五個 tabs | decoded/reconstructed 波形不是類比量測；address candidate 不是確切型號 | 依[附錄 A](appendix_chart_guide.md)解讀圖表，再補 raw/driver/power evidence。 |

### 2. [I2C 封包模擬器與驅動產生](ch02_packet_builder.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| canonical operation（register/direct）、7-bit address、optional register offset/width/order、data 或 read length、bus number | canonical transaction preview 與 ideal waveform | 產生的 bytes/`Unknown` read placeholder 不是裝置回應 | 以 datasheet transaction review，再在安全板卡上執行。 |

### 3. [Golden 與 Failing 雙波形差分對比（Waveform Diff）](ch03_waveform_diff.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| Golden 與 Failing decoded trace，或先按 GUI 內建 pair loader | insufficient evidence、第一個 divergence、mismatch type | protocol diff 不等於 analog 或 firmware state diff | 同一時間窗補 raw edge、driver log、status register。 |

### 4. [UART 崩潰轉儲與 HardFault 分析（Crash Dump）](ch04_uart_crash.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| kernel panic/dmesg 或 Cortex-M HardFault log | RIP/CR2/call trace，或 HFSR/CFSR/stacked PC | 沒有 matching symbols/ELF 不能宣稱唯一 source line/root cause | 保存原始 log，以相同 build 的 symbols 對照。 |

### 5. [MCTP／IPMB 伺服器管理協定解析](ch05_mctp_ipmb.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 每行一個完整 hex frame | protocol/header/payload/checksum/frame count | parser output 不代表完整 DSP0236/PLDM/SPDM conformance | 用規格重算 checksum，核對 binding、EID 與平台設定。 |

### 6. [Device Tree（.dts）產生器](ch06_dts_generator.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| bus、MUX、clock-frequency、device addr/channel/name/compatible | node hierarchy、`reg`、`compatible`、clock 與 channel | template 不代表 kernel 已 probe 或 wiring 正確 | 以 schematic、DT binding、build 與 target dmesg 驗證。 |

### 7. [PCIe Config Space、AER 與 Link 降級診斷](ch07_pcie_aer.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| `lspci -xxxx`/config dump 或 `examples/data/pcie_aer_dmesg.log` | vendor/device、capability chain、link width/speed、AER status、captured TLP header | partial dump 不能證明整個 link 或唯一 root cause | 保存完整 dump，對照 PCIe spec、kernel log、LTSSM/硬體量測。 |

### 8. [SPI NOR Flash 協定診斷](ch08_spi_flash.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| decoded MOSI/MISO/CS CSV 或內建 sample | opcode、WREN/WEL、busy、page boundary、JEDEC response | 沒有 raw SCLK/電壓不能宣稱 signal integrity | 對照 flash datasheet、status register 與安全 write-protect 流程。 |

### 9. [晶片暫存器 Bitfield 解碼器](ch09_register_codegen.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| register map YAML、offset、raw value | field position、mask、access、decoded value | YAML 不代表該 register read 真的來自目標硬體 | 以 datasheet revision、readback 與 reserved-bit 規則核對。 |

### 10. [C 語言 Register 巨集產生器](ch09_register_codegen.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| register YAML 與 access/reset/field 定義 | `_GET`、RW setter、W1C mask、reset constants | generated header 不是整個 driver 的 concurrency/atomicity proof | compile、review volatile/MMIO、reserved bits、RMW 與 ISR/thread 邊界。 |

### 11. [初階 Firmware 實戰除錯實驗室（Fault Arena）](ch10_fault_arena.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 內建 synthetic Case 01～20 | observed symptom、兩個 hypotheses、區分測試 | synthetic case 不是公司板卡或真實 root cause | 把同一推理流程套到原始 capture，保留 provenance。 |

### 12. [韌體除錯指南與 SOP](ch12_sop.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 問題描述與目前所有 raw/log/config evidence | L1～L7、Measured/Inferred/Reconstructed/Hypothesis/Unavailable | SOP 是分層與取證框架，不是自動 root-cause oracle | 按七步保存、分類、交叉驗證並寫出可重現結論。 |

### 13. [I2C 晶片資料庫瀏覽器](ch13_chip_db.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 7-bit 位址（如 0x50）或晶片關鍵字 | 8-bit 讀寫換算、衝突警告、8x16 位址熱力圖、晶片實戰指引 | 資料庫型號不等於實體板卡掛載晶片；無衝突不等於上電正常 | 核對板卡原理圖（Schematic）、硬體位址引腳與實體 I2C 掃描。 |

### 14. [虛擬設備模擬器實驗室](ch14_emulator.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 模擬參數（溫度/Hex 讀寫/位址位移） | 暫存器狀態、WEL/BUSY 狀態機、Page Rollover 警告、Hex Dump | 軟體狀態機不等於實體晶片；無類比訊號與實際雜訊 | 將模擬驗證過之分頁/WREN 邏輯移植至實體 Driver 並於開發板測試。 |

### 15. [協定解析器 Fuzz 測試](ch15_fuzz_lab.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 目標協定、隨機種子（Seed）與資料規模 | 單次解析狀態（Parsed/Handled/Crash）、批次成功率與崩潰統計 | 隨機 Fuzz 測試不等於完整官方一致性或硬體訊號驗證 | 針對 Handled/Crash 邊界輸入補強單元測試與解析器例外防禦。 |

### 16. [功能總覽與快速入門](ch16_dashboard.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 欲排查的故障徵狀或學習目標 | 3 步快速上手流程、場景推薦起點、16 大模組卡片清單 | 總覽卡片與指引不包含特定板卡診斷結論 | 依推薦跳轉至對應專屬診斷頁面，並搭配 L1~L7 SOP 進行取證。 |

### 17. [跨協定時間線關聯分析](ch17_correlation.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| I2C CSV、SPI CSV 及/或 UART Crash Log | 跨協定對齊時間線、總事件數、異常標記（紅色星號）與跨協定異常叢集 | 時間相近不等於物理因果關係；UART 預設基準點不代表絕對時間戳 | 依時間差與涉及協定縮小範圍，以示波器量測共同電源軌（如 3.3V）與 Reset 訊號。 |
