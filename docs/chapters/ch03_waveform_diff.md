# 第三章：Golden vs Failing 雙波形差分對比 (Waveform Diff)

## 這個頁面在做什麼？

在硬體除錯中，A/B 比對可以協助縮小問題範圍：
- **Golden（參考資料）**：已確認行為符合預期的 decoded I2C trace。
- **Failing（待分析資料）**：在相同測試條件下取得的 decoded I2C trace。

目前工具依交易順序逐筆比對兩份 trace，自動找出第一個分歧點，
並告訴你分歧的原因是 NACK、資料不一致、還是方向錯誤。

> [!IMPORTANT]
> 這裡比較的是已解碼交易，不是 SCL/SDA raw edge 或類比波形。Failing 多出一次 retry 時，後續交易可能因 index 位移而需要人工重新對齊。

## 怎麼操作？

1. 進入 GUI 第 3 頁 **「⚖️ 雙波形對比檢視 (Waveform Diff)」**。
2. 左邊上傳 Golden Trace CSV（如 `examples/data/i2c_golden.csv`）。
3. 右邊上傳 Failing Trace CSV（如 `examples/data/i2c_failing_nack.csv`）。
4. 系統自動比對並顯示結果。

## 怎麼看懂輸出結果？

### 比對結果類型

| 結果 | 白話解釋 | 排查方向 |
|---|---|---|
| **Compared fields identical** | 目前實作有比較的交易欄位一致 | 代表沒有找到支援欄位的差異；不代表電氣波形、所有 timing 或板卡狀態完全相同 |
| **NACK_MISMATCH** | 同一筆交易的 ACK/NACK 語意不同 | 先確認是否為正常 read-final NACK，再檢查供電、reset、位址、busy 與 transaction direction |
| **DATA_MISMATCH** | 同一筆交易的資料不同 | 比對測試前置狀態、韌體版本、register/page 與裝置回應 |
| **ADDRESS_MISMATCH** | 兩份 trace 存取不同位址 | 檢查測試流程、MUX 狀態、board variant 與驅動設定 |
| **DIRECTION_MISMATCH** | 一邊是 Read，另一邊是 Write | 檢查 API 呼叫參數與程式流程；不能只由此欄位確定原因 |
| **MISSING_TX** | Failing trace 缺少參考資料中的交易 | 先確認 capture window，再檢查 timeout、early return 或流程分支 |
| **UNEXPECTED_EXTRA_TX** | Failing trace 多出交易 | 檢查 retry、polling、背景裝置與 capture 起點是否一致 |

### 輸出範例解讀

```text
🚨 Found 1 divergence point(s). First mismatch at Transaction #3.
現象描述: ACK mismatch on 0x50: Golden NACK=False, Failing NACK=True
排查建議: Slave 晶片在故障板卡上返回 NACK (可能未上電、被 Reset 或內部忙碌)。
```

**白話翻譯**：工具在第 3 筆已解碼交易找到 ACK/NACK 差異。
**下一步行動**：先確認兩份 capture 的 transaction alignment 與 NACK 發送端，再檢查供電、reset、MUX channel 和裝置 busy 狀態。

## 測試資料

- **Golden**: `examples/data/i2c_golden.csv`（小型 synthetic 參考資料）
- **Failing**: `examples/data/i2c_failing_nack.csv`（加入 NACK 差異的 synthetic 資料）
