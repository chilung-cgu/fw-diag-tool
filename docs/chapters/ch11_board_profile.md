# Board Profile 板級 I2C 拓撲定義與視覺化編輯

## 先看結論

第 11 頁 **「📋 Board Profile 視覺化編輯器」** 負責建立、驗證與管理硬體板級的 I2C / PMBus 匯流排拓撲宣告。透過結構化的 YAML / JSON 定義，工具能精確掌握哪條匯流排（Bus）掛載了哪些晶片、是否存在 I2C MUX 多工器（如 PCA9548A）及其子通道（Channels）分佈。

將 Board Profile 載入至 **第 1 頁（I2C/PMBus 診斷）** 後，診斷引擎會以板級拓撲取代啟發式猜測（Heuristic Guessing），將 7-bit 位址直接對齊至特定元件名稱、暫存器定義與 PMBus 命令集，大幅提升晶片識別準確度與報告品質。

---

## 什麼是 Board Profile？為何需要定義板級拓撲？

在伺服器主機板（如 OpenBMC Yosemite V4）與複雜嵌入式系統中，單一 SoC 或 BMC 通常管理數十條 I2C / SMBus 匯流排，每條匯流排上可能掛載數十顆周邊晶片，甚至透過 I2C MUX 擴充出多個獨立通道。

### 傳統除錯的痛點
1. **位址重疊與歧義**：多顆相同型號的感測器（如 TMP75 溫度晶片）可能設定為相同 7-bit 位址（例如 `0x48`），分別掛在 MUX 的 Channel 0（進風口 Inlet）與 Channel 1（出風口 Outlet）。純邏輯分析儀 capture 若缺乏拓撲資訊，無法判斷該筆交易存取的是哪一顆實體晶片。
2. **暫存器意義不明**：通用解碼器只能辨識十六進位 Offset（如 `0x88`），無法自動對照該晶片是標準 PMBus 電源控制器的 `READ_VIN` 還是特定 GPIO 擴充晶片的暫存器。
3. **缺乏位址衝突驗證**：在硬體設計或 Device Tree 撰寫階段，若不慎將相同位址指派給同一匯流排上的兩顆晶片，會造成匯流排爭用與 ACK 衝突。

### Board Profile 的核心價值
- **精準映射**：明確定義 `Bus ID -> MUX -> Channel -> Device Address -> Registers / Commands` 的完整階層。
- **提升診斷深度**：診斷引擎自動比對捕捉到的位址與資料，直接輸出具備物理語意的元件名稱（如 `inlet-temp-sensor`）與暫存器名稱。
- **設計階段防錯**：提供即時靜態語意檢查，自動攔截位址重複、I2C 保留位址誤用以及匯流排速度不相容等問題。

---

## 支援格式：YAML 與 JSON

Board Profile 支援 **YAML** 與 **JSON** 雙格式解析與匯出。底層由 Pydantic 嚴格驗證 Schema，確保所有欄位格式與數值範圍符合標準。

### 核心 Schema 結構說明

| 欄位名稱 | 型別 | 必填 | 說明與限制 |
|---|---|---|---|
| `board_name` | 字串 | 是 | 板卡識別名稱（例如 `OpenBMC-Server-YV4`） |
| `version` | 字串 | 是 | 拓撲版本編號（例如 `"1.0"`） |
| `i2c_buses` | 列表 | 是 | I2C 匯流排清單（至少包含 1 組 Bus） |
| `bus_num` | 整數 | 是 | 實體匯流排編號（`0..65535`），同一 Profile 內不可重複 |
| `speed_mode` | 字串 | 是 | 匯流排速率：`standard` (100 kHz)、`fast` (400 kHz)、`fast_plus` (1000 kHz)、`high_speed` (3400 kHz)、`ultra_fast` (5000 kHz) |
| `devices` | 列表 | 否 | 直連於該 Bus 的從屬裝置清單 |
| `muxes` | 列表 | 否 | 掛載於該 Bus 的 I2C MUX 清單 |
| `address_7bit` | 整數 / 16進位 | 是 | 7-bit 裝置位址，有效範圍為非保留位址 `0x08..0x77` |
| `compatible` | 字串 | 是 | 符合 Linux Device Tree 規範的 `"vendor,device"` 字串（如 `ti,tmp75`） |
| `register_width` | 整數 | 是 | 暫存器位址寬度，限 `8` 或 `16` bit |
| `registers` | 列表 | 否 | 暫存器清單（包含 `name`, `offset`, `access` [RO/RW/WO/W1C], `description`） |
| `commands` | 列表 | 否 | PMBus/SMBus 命令清單（包含 `name`, `code`, `description`） |
| `channels` | 列表 | 是 (MUX) | MUX 下游通道清單（通道編號 `0..7`，各通道可掛載獨立 `devices`） |

---

## 完整範例解析：OpenBMC Yosemite V4 參考拓撲

專案內建範例檔 `examples/data/board_yv4.yaml` 展示了典型的伺服器主機板配置：

```yaml
board_name: OpenBMC-Server-YV4
version: "1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: fast-mode-plus
    devices:
      - address_7bit: 0x20
        name: board-gpio-expander
        category: GPIO Expander
        protocol: I2C
        compatible: nxp,pca9555
        register_width: 8
        registers:
          - name: input_port_0
            offset: 0x00
            access: RO
          - name: output_port_0
            offset: 0x02
            access: RW
          - name: config_port_0
            offset: 0x06
            access: RW
      - address_7bit: 0x50
        name: baseboard-fru-eeprom
        category: EEPROM
        protocol: EEPROM
        compatible: atmel,24c64
        register_width: 16
        registers:
          - name: fru_header
            offset: 0x0000
            access: RO
    muxes:
      - address_7bit: 0x70
        name: main-i2c-mux
        category: I2C Multiplexer
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        channels:
          - channel: 0
            devices:
              - address_7bit: 0x48
                name: inlet-temp-sensor
                category: Temperature Sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
          - channel: 1
            devices:
              - address_7bit: 0x48
                name: outlet-temp-sensor
                category: Temperature Sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
          - channel: 2
            devices:
              - address_7bit: 0x58
                name: core-voltage-regulator
                category: PMBus Power Controller
                protocol: PMBus
                compatible: infineon,xdpe12284
                register_width: 8
                commands:
                  - name: READ_VIN
                    code: 0x88
                  - name: READ_VOUT
                    code: 0x8B
                  - name: READ_IOUT
                    code: 0x8C
                  - name: READ_TEMPERATURE_1
                    code: 0x8D
          - channel: 3
            devices:
              - address_7bit: 0x40
                name: main-power-monitor
                category: Power Monitor
                protocol: I2C
                compatible: ti,ina226
                register_width: 8
                registers:
                  - name: bus_voltage
                    offset: 0x02
                    access: RO
                  - name: shunt_voltage
                    offset: 0x01
                    access: RO
```

### 拓撲重點剖析：
1. **直連裝置（Direct Devices）**：Bus 1 直連 `0x20`（PCA9555 GPIO 擴充）與 `0x50`（24C64 FRU EEPROM）。
2. **MUX 擴充（PCA9548A @ 0x70）**：
   - **Channel 0**：掛載 `0x48`（TMP75 進風口感測器）。
   - **Channel 1**：掛載 `0x48`（TMP75 出風口感測器）。**兩顆感測器位址相同，但因位於不同 MUX 通道，硬體上彼此隔離、不發生衝突**。
   - **Channel 2**：掛載 `0x58`（XDPE12284 PMBus VR 電源控制器），定義了標準 PMBus 讀取指令。
   - **Channel 3**：掛載 `0x40`（INA226 電源監控晶片）。

---

## Step-by-Step 教學：建立與整合 Board Profile

### Step 1: 從硬體原理圖（Schematic）識別匯流排與元件
在建立設定檔前，需先查閱硬體設計圖或 BOM 表，確認以下四項關鍵資訊：
1. **I2C Bus 編號**（如 SoC I2C-1、I2C-2）。
2. **各匯流排設計時鐘頻率**（100 kHz Standard、400 kHz Fast 或 1000 kHz Fast-mode Plus）。
3. **直連晶片與 MUX 之 7-bit 從屬位址**（注意腳位 A0/A1/A2 之上拉或下拉接地狀態）。
4. **MUX 下游各通道（Channel 0~7）連接的週邊元件與型號**。

### Step 2: 使用 GUI 視覺化編輯器建立拓撲
1. 啟動 GUI 並切換至側邊欄 **「產生器與硬體工具」** -> **「📋 Board Profile 視覺化編輯器」**。
2. **設定板卡基本資訊**：輸入板卡名稱（如 `YV4-CraterLake`）與版本號（如 `1.0`）。
3. **配置 I2C Bus**：點擊「➕ 新增 I2C Bus」，設定 Bus 編號與時鐘速率。
4. **加入直連裝置**：
   - 從「晶片型號快捷預設」選單選取常見元件（如 `PCA9555` 或 `24C64`），系統將自動填入建議的類別、相容字串與暫存器寬度。
   - 填寫 7-bit 位址（支援十六進位格式如 `0x20`）與元件自訂名稱。
5. **配置 I2C MUX 與通道**：
   - 點擊「➕ 新增 I2C MUX」，設定 MUX 位址（如 `0x70`）與通道數（1~8 通道）。
   - 在對應通道（如 Channel 0、Channel 1）下分別新增掛載的從屬元件。

### Step 3: 即時驗證與 YAML 匯出 / 匯入
- **即時驗證機制**：編輯器右側會即時檢查拓撲結構。若無任何錯誤，狀態面板會顯示綠色 `✅ 拓撲結構驗證通過，無語法或位址衝突錯誤`。
- **YAML 匯出**：點擊 **「💾 下載 board_profile.yaml」** 按鈕儲存設定檔。
- **既有 YAML 匯入**：在「📥 既有 YAML 匯入」區塊上傳或貼上既有 YAML 內容，點擊「執行匯入並套用至表單」，即可反向解析並還原至視覺化介面供後續修改。

### Step 4: 整合至 I2C 診斷分析（提升識別準確度）
1. 切換至側邊欄 **「📊 I2C / PMBus 診斷與波形檢視」** 頁面。
2. 在「資料輸入」區域展開 **「📋 板級拓撲（Board Profile YAML，可選）」**。
3. 貼上剛才產生的 Board Profile YAML 內容（或載入已存檔案）。
4. 上傳邏輯分析儀 capture 並點擊 **「🚀 開始診斷分析」**。
5. **成果對比**：
   - **未套用 Profile**：交易列表顯示 `Candidate: LM75 / TMP75 / TMP102 (Heuristic)`，暫存器顯示原始 Offset `0x00`。
   - **套用 Profile 後**：交易列表精確識別為 `inlet-temp-sensor`（相容性 `ti,tmp75`），暫存器明確標註為 `temperature (RO)`。

---

## 位址衝突與相容性自動偵測

Board Profile 編輯器內建三道防護檢查：

### 1. 同一匯流排 / 通道位址衝突偵測
若在同一個 Bus 或同一 MUX 通道下設定了兩顆相同 7-bit 位址的裝置，編輯器會立即阻斷下載並顯示紅色錯誤：
```text
❌ 發現 1 項錯誤需修正：
Bus #1：位址衝突！「outlet-temp」與「inlet-temp」皆使用相同 7-bit 位址 0x48。
```
*(註：若兩顆 `0x48` 分別位於 MUX 的 Channel 0 與 Channel 1，則屬合法配置，編輯器會判定為通過。)*

### 2. I2C 保留位址警告
若不慎將裝置位址設定在 NXP I2C 規範（UM10204）之保留區間（`0x00..0x07` 或 `0x78..0x7F`），編輯器會主動警示：
```text
❌ Bus #1 -> 直連裝置「test-dev」：位址 0x00 屬於 I2C 保留位址範圍（General Call / START byte）。標準從裝置位址範圍為 0x08~0x77。
```

### 3. 時鐘速度相容性警示
若 Bus 設定為高頻模式（如 `fast_plus` 1000 kHz），但掛載的晶片典型最高工作頻率僅支援 400 kHz（如部分 EEPROM 或標準感測器），編輯器會輸出黃色警告：
```text
⚠️ 時鐘速度相容性警示：Bus 設定速度為 1000 kHz，但晶片「LM75 / TMP75」典型最高速度為 400 kHz，高頻下可能通訊失真或無回應。
```

---

## I2C MUX 多工器多通道支援

當系統需要掛載多個相同 I2C 位址的晶片時，硬體工程師會引入 I2C Switch / Multiplexer（如 NXP PCA9548A 8-channel、PCA9546 4-channel 或 TI TCA9548A）。

### 工作原理與拓撲映射
```text
                    +------------------+
                    |   I2C Bus 1      |
                    +--------+---------+
                             |
                    +--------v---------+
                    | PCA9548A @ 0x70  |
                    +---+----+----+----+
                        |    |    |    |
             Channel 0 -+    |    |    +- Channel 3
             [0x48 Temp]     |    |       [0x40 Power]
                             |    +- Channel 2
              Channel 1 -----+       [0x58 PMBus VR]
              [0x48 Temp]
```

在診斷分析時，若邏輯分析儀 capture 記錄了對 MUX `0x70` 寫入控制暫存器啟用特定通道（例如寫入 `0x01` 開啟 Channel 0，寫入 `0x02` 開啟 Channel 1）的交易，診斷引擎的 `MuxTracker` 會動態追蹤當前啟用的通道，並精準將後續 `0x48` 的讀寫操作映射至正確的感測器元件。

`downstream_bus_num` 是 MUX channel 對應到 Linux runtime I2C adapter 的明確編號。DTS 產生只需要 parent bus、MUX address 與 channel，因此可以省略；Entity-Manager 的 `Bus` 欄位則必須填入實際 adapter number。工具不會猜測此值：只要 populated channel 缺少 `downstream_bus_num`，`fw-diag em generate --format json` 就會停止並指出 MUX 與 channel。請在目標板上依 `/sys/bus/i2c/devices` 或 `i2cdetect -l` 的實際結果填入，不能直接複製另一塊板的編號。

---

## 限制與能力邊界（Limitations & Boundaries）

在使用 Board Profile 時，請務必釐清以下認知邊界：

1. **靜態宣告不等於實體量測（Static Declaration != Live Probe）**：
   - Board Profile 是工程師手動定義或從原理圖匯出的「預期拓撲（Expected Topology）」，**不是實體硬體掃描的 probe 結果**。
   - Profile 中宣告了元件，不代表實體板卡上該元件已正確上電、焊接良好或韌體驅動 probe 成功。
2. **歧義位址防護（Ambiguity Safeguard）**：
   - 若 Capture 記錄中缺乏 MUX 切換指令，導致診斷引擎無法判定當前作用中的 MUX 通道，且多個通道存在相同位址（如兩個 `0x48`），引擎會標記為 `Ambiguous Board Profile (0x48)` 並保留原始 Hex，避免輸出錯誤的物理語意。
3. **相容字串（Compatible）用途**：
   - 相容字串供系統對齊 Linux Device Tree 驅動命名規範，不代表目標 Linux Kernel 核心必然已編譯並載入該驅動模組。
4. **排查流程建議**：
   - 遇到 I2C NACK 或無回應時，應優先配合示波器確認硬體供電、上拉電阻（Pull-up Resistors）與 SCL/SDA 波形品質，再核對 Board Profile 定義是否與實體電路圖一致。
