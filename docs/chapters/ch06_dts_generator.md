# Linux／OpenBMC Device Tree Source（.dts）拓撲產生器

## 先看結論

第 6 頁把明確的 I2C MUX 拓撲轉成 `i2c_busN.dtsi` 起始模板：它整理 bus、MUX、channel、I2C address 與 `compatible` 的層級關係，但不會替產品猜測 binding 或硬體狀態。

這一頁的 GUI 輸入是數值／字串欄位加上 `devices` YAML list；不是上傳 `.dts` 後自動修正。產生檔要併入目標 board DTS，再用該版本 kernel 的 `dtc`、`dt-schema` 與實機證據驗證。

## 這個頁面回答什麼問題？

Linux Kernel／OpenBMC 需要 Device Tree Source（DTS）描述硬體拓撲，例如：

- 哪一條 I2C bus 連到 PCA9548A 類型的 MUX。
- MUX 的 7-bit address、每個 channel，以及 channel 下掛的裝置 address。
- Kernel 應以哪個 `compatible` 字串尋找 driver。

手寫節點時，`reg`、`#address-cells`、`#size-cells`、channel 層級或 `compatible` 拼字都可能出錯。本工具只負責產生可審查的拓撲骨架；真正的 binding 仍以目標 kernel 原始碼、datasheet 與 board schematic 為準。

## 輸入契約（Input Contract）

GUI 目前直接讀取文字框，不提供 DTS 檔案上傳控制項。按下 **「產生 Device Tree（.dts）」** 時，程式先以 YAML parser 讀取裝置清單，再呼叫 `DeviceTreeGenerator.generate_dts_from_topology()`。

| GUI 欄位 | 型別與範圍 | 會放進輸出的內容 |
|---|---|---|
| I2C 匯流排編號（`bus_num`／Bus Number） | 整數 `0..65535` | 父節點 `&i2cN`；例如 `1` 變成 `&i2c1` |
| PCA9548A MUX 位址（`mux_addr`／MUX Address） | 整數或 `0x` 字串；非保留 7-bit address `0x08..0x77` | 節點名稱 `i2c-mux@70` 與 `reg = <0x70>;` |
| 時鐘頻率（`clock_frequency`／`clock-frequency`） | 整數 `1..0xFFFFFFFF`，單位 Hz | 父 bus 的 `clock-frequency = <...>;` |
| 多工器相容字串（`mux_compatible`／MUX `compatible`） | 明確的 `vendor,device` 字串；預設 `nxp,pca9548` | MUX 的 `compatible` property；必須對照 kernel binding |
| 裝置清單（`devices`） | YAML list；每項是 mapping | 依 `channel` 分組，產生 child node、`reg` 與裝置 `compatible` |

每一項 `devices` mapping 建議明確提供以下四個欄位。`addr` 與 `compatible` 是必要的硬體語意；API 對省略的 `channel` 會採 `0`、省略的 `name` 會採 `device`，但 GUI 預填欄位與可讀性都要求不要依賴這些預設值。

| YAML 欄位 | 型別與範圍 | 白話說明 |
|---|---|---|
| `addr` | 整數或 `0x` 字串，`0x08..0x77` | 裝置的 7-bit I2C address；保留位址會被拒絕 |
| `channel` | 整數或數字字串，`0..7` | PCA9548A channel index；同一 channel 不可重複相同 address |
| `name` | 以英文字母開頭的 Device Tree node name | 只接受 Device Tree node name 字元，不能含空白 |
| `compatible` | `vendor,device` | 要使用目標 kernel binding 的實際字串，不要自行杜撰 |

### 可直接貼上的 YAML 範例

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

`yaml.safe_load()` 讀到的頂層必須是 list。空白輸入或 YAML `null` 會轉成空 list，產生只有 bus、MUX 與八個 channel 的骨架，不會憑空增加 EEPROM、sensor 或 PMBus device。

### 範例檔案（Example files）

- `tests/test_dts_gen.py`：可執行的 `DeviceTreeGenerator` topology fixture；其中的 `devices` 內容與上方 YAML 對應，可用來核對 API 產生結果。
- `examples/data/board_yv4.yaml`：Board Profile 拓撲參考，含 bus、MUX channel 與 address 命名。它不是第 6 頁的 `devices` schema，請先依上表轉成 YAML list 再貼入 GUI。

第 6 頁目前沒有 `load_*_sample()` 內建 DTS resource；因此文件中的 YAML block 是可直接貼入的 GUI example，`tests/test_dts_gen.py` 則是 repository 內可重跑的契約 example file。兩者都不能取代 schematic 或 datasheet。

## 怎麼操作？

1. 在專案根目錄執行 `uv run fw-diag gui`，進入 GUI 第 6 頁 **「🌲 Device Tree（.dts）產生器」**。
2. 先填 I2C 匯流排編號、MUX address、`clock-frequency` 與 MUX `compatible`。數值可用十進位或 `0x` 字串，例如 `1`、`0x70`、`400000`。
3. 把實際拓撲整理成上方的 YAML list，確認每個 `addr`、`channel`、`name`、`compatible` 都來自 schematic、MUX datasheet 與目標 kernel binding。
4. 按 **「產生 Device Tree（.dts）」**。遇到 YAML 型別、保留 address、channel 超出 `0..7`、同 channel address 重複或 `compatible` 不符合 `vendor,device` 時，頁面會顯示中文化錯誤並拒絕輸出。
5. 檢視程式碼後按 **「下載 i2c_bus.dtsi」**；實際檔名會依 bus 變成 `i2c_bus1.dtsi` 之類。

CLI 另提供不帶裝置清單的快速骨架：

```bash
uv run fw-diag gen dts --bus 1 --mux 0x70 --out i2c_bus1.dtsi
```

CLI `gen dts` 目前只有 `--bus`、`--mux` 與輸出路徑選項，不會讀取 `devices` YAML；需要明確加入 child device 時請使用 GUI/API，或在產生後依專案流程編輯並審查。

## 怎麼讀懂輸出的 DTS？

以下是輸出的代表性片段；`/* 其餘 channel */` 只是文件省略標記，不是 generator 寫入的語法。

```dts
&i2c1 {
    status = "okay";
    clock-frequency = <400000>;

    i2c-mux@70 {
        compatible = "nxp,pca9548";
        reg = <0x70>;
        #address-cells = <1>;
        #size-cells = <0>;
        i2c-mux-idle-disconnect;

        i2c@0 {
            #address-cells = <1>;
            #size-cells = <0>;
            reg = <0>;

            eeprom@50 {
                compatible = "atmel,24c64";
                reg = <0x50>;
            };
        };

        /* 其餘 i2c@1..i2c@7 channel 會照樣產生 */
    };
};
```

| DTS token | 中文意義 | 閱讀重點 |
|---|---|---|
| `&i2c1` | 父 I2C controller node | `1` 必須對應 SoC DTS 真實存在且可用的 controller |
| `clock-frequency` | bus clock 設定 | 是輸出設定值，不是工具量到的實際 SCL 頻率 |
| `i2c-mux@70`、`reg` | MUX node 與 7-bit address | address 需和 wiring、strap 與 datasheet 一致 |
| `#address-cells`／`#size-cells` | 子節點 address／size 的 cell 數 | generator 對 I2C node 使用 `1`／`0`；仍須服從父 binding |
| `i2c@0`、`reg = <0>` | MUX channel node 與 channel index | channel `0..7` 是 MUX 通道，不是裝置 I2C address |
| `eeprom@50`、`compatible` | 裝置 node 名稱與 driver matching token | `atmel,24c64` 等字串必須由 kernel binding 證實 |
| `i2c-mux-idle-disconnect` | MUX idle policy | 這是產物內建的 policy；若產品不適用，需依 binding 與 driver policy 審查 |

本工具只輸出 bus clock、MUX、channel、`reg` 與 `compatible` 等通用欄位。它不會猜測 EEPROM `pagesize`、電源供應、GPIO reset、interrupt、`status` 或其他 board-specific binding property；需要時請在產品 DTS 中補上並驗證。

## 證據等級與驗證順序

- **Source-provided**：`addr`、`channel`、`compatible` 與 bus 設定來自使用者貼上的 YAML／欄位；工具不會確認它們真的存在於板上。
- **Reconstructed**：產生的 `.dtsi` 是依輸入重建的語法與拓撲模板，不是 kernel probe 或實體 bus 量測結果。
- **Unavailable**：沒有 schematic、binding、目標 DTB、driver log 或 live tree 時，無法由本頁判斷 wiring、電源、reset、driver probe 或唯一 root cause。

建議依序驗證：

1. 將輸入 YAML、產生檔、工具版本與 SHA-256 一起保存，方便 review 與重現。
2. 人工比對 SoC controller、MUX address、channel、每個 child address、compatible 與 board revision。
3. 把 `.dtsi` include 到目標 board DTS；使用該 kernel 的 include path 執行 `dtc`，確認語法與 phandle 結構。
4. 若專案使用 Devicetree schema，執行其 `dt_binding_check`／`dtbs_check`；`dtc` 通過不等於 binding 通過。
5. 開機後再檢查實際 DTB／`/sys/firmware/devicetree/base`、driver probe log 與 `/sys/bus/i2c/devices/`，把 runtime 結果與模板分開記錄。

## 常見問題

| 症狀 | 常見原因 | 下一個檢查點 |
|---|---|---|
| `devices` 被拒絕 | 頂層不是 YAML list、某項不是 mapping，或缺少 `addr`／`compatible` | 先用最小 YAML 範例逐項加入欄位，再對照錯誤中的 `devices[index]` |
| `addr` 錯誤 | 使用保留 address、超出 `0x08..0x77`，或把 8-bit wire byte 當成 7-bit address | 回到 datasheet 與 schematic，確認顯示值是 7-bit address |
| `channel` 錯誤或重複 | channel 不在 `0..7`，或同一 channel 的 address 重複 | 確認 MUX 型號、channel index 與每條下游 bus 的裝置清單 |
| 產生成功但 driver 不 probe | `compatible`、父 controller、binding property、電源、reset 或 kernel config 不符 | 先看目標 DTB 與 driver log，再做 `dtbs_check`；不要把生成成功當成硬體通訊成功 |
| `/sys/bus/i2c/devices/` 沒有預期節點 | DTB 未載入、MUX policy／driver 不符，或裝置未供電 | 交叉檢查 live tree、probe log、電源與 reset 狀態 |

> **硬體安全提醒**
>
> `i2cdetect` 會主動對多個 address 送出 probe，部分 EEPROM、PMBus 或 sensor 可能把 probe 當成命令。公司板卡上執行前，先核對 bus、7-bit address、driver ownership、裝置 datasheet 與團隊操作規範；本工具不會替你執行任何 I2C 寫入。

進一步的共通限制與證據詞彙，請參閱[能力、證據層級與限制](../LIMITATIONS.md)。
