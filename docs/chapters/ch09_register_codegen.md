# 第九章：晶片暫存器 Bitfield 視覺化與 C 語言巨集生成

## 這兩個頁面在做什麼？

### 頁面 9：晶片暫存器 Bitfield 解碼器

當你從示波器、邏輯分析儀或 `devmem2` / `i2cget` 讀到一個暫存器的 Raw Hex 值（如 `0x8400`），
你需要知道每個 Bit 代表什麼意義。這個工具讓你選擇暫存器定義檔（YAML），輸入 Hex，
即時展開每個 Bitfield 的名稱、數值與狀態含義。

**操作步驟**：
1. 進入 GUI 第 9 頁 **「🎛 晶片暫存器 Bitfield 解碼器」**。
2. 從下拉選單選擇預設定義檔（PMBus STATUS_WORD 或 PCIe AER）。
3. 在 Raw Hex 欄位輸入 `0x8400`。
4. 表格自動展開：

Raw value 必須是非負、且不超過該 register 宣告的寬度；例如 8-bit register 不能輸入
`0x100`。這是為了避免把另一個 register 或整個 32-bit snapshot 誤當成目前欄位的值。
若 YAML root、`registers`、`fields`、enum map 或 warning list 的型態不正確，工具會在載入邊界拒絕，
不會靜默覆蓋同名 register。

| Bit Range | Field | Value | Meaning |
|---|---|---|---|
| 15 | VOUT_FAULT | 0x1 | ⚠ Vout Overvoltage Fault |
| 14 | IOUT_FAULT | 0x0 | Normal |
| 10 | TEMPERATURE | 0x1 | ⚠ Overtemperature Alarm |

### 頁面 10：C 語言 Register 巨集產生器

在嵌入式 C 開發中，操作暫存器需要定義大量的 `#define` 巨集。
手寫容易出錯（bit shift 算錯、mask 遺漏、型別不安全）。
目前 GUI 讓你從內建 YAML 範本選擇定義，產出具固定寬度型別與遮罩的 MISRA-oriented 起始模板：

```c
#define REG_STATUS_WORD_OFFSET              (0x0079U)
#define REG_STATUS_WORD_VOUT_FAULT_POS     (15U)
#define REG_STATUS_WORD_VOUT_FAULT_MSK     (0x00008000U)
#define REG_STATUS_WORD_VOUT_FAULT_GET(val)   (((val) & REG_STATUS_WORD_VOUT_FAULT_MSK) >> REG_STATUS_WORD_VOUT_FAULT_POS)
#define REG_STATUS_WORD_VOUT_FAULT_SET(reg, val) (((reg) & ~REG_STATUS_WORD_VOUT_FAULT_MSK) | (((uint32_t)(val) << REG_STATUS_WORD_VOUT_FAULT_POS) & REG_STATUS_WORD_VOUT_FAULT_MSK))
```

**為什麼要使用固定寬度 unsigned 型別？**
這可降低 integer promotion 與 signed shift 帶來的風險，但單一 cast 不足以證明整份 header 符合 MISRA-C。產物仍要依專案的 register access policy、compiler warning 與 MISRA checker 驗證。

## 怎麼操作 C Header 產生器？

1. 進入 GUI 第 10 頁 **「🛠 C 語言 Register 巨集產生器」**。
2. 從下拉選單選擇 YAML 範本（如 `pmbus_standard.yaml`）。
3. 輸入模組名稱（如 `PMBUS_REGS`）。
4. 頁面即時顯示完整的 C 標頭檔代碼。
5. 點擊 **「下載 pmbus_regs.h」** 按鈕存檔。

> [!CAUTION]
> 產生器只建立巨集模板，不知道硬體的 read-only、write-one-to-clear、副作用或存取順序，除非 YAML schema 明確提供並通過驗證。套用到 driver 前仍須對照 datasheet。
