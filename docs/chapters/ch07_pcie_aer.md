# 第七章：PCIe Config Space、AER 嚴重錯誤與 Link 降級排查

## 這個頁面在做什麼？

PCIe 設備（GPU、NVMe SSD、網卡）在開機時，BIOS/UEFI 會讀取每個設備的 4KB Configuration Space，
了解設備身份、BAR 記憶體映射、Capability 鏈表與 Link 速度。
當設備異常時，Linux Kernel 會透過 AER (Advanced Error Reporting) 機制記錄錯誤詳情。
這個工具讓你貼上 `lspci -xxxx` 輸出或 `dmesg` AER 錯誤，自動解析並提供排查指引。

## 怎麼操作？

1. 進入 GUI 第 7 頁 **「🚀 PCIe Config & AER 診斷」**。
2. 選擇輸入方式：
   - **貼上 lspci -xxxx**：分析設備身份、BAR、Capability 鏈表與 Link 速度。
   - **貼上 dmesg AER Log**：分析 PCIe Bus Error 的 TLP 封包詳情與 Root Cause。
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

這是最重要的診斷功能之一！

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
| **Completion Timeout** | 發出讀取請求但等不到回應 | 檢查目標設備是否 Hang 或未正確初始化 |
| **Unsupported Request** | 收到不支援的存取 | 檢查 BAR 映射是否正確、MSE 是否開啟 |
| **Malformed TLP** | 封包格式違規 | 檢查 Max Payload Size 設定是否一致 |
| **Poisoned TLP** | 資料帶有 ECC 錯誤標記 | 排查上游主記憶體的 ECC 錯誤來源 |
| **Surprise Down** | 連線無預警斷開 | 檢查供電、PERST# 訊號或實體接觸 |