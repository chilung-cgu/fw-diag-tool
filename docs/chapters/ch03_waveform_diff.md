# Golden 與 Failing 雙波形差分對比（Waveform Diff）

## 這個頁面在做什麼？

在硬體除錯中，A/B 比對（A/B comparison）可以協助縮小問題範圍。這一頁只比較兩份
已解碼的 I2C 交易，先找出協定層的第一個分歧，再決定要補哪一種外部證據：

- **Golden（參考資料）**：已確認行為符合預期的解碼後 I2C trace（decoded I2C trace）。
- **Failing（待分析資料）**：在相同測試條件下取得的解碼後 I2C trace（decoded I2C trace）。

目前工具依交易順序（transaction order）逐筆比對兩份 trace，自動找出第一個分歧點，
並告訴你分歧的原因是 NACK、資料不一致，還是讀寫方向錯誤。這個結果是範圍縮小工具，
不是類比電氣或韌體根因的自動判定器。

> **重要：**
>
> 這裡比較的是已解碼交易，不是 SCL/SDA raw edge 或類比波形。Failing 多出一次 retry 時，
> 後續交易可能因 index 位移而需要人工重新對齊；請把對齊狀態（alignment）當成待驗證證據。

## 怎麼操作？

1. 進入 GUI 第 3 頁 **「⚖️ 雙波形對比檢視（Waveform Diff）」**。
2. 第一次操作可先按 **「載入內建 Golden/Failing 範例」**；GUI 會載入套件內建的最小
   解碼後 CSV 配對（decoded CSV pair），並提供兩份 CSV 的下載按鈕。
3. 若要使用自己的 capture（擷取檔），左邊上傳 Golden Trace CSV（如
   `examples/data/i2c_golden.csv`），右邊上傳 Failing Trace CSV（如
   `examples/data/i2c_failing_nack.csv`）。
4. 兩份輸入都就緒後，系統自動比對並顯示結果；只有一邊上傳時會先提示補齊另一邊。

## 怎麼看懂輸出結果？

### 比對結果類型

| 結果 | 白話解釋 | 排查方向 |
|---|---|---|
| **比較欄位一致（Compared fields identical）** | 目前實作有比較的交易欄位一致 | 代表沒有找到支援欄位的差異；不代表電氣波形、所有 timing 或板卡狀態完全相同 |
| **ACK／NACK 不一致（NACK_MISMATCH）** | 同一筆交易的 ACK/NACK 語意不同 | 先確認是否為正常 read-final NACK，再檢查供電、reset、位址、busy 與 transaction direction |
| **資料不一致（DATA_MISMATCH）** | 同一筆交易的資料不同 | 比對測試前置狀態、韌體版本、register/page 與裝置回應 |
| **位址不一致（ADDRESS_MISMATCH）** | 兩份 trace 存取不同位址 | 檢查測試流程、MUX 狀態、board variant 與驅動設定 |
| **讀寫方向不一致（DIRECTION_MISMATCH）** | 一邊是 Read，另一邊是 Write | 檢查 API 呼叫參數與程式流程；不能只由此欄位確定原因 |
| **缺少交易（MISSING_TX）** | Failing trace 缺少參考資料中的交易 | 先確認 capture window，再檢查 timeout、early return 或流程分支 |
| **多出非預期交易（UNEXPECTED_EXTRA_TX）** | Failing trace 多出交易 | 檢查 retry、polling、背景裝置與 capture 起點是否一致 |

### 輸出範例解讀（保留 canonical raw lines）

以下區塊是 CLI/API 的穩定原始輸出（canonical raw output）；請勿把其中的英文欄位名稱
翻譯後再拿去做自動化比對。人類閱讀時可搭配區塊下方的中文說明。

```text
Found 1 divergence point(s). First mismatch at Transaction #3.
Divergence at Tx #3
Type: NACK_MISMATCH
Description: ACK outcome mismatch on 0x50: Golden=aggregate_ack, Failing=aggregate_nack. A final controller NACK on a read is treated as normal termination.
Hint: 先確認 NACK 是 address、write-data、read 終止，還是來源欄位缺失；只有 address/data NACK 才進一步檢查供電、reset、busy 與 command。
```

**白話翻譯**：工具在第 3 筆已解碼交易找到 aggregate ACK/NACK 差異；讀取交易結尾由 controller 發出的 NACK 會視為正常終止。

**下一步行動**：先確認兩份 capture 的 transaction alignment 與 NACK 發送端，再檢查供電、reset、MUX channel 和裝置 busy 狀態。

## 測試資料

- **Golden**: `examples/data/i2c_golden.csv`（小型 synthetic 參考資料）
- **Failing**: `examples/data/i2c_failing_nack.csv`（加入 NACK 差異的 synthetic 資料）
- GUI 內建 pair 與上述檔案內容一致；載入後預期看到 `Found 1 divergence point(s). First mismatch at Transaction #3.` 與 `Type: NACK_MISMATCH`。
