# UART 序列埠崩潰轉儲與 ARM Cortex-M HardFault 智慧診斷（Crash Dump）

## 這個頁面在做什麼？

當嵌入式系統當機時，工程師最依賴的就是 UART Serial Log。
這個工具能解析兩種最常見的 Crash Dump：

- **Linux Kernel Panic**：伺服器/開發板的 Linux 作業系統崩潰。
- **ARM Cortex-M HardFault**：MCU（如 STM32、NXP）的 HardFault 中斷觸發。

## 怎麼操作？

1. 進入 GUI 第 4 頁 **「📟 UART 崩潰轉儲與 HardFault 分析（Crash Dump）」**。
2. 選擇輸入方式：貼上自己的 Log，或載入範例。
3. 點擊 **「執行 UART 崩潰轉儲分析（Crash Dump）」** 按鈕。

## 怎麼看懂輸出結果？

### Linux Kernel Panic 解讀

工具會自動提取以下關鍵欄位：

| 欄位 | 白話解釋 | 怎麼用？ |
|---|---|---|
| Panic Reason | 崩潰原因描述 | 判斷是 Page Fault、Oops 还是 Fatal Exception |
| Faulting IP / RIP | CPU 當機時正在執行的指令位址 | 用 addr2line 定位源碼行號 |
| Faulting Function | 出錯的函式名稱 | 直接知道哪個函式出了問題 |
| Faulting Memory Address | 存取了 fault log 中提供的記憶體位址 | < 0x1000 是 NULL pointer 的候選訊號；仍須依架構、頁表/MPU 與 fault context 驗證 |
| Call Trace | 函式呼叫堆疊鏈 | 往回追蹤是誰呼叫了出錯的函式 |

### ARM Cortex-M HardFault 解讀

ARM MCU 的 Crash 分析需要理解 SCB (System Control Block) 暫存器：

**HFSR (HardFault Status Register)**：

| Bit | 名稱 | 白話解釋 |
|---|---|---|
| 30 | FORCED | 本來是 Configurable Fault，但因為沒開啟獨立 handler 而升級為 HardFault |
| 1 | VECTTBL | 從 Vector Table 讀取異常處理函式位址時發生 Bus Error |

**CFSR (Configurable Fault Status Register)** 分三部分：

#### UFSR (Usage Fault Status Register, bits [31:16])

| Bit | 名稱 | 白話解釋 | 排查方向 |
|---|---|---|---|
| 9 | DIVBYZERO | 除以零！分母為 0 | 加 if(denom==0) 防護 |
| 8 | UNALIGNED | 以 uint32_t* 存取非 4-byte 對齊位址 | 改用 memcpy 或 __packed |
| 3 | NOCP | FPU 未開啟但執行了浮點指令 | 開啟 SCB->CPACR FPU 致能 |
| 0 | UNDEFINSTR | 執行了非法 Opcode | 函式指標跑飛或 Flash 被覆蓋 |

#### BFSR (Bus Fault Status Register, bits [15:8])

| Bit | 名稱 | 白話解釋 | 排查方向 |
|---|---|---|---|
| 7 | BFARVALID | BFAR 暫存器中的位址有效 | 查看 BFAR 得知非法存取位址 |
| 4 | STKERR | 中斷入棧時發生總線錯誤 | 檢查 Stack 區域的 MPU 設定 |
| 2 | IMPRECISERR | 非精確總線錯誤（Write Buffer 導致無法定位精確行號）| 開啟 DISDEFWBUF 強制轉為 Precise |
| 1 | PRECISERR | 精確總線錯誤（BFAR 記錄了非法位址） | 查看 BFAR 找到非法位址 |
| 0 | IBUSERR | 取指（Instruction Fetch）總線錯誤 | 檢查 Flash 映射與 XIP 設定 |

#### MMFSR (Memory Manage Fault Status Register, bits [7:0])

| Bit | 名稱 | 白話解釋 |
|---|---|---|
| 1 | DACCVIOL | 資料存取違反 MPU Region 設定 |
| 0 | IACCVIOL | 指令存取違反 MPU Region 設定 |

**新手提示**：如果 HFSR.FORCED = 1 且 CFSR.DIVBYZERO = 1，這表示 fault status register
記錄了除以零 trap；它指出「CPU 觀察到這個 fault」，但不等於已經找到造成錯誤的唯一程式碼路徑。
接著用 stacked PC、map file/`addr2line` 與原始碼確認。修復時可在除法前加入
`if (denom == 0) return ERROR;`，但要依專案的錯誤處理契約決定回傳方式。
