# Junior 韌體工程師全方位實戰上手與除錯指南

歡迎使用 **Firmware Diagnostic Toolkit (`fw-diag-tool`)**！

本指南專為 **0 基礎 / Junior 韌體與硬體工程師** 設計，從「硬體電氣訊號」到「通訊協定封包」、再到「軟韌體驅動實作」，以圖文、範例資料（Test Data）與 Step-by-Step 步驟，引導你掌握日常開發與現場除錯必備的核心技能。

> 💡 **建議閱讀順序**：先讀第一章（I2C 波形分析），這是所有韌體工程師的入門起點。之後根據你目前遇到的問題類型，跳轉到對應章節即可。

> 🧭 **不知道頁面或圖表在說什麼？** 先看[12 個 GUI 頁面的閱讀地圖](chapters/appendix_gui_reading_guide.md)，它用「輸入 → 先看什麼 → 不能證明什麼 → 下一步」帶你逐頁定位；再進入該頁的詳細章節。

---

## 快速啟動 Web 視覺化工作站

```bash
# macOS / Linux，需 Python 3.10+ 與 uv
# 先在 clone 出來的 fw-diag-tool 專案根目錄執行
uv sync --all-extras
uv run fw-diag gui
```

瀏覽器將自動開啟 `http://127.0.0.1:8501`，左側側邊欄可切換 12 大功能模組。

> 若你的環境沒有 `uv`，可依公司規範建立 virtualenv 後安裝專案；重點是使用專案鎖定的依賴，
> 不要把套件裝進系統 Python。首次啟動遇到問題，先看根目錄 README 的環境需求與 `uv lock --check`。

---

## 章節目錄（點擊連結前往對應章節）

| # | GUI 頁面 | 對應章節文件 | 測試資料 |
|---|---|---|---|
| 1 | 📊 I2C / PMBus 診斷與波形檢視 | [ch01_i2c_pmbus.md](chapters/ch01_i2c_pmbus.md) + [附錄A 圖表判讀](chapters/appendix_chart_guide.md) | `i2c_split_decoded.csv`、`i2c_raw_100khz.csv`、`i2c_text_trace.log`、aggregate `i2c_golden.csv` |
| 2 | 🎨 I2C 封包模擬器與驅動產生 | [ch02_packet_builder.md](chapters/ch02_packet_builder.md) | 無需檔案 |
| 3 | ⚖️ 雙波形對比檢視（Waveform Diff） | [ch03_waveform_diff.md](chapters/ch03_waveform_diff.md) | GUI 內建 pair：`i2c_golden.csv` + `i2c_failing_nack.csv` |
| 4 | 📟 UART 崩潰轉儲與 HardFault 分析（Crash Dump） | [ch04_uart_crash.md](chapters/ch04_uart_crash.md) | `kernel_panic_nvme.log` / `arm_hardfault_stm32.log` |
| 5 | 🌐 MCTP／IPMB 伺服器管理協定解析 | [ch05_mctp_ipmb.md](chapters/ch05_mctp_ipmb.md) | `mctp_pldm_sample.hex` / `ipmb_sample.hex` |
| 6 | 🌲 Device Tree（.dts）產生器 | [ch06_dts_generator.md](chapters/ch06_dts_generator.md) | 無需檔案 |
| 7 | 🚀 PCIe 設定空間（Config Space）與 AER 診斷 | [ch07_pcie_aer.md](chapters/ch07_pcie_aer.md) | `pcie_aer_lspci.txt` / `pcie_aer_dmesg.log` |
| 8 | ⚡ SPI Flash 協定診斷 | [ch08_spi_flash.md](chapters/ch08_spi_flash.md) | `spi_w25q128_sample.csv` |
| 9 | 🎛 晶片暫存器 Bitfield 解碼器 | [ch09_register_codegen.md](chapters/ch09_register_codegen.md) | 內建 YAML |
| 10 | 🛠 C 語言 Register 巨集產生器 | [ch09_register_codegen.md](chapters/ch09_register_codegen.md)（同第9章） | 內建 YAML |
| 11 | 🏆 初階 Firmware 實戰除錯實驗室（Fault Arena） | [ch10_fault_arena.md](chapters/ch10_fault_arena.md) | 內建案例 |
| 12 | 📚 韌體除錯指南與 SOP | [ch12_sop.md](chapters/ch12_sop.md) + [GUI 閱讀地圖](chapters/appendix_gui_reading_guide.md) + GUI L1~L7 分層模型 | 無需檔案 |

> 📂 **測試資料路徑**：`examples/data/` 目錄下有所有演練用的 CSV / Log / Hex 檔案。第 3 頁也提供套件內建的 Golden/Failing pair 載入與下載按鈕；PCIe dmesg 範例則可直接貼上 `examples/data/pcie_aer_dmesg.log` 的內容。

---

## 文件結構說明

```
docs/
├── index.md                    ← 唯一的總目錄與學習路線（本檔案）
├── chapters/                    ← 各章節詳細教學（每個 GUI 頁面一個檔案）
│   ├── ch01_i2c_pmbus.md        ← I2C 波形診斷與數位波形判讀
│   ├── ch02_packet_builder.md   ← 封包模擬器與 C 驅動產生
│   ├── ch03_waveform_diff.md    ← Golden 與 Failing 雙波形比對
│   ├── ch04_uart_crash.md       ← Linux Kernel Panic + ARM HardFault
│   ├── ch05_mctp_ipmb.md        ← MCTP／IPMB 伺服器管理協定
│   ├── ch06_dts_generator.md    ← Device Tree 自動生成
│   ├── ch07_pcie_aer.md         ← PCIe Config Space + Link 降級 + AER
│   ├── ch08_spi_flash.md        ← SPI NOR Flash 協定診斷
│   ├── ch09_register_codegen.md ← Bitfield 解碼 + C Header RMW 巨集
│   ├── ch10_fault_arena.md      ← 20 大故障案例分類總覽
│   ├── ch12_sop.md               ← L1~L7 分層除錯 SOP 與證據詞彙
│   ├── appendix_chart_guide.md  ← I2C 圖表與 evidence level 判讀
│   └── appendix_gui_reading_guide.md ← 12 個 GUI 頁面的第一輪閱讀地圖
└── ...
```
