# UART 序列埠崩潰轉儲與 ARM Cortex-M HardFault 智慧診斷（Crash Dump）

## 這個頁面在做什麼？

當嵌入式系統當機時，工程師最依賴的是 UART 序列埠日誌（UART Serial Log）。
這個工具會由文字擷取可辨識欄位，並由解析器（parser）解析兩種常見的崩潰轉儲（Crash Dump）：

- **Linux 核心 Panic（Kernel Panic）**：伺服器或開發板的 Linux 作業系統崩潰。
- **ARM Cortex-M 硬錯誤（HardFault）**：MCU（例如 STM32、NXP）觸發 HardFault 例外。

報告整理的是輸入 log 中能被解析器（parser）證明的 fault 欄位；沒有相同建置版本的 ELF 與符號（matching
ELF／symbol），或沒有目標板重現時，不能把候選位址直接寫成唯一的原始碼根因。

## 怎麼操作？

1. 進入 GUI 第 4 頁 **「📟 UART 崩潰轉儲與 HardFault 分析（Crash Dump）」**。
2. 選擇輸入方式：貼上自己的 log，或載入內建 Linux Kernel Panic／ARM HardFault 範例。
3. 點擊 **「執行 UART 崩潰轉儲分析（Crash Dump）」** 按鈕。
4. 先讀可解析欄位與資料限制，再使用相同建置版本的符號檔（matching ELF）、
   `addr2line` 或故障框架（fault frame）交叉確認；下載的 Markdown 報告只保存分析結果，
   不取代原始 UART log。

## 範例資料與實際路徑

UART 頁面沒有從 `examples/data/` 自動讀檔；兩個「載入範例」選項使用 GUI 內嵌的最小文字，
並可用下載按鈕保存。若要演練專案提供的完整 log，請選擇貼上模式，再貼入下表檔案內容：

| 使用方式 | GUI 顯示／下載檔名 | 專案中的完整範例 |
|---|---|---|
| Linux 核心 Panic | `uart_kernel_panic_minimal.log` | `examples/data/kernel_panic_nvme.log` |
| ARM Cortex-M HardFault | `uart_hardfault_minimal.log` | `examples/data/arm_hardfault_stm32.log` |

兩種來源走同一個 parser，但可解析欄位會隨 log 內容不同；完整 log 可能包含更多暫存器或時間戳。
請保留原始檔名與內容，不要把 GUI 下載的最小樣本誤當成目標板的完整 crash dump。

## GUI 輸出先看哪裡？

按下執行按鈕後，GUI 會在頁面顯示 Markdown 報告，並提供
**「下載 UART Markdown 診斷報告」**（檔名 `uart_crash_report.md`）。依輸入類型先看下列區段：

| 輸入類型 | 報告區段 | 先確認什麼 |
|---|---|---|
| Linux Kernel Panic | 崩潰摘要（Crash Summary）、呼叫追蹤（Call Trace）、根因分析與除錯清單（Root Cause Analysis & Debug Checklist） | 架構、Panic 原因、故障位址／函式與 trace 是否來自同一份 log |
| ARM Cortex-M HardFault | HardFault 暫存器（HardFault Registers）、Fault 旗標與根因（Fault Flags & Root Cause） | `HFSR`、`CFSR`、故障 PC、`BFAR`／`MMFAR` 是否有有效旗標支援 |
| 其他或一般序列埠 log | 未辨識 Crash Signature（Unsupported Crash Signature）、建議下一步（Next Step） | parser 沒有找到支援標記時，先補完整 log，不要把空報告當成「沒有故障」 |

UART 報告中的 `N/A`（其他頁面可能顯示 `Unavailable`）是「輸入沒有提供可解析證據」，不是工具替你推導出的位址或數值；
原始 log 裡的 stacked registers 也不一定會全部列在 Markdown 報告中。

## 怎麼看懂輸出結果？

### Linux 核心 Panic（Kernel Panic）解讀

工具會自動提取以下關鍵欄位。表格中的英文 token 會保留，方便和原始 kernel log、腳本及
`addr2line` 輸入逐字比對：

| 欄位 | 白話解釋 | 怎麼用？ |
|---|---|---|
| 崩潰原因（Panic Reason） | kernel 提供的崩潰原因描述 | 判斷是 Page Fault、Oops 或 Fatal Exception；仍要保留原始 log |
| 故障指令位址（Faulting IP / RIP） | CPU 當機時正在執行的指令位址 | 用相同建置版本的符號檔（matching ELF）搭配 `addr2line` 定位候選原始碼行 |
| 故障函式（Faulting Function） | parser 從 log 辨識出的函式名稱 | 取得追查起點；不單獨證明該函式就是 root cause |
| 故障記憶體位址（Faulting Memory Address） | fault log 提供的存取位址 | `< 0x1000` 是 NULL pointer 候選訊號；仍須依架構、頁表／MPU 與 fault context 驗證 |
| 呼叫追蹤（Call Trace） | 函式呼叫堆疊鏈 | 往回追蹤誰呼叫出錯函式，再以符號（symbol）驗證每一層 |

**判讀邊界**：小位址常提示 NULL pointer，但也可能來自其他 fault context；缺少 `CR2`、
`RIP` 或 call trace 時，報告會保留資料不足，不會自行補值。

### ARM Cortex-M 硬錯誤（HardFault）解讀

ARM MCU 的崩潰分析需要理解 SCB（System Control Block，系統控制區塊）暫存器。以下
`HFSR`、`CFSR` 與各子欄位名稱保留 ARM architectural token，中文只補充其用途：

**HFSR（HardFault Status Register，HardFault 狀態暫存器）**：

| Bit | 名稱 | 白話解釋 |
|---|---|---|
| 30 | FORCED | 原本是 Configurable Fault，但因未啟用獨立 handler 而升級為 HardFault |
| 1 | VECTTBL | 從 Vector Table 讀取例外處理函式位址時發生 Bus Error |

**CFSR（Configurable Fault Status Register，可設定 Fault 狀態暫存器）** 分三部分：

#### UFSR（Usage Fault Status Register，使用錯誤狀態暫存器；bits [31:16]）

| Bit | 名稱 | 白話解釋 | 排查方向 |
|---|---|---|---|
| 9 | DIVBYZERO | 除以零，分母為 0 | 在除法前加入 `if (denom == 0)` 防護，並遵循專案錯誤契約 |
| 8 | UNALIGNED | 以 `uint32_t*` 存取非 4-byte 對齊位址 | 改用 `memcpy` 或專案允許的 `__packed` 方式 |
| 3 | NOCP | FPU 未開啟卻執行浮點指令 | 依 MCU 啟動流程設定 `SCB->CPACR` 的 FPU 權限 |
| 0 | UNDEFINSTR | 執行非法 Opcode | 檢查函式指標跑飛、映像損毀或 Flash 被覆蓋 |

#### BFSR（Bus Fault Status Register，匯流排錯誤狀態暫存器；bits [15:8]）

| Bit | 名稱 | 白話解釋 | 排查方向 |
|---|---|---|---|
| 7 | BFARVALID | BFAR 暫存器中的位址有效 | 查看 BFAR 取得非法存取位址，再核對 stacked frame |
| 4 | STKERR | 例外入棧時發生匯流排錯誤 | 檢查 Stack 區域的 MPU 設定與 stack 邊界 |
| 2 | IMPRECISERR | 非精確匯流排錯誤，Write Buffer 使行號不一定精確 | 依 MCU 能力評估 `DISDEFWBUF`，並補充其他 trace |
| 1 | PRECISERR | 精確匯流排錯誤，BFAR 記錄非法位址 | 查看 BFAR 並用 stacked PC／symbols 交叉確認 |
| 0 | IBUSERR | 取指（Instruction Fetch）匯流排錯誤 | 檢查 Flash 映射、XIP 與執行權限設定 |

#### MMFSR（Memory Manage Fault Status Register，記憶體管理錯誤狀態暫存器；bits [7:0]）

| Bit | 名稱 | 白話解釋 | 排查方向 |
|---|---|---|---|
| 1 | DACCVIOL | 資料存取違反 MPU Region 設定 | 核對資料位址、權限與 MPU region |
| 0 | IACCVIOL | 指令存取違反 MPU Region 設定 | 核對 stacked PC、執行區域與 MPU region |

**新手提示**：如果 `HFSR.FORCED = 1` 且 `CFSR.DIVBYZERO = 1`，表示 fault status register
記錄到除以零 trap；這證明 CPU 觀察到該 fault，不等於已找到唯一的程式碼路徑。
接著用 stacked PC、map file／`addr2line` 與原始碼確認。修復時可在除法前加入
`if (denom == 0) return ERROR;`，但回傳方式必須依專案錯誤處理契約決定。

## 建議的證據順序

1. 保存完整 UART log 與原始檔名，避免只保留複製貼上的片段。
2. 確認 parser 找到的 crash type、`HFSR`／`CFSR`、故障位址，以及原始 log 是否含 stacked frame。
3. 以與目標映像完全相同的符號檔（matching ELF）／map file 做 symbolication；不要混用其他 build。
4. 將候選 source line 對回 driver、MPU／FPU 設定與重現結果，再決定修復方案。
