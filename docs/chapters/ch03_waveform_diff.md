# 第三章：Golden vs Failing 雙波形差分對比 (Waveform Diff)

## 這個頁面在做什麼？

在硬體除錯中，最有力的方法就是「A/B 比對」：
- **Golden（良品）**：正常板卡上抓到的 I2C 波形。
- **Failing（不良品）**：故障板卡上抓到的同一組通訊波形。

這個工具會逐筆比對兩份波形的每一筆交易，自動抓出第一個分歧點，
並告訴你分歧的原因是 NACK、資料不一致、還是方向錯誤。

## 怎麼操作？

1. 進入 GUI 第 3 頁 **「⚖️ 雙波形對比檢視 (Waveform Diff)」**。
2. 左邊上傳 Golden Trace CSV（如 `examples/data/i2c_golden.csv`）。
3. 右邊上傳 Failing Trace CSV（如 `examples/data/i2c_failing_nack.csv`）。
4. 系統自動比對並顯示結果。

## 怎麼看懂輸出結果？

### 比對結果類型

| 結果 | 白話解釋 | 排查方向 |
|---|---|---|
| **100% identical** | 兩份波形完全一致 | 正常，無需排查 |
| **NACK_MISMATCH** | 同一筆交易：Golden 有 ACK 但 Failing 是 NACK | Slave 在故障板上未回應。檢查供電、焊接、位址設定。 |
| **DATA_MISMATCH** | 同一筆交易：傳送的資料不同 | EEPROM 內容損毀或韌體版本不一致。檢查暫存器初始值。 |
| **ADDRESS_MISMATCH** | 兩份波形存取了不同的 Slave 位址 | 硬體 Address Pin 配置不同或驅動常數寫錯。 |
| **DIRECTION_MISMATCH** | 一邊是 Read 另一邊是 Write | 韌體流程不一致，可能是條件分支判斷不同。 |
| **MISSING_TX** | Failing 波形提前結束，缺少後續交易 | 前一筆失敗導致韌體跳出重試迴圈或直接退出。 |
| **UNEXPECTED_EXTRA_TX** | Failing 多出不預期的交易 | 韌體可能陷入無限重試迴圈。檢查重試上限設定。 |

### 輸出範例解讀

```text
🚨 Found 1 divergence point(s). First mismatch at Transaction #3.
現象描述: ACK mismatch on 0x50: Golden NACK=False, Failing NACK=True
排查建議: Slave 晶片在故障板卡上返回 NACK (可能未上電、被 Reset 或內部忙碌)。
```

**白話翻譯**：第 3 筆交易（讀取 EEPROM 0x50 的 4 bytes），正常板卡有 ACK，但故障板卡收到 NACK。
**下一步行動**：量測故障板卡的 EEPROM VCC 供電是否正常；確認 MUX Channel 是否切換到正確的通道。

## 測試資料

- **Golden**: `examples/data/i2c_golden.csv`（5 筆正常交易）
- **Failing**: `examples/data/i2c_failing_nack.csv`（第 3 筆改為 NACK）