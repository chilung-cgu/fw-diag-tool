# I2C 封包模擬器：canonical transaction 與多平台模板

第 2 頁 **「🎨 I2C 封包模擬器與驅動產生」** 只產生兩種東西：協定層的 ideal waveform，以及可供 review 的 driver/CLI template。它不連線、不讀取真實裝置、不量測 SCL/SDA；Read 的資料 byte 是 `Unknown` placeholder（只知道長度，不知道值）。

## 1. 輸入欄位與單位

| GUI 欄位 | 範例 | 契約 |
|---|---|---|
| `從裝置 7-bit 位址（Slave 7-bit Address）` | `0x50` | 7-bit address；generator 接受 `0x08`～`0x77`，不是 8-bit wire address `0xA0`。 |
| `操作類型（Operation）`（新版 GUI） | `register_write`／`combined_register_read`／`direct_write`／`direct_read` | 明確選擇 canonical operation，不再由 R/W 與 register 是否留空推測。 |
| `暫存器位移（Register Offset）` | `0x10`／`0x1234` | 8-bit 或 16-bit register/command offset；值域依 register width。 |
| `寫入資料位元組（Write Data Bytes，Hex）` | `0xAA 0xBB` | 每個 token 是 0～255 的一個 byte；只在 Write 使用。GUI 會依 operation/width 限制 data bytes：Direct Write 最多 3702、8-bit register 最多 3701、16-bit register 最多 3700（總理想波形上限 100,000 points）；parser 的絕對上限仍是 4096 bytes。 |
| `讀取長度（Read Length，bytes）` | `2` | 1～255 bytes；Read template 只配置 buffer，資料仍須由 hardware/capture 提供。 |
| `I2C 匯流排編號（I2C Bus Number）` | `1` | Linux `/dev/i2c-1` 與 `i2ctransfer 1` 的 bus number；不是 address。模板刻意不自動加 `-y`。 |
| `暫存器寬度（Register Width，bits）` | `8`／`16` | 決定 register offset 在 bus 上佔 1 或 2 bytes；不改變 payload data endian。 |
| `暫存器位元組順序（Register Byte Order）`（僅 16-bit） | `Big-endian / MSB first`／`Little-endian / LSB first` | 決定 register offset 兩個 byte 在 wire 上的順序；payload data bytes 不重排。 |
| `預期讀回資料（Expected Read Bytes；選填）` | `0x12 0x34` | 只標示 assumed waveform；byte 數必須等於 Read Length，不會進入生成程式碼或送出裝置。 |
| `理想時鐘頻率（Ideal Clock，kHz）` | `100` | 只影響 ideal waveform 時間軸；不是實測頻率。 |
| `模板逾時門檻（Template Timeout，ms）` | `25`／`100` | 目前只注入 STM32 HAL API 的 timeout 參數（向上取整為整數 ms）；Linux `i2c-dev`、i2c-tools 與 Arduino 模板需由呼叫端自行加入 timeout／取消策略；它不是 SMBus tTIMEOUT 量測或 datasheet 值。 |

## 2. 四個 canonical operations

先把「暫存器」和「直接」操作分清楚，再看 API 是否有 repeated START。

| Operation | Bus sequence | 何時使用 |
|---|---|---|
| **Register write** | `START → Addr(W) → ACK → Reg bytes → ACK → Data bytes → ACK → STOP` | EEPROM、sensor、PMBus command 寫入。 |
| **Direct write** | `START → Addr(W) → ACK → Data bytes → ACK → STOP` | 裝置協定沒有 register pointer，或 datasheet 明確要求 raw payload。 |
| **Register read（combined）** | `START → Addr(W) → ACK → Reg bytes → ACK → Repeated START → Addr(R) → ACK → Data → controller ACK…NACK → STOP` | 先指定 register/command，再讀回 response；保留 bus ownership。 |
| **Direct read** | `START → Addr(R) → ACK → Data → controller ACK…NACK → STOP` | 裝置允許從目前 pointer/stream 直接讀取。 |

Read 的最後一個 NACK 是 **controller 的正常 termination**：它告訴 slave 不要再送下一個 byte，接著由 controller 送 STOP。它不是 `I2C_DATA_NACK`。

## 3. Register width 與 endian

工具產出的 register offset 順序是明確的：

- **8-bit**：`0x10` → bus 上一個 byte `10`。
- **16-bit**：`0x1234` → **MSB first / big-endian register address**：`12 34`。
- Register offset endian 與 payload data endian 是兩個獨立契約。某些裝置的 16-bit measurement payload 可能是 little-endian；必須以 datasheet 的 payload ordering 為準，不要因 register offset 使用 MSB first 就自動交換資料。

以 `0x50 / Reg 0x1234 / Write 0xAB 0xCD` 為例，wire bytes 是：

```text
Address(W) = 0xA0；Register = 0x12 0x34；Payload = 0xAB 0xCD
```

`0xA0` 是由 `7-bit 0x50 << 1` 得到的 write wire byte；程式 API 仍應依平台慣例傳 7-bit address。

## 4. Ideal waveform 怎麼讀

GUI 使用 default 100 kHz 的理想協定模型繪製 START、8-bit address byte、每 byte 的 ACK slot、data、Repeated START 與 STOP。這個時間軸是 **Reconstructed / Ideal**：不能證明硬體真的跑在 100 kHz，也不能回答電壓、rise time、clock stretch、noise 或 pull-up。

GUI 先顯示 **Canonical Transaction Preview**：每個 segment 的 START/Sr、R/W、7-bit address、wire address byte、payload 與 final ACK slot 都來自同一份 spec。Read payload 預設標示 `Unknown`；若使用者填入 Expected Read Bytes，波形只會加上 `Expected ... (assumed)`，生成程式碼仍不會包含這些假設值。

Register read 的概念圖：

```text
[START] Addr(W) ACK Reg ACK [Repeated START]
        Addr(R) ACK Data#1 ACK ... Data#N controller-NACK [STOP]
```

Read 的 data bytes 在 GUI 中預設為 `Unknown` placeholder；波形為了維持 digital bit 區段會使用不具語意的繪圖電平，但 annotation 明確標成 `Unknown`，不代表 `0xFF` 回應。不要把 waveform 或生成的 `rx_buf` 當成裝置回應。要驗證回傳內容，請匯入第 1 頁的 per-byte/raw capture，或在目標板上執行 driver 後保存 log。

## 5. Bus、clock 與 timeout 的邊界

- `I2C Bus Number` 只會進入 `/dev/i2c-N`、`i2ctransfer N` 或使用者自己選擇的 HAL handle；它不能由 GUI 推導實際 wiring。生成的 CLI 刻意省略 `-y`，讓 i2c-tools 在互動終端先確認；自動化腳本必須自行承擔明確的安全 gate。
- Write data 的 4096-byte parser 上限不是 GUI 的實際可用上限：為避免 Plotly/瀏覽器放大，GUI 另外把 ideal waveform 限在 100,000 points，因此上表的 3702/3701/3700 是依 register phase 預留後的 effective limits；超出會在產生 waveform 前拒絕。
- ideal waveform 的 100 kHz 是模型預設值。第 1 頁只有 raw digital transition 或來源提供的 per-byte duration/bitrate 才能顯示 measured frequency。
- GUI 第 1 頁的 SMBus clock-stretch timeout 預設為 **25 ms**（可調範圍 1～100 ms）。達到設定值才會產生 `I2C_SMBUS_TIMEOUT`；大於 100 µs 但未達 timeout 的來源 timing 會產生 `I2C_LONG_CLOCK_STRETCH`。
- STM32 範例的 `HAL_I2C_*` timeout `100` 是 API 呼叫的 millisecond timeout placeholder，不是裝置 datasheet 的 SMBus tTIMEOUT，也不是測得的 bus duration。

## 6. 三個 C/C++ templates + 一個 CLI template

以下使用 `bus=2`、7-bit address `0x50`、16-bit register `0x1234`、Read length `4` 示範 canonical combined register read。產生器會依同一輸入替換 bytes、bus、width 與 read length。

### 6.1 Linux userspace `i2c-dev`（C）

```c
/* Fragment prerequisites: <fcntl.h>, <linux/i2c-dev.h>, <linux/i2c.h>,
 * <sys/ioctl.h>, <unistd.h>, <stdint.h>, and <stdio.h>. */
int fd = open("/dev/i2c-2", O_RDWR);
uint8_t reg_buf[2] = { 0x12, 0x34 }; /* 16-bit register, MSB first */
uint8_t rx_buf[4];
struct i2c_msg msgs[2] = {
    { .addr = 0x50, .flags = 0,        .len = sizeof(reg_buf), .buf = reg_buf },
    { .addr = 0x50, .flags = I2C_M_RD, .len = sizeof(rx_buf),  .buf = rx_buf  },
};
struct i2c_rdwr_ioctl_data transfer = { .msgs = msgs, .nmsgs = 2 };
if (ioctl(fd, I2C_RDWR, &transfer) < 0) {
    /* handle NACK, timeout, or transport error */
}
```

兩個 `i2c_msg` 讓 kernel 產生 write-pointer 後的 repeated START；不要把 register read 拆成兩個不相關的 `write()`/`read()`，除非 datasheet 明確允許中間 STOP。

### 6.2 STM32 HAL（C）

```c
uint8_t rx_buf[4];
HAL_StatusTypeDef status = HAL_I2C_Mem_Read(
    &hi2c1, (0x50 << 1), 0x1234, I2C_MEMADD_SIZE_16BIT,
    rx_buf, sizeof(rx_buf), 100 /* ms API timeout */);
if (status != HAL_OK) {
    /* inspect HAL error state before retrying */
}
```

HAL 的 address 參數通常是左移後的 8-bit wire form；Linux `i2c-dev` 與本頁 generator 的輸入欄位則以 7-bit address 為 canonical。兩者不可直接把 `0xA0` 當成 7-bit 欄位再左移一次。

若選 **16-bit little-endian register**，STM32 HAL 沒有對 `HAL_I2C_Mem_Read` 的 register byte order 做通用切換；產生器會改用 `HAL_I2C_Master_Seq_Transmit_IT` → `HAL_I2C_Master_Seq_Receive_IT` 的 file-scope static callback skeleton，以保留 repeated START。請把 callback 合併到既有 HAL callback dispatcher，並由 application 等待完成旗標與整體 timeout；這是可 review 的起始模板，不是可直接貼入任意 function 的完整 driver。

### 6.3 Arduino / ESP32 `Wire.h`（C++）

```cpp
uint8_t rx_buf[4];
Wire.beginTransmission(0x50);  // 7-bit address
Wire.write(0x12);               // register MSB
Wire.write(0x34);               // register LSB
uint8_t err = Wire.endTransmission(false);  // repeated START, no STOP
if (err != 0) {
    // handle address/data NACK
}

uint8_t received = Wire.requestFrom(0x50, 4);
if (received != 4) {
    // Handle a short read and verify this board's Wire buffer limit.
}
for (uint8_t i = 0; (i < received) && Wire.available(); ++i) {
    rx_buf[i] = Wire.read();
}
```

`false` 保留 bus 進入 repeated START；若裝置要求 direct read，省略 register bytes 並依 datasheet 選擇 `endTransmission()` 行為。
Write template 也要先核對目標板的 Wire TX buffer；若 payload 超過平台 buffer，必須依 datasheet/平台 API 分段，不能只因 GUI parser 接受就一次送出。

### 6.4 OpenBMC/Linux CLI（`i2c-tools`）

```bash
# Combined register read: w2 sends 0x12 0x34, then repeated START and r4
i2ctransfer 2 w2@0x50 0x12 0x34 r4
```

Direct read 是 `i2ctransfer 2 r4@0x50`；register write `0x1234` 加兩個 data bytes 則是：

```bash
i2ctransfer 2 w4@0x50 0x12 0x34 0xAB 0xCD
```

CLI template 不加 `-f` 強行繞過 kernel ownership；先確認 bus、MUX channel、7-bit address、register endian、payload 與 power/reset 狀態。

### 6.5 可下載 bundle

GUI 可下載 deterministic ZIP：`transfer_spec.json`、四平台 snippets、`SAFETY.txt` 與 `manifest.json`。manifest 提供 each file SHA-256 與 canonical spec SHA-256，方便 review/CI 比對；ZIP 本身也有 SHA-256。它仍是模板與規格，不是硬體執行結果。

## 7. 硬體安全與 review gate

生成程式碼不代表可以立即在板上執行。尤其寫入操作可能改變 PMBus 電源設定、GPIO 輸出、感測器設定（sensor configuration）或 EEPROM 內容。

執行前逐項確認：

1. bus number 與 schematic/`i2cdetect`/board profile 一致。
2. API 使用的 address 形式正確：7-bit `0x50`、wire write `0xA0`、wire read `0xA1` 不可混用。
3. register width、offset endian、payload byte order 與 datasheet 完全一致。
4. 先用 read-only 或 offline review 驗證，再決定是否送 write；避免在不明 power/reset 狀態下寫入。
5. 設定合理 timeout/retry，保存原始 command、driver log 與回傳錯誤；NACK/timeout 後不要無限重試或直接 recovery write。

這一頁產出的 ideal waveform、C 片段與 CLI 只回答「應該送什麼 transaction」；真實 ACK、資料、timing 與硬體安全結果必須回到第 1 頁的 capture、driver log、datasheet 與實際板卡驗證。
