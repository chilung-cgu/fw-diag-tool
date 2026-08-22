# Junior 韌體工程師全方位實戰上手與除錯指南

歡迎使用 **Firmware Diagnostic Toolkit (`fw-diag-tool`)**！
本指南專為 **0 基礎 / Junior 韌體與硬體工程師** 設計，從「硬體電氣訊號」到「通訊協定封包」、再到「軟韌體驅動實作」，以圖文、範例資料（Test Data）與 Step-by-Step 步驟，引導你掌握日常開發與現場除錯必備的核心技能。

---

## 快速啟動 Web 視覺化工作站

在 macOS / Linux 終端機中執行：

```bash
cd ~/fw-diag-tool
# 啟動 Web 視覺化除錯工作站
fw-diag gui
```

瀏覽器將自動開啟 `http://127.0.0.1:8501`，左側側邊欄可切換 12 大功能模組。

---

## 第一章：I2C / PMBus 波形診斷與數位波形檢視

### 1.1 背景心智模型：為什麼光看數字不夠，一定要看波形？
- **I2C 物理層 (L1)** 只有兩條線：**SCL (時鐘線)** 與 **SDA (資料線)**，兩條線均透過上拉電阻（Pull-up Resistor）接至 3.3V / 1.8V。
- **標準通訊時序**：
  1. **START**：SCL 為高電平 (High) 時，SDA 由 High 掉到 Low。
  2. **8 個 Data Bits + 1 個 ACK Bit = 9 個 Clock Pulse**：
     - 在 SCL 為 Low 時，SDA 改變電平（Setup）；在 SCL 為 High 時，SDA 保持穩定（Sample）。
     - 第 9 個 Pulse 時，發送端釋放 SDA，**接收端若正常收到，必須將 SDA 強行拉低 (ACK = 0)**；若接收端沒拉低（保持 High），即為 **NACK = 1**。
  3. **STOP**：SCL 為 High 時，SDA 由 Low 升到 High。

---

### 1.2 測試資料演練與 Step-by-Step 操作

- **測試資料路徑**：`examples/data/i2c_golden.csv` 或點擊介面上的 **「載入內建測試波形」**。
- **步驟 1**：進入 GUI 第 1 頁 **「📊 I2C / PMBus 診斷與波形檢視」**。
- **步驟 2**：點擊「載入內建測試波形」按鈕。
- **步驟 3**：觀察頂部 4 大 KPI 卡片：
  - `總傳輸次數`：統計共抓取了幾筆交易（Transaction）。
  - `異常事件數`：若為 0 表示全數通訊合規；若大於 0 會標註紅色警告。
  - `平均時鐘頻率`：判斷目前是標準模式（100 kHz）還是快速模式（400 kHz）。
  - `時鐘抖動 (Jitter)`：若 Jitter > 35%，通常代表中斷 ISR 搶佔嚴重或硬體電容過大。
- **步驟 4 (看波形)**：切換至 **「📈 數位方波與協定軌 (Waveform)」** 分頁：
  - 下拉選單選擇任一筆交易（如 `Tx #1: 0x70 (WRITE)`）。
  - 畫面即刻繪出 SCL 與 SDA 的微秒級數位方波！
  - **彩色協定軌 (Protocol Annotation Track)**：
    - `[START]` (綠色)：起始訊號。
    - `[0x70 (W)]` (藍色)：7-bit Slave 位址 + 寫入方向。
    - `[ACK]` (綠色)：Slave 回應確認。
    - `[0x04]` (紫色)：傳送的資料內容。
    - `[STOP]` (粉色)：停止訊號。
  - **互動操作**：使用滑鼠滾輪可自由放大 (Zoom In) 到單個 Clock Cycle 觀察 SDA 轉折，按住滑鼠可左右平移 (Pan)。

---

### 1.3 常見故障與 Root Cause Analysis (RCA) SOP

| 故障現象 | 波形特徵 | 根本原因 (Root Cause) | 新手排查行動清單 (Checklist) |
|---|---|---|---|
| **Address NACK** | 第 9 個 Clock Pulse 時，SDA 仍為 High (紅色 NAK) | Slave 晶片完全沒有回應 | 1. 用萬用表量測 Slave 晶片 VCC 是否有 3.3V 供電。<br>2. 檢查晶片硬體 A0/A1/A2 位址設定腳位是否接地/接高。<br>3. 檢查程式碼中 7-bit 位址 (0x50) 是否被誤寫為 8-bit (0xA0)。 |
| **Data NACK** | 前面 Address 有 ACK，傳輸到一半突然出現 NACK | Slave 拒絕接收後續資料 | 1. 若為 EEPROM，前一次寫入尚未完成內部燒錄週期 (tWR 5ms)，晶片正忙。<br>2. 寫入的 Register Offset 超出晶片硬體範圍。 |
| **Clock Stretching 逾時** | SCL 被 Slave 持續拉低超過 25ms 不釋放 | Slave MCU 當機或在中斷中死鎖 | 1. 檢查 Slave MCU 是否發生 HardFault 或中斷未清除。<br>2. Master 韌體需啟動 25ms 逾時計時器並執行 SCL 9-Clock Reset 恢復匯流排。 |
| **EEPROM Page Rollover** | 連續寫入超過 Page Size (如 24C64 的 32B) | EEPROM 內部指標在 Page 內循環覆蓋 | 1. 韌體中封裝寫入函式時，必須以 Page 為邊界分段寫入 (Chunked Write)。 |

---

## 第二章：I2C 封包模擬器與多平台 C 驅動產生

### 2.1 功能說明
新人工程師常遇到「讀懂了手冊，卻不知道怎麼寫第一行驅動程式」的問題。本模組讓你輸入想通訊的位址與資料，即刻產生「標準理想波形」並一鍵產出 4 大主流平台代碼。

### 2.2 操作步驟
1. 進入 GUI 第 2 頁 **「🎨 I2C 封包模擬器與驅動產生」**。
2. 設定參數：
   - `Slave 7-bit Address`：輸入 `0x50` (EEPROM)。
   - `Operation`：選擇 `Write` 或 `Read`。
   - `Register Offset`：輸入 `0x10`。
   - `Data Bytes`：輸入 `0xAA 0xBB`。
3. 頁面上方立即生成標準的 SCL/SDA 理想方波，供你與示波器實測波形進行比對。
4. 下方展開 4 大平台代碼，直接複製進專案：
   - **Linux Userspace (i2c-dev)**：`ioctl(file, I2C_SLAVE, 0x50); i2c_smbus_write_byte_data(...);`
   - **OpenBMC / Linux CLI**：`i2cset -y -f 1 0x50 0x10 0xAA b`
   - **STM32 HAL C Driver**：`HAL_I2C_Mem_Write(&hi2c1, (0x50 << 1), 0x10, ...);`
   - **Arduino / Baremetal**：`Wire.beginTransmission(0x50); Wire.write(0x10); ...`

---

## 第三章：Golden vs Failing 雙波形差分對比 (Waveform Diff)

### 3.1 什麼時候使用？
- **硬體 A/B 測試**：產線上「正常板卡 (Golden)」通訊成功，但「不良板卡 (Failing)」開機失敗。
- **韌體升級驗證**：修改 Driver 前抓一份波形，修改後抓一份波形，快速比對兩者時序與封包是否脫節。

### 3.2 操作與判讀
1. 進入 GUI 第 3 頁 **「⚖️ 雙波形對比檢視 (Waveform Diff)」**。
2. 上傳測試檔案：
   - Golden CSV：上傳 `examples/data/i2c_golden.csv`。
   - Failing CSV：上傳 `examples/data/i2c_failing_nack.csv`。
3. 系統自動進行逐筆交易對比，並標註：
   - 🚨 `Found 1 divergence point(s). First mismatch at Transaction #3.`
   - `現象描述`: ACK mismatch on 0x50: Golden NACK=False, Failing NACK=True.
   - `排查建議`: Slave 晶片在故障板卡上返回 NACK，可能未上電、被 Reset 或內部忙碌。
4. 下方自動繪出上下兩組波形對照圖，一眼看出第 3 筆交易中 Failing 波形在 SDA 上出現紅色 NACK 脈衝！

---

## 第四章：UART Serial Crash Dump 與 ARM HardFault 智慧診斷

### 4.1 Linux Kernel Panic 診斷
- **測試資料**：`examples/data/kernel_panic_nvme.log`。
- **判讀重點**：
  1. `Faulting Address: 0x0000000000000010`：存取位址小於 0x1000，判定為 **NULL Pointer Dereference**（結構體指標為 NULL，存取 offset 0x10 的成員變數）。
  2. `RIP: nvme_pci_complete_rq+0x38/0x120`：點出出錯的函式與偏移量。
  3. `Call Trace`：清楚展開中斷處理與函式呼叫鏈。

### 4.2 STM32 / ARM Cortex-M HardFault 診斷
- **測試資料**：`examples/data/arm_hardfault_stm32.log`。
- **SCB 狀態暫存器解讀指南**：
  - **HFSR.FORCED (0x40000000)**：表示原本的 Configurable Fault（如 UsageFault/BusFault）因未開啟獨立中斷而升級為 HardFault。
  - **CFSR.DIVBYZERO (0x02000000)**：分母為 0 引發除以零硬體中斷。
  - **CFSR.UNALIGNED (0x01000000)**：用 `uint32_t*` 指標存取了奇數記憶體位址。
  - **CFSR.IMPRECISERR (0x00000400)**：非同步總線寫入錯誤（通常是周邊時鐘 RCC 未開就去寫暫存器）。
  - **Stacked PC**：精確指向當機瞬間 CPU 正在執行的組合語言指令位址，可用 `arm-none-eabi-addr2line -e firmware.elf <PC>` 查出源碼行號！

---

## 第五章：MCTP (DSP0236/PLDM/SPDM) 與 IPMB 伺服器管理協定

### 5.1 測試資料演練
- **測試資料**：`examples/data/mctp_pldm_sample.hex` 與 `examples/data/ipmb_sample.hex`。
- **判讀重點**：
  - **MCTP**：解析 `EID 0x00 -> 0x08`，識別 `MsgType 0x01 (PLDM Platform Monitoring)`，提取感測器讀取指令與溫度讀數 `25.5°C`。
  - **IPMB**：自動驗證 Checksum 1 與 Checksum 2，分離 NetFn (`0x06 App`) 與 Cmd (`0x01 Get Device ID`)，並標記回應碼 `CC: 0x00 (Success)`。

---

## 第六章：Linux & OpenBMC Device Tree (.dts) 自動產生器

### 6.1 操作說明
1. 進入 GUI 第 6 頁 **「🌲 Device Tree (.dts) 產生器」**。
2. 輸入 I2C Bus Number (如 `1`) 與 PCA9548A MUX 位址 (`0x70`)。
3. 系統自動產生符合 **Devicetree Specification v0.4** 標準的 `.dtsi` 代碼：
   - 自動將各通道設備掛載至 `i2c@0`, `i2c@1`...
   - 遵循連字符命名標準 (`temp-sensor@48`, `power-monitor@40`, `eeprom@50`)。
4. 點擊「下載 i2c_bus1.dtsi」即可直接 include 進你的 OpenBMC / Linux BSP 專案！

---

## 第七章：PCIe Config Space、AER 嚴重錯誤與 Link 降級排查

### 7.1 測試資料演練
- **測試資料**：`examples/data/pcie_aer_lspci.txt`。
- **判讀重點**：
  1. **Link 降級偵測 (Link Health)**：
     - Maximum Capable: `16.0 GT/s (Gen4) x16`
     - Negotiated Status: `2.5 GT/s (Gen1) x1`
     - 診斷系統標記：`🚨 DEGRADED`，並提示檢查金手指髒污、Riser 轉接卡訊號完整性與 100MHz 差分時脈。
  2. **AER 4DW TLP Header Log 解碼**：
     - 將 `00000001 0100000f fe000000 00000000` 還原為當下發送的 `Memory Write 3DW` 封包、目標位址 `0xFE000000` 與長度。

---

## 第八章：SPI / QSPI NOR Flash 協定診斷

### 8.1 測試資料演練
- **測試資料**：`examples/data/spi_w25q128_sample.csv`。
- **判讀重點**：
  1. **JEDEC 0x9F ID 解析**：自動識別為 `Winbond W25Q128 (128 Mbit / 16 MB)`。
  2. **WREN 狀態追蹤**：檢查 Page Program (0x02) 前是否有發送 0x06 WREN。
  3. **Page Wrap 覆蓋警示**：若從 Offset 0xF0 連續寫入 30 Bytes，工具會警告超出 256-byte 邊界並發生迴轉覆蓋！

---

## 第九章：晶片暫存器 Bitfield 視覺化與 C 巨集生成

### 9.1 操作說明
1. 進入 GUI 第 9 頁與第 10 頁。
2. 選擇內建之 `pmbus_standard.yaml` 或 `pcie_aer_registers.yaml`。
3. 輸入 Raw Hex (如 `0x8400`)：
   - 介面自動展開每個 Bit 欄位的狀態與警告圖示 (⚠️)。
4. 一鍵產生 MISRA-C 規範標頭檔，包含安全型別轉型的 `REG_..._GET(val)` 與 `REG_..._SET(reg, val)` RMW 巨集。

---

## 第十章：Junior FW 20 大實戰故障演練場 (Fault Arena)

在 GUI 第 11 頁中，整理了 20 個一線大廠高頻發生的硬韌體真實故障案例：
- *Case 01~05*：I2C NACK、Clock Stretching、EEPROM 跨頁覆蓋、MUX 通道衝突。
- *Case 06~10*：PMBus 負微調計算、PCIe Gen4 降速 Gen1、AER CTO 逾時、Malformed TLP。
- *Case 11~14*：SPI Flash 遺漏 WREN、256B Wrap 覆蓋、MISO 浮接 (0xFF) / 短路 (0x00)。
- *Case 15~18*：Kernel Panic NULL Pointer、ARM HardFault DIVBYZERO、UNALIGNED、IMPRECISERR。
- *Case 19~20*：MCTP PLDM 順序錯亂、IPMB Checksum 校驗錯誤。

新人工程師可逐案點選研讀，快速累積相當於 2~3 年現場 Debug 的實戰直覺！

---

## 附錄 A：圖表判讀完全指南 (Chart Interpretation Guide)

### A.1 SCL Clock Frequency Distribution（時脈頻率分佈直方圖）

**這張圖在做什麼？**
統計每一個 I2C Byte 傳輸的實際 SCL 時脈頻率（kHz），並以直方圖呈現分佈情況。

**X 軸（SCL Clock Frequency in kHz）**：
- 100 kHz = Standard-mode（標準模式）
- 400 kHz = Fast-mode（快速模式）
- 1000 kHz = Fast-mode Plus

**Y 軸（count）**：出現在該頻率區間的 Byte 傳輸次數。

**怎麼判讀？**

| 圖形特徵 | 意義 | 排查方向 |
|---|---|---|
| **單一窄峰**（如全部集中在 360 kHz）| 匯流排時脈穩定，Master 固定頻率運作 | 正常，無需處理 |
| **多峰分散**（如 100k 和 400k 同時出現）| 不同 Master 或 Clock Stretching 導致頻率變異 | 檢查 Clock Stretching 或多 Master 衝突 |
| **寬廣散佈**（Jitter > 35%）| 時脈不穩定，可能為 ISR 搶佔或硬體電容過大 | 檢查中斷服務常式延遲、上拉電阻值 |
| **頻率遠低於設定值**（如設定 400k 但實測 100k）| 匯流排負載過重或 Master 降速 | 檢查上拉電阻是否過大 (>4.7kOhm) 或總線電容 >400pF |

> 新手提示：如果你只看到一根柱子，這是正常的！表示所有 Byte 都以相同頻率傳輸，匯流排時序非常穩定。

---

### A.2 Bus Transaction Timeline & Active Device Map（匯流排交易時間軸與設備地圖）

**這張圖在做什麼？**
以時間軸（X 軸）為基準，將每一筆 I2C 交易按「哪個 Slave 被存取（Y 軸）」與「成功/失敗（顏色）」繪製成散點圖。

**X 軸（Start Time in seconds）**：交易的起始時間。
**Y 軸（Device）**：被存取的 Slave 設備名稱。
**圓點大小**：交易持續時間（Duration in ms），越大表示該筆交易佔用匯流排越久。
**圓點顏色**：
- 綠色 **ACK**：交易成功完成，Slave 正常回應。
- 橘色 **DATA NAK**：Address 有 ACK 但資料傳輸中被 NACK。
- 紅色 **ADDR NAK**：Slave 沒有回應 Address（完全沒有 ACK）。

**怎麼判讀？**

| 觀察重點 | 意義 | 排查方向 |
|---|---|---|
| **全部綠色** | 所有交易成功，匯流排健康 | 正常 |
| **某個設備出現橘色/紅色點** | 該設備通訊異常 | 檢查該設備供電、位址設定或是否忙碌中 |
| **某個時間點突然出現紅色** | 匯流排在該時刻發生故障 | 檢查該時間點附近是否有電源瞬斷或 ESD 干擾 |
| **同一設備連續多次 ACK** | 韌體在連續讀寫該設備 | 正常行為，如連續讀取 EEPROM |
| **同一設備連續多次 NACK** | 韌體在重試（Retry Loop） | 檢查驅動程式是否有無限重試邏輯 |

> 新手提示：把滑鼠游標懸停在圓點上，會顯示該筆交易的詳細資訊（Transaction ID、方向、資料長度、持續時間）。

---

### A.3 匯流排物理層健康評等（Device Health Grade Table）

**這張表在做什麼？**
對匯流排上每一個 Slave 設備進行自動化健康評分，類似學校的 A/B/C/D/F 成績。

**評分欄位說明**：

| 欄位 | 意義 |
|---|---|
| **Slave Address** | 該設備的 7-bit I2C 位址（如 0x50） |
| **Device Name** | 根據位址自動識別的晶片型號（如 AT24Cxx EEPROM） |
| **Category** | 設備類別（如 EEPROM/Memory、Temperature Sensor、PMBus） |
| **Total Transactions** | 該設備被存取的總次數 |
| **NACK Count** | 該設備發出 NACK 的次數（越多越不健康） |
| **Success Rate** | 成功率 = (Total - NACK) / Total x 100% |
| **Clock Stretches** | 該設備拉低 SCL 的次數（Clock Stretching） |
| **Health Grade** | 綜合評等：A/B/D/F |

**Health Grade 評分標準**：

| 等級 | 條件 | 白話解釋 |
|---|---|---|
| **A (Excellent)** | 成功率 >= 95% 且無 Clock Stretch | 完美！所有通訊都正常。 |
| **B (Minor Jitter)** | 成功率 >= 95% 但有 Clock Stretch，或成功率 80~95% | 偶爾有延遲或重試，但功能正常。 |
| **D (High NACK Rate)** | 成功率 < 80% | 超過 20% 的通訊失敗，需要排查！ |
| **F (Critical Fault)** | 成功率 < 50% 或 Clock Stretch >= 5 次 | 嚴重故障，該設備可能已損壞或未正確連接。 |

> 新手提示：如果你的測試資料中所有設備都是 A 或 B，表示硬體和韌體都正常。如果有 D 或 F，優先檢查該設備的供電與焊接。

---

### A.4 異常診斷面板（Anomalies Tab）判讀

**這個分頁在做什麼？**
列出所有自動偵測到的 I2C/SMBus 協定違規與時序異常，並提供 Root Cause 分析與排查行動清單。

**常見異常代碼說明**：

| 異常代碼 | 白話解釋 | 排查優先順序 |
|---|---|---|
| **I2C_ADDR_NACK** | Slave 沒有回應位址 | 1.量VCC 2.查A0/A1/A2腳位 3.檢查7-bit vs 8-bit |
| **I2C_DATA_NACK** | Slave 在資料階段 NACK | 1.EEPROM tWR 忙碌 2.Register Offset 越界 |
| **I2C_CLOCK_STRETCH_TIMEOUT** | Slave 拉低 SCL > 25ms | 1.Slave MCU 當機 2.執行 SCL 9-Clock Reset |
| **I2C_BUS_HANG_NO_STOP** | 匯流排未收到 STOP 條件 | 1.Master 韌體異常退出 2.發送 STOP 恢復 |
| **I2C_EEPROM_PAGE_ROLLOVER** | EEPROM 寫入跨頁覆蓋 | 1.以 Page Size 分段寫入 |
| **I2C_MUX_MULTI_CHANNEL** | MUX 同時開啟多通道 | 1.關閉其他通道 2.檢查位址衝突 |
