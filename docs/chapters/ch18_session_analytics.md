# Ch18 — 多工作階段趨勢分析

## 功能概述

多工作階段趨勢分析（Multi-Session Trend Analysis）把數次已儲存的診斷 Session 放在同一張表與時間順序中，協助回答「修正前後異常數是否下降」以及「交易量是否改變」。它讀取 `.fwsession.json` 的 `created_at`、`config.protocol` 與 `report` 摘要欄位，並繪製異常數與交易數的雙軸折線圖。

這個頁面適合用於韌體版本、硬體改版或測試條件變更後的回歸比較。它不是新的波形解析器：每個 Session 的原始 capture 不會被趨勢引擎重新解碼。

## Session 檔案格式

### v2.0 頂層欄位

Session 由 `SessionManager` 產生，檔名慣例為 `*.fwsession.json`。目前格式是 `schema_version: "2.0"`；檔案大小上限為 10 MiB。欄位用途如下：

| 欄位 | 必要性與用途 |
|---|---|
| `schema_version` | 必要；目前為 `"2.0"`。讀取器也接受舊版 `version` 別名。 |
| `tool_version` | 產生這份報告的 fw-diag-tool 版本。 |
| `created_at` | UTC 的 ISO 8601 時間，例如 `2026-08-30T08:00:00Z`；分析時用來排序。 |
| `name` | Session 顯示名稱；未提供時 GUI 使用檔名或 `Session #n`。 |
| `capture_sha256` | 原始輸入的 SHA-256，可用來確認是否為同一份 capture；可以是 `null`。 |
| `board_profile_name` | 使用的 Board Profile 名稱；可以是 `null`。 |
| `config` | 分析設定，例如 `protocol`、`input_format`、`smbus_timeout_ms`。 |
| `report` | 該次協定分析的結構化結果，趨勢引擎從此處取交易數、異常數與狀態。 |
| `notes` | 工程師補充說明，預設為空字串。 |
| `provenance` | 選填的來源與環境中繼資料；不得把 `capture_sha256` 或 `board_profile_name` 重複放在此處。 |

最小可分析範例（實際 `report` 欄位會依協定不同）：

```json
{
  "schema_version": "2.0",
  "tool_version": "1.1.1",
  "created_at": "2026-08-30T08:00:00Z",
  "name": "build-2026-08-30",
  "capture_sha256": "0123456789abcdef...",
  "board_profile_name": null,
  "config": {"protocol": "i2c", "input_format": "decoded_csv"},
  "report": {
    "total_transactions": 120,
    "anomaly_count": 3,
    "status": "warning"
  },
  "notes": "加入重試與電源穩定化後的回歸測試"
}
```

舊的 v1.0 檔案若使用 `version: "1.0"`、`data` 與 `provenance`，載入時會在記憶體中遷移成 v2.0；工具不會未經同意改寫原檔。Session 只保存報告與 provenance，不內嵌原始波形，因此要重現單次分析仍需保留原始檔並核對 `capture_sha256`。

### 趨勢引擎可接受的摘要欄位

為了相容不同協定報告，欄位會依下列順序尋找：

- 交易數：`report.total_transactions`、`transaction_count`、`transactions` 整數；若只有 `report.transactions` 陣列，使用陣列長度。
- 異常數：`report.anomaly_count`、`anomalies_count` 整數；若只有 `report.anomalies` 陣列，使用陣列長度。
- 協定：優先 `config.protocol`，其次 `report.protocol`，都沒有時為 `unknown`。
- 狀態：只接受 `success`、`warning`、`error`；其他值會依異常數是否大於零回退為 `warning` 或 `success`。

## GUI 操作教學

1. 執行 `uv run fw-diag gui`，在左側「Advanced Analysis」分類開啟 **Multi-Session Trend Analysis**（網址路徑 `session-analytics`）。
2. 在 **Upload Session Files** 選取兩個以上 `.fwsession.json`。可一次拖曳多個檔案；無法解析的 JSON 會顯示警告並跳過。
3. 若檔案包含多種協定，使用 **Filter by Protocol** 選擇要比較的協定；此篩選會在趨勢計算前套用。
4. 先看三張指標卡：`Sessions`（工作階段數）、`Latest Anomalies`（依日期排序後最新值與起始值差異）、`Trend`（Improving / Stable / Degrading）。
5. 在 **Session Trend** 圖表讀取左軸紅線（Anomaly Count）與右軸藍色點虛線（Transaction Count），再以下方 **Session Comparison** 表核對每一列的時間、協定、交易數、異常數與狀態。
6. 最後查看 **Analysis Summary**。改善趨勢以成功提示顯示，惡化趨勢以警告顯示，穩定或資料不足以資訊提示顯示。

至少要有兩個有效 Session 才會畫圖；只有一個檔案時仍會顯示摘要與比較表，但圖表會提示再上傳一個 Session。

## 趨勢判定邏輯

引擎先以 `created_at` 字串升冪排序（`unknown` 排在最前），再只觀察最後三個點：

| 條件（最近 2～3 個點） | 結果 |
|---|---|
| 異常數單調不增加，且第一個值大於最後一個值 | `improving` |
| 異常數單調不減，且最後一個值大於第一個值 | `degrading` |
| 數值相同、只有一個點，或中間先升後降／先降後升 | `stable` |

例如異常數 `10 → 5 → 2` 會是 improving；`1 → 5 → 12` 會是 degrading；`3 → 3` 或 `1 → 4 → 2` 會是 stable。摘要另外加總所有載入 Session 的交易數與異常數，並計算第一個與最後一個點的變化百分比（第一個異常數為零時不做百分比除法）。

這是啟發式趨勢，不是統計檢定，也不會按異常嚴重度加權。交易量與異常量使用不同 Y 軸，讀圖時不要把兩條線的高度直接互相比較。

## 實戰範例：確認 I2C 修正是否有效

### 1. 建立三次可追溯 Session

在 I2C 頁面分別載入同一測試流程的原始 CSV，完成分析後按 **儲存分析 Session**，並把檔名或 `name` 設為 `before-fix`、`retry-fix`、`power-fix`。保留每次分析的 `capture_sha256` 與韌體版本筆記。

### 2. 上傳並判讀

假設比較表如下：

| Session | created_at | Transactions | Anomalies | Status |
|---|---|---:|---:|---|
| before-fix | 08:00Z | 120 | 10 | warning |
| retry-fix | 09:00Z | 124 | 5 | warning |
| power-fix | 10:00Z | 121 | 2 | warning |

引擎會顯示 `improving`，摘要指出異常由 10 降至 2（80% reduction）。這個結果支持「輸入報告中的異常數下降」；接著仍應回到原始 capture、電源量測與韌體 log，確認修正沒有只是讓交易少跑或把錯誤隱藏。

若修正後交易數從 120 變成 40，即使異常數下降，也要先確認測試是否完整。趨勢頁不會自動計算每千筆交易的異常率。

## 證據層級、限制與邊界

**Measured（輸入中已量測／已記錄）**：Session `report` 中由協定解析器產生的交易數、異常數、狀態，以及檔案的 `created_at` 和 `capture_sha256` 字串。這些是報告或檔案中實際存在的值，不代表趨勢頁重新量測了電氣訊號。

**Inferred（工具推論）**：依時間排序後的 `improving`、`stable`、`degrading` 標籤、變化百分比、協定篩選結果，以及「多次報告的異常量呈單調變化」的摘要。它們是程式規則的推導，不是根因判定。

**Unavailable（此頁無法提供）**：原始波形、類比電壓、跨檔案時鐘偏移、每筆異常嚴重度、異常率的統計信賴區間、以及「某次修正造成改善」的因果證明。缺少有效 `created_at` 時，排序可能只反映輸入字串；不同測試條件或不同協定混在一起時，結論只能作為整理線索。

建議把每次 Session 的韌體 commit、板號、測試條件與原始檔案路徑寫入 `notes`／`provenance`，並用相同輸入格式與相同測試範圍建立可比的資料集。
