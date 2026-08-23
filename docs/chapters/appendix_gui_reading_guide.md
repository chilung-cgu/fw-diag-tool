# 附錄 B：12 個 GUI 頁面的閱讀地圖

這份文件回答一個很實際的問題：**我現在看到的頁面、表格或圖，究竟代表什麼？下一步要做什麼？**

`JUNIOR_FW_GUIDE.md` 保持目錄和學習路線；本附錄集中放「每一頁的輸入、輸出、不能證明什麼、第一個練習」。因此未來增加功能時，可以新增章節並更新這張地圖，不必把總指南變成一份幾百頁的單一檔案。

## 先做一次完整導覽（建議第一次使用）

1. 在 macOS Terminal 執行 `uv sync --all-extras`，再執行 `uv run fw-diag gui`。
2. 開啟 `http://127.0.0.1:8501`，先選第 1 頁，按「載入內建測試波形」。
3. 先讀「資料證據與限制」，再看 KPI；不要一開始只看綠色或紅色。
4. 在交易列表選一筆 transaction，依序看 Waveform、Anomalies、時序圖、交易列表與 Markdown。
5. 另準備一份 raw digital `Time [s],SCL,SDA` CSV，切換輸入模式後再分析一次。前一次是 decoded/reconstructed 證據，後一次才有機會量到 digital edge timing。
6. 下載 Markdown 報告和 session JSON。session 不包含原始檔，原始 capture 必須另外保存。
7. 再依下表逐頁做一個最小練習；每一頁都回答「輸入是什麼、看到了什麼、還不知道什麼、要用什麼資料驗證」。

## 一頁一頁看懂

### 1. I2C / SMBus / PMBus 診斷與波形檢視

| 項目 | 說明 |
|---|---|
| 放入什麼 | decoded analyzer CSV/text trace，或 raw digital `Time/SCL/SDA` transition CSV。 |
| 先看什麼 | 資料品質面板、總交易數、ACK/NACK、frequency sample count，再看波形與 device health。 |
| 圖表在回答什麼 | Frequency 圖回答「有多少可靠 timing samples」；Timeline 回答「哪個 device 在何時被存取、ACK 狀態如何」。 |
| 不能證明什麼 | decoded table 不能證明類比電壓、rise/fall、pull-up 或 PCIe/I2C signal integrity；address 候選不是確定型號。 |
| 下一步 | 把 NACK 的位置對回 driver retry、power/reset、MUX 與 datasheet；需要頻率或 SCL low 延長時，補 raw digital capture。 |

注意：Read 最後由 controller 發出的 NACK 是正常讀取終止，不應當成 slave 失敗。aggregate row 只有一個 ACK/NACK 時，工具會標記 ACK 歸屬不明，不會替每個 byte 猜 ACK。

### 2. I2C 封包模擬器與驅動產生

| 項目 | 說明 |
|---|---|
| 放入什麼 | 7-bit address、operation、register offset、write bytes 或 read length。 |
| 先看什麼 | 理想 START/address/data/ACK/STOP 示意，再讀生成的 Linux i2c-dev、OpenBMC、STM32 HAL、Arduino 範例。 |
| 它的用途 | 練習 7-bit 與 8-bit address、register pointer、read/write 交易順序，建立 driver 骨架。 |
| 不能證明什麼 | 這是 reconstructed/模板輸出，不是實際裝置回應；Read 的資料仍要由硬體、driver 或 capture 提供。 |
| 下一步 | 用 datasheet 的 register transaction 對照每一個 byte，先在不接硬體的情況下 review API，再由公司測試板驗證。 |

### 3. Golden vs Failing Waveform Diff

| 項目 | 說明 |
|---|---|
| 放入什麼 | 一份正常 Golden 與一份故障 Failing 的 decoded I2C CSV。 |
| 先看什麼 | 是否為 insufficient evidence、第一個 divergence、mismatch type、兩邊同一筆交易的 address/direction/data/ACK。 |
| 它的用途 | 把「正常與故障差在哪一筆」縮小，幫助建立下一個可區分假設。 |
| 不能證明什麼 | 兩份空檔或解析失敗不能證明 100% identical；協定相同也不代表類比訊號或 firmware state 相同。 |
| 下一步 | 針對第一個差異補同一時間窗的 raw edge、driver log 或 status register，不要只比較最後一筆錯誤。 |

### 4. UART Crash & HardFault 分析

| 項目 | 說明 |
|---|---|
| 放入什麼 | Linux kernel panic / dmesg，或 ARM Cortex-M HardFault log。 |
| 先看什麼 | Linux 的 RIP、CR2、Call Trace；Cortex-M 的 HFSR/CFSR 與 stacked PC/LR。 |
| 它的用途 | 把原始 crash 轉成可讀欄位，指出 NULL dereference、DIVBYZERO、UNALIGNED 等候選方向。 |
| 不能證明什麼 | 沒有 matching `vmlinux`/ELF、symbol、完整 register dump 時，不能宣稱確切 source line 或唯一 root cause。 |
| 下一步 | 保存原始 log，使用相同 build 的 `addr2line`/debug symbols，對照 source、commit 與重現步驟。 |

### 5. MCTP / IPMB 伺服器協定解析

| 項目 | 說明 |
|---|---|
| 放入什麼 | 每行一個完整的 hex frame；可包含 MCTP、PLDM/SPDM 類型或 IPMB frame。 |
| 先看什麼 | parser 判定的 protocol、header、payload、checksum 與 frame count。 |
| 它的用途 | 學習 header、source/destination、message type 與 checksum 的關係。 |
| 不能證明什麼 | 目前不是完整 DSP0236/PLDM/SPDM conformance checker；未知或 checksum-invalid frame 不能當成成功訊息。 |
| 下一步 | 用規格逐 byte 重算 checksum，確認 transport binding、endpoint ID 與實際平台設定。 |

### 6. Device Tree (`.dts`) 產生器

| 項目 | 說明 |
|---|---|
| 放入什麼 | bus number、MUX address/compatible、clock-frequency 與每個 device 的 addr/channel/name/compatible。 |
| 先看什麼 | 產生的 node hierarchy、reg、compatible、clock-frequency 與 MUX channel。 |
| 它的用途 | 產生可 review 的起始 `.dtsi` 模板，練習 hardware topology 如何映射到 Linux DT。 |
| 不能證明什麼 | generator 不知道你的 schematic、board variant 或 kernel binding 是否正確；它不會替你猜地址。 |
| 下一步 | 用對應 kernel binding、`dtc`、`dt-schema` 與實際 schematic review；確認 32-bit cell 與合理 bus speed。 |

### 7. PCIe Config & AER 診斷

| 項目 | 說明 |
|---|---|
| 放入什麼 | `lspci -xxxx`/config dump，或 Linux dmesg AER log。 |
| 先看什麼 | Vendor/Device ID、capability chain、link speed/width、AER status 與 TLP header log。 |
| 它的用途 | 先確認「設備是誰、link 是否降級、AER 報了哪一類錯」。 |
| 不能證明什麼 | config/AER dump 不能量 PCIe eye、jitter、SI、LTSSM 全部過程，也不能只靠一個 AER bit 宣稱硬體 root cause。 |
| 下一步 | 對照 `lspci -vv`、kernel log、slot/riser/power/reset 與平台設計；需要電氣證據時使用專用 PCIe analyzer/示波器。 |

### 8. SPI Flash 協定診斷

| 項目 | 說明 |
|---|---|
| 放入什麼 | 含明確 `Time`、`MOSI`、`MISO`、`CS/Enable` 的 decoded SPI CSV；CS active-low。 |
| 先看什麼 | transaction 數、JEDEC ID、WREN/WEL 狀態、Page Program/erase、data-quality（truncated/overlong）。 |
| 不能證明什麼 | 沒有 raw SCLK edge 時，不能驗 CPOL/CPHA、bit timing、setup/hold 或 signal integrity；異常數為規則命中數，不是完整 compliance。 |
| 格式規則 | `0x20` 是明確十六進位；全數字裸 token（例如 `20`）按十進位解析；`AA` 這類含 A-F 的裸 token 可按十六進位。格式不確定時請加 `0x`。 |
| 下一步 | 以該 flash datasheet 確認 command width/page size/WEL/WIP，再擴大 capture window 包含 WREN 與 status read。 |

### 9. 晶片暫存器 Bitfield 解碼器

| 項目 | 說明 |
|---|---|
| 放入什麼 | 內建或已 review 的 YAML register map，以及 raw register value。 |
| 先看什麼 | register name、bit range、mask、decoded value、meaning/warning。 |
| 它的用途 | 練習從 raw hex 回到 datasheet 的 bitfield；把 status bit 與 firmware branch 對起來。 |
| 不能證明什麼 | 只有 address/raw value 不足以確認 register 來源；錯誤 board variant 或過時 YAML 會產生錯誤解釋。 |
| 下一步 | 對照同一版本 datasheet/header，檢查 register width、access、W1C 與 reserved bits，再寫入任何硬體前先做 code review。 |

### 10. C 語言 Register 巨集產生器

| 項目 | 說明 |
|---|---|
| 放入什麼 | 已通過 schema review 的 YAML register map與 module name。 |
| 先看什麼 | `SHIFT`、`MASK`、`GET`；RW 欄位的 setter；W1C 欄位的 direct clear mask。 |
| 重要限制 | 目前 access token 只接受 `RO`、`RW`、`W1C`。RO 不產 setter；W1C 不產一般 read-modify-write `_SET`，避免把 status clear 誤當普通寫入。 |
| 不能證明什麼 | 產出的 header 仍須由目標 compiler、coding standard、static analyzer 與 datasheet review 驗證。 |
| 下一步 | 在 host 先 compile 一個最小使用例，再檢查 volatile/MMIO、reserved bit、W1C/W0C 與 atomicity。 |

### 11. Junior FW Fault Arena

| 項目 | 說明 |
|---|---|
| 放入什麼 | 內建 synthetic Case 01～20；不需要公司 capture。 |
| 建議玩法 | 先遮住解答，寫下 observed symptom、兩個 hypotheses、最能區分它們的下一個量測；再打開 SOP 對答案。 |
| 不能證明什麼 | synthetic case 不是實際板卡、真實 driver 或公司 root cause 的證據。 |
| 下一步 | 將相同方法套到真實 capture：先保存原始資料，再把每個假設對應到一個可重現 test。 |

### 12. 韌體除錯指南與 SOP

| 項目 | 說明 |
|---|---|
| 先看什麼 | L1～L7 分層、Measured/Inferred/Reconstructed/Hypothesis/Unavailable 詞彙與七步 SOP。 |
| 它的用途 | 決定下一個要收集的是電源/edge、frame、protocol、driver log、reset state、DT 或產品語意。 |
| 不能證明什麼 | SOP 是思考框架，不是自動 root-cause oracle；每個結論仍要有來源與下一個驗證。 |
| 下一步 | 在 Markdown 報告中分開記錄 observed facts、interpretation、alternative hypotheses、discriminating test、未驗證限制。 |

## 圖表的共同閱讀順序

不論是哪一頁，看到圖表時固定問五個問題：

1. **資料從哪裡來？** raw edge、decoded CSV、log、YAML，還是 synthetic case？
2. **每個軸／欄位的單位是什麼？** 秒、kHz、byte、7-bit address、bit range 不可混用。
3. **樣本數和品質在哪裡？** `Unavailable`、`N/A`、`truncated`、`ambiguous` 都是結果的一部分。
4. **這是 measured、inferred 還是 reconstructed？** 顏色與漂亮的圖不會提升證據等級。
5. **下一個能證偽假設的動作是什麼？** 回到原始 capture、datasheet、driver log 或實際量測。

## 文件怎麼維護才不會失控

- `docs/JUNIOR_FW_GUIDE.md`：只保留啟動方式、12 頁索引、閱讀路線與文件結構。
- `docs/chapters/chNN_*.md`：每個功能自己的操作、欄位、範例與限制。
- `appendix_chart_guide.md`：I2C 圖表和 evidence-level 的深度判讀。
- 本檔：跨頁面的「我現在看到什麼」地圖；新增 GUI 頁面時加一個小節，不把所有細節複製進總指南。
- `docs/LIMITATIONS.md`：只放跨模組限制與不能宣稱的能力。

這樣 junior 可以先用本檔定位，再進入單一章節深入；資深工程師則可以直接跳到章節或限制文件，不需要先閱讀整份總指南。
