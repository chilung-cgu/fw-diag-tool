# Firmware Diagnostic Suite (`fw_diag_tool`)

專為 **Junior 韌體 / 嵌入式 / 硬體工程師** 量身打造的旗艦級跨平台工作站。
結合 **邏輯分析儀波形還原**、**5 大伺服器與嵌入式協定解析**（I2C/PMBus, PCIe AER, SPI Flash, UART Crash Dump, MCTP/IPMB）、**雙波形差分對比 (Waveform Diff)**、**Linux & OpenBMC Device Tree 自動生成** 以及 **20 大實戰除錯演練場**。

👉 **完整新人圖文教學指南**：請參閱 [docs/JUNIOR_FW_GUIDE.md](docs/JUNIOR_FW_GUIDE.md)。

---

## 🚀 快速啟動 Web 視覺化工作站

```bash
# 1. 進入專案目錄並啟動虛擬環境 (Python 3.10+)
cd ~/fw-diag-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. 啟動 Web 視覺化工作站 (macOS / Linux 一鍵啟動)
fw-diag gui
```
*(瀏覽器將自動開啟 `http://127.0.0.1:8501`，支援滑鼠滾輪縮放波形、檔案拖放與互動分析)*

---

## 🌟 12 大核心功能模組一覽

| 功能模組 | 協定 / 功能 | 核心特色與排查重點 |
|---|---|---|
| **1. I2C / PMBus 診斷與波形檢視** | I2C, SMBus, PMBus | SCL/SDA 微秒級數位方波還原、彩色協定軌（START, Addr, ACK, Data, STOP）、時脈抖動直方圖。 |
| **2. I2C 封包模擬與驅動產生** | C Driver CodeGen | 輸入 Slave Addr 與暫存器即時「造波形」，並產出 Linux `i2c-dev`、OpenBMC、STM32 HAL 與 Arduino C 代碼。 |
| **3. 雙波形差分對比 (Waveform Diff)** | A/B 測試比對 | 同時載入 Golden (良品) 與 Failing (不良品) 波形，自動抓出第一筆通訊分歧點並繪製上下對比圖。 |
| **4. UART Crash & HardFault 分析** | Linux Panic, ARM Cortex-M | 自動拆解 Kernel Panic (RIP/CR2/Call Trace) 與 ARM HardFault (HFSR/CFSR/DIVBYZERO/UNALIGNED)。 |
| **5. MCTP / IPMB 伺服器協定解析** | DSP0236, PLDM, SPDM, IPMB | 解析 OpenBMC / GPU / NIC 之 MCTP 傳輸標頭、PLDM 感測器監控與 IPMB Checksum 1/2 校驗。 |
| **6. Device Tree (.dts) 產生器** | Linux / OpenBMC BSP | 依據 I2C MUX 拓撲自動產出符合 Devicetree Spec v0.4 標準的 `.dtsi` 節點原始碼。 |
| **7. PCIe Config & AER 診斷** | PCIe Gen1~Gen6, AER | 4KB 配置空間解析、AER 4DW TLP Header 拆解、Link 降速/降寬 (Gen4 x16 -> Gen1 x1) 與 Link Down 告警。 |
| **8. SPI Flash 協定診斷** | SPI / QSPI NOR Flash | JEDEC 0x9F ID 自動識別、0x06 WREN 寫入保護狀態追蹤、256B Page Buffer 溢位覆蓋預警、MISO 線路故障偵測。 |
| **9. 晶片暫存器 Bitfield 解碼器** | Hardware Registers | 支援 PMBus / PCIe 定義，輸入 Raw Hex 即時展開 Bit 欄位與異常警報。 |
| **10. C 語言 Register 巨集產生器** | MISRA-C CodeGen | 從 YAML 自動產出 Position、Mask 與安全型別轉型的 `REG_..._GET` / `REG_..._SET` RMW 巨集。 |
| **11. 20 大實戰故障實驗室 (Fault Arena)** | Junior FW 演練 | 內建 20 個來自矽谷與伺服器一線大廠的真實故障波形案例，快速建立除錯直覺。 |
| **12. 韌體除錯指南 & SOP** | L1~L7 心智模型 | 整合硬體電氣訊號、協定層封包與驅動狀態機之標準排查 SOP。 |

---

## 🛠 常用 CLI 命令列指令速查

```bash
# 1. 診斷邏輯分析儀 I2C 波形 (支援 Saleae CSV)
fw-diag i2c analyze examples/data/i2c_golden.csv --md i2c_report.md

# 2. 診斷邏輯分析儀 SPI Flash 波形
fw-diag spi analyze examples/data/spi_w25q128_sample.csv --md spi_report.md

# 3. 診斷 UART Serial Crash Dump (Linux Kernel Panic / ARM HardFault)
fw-diag uart analyze examples/data/kernel_panic_nvme.log --md crash_report.md
fw-diag uart analyze examples/data/arm_hardfault_stm32.log

# 4. 解碼 MCTP 封包或 IPMB 伺服器管理訊框
fw-diag mctp analyze examples/data/mctp_pldm_sample.hex

# 5. 分析 PCIe lspci Dump (支援 Link 降級與 AER 4DW TLP 拆解)
fw-diag pcie analyze examples/data/pcie_aer_lspci.txt --md pcie_report.md

# 6. 自動產出 Linux Device Tree (.dts) 原始碼
fw-diag gen dts --bus 1 --mux 0x70 --out i2c_bus1.dtsi

# 7. 產生 C 語言暫存器標頭檔與 RMW 巨集
fw-diag gen c-header src/fw_diag_tool/data/pmbus_standard.yaml --out pmbus_regs.h --name PMBUS_REGS
```

---

## 🧪 測試與驗證

全專案具備完整單元測試套件（56 項測試，100% 通過）：
```bash
pytest -v
```