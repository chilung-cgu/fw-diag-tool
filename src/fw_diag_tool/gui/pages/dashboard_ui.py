from __future__ import annotations

import streamlit as st

from fw_diag_tool import __version__


def render() -> None:
    st.header("韌體訊號與協定診斷套件 — 總覽")
    st.caption(
        f"⚡ fw-diag-tool v{__version__} — 專為韌體與嵌入式系統工程師打造的離線訊號、協定與崩潰轉儲診斷分析套件。"
    )

    st.info(
        "💡 **工具能力邊界聲明**：\n"
        "- 本工具主要分析已擷取的追蹤記錄（Trace）、日誌（Log）與暫存器傾印（Dump），不會主動連線或控制實體硬體。\n"
        "- 圖表與診斷報告能有效縮小除錯範圍，但無法取代示波器實體量測、晶片規格書（Datasheet）及目標板上的實體驗證。"
    )

    with st.expander("🚀 第一次使用？快速入門指引與場景導覽", expanded=False):
        st.markdown(
            "### 3 步快速上手流程\n\n"
            "1. **準備擷取資料**：從邏輯分析儀（如 Saleae）、串列埠終端（如 minicom/picocom）或系統日誌（dmesg/lspci）匯出 CSV、TXT 或十六進位資料。\n"
            "2. **切換至對應功能頁面**：於左側導覽列選擇目標協定（如 I2C/PMBus、SPI、PCIe、UART）或代碼產生工具。\n"
            "3. **載入資料並檢視報告**：可直接上傳檔案、貼上文字，或點擊「載入範例」體驗自動化診斷分析與下載 Markdown 報告。\n\n"
            "---"
        )
        st.markdown(
            "### 常見工作場景推薦起始頁面\n\n"
            "- **I2C / PMBus 匯流排通訊失敗、NACK、時鐘延展或死鎖**：推薦 **📊 I2C/PMBus 診斷** 或 **⚖️ 雙波形差分**。\n"
            "- **系統當機、Linux Kernel Panic 或 ARM HardFault**：推薦 **📟 UART Crash**。\n"
            "- **伺服器 BMC / IPMI / PLDM 封包分析與 Checksum 驗證**：推薦 **🌐 MCTP/IPMB**。\n"
            "- **PCIe 裝置無法識別、Link 降速或 AER 錯誤回報**：推薦 **🚀 PCIe AER**。\n"
            "- **Flash 讀寫異常、WREN 遺漏或 256B 跨頁覆蓋**：推薦 **⚡ SPI Flash**。\n"
            "- **撰寫 Linux 裝置樹、解析狀態暫存器或產生 C 驅動巨集**：推薦 **🌲 Device Tree**、**🎛 暫存器解碼** 或 **🛠 C Header 產生器**。\n"
            "- **新人培訓、故障模式排查練習或建立除錯心智模型**：推薦 **🏆 Fault Arena** 與 **📚 除錯 SOP**。"
        )

    st.subheader("🛠 功能模組總覽")

    st.markdown("#### 協定分析與波形")
    col1, col2, col3 = st.columns(3)
    with col1, st.container(border=True):
        st.markdown("##### 📊 I2C/PMBus 診斷")
        st.write("**說明**：解碼 CSV/raw trace，分析 timing、anomaly、chip 識別")
        st.write(
            "**支援格式**：Saleae Decoded CSV、Raw Digital CSV (100 kHz / 400 kHz)、Text Trace、.fwsession.json"
        )
        st.write(
            "**適用場景**：I2C/SMBus/PMBus 通訊失敗、NACK、時鐘延展 (Clock Stretching) 逾時、匯流排死鎖 (Bus Hang)、電源晶片狀態分析"
        )
    with col2, st.container(border=True):
        st.markdown("##### 🎨 I2C 封包模擬器")
        st.write("**說明**：自訂 I2C 傳輸規格，產生波形與 C driver code")
        st.write("**支援格式**：自訂 7-bit 位址、暫存器位移、讀寫長度、寫入資料 Payload")
        st.write(
            "**適用場景**：驅動開發前的封包行為模擬、i2ctransfer CLI 命令生成、Linux Kernel i2c_msg / C driver 程式碼範本"
        )
    with col3, st.container(border=True):
        st.markdown("##### ⚖️ 雙波形差分")
        st.write("**說明**：Golden vs Failing trace 比對")
        st.write("**支援格式**：兩個 Saleae Decoded CSV（正常板卡 Golden vs 故障板卡 Failing）")
        st.write(
            "**適用場景**：板卡 A/B 對比除錯、找出首次通訊分歧點（Timing Jitter、位址/資料 NACK 差異、長度不符）"
        )

    st.markdown("#### 系統協定")
    col4, col5, col6, col7 = st.columns(4)
    with col4, st.container(border=True):
        st.markdown("##### 📟 UART Crash")
        st.write("**說明**：Linux kernel panic / ARM HardFault crash dump 解析")
        st.write(
            "**支援格式**：文字日誌 (.txt / .log)、Linux dmesg / Call Trace、ARM Cortex-M 暫存器轉儲 (HFSR/CFSR/Stacked PC)"
        )
        st.write(
            "**適用場景**：Linux 核心當機 (Kernel Panic / Oops / NULL Pointer)、ARM 微控制器 HardFault (除以零、未對齊存取、非精確匯流排錯誤)"
        )
    with col5, st.container(border=True):
        st.markdown("##### 🌐 MCTP/IPMB")
        st.write("**說明**：伺服器管理協定封包解碼")
        st.write("**支援格式**：十六進位位元組字串 (Hex Bytes，以空白、逗號或分號分隔)")
        st.write(
            "**適用場景**：BMC 伺服器管理協定除錯、MCTP (DSP0236 / PLDM / SPDM) 封包解碼與順序驗證、IPMB (IPMI v2.0) 兩段 Checksum 校驗"
        )
    with col6, st.container(border=True):
        st.markdown("##### 🚀 PCIe AER")
        st.write("**說明**：PCIe config space 與進階錯誤報告")
        st.write(
            "**支援格式**：lspci -xxxx / -vvv 十六進位傾印、Linux dmesg AER 錯誤記錄、自訂 64+ bytes Hex Dump"
        )
        st.write(
            "**適用場景**：PCIe 裝置無法識別、Link 降速 (Gen4 -> Gen1)、進階錯誤回報 (AER Correctable/Uncorrectable/Fatal)、Malformed/Poisoned TLP 診斷"
        )
    with col7, st.container(border=True):
        st.markdown("##### ⚡ SPI Flash")
        st.write("**說明**：SPI NOR Flash 命令序列與異常偵測")
        st.write("**支援格式**：邏輯分析儀 SPI Decoded CSV (需含 timestamp, MOSI, MISO, CS/Enable)")
        st.write(
            "**適用場景**：SPI NOR Flash 讀寫異常、JEDEC ID 全 0xFF/0x00 排查、Page Program 遺漏 WREN (0x06)、Page Buffer (256B) 跨頁回繞覆蓋偵測"
        )

    st.markdown("#### 產生器與工具")
    col8, col9, col10 = st.columns(3)
    with col8, st.container(border=True):
        st.markdown("##### 🌲 Device Tree")
        st.write("**說明**：從拓撲定義產生 .dts/.dtsi")
        st.write("**支援格式**：YAML 格式的 I2C / MUX 匯流排與周邊裝置拓撲定義")
        st.write(
            "**適用場景**：Linux 系統移植與板級支援包 (BSP) 開發、自動產生標準 OpenBMC / Linux I2C Device Tree 節點"
        )
    with col9, st.container(border=True):
        st.markdown("##### 🎛 暫存器解碼")
        st.write("**說明**：Bitfield 解碼器支援自訂 YAML")
        st.write(
            "**支援格式**：十六進位暫存器數值 (如 0x18000)、內建/自訂 YAML 暫存器對映檔 (Register Map)"
        )
        st.write(
            "**適用場景**：硬體狀態暫存器欄位即時拆解、PMBus STATUS_WORD / PCIe AER 錯誤暫存器 bitfield 快速查閱"
        )
    with col10, st.container(border=True):
        st.markdown("##### 🛠 C Header 產生器")
        st.write("**說明**：暫存器定義轉 C macro")
        st.write("**支援格式**：YAML 暫存器與欄位定義檔")
        st.write(
            "**適用場景**：韌體/驅動開發中將暫存器定義自動轉換為符合規範的 C 語言 #define 位移、遮罩與讀改寫 (RMW) 巨集"
        )

    st.markdown("#### 學習與實驗")
    col11, col12 = st.columns(2)
    with col11, st.container(border=True):
        st.markdown("##### 🏆 Fault Arena")
        st.write("**說明**：20 個合成除錯案例")
        st.write("**支援格式**：內建 20 個經典案例一鍵載入（涵蓋 I2C、SPI、PCIe、UART、MCTP/IPMB）")
        st.write(
            "**適用場景**：初階工程師除錯實戰培訓、各類硬韌體故障模式（NACK, Timeout, Rollover, HardFault 等）演練與自動診斷比對"
        )
    with col12, st.container(border=True):
        st.markdown("##### 📚 除錯 SOP")
        st.write("**說明**：L1-L7 分層診斷模型")
        st.write("**支援格式**：互動式知識庫與對照手冊（無須輸入）")
        st.write(
            "**適用場景**：建立系統化除錯心智模型、依據 L1 (物理) 到 L7 (應用) 分層定位問題邊界、判斷各層所需量測工具與證據"
        )


__all__ = ["render"]
