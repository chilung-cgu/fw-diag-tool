# Entity-Manager 組態視覺化產生器與校驗 (OpenBMC EM Builder & Validator)

## 什麼是 OpenBMC Entity-Manager

在現代伺服器基板管理控制器 (OpenBMC) 架構中，**Entity-Manager (EM)** 是負責硬體拓撲動態偵測與系統抽象的核心 Daemon：

- **動態硬體偵測**：Entity-Manager 在開機與執行期間，透過 `FruDevice` 掃描各 I2C 匯流排上的 FRU EEPROM 內容（如 Board Product Name、Chassis Type）。
- **組態綁定與 D-Bus 抽象**：當 FRU 資訊與預先定義的 JSON 設定檔（Probe 運算式）匹配成功時，Entity-Manager 會在 D-Bus 上發布該板卡掛載的所有硬體感測器與裝置定義。
- **驅動 `dbus-sensors` Daemon 家族**：`psusensor`、`hwmontempsensor`、`adcsensor`、`fansensor` 等專屬感測器程序會監聽 Entity-Manager 的 D-Bus 介面，自動載入 Linux Kernel 驅動、建立 hwmon sysfs 節點並定期讀取數值。

簡言之，Entity-Manager JSON 是 OpenBMC 連接底層實體硬體與上層 IPMI/Redfish 監控的組態中樞。

---

## 手寫 EM JSON 的痛點

在日常開發與 BSP 移植中，工程師手動撰寫 Entity-Manager JSON 設定檔常面臨許多容易出錯的環節：

1. **I2C Bus 與 Address 重複衝突**：同一匯流排上意外配置了重複的 7-bit 位址，導致感測器互相覆蓋或 probe 失敗。
2. **PowerState 設定遺漏或誤用**：未區分待命電源（`Always`）與開機主電源（`On`），導致 Host 未上電時 Daemon 瘋狂報錯 `-ENXIO` 或發出虛假故障警報。
3. **門檻值 (Thresholds) 方向與階層錯誤**：例如將 Upper Critical 的數值設定得比 Upper Non-Critical 還低，或是 Direction 設定相反，引發風扇狂轉或監控邏輯異常。
4. **必填欄位缺失與大小寫錯誤**：如遺漏 `Name`、`Type` 或 `Address` 拼字錯誤，在 Entity-Manager 解析時直接被默默忽略（Silent Failure）。

本工具提供 **視覺化產生器 (Build Mode)** 與 **結構/拓撲校驗器 (Validate Mode)**，幫助工程師在部署前即時消除所有潛在組態缺陷。

---

## 視覺化建置模式 (Build Mode) 教學

進入 Web 介面側邊欄 **「系統日誌」** 區塊的 **「⚙️ Entity-Manager 組態產生器 (EM Builder)」** 頁面。

### 步驟 1：基本設定

1. 切換至 **「🔨 組態建置 (Build Mode)」** 標籤頁。
2. 輸入板卡名稱 (**Board Name**，例如 `Baseboard_Yosemite4`)。
3. 設定 Probe 運算式 (**Probe String**，預設為 `TRUE`，或指定 FRU 匹配條件如 `xyz.openbmc_project.FruDevice({'BOARD_PRODUCT_NAME': 'YV4'})`)。

### 步驟 2：從 7 大類別選擇裝置範本

系統內建 7 大類別、13+ 種伺服器主流晶片範本：

1. 選擇分類（如 **Temperature**、**ADC**、**FRU / EEPROM**、**Fan Controller**、**PSU**、**GPIO**、**Hot-swap**）。
2. 選擇晶片型號（如 `TMP75`、`MAX31790`、`AT24C64`、`ADM1272`）。
3. 填入實體硬體參數：
   - **裝置名稱 (Name)**：例如 `TEMP_INLET` 或 `FAN0_TACH`。
   - **I2C Bus 編號**：例如 `1`。
   - **I2C 7-bit 位址**：支援 Hex（如 `0x48`）或十進位（如 `72`）。
   - **電源狀態 (PowerState)**：可選 `On`、`Always`、`Standby` 等。
4. 點擊 **「➕ 加入裝置」** 按鈕將裝置收錄至板卡配置清單。

### 步驟 3：產生標準 JSON 與下載

1. 下方清單即時顯示目前已加入之所有裝置矩陣（包含 Bus、Address、Type、PowerState）。
2. 點擊 **「⚡ 產生 Entity-Manager JSON」** 按鈕。
3. 系統自動生成符合 OpenBMC 官方規範的 JSON 結構，並提供 **一鍵複製** 與 **下載 JSON 檔案** 功能。

---

## 語法與拓撲校驗模式 (Validate Mode) 教學

當你已有現成的 Entity-Manager JSON 檔案，或剛從 upstream repo 下載組態時，可使用校驗模式進行靜態全面檢查。

### 步驟 1：上傳或貼上 JSON 組態

1. 切換至 **「🔍 組態校驗 (Validate Mode)」** 標籤頁。
2. 上傳 `.json` 檔案，或直接貼入 JSON 文字內容。
3. 可點擊「載入位址衝突範例 JSON」快速體驗校驗回饋。

### 步驟 2：板級拓撲 (Board Profile) 交叉比對（選填）

- 可在側邊欄載入硬體設計拓撲檔案（`board_profile.yaml`）。
- 校驗器會比對實體板卡定義與 JSON 設定：
  - 檢查 EM JSON 中的裝置是否真實存在於 Board Profile。
  - 比對晶片型號相容性與位址宣告一致性。

### 步驟 3：檢視校驗結果與錯誤排查建議

點擊 **「🔍 執行全面校驗」** 後，系統會輸出結構化結果：

- **校驗指標摘要**：已檢查裝置數、Critical 嚴重錯誤數、Warning 警告數、Info 提示數。
- **問題清單卡片**：針對每一項違規項目，列出：
  - **位置 (Field Path)**：明確指出出錯的 JSON 路徑（例如 `Exposes[1].Address`）。
  - **問題說明 (Message)**：如「I2C Bus 1 上位址 0x48 發生重複衝突」。
  - **修復建議 (Suggestion)**：具體指引如何調整位址或修改閾值設定。

---

## 內建裝置範本庫一覽表

系統預載之 7 大類別與 13+ 種晶片範本詳細規範如下：

| 類別 (Category) | 晶片名稱 (Chip) | EM Type 標頭 | 預設 PowerState | 支援欄位與預設門檻 | 晶片說明 |
|---|---|---|---|---|---|
| **Temperature** | **TMP75** | `TMP75` | `On` | Critical (95 °C), Non-Critical (85 °C) | TI 數位溫度感測器 |
| **Temperature** | **TMP421** | `TMP421` | `On` | Critical (90 °C), Non-Critical (80 °C) | TI 遠端/本地雙溫感測器 |
| **Temperature** | **LM75** | `LM75` | `On` | Critical (85 °C), Non-Critical (75 °C) | 業界通用標準溫度晶片 |
| **Temperature** | **EMC1413** | `EMC1413` | `On` | Critical (95 °C), Non-Critical (85 °C) | Microchip 多通道溫度感測器 |
| **ADC** | **ADC128D818** | `ADC128D818` | `On` | `Channel: 0` | TI 12-Bit 8 通道系統電壓監控 |
| **FRU / EEPROM** | **AT24C256** | `EEPROM` | `Always` | 必填 Bus / Address / Name | 256K I2C Serial EEPROM |
| **FRU / EEPROM** | **AT24C64** | `EEPROM` | `Always` | 必填 Bus / Address / Name | 64K I2C Serial EEPROM |
| **Fan Controller** | **MAX31790** | `MAX31790` | `On` | `TachConnector`, `TargetConnector` | 6 通道 PWM 風扇控制與轉速計 |
| **Fan Controller** | **EMC2305** | `EMC2305` | `On` | `PwmChannel: 0` | 轉速閉迴路 PWM 風扇控制器 |
| **Power Supply** | **PMBus** | `PMBus` | `On` | 標準 PMBus 電源供應器介面 | 通用伺服器電源監控 |
| **GPIO Expander** | **PCA9555** | `PCA9555` | `Always` | `PolarityInversion: false` | NXP 16-Bit I2C GPIO 擴展晶片 |
| **Hot-swap** | **ADM1272** | `ADM1272` | `On` | `Rsense: 0.001` | ADI 高壓熱插拔電源監控器 |
| **Hot-swap** | **LTC4282** | `LTC4282` | `On` | `Rsense: 0.001` | Linear / ADI 熱插拔控制器 |

---

## CLI 命令列使用指南

在 CI/CD 靜態代碼檢查或建置流程中，可使用 CLI 直接對 Entity-Manager JSON 進行校驗。

### 基本校驗

```bash
# 校驗單一 Entity-Manager JSON 設定檔
uv run fw-diag em validate board_config.json
```

### 搭配板級拓撲交叉檢查並輸出 JSON

```bash
# 結合 Board Profile 檢查未定義硬體或相容性問題
uv run fw-diag em validate board_config.json --board-profile examples/data/board_yv4.yaml

# 輸出 JSON 格式錯誤報告供自動化工具處理
uv run fw-diag em validate board_config.json --json validation_result.json
```

---

## D-Bus Mock 產生器

產生的 Mock 是長時間執行的 D-Bus service，不是一次性的 `busctl set-property` 指令。它會取得 `xyz.openbmc_project.FWDiagMock` bus name 並 export sensor/inventory objects；執行環境必須安裝 `dbus-next`，且 D-Bus policy 必須允許該 process 連線、取得名稱與匯出物件。任一動作失敗時程式會以非零狀態結束，不會顯示假成功。

---

## 實體硬體安全與驗證限制

Entity-Manager Builder 與 Validator 是提升組態正確性與開發效率的強大工具，但在真實硬體部署前，工程師仍需理解以下邊界：

- **起始範本非最終韌體驗收**：產生的 JSON 組態檔為標準初始模板，實際伺服器各散熱風道、供電架構之臨界溫度（Thresholds）需依 Thermal/Power 團隊規範調校。
- **靜態無衝突不代表實體上電正常**：靜態檢查通過僅代表 JSON 語法無位址重複，若實體硬體供電軌未拉高、I2C Pull-up 電阻異常或晶片焊接虛焊，OpenBMC 開機時仍可能發生通訊中斷。
- **目標板 D-Bus 運行期驗證 SOP**：在將新 JSON 燒錄至 BMC 映像檔後，應透過 SSH 登入目標板，執行以下指令驗證：
  1. `busctl tree xyz.openbmc_project.EntityManager`：確認 EM 成功識別該板卡。
  2. `busctl tree xyz.openbmc_project.HwmonTempSensor` 或 `busctl introspect`：確認各 Sensor Object 正常建立且 `Value` 屬性有正確讀值。
  3. `ipmitool sdr list`：確認 IPMI SDR 能正確回報所有感測器狀態，無 `ns` (Not Sensed) 異常。
