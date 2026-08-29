# Linux／OpenBMC Device Tree（.dts）自動產生器

## 這個頁面在做什麼？

在 Linux Kernel 與 OpenBMC 開發中，你必須撰寫 Device Tree Source (.dts) 檔案來告訴 Kernel：

- 匯流排上掛了哪些晶片（EEPROM、溫度感測器、電源管理 IC）
- 每顆晶片的 I2C 位址是多少
- 使用哪個 Linux Driver 來驅動它（compatible 字串）

手寫 .dts 容易出錯（忘記 `#address-cells`、`compatible` 拼錯、`reg` 格式不對）。
這個工具產生 I2C MUX 拓撲的起始模板；實際產品仍必須依晶片 binding、SoC DTS 結構與目標 kernel 驗證，不能只因工具成功輸出就視為符合規格。

## 怎麼操作？

1. 進入 GUI 第 6 頁 **「🌲 Device Tree（.dts）產生器」**。
2. 輸入 I2C Bus Number（如 `1` 代表 `&i2c1`）、MUX address、MUX `compatible` 與 `clock-frequency`。
3. 在 YAML 裝置清單中，為每一顆實際存在的裝置填入 `addr`、`channel`、`name`、`compatible`。
4. 按 **「產生 Device Tree（.dts）」**；輸入不完整、位址保留、同一 channel 位址重複或 compatible 不是
   `vendor,device` 格式時，頁面會拒絕生成並顯示錯誤。
5. 下載產生的 `i2c_busN.dtsi`。工具輸出的是拓撲模板，不是已經通過目標 kernel binding 的完整 board DTS。

GUI 使用的最小 YAML 範例：

```yaml
- addr: 0x50
  channel: 0
  name: eeprom
  compatible: atmel,24c64
- addr: 0x48
  channel: 1
  name: temp-sensor
  compatible: national,lm75
```

`addr` 與 `channel` 必須和 schematic、MUX datasheet 及實際 wiring 一致；
`compatible` 必須查目標 kernel 的 binding 或 driver，而不是只填一個看起來合理的名稱。

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
            reg = <0>;                // channel index
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

本工具目前只輸出通用的 `reg`、`compatible`、MUX channel 與 bus clock；它不會替裝置猜測
`pagesize`、電源供應、GPIO reset、interrupt 或 board-specific binding property。若 datasheet 或
binding 要求這些欄位，請在生成後依產品 DTS 慣例補上並用 `dtc`/`dt-schema` 驗證。

## 生成後的驗證順序

1. 先人工比對 bus、MUX address、channel 與每個 device address。
2. 在目標 kernel source tree 以適用的 include path 執行 `dtc`；只通過語法不代表 binding 正確。
3. 若專案使用 Devicetree schema，執行該專案規定的 `dt_binding_check` / `dtbs_check`。
4. 將產生檔整合到 board DTS 後，再檢查 live tree、driver probe log 與 `/sys/bus/i2c/devices/`。

## 常見問題

| 問題 | 原因 | 解法 |
|---|---|---|
| 設備沒有出現在 `/sys/bus/i2c/devices/` | 可能是節點未載入、`compatible`/`status`/driver/config 不符 | 先確認正在執行的 DTB，再用 `dtc -I fs /sys/firmware/devicetree/base` 或適用工具檢查 live tree |
| I2C 通訊失敗 | 位址、MUX channel、供電、reset、driver ownership 都可能造成 | 對照 schematic 與 `/sys/bus/i2c/devices`；掃描 bus 前先確認該 bus 可安全 probe |
| MUX 通道切換失敗 | compatible、channel node、父 bus、reset 或 idle policy 都可能造成 | 對照 MUX binding 與 driver log；`i2c-mux-idle-disconnect` 是 policy，不是所有失敗的通用修正 |

> **注意：**
>
> `i2cdetect` 會主動對多個位址送出 probe，部分裝置可能把 probe 當成命令。公司板卡上執行前，先確認 bus、device datasheet、driver ownership 與團隊操作規範。
