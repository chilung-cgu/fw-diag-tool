# 能力、證據層級與限制

本文件說明 `fw-diag-tool` 能從不同輸入可靠判斷什麼，以及哪些結論仍需要示波器、邏輯分析儀原始資料、datasheet 或目標板驗證。

## 先分清楚輸入資料

| 輸入 | 工具能看到 | 可以判斷 | 不能直接判斷 |
|---|---|---|---|
| Analyzer / decoded CSV | Analyzer 已解出的 address、方向、data、ACK/NACK 與部分時間欄位 | 交易順序、已提供的協定欄位、部分 retry 或缺少 STOP | 真實 SCL/SDA edge、rise/fall time、電壓、未匯出的 bit timing |
| Raw digital CSV | 每次 digital transition 的時間與邏輯狀態 | START/STOP、bit、ACK/NACK、digital tHIGH/tLOW、可見的 clock stretch | 類比電壓、overshoot、ringing、threshold margin、精確 rise/fall time |
| Analog capture | 取樣後的電壓與時間 | 電壓、rise/fall、overshoot、ringing；仍受 sample rate 與 probe 影響 | 沒有協定解碼時的高階 command 意義 |
| Log / register dump | 軟體或硬體記錄下來的狀態 | 已記錄的 error bit、stack、register 與事件關聯 | 未被記錄的線路事件與單一確定根因 |

## 工具輸出的四種證據層級

- **Measured**：直接由輸入中的時間、edge 或值計算。
- **Inferred**：由多個已觀察欄位推論，仍可能有其他解釋。
- **Reconstructed**：依 decoded bytes 與協定規則畫出的示意圖，不是實際 capture。
- **Unavailable**：輸入沒有足夠資料，工具不應補值或顯示看似精準的結果。

## I2C / SMBus / PMBus

- I2C address 不是唯一的晶片識別碼；相同 address 可能對應多種 EEPROM、sensor、GPIO expander 或 PMBus device。
- Read transaction 最後一個 byte 的 NACK 可能是 controller 正常終止讀取，不應單獨視為故障。
- Decoded CSV 沒有 SCL edge 或可靠 duration 時，不能計算真實 clock frequency、jitter、tHIGH 或 tLOW。
- GUI/CLI 的 Raw digital 模式要求可辨識的 timestamp、SCL、SDA 欄位，且每列時間嚴格遞增、邏輯值只能是 0/1；欄位不明或 sampling edge 同時變化時會拒絕猜測。
- Raw digital 模式量到的是 logic-level transition，不是類比電壓；rise/fall time、pull-up 強度與 ringing 仍需示波器或類比資料。
- Digital capture 無法證明 pull-up 電阻、bus capacitance、overshoot 或 ringing；這些需要 schematic、datasheet 與 analog measurement。
- PMBus 單位、format、PAGE/PHASE 與 command 意義可能依 device 而異；沒有明確 device profile 時只顯示原始值與候選解釋。

## SPI、UART、MCTP/IPMB 與 PCIe

- SPI decoded CSV 可用於 opcode/sequence 分析；沒有 SCLK/MOSI/MISO/CS raw edge 時，不代表工具量到實際 SPI waveform 或 CPOL/CPHA timing。
- UART crash log 的 fault address 與 status bit 可縮小範圍，但通常不能單獨證明 root cause；可靠 symbolication 需要匹配的 ELF、map file 或 symbols。
- MCTP、PLDM、SPDM 與 IPMB 目前只支援已實作的 header/message 欄位；未知 message type 應保留原始 bytes，而不是猜測內容。
- 一般低速 logic analyzer 不適合直接量測 PCIe 高速 differential link。此工具的 PCIe 功能以 Config Space、`lspci` 與 AER log 為主，不代表 protocol analyzer 或示波器能力。

## 產生器與硬體安全

- Device Tree、C header 與 driver snippet 是起始模板，不是可直接上產品的保證產物。
- Device Tree 必須搭配實際 SoC/board binding，以 `dtc`、dt-schema 與目標 kernel 驗證。
- C header 必須以目標 compiler、warning policy、coding standard 與靜態分析器驗證。
- 工具不應自動執行 `i2cset`、`i2ctransfer`、`devmem`、flash 或 EEPROM 寫入；使用任何寫入命令前，仍需人工確認 bus、address、register、device 與電源狀態。

## 隱私與重現性

- 工具預設在本機分析，不需要把公司 capture 上傳到雲端。
- 匯出報告或 session 前，請檢查 device name、路徑、log、serial number 與 proprietary register value。
- 可重現報告應記錄 tool version、輸入檔 SHA-256、分析設定與 board profile；缺少這些資訊時，不應宣稱兩次結果完全等價。
