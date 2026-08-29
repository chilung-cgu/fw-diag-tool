# PCIe Config Space、AER 嚴重錯誤與 Link 降級排查

## 這個頁面在做什麼？

PCIe 設備（GPU、NVMe SSD、網卡）在開機時，BIOS/UEFI 會讀取每個設備的 4KB 設定空間
（Configuration Space），以了解設備身份、BAR 記憶體映射、Capability 鏈表與 Link 速度。
設備異常時，Linux Kernel 會透過 AER（Advanced Error Reporting，進階錯誤回報）記錄錯誤詳情。
本工具接受 `lspci -xxxx` 輸出或 `dmesg` AER 錯誤，協助你整理可解析欄位與下一個排查方向；
它不會從 partial dump 猜出缺失的 Config Space，也不會單獨宣稱硬體 root cause。

## 怎麼操作？

1. 進入 GUI 第 7 頁 **「🚀 PCIe 設定空間（Config Space）與 AER 診斷」**。
2. 選擇輸入方式：
   - **貼上 lspci -xxxx**：分析設備身份、BAR、Capability 鏈表與 Link 速度。
   - **貼上 dmesg AER Log**：解析目前支援的 PCIe Bus Error 與 TLP header 欄位，列出可能排查方向；
     可直接貼上 `examples/data/pcie_aer_dmesg.log`。
3. 點擊 **「執行 PCIe 分析」** 按鈕。
4. 先查看資料品質限制與 BDF，再閱讀 Link／AER 摘要；若要回答 LTSSM、眼圖或電氣問題，
   另保存完整 dump、kernel log 與硬體量測。

## 怎麼看懂輸出結果？

### 設備概覽（Device Overview）

| 欄位 | 意義 | 白話解釋 |
|---|---|---|
| Vendor / Device ID（廠商／裝置識別碼） | 0x10EE / 0x7024 | 廠商是 Xilinx，型號 7024 |
| Class（類別） | Processing Accelerator | 這是處理加速器；括號中的英文是 lspci 原始分類 |
| Header Type（標頭類型） | TYPE_0_ENDPOINT | 這是端點裝置，不是 Switch／Root Port |
| Standard Capabilities（標準能力） | 1 | 有 1 個標準 Capability，例如 PCIe Capability |
| Extended Capabilities（延伸能力） | 1 | 內建範例在位移 `0x100` 有 AER Extended Capability |

### Link 降級偵測（Link Health）

Link capability 與 negotiated status 的差異可指出「目前沒有跑到最大能力」，但不會單獨證明原因。
請把它當成優先級訊號，並以拓撲、供電、reset、BIOS 設定、kernel log 與實體量測區分假設。

| 欄位 | 意義 | 白話解釋 |
|---|---|---|
| Maximum Capable（最大能力） | 16.0 GT/s (Gen4) x16 | 設計規格支援 PCIe Gen4，16 條 Lane |
| Negotiated Status（協商狀態） | 2.5 GT/s (Gen1) x1 | 實際只跑 PCIe Gen1，1 條 Lane |
| Link Health（Link 健康度） | DEGRADED | 目前速度／寬度低於最大能力；不是單一根因結論 |

**降級的常見原因與排查順序**：

| 優先順序 | 排查步驟 | 白話解釋 |
|---|---|---|
| 1 | 檢查 PCIe 金手指 | 確認接點沒有髒污、氧化或刮傷，並保留更換／重插結果 |
| 2 | 檢查 Riser 轉接卡 | 確認 PCIe Switch 或 Retimer 正常供電、reset 與拓撲連接 |
| 3 | 檢查 100MHz 差分時脈 | 用示波器量測 REFCLK 的 jitter；本工具不能代替眼圖或類比量測 |
| 4 | 檢查 BIOS 設定 | 確認 BIOS 沒有手動限制 Link Speed 或 Link Width |

### AER TLP Header Log（TLP 標頭記錄）解碼

當 PCIe 發生 Completion Timeout 或 Malformed TLP 錯誤時，設備可能記錄肇事 TLP 封包的
4DW（4 Double Words = 16 bytes）Header Log。工具會自動拆解目前輸入中可取得的欄位；
缺少 DW 時應保留 `Unavailable`，不能把填補值當成硬體回報：

| 欄位 | 意義 |
|---|---|
| TLP Packet Type（TLP 封包類型） | Memory Read 3DW / Memory Write 4DW / Config Read 等 |
| Length（長度） | 資料長度（DW 數量 x 4 = bytes） |
| Target Address（目標位址） | 記憶體讀寫的目標位址 |
| Requester BDF（請求端 BDF） | 發出請求的設備（Bus:Device.Function） |
| Traffic Class（流量類別） | 服務品質等級（TC0~TC7） |

### 常見 AER 錯誤排查 SOP

| 錯誤類型 | 白話解釋 | 排查方向 |
|---|---|---|
| **Completion Timeout（完成逾時）** | Request 沒在規定時間取得 Completion | 檢查 Requester／Completer 狀態、路由、timeout 設定與先前錯誤；不能直接等同設備 Hang |
| **Unsupported Request（不支援的請求）** | Completer 回報該 request 不受支援 | 檢查 address／BAR、權限、request type 與裝置狀態 |
| **Malformed TLP（格式錯誤 TLP）** | 接收端判定 TLP 格式不合法 | 需要更多 header、Requester 與 link evidence 才能定位來源 |
| **Poisoned TLP（毒化 TLP）** | TLP 帶有 poisoned indication | 追蹤 poison 產生端與資料路徑；不一定是主記憶體 ECC |
| **Surprise Down（非預期 Link 中斷）** | Link 非預期離開正常運作狀態 | 檢查 power、reset、hot-plug、link log 與實體連接等多種可能原因 |

> **說明：**
>
> 本頁分析 Config Space、`lspci` 與 AER log，不是 PCIe protocol analyzer、LTSSM trace 或高速差分電氣量測工具。

## 證據解讀與停損點

- `lspci -xxxx` 只代表該次 dump 可讀到的 Config Space；partial dump、缺少 Capability 或填零欄位都要先標成資料限制。
- `Captured TLP Header` 只證明 kernel log 捕獲到 header，不代表已定位唯一 Requester、Completer 或硬體 root cause。
- Link `DEGRADED` 是 capability 與 negotiated status 的差異；要判斷是接觸、REFCLK、reset、BIOS 或 endpoint 狀態，必須補外部證據。

## 測試資料

- **Config Space**：`examples/data/pcie_aer_lspci.txt`，用於設備身份、Capability 與 Link 欄位教學。
- **Linux dmesg AER**：`examples/data/pcie_aer_dmesg.log`，包含 `MalformedTLP` 事件與 `TLP Header: 00000001 0100000f fe000000 00000000`。
- dmesg 範例預期在報告中看到 `Captured TLP Header`；這只代表 kernel log 捕獲到 header，不等於已定位唯一硬體 root cause。
