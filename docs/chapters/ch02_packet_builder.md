# I2C 封包模擬器與多平台 C 驅動產生

## 1. 本章導讀與核心價值

在嵌入式系統與韌體開發中，工程師常面臨兩大挑戰：
1. **尚未拿到硬體板卡前**：需要先理解目標晶片（如 EEPROM、RTC、感測器、PMBus VR）的讀寫時序序列（START、Address、Register Offset、Repeated START、Data、ACK/NACK、STOP），避免在撰寫驅動程式時犯下基本的協定邏輯錯誤。
2. **需要跨平台實作驅動時**：相同的暫存器讀寫邏輯，在 Linux Userspace（`i2c-dev`）、OpenBMC Shell（`i2ctransfer`）、STM32 MCU（`HAL_I2C`）與 Arduino（`Wire.h`）上的 API 結構與暫存器長度處理方式截然不同。

本頁面 **「🎨 I2C 封包模擬器與驅動產生」** 提供：
- **封包模擬與理想波形產生器**：在無硬體連接的情況下，由使用者自訂位址、讀寫方向、暫存器位移、資料長度與位元寬度，即時繪製微秒級的理想 SCL/SDA 數位方波與協定軌道。
- **多平台 C 語言驅動代碼產生器**：自動輸出 4 大主流嵌入式平台的驅動代碼片段，大幅縮短開發與除錯時間。

> **重要觀念宣告：**
> 
> 本頁面產出的波形為「協定理想時序模型（Ideal Protocol Model）」，並非實際硬體上的 Logic Analyzer 取樣結果，不能用於評估訊號品質（如電壓、上升時間、雜訊）。Read 操作中的資料內容為長度佔位符，真實資料必須由硬體裝置提供。

---

## 2. 參數設定與操作步驟

進入 GUI 第 2 頁 **「🎨 I2C 封包模擬器與驅動產生」**，依序設定以下參數：

| 參數名稱 | 範例值 | 說明與輸入規則 |
|---|---|---|
| **Slave 7-bit Address** | `0x50` | 目標晶片的 7-bit I2C 位址（支援 16 進位字串）。 |
| **Operation (R/W)** | `Write` 或 `Read` | 選擇通訊方向（寫入暫存器或自暫存器讀取）。 |
| **Register Offset** | `0x00` 或 `0x1000` | 目標暫存器位移（Offset / Command Code）。 |
| **Write Data Bytes (Hex)** | `0xAA 0xBB` | （僅 Write 時生效）寫入的資料序列，以空白分隔。 |
| **Read Length (bytes)** | `2` | （僅 Read 時生效）預計自 Slave 讀回的 Byte 數量（1~255）。 |
| **I2C Bus Number** | `1` | 目標系統的匯流排編號（用於 Linux `/dev/i2c-N` 或 OpenBMC）。 |
| **Register Width (bits)** | `8` 或 `16` | 暫存器位址寬度。8-bit（如一般感測器）或 16-bit（如大容量 EEPROM 24C64）。 |

---

## 3. 實戰教學一：看懂一個標準 Write（暫存器寫入）

以 `Slave: 0x50 / Write / Reg: 0x10 / Data: 0xAA 0xBB / Reg Width: 8-bit` 為例：

### 波形循序解析
在上方波形圖中，SCL 與 SDA 方波按以下時序嚴格展開：

1. **START 條件**：SCL 保持 High 時，SDA 產生下降邊緣（1 → 0），代表 Master 取得匯流排控制權。
2. **Address Byte 發送 (`0x50` + W = `0xA0`)**：
   - 7-bit 位址 `0x50`（`0101000b`）左移一位，最末位補 `0`（Write），組成 8-bit 位元組 `0xA0`（`10100000b`）。
   - MSB 到 LSB 依序在 SCL High 期間被 Slave 取樣。
   - **第 9 個 Clock (ACK)**：Slave 將 SDA 拉低為 Low，確認位址存在。
3. **Register Offset 發送 (`Reg:0x10`)**：
   - Master 送出 `0x10`，指定晶片內部暫存器位址。
   - **第 9 個 Clock (ACK)**：Slave 回應 ACK。
4. **Data Bytes 發送 (`0xAA`, `0xBB`)**：
   - 依序發送 `0xAA`（`10101010b`）與 `0xBB`（`10111011b`）。
   - 每個 Byte 後均緊隨 Slave 的 ACK 位元。
5. **STOP 條件**：SCL 保持 High 時，SDA 產生上升邊緣（0 → 1），Master 釋放匯流排。

> ⚠️ **硬體安全提醒**：寫入指令可能直接改變周邊暫存器或改寫 EEPROM；在實際硬體執行產出的寫入指令前，務必再三核對位址與資料！

---

## 4. 實戰教學二：看懂 Combined Read（複合暫存器讀取）

以 `Slave: 0x50 / Read / Reg: 0x10 / Read Length: 2 / Reg Width: 8-bit` 為例：

多數 I2C 周邊讀取暫存器時，無法「直接讀取」，必須先告訴晶片「我要讀哪個暫存器」。這需要由兩段交易組成的 **Combined Transaction（複合交易）**：

```
[START] -> Addr(W) -> ACK -> Reg(0x10) -> ACK -> [Repeated START] -> Addr(R) -> ACK -> Data#1 -> Master ACK -> Data#2 -> Master NACK -> [STOP]
```

### 波形循序解析
1. **第一階段：Write Register Pointer（設定指標）**
   - 發送 `0x50 (W)` 與暫存器位址 `0x10`。
   - **注意**：此時 **不發送 STOP 條件**，而是立即切入 Repeated START。
2. **第二階段：Repeated START (Sr)**
   - SCL 為 High 時再次產生 SDA 下降邊緣。Repeated START 的作用在於「不釋放匯流排（防止多 Master 系統被搶佔）」，直接切換讀寫方向。
3. **第三階段：Address Read (`0x50` + R = `0xA1`)**
   - 重新發送位址，最末位改為 `1`（Read）。Slave 回應 ACK。
4. **第四階段：Slave 回傳資料與 Master 終止訊號**
   - Slave 回傳第 1 個 Byte：Master 在第 9 個 Clock 回應 **ACK (Low)**，表示「請繼續送下一個 Byte」。
   - Slave 回傳第 2 個 Byte（最後一個預期 Byte）：Master 在第 9 個 Clock 回應 **NACK (High)**！
   - **資深關鍵觀念**：此處的 NACK 是 Master 發出的「正常終止訊號」，通知 Slave 停止發送，**絕非故障或錯誤**！
5. **STOP 條件**：Master 發出 STOP 結束通訊。

---

## 5. 四大平台 C 語言驅動代碼深度解析

在波形圖下方，工具即時產出 4 大平台的驅動程式碼：

### 5.1 Linux Userspace (`i2c-dev`)
適用於嵌入式 Linux（如 Raspberry Pi、工業電腦、Yocto 系統）：
- **Combined Read**：採用 `ioctl(file, I2C_RDWR, &transfer)`，將 Write Reg 與 Read Data 打包在同一組 `i2c_msg` 陣列中，底層驅動會自動產生 Repeated START。
- **Direct Write**：採用標準 `ioctl(file, I2C_SLAVE, addr)` 搭配 `write()` 系統呼叫。

### 5.2 OpenBMC / Linux CLI (`i2c-tools`)
適用於 BMC Shell 快速除錯或 Bash 腳本撰寫：
- **語法**：`i2ctransfer -y <bus> w<len>@<addr> <reg> r<len>`
- **範例**：`i2ctransfer -y 1 w1@0x50 0x10 r2`
- **參數說明**：`w1@0x50 0x10` 代表向 0x50 寫入 1 byte 暫存器位移；`r2` 代表以 Repeated START 讀回 2 bytes。

### 5.3 STM32 HAL C Driver
適用於 STM32 系列 MCU 韌體開發：
- **函式**：`HAL_I2C_Mem_Read()` 與 `HAL_I2C_Mem_Write()`。
- **暫存器寬度適配**：若選擇 16-bit Register，工具會自動產生 `I2C_MEMADD_SIZE_16BIT` 與 16-bit 16進位位移值，完全符合 STM32 HAL 標準。

### 5.4 Arduino / ESP32 (`Wire.h`)
適用於快速原型驗證或 Maker 專案：
- **關鍵用法**：`Wire.endTransmission(false);`
- **說明**：傳入 `false` 參數即代表「發送完暫存器位址後不發送 STOP，保持 Bus 控制並發出 Repeated START」，隨後呼叫 `Wire.requestFrom()` 讀回資料。

