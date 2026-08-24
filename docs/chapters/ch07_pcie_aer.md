# PCIe Config Space、AER 嚴重錯誤與 Link 降級排查

## 這個頁面在做什麼？

PCIe 設備（GPU、NVMe SSD、網卡）在開機時，BIOS/UEFI 會讀取每個設備的 4KB Configuration Space，
了解設備身份、BAR 記憶體映射、Capability 鏈表與 Link 速度。
當設備異常時，Linux Kernel 會透過 AER (Advanced Error Reporting) 機制記錄錯誤詳情。
這個工具讓你貼上 `lspci -xxxx` 輸出或 `dmesg` AER 錯誤，自動解析並提供排查指引。

## 怎麼操作？

1. 進入 GUI 第 7 頁 **「🚀 PCIe Config & AER 診斷」**。
2. 選擇輸入方式：
   - **貼上 lspci -xxxx**：分析設備身份、BAR、Capability 鏈表與 Link 速度。
   - **貼上 dmesg AER Log**：解析目前支援的 PCIe Bus Error 與 TLP header 欄位，列出可能排查方向。
3. 點擊 **「執行 PCIe 分析」** 按鈕。

## 怎麼看懂輸出結果？

### 設備概覽 (Device Overview)

| 欄位 | 意義 | 白話解釋 |
|---|---|---|
| Vendor / Device ID | 0x10EE / 0x7024 | 廠商是 Xilinx，型號 7024 |
| Header Type | TYPE_0_ENDPOINT | 這是終端設備（不是 Switch/Root Port） |
| Standard Capabilities | 1 | 有 1 個標準 Capability（如 PCIe Capability） |
| Extended Capabilities | 0 | 沒有 Extended Capability（如 AER） |

### Link 降級偵測 (Link Health)

Link capability 與 negotiated status 的差異可指出「目前沒有跑到最大能力」，但不會單獨證明原因。

| 欄位 | 意義 | 白話解釋 |
|---|---|---|
| Maximum Capable | 16.0 GT/s (Gen4) x16 | 設計規格支援 PCIe Gen4，16 條 Lane |
| Negotiated Status | 2.5 GT/s (Gen1) x1 | 實際只跑 PCIe Gen1，1 條 Lane |
| Link Health | DEGRADED | 速度嚴重降級！ |

**降級的常見原因與排查順序**：

| 優先順序 | 排查步驟 | 白話解釋 |
|---|---|---|
| 1 | 檢查 PCIe 金手指 | 拔出來看看有沒有髒污、氧化或刮傷 |
| 2 | 檢查 Riser 轉接卡 | 確認轉接卡上的 PCIe Switch 或 Retimer 正常供電 |
| 3 | 檢查 100MHz 差分時脈 | 用示波器量測 REFCLK 是否有過大 Jitter |
| 4 | 檢查 BIOS 設定 | 確認 BIOS 沒有手動限制 Link Speed |

### AER TLP Header Log 解碼

當 PCIe 發生 Completion Timeout 或 Malformed TLP 錯誤時，
設備會記錄肇事 TLP 封包的 4DW (4 Double Words = 16 bytes) Header Log。
工具會自動拆解為：

| 欄位 | 意義 |
|---|---|
| TLP Packet Type | Memory Read 3DW / Memory Write 4DW / Config Read 等 |
| Length | 資料長度（DW 數量 x 4 = bytes） |
| Target Address | 記憶體讀寫的目標位址 |
| Requester BDF | 發出請求的設備 (Bus:Device.Function) |
| Traffic Class | 服務品質等級 (TC0~TC7) |

### 常見 AER 錯誤排查 SOP

| 錯誤類型 | 白話解釋 | 排查方向 |
|---|---|---|
| **Completion Timeout** | Request 沒在規定時間取得 Completion | 檢查 Requester/Completer 狀態、路由、timeout 設定與先前錯誤；不能直接等同設備 Hang |
| **Unsupported Request** | Completer 回報該 request 不受支援 | 檢查 address/BAR、權限、request type 與裝置狀態 |
| **Malformed TLP** | 接收端判定 TLP 格式不合法 | 需要更多 header、Requester 與 link evidence 才能定位來源 |
| **Poisoned TLP** | TLP 帶有 poisoned indication | 追蹤 poison 產生端與資料路徑；不一定是主記憶體 ECC |
| **Surprise Down** | Link 非預期離開正常運作狀態 | 檢查 power、reset、hot-plug、link log 與實體連接等多種可能原因 |

> **說明：**
>
> 本頁分析 Config Space、`lspci` 與 AER log，不是 PCIe protocol analyzer、LTSSM trace 或高速差分電氣量測工具。
