# 附錄 B：26+ 個 GUI 頁面的閱讀地圖

這份附錄只回答「我現在在哪一頁、先放什麼、不能證明什麼、下一步去哪裡」。每一節都有該頁的直接章節連結；I2C 圖表細節請跳到[附錄 A：圖表與證據判讀](appendix_chart_guide.md)，不要在這張地圖重複定義 axes 或 thresholds。

## 文件分工（避免同一規則散落多處）

| 文件 | Canonical ownership | 這裡只保留 |
|---|---|---|
| [ch01 I2C/SMBus/PMBus](ch01_i2c_pmbus.md) | 第 1 頁輸入契約、fixture、五個 tabs 的操作流程與預期輸出 | 具體 workflow 與下一步 |
| [附錄 A 圖表判讀](appendix_chart_guide.md) | frequency/timeline/health/anomaly 的軸、threshold、status 與 evidence 規則 | 第 1 頁連結 |
| [ch02 Packet Builder](ch02_packet_builder.md) | 第 2 頁 canonical transfer、ideal waveform、四種模板與安全 gate | 第 2 頁欄位摘要 |
| 本附錄 B | 26+ 個 GUI 頁面的導航與跨頁證據邊界 | 每頁入口、不能直接證明、下一步 |

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

### 12. [Board Profile 視覺化編輯器](ch11_board_profile.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 板卡基本資訊（名稱/版本）、I2C Bus 編號、時鐘速率、直連裝置與 MUX 通道裝置定義，或既有 YAML | 即時拓撲結構預覽、位址衝突警告、I2C 保留位址提醒與時鐘相容性警示 | 靜態宣告不代表實體板卡已上電或晶片已成功 probe | 下載 YAML 並套用至 I2C 診斷頁面，或結合示波器量測硬體電源與訊號。 |

### 13. [韌體除錯指南與 SOP](ch12_sop.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 問題描述與目前所有 raw/log/config evidence | L1～L7、Measured/Inferred/Reconstructed/Hypothesis/Unavailable | SOP 是分層與取證框架，不是自動 root-cause oracle | 按七步保存、分類、交叉驗證並寫出可重現結論。 |

### 14. [I2C 晶片資料庫瀏覽器](ch13_chip_db.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 7-bit 位址（如 0x50）或晶片關鍵字 | 8-bit 讀寫換算、衝突警告、8x16 位址熱力圖、晶片實戰指引 | 資料庫型號不等於實體板卡掛載晶片；無衝突不等於上電正常 | 核對板卡原理圖（Schematic）、硬體位址引腳與實體 I2C 掃描。 |

### 15. [虛擬設備模擬器實驗室](ch14_emulator.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 模擬參數（溫度/Hex 讀寫/位址位移） | 暫存器狀態、WEL/BUSY 狀態機、Page Rollover 警告、Hex Dump | 軟體狀態機不等於實體晶片；無類比訊號與實際雜訊 | 將模擬驗證過之分頁/WREN 邏輯移植至實體 Driver 並於開發板測試。 |

### 16. [協定解析器 Fuzz 測試](ch15_fuzz_lab.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 目標協定、隨機種子（Seed）與資料規模 | 單次解析狀態（Parsed/Handled/Crash）、批次成功率與崩潰統計 | 隨機 Fuzz 測試不等於完整官方一致性或硬體訊號驗證 | 針對 Handled/Crash 邊界輸入補強單元測試與解析器例外防禦。 |

### 17. [功能總覽與快速入門](ch16_dashboard.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 欲排查的故障徵狀或學習目標 | 3 步快速上手流程、場景推薦起點、16 大模組卡片清單 | 總覽卡片與指引不包含特定板卡診斷結論 | 依推薦跳轉至對應專屬診斷頁面，並搭配 L1~L7 SOP 進行取證。 |

### 18. [跨協定時間線關聯分析](ch17_correlation.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| I2C CSV、SPI CSV 及/或 UART Crash Log | 跨協定對齊時間線、總事件數、異常標記（紅色星號）與跨協定異常叢集 | 時間相近不等於物理因果關係；UART 預設基準點不代表絕對時間戳 | 依時間差與涉及協定縮小範圍，以示波器量測共同電源軌（如 3.3V）與 Reset 訊號。 |

### 19. [互動式教學導覽](ch16_dashboard.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 學習路徑選擇（零基礎入門 / 已有硬體經驗 / 進階使用） | 6 大步驟互動式演練（I2C 解碼、NACK 異常、波形重建、SPI Flash、UART Panic、Board Profile）與進度追蹤 | 範例演練成功不代表目標硬體無未知 bug | 完成學習後前往實際協定診斷頁面載入真實 capture 檔案。 |

### 20. [附錄 A 圖表與證據判讀指南](appendix_chart_guide.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 第 1 頁產生的五個 Tabs 分析圖表與異常代碼 | Measured / Source-provided / Reconstructed / Inferred / Hypothesis / Unavailable 證據標籤分類與閾值定義 | 圖表統計數據不代表類比訊號完整性或物理損壞 | 對照證據等級補足示波器實體量測或硬體電源測試。 |

### 21. [多工作階段趨勢分析](ch18_session_analytics.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 多個 `.fwsession.json` 檔案 | 趨勢雙軸折線圖（異常數 vs 交易數）、Session 列表與健康狀態 | 趨勢改善不代表底層硬體無未擷取到的零星異常 | 針對異常尖峰的特定 Session 載入原始 capture 做協定層深度分析。 |

### 22. [PDF 報告匯出](ch19_pdf_export.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 各協定分析產生的結構化診斷結果 | PDF 匯出預覽、標題、中繼資料橫幅、表格與程式碼區塊 | 靜態 PDF 報告不包含互動式圖表與原始未解碼波形 | 保存 PDF 作為驗收記錄，原始 capture 與 JSON 檔另外歸檔保存。 |

### 23. [協定 A/B 對比分析（Protocol Diff）](ch20_protocol_diff.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 目標協定（I2C/SPI/UART/PCIe/MCTP）、Baseline 與 Candidate 雙側追蹤或日誌 | 4 組 KPI 指標卡片、判定 Banner、新增/已解決/共同項目清單 | 協定層差異不代表實體層類比電氣特性相同 | 對照差異清單鎖定首個分歧點，結合示波器量測電源與匯流排訊號。 |

### 24. [Session A/B 對比（Session Comparison）](ch21_session_compare.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| Baseline 與 Candidate 兩份 `.fwsession.json` 檔案或示範資料 | 改善/退化/持平判定徽章、Delta 指標卡片、詳細指標對比矩陣 | 結構化摘要對比不等於重新解碼底層波形；跨協定比對僅供參考 | 核對 Delta 數據，若判定退化則依 Session 的 `capture_sha256` 取出原始檔深查。 |

### 25. [批次分析（Batch Analysis）](ch22_batch_analysis.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| 多個 `.csv`、`.log`、`.txt` 或 `.hex` 檔案，選擇自動偵測或指定協定 | 總檔案數/成功/警告/錯誤統計卡片、結果彙總表、ZIP 報告打包 | 批次分析成功只代表無已知異常，不保證覆蓋所有硬體 corner case | 下載 ZIP 報告包檢閱各檔案詳情，將 SARIF 匯入 CI/CD 或集中管理系統。 |

### 26. [偏好設定（Settings & Preferences）](ch23_settings.md)

| 先放什麼 | 先看什麼 | 不能直接證明 | 下一步 |
|---|---|---|---|
| I2C Timeout、語系、主題、資料列數上限、SPI Page Size 參數 | 目前生效設定摘要看板（5 組指標）、即時套用狀態 | 偏好設定僅調整本機分析門檻與介面外觀，不改變實體硬體暫存器 | 依測試規格微調門檻後，返回協定診斷頁面進行標準化判定。 |
