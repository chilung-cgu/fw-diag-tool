# 第二章：I2C 封包模擬器與多平台 C 驅動產生

## 這兩個功能在做什麼？

### 封包模擬器（造波形）
讓你在沒有硬體的情況下，「虛構」一筆 I2C 通訊（指定位址、讀寫方向、暫存器偏移量與資料），
系統會即時畫出這筆通訊的理想 SCL/SDA 數位方波。
用途：對照手冊規格與實際示波器波形，理解每個 Bit 在匯流排上的樣子。

### 驅動代碼產生
根據你指定的位址與操作，自動產出 4 大平台的 C 語言驅動程式碼片段。

## 怎麼操作？

1. 進入 GUI 第 2 頁 **「🎨 I2C 封包模擬器與驅動產生」**。
2. 填寫參數：Slave Address (`0x50`)、Operation (`Write/Read`)、Register Offset (`0x10`)、Data Bytes (`0xAA 0xBB`)。
3. 頁面上方顯示理想波形圖，下方展開 4 平台 C 代碼。

## 四大平台代碼解釋

| 平台 | 函式庫 | 使用場景 |
|---|---|---|
| Linux Userspace | `<linux/i2c-dev.h>` + `i2c_smbus_*()` | 使用者空間透過 `/dev/i2c-N` 操作 |
| OpenBMC / CLI | `i2cget` / `i2cset` / `i2ctransfer` | BMC shell 快速除錯 |
| STM32 HAL | `HAL_I2C_Mem_Read()` / `HAL_I2C_Mem_Write()` | STM32 MCU 韌體開發 |
| Arduino Wire | `Wire.beginTransmission()` / `Wire.write()` | Arduino / ESP32 快速原型 |
