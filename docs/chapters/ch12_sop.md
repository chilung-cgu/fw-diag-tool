# 韌體除錯分層 SOP

若你第一次使用 GUI，先看[12 個 GUI 頁面的閱讀地圖](appendix_gui_reading_guide.md)，再用本章的 L1～L7 SOP 組織跨模組排查。

本章是 GUI 第 12 頁「📚 韌體除錯指南與 SOP」的完整教學。它不新增一種協定解碼器，而是教你把不同來源的證據放在正確層次，避免看到一張漂亮的圖就直接宣布 root cause。

## 先記住三句話

1. **先保存原始證據，再開始解讀。** 截圖只適合溝通，不足以重跑分析。
2. **工具可以縮小範圍，不會自動證明根因。** 根因仍要用 datasheet、schematic、driver source、matching ELF、kernel log 或目標板重現確認。
3. **缺資料就寫 `Unavailable`，不要用 0、預設值或猜測填滿畫面。**

## 這一頁的 L1～L7 是什麼？

這是實務上的排查順序，不是宣稱所有問題都嚴格符合 OSI 七層模型。每一層都回答不同問題：

| 層次 | 白話問題 | `fw-diag-tool` 可以提供的證據 | 仍然要到哪裡確認 |
|---|---|---|---|
| **L1 物理 / 電氣** | 線上真的有正確的電平、clock、pull-up、termination 嗎？ | Raw I2C 的 digital 0/1 edge、`tHIGH`、`tLOW`、period、頻率 | 示波器、公司的 logic analyzer、電源量測、schematic；本工具不能量類比電壓、rise/fall 或 PCIe eye |
| **L2 Link / Framing** | START/STOP、CS、byte boundary、ACK/NACK 是否合理？ | I2C/SPI analyzer decode、raw I2C bit decode、PCIe config/AER 欄位 | 原始 capture、analyzer 設定、協定規格 |
| **L3 Protocol** | address、opcode、register、command、checksum、message type 是否正確？ | I2C/SMBus/PMBus、EEPROM、SPI、MCTP/IPMB、PCIe 欄位解碼 | 目標晶片 datasheet、DMTF/SMBus/PMBus 或產品協定文件 |
| **L4 Driver / Transport** | driver 或 transport 是否送出預期序列？ | 將 capture/log 的交易順序整理出來；產生 driver/DTS 起始模板 | kernel source、driver debug log、DTS、實際執行環境；工具不會直接讀 live kernel state |
| **L5 Retry / State** | 是一次性錯誤，還是 retry、timeout、WREN/Busy、MUX/reset 狀態機？ | 列出已觀察到的 retry、NACK、clock stretch、SPI WREN/Busy 等事件 | driver 狀態機、timeout 設定、reset/power 時序與重現測試 |
| **L6 Platform / Board** | board wiring、binding、power/reset ownership 是否吻合？ | DTS/driver 起始模板與欄位檢查 | schematic、BOM、board revision、binding、`dtc`、`dt-schema` |
| **L7 Application / Meaning** | 這個 register 或 telemetry 值對產品行為代表什麼？ | register/bitfield、PMBus/sensor 的候選語意 | 正確 device profile、firmware source、產品需求與系統 log |

## 每次都照著做的 7 步

### Step 1：保存可重現的原始資料

建立一個資料夾，至少保留：

```text
case-2026-08-23/
├── raw/          # Saleae CSV、原始 log、lspci、register dump
├── config/       # analyzer channel/rate、命令列、board revision
├── reports/      # fw-diag 輸出的 Markdown/JSON/截圖
└── notes.md      # 觀察、假設、下一個測試
```

不要先用試算表改寫 timestamp 或刪掉 NACK。若要清理資料，另存清理後的檔案並記錄轉換方式。報告中的 `Input`、資料品質警告與 SHA256（若由你的流程產生）應能回到同一個原始檔。

I2C 頁面的 Markdown 分頁會提供「下載可重現 Session（不含原始檔）」：它包含工具版本、分析設定、輸入檔名、輸入 SHA-256 與結構化報告。Session 不是 capture 備份；請把原始 CSV/log 與它放在同一個 case 資料夾，並檢查是否含公司機密。

### Step 2：先辨認輸入證據等級

在 GUI 第 1 頁先看檔案屬於哪一種：

- **Decoded table**：已有 analyzer 解出的 transaction；可做協定與異常分析，但不代表工具看到了每一個 raw edge。
- **Raw digital**：每列至少有單調遞增的時間、SCL、SDA 0/1；可直接由 edge 計算 digital timing 與 bit decode。
- **Analog waveform**：目前本工具不接收類比電壓波形，rise/fall time 應標為 `Unavailable`。
- **Log / register dump / config dump**：分別送到 UART、MCTP/IPMB、PCIe 或 register 頁面，不要當成 I2C 波形輸入。

看到 `Unavailable` 不是程式壞掉，而是輸入沒有足夠證據。先記錄它，再決定是否回到公司 LA 重新 capture。

### Step 3：先查 L1，再看漂亮的圖

Raw I2C 模式中，先確認：

1. `Time` 是否為秒、有限值、非負、嚴格遞增。
2. SCL/SDA 是否真的只有 0 或 1。
3. `tHIGH`、`tLOW`、period 與 sample count 是否顯示為 measured；沒有 edge 時不能把預設 100 kHz 當量測結果。
4. 是否有 clock stretching、截斷 capture、同一 timestamp 同時變化等資料品質問題。

這個頁面仍然不能回答「電壓是否達到 VIH/VIL」或「pull-up RC 是否合格」。那是示波器/LA 與硬體規格的工作。

### Step 4：用 L2/L3 對照協定文件

在 I2C 圖表或 transaction table 中，逐筆確認：

- START → 7-bit address + R/W → ACK/NACK → data byte → ACK/NACK → STOP。
- Read 的最後一個 byte 若由 controller 發 NACK 來結束讀取，通常是正常終止；不要把它當成 target failure。
- Address NACK、write data NACK、checksum 錯誤或不合法 frame boundary 才是需要進一步排查的觀察。
- 輸入只有 address、byte、ACK 而沒有 timestamp 時，仍可做部分協定分析，但 timing 圖與時間排序要標示 `Unavailable`。

其餘頁面用同一個問題：SPI 看 opcode/WREN/Busy/page boundary；MCTP/IPMB 看 header、tag、sequence、checksum；PCIe 看 config capability/AER；UART 看 log 中可解析的 fault 欄位。每一項都要回到相應規格或 source 交叉確認。

### Step 5：把 L4/L5 對回 driver 與狀態機

不要只問「哪個裝置是紅色」。請把交易時間或順序對回：

| 觀察 | 可能方向（不是結論） | 下一個可區分測試 |
|---|---|---|
| 同一 address 連續 NACK | address、power/reset、MUX、target busy 或 driver retry | 比對 power/reset/MUX log，限制 retry 次數後重現 |
| SPI program 後立即讀回不一致 | 缺 WREN、仍 Busy、page boundary 或供電問題 | 比對 WEL/Busy/status，確認 page size 與 erase/program 時序 |
| UART fault address 很小 | NULL pointer 候選，亦可能是其他 fault context | 用 matching ELF、symbolication、CFSR/HFSR 與 fault frame 確認 |
| PCIe AER 出現錯誤 | link/config/endpoint 或電氣問題皆可能 | 對照 link status、AER severity、kernel log 與實際拓撲 |

`Possible`、`candidate`、`hypothesis` 都代表還有替代解釋；只有 source、規格與重現結果一致，才可以升級成已確認原因。

### Step 6：最後才檢查 L6/L7

當協定序列看起來合理，才檢查 board 與語意：

- DTS 產生器輸出是起始模板，不等於產品可直接合入的 binding。
- register decoder 只有在正確的 device profile、revision 與 register width 下才有可靠語意。
- Device name 若有多個候選，報告會保留候選與 confidence；不要把候選名稱寫成已確認的晶片型號。
- 對照 schematic、BOM、board revision、driver source、產品需求；這些不是 CSV 可以推導出來的。

### Step 7：寫一份可重現的結論

每個 finding 都用下面四欄，不要只寫「根因是 XXX」：

```text
Observed facts:
- Raw capture 在 0.0012 s 的 address 0x50 出現 NACK。
- timestamp 可用；頻率樣本 42 個，約 400 kHz。

Hypothesis:
- 可能是 EEPROM 尚未完成 write cycle，或 driver address/流程錯誤。

Discriminating test:
- 對照 datasheet tWR 與 status polling；同時保留 power/reset/MUX log。

Unverified:
- 尚未用示波器確認類比 VIH/VIL、rise time，也尚未確認 board revision。
```

## GUI 圖表怎麼讀

第 1 頁的詳細圖表解讀在 [附錄 A：圖表與證據判讀](appendix_chart_guide.md)。先看圖表標題、evidence label、sample count，再看顏色與大小：

- **SCL Clock Frequency Distribution**：X 軸是頻率，Y 軸是有效樣本數；單一窄柱只代表輸入中的樣本分布，不代表整條 bus 永遠穩定。
- **Bus Transaction Timeline & Active Device Map**：X 軸是 transaction start time，Y 軸是 device；圓點大小是 duration，顏色反映 ACK/NACK 狀態。沒有 timestamp 的資料不能當作可靠時間軸。
- **Waveform**：Raw digital 圖是 `Measured` 的 0/1 edge；decoded table 畫出的圖是 `Reconstructed` 示意。兩者都不是類比電壓波形。
- **Health Grade**：是目前輸入與規則的排查優先級摘要，不是晶片健康保證。

## 證據詞彙表

| 詞 | 代表什麼 | 不代表什麼 |
|---|---|---|
| `Measured` | 直接由輸入 timestamp、edge、duration 或 value 計算 | 不代表類比電壓或所有硬體條件都已驗證 |
| `Inferred` | 由多個觀察值推論 | 不代表只有一個可能原因 |
| `Reconstructed` | 依 decoded bytes 畫出的理想示意 | 不代表 LA 實際捕捉到同樣的每個 edge |
| `Hypothesis` | 值得排查的方向 | 不代表 root cause 已證明 |
| `Unavailable` | 輸入缺少必要證據，工具拒絕猜測 | 不代表數值為 0，也不代表硬體一定正常 |

## 什麼時候應該停止相信這份報告？

遇到以下任一情況，先修正輸入或取得外部證據，不要繼續堆疊推論：

- raw CSV 欄位不明確、timestamp 不單調、SCL/SDA 不是 0/1，或 parser 明確拒絕資料。
- capture 被截斷，缺少 START/STOP 或 reset/power transition。
- 報告出現 `Unavailable`，但你仍需要回答 timing、類比電氣或 live driver 狀態問題。
- device profile、board revision、datasheet 或 matching ELF 不明確。
- 只有一個 synthetic test data 或重建圖，沒有實際目標板 evidence。

這些不是失敗，而是正確的停損點：先補證據，再重新分析。
