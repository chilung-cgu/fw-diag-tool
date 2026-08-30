# Ch21 — Session A/B 對比

## 功能簡介

在韌體產品反覆迭代、Bug 修復與 CI 回歸測試中，工程師經常需要比對兩次測試工作階段（Session）的整體健康度。Session A/B 對比（Session Comparison）可直接載入兩份 `.fwsession.json` 診斷記錄檔，自動比對異常數量（Anomaly Count）、交易總數（Total Transactions）與協定一致性，並以直觀的判定徽章（Verdict Badge）與 Delta 數值呈現改善或退化趨勢。

與需要原始波形或日誌檔的協定差分不同，Session 對比直接讀取已結構化的 Session 報告，省去重新解碼的時間，非常適合作為高階品質追蹤與驗收標準。

---

## 輸入方式與操作步驟

### 步驟 1：進入頁面與載入 Session

1. 啟動 Web 介面並切換至側邊欄 **「進階分析」** 區塊的 **「⚖️ Session A/B 對比」** 頁面。
2. 系統提供兩種載入方式：
   - **載入內建示範範例**：點擊 **「載入示範 Baseline 與 Candidate Session」** 按鈕，快速體驗修復前（4 項異常）與修復後（0 項異常）之對比效果。
   - **自訂檔案上傳**：分別於左欄 **「上傳 Baseline .fwsession.json」** 與右欄 **「上傳 Candidate .fwsession.json」** 拖曳或選取檔案。

### 步驟 2：檢視判定結果與指標卡片

當兩份 Session 檔案解析成功後，系統將自動比對並即時更新下方判定結果：

- **判定結果徽章（Verdict）**：
  - 🟢 **改善（Improved）**：待測版本異常總數少於基準版本。
  - 🔴 **退化（Degraded）**：待測版本異常總數多於基準版本。
  - 🔵 **持平（Unchanged）**：兩版本異常總數完全相同。
- **即時 Delta 指標卡片**：
  - **異常總數（Anomaly Count）**：顯示 Candidate 異常數，並以顏色反轉標示 Delta 變化（減少顯示為綠色正向，增加顯示為紅色負向）。
  - **交易總數（Total Transactions）**：顯示 Candidate 交易筆數與增減差額。
  - **協定（Protocol）**：顯示 Candidate 協定名稱；若兩側協定不同，則顯示跨協定警示。

### 步驟 3：檢視對比表與匯出報告

1. 在 **「📊 詳細指標對比表」** 中檢視結構化指標對照矩陣。
2. 滾動至 **「⬇️ 匯出對比報告」** 區塊，點擊 **「下載 Markdown 對比報告」** 按鈕，儲存 `session_comparison_report.md`。

---

## 比較維度與輸出範例

### 指標對比矩陣

| 指標 / 項目（Metric） | Baseline（基準） | Candidate（待測） | 差異（Delta） |
|---|---|---|---|
| **異常總數（Anomaly Count）** | 4 | 0 | -4 |
| **交易總數（Total Transactions）** | 20 | 24 | +4 |
| **協定（Protocol）** | i2c | i2c | 一致（Same） |

### Markdown 對比報告格式

產出的 Markdown 報告包含完整之 metadata 與差異摘要：

```markdown
# Session A/B 對比報告（Session Comparison Report）

- **Baseline（基準）**: I2C Baseline (Golden/Before)
- **Candidate（待測）**: I2C Candidate (Fixed/After)
- **判定結果（Verdict）**: improved

## 指標差異對比（Metric Deltas）

| 指標 / 項目（Metric） | Baseline（基準） | Candidate（待測） | 差異（Delta） |
|---|---|---|---|
| 異常總數（Anomaly Count） | 4 | 0 | -4 |
| 交易總數（Total Transactions） | 20 | 24 | +4 |
| 協定（Protocol） | i2c | i2c | 一致（Same） |

## 分析摘要（Summary）

待測版本異常數減少 4 項（4 -> 0），判定為改善（Improved）。
```

---

## 典型使用場景

- **韌體修復效果確認**：驗證 Bug 修復補丁（Patch）是否確實解決目標異常，且未引發其他匯流排錯誤。
- **CI/CD 自動化品質門檻**：在自動化測試流程中比對每日建置（Nightly Build）與基準版本之 Session，若判定為 `degraded` 則阻擋發布。
- **長期硬體老化與壓力測試對比**：比對常溫初期測試與高溫高濕（HTOL）長時運作後之 Session，評估訊號健康度退化趨勢。

---

## 限制與注意事項

- **依賴結構化報告欄位**：本比對引擎讀取 Session 中的 `report` 摘要數據（如 `anomaly_count`, `total_transactions`），不重新解碼原始底層波形。
- **跨協定比對限制**：若比對不同協定（例如 I2C Session vs SPI Session），系統會發出警告，因各協定交易與異常語意不同，其數值差額僅供參考。
- **原始輸入歸檔**：若需追溯異常發生的具體時間戳與封包欄位，請透過 Session 中的 `capture_sha256` 取出原始 capture 檔案進一步分析。

