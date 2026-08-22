# FW Signal & Trace Diagnostic Toolkit (`fw_diag_tool`)

專為 **Junior Firmware / Hardware Engineer** 設計的跨平台除錯、波形分析、協定診斷與 C 程式碼生成工具箱。
無需額外購買硬體（如 Raspberry Pi），直接搭配公司現有的**邏輯分析儀 (Logic Analyzer, 如 Saleae)** 匯出的波形 Log、系統 **`lspci` / PCIe AER 日誌** 與 **晶片暫存器定義 (YAML)** 進行深度語意解碼與 Root Cause Analysis (RCA)。

提供 **CLI 命令列工具** 與 **macOS 輕量 Web GUI 視覺化介面**。

---

## 核心功能模組

### 1. 🖥 互動式視覺化 Web GUI (`fw-diag gui`)
- **零原生視窗依賴**：基於 Streamlit + Plotly，純 Python 實作，macOS 一鍵啟動。
- **多功能除錯看板**：
  1. **📊 I2C / PMBus 波形診斷**：拖放 CSV / Log，即時渲染 Slave 位址統計、Clock Stretching 逾時警報與 MUX 拓撲路徑。
  2. **🚀 PCIe Config & AER 診斷**：貼上 `lspci -xxxx` 或 `dmesg` 報錯，自動展開 4KB 配置空間、Link 降速/降寬警示與 4DW TLP Header 封包。
  3. **⚡ SPI Flash 協定診斷**：解析 JEDEC 0x9F ID、Page Program 跨頁覆蓋預警、未發送 0x06 WREN 寫入無效偵測。
  4. **🎛 晶片暫存器 Bitfield 解碼器**：內建 PMBus 與 PCIe 暫存器模板，輸入 Hex 數值即時展開各 Bit 欄位與異常標記。
  5. **🛠 C 語言 Register 巨集產生器**：從 YAML 一鍵產生安全 MISRA-C `#define`、Mask 與 RMW (Read-Modify-Write) 巨集。
  6. **🧪 Junior FW 故障模擬實驗室 (Fault Lab)**：內建 5 大經典硬體故障情境（I2C NACK、Clock Stretching、EEPROM Wrap、PCIe CTO、SPI WREN），供新人快速演練排查。
  7. **📚 韌體除錯指南 & SOP**：整合 Junior 工程師必備的 L1~L7 分層排查心智模型與 I2C NACK 排查 SOP。

### 2. I2C / SMBus / PMBus 智慧異常診斷 (`fw-diag i2c`)
- **Saleae Logic 2 CSV / Raw Trace 匯入**：直接分析邏輯分析儀匯出的波形數據。
- **PCA9548A / PCA9546 I2C MUX 拓撲追蹤**：自動識別 Channel 切換狀態，標註後續子交易拓撲路徑（如 `[MUX 0x70: Ch2] -> Slave 0x50`），並告警多通道同時開啟之衝突風險。
- **EEPROM Page Boundary Rollover 偵測**：當連續寫入長度超過晶片 Page Size（如 24C64 的 32 bytes）時，精準告警位址迴轉覆蓋風險。
- **時序與通訊異常告警**：
  - **Address NACK vs Data NACK**：判斷是晶片未上電/位址錯誤，還是傳輸中被 Slave 拒絕。
  - **Clock Stretching 逾時**：自動偵測 Slave 拉低 SCL 超過 SMBus 25ms 規範，預警 Bus Hang。
  - **Missing STOP Condition**：標記 Bus 未正常釋放之異常。
- **PMBus & 感測器自動解碼**：支援 Linear11、Linear16 浮點數轉換、STATUS_WORD 故障診斷，以及 LM75 / INA226 暫存器解析。

### 3. PCIe Config Space、AER 與 Link 降級解碼 (`fw-diag pcie`)
- **PCIe Link Speed / Width 降級智慧診斷**：自動比對 `Link Capabilities` 與 `Link Status`，若未達最高設計速率（如 Gen4 x16 降為 Gen3 x8）立即觸發警示並提供金手指/SI/供電排查建議。
- **Multi-BDF 批次解析**：支援一次貼上包含多個 PCIe 設備的整機 `lspci -xxxx` 輸出。
- **PCIe Config Space (4KB) 解析**：支援 Type 0 (Endpoint) 與 Type 1 (Bridge) Header、32/64-bit BAR 空間計算。
- **AER (Advanced Error Reporting) 診斷**：
  - 解碼 4DW Header Log（還原肇事的 Memory Read/Write, Config Request 或 Completion 封包、目標位址、Requester BDF 與 Length）。
  - 自動提供韌體排查指引（如 Completion Timeout, Unsupported Request, Malformed TLP 等排查 SOP）。
- **Kernel `dmesg` AER 日誌直接診斷**：直接輸入 Linux dmesg 錯誤日誌即可進行結構化分析。

### 4. SPI / QSPI Flash 協定診斷 (`fw-diag spi`)
- **JEDEC 0x9F 自動識別**：內建 Winbond, Macronix, Micron, GigaDevice 等主流 Flash 晶片資料庫。
- **WREN 狀態追蹤**：偵測未發送 0x06 (Write Enable) 即發送 0x02/Erase 指令的無效寫入。
- **Page Program 256-byte 溢位覆蓋預警**：計算寫入位址與長度，標記內部 Page Buffer Wrap-Around 風險。

### 5. C 語言暫存器代碼自動生成器 (`fw-diag gen`)
- **一鍵產出 C 語言 Header**：輸入 YAML 規範，自動產出含 Header Guards、Position、Mask、Get/Set 巨集與 Value Enums 的 C 標頭檔。

---

## 安裝與啟動 (macOS / Linux)

### 1. 建立虛擬環境與安裝
```bash
# 進入專案目錄
cd build_fw_tool

# 建立 Python 虛擬環境 (Python 3.10+)
python3 -m venv .venv
source .venv/bin/activate

# 安裝套件 (Editable Mode)
pip install -e .
```

### 2. 啟動 Web GUI 視覺化介面 (推薦)
```bash
fw-diag gui
```
*(會自動在 macOS 瀏覽器開啟 `http://127.0.0.1:8501`，支援拖放上傳與互動圖表)*

---

## 常用 CLI 指令範例

### 1. 診斷邏輯分析儀 I2C 波形
```bash
fw-diag i2c analyze trace.csv --md i2c_report.md
```

### 2. 診斷邏輯分析儀 SPI Flash 波形
```bash
fw-diag spi analyze spi_trace.csv --md spi_report.md
```

### 3. 分析 PCIe 配置空間與 AER 錯誤
```bash
# 分析 lspci -xxxx 文字輸出或 4KB Hex Dump
fw-diag pcie analyze lspci_dump.txt --md pcie_report.md

# 分析 Linux dmesg 中的 PCIe Bus Error / AER 紀錄
fw-diag pcie analyze dmesg_aer.log
```

### 4. 產生 C 語言暫存器標頭檔
```bash
fw-diag gen c-header src/fw_diag_tool/data/pmbus_standard.yaml --out pmbus.h --name PMBUS_REGS
```

---

## 測試與驗證

專案包含 37 項單元測試：
```bash
pytest -v
```