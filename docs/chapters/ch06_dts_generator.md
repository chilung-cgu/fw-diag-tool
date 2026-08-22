# 第六章：Linux & OpenBMC Device Tree (.dts) 自動產生器

## 這個頁面在做什麼？

在 Linux Kernel 與 OpenBMC 開發中，你必須撰寫 Device Tree Source (.dts) 檔案來告訴 Kernel：
- 匯流排上掛了哪些晶片（EEPROM、溫度感測器、電源管理 IC）
- 每顆晶片的 I2C 位址是多少
- 使用哪個 Linux Driver 來驅動它（compatible 字串）

手寫 .dts 非常容易出錯（忘記 #address-cells、compatible 拼錯、reg 格式不對），
這個工具自動根據 I2C MUX 拓撲產出符合 Devicetree Specification v0.4 標準的代碼。

## 怎麼操作？

1. 進入 GUI 第 6 頁 **「🌲 Device Tree (.dts) 產生器」**。
2. 輸入 I2C Bus Number（如 `1` 代表 `&i2c1`）。
3. 輸入 PCA9548A MUX 位址（預設 `0x70`）。
4. 頁面即時顯示完整的 `.dtsi` 代碼。
5. 點擊 **「下載 i2c_bus1.dtsi」** 按鈕存檔。

## 怎麼看懂輸出的 .dts 代碼？

```dts
&i2c1 {                          // 掛在 I2C Bus 1 上
    status = "okay";              // 啟用這條匯流排
    bus-frequency = <400000>;     // 400 kHz Fast-mode

    i2c-mux@70 {                  // PCA9548A MUX 在位址 0x70
        compatible = "nxp,pca9548";  // 使用 Linux 內建 pca9548 driver
        reg = <0x70>;                 // I2C 位址 0x70
        #address-cells = <1>;         // 子節點用 1 個 cell 表示位址
        #size-cells = <0>;            // 子節點不需要 size

        i2c@0 {                       // MUX Channel 0
            eeprom@50 {               // EEPROM 在位址 0x50
                compatible = "atmel,24c64";  // 使用 Linux at24 driver
                reg = <0x50>;                // I2C 位址 0x50
                pagesize = <32>;             // Page Size 32 bytes
            };
        };
    };
};
```

### 關鍵欄位解釋

| 欄位 | 意義 | 為什麼重要？ |
|---|---|---|
| `compatible` | 告訴 Linux Kernel 用哪個 driver | 如果拼錯，driver 不會載入，設備不會出現 |
| `reg` | 設備的 I2C 位址 | 如果寫錯，Kernel 會去錯誤的位址通訊 |
| `#address-cells` | 位址用幾個 32-bit cell 表示 | I2C 固定為 1，SPI 為 1，Memory Mapped 為 1~2 |
| `#size-cells` | 大小用幾個 cell 表示 | I2C 固定為 0（不需要 size） |
| `pagesize` | EEPROM 的 Page Write 大小 | 影響 Linux at24 driver 的寫入策略 |

## 常見問題

| 問題 | 原因 | 解法 |
|---|---|---|
| 設備沒有出現在 `/sys/bus/i2c/devices/` | compatible 拼錯或 driver 未編譯 | 用 `grep compatible /lib/firmware/*.dtb` 確認 |
| I2C 通訊失敗 | reg 位址與硬體不一致 | 用 `i2cdetect -y 1` 掃描實際位址 |
| MUX 通道切換失敗 | i2c-mux-idle-disconnect 屬性遺漏 | 加上此屬性讓 MUX 在 idle 時斷開所有通道 |