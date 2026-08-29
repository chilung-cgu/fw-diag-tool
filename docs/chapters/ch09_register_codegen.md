# 暫存器 Bitfield 解碼與 C 標頭檔巨集產生（Register Decoder／C Header Codegen）

## 先看結論

第 9 頁用 register-map YAML 定義把 Raw Hex 展開成 Bitfield；第 10 頁使用同一類 YAML 產生 C `#define`、mask、position 與存取巨集。兩頁都在處理「輸入值依定義如何解讀」，不會讀取 live register，也不會替 driver 證明硬體副作用、並行安全或 MISRA 全部合規。

## 共用的 register-map YAML 契約

GUI 的預設檔來自 `src/fw_diag_tool/data/*.yaml`。目前可選的兩個內建檔是 `pmbus_standard.yaml` 與 `pcie_aer_registers.yaml`；CLI 則可將任何符合下表的 register-map YAML 路徑交給 `reg decode` 或 `gen c-header`。

| YAML 層級 | 欄位與格式 | 用途 |
|---|---|---|
| root | mapping，必須有非空 `registers` list | 一個 register catalog；root 不能直接是 list |
| register | `name`、`offset`；可選 `size`（8／16／32）、`reset`、`description`、`fields` | 定義 register 名稱、位移、寬度、reset 值與欄位集合 |
| field | `name`、`bits`（例如 `"15"` 或 `"5:4"`）；可選 `access`、`values`、`warning_values` | 定義 Bitfield 位置、存取權限、列舉值與警告值 |
| `access` | `RO`（唯讀）、`RW`（可讀寫）、`W1C`（寫 1 清除）；預設 `RW` | 決定解碼顯示與 C header 產生的 setter／clear mask |
| `values`／`warning_values` | enum mapping／整數 list | 把 field raw value 對應到語意；warning value 只代表需要注意，不是根因 |

`offset`、`bits`、enum key 與 reset 可用 YAML 整數或 `0x` 字串。已知 register 的 `value` 不可超過其 `size`；field 不可超過 register 寬度或彼此重疊；重複 register name／offset 會在載入或產生時拒絕，不會靜默覆蓋先前定義。未知欄位值則保留 raw value，不會替你猜一個 enum 意義。

### 可直接使用的範例檔案（Example files）

- `src/fw_diag_tool/data/pmbus_standard.yaml`：GUI 內建 PMBus map；可選 `STATUS_WORD`（16-bit）並用 Raw Hex `0x8400` 練習。
- `src/fw_diag_tool/data/pcie_aer_registers.yaml`：GUI 內建 PCIe AER map；可選 `UNCORRECTABLE_ERROR_STATUS`（32-bit）並用 `0x00040000` 觀察 `MALFORMED_TLP` warning value。
- `tests/test_codegen.py`：小型 register-map YAML 字串與輸出契約的可執行範例；適合對照自訂 `RW` 欄位與 enum macro。
- `tests/test_gui_packaging.py`：GUI 的 Raw Hex、內建 YAML 與錯誤邊界 smoke test；它是可重跑的契約檔，不是硬體 dump 上傳格式。

第 9／10 頁目前從套件內建 YAML 選單載入定義，沒有「上傳自訂 register YAML」的 GUI 控制項。要使用自己的 YAML，請走 CLI/API，並把實際 datasheet revision 與來源檔一併保存。

## 第 9 頁：晶片暫存器 Bitfield 解碼器

### 操作步驟

1. 進入 GUI 第 9 頁 **「🎛 晶片暫存器 Bitfield 解碼器」**。
2. 從 **「選擇預設暫存器定義檔」** 選 `PMBus 標準狀態暫存器（PMBus STATUS_WORD）` 或 PCIe AER map。
3. 在 **「選擇暫存器」** 選 `STATUS_WORD`，於 **「輸入暫存器原始十六進位值（Raw Hex）」** 輸入 `0x8400`。
4. 讀取欄位表的 Bit Range、Field、Value、Access、Meaning，以及下方 `Unmapped bits`。Raw Hex 不是一份自動上傳的檔案；它是你從 `i2cget`、`devmem2`、driver log 或其他 readback 證據取得後貼入的整數。

### `STATUS_WORD = 0x8400` 的預期解讀

`0x8400` 在 16-bit `STATUS_WORD` 中會使 bit 15 與 bit 10 為 1。表格中的中文先寫可讀意義，括號保留 YAML／報告會用到的英文 token：

| 位元範圍（Bit Range） | 欄位（Field） | 值（Value） | 存取權限（Access） | 意義（Meaning） |
|---|---|---|---|---|
| 15 | `VOUT_FAULT` | `0x1` | `RO` | ⚠ 發生 VOUT 故障／警告（VOUT Fault/Warning occurred） |
| 14 | `IOUT_FAULT` | `0x0` | `RO` | 正常（Normal） |
| 10 | `TEMPERATURE` | `0x1` | `RO` | ⚠ 過溫警報（Overtemperature Alarm） |

這張表是 register-map YAML 對 Raw Hex 的計算結果（Reconstructed／Source-provided semantics）。它證明輸入值在定義中對應哪些 bits，不證明該值是在正確 bus、正確時間或沒有 side effect 的情況下從目標硬體讀回。

請不要把 `STATUS_WORD.VOUT_FAULT` 的一般 VOUT 故障／警告語意縮寫成特定故障；`輸出過電壓故障（Vout Overvoltage Fault）` 是 `STATUS_BYTE.VOUT_OV` 的另一個 field 意義，必須依選到的 register 與 datasheet 判讀。

### 解碼輸出怎麼讀？

| 輸出 | 中文解釋 | 下一步 |
|---|---|---|
| Field／Value／Meaning | 依 `bits`、enum map 與 warning list 展開的欄位語意 | 回 datasheet 確認 bit polarity、revision 與 command context |
| Access | `RO`、`RW` 或 `W1C` | 決定後續讀寫策略；不能因表格顯示 `RW` 就忽略硬體 access rule |
| `Unmapped bits` | YAML 沒有描述的 raw bits | 回 datasheet 補齊或確認 reserved bits；不要把 unmapped 當成 0 |
| 值寬度錯誤 | 例如 8-bit register 輸入 `0x100` | 先確認選到的 register、width 與 readback 是否對應 |

CLI 解碼同一個內建 map 的方式：

```bash
uv run fw-diag reg decode src/fw_diag_tool/data/pmbus_standard.yaml STATUS_WORD 0x8400
```

CLI 也接受 register name 或 offset（例如 `STATUS_WORD` 或 `0x79`）；輸入值必須是整數或 `0x` 開頭的十六進位字串。未知 name 會保留 `Unknown / Custom Register` 與 unmapped bits，這不是自動辨識晶片型號。

## 第 10 頁：C 語言 Register 巨集產生器

### 操作步驟

1. 進入 GUI 第 10 頁 **「🛠 C 語言 Register 巨集產生器」**。
2. 在 **「選擇 YAML 範本」** 選 `pmbus_standard.yaml` 或 `pcie_aer_registers.yaml`。
3. 在 **「模組名稱（Module Name）」** 輸入以英文字母開頭的名稱，例如 `PMBUS_REGS`；產生檔名會是 `pmbus_regs.h`。
4. 檢視可編輯的 C header 起始模板，再按下載按鈕。GUI 會以 `<stdint.h>` 與固定寬度 unsigned 型別產生 macros，但不會產生 MMIO pointer、volatile access、lock 或 interrupt/thread synchronization。

CLI 產生同一份 PMBus header 的範例：

```bash
uv run fw-diag gen c-header \
  src/fw_diag_tool/data/pmbus_standard.yaml \
  --out pmbus_regs.h \
  --name PMBUS_REGS
```

### 產物中的 macro 類型

產生器對每個 field 都會輸出 position、mask 與 `_GET`；是否有 setter 或 W1C mask 由 YAML 的 `access` 決定：

| Access | 產生的內容 | 白話與風險 |
|---|---|---|
| `RO`（唯讀） | `POS`、`MSK`、`GET` | 可解碼但不產生 `_SET`；不要自行對唯讀／read-clear register 做 RMW |
| `RW`（可讀寫） | `POS`、`MSK`、`GET`、`SET` | `_SET` 是 read-modify-write；需保留 reserved bits，並依 driver concurrency policy 保護 |
| `W1C`（寫 1 清除） | `POS`、`MSK`、`GET`、`W1C_MASK` | 產物明確不產生 `_SET`；直接寫 mask 前要確認其他 bits、side effect 與硬體規格 |

代表性輸出如下；實際名稱與 mask 以 YAML 為準：

```c
#define REG_STATUS_WORD_OFFSET                 (0x0079U)
#define REG_STATUS_WORD_VOUT_FAULT_POS        (15U)
#define REG_STATUS_WORD_VOUT_FAULT_MSK        (0x00008000U)
#define REG_STATUS_WORD_VOUT_FAULT_GET(val)   (((val) & REG_STATUS_WORD_VOUT_FAULT_MSK) >> REG_STATUS_WORD_VOUT_FAULT_POS)

/* RW field 才會有 SET；這個 macro 會保留其他 bits，再寫入新值。 */
#define REG_DEVICE_CTRL_ENABLE_POS            (0U)
#define REG_DEVICE_CTRL_ENABLE_MSK            (0x00000001U)
#define REG_DEVICE_CTRL_ENABLE_SET(reg, val)  (((reg) & ~REG_DEVICE_CTRL_ENABLE_MSK) | (((uint32_t)(val) << REG_DEVICE_CTRL_ENABLE_POS) & REG_DEVICE_CTRL_ENABLE_MSK))

/* W1C：寫入 1 清除；不可使用讀取-修改-寫入（read-modify-write）。 */
#define REG_UNCORRECTABLE_ERROR_STATUS_MALFORMED_TLP_MSK (0x00040000U)
#define REG_UNCORRECTABLE_ERROR_STATUS_MALFORMED_TLP_W1C_MASK (REG_UNCORRECTABLE_ERROR_STATUS_MALFORMED_TLP_MSK)
```

`reset` 只有在 YAML 明確提供時才產生 `REG_<NAME>_RESET`；enum map 會產生 `VAL_<REGISTER>_<FIELD>_<LABEL>` 常數。名稱會轉成大寫 C identifier；若模組名稱清理後不是以英文字母開頭，GUI／CLI 會拒絕，避免輸出不可攜的 include guard。

固定寬度 `uint32_t` cast 可降低 integer promotion 與 signed shift 的風險，但單一 cast 不足以證明整份 header 符合 MISRA-C。產物是可 review 的 C header template，不是已驗證的 production driver。

## 產生後的驗證順序

1. 先鎖定 datasheet／register map revision，核對每個 offset、register width、bit range、polarity、reserved bits、`RO`／`RW`／`W1C` 與 reset value。
2. 用內建範例重現：PMBus `STATUS_WORD`／`0x8400` 應看到 bit 15、10 的 warning；PCIe AER `UNCORRECTABLE_ERROR_STATUS`／`0x00040000` 應對應 `MALFORMED_TLP` warning value。
3. 將產生的 header 交給目標 compiler 編譯，開啟專案既定 warnings、C standard 與 static analysis／MISRA checker；先檢查 macro precedence、型別寬度與 include guard。
4. 在 driver review 中分開處理 MMIO／I2C read/write、volatile ownership、RMW atomicity、W1C side effect、ISR／thread concurrency 與 reserved bits；這些不是 code generator 能單獨證明的。
5. 在安全的硬體測試流程中做 readback／clear 行為驗證，保存 raw register evidence、命令 context、時間戳與 board revision。

## 證據邊界與常見問題

| 觀察 | 能回答什麼 | 還需要什麼 |
|---|---|---|
| YAML + Raw Hex 解碼表 | 這個整數依目前 map 落在哪些 Bitfield、enum 與 warning value | 真正的 readback 來源、bus／command context、datasheet revision |
| 產生的 C header | 可重現的 offset／mask／position／access macro 起始碼 | compiler、static analysis、driver access policy、hardware side effect 測試 |
| `Unmapped bits` | 目前 YAML 沒有定義的 bits | reserved-bit 規則或補充 register map；不要靜默忽略 |
| 產生成功 | 輸入符合 parser／generator 的結構與邊界 | 不能直接推出晶片身份、live register 狀態或 root cause |

| 症狀 | 原因與處理 |
|---|---|
| YAML 載入失敗 | root 不是 mapping、缺少非空 `registers` list、欄位型別錯誤或重複 name／offset；先用內建檔與最小 schema 對照 |
| Raw Hex 被拒絕 | 非整數、負值、超過 `0xFFFFFFFF`，或超過已選 register 的 8／16／32-bit width；確認 register 與 readback width |
| 沒有 `_SET` | 欄位是 `RO` 或 `W1C`；這是避免誤用 RMW 的設計，不是產生失敗 |
| C header 名稱錯誤 | module／register／field 清理後無法形成以字母開頭的 C identifier；改用如 `PMBUS_REGS` 的穩定名稱 |
| warning 被當成 root cause | warning value 只是 map 對 raw bits 的標記；仍要補來源 readback、時間序列、driver log 與硬體條件 |

共通的證據層級與寫入安全限制，請參閱[能力、證據層級與限制](../LIMITATIONS.md)。
