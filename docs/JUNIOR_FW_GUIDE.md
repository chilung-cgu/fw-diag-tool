# Junior 韌體工程師全方位實戰上手與除錯指南

歡迎使用 **Firmware Diagnostic Toolkit (`fw-diag-tool`)**！

本指南專為 **0 基礎 / Junior 韌體與硬體工程師** 設計，從「硬體電氣訊號」到「通訊協定封包」、再到「軟韌體驅動實作」，以圖文、範例資料（Test Data）與 Step-by-Step 步驟，引導你掌握日常開發與現場除錯必備的核心技能。

> 💡 **建議閱讀順序**：先讀第一章（I2C 波形分析），這是所有韌體工程師的入門起點。之後根據你目前遇到的問題類型，跳轉到對應章節即可。

---

## 快速啟動 Web 視覺化工作站

```bash
cd ~/fw-diag-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
fw-diag gui
```

瀏覽器將自動開啟 `http://127.0.0.1:8501`，左側側邊欄可切換 12 大功能模組。

---

## 章節目錄（點擊連結前往對應章節）

| # | GUI 頁面 | 對應章節文件 | 測試資料 |
|---|---|---|---|
| 1 | 📊 I2C / PMBus 診斷與波形檢視 | [ch01_i2c_pmbus.md](chapters/ch01_i2c_pmbus.md) + [附錄A 圖表判讀](chapters/appendix_chart_guide.md) | `examples/data/i2c_golden.csv` |
| 2 | 🎨 I2C 封包模擬器與驅動產生 | [ch02_packet_builder.md](chapters/ch02_packet_builder.md) | 無需檔案 |
| 3 | ⚖️ 雙波形對比檢視 (Waveform Diff) | [ch03_waveform_diff.md](chapters/ch03_waveform_diff.md) | `i2c_golden.csv` + `i2c_failing_nack.csv` |
| 4 | 📟 UART Crash & HardFault 分析 | [ch04_uart_crash.md](chapters/ch04_uart_crash.md) | `kernel_panic_nvme.log` / `arm_hardfault_stm32.log` |
| 5 | 🌐 MCTP / IPMB 伺服器協定解析 | [ch05_mctp_ipmb.md](chapters/ch05_mctp_ipmb.md) | `mctp_pldm_sample.hex` / `ipmb_sample.hex` |
| 6 | 🌲 Device Tree (.dts) 產生器 | [ch06_dts_generator.md](chapters/ch06_dts_generator.md) | 無需檔案 |
| 7 | 🚀 PCIe Config & AER 診斷 | [ch07_pcie_aer.md](chapters/ch07_pcie_aer.md) | `pcie_aer_lspci.txt` |
| 8 | ⚡ SPI Flash 協定診斷 | [ch08_spi_flash.md](chapters/ch08_spi_flash.md) | `spi_w25q128_sample.csv` |
| 9 | 🎛 晶片暫存器 Bitfield 解碼器 | [ch09_register_codegen.md](chapters/ch09_register_codegen.md) | 內建 YAML |
| 10 | 🛠 C 語言 Register 巨集產生器 | [ch09_register_codegen.md](chapters/ch09_register_codegen.md)（同第9章） | 內建 YAML |
| 11 | 🏆 Junior FW 實戰除錯實驗室 (Fault Arena) | [ch10_fault_arena.md](chapters/ch10_fault_arena.md) | 內建案例 |
| 12 | 📚 韌體除錯指南 & SOP | 直接在 GUI 中查看 L1~L7 分層模型 | 無需檔案 |

> 📂 **測試資料路徑**：`examples/data/` 目錄下有所有演練用的 CSV / Log / Hex 檔案。

---

## 文件結構說明

```
docs/
├── JUNIOR_FW_GUIDE.md          ← 你目前在看的總目錄（本檔案）
├── chapters/                    ← 各章節詳細教學（每個 GUI 頁面一個檔案）
│   ├── ch01_i2c_pmbus.md        ← I2C 波形診斷與數位波形判讀
│   ├── ch02_packet_builder.md   ← 封包模擬器與 C 驅動產生
│   ├── ch03_waveform_diff.md    ← Golden vs Failing 雙波形比對
│   ├── ch04_uart_crash.md       ← Linux Kernel Panic + ARM HardFault
│   ├── ch05_mctp_ipmb.md        ← MCTP / IPMB 伺服器管理協定
│   ├── ch06_dts_generator.md    ← Device Tree 自動生成
│   ├── ch07_pcie_aer.md         ← PCIe Config Space + Link 降級 + AER
│   ├── ch08_spi_flash.md        ← SPI NOR Flash 協定診斷
│   ├── ch09_register_codegen.md ← Bitfield 解碼 + C Header RMW 巨集
│   ├── ch10_fault_arena.md      ← 20 大故障案例分類總覽
│   └── appendix_chart_guide.md  ← 所有圖表的詳細判讀教學
└── ...
```