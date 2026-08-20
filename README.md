# FW Signal & Trace Diagnostic Toolkit (`fw_diag_tool`)

專為 **Junior Firmware / Hardware Engineer** 設計的跨平台除錯、波形分析與協定診斷工具箱。
無需額外購買硬體（如 Raspberry Pi），直接搭配公司現有的**邏輯分析儀 (Logic Analyzer, 如 Saleae)** 匯出的波形 Log、系統 **`lspci` / PCIe AER 日誌** 與 **晶片暫存器定義 (YAML)** 進行深度語意解碼與 Root Cause Analysis (RCA)。

提供 **CLI 命令列工具** 與 **macOS 輕量 Web GUI 視覺化介面**。

---

## 核心功能模組

### 1. 🖥 互動式視覺化 Web GUI (`fw-diag gui`)
- **零原生視窗依賴**：基於 Streamlit + Plotly，純 Python 實作，macOS 一鍵啟動。
- **四大專屬除錯面板**：
  1. **📊 I2C / PMBus 波形診斷**：拖放 CSV / Log，即時渲染 Slave 位址統計、Clock Stretching 逾時警報與交易列表。
  2. **🚀 PCIe Config & AER 診斷**：貼上 `lspci -xxxx` 或 `dmesg` 報錯，自動展開 4KB 配置空間、BAR 與 4DW TLP Header 封包。
  3. **🎛 晶片暫存器 Bitfield 解碼器**：內建 PMBus 與 PCIe 暫存器模板，輸入 Hex 數值即時展開各 Bit 欄位與異常標記。
  4. **📚 韌體除錯指南 & SOP**：整合 Junior 工程師必備的 L1~L7 分層排查心智模型與 I2C NACK 排查 SOP。

### 2. I2C / SMBus / PMBus 智慧異常診斷 (`fw-diag i2c`)
- **Saleae Logic 2 CSV / Raw Trace 匯入**：直接分析邏輯分析儀匯出的波形數據。
- **EEPROM Page Boundary Rollover 偵測**：當連續寫入長度超過晶片 Page Size（如 24C64 的 32 bytes）時，精準告警位址迴轉覆蓋風險。
- **時序與通訊異常告警**：
  - **Address NACK vs Data NACK**：判斷是晶片未上電/位址錯誤，還是傳輸中被 Slave 拒絕。
  - **Clock Stretching 逾時**：自動偵測 Slave 拉低 SCL 超過 SMBus 25ms 規範，預警 Bus Hang。
  - **Missing STOP Condition**：標記 Bus 未正常釋放之異常。
- **PMBus & 感測器自動解碼**：支援 Linear11、Linear16 浮點數轉換、STATUS_WORD 故障診斷，以及 LM75 / INA226 暫存器解析。

### 3. PCIe Config Space、AER 與 TLP Header 解碼 (`fw-diag pcie`)
- **PCIe Config Space (4KB) 解析**：支援 Type 0 (Endpoint) 與 Type 1 (Bridge) Header、32/64-bit BAR 空間計算。
- **Capability 鏈表走訪**：自動解析 MSI, MSI-X, PCIe Cap, AER, DSN, SR-IOV 等鏈表。
- **AER (Advanced Error Reporting) 診斷**：
  - 解碼 Uncorrectable (Fatal/Non-Fatal) 與 Correctable Status/Mask/Severity。
  - 解碼 4DW Header Log（還原肇事的 Memory Read/Write, Config Request 或 Completion 封包、目標位址、Requester BDF 與 Length）。
  - 自動提供韌體排查指引（如 Completion Timeout, Unsupported Request, Malformed TLP 等排查 SOP）。
- **Kernel `dmesg` AER 日誌直接診斷**：直接輸入 Linux dmesg 錯誤日誌即可進行結構化分析。

### 4. 硬體暫存器 Map 位元對應解碼器 (`fw-diag reg`)
- **YAML 驅動的暫存器定義檔**：將晶片 Datasheet 中的 Register Bitfield 轉化為 YAML 規範。
- **Bitfield 與警報視覺化**：輸入 Raw Hex（如 `0x8400`），自動展開每個 Bit 欄位與狀態意義，並對異常位元高亮警示。

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
# 分析 Saleae Logic 匯出的 CSV 並產出 Markdown 報告
fw-diag i2c analyze trace.csv --md i2c_report.md
```

### 2. 分析 PCIe 配置空間與 AER 錯誤
```bash
# 1. 分析 lspci -xxxx 文字輸出或 4KB Hex Dump
fw-diag pcie analyze lspci_dump.txt --md pcie_report.md

# 2. 分析 Linux dmesg 中的 PCIe Bus Error / AER 紀錄
fw-diag pcie analyze dmesg_aer.log
```

### 3. 解碼硬體暫存器 Bitfield
```bash
# 依據 YAML 定義解碼 PMBUS_STATUS_WORD 暫存器數值
fw-diag reg decode src/fw_diag_tool/data/pmbus_standard.yaml STATUS_WORD 0x8400
```

---

## 測試與驗證

專案包含 29 項單元測試：
```bash
pytest -v
```
