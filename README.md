# Firmware Diagnostic Suite (`fw_diag_tool`)

專為 **Junior 韌體 / 嵌入式 / 硬體工程師** 設計的本機診斷與學習工具，目標平台為 macOS 與 Linux。
目前提供 I2C/PMBus、PCIe AER、SPI Flash、UART Crash Dump、MCTP/IPMB 的檔案分析，以及協定示意圖、差分比較、程式碼產生器與 20 個 synthetic 練習情境。各模組的輸入能力與限制請先閱讀 [能力與限制](docs/LIMITATIONS.md)。

👉 **完整新人圖文教學指南**：請參閱 [docs/JUNIOR_FW_GUIDE.md](docs/JUNIOR_FW_GUIDE.md)。
> 📂 **各章節詳細文件**：[ch01 I2C波形](docs/chapters/ch01_i2c_pmbus.md) | [ch02 封包/驅動產生](docs/chapters/ch02_packet_builder.md) | [ch03 Waveform Diff](docs/chapters/ch03_waveform_diff.md) | [ch04 UART Crash](docs/chapters/ch04_uart_crash.md) | [ch05 MCTP/IPMB](docs/chapters/ch05_mctp_ipmb.md) | [ch06 Device Tree](docs/chapters/ch06_dts_generator.md) | [ch07 PCIe AER](docs/chapters/ch07_pcie_aer.md) | [ch08 SPI Flash](docs/chapters/ch08_spi_flash.md) | [ch09 Register/Codegen](docs/chapters/ch09_register_codegen.md) | [ch10 Fault Arena](docs/chapters/ch10_fault_arena.md) | [附錄A 圖表判讀](docs/chapters/appendix_chart_guide.md)

---

## 🚀 快速啟動 Web 視覺化工作站

```bash
# 1. 進入專案目錄並同步鎖定環境 (Python 3.10+)
cd ~/fw-diag-tool
uv sync --all-extras

# 2. 啟動 Web 視覺化工作站 (macOS / Linux 一鍵啟動)
uv run fw-diag gui
```
*(瀏覽器將自動開啟 `http://127.0.0.1:8501`，支援滑鼠滾輪縮放波形、檔案拖放與互動分析)*

---

## 🌟 12 大核心功能模組一覽

| 功能模組 | 協定 / 功能 | 核心特色與排查重點 |
|---|---|---|
| **1. I2C / PMBus 診斷與波形檢視** | I2C, SMBus, PMBus | Analyzer table 做協定診斷；Raw digital `Time/SCL/SDA` CSV 可量測 digital edge、tHIGH/tLOW 與頻率；兩者都明確標示證據限制。 |
| **2. I2C 封包模擬與驅動產生** | C Driver CodeGen | 輸入 Slave Addr 與暫存器即時「造波形」，並產出 Linux `i2c-dev`、OpenBMC、STM32 HAL 與 Arduino C 代碼。 |
| **3. 雙波形差分對比 (Waveform Diff)** | A/B 測試比對 | 逐筆比較 Golden 與 Failing 的已解碼交易，找出第一筆協定差異並繪製重建示意圖。 |
| **4. UART Crash & HardFault 分析** | Linux Panic, ARM Cortex-M | 自動拆解 Kernel Panic (RIP/CR2/Call Trace) 與 ARM HardFault (HFSR/CFSR/DIVBYZERO/UNALIGNED)。 |
| **5. MCTP / IPMB 伺服器協定解析** | MCTP, PLDM, SPDM, IPMB | 解析基本 MCTP/IPMB header 與 checksum，並辨識目前已支援的 PLDM/SPDM message type；尚非完整 conformance decoder。 |
| **6. Device Tree (.dts) 產生器** | Linux / OpenBMC BSP | 依明確輸入的 I2C MUX 拓撲產生 `.dtsi` 模板；套用至產品前仍須以對應 binding、`dtc` 與 dt-schema 驗證。 |
| **7. PCIe Config & AER 診斷** | PCIe Config, AER | 解析目前支援的 Config Space、Capability、AER 與 Link 資訊；不分析 PCIe 高速電氣波形或 LTSSM。 |
| **8. SPI Flash 協定診斷** | SPI NOR Flash | 解析已解碼的 SPI CSV、JEDEC opcode 與基本 WREN/erase/program 序列，並列出可能異常原因。 |
| **9. 晶片暫存器 Bitfield 解碼器** | Hardware Registers | 支援 PMBus / PCIe 定義，輸入 Raw Hex 即時展開 Bit 欄位與異常警報。 |
| **10. C 語言 Register 巨集產生器** | MISRA-oriented CodeGen | 從 YAML 產出 Position、Mask 與 `REG_..._GET` / `REG_..._SET` 巨集；仍須依專案 compiler、coding standard 與靜態分析器驗證。 |
| **11. 20 大實戰故障實驗室 (Fault Arena)** | Junior FW 演練 | 內建 20 個 synthetic 故障情境，用來練習從症狀建立假設與排查順序；不是實際公司 capture。 |
| **12. 韌體除錯指南 & SOP** | L1~L7 心智模型 | 整合硬體電氣訊號、協定層封包與驅動狀態機之標準排查 SOP。 |

---

## 🛠 常用 CLI 命令列指令速查

```bash
# 1. 診斷邏輯分析儀 I2C 波形 (支援 Saleae CSV)
fw-diag i2c analyze examples/data/i2c_golden.csv --md i2c_report.md

# 1b. 診斷 raw digital transition（Time/SCL/SDA；顯示實測 digital 0/1 波形）
fw-diag i2c analyze capture_raw.csv --raw-digital --md raw_i2c_report.md

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

執行目前的單元與整合測試；精確數量以當次輸出為準：
```bash
uv run pytest -v
```
