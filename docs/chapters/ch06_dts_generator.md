# 第六章：Linux & OpenBMC Device Tree (.dts) 自動產生器

## 這個頁面在做什麼？

在 Linux Kernel 與 OpenBMC 開發中，你必須撰寫 Device Tree Source (.dts) 檔案來告訴 Kernel：
- 匯流排上掛了哪些晶片（EEPROM、溫度感測器、電源管理 IC）
- 每顆晶片的 I2C 位址是多少
- 使用哪個 Linux Driver 來驅動它（compatible 字串）

手寫 .dts 容易出錯（忘記 `#address-cells`、`compatible` 拼錯、`reg` 格式不對）。
這個工具產生 I2C MUX 拓撲的起始模板；實際產品仍必須依晶片 binding、SoC DTS 結構與目標 kernel 驗證，不能只因工具成功輸出就視為符合規格。

## 怎麼操作？

1. 進入 GUI 第 6 頁 **「🌲 Device Tree (.dts) 產生器」**。
2. 輸入 I2C Bus Number（如 `1` 代表 `&i2c1`）。
3. 輸入 PCA9548A MUX 位址（預設 `0x70`）。
4. 頁面即時顯示 MUX skeleton `.dtsi`；裝置節點必須來自實際 schematic、datasheet 與 board profile。
5. 點擊 **「下載 i2c_bus1.dtsi」** 按鈕存檔。

## 怎麼看懂輸出的 .dts 代碼？

```dts
&i2c1 {                          // 掛在 I2C Bus 1 上
    status = "okay";              // 啟用這條匯流排
    clock-frequency = <400000>;   // 400 kHz Fast-mode

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
| 設備沒有出現在 `/sys/bus/i2c/devices/` | 可能是節點未載入、`compatible`/`status`/driver/config 不符 | 先確認正在執行的 DTB，再用 `dtc -I fs /sys/firmware/devicetree/base` 或適用工具檢查 live tree |
| I2C 通訊失敗 | 位址、MUX channel、供電、reset、driver ownership 都可能造成 | 對照 schematic 與 `/sys/bus/i2c/devices`；掃描 bus 前先確認該 bus 可安全 probe |
| MUX 通道切換失敗 | compatible、channel node、父 bus、reset 或 idle policy 都可能造成 | 對照 MUX binding 與 driver log；`i2c-mux-idle-disconnect` 是 policy，不是所有失敗的通用修正 |

> [!CAUTION]
> `i2cdetect` 會主動對多個位址送出 probe，部分裝置可能把 probe 當成命令。公司板卡上執行前，先確認 bus、device datasheet、driver ownership 與團隊操作規範。
