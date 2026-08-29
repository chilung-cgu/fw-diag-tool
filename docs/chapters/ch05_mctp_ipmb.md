# MCTP／IPMB 伺服器管理協定解析

## 這個頁面在做什麼？

在伺服器與資料中心主機板中，基板管理控制器（Baseboard Management Controller；BMC）需要與 GPU、NIC、SSD 等設備通訊。
通訊協定有兩種：

- **MCTP**（管理元件傳輸協定；Management Component Transport Protocol；DMTF DSP0236）：新一代標準，支援 PLDM 感測器讀取與 SPDM 安全認證。
- **IPMB**（智慧平台管理匯流排；Intelligent Platform Management Bus；IPMI v2.0）：傳統標準，BMC 與衛星控制器（Satellite Controller）間的 I2C 匯流排。

## 怎麼操作？

1. 進入 GUI 第 5 頁 **「🌐 MCTP／IPMB 伺服器管理協定解析」**。
2. 在文字框中貼上十六進位位元組（Hex Dump；每行一個完整封包）。預設已填入範例資料。
3. 點擊 **「執行 MCTP／IPMB 伺服器管理協定解碼」** 按鈕。

## 怎麼看懂輸出結果？

### MCTP 封包解碼範例

輸入 `01 08 00 C0 01 00 02 01 00`，輸出會顯示：

| 欄位 | 值 | 白話解釋 |
|---|---|---|
| 標頭版本（Header Version） | 0x01 | MCTP v1.x 標準標頭 |
| 目的端點識別碼（Dest EID） | 0x08 | 目標設備的 Endpoint ID（例如 GPU 的 BMC） |
| 來源端點識別碼（Src EID） | 0x00 | 發送端 EID（通常是 BMC 自己） |
| 封包起訖（SOM / EOM） | True / True | 這是單一完整封包（不是分段傳輸） |
| 訊息類型（Msg Type） | PLDM | 訊息類型為 PLDM 感測器監控協定 |
| PLDM 命令（PLDM Command） | 平台監控回應（Platform Monitoring, Response；Cmd 0x01；CC 0x00） | 讀取感測器數值的回應；CC=0x00 表示成功 |

### IPMB 訊框解碼範例

輸入 `20 18 C8 81 00 01 7E`，輸出會顯示：

| 欄位 | 值 | 白話解釋 |
|---|---|---|
| 請求位址（Rq Addr） | 0x81 | 發送方（通常是 BMC）的 I2C 位址 |
| 回應位址（Rs Addr） | 0x20 | 接收方（Satellite Controller）的位址 |
| 網路功能（NetFn） | 應用請求（App；Request） | 功能類別為 Application，這是一筆請求 |
| 命令（Command） | 取得裝置識別碼（Get Device ID；Cmd 0x01） | 查詢設備型號與版本 |
| 狀態（Status） | 通過（OK） | Checksum 1/2 皆通過 |

### 常見問題排查

| 現象 | 可能原因 |
|---|---|
| Checksum 1 失敗（Checksum 1 FAIL） | 封包標頭資料損毀，可能是 I2C 訊號完整性問題 |
| Checksum 2 失敗（Checksum 2 FAIL） | 封包資料區損毀，可能是匯流排雜訊或設備回應錯誤 |
| 訊息類型（Msg Type）顯示未知（Unknown） | 可能是廠商自訂協定（VDPCI／VDIANA），需查規格書 |
| PLDM 完成碼（CC）不等於 0x00（PLDM CC != 0x00） | PLDM 回應了錯誤碼，檢查 CC 數值對照 DSP0240 規格 |
