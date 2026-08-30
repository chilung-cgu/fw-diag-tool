# Ch22 — 批次分析

## 功能簡介

在量產產線檢驗、多板卡同步掃描或自動化 CI/CD 流程中，逐一手動上傳與分析日誌耗時費力。批次分析（Batch Analysis）支援一次上傳多個追蹤或日誌檔案，具備智慧**協定自動偵測（Auto Protocol Detection）**能力，並行執行診斷分析，即時彙整所有檔案的狀態矩陣，最後提供一鍵打包下載所有格式診斷報告之 ZIP 封裝。

---

## 支援格式與協定自動偵測

### 支援檔案類型

單一檔案大小上限為 20 MiB，支援以下副檔名：

- **`.csv`**：Saleae Logic 等儀器匯出之 I2C 或 SPI 解碼 CSV。
- **`.log`**：系統核心傾印、Linux dmesg、UART 終端日誌。
- **`.txt`**：文字追蹤記錄、lspci 設定空間 dump、PCIe 診斷文字。
- **`.hex`**：MCTP / IPMB 十六進位封包傾印檔。

### 協定偵測機制

| 協定模式 | 行為說明 |
|---|---|
| **自動偵測（Auto Detect）** | 系統依據檔案副檔名與內容特徵前綴（如 CSV 欄位名稱、`lspci` 標頭、`Kernel panic`、`HardFault` 關鍵字、Hex 字元分佈）自動分流至對應協定引擎。 |
| **手動指定協定** | 可強制指定將所有上傳檔案套用特定協定分析器（可選：**I2C / PMBus**、**SPI Flash**、**UART Crash Dump**、**PCIe Config / AER**）。 |

---

## GUI 操作流程

1. 進入 GUI 側邊欄 **「協定分析」** 或 **「工具」** 區塊的 **「📦 批次分析」** 頁面。
2. 於 **「協定選擇」** 下拉選單中選擇 **「自動偵測（Auto Detect）」** 或指定單一協定。
3. 於檔案上傳區一次選取或拖曳多個檔案（可同時包含不同協定之檔案）。
4. 點擊 **「開始批次分析」** 按鈕。
5. 觀察即時診斷結果：
   - **4 組統計卡片**：總檔案數、成功（Success）、警告（Warning）、錯誤（Error）。
   - **結果彙總表格**：列出各檔案之檔名、識別協定、狀態與問題數（Findings Count）。
6. 點擊 **「📦 下載全部報告 ZIP（Download All Reports ZIP）」** 按鈕，下載包含所有報表之壓縮檔。

---

## 輸出內容與 ZIP 報告結構

批次分析執行完畢後，輸出的 ZIP 檔案包含每個檔案獨立生成的完整多格式報告與批次清單：

- **Markdown 報告（`.md`）**：輕量化結構報告，適合文字檢視或整合至 Issue 追蹤系統。
- **HTML 報告（`.html`）**：獨立視覺化報表，包含完整樣式，適合離線瀏覽分享。
- **SARIF 靜態分析報告（`.sarif`）**：標準靜態分析結果交換格式，可直接匯入 GitHub Code Scanning 或 CI 工具。
- **批次清單（`batch_manifest.json`）**：包含所有檔案分析結果之 JSON 總表，格式如下：

```json
{
  "schema_version": "1.0",
  "entries": [
    {
      "file": "i2c_trace_01.csv",
      "protocol": "I2C",
      "status": "warning",
      "findings_count": 2
    },
    {
      "file": "uart_crash.log",
      "protocol": "UART",
      "status": "error",
      "findings_count": 1
    }
  ],
  "total": 2,
  "passed": 0,
  "failed": 2
}
```

---

## CLI 命令列支援

除了 GUI 介面外，批次分析亦提供完整的命令列指令，方便無頭環境（Headless）與 CI/CD 腳本直接呼叫：

```bash
# 基本用法：自動偵測指定目錄下所有檔案並輸出報告
uv run fw-diag batch ./test_captures/ -o ./batch_reports/

# 指定報告格式（可選 markdown, html, sarif, all）與特定協定
uv run fw-diag batch ./logs/ -o ./reports/ -f all --protocol i2c
```

### CLI 常用參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `directory` | 包含待分析日誌或追蹤檔案之目錄路徑（必要參數） | 無 |
| `-o, --output-dir` | 儲存產出報告與 `batch_manifest.json` 之目錄路徑 | 當前目錄 |
| `-f, --format` | 匯出報告格式：`markdown`、`html`、`sarif` 或 `all` | `all` |
| `--protocol` | 指定協定（`auto`、`i2c`、`spi`、`uart`、`pcie`） | `auto` |

---

## 典型使用場景

- **產線治具批量測試（Factory ATE）**：自動讀取測試機台匯出的整批匯流排 CSV，產出良率與異常統計表。
- **CI/CD 自動化回歸流水線**：每次韌體提交時批次分析所有硬體驗證日誌，並由 SARIF 報告自動在 PR 標記問題位置。
- **多核心/多匯流排同步健檢**：一次匯入系統上所有 I2C、SPI、UART 與 PCIe 擷取記錄，進行全機健康度普查。

---

## 限制與注意事項

- **單檔大小限制**：單一檔案限制為 20 MiB；若有數小時之大型 capture 檔案，建議先以時間窗截取關鍵片段後再上傳。
- **未識別格式處理**：若文字內容無法被任何已知協定解析器辨識，狀態將標記為錯誤（Error）並記錄於清單中。

