# 第二章：I2C 封包模擬器與多平台 C 驅動產生

## 這兩個功能在做什麼？

### 封包模擬器（造波形）
讓你在沒有硬體的情況下，「虛構」一筆 I2C 通訊（指定位址、讀寫方向、暫存器偏移量與資料），
系統會即時畫出這筆通訊的理想 SCL/SDA 數位方波。這是協定模型，不是 Logic Analyzer 的取樣結果，
不能用來判斷實際電壓、上升時間、clock stretching 或線路雜訊。
用途是先建立「一個 address byte、每個 data byte、ACK、START/STOP」在時間軸上的心智模型，
再拿它和第 1 頁的實測 raw digital capture 對照。

### 驅動代碼產生
根據你指定的位址與操作，自動產出 4 大平台的 C 語言驅動程式碼片段。

## 怎麼操作？

1. 進入 GUI 第 2 頁 **「🎨 I2C 封包模擬器與驅動產生」**。
2. 填寫 `Slave 7-bit Address`（例如 `0x50`）、`Operation`、`Register Offset`。
3. `Write` 時，在 `Write Data Bytes (Hex)` 輸入以空白分隔的 bytes，例如 `0xAA 0xBB`。
4. `Read` 時，`Read Length (bytes)` 代表預期從裝置讀回幾個 bytes；頁面不會虛構讀回內容，
   理想波形只顯示 read transaction 的方向與長度。
5. 頁面上方看理想波形，下方展開 4 個平台的程式碼模板。生成的程式碼仍須補上 include、錯誤處理、
   bus ownership、timeout 與目標平台的實際 API 設定，不能直接當成已驗證的 production driver。

## 第一次練習：先看懂一個 Write

用 `0x50 / Write / 0x10 / 0xAA 0xBB` 練習，按以下順序讀圖：

1. `START`：SDA 在 SCL 為高時由高變低，表示 master 開始傳輸。
2. address byte：`0x50` 左移一位後加上 Write bit，實際送出 `0xA0`；接著是 slave 的 ACK bit。
3. register byte：`0x10` 通常代表裝置內部 offset，但是否真的是 register 要以 datasheet 確認。
4. data bytes：依序是 `0xAA`、`0xBB`，每個 byte 後都有一個 ACK slot。
5. `STOP`：SDA 在 SCL 為高時由低變高，表示 master 釋放 bus。

如果你要判斷實際板卡是否真的送出這些 bits，請回到第 1 頁選擇
`Raw digital transition (Time, SCL, SDA)`，不要把這一頁的重建圖當作量測證據。

## 第二次練習：Read 的兩個容易混淆處

用 `0x50 / Read / 0x10 / Read Length = 2`。這個工具只描述「讀兩個 bytes」的請求，
不會假裝知道裝置回傳哪兩個值。典型 combined read 通常包含先寫入 register offset、
`Repeated START`、再以 Read bit 發出 address；controller 在最後一個讀回 byte 後送 NACK，
表示「我不再要下一個 byte」，這是正常結束，不是 slave 故障。

## 四大平台代碼解釋

| 平台 | 函式庫 | 使用場景 |
|---|---|---|
| Linux Userspace | `<linux/i2c-dev.h>` + `i2c_smbus_*()` | 使用者空間透過 `/dev/i2c-N` 操作 |
| OpenBMC / CLI | `i2cget` / `i2cset` / `i2ctransfer` | BMC shell 快速除錯 |
| STM32 HAL | `HAL_I2C_Mem_Read()` / `HAL_I2C_Mem_Write()` | STM32 MCU 韌體開發 |
| Arduino Wire | `Wire.beginTransmission()` / `Wire.write()` | Arduino / ESP32 快速原型 |
