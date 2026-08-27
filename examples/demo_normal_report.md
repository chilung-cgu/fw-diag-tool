# I2C / SMBus / PMBus Protocol Diagnostic Report (協定診斷報告)

> **總結摘要 (Summary)**: 共分析 53 筆實體事件，歸納為 18 筆邏輯交易，涵蓋 4 個從裝置。共偵測出 0 筆協定診斷異常。

## 1. 匯流排時序與交易健康啟發評等 (Bus Timing & Health)

> 本健康度摘要為協定層證據之啟發式統計，非實體電氣特性或晶片良率之通過判定。

- **標準速度模式 (Nominal Speed Mode)**: `Custom / Unknown Speed（自訂 / 未知速率）`
- **平均 SCL 時鐘頻率 (Average Clock Frequency)**: `不可用 (Unavailable)` (來源無每位元組時序或位元率證據)
- **時鐘頻率抖動 (Clock Frequency Jitter)**: `不可用 (Unavailable)`
- **頻率分佈跨度 (Frequency Spread p-p)**: `不可用 (Unavailable)`
- **時鐘延展事件 (Clock Stretching Events)**: `0` 筆 (最大持續時間: `0.000 ms`)
- **位元組間平均延遲 (Avg Inter-byte Delay)**: `25.00 µs` (最大值: `25.00 µs`)
- **交易間平均間隔 (Avg Inter-transaction Delay)**: `0.00 ms`
- **匯流排使用率 (Bus Utilization)**: `不可用 (Unavailable)` (總捕捉時間不可用)

## 2. 偵測之從裝置分佈表 (Detected Peripheral Device Map)

| 7-bit 位址 | 8-bit 位址 (W/R) | 識別晶片型號 (Device Profile) | 裝置類別 (Category) | 協定 (Protocol) | 交易次數 |
|---|---|---|---|---|---|
| `0x58` | `0xB0` | **Possible: PMBus Power Controller / VR (XDPE / ISL / TPS / MP / MAX); Delta / Murata / BelPower PMBus PSU** | PMBus (ambiguous candidates) | PMBus | 11 |
| `0x50` | `0xA0` | **Possible: AT24Cxx / 24LCxx EEPROM; DDC / EDID Display EEPROM** | EEPROM (ambiguous candidates) | EEPROM | 3 |
| `0x48` | `0x90` | **Possible: LM75 / TMP75 / TMP102 Temperature Sensor; ADT7410 / ADT7420 High-Accuracy Temp Sensor** | 溫度感測器 | I2C | 2 |
| `0x20` | `0x40` | **Possible: PCA9555 / TCA9539 / PCA9535 16-bit GPIO Expander; PCF8574 / PCF8574A 8-bit Quasi-bidirectional GPIO Expander; MCP23017 / MCP23008 GPIO Expander** | GPIO 擴充晶片 | I2C | 2 |

## 3. 封包交易序列與解碼明細 (Transaction Sequence & Decoded Telemetry)

| # | 時間 Time (s) | 位址 Addr | 方向 R/W | 原始資料 (Raw Hex) | 協定語意與遙測解碼 (Decoded Telemetry) | 狀態 (Status) |
|---|---|---|---|---|---|---|
| 1 | 0.000100 | `0x58` | `WRITE` | `[0x00, 0x00]` | PAGE = Rail 0 | ACK |
| 2 | 0.000200 | `0x58` | `WRITE` | `[0x01, 0x80]` | OPERATION = ON, Nominal (0x80) | ACK |
| 3 | 0.000300 | `0x58` | `WRITE` | `[0x20, 0x17]` | VOUT_MODE = 0x17 | ACK |
| 4 | 0.000400 | `0x58` | `WRITE` | `[0x88]` | READ_VIN command selected; response bytes are not present in this write phase | ACK |
| 5 | 0.000450 | `0x58` | `READ` | `[0x00, 0xE2]` | READ_VIN = 32.0 V | READ END NAK |
| 6 | 0.000600 | `0x58` | `WRITE` | `[0x8B]` | READ_VOUT command selected; response bytes are not present in this write phase | ACK |
| 7 | 0.000650 | `0x58` | `READ` | `[0x1A, 0x02]` | READ_VOUT = 1.0508 V (exp=-9) | READ END NAK |
| 8 | 0.000800 | `0x58` | `WRITE` | `[0x8D]` | READ_TEMPERATURE_1 command selected; response bytes are not present in this write phase | ACK |
| 9 | 0.000850 | `0x58` | `READ` | `[0xE0, 0xE2]` | READ_TEMPERATURE_1 = 46.0 °C | READ END NAK |
| 10 | 0.001000 | `0x58` | `WRITE` | `[0x79]` | STATUS_WORD: insufficient data (received 0 byte(s), expected 2) | ACK |
| 11 | 0.001050 | `0x58` | `READ` | `[0x00, 0x00]` | STATUS_WORD=0x0000 -> OK / All Clean | READ END NAK |
| 12 | 0.001500 | `0x50` | `WRITE` | `[0x00, 0x55, 0xAA, 0x12, 0x34]` | EEPROM write not decoded: address width/page size unavailable; select an explicit EEPROM profile | ACK |
| 13 | 0.002000 | `0x50` | `WRITE` | `[0x00]` | EEPROM write not decoded: address width/page size unavailable; select an explicit EEPROM profile | ACK |
| 14 | 0.002050 | `0x50` | `READ` | `[0x55, 0xAA, 0x12, 0x34]` | EEPROM Sequential Read (4 bytes): [55 AA 12 34] | READ END NAK |
| 15 | 0.002500 | `0x48` | `WRITE` | `[0x00]` | 設定暫存器指標為 TEMP_REG (0x00) | ACK |
| 16 | 0.002550 | `0x48` | `READ` | `[0x19, 0x20]` | Temperature = 25.12 °C (LM75/TMP102, raw 0x1920) | READ END NAK |
| 17 | 0.003000 | `0x20` | `WRITE` | `[0x06, 0x00]` | CONFIG_DIR_PORT_0 = 0b00000000 (0x00) | ACK |
| 18 | 0.003100 | `0x20` | `WRITE` | `[0x02, 0xA5]` | OUTPUT_PORT_0 = 0b10100101 (0xA5) | ACK |

## ⚠ 資料證據與品質限制 (Data Quality Limitations)

- **I2C_EEPROM_PROFILE_UNAVAILABLE** (2 筆): 目標位址存在多種可能裝置（如 EEPROM），在未指定明確 Board Profile 或位址寬度前，保留 Offset/分頁解碼。
- **I2C_PMBUS_PAYLOAD_TRUNCATED** (1 筆): PMBus 指令回應位元組數小於標準規格長度，已保留狀態與遙測數據解碼。
- **I2C_TIMING_UNAVAILABLE** (53 筆): 未提供每位元組持續時間或傳輸速率證據，SCL 時鐘頻率不可用。

## 4. 異常診斷與排查行動建議 (Diagnostic Issues & Debugging Advice)

⚠ **在現有證據下未發現違規規則，但來源資料品質不完整；在確認通訊正常前請先檢視上方資料限制。**
