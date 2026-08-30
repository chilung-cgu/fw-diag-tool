# 虛擬設備模擬器實驗室（Emulator Playground）

## 這個頁面在做什麼？

在沒有實體目標板卡或硬體工程樣品（EVB）的情況下，初階韌體工程師往往難以直觀理解硬體週邊晶片的底層行為（例如暫存器指標機制、狀態機鎖存、快閃記憶體物理寫入限制、跨頁回繞覆蓋與 ACK 輪詢等）。若直接在實體板卡上盲目測試，甚至可能因錯誤的操作邏輯抹除關鍵開機韌體。

**虛擬設備模擬器實驗室（Emulator Playground）** 在純軟體環境中完整模擬了嵌入式系統中最核心的三大週邊設備：

1. **LM75 / TMP102 數位溫度感測器（I2C 7-bit 位址：0x48）**
2. **Winbond W25Q128 SPI NOR Flash（16 MB / 128 Mbit 容量）**
3. **Microchip / Atmel 24C64 I2C 序列 EEPROM（8 KB / 64 Kbit 容量）**

透過本實驗室，工程師能自由進行暫存器讀寫、觸發硬體警報、觀察快閃記憶體擦除與寫入狀態機轉換、重現經典的 **Page Rollover（跨頁回繞覆蓋）** 災難，並實踐高效的 **ACK Polling（確認輪詢）** 技術。

---

## 怎麼操作？

進入 GUI 側邊欄 **「實驗室與學習」** 區塊的 **「🧪 虛擬設備模擬器實驗室」** 頁面。頂部設有三個獨立分頁：

### 分頁一：🌡️ LM75 溫度感測器模擬 (I2C)

1. **環境溫度調節**：滑動「環境溫度設定」滑桿（範圍 -40.0 °C ~ 125.0 °C，步進 0.5 °C），即時觀察內部暫存器數值與 OS（Over-Temperature Shutdown）警報腳位狀態。
2. **檢視暫存器表**：觀察 4 大內部暫存器（TEMP `0x00`、CONFIG `0x01`、THYST `0x02`、TOS `0x03`）的原始 16-bit Hex 值、解碼意義與當前指針（Active Pointer）。
3. **I2C 寫入命令**：
   - 輸入寫入 Hex 位元組（例如 `0x00` 設定指針為 TEMP、`0x01 0x01` 進入低功耗關機模式）。
   - 亦可直接從「快速載入指令範例」下拉選單選取常用指令。
4. **I2C 讀取命令**：
   - 選擇讀取位元組數（1 或 2 Bytes），點擊「執行 I2C 讀取」，檢視從晶片回傳的原始位元組與自動解碼結果。

### 分頁二：⚡ SPI Flash W25Q128 模擬 (16MB NOR)

1. **狀態列監控**：即時查看 JEDEC ID（`0xEF 0x40 0x18`）、WEL（寫入致能鎖存）、BUSY（忙碌狀態）與已寫入位元組統計。
2. **狀態機控制按鈕**：
   - **WREN (0x06)**：發送 Write Enable 命令將 WEL 置 1（允許後續寫入或擦除）。
   - **WRDI (0x04)**：發送 Write Disable 將 WEL 置 0。
   - **完成操作 / 清除 Busy**：手動結束內部 Program/Erase 週期，將 Flash 還原至 Ready 狀態。
   - **重設 Flash 記憶體**：將 16 MB 全部還原為未抹寫的初始狀態 `0xFF`。
3. **三種核心操作**：
   - **Page Program (0x02)**：輸入目標位址與 Hex 位元組（最多 256B），體驗 WEL 檢查機制與 1->0 物理寫入行為。
   - **Sector Erase (0x20)**：輸入 4KB 扇區內任意位址，將該扇區 4096 位元組全部還原為 `0xFF`。
   - **Read Data (0x03)**：輸入位址與長度，以標準十六進位傾印（Hex Dump）檢視 Flash 內容。

### 分頁三：💾 EEPROM 24C64 模擬 (I2C 8KB)

1. **狀態列與 ACK Polling**：查看裝置位址（`0x50`）、容量（8192B）、頁面大小（32B）與 BUSY 狀態。在寫入後點擊「執行 ACK Polling (0x50)」以模擬確認輪詢流程。
2. **Page Write 寫入與 Rollover 模擬**：
   - 輸入 2-Byte Word Address（例如 `0x001E`）與 Payload 資料（例如 `0xAA 0xBB 0xCC 0xDD 0xEE 0xFF` 共 6 位元組）。
   - 當寫入長度跨越 32-Byte 邊界時，系統會跳出黃色 **Page Boundary Rollover 警告**。
   - 點擊「執行 EEPROM 寫入」，晶片將自動進入內部寫入週期（Busy=True）。
3. **I2C Read 讀取**：輸入起始 Offset 與長度進行隨機讀取。
4. **記憶體 Hex 檢視器**：從下拉選單切換檢視特定 Page（Page 0 ~ Page 15，每頁 32 Bytes）或前 256/512 Bytes 記憶體內容。

---

## GUI 會顯示哪些輸出？

| 模擬裝置 | 畫面區段 | 顯示內容 | 物理意義與除錯重點 |
|---|---|---|---|
| **LM75** | 頂部 Metric 與狀態表 | 當前溫度、TOS 門檻（80.0 °C）、THYST 門檻（75.0 °C）、OS 警報電位 | 驗證遲滯防彈跳機制；警報觸發後需降回 THYST 之下方釋放 |
| **LM75** | I2C 讀寫交互區 | 指針設定結果、讀取 Hex 位元組、12-bit 二補數溫度解碼 | 掌握 Pointer Register 行為：讀取前必須先發送暫存器位移 |
| **W25Q128** | 頂部狀態與指標 | JEDEC ID、WEL (0/1)、BUSY (0/1)、已寫入位元組與使用率 | 寫入或擦除前必須先確認 WEL=1；執行期間晶片處於 BUSY 狀態 |
| **W25Q128** | 操作結果與 Hex Dump | Page Program 成功/拒絕提示、Sector Erase 範圍提示、標準 Hex Dump | 驗證 NOR Flash 只能 1->0，若重複寫入未擦除區域將產生 Bitwise AND |
| **24C64** | 狀態與 Rollover 警告 | BUSY 狀態、tWR（5.0 ms）、跨頁回繞警報、ACK Polling 回應 | 深刻體會 Page Rollover 陷阱：超出頁面邊界的位元組會覆蓋該頁開頭 |
| **24C64** | 記憶體 Hex Viewer | 分頁或連續區塊的 16 進位與 ASCII 對照傾印 | 直觀確認寫入資料是否精準落在預期記憶體位址 |

### 核心硬體原理與底層機制精解

#### 1. LM75 溫度換算與指針暫存器
- **指針機制**：LM75 只有 1 個 8-bit 指針暫存器。Master 發送 I2C Write `[0x00]` 即可切換至 TEMP 暫存器；後續發送 I2C Read 時，晶片會自動回傳該指針指向的暫存器內容。
- **12-bit 溫度換算公式**：`溫度 (°C) = (raw_16bit >> 4) * 0.0625`（高 12 位有效，左對齊；最高位元為符號位，負數需做二補數符號延伸）。
- **遲滯（Hysteresis）保護**：當溫度升至 TOS（預設 80.0 °C）時，OS 引腳拉低為 LOW（觸發中斷）；唯有當溫度降回 THYST（預設 75.0 °C）以下時，OS 引腳才恢復為 HIGH。這 5.0 °C 的遲滯區間能防止系統在臨界溫度時發生中斷訊號震盪（Chattering）。

#### 2. SPI NOR Flash 寫入鎖存與物理改寫限制
- **只能 1 -> 0（Program Restriction）**：NOR Flash 浮閘單元擦除後均為 `0xFF`（全 1）。Page Program 只能將 `1` 轉為 `0`，**無法直接將 0 改寫回 1**。若未經 Erase 就重複寫入，內部記憶體將發生 `Memory &= Data`，導致資料錯誤損毀。
- **WEL（Write Enable Latch）機制**：為防止程式跑飛或雜訊誤寫，Flash 規定在執行 Page Program (0x02) 或 Sector Erase (0x20) 前，必須先發送 `0x06 WREN`。操作完成後硬體自動將 WEL 重設為 `0`。
- **Page Buffer 跨頁回繞**：Flash 具備 256 位元組的 Page Buffer。若單次寫入跨越 256-Byte 邊界（例如從 `0x0010F0` 寫入 32 Bytes），超出 `0x0010FF` 的資料會回繞覆蓋 `0x001000` 開頭，而非寫入下一頁。

#### 3. EEPROM 24C64 跨頁覆蓋與 ACK Polling
- **Page Rollover 陷阱**：24C64 頁面大小為 32 Bytes。晶片內部僅有低 5 位的位址計數器在連續寫入時累加。若從 `0x001E`（第 0 頁倒數第 2 個 Byte）連續寫入 6 個 Bytes，前 2 個 Bytes 寫入 `0x001E` 與 `0x001F`，後續 4 個 Bytes 會**回繞覆蓋 `0x0000` ~ `0x0003`**！
- **ACK Polling（確認輪詢）優化**：EEPROM 內部快閃寫入週期（`tWR`）約需 5.0 ms。傳統驅動程式使用 `usleep(5000)` 會浪費大量 CPU 週期。透過 ACK Polling（Master 連續發送 I2C Start + Slave Address(W)，若晶片忙碌則回傳 NACK；一旦完成寫入則回傳 ACK），可即時獲知寫入完畢，大幅提升匯流排吞吐量。

---

## 證據等級邊界（Evidence Level & Limitations）

使用虛擬設備模擬器時，請注意以下軟體模擬與實體硬體的邊界差異：

- **純軟體狀態機模擬（Software Behavioral Simulation）**：模擬器旨在重現邏輯協定與暫存器行為，非實體硬體驅動或電氣模擬。
- **不能證明實體電氣品質**：模擬器中讀寫成功，不代表實體電路板上的 Pull-up 上拉電阻、訊號上升時間（Rise Time）、電源雜訊或線路長度滿足 I2C / SPI 規範。
- **時間常數為離散切換**：實體晶片的 tWR 寫入時間會隨供電電壓與環境溫度在 3.0 ~ 5.0 ms 間浮動；模擬器提供的是離散的狀態切換模型。
- **無實體時鐘延展（Clock Stretching）**：實體 MCU 模擬 I2C Slave 時可能拉低 SCL 進行時鐘延展，本頁面模擬之硬體 ASIC 晶片不包含類比電平延展。

---

## 實際場景範例

### 場景 1：驗證 EEPROM 驅動程式之分頁寫入演算法

**背景**：韌體工程師需要向 24C64 EEPROM 寫入長度為 100 Bytes 的系統組態結構體（起始位址 `0x0010`）。  
**模擬驗證步驟**：
1. 若驅動程式直接呼叫一次長度 100 Bytes 的 I2C 寫入，在模擬器中將會觸發嚴重的 Page Rollover 警告，導致 `0x0000` 開頭的資料被覆寫。
2. 工程師修改驅動程式，實作分頁切分演算法：
   - 第 1 次寫入：位址 `0x0010`，長度 16 Bytes（填滿 Page 0 剩餘空間至 `0x001F`）。
   - 執行 ACK Polling 等待寫入完成。
   - 第 2 次寫入：位址 `0x0020`，長度 32 Bytes（完整 Page 1）。
   - 執行 ACK Polling。
   - 第 3 次寫入：位址 `0x0040`，長度 32 Bytes（完整 Page 2）。
   - 執行 ACK Polling。
   - 第 4 次寫入：位址 `0x0060`，長度 20 Bytes（Page 3 剩餘資料）。
3. 透過模擬器驗證後，確保所有位元組均精準寫入目標區間，無任何跨頁覆蓋。

### 場景 2：SPI NOR Flash 刷新未發送 WREN 導致寫入失效

**背景**：在開發 Bootloader 的 SPI Flash 寫入函式時，初學者常直接發送 `0x02` 指令而忽略了 `0x06 WREN`。  
**模擬驗證步驟**：
1. 在模擬器中直接點擊「執行 Page Program (0x02)」，系統立即報錯：`寫入被拒絕：Flash WEL (Write Enable Latch) 為 0，請先點擊『寫入致能 WREN (0x06)』！`。
2. 點擊「寫入致能 WREN (0x06)」使 WEL 置 1，再執行 Page Program，寫入順利成功且 WEL 自動清除為 0。
3. 該實驗幫助工程師建立「每次 Program/Erase 前都必須發送 WREN」的嚴謹韌體開發規範。

