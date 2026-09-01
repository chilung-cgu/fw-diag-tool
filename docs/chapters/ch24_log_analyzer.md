# 系統日誌關聯分析 (System Log Correlation & Incident Triage)

## 核心概念與為什麼需要日誌分析

在伺服器硬體與韌體開發過程中，當系統發生故障或感測器異常時，工程師面臨的第一道難題往往是海量日誌的篩選與關聯。傳統除錯模式通常是由工程師手動使用 `grep` 搜尋 `dmesg` 或 `journalctl`，然而：

- **日誌分散且雜訊高**：一次開機或異常重啟可能產生數千至數萬行日誌，核心錯誤容易被一般資訊淹沒。
- **孤立事件難以拼湊全貌**：I2C 匯流排逾時、PCIe AER 錯誤、感測器讀取失敗往往互為因果，單看單一行訊息難以還原事發時間軸與因果鏈。
- **缺少硬體拓撲對映**：日誌中僅記載 `i2c-1: client at 0x50` 或 `0000:01:00.0`，工程師必須來回對照原理圖與 Device Tree 才能得知受影響的晶片是哪一顆。

本工具提供 **Top-Down 系統級日誌診斷工作流**。日誌分析作為韌體除錯的第一站，能自動剖析 Linux Kernel `dmesg` 與 OpenBMC `journalctl`，提取結構化硬體事件，依時間與匯流排拓撲聚合為「異常事件群組 (Incidents)」，並直接引導工程師跳轉至對應的協定分析頁面。

---

## 支援的日誌類型與特徵庫

系統日誌分析引擎內建針對韌體與硬體錯誤的特徵庫（Pattern Library），支援以下日誌來源格式：

- **Linux Kernel `dmesg`**：標準核心環形緩衝區日誌（含時間戳如 `[ 10.123456]`）。
- **OpenBMC `journalctl`**：systemd 結構化系統日誌（含服務名稱如 `psusensor[1024]`、`entity-manager[512]`）。
- **Mixed 混合日誌**：串列埠 (UART) 抓取之開機綜合輸出，同時包含 Bootloader、Kernel 與 Userspace 日誌。

### 涵蓋的 10+ 大硬體子系統

| 子系統 (Subsystem) | 識別特徵與常見錯誤簽章 | 診斷指引與影響 |
|---|---|---|
| **I2C** | `i2c_designware`, `tx abort`, `timeout waiting for bus`, `client at 0x..: -ENXIO` | 匯流排仲裁遺失、SCL Clock Stretching 逾時、從端未回應 NACK |
| **PCIe** | `pcieport`, `AER`, `Uncorrectable error`, `Data Link Layer Link Degraded` | PCIe 鏈路降級、未更正錯誤、TLP 接收錯誤 |
| **HWMON** | `hwmon`, `sensor not available`, `read failed -110`, `read error` | 硬體監控驅動讀取失敗、通訊中斷 |
| **Thermal** | `thermal_zone`, `critical temperature`, `throttling`, `temperature above threshold` | 晶片過溫警報、散熱調節、緊急降頻 |
| **Watchdog** | `watchdog`, `watchdog0: watchdog did not stop`, `nowayout`, `reboot` | 硬體看門狗觸發、系統無回應逾時重啟 |
| **Power** | `psusensor`, `PowerState`, `chassis power state`, `power supply lost` | 機殼電源狀態轉換、PSU 供電遺失、電源軌異常 |
| **SPI** | `spi-nor`, `spi_master`, `unrecognized JEDEC id`, `erase timed out` | Flash JEDEC ID 讀取錯誤、抹除/寫入逾時 |
| **MCTP** | `mctp`, `mctp_i2c`, `packet dropped`, `binding failed` | 伺服器管理協定封包丟失、端點初始化失敗 |
| **GPIO** | `gpio`, `gpiod_`, `failed to request GPIO`, `interrupt error` | 腳位資源衝突、中斷註冊失敗 |
| **USB** | `usb`, `device descriptor read/64, error`, `over-current` | USB 列舉失敗、過電流保護觸發 |

---

## GUI 操作教學

進入 Web 介面側邊欄 **「系統日誌」** 區塊的 **「📋 系統日誌關聯分析 (Log Analyzer)」** 頁面。

### 步驟 1：輸入日誌與載入範例

1. **選擇載入模式**：
   - **快速載入範例**：可直接點擊「I2C 匯流排錯誤範例」、「PCIe AER 錯誤範例」或「OpenBMC 服務錯誤範例」一鍵填入標準日誌。
   - **自訂檔案上傳**：支援拖曳上傳 `.log`、`dmesg.txt` 或 `journalctl.txt` 檔案。
   - **貼上文字**：可直接將終端機複製之日誌內容貼入文字方塊中。
2. **選擇板級拓撲 (Board Profile)**（選填）：可載入板卡設定檔（如 `board_yv4.yaml`）啟用硬體關聯對映。
3. 點擊 **「🚀 開始關聯分析」** 按鈕。

### 步驟 2：四大 KPI 指標看板

分析完成後，頂部呈現 4 組即時指標卡片：

- **總日誌行數 (Total Lines)**：分析的原始日誌文字總行數。
- **辨識硬體事件 (Detected Events)**：特徵庫成功比對並提取的硬體錯誤事件數量。
- **關聯異常群組 (Correlated Incidents)**：時間與拓撲聚合後收斂出的獨立故障事件數。
- **涉及子系統 (Affected Subsystems)**：受波及的硬體子系統種類數量。

### 步驟 3：異常事件群組 (Incidents) 與導航

系統將相關聯的 LogEvents 聚合成獨立的 Incident 卡片：

- **嚴重性徽章**：明確標示 CRITICAL (紅色)、ERROR (橘色)、WARNING (黃色)、INFO (藍色)。
- **根本原因推論 (Root-Cause Hypothesis)**：根據子系統錯誤碼自動給出初步故障推論。
- **建議處置作為 (Recommended Actions)**：條列式提供排查步驟（如檢查供電軌、量測 Pull-up 電阻、核對 MUX 通道）。
- **板級拓撲對映 (Board Context)**：自動標示目標匯流排對應的晶片型號與用途。
- **相關工具跳轉按鈕**：點擊按鈕可直接跳轉至本工具的 **I2C 診斷**、**PCIe 診斷** 或 **UART 診斷** 頁面載入進一步波形。

### 步驟 4：視覺化圖表與時間軸

- **子系統分佈圖 (Subsystem Distribution)**：圓餅圖與長條圖呈現各子系統錯誤佔比。
- **嚴重性分佈 (Severity Distribution)**：量化統計各級別事件比例。
- **事件時間軸 (Event Timeline)**：依日誌時間戳排序，視覺化標示各事件發生的先後順序與時間差。

---

## 板級拓撲 (Board Profile) 關聯加值

單純的日誌訊息僅有抽象的 Bus 編號與 Address：

```text
[   10.123600] i2c-1: client at 0x50: No such device or address (-ENXIO)
```

當在分析時提供板級拓撲 YAML 檔（`--board-profile board_yv4.yaml`）時，分析引擎會自動查詢拓撲資料庫，進行語意增強：

- **目標晶片識別**：將 `Bus 1, Addr 0x50` 自動解析為 `AT24C64 (Baseboard FRU EEPROM)`。
- **驅動與相容性**：標註 Compatible 字串 `atmel,24c64`。
- **MUX 通道與上游路徑**：若裝置位於 I2C MUX 後方，自動還原上游切換通道拓撲。

---

## A/B 日誌差分對比分析 (Log Diff)

除了單一日誌分析，工具亦支援兩份日誌的差分比對：

- **基準日誌 (Baseline)**：正常開機或修復前之日誌。
- **待測日誌 (Candidate)**：異常開機或改版後之日誌。

Log Diff 引擎會自動比對雙方的事件特徵簽章，歸類為：
- **新增事件 (New Events)**：待測日誌中新出現的故障。
- **已解決事件 (Resolved Events)**：待測日誌中已消失的歷史故障。
- **共通事件 (Common Events)**：雙方皆持續存在的未修復問題。

---

## CLI 命令列使用指南

所有分析功能皆可在終端機或 CI/CD pipeline 中透過命令列無縫執行。

### 1. 系統日誌關聯分析

```bash
# 基本分析並輸出摘要
uv run fw-diag log analyze dmesg.log

# 搭配板級拓撲並匯出 Markdown 診斷報告
uv run fw-diag log analyze dmesg.log --board-profile examples/data/board_yv4.yaml --md log_report.md

# 匯出 JSON 格式結構化資料供自動化解析
uv run fw-diag log analyze journalctl.log --json log_report.json

# 設定 CI 門檻：若發現 ERROR 或 CRITICAL 級別問題則以非 0 代碼離開
uv run fw-diag log analyze dmesg.log --fail-on error
```

### 2. A/B 日誌差分對比

```bash
# 比對基準版本與待測版本日誌
uv run fw-diag log diff baseline_dmesg.log candidate_dmesg.log

# 將差分結果輸出為 JSON
uv run fw-diag log diff baseline_dmesg.log candidate_dmesg.log --json log_diff.json
```

---

## 證據邊界與限制

系統日誌分析是頂層排查與問題收斂的利器，但在物理與硬體層面仍有其證據邊界：

- **啟發式特徵匹配不是物理證明**：日誌分析引擎基於正則表達式與特徵庫進行分類，屬於「Inferred（推論）」與「Hypothesis（假設）」層級。
- **核心報錯不等於硬體晶片損壞**：日誌中的 `-ENXIO` 或 `tx abort` 可能源於電源未開啟、I2C MUX 通道切換錯誤、Reset Pin 被拉低或軟體驅動時序設定不當，而非晶片本身損壞。
- **時間戳記精度與同步限制**：Kernel `dmesg` 時間為開機相對秒數，而 `journalctl` 採用系統牆上時鐘 (Wall-clock time)。混合日誌分析時的時間軸對齊屬於概略關聯，無法達到示波器奈秒級精度。
- **後續實體驗證 SOP**：透過本頁面定位到可疑硬體端點（如 I2C 0x50 或 PCIe 01:00.0）後，應進一步使用本工具之 **I2C 診斷**、**PCIe AER 診斷** 或以實體示波器量測電源軌與匯流排訊號進行最終確認。

