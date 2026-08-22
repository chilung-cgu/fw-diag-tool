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

| Bit Range | Field | Value | Meaning |
|---|---|---|---|
| 15 | VOUT_FAULT | 0x1 | ⚠ Vout Overvoltage Fault |
| 14 | IOUT_FAULT | 0x0 | Normal |
| 10 | TEMPERATURE | 0x1 | ⚠ Overtemperature Alarm |

### 頁面 10：C 語言 Register 巨集產生器

在嵌入式 C 開發中，操作暫存器需要定義大量的 `#define` 巨集。
手寫容易出錯（bit shift 算錯、mask 遺漏、型別不安全）。
這個工具讓你上傳 YAML 定義檔，自動產出符合 MISRA-C 規範的安全代碼：

```c
#define REG_STATUS_WORD_OFFSET              (0x0079U)
#define REG_STATUS_WORD_VOUT_FAULT_POS     (15U)
#define REG_STATUS_WORD_VOUT_FAULT_MSK     (0x00008000U)
#define REG_STATUS_WORD_VOUT_FAULT_GET(val)   (((val) & REG_STATUS_WORD_VOUT_FAULT_MSK) >> REG_STATUS_WORD_VOUT_FAULT_POS)
#define REG_STATUS_WORD_VOUT_FAULT_SET(reg, val) (((reg) & ~REG_STATUS_WORD_VOUT_FAULT_MSK) | (((uint32_t)(val) << REG_STATUS_WORD_VOUT_FAULT_POS) & REG_STATUS_WORD_VOUT_FAULT_MSK))
```

**為什麼要強制 `(uint32_t)(val)` 轉型？**
在 C99/C11 中，對 signed 負數進行左移是 Undefined Behavior（違反 MISRA C:2012 Rule 10.1）。
強制轉型為 unsigned 可以避免編譯器警告與潛在的硬體行為差異。

## 怎麼操作 C Header 產生器？

1. 進入 GUI 第 10 頁 **「🛠 C 語言 Register 巨集產生器」**。
2. 從下拉選單選擇 YAML 範本（如 `pmbus_standard.yaml`）。
3. 輸入模組名稱（如 `PMBUS_REGS`）。
4. 頁面即時顯示完整的 C 標頭檔代碼。
5. 點擊 **「下載 pmbus_regs.h」** 按鈕存檔。