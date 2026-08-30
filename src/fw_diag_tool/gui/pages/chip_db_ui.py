"""I2C / SMBus / PMBus 晶片資料庫瀏覽器（Chip Database Browser）。

提供常見 I2C / SMBus / PMBus 週邊晶片目錄檢視、7-bit 位址反向查詢、
0x00-0x7F 全位址空間分佈地圖與韌體工程實戰指引。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool.gui.shared import render_guide_expander, render_page_footer
from fw_diag_tool.i2c.chip_db import (
    CHIP_DATABASE,
    ChipProfile,
    get_all_matching_devices,
    lookup_device,
)

# 定義 7-bit 位址類別常數與顏色映射
_CATEGORY_COLORS = {
    "未配置（Unassigned）": "#2A2D34",
    "保留位址（Reserved）": "#E63946",
    "多裝置共用／衝突（Conflict）": "#FFB703",
    "EEPROM / Memory": "#4361EE",
    "Display / DDC": "#06D6A0",
    "Temperature Sensor": "#4CC9F0",
    "Power Monitor": "#2EC4B6",
    "GPIO Expander": "#7209B7",
    "PMBus Power Management": "#F72585",
    "PMBus Power Supply": "#E040FB",
    "Real-Time Clock (RTC)": "#FB8500",
    "Display Controller": "#00B4D8",
    "I2C Switch / Mux": "#3A0CA3",
    "Special / Broadcast": "#8D99AE",
    "SMBus Alert": "#C77DFF",
}

# 晶片進階教學指引與韌體排查重點
_CHIP_TEACHING_INSIGHTS: dict[str, dict[str, str]] = {
    "AT24Cxx / 24LCxx EEPROM": {
        "核心架構與特點": "標準序列 EEPROM（如 24C02/04/08/16/32/64/128/256/512/M01），透過硬體引腳 A0/A1/A2 決定 0x50~0x57 位址。",
        "跨頁覆蓋風險（Page Rollover）": "寫入資料時若位元組數量超過單一 Page 邊界（例如 16、32 或 64 Bytes），位址計數器會自動回捲至當前頁面開頭並覆寫舊資料，而不會自動跳轉至下一頁。",
        "寫入週期時間（Write Cycle Time）": "EEPROM 內部快閃抹寫通常需要 5.0 ms 週期時間；在寫入期間發送 I2C 請求會收到 NACK，韌體應實作 ACK Polling（定址輪詢）以提升傳輸效率。",
        "位址長度注意事項": "小容量（24C01~24C16）使用 1 Byte 暫存器位移（部分容量利用 I2C 位址位元擴充）；大容量（24C32 以上）則需發送 2 Bytes 大端序（Big-Endian）記憶體位址。",
    },
    "DDC / EDID Display EEPROM": {
        "核心架構與特點": "HDMI、DisplayPort 與 VGA 顯示器傳輸線內的 VESA 顯示資料通道（DDC），固定掛載於 0x50 位址。",
        "通訊協定約束": "標準 DDC 讀取限制為標準模式 100 kHz；傳輸速率過高可能導致訊號衰減或顯示器微控制器無回應。",
        "區塊結構與擴充": "前 128 Bytes 為 VESA EDID 基礎資料塊；若支援 CEA/CTA-861 音訊或 4K HDR 擴充，主機須透過 I2C 位址 0x30（Segment Pointer）切換分段。",
        "熱插拔與通訊穩定性": "當 HPD（Hot Plug Detect）引腳拉高時，主機作業系統會啟動 DDC 讀取；若線材雜散電容過大可能導致 NACK 錯誤。",
    },
    "LM75 / TMP75 / TMP102 Temperature Sensor": {
        "核心架構與特點": "數位溫度感測器，透過 A0/A1/A2 設定 0x48~0x4F 位址，輸出 9-bit 至 12-bit 二補數（Two's Complement）格式。",
        "溫度暫存器格式": "讀取 0x00 暫存器回傳 2 Bytes；最高位元（Bit 15）為符號位（0 為正溫，1 為負溫）。",
        "解析度換算公式": "9-bit 解析度為 0.5 °C（raw >> 7 * 0.5）；12-bit 解析度為 0.0625 °C（raw >> 4 * 0.0625）。",
        "警報與中斷輸出（OS/ALERT）": "可透過 0x01 Config 暫存器配置為 Comparator 模式或 Interrupt 模式，並設定 Thyst (0x02) 與 Tos (0x03) 臨界溫度門檻。",
    },
    "ADT7410 / ADT7420 High-Accuracy Temp Sensor": {
        "核心架構與特點": "高精度 16-bit 數位溫度感測器，支援 0x48~0x4B 位址，適用於伺服器主機板關鍵散熱監控。",
        "解析度切換模式": "預設為 13-bit 模式（0.0625 °C 解析度，轉換時間 60 ms）；可配置設定暫存器切換至 16-bit 模式（0.0078125 °C 解析度，轉換時間 240 ms）。",
        "省電與轉換機制": "支援連續轉換（Continuous Conversion）、單次觸發（One-Shot）與 1 SPS 取樣模式，以大幅降低整體耗電量。",
        "過溫臨界保護（T_CRIT）": "提供獨立的 CT Pin 開汲極（Open-Drain）硬體過溫警報輸出，可直接連接至電源保護或風扇轉速控制器。",
    },
    "MCP9808 Precision Temperature Sensor": {
        "核心架構與特點": "Microchip 高精準度溫度感測器，精確度高達 ±0.25 °C，支援 0x18~0x1F 位址範圍。",
        "暫存器位元組順序": "所有暫存器均為 16-bit 大端序（Big-Endian；MSB 先傳，LSB 後傳），讀取時需組合成 16-bit 整數後解析。",
        "溫度警報旗標": "Ambient Temperature Register (0x05) 的高 3 位元包含 TCRIT、TUPPER、TLOWER 狀態旗標，低 13 位元為溫度數值。",
        "關機模式（Shutdown Mode）": "可透過設定暫存器進入極低功耗關機模式（典型電流 0.1 µA），適合低功耗電池供電裝置。",
    },
    "INA219 / INA226 / INA230 Current/Power Monitor": {
        "核心架構與特點": "雙向高側分流（Shunt）電流與電壓監控晶片，支援 0x40~0x45 位址，廣泛用於伺服器與嵌入式電源軌監控。",
        "分流電阻與校準暫存器": "Shunt Voltage (0x01) 量測分流電阻兩端微伏級壓降；必須依據分流電阻值計算並寫入 Calibration Register (0x05)，晶片內部方能自動計算電流 (0x04) 與功率 (0x03)。",
        "匯流排電壓量測（Bus Voltage）": "暫存器 0x02 提供高達 26V (INA219) 或 36V (INA226) 匯流排電壓量測，需留意高壓側共模電壓上限。",
        "平均與取樣濾波": "可於 Config 暫存器配置 ADC 平均次數（1~1024 samples）與轉換時間，以平滑電壓瞬波與開關雜訊。",
    },
    "PAC1934 Multi-Channel Power Monitor": {
        "核心架構與特點": "Microchip 4 通道直流電源與電能累積監控晶片，支援 0x10~0x12 位址與高達 1000 kHz (1 MHz) 高速 I2C 通訊。",
        "多通道同步取樣": "單一晶片同時監控 4 組獨立電源軌之電壓、電流與瞬時功率，取樣率高達 1024 samples/sec。",
        "電能累積暫存器（Energy Accumulator）": "內建 48-bit 功率積分器與 24-bit 取樣計數器，韌體可直接讀取累積電能，無需高頻率軟體輪詢。",
        "快照暫存器（Snapshot Mode）": "發送 REFRESH 或 REFRESH_V 命令後會將所有量測值鎖定至 Snapshot 暫存器，確保讀取過程資料一致性（避免資料撕裂）。",
    },
    "PCA9555 / TCA9539 / PCA9535 16-bit GPIO Expander": {
        "核心架構與特點": "16-bit 雙埠（Port 0 / Port 1）I2C 遠端 I/O 擴展晶片，支援 0x20~0x27 位址。",
        "暫存器成對結構": "包含 8 個暫存器：Input (0x00/0x01)、Output (0x02/0x03)、Polarity Inversion (0x04/0x05)、Configuration 方向 (0x06/0x07)。",
        "中斷訊號輸出（INT#）": "具備 Open-Drain 中斷引腳；當任何配置為輸入的引腳電位改變時拉低，主控端讀取 Input 暫存器即可自動清除中斷。",
        "方向配置預設值": "重置後 Configuration 暫存器預設為 0xFF（全引腳為 High-Z 輸入模式）；若欲作為輸出控制，必須先將相應 bit 寫 0。",
    },
    "PCF8574 / PCF8574A 8-bit Quasi-bidirectional GPIO Expander": {
        "核心架構與特點": "8-bit 準雙向（Quasi-bidirectional）遠端 I/O 晶片；PCF8574 位址為 0x20~0x27，PCF8574A 位址為 0x38~0x3F。",
        "無暫存器位移位元組": "通訊時不包含 Register Offset 位元組！直接對 I2C 位址發送 1 Byte 寫入即更新輸出，發送 1 Byte 讀取即獲取輸入狀態。",
        "準雙向 I/O 操作陷阱": "引腳為「強下拉、弱上拉」結構。欲將某引腳作為輸入使用時，必須先對該 bit 寫入 1（輸出 High-Z 弱上拉），外部信號方能將其下拉至 Low。",
        "中斷輸出機制": "具備 INT# 開汲極中斷引腳，輸入狀態改變時觸發中斷，讀取或寫入資料時中斷重置。",
    },
    "MCP23017 / MCP23008 GPIO Expander": {
        "核心架構與特點": "Microchip 16-bit 高速 I2C I/O 擴展器，支援 0x20~0x27 位址與高達 1.7 MHz 通訊速度。",
        "IOCON.BANK 分頁排列陷阱": "IOCON 暫存器的 BANK 位元決定暫存器映射方式：BANK=0 時 Port A 與 Port B 暫存器交錯排列（0x00~0x15）；BANK=1 時分為兩組獨立區塊（0x00~0x0A 與 0x10~0x1A）。若驅動程式與晶片 BANK 設定不一致，將導致所有暫存器位移錯位。",
        "中斷鏡像（Mirror）與捕捉": "支援 INTA/INTB 鏡像合併輸出，並具備 Interrupt-on-Change (IOC) 與中斷捕捉暫存器（INTCAP），可記錄中斷觸發瞬間之引腳電位。",
        "內建 100 kΩ 上拉電阻": "可透過 GPPU 暫存器個別啟用內部弱上拉電阻，精簡電路板週邊元件。",
    },
    "PMBus Power Controller / VR (XDPE / ISL / TPS / MP / MAX)": {
        "核心架構與特點": "伺服器與通訊設備多相電源控制器（VR Controller），支援 0x58~0x5F、0x40~0x47 與 0x60~0x67 位址範圍。",
        "PMBus 標準命令集": "採用標準 PMBus 指令集：STATUS_WORD (0x79)、STATUS_BYTE (0x78)、READ_VIN (0x88)、READ_VOUT (0x8B)、READ_IOUT (0x8C)、READ_TEMPERATURE_1 (0x8D)。",
        "數值格式解碼": "電源遙測數值通常採用 Linear11（5-bit 補碼指數 + 11-bit 補碼尾數）或 Linear16（搭配 VOUT_MODE 指數）格式，解碼時需套用相應公式。",
        "封包錯誤校驗（PEC）": "支援 PMBus/SMBus Packet Error Checking（CRC-8 多項式 C(x) = x^8 + x^2 + x + 1），在高電流雜訊環境下可有效防止誤動作與假警報。",
    },
    "Delta / Murata / BelPower PMBus PSU": {
        "核心架構與特點": "伺服器共用備援電源供應器（CRPS / AC-DC PSU），遵循 PMBus Power Supply 規範，位址範圍通常位於 0x58~0x5F。",
        "FRU 與 PMBus 共存結構": "PSU 模組通常在同一組 I2C 引腳上同時包含 24C02 FRU EEPROM（位於 0x50~0x57）與 PMBus 控制晶片（位於 0x58~0x5F）。",
        "黑盒子記錄（Blackbox Logging）": "高階 PSU 支援電源跳脫事件快照（Fault Log Record），在 AC 斷電或過溫跳脫時可讀取故障瞬間之電壓與電流歷程。",
        "風扇與狀態監控": "支援 FAN_COMMAND_1 (0x3B)、READ_FAN_SPEED_1 (0x90) 與 MFR 專屬指令，可依伺服器散熱需求動態調節風扇轉速。",
    },
    "DS1307 / DS3231 / PCF8563 Real-Time Clock": {
        "核心架構與特點": "即時時鐘／日曆晶片；DS1307/DS3231 位於 0x68 位址，PCF8563 位於 0x51 位址。",
        "BCD 格式編碼": "秒、分、時、日、月、年暫存器均採用 BCD (Binary Coded Decimal) 格式編碼；讀取後須經由 (val & 0x0F) + ((val >> 4) * 10) 轉換為十進位數值。",
        "時鐘震盪器致能（Clock Halt）": "DS1307 秒暫存器 (0x00) 的最高位元 Bit 7 為 CH (Clock Halt) 位元；初次上電時預設為 1（停止震盪），韌體必須將其寫 0 才能啟動計時。",
        "DS3231 溫補晶振（TCXO）": "DS3231 內部整合溫度補償晶體震盪器，年誤差小於 ±2 分鐘，並提供 0x11/0x12 內部溫度暫存器（0.25 °C 解析度）。",
    },
    "SSD1306 / SH1106 OLED Display Controller": {
        "核心架構與特點": "128x64 單色點矩陣 OLED 驅動晶片，透過 SA0 引腳配置 0x3C 或 0x3D 位址。",
        "控制位元組格式（Control Byte）": "每段 I2C 傳輸前需發送 Control Byte：0x00 代表後續為指令（Command），0x40 代表後續為 GDDRAM 顯示資料（Data）。",
        "定址模式（Addressing Modes）": "支援 Page Addressing Mode、Horizontal Addressing Mode 與 Vertical Addressing Mode，寫入畫面時需先設定欄位與頁面位址指標。",
        "I2C 頻寬與更新率限制": "全螢幕更新（1024 Bytes）在 400 kHz 速度下約需 25 ms，理論更新率上限約 40 FPS；建議採用局部 dirty rectangle 刷新以降低匯流排負載。",
    },
    "PCA9548A / PCA9546A / TCA9548A I2C Multiplexer": {
        "核心架構與特點": "8 通道（PCA9548A）或 4 通道（PCA9546A）I2C 匯流排切換器／多工器，支援 0x70~0x77 位址。",
        "位址衝突隔離利器": "當主機板上有多顆相同位址晶片（如多根記憶體模組 SPD EEPROM 或多顆溫度感測器）時，可透過 Mux 將其分佈於不同下游通道，消除位址衝突。",
        "控制暫存器操作": "無暫存器位移；直接寫入 1 Byte 控制字元，每個 Bit 對應一個通道（如寫入 0x01 開啟 Channel 0，寫入 0x00 關閉所有通道）。",
        "硬體重置防鎖死（RESET#）": "具備主動低電位 RESET# 引腳；當某下游通道因設備異常導致 SCL/SDA 被拉低鎖死時，主控端可拉低 RESET# 斷開所有通道以恢復主匯流排運作。",
    },
    "General Call / START Byte": {
        "核心架構與特點": "I2C 規範定義之廣播位址（0x00），所有支援 General Call 的從屬裝置均會回應 ACK。",
        "軟體重置指令（Software Reset）": "寫入 0x00 後接續發送 0x06 位元組，會觸發所有相容晶片執行內部重置序列並重新載入硬體位址引腳狀態。",
        "可程式化定址（Hardware Address Programming）": "寫入 0x04 後可對動態定址設備進行位址配置。",
        "使用限制": "0x00 為 I2C 保留位址，一般自定義從屬裝置嚴禁使用 0x00 作為其專屬定址。",
    },
    "SMBus Alert Response Address (ARA)": {
        "核心架構與特點": "SMBus 規範定義之警報應答位址（0x0C），用於共享中斷線（SMBALERT#）的硬體仲裁通訊。",
        "中斷應答與硬體仲裁流程": "當任一從屬裝置拉低 SMBALERT# 引腳時，主控端向 0x0C 發送 Read 請求；所有觸發警報的裝置會同時送出自己的 7-bit 位址，位址數值較小者透過硬體仲裁獲勝，主控端即可得知觸發警報之確切裝置。",
        "清除警報狀態": "仲裁獲勝之裝置在回傳位址後會自動釋放 SMBALERT# 引腳並清除內部中斷狀態。",
        "使用限制": "0x0C 為 SMBus 專屬保留位址，一般 I2C 從屬設備不應指派 0x0C 作為設備位址。",
    },
}


def _format_address_range(addrs: list[int]) -> str:
    """將 7-bit 位址列表格式化為易讀的十六進位字串。"""
    if not addrs:
        return "無"
    sorted_addrs = sorted(set(addrs))
    if len(sorted_addrs) == 1:
        return f"0x{sorted_addrs[0]:02X}"
    is_continuous = (
        len(sorted_addrs) > 1 and sorted_addrs[-1] - sorted_addrs[0] == len(sorted_addrs) - 1
    )
    if is_continuous:
        return (
            f"0x{sorted_addrs[0]:02X} ~ 0x{sorted_addrs[-1]:02X}（共 {len(sorted_addrs)} 個位址）"
        )
    return ", ".join(f"0x{a:02X}" for a in sorted_addrs)


def _parse_address_input(addr_str: str) -> int:
    """解析使用者輸入的位址字串（支援十六進位或十進位），並驗證 7-bit 範圍。"""
    clean_str = addr_str.strip()
    if not clean_str:
        raise ValueError("位址輸入不可為空。")
    try:
        val = int(clean_str, 0)
    except ValueError:
        raise ValueError(
            f"無法辨識的位址格式「{clean_str}」；請輸入 0x 開頭的十六進位值（如 0x50）或十進位整數。"
        )
    if val < 0 or val > 0x7F:
        if 0x80 <= val <= 0xFF:
            hint = f"（若您輸入的是 8-bit 位址含 R/W bit，右移 1 位元後為 0x{val >> 1:02X}）"
        else:
            hint = ""
        raise ValueError(
            f"7-bit I2C 位址範圍必須介於 0x00 至 0x7F 之間（0 ~ 127）；您輸入的值為 0x{val:02X}{hint}。"
        )
    return val


def _get_reserved_address_info(addr: int) -> str | None:
    """判斷位址是否為標準 I2C 規範保留位址，若是則回傳詳細說明。"""
    if 0x00 <= addr <= 0x07:
        reserved_map = {
            0x00: "General Call（廣播呼叫）/ START Byte（軟體重置或啟動位元組）",
            0x01: "CBUS 位址相容模式（CBUS Compatibility）",
            0x02: "保留給不同匯流排格式（Reserved for different bus formats）",
            0x03: "保留供未來擴充（Reserved for future purposes）",
            0x04: "高速主控碼（High-Speed Master Code 0000 100）",
            0x05: "高速主控碼（High-Speed Master Code 0000 101）",
            0x06: "高速主控碼（High-Speed Master Code 0000 110）",
            0x07: "高速主控碼（High-Speed Master Code 0000 111）",
        }
        return reserved_map.get(addr, "標準 I2C 保留位址（0x00 - 0x07）")
    if 0x78 <= addr <= 0x7F:
        if 0x78 <= addr <= 0x7B:
            return f"10-bit 從屬定址前綴碼（10-bit Addressing prefix 1111 0XX；位址 0x{addr:02X}）"
        return f"裝置識別碼 / 保留供未來擴充（Device ID / Reserved 1111 1XX；位址 0x{addr:02X}）"
    return None


def _build_address_map_figure() -> go.Figure:
    """建構 0x00 ~ 0x7F 全位址空間分佈的 Plotly 8x16 視覺化地圖。"""
    categories_order = list(_CATEGORY_COLORS.keys())
    cat_to_idx = {cat: idx for idx, cat in enumerate(categories_order)}
    n_cats = len(categories_order)

    colorscale: list[list[float | str]] = []
    for i, cat in enumerate(categories_order):
        color = _CATEGORY_COLORS[cat]
        colorscale.append([i / n_cats, color])
        colorscale.append([(i + 1) / n_cats, color])

    z: list[list[int]] = []
    text_matrix: list[list[str]] = []
    customdata: list[list[list[Any]]] = []

    for r in range(8):
        row_z: list[int] = []
        row_text: list[str] = []
        row_custom: list[list[Any]] = []
        for c in range(16):
            addr = r * 16 + c
            matches = get_all_matching_devices(addr)
            reserved_info = _get_reserved_address_info(addr)

            if reserved_info and not matches:
                cat_name = "保留位址（Reserved）"
            elif len(matches) > 1:
                cat_name = "多裝置共用／衝突（Conflict）"
            elif len(matches) == 1:
                cat_name = matches[0].category
                if cat_name not in cat_to_idx:
                    cat_name = "未配置（Unassigned）"
            else:
                cat_name = "未配置（Unassigned）"

            row_z.append(cat_to_idx.get(cat_name, 0))
            row_text.append(f"{addr:02X}")

            match_names = "、".join(m.name for m in matches) if matches else "無已知晶片"
            res_text = reserved_info if reserved_info else "無（標準 7-bit 定址空間）"

            row_custom.append(
                [
                    f"0x{addr:02X}",
                    str(addr),
                    cat_name,
                    match_names,
                    res_text,
                ]
            )
        z.append(row_z)
        text_matrix.append(row_text)
        customdata.append(row_custom)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[f"+0x{c:X}" for c in range(16)],
            y=[f"0x{r:X}0" for r in range(8)],
            text=text_matrix,
            texttemplate="<b>%{text}</b>",
            textfont={"size": 11, "color": "#FFFFFF"},
            customdata=customdata,
            hovertemplate=(
                "<b>位址 0x%{customdata[0]}（十進位 %{customdata[1]}）</b><br>"
                "<b>類別／狀態</b>：%{customdata[2]}<br>"
                "<b>匹配晶片</b>：%{customdata[3]}<br>"
                "<b>保留說明</b>：%{customdata[4]}<extra></extra>"
            ),
            zmin=0,
            zmax=n_cats,
            colorscale=colorscale,
            showscale=False,
            xgap=3,
            ygap=3,
        )
    )

    fig.update_layout(
        title="I2C 7-bit 位址空間地圖（0x00 ~ 0x7F；點擊或懸停檢視詳細狀態）",
        template="plotly_dark",
        height=380,
        margin={"l": 40, "r": 20, "t": 50, "b": 30},
        xaxis={
            "title": "低 4 位元（Low Nibble）",
            "side": "top",
            "tickmode": "array",
            "tickvals": list(range(16)),
            "ticktext": [f"+0x{c:X}" for c in range(16)],
        },
        yaxis={
            "title": "高 3 位元（High Nibble）",
            "autorange": "reversed",
            "tickmode": "array",
            "tickvals": list(range(8)),
            "ticktext": [f"0x{r:X}0" for r in range(8)],
        },
    )
    return fig


def render() -> None:
    """渲染 I2C / SMBus / PMBus 晶片資料庫瀏覽器主畫面。"""
    st.header("I2C / SMBus / PMBus 晶片資料庫瀏覽器")
    st.caption(
        "提供常見 I2C、SMBus 與 PMBus 週邊晶片目錄清單、7-bit 位址反向查詢、"
        "全域位址空間分佈地圖與硬體暫存器實戰教學指南。"
    )
    render_guide_expander(
        "chapters/ch01_i2c_pmbus.md",
        "📖 點擊展開：I2C、SMBus 與 PMBus 晶片定址與協定實戰教學",
    )

    # -------------------------------------------------------------------------
    # 區域 1：完整晶片目錄表格
    # -------------------------------------------------------------------------
    st.subheader("1. 完整晶片目錄清單（Chip Catalog）")

    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        search_kw = st.text_input(
            "搜尋晶片（名稱或說明關鍵字）",
            value="",
            placeholder="例如：EEPROM、LM75、INA219、GPIO、PMBus、0x50…",
            key="chip_db_search_kw",
        )
    with f_col2:
        all_categories = sorted({p.category for p in CHIP_DATABASE})
        selected_categories = st.multiselect(
            "篩選設備類別（Category）",
            options=all_categories,
            default=[],
            placeholder="全部類別",
            key="chip_db_filter_cat",
        )
    with f_col3:
        all_protocols = sorted({p.protocol for p in CHIP_DATABASE})
        selected_protocols = st.multiselect(
            "篩選通訊協定（Protocol）",
            options=all_protocols,
            default=[],
            placeholder="全部協定",
            key="chip_db_filter_proto",
        )

    # 執行過濾
    filtered_chips: list[ChipProfile] = []
    for chip in CHIP_DATABASE:
        if search_kw:
            kw = search_kw.strip().lower()
            name_match = kw in chip.name.lower()
            desc_match = kw in chip.description.lower()
            cat_match = kw in chip.category.lower()
            proto_match = kw in chip.protocol.lower()
            addr_match = any(
                kw in f"0x{a:02x}" or kw == str(a) or kw == f"{a:02x}" for a in chip.addr_7bit_range
            )
            if not (name_match or desc_match or cat_match or proto_match or addr_match):
                continue
        if selected_categories and chip.category not in selected_categories:
            continue
        if selected_protocols and chip.protocol not in selected_protocols:
            continue
        filtered_chips.append(chip)

    catalog_data = [
        {
            "晶片型號與名稱": p.name,
            "設備類別": p.category,
            "通訊協定": p.protocol,
            "典型速度": f"{p.typical_speed_khz} kHz",
            "7-bit 位址範圍": _format_address_range(p.addr_7bit_range),
            "預設暫存器位移": (
                f"{p.default_register_len} Byte" if p.default_register_len > 0 else "無（直接資料）"
            ),
            "功能與規格說明": p.description,
        }
        for p in filtered_chips
    ]
    catalog_df = pd.DataFrame(catalog_data)

    if not catalog_df.empty:
        st.dataframe(
            catalog_df,
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"顯示 {len(filtered_chips)} 筆晶片資料（總計 {len(CHIP_DATABASE)} 筆）。")
    else:
        st.warning("查無符合篩選條件的晶片，請調整搜尋關鍵字或清除篩選條件。")

    st.divider()

    # -------------------------------------------------------------------------
    # 區域 2：位址查詢工具
    # -------------------------------------------------------------------------
    st.subheader("2. 7-bit I2C 位址反向查詢與衝突診斷（Address Lookup）")

    lookup_col1, lookup_col2 = st.columns([1, 2])
    with lookup_col1:
        query_addr_str = st.text_input(
            "輸入 7-bit 位址（十六進位或十進位）",
            value="0x50",
            help="支援 0x 開頭十六進位值（如 0x50、0x48）或十進位整數（如 80）。",
            key="chip_db_query_addr",
        )

    with lookup_col2:
        try:
            target_addr = _parse_address_input(query_addr_str)
        except ValueError as exc:
            st.error(f"位址輸入錯誤：{exc}")
            target_addr = None

    if target_addr is not None:
        legacy_first = lookup_device(target_addr)
        matches = get_all_matching_devices(target_addr)
        reserved_desc = _get_reserved_address_info(target_addr)

        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("7-bit 位址", f"0x{target_addr:02X} ({target_addr})")
        m_c2.metric("8-bit 寫入位址 (Write)", f"0x{(target_addr << 1):02X}")
        m_c3.metric("8-bit 讀取位址 (Read)", f"0x{((target_addr << 1) | 1):02X}")
        m_c4.metric("匹配已知晶片數", f"{len(matches)} 款")

        if reserved_desc:
            st.info(
                f"ℹ️ **I2C 規範保留位址提示**：位址 `0x{target_addr:02X}` 屬於「{reserved_desc}」。"
                "除非特定系統架構需要，一般自定義 I2C 從屬裝置應避免配置在此區段。"
            )

        if len(matches) > 1:
            st.warning(
                f"⚠️ **偵測到位址衝突風險（Address Conflict Risk）**：位址 `0x{target_addr:02X}` 同時對應 "
                f"{len(matches)} 款常見週邊晶片（{', '.join(m.name for m in matches)}）。"
                "在同一條實體 I2C 匯流排上，若同時掛載多個設定為相同位址的裝置，將引發 ACK 衝突、匯流排仲裁混亂或資料損毀。"
                "建議解決方案：透過硬體位址引腳（A0/A1/A2）變更位址、使用 I2C 多工器（如 PCA9548A）分流，或將裝置隔離至不同實體 Bus。"
            )
        elif len(matches) == 1 and legacy_first:
            st.success(
                f"✅ 找到 1 款匹配晶片：**{legacy_first.name}**（類別：{legacy_first.category}，協定：{legacy_first.protocol}）。"
            )
        else:
            st.info(
                f"ℹ️ 在內建資料庫中未找到預設對應 `0x{target_addr:02X}` 的已知晶片。"
                "這可能是特殊專利晶片、客製 ASIC，或是具有可程式化位址特性的週邊設備。"
            )

        if matches:
            st.markdown("##### 匹配晶片詳細列表：")
            for idx, match_chip in enumerate(matches, 1):
                with st.expander(
                    f"#{idx} — {match_chip.name}（{match_chip.category}／{match_chip.protocol}）",
                    expanded=True,
                ):
                    dc1, dc2 = st.columns([1, 1])
                    with dc1:
                        st.markdown(f"- **晶片名稱**：{match_chip.name}")
                        st.markdown(f"- **設備類別**：{match_chip.category}")
                        st.markdown(f"- **通訊協定**：{match_chip.protocol}")
                        st.markdown(f"- **典型速度**：{match_chip.typical_speed_khz} kHz")
                    with dc2:
                        st.markdown(
                            f"- **位址範圍**：{_format_address_range(match_chip.addr_7bit_range)}"
                        )
                        st.markdown(f"- **暫存器位移**：{match_chip.default_register_len} Byte")
                        st.markdown(f"- **晶片功能說明**：{match_chip.description}")
                    if match_chip.extra_info:
                        st.markdown("**暫存器與額外參數（Extra Info）**：")
                        extra_rows = [
                            {
                                "參數名稱（Key）": str(k),
                                "參數數值（Value）": (
                                    f"0x{v:02X}"
                                    if isinstance(v, int) and "reg" in str(k)
                                    else str(v)
                                ),
                            }
                            for k, v in match_chip.extra_info.items()
                        ]
                        st.table(pd.DataFrame(extra_rows))

    st.divider()

    # -------------------------------------------------------------------------
    # 區域 3：位址地圖視覺化
    # -------------------------------------------------------------------------
    st.subheader("3. I2C 7-bit 位址空間分佈地圖（0x00 ~ 0x7F Address Map）")
    st.caption(
        "橫軸為位址低 4 位元（0x_0 ~ 0x_F），縱軸為位址高 3 位元（0x0_ ~ 0x7_）。"
        "滑鼠懸停於方格上方可即時預覽該位址之晶片匹配與保留狀態。"
    )

    fig_map = _build_address_map_figure()
    st.plotly_chart(fig_map, width="stretch")

    # 圖例與統計指標
    total_addrs = 128
    reserved_addrs = 16
    occupied_addrs = len({addr for chip in CHIP_DATABASE for addr in chip.addr_7bit_range})
    conflict_addrs = len([addr for addr in range(128) if len(get_all_matching_devices(addr)) > 1])

    stat1, stat2, stat3, stat4 = st.columns(4)
    stat1.metric("總定址空間 (7-bit)", f"{total_addrs} 個位址")
    stat2.metric("規範保留位址", f"{reserved_addrs} 個位址")
    stat3.metric("資料庫涵蓋位址", f"{occupied_addrs} 個位址")
    stat4.metric("多裝置潛在衝突位址", f"{conflict_addrs} 個位址")

    with st.expander("🎨 點擊展開位址地圖圖例說明（Category Legend）", expanded=False):
        leg_cols = st.columns(3)
        cat_items = list(_CATEGORY_COLORS.items())
        for i, (cat, color) in enumerate(cat_items):
            col_idx = i % 3
            with leg_cols[col_idx]:
                st.markdown(
                    f"<span style='display:inline-block; width:14px; height:14px; "
                    f"background-color:{color}; border-radius:3px; margin-right:6px;'></span>"
                    f"**{cat}**",
                    unsafe_allow_html=True,
                )

    st.divider()

    # -------------------------------------------------------------------------
    # 區域 4：晶片詳情卡片與教學指引
    # -------------------------------------------------------------------------
    st.subheader("4. 晶片詳情規格卡片與韌體工程實戰指南")

    chip_names = [chip.name for chip in CHIP_DATABASE]
    selected_chip_name = st.selectbox(
        "選擇要檢視詳細規格與教學指引的晶片型號",
        options=chip_names if chip_names else [],
        index=0,
        key="chip_db_selected_detail_chip",
    )

    selected_profile = next(
        (chip for chip in CHIP_DATABASE if chip.name == selected_chip_name),
        None,
    )

    if selected_profile:
        store_profile = selected_profile
        _ = isinstance(store_profile, ChipProfile)
    if selected_profile:
        det_col1, det_col2 = st.columns([1, 1])
        with det_col1:
            st.markdown(f"### 📋 {selected_profile.name}")
            st.markdown(f"- **設備類別（Category）**：`{selected_profile.category}`")
            st.markdown(f"- **通訊協定（Protocol）**：`{selected_profile.protocol}`")
            st.markdown(
                f"- **典型速度（Typical Speed）**：`{selected_profile.typical_speed_khz} kHz`"
            )
            st.markdown(f"- **暫存器位移長度**：`{selected_profile.default_register_len} Byte`")
            st.markdown(
                f"- **7-bit 位址範圍**：`{_format_address_range(selected_profile.addr_7bit_range)}`"
            )
            st.markdown(f"- **功能說明**：{selected_profile.description}")

        with det_col2:
            st.markdown("### ⚙️ 暫存器與額外參數（Extra Info）")
            if selected_profile.extra_info:
                extra_df = pd.DataFrame(
                    [
                        {
                            "參數名稱（Parameter）": str(k),
                            "數值（Value / Offset）": (
                                f"0x{v:02X}"
                                if isinstance(v, int) and "reg" in str(k)
                                else (f"{v} ms" if "ms" in str(k) else str(v))
                            ),
                        }
                        for k, v in selected_profile.extra_info.items()
                    ]
                )
                st.table(extra_df)
            else:
                st.info("此晶片無額外暫存器定義參數（採用標準協定或無暫存器結構）。")

        insights = _CHIP_TEACHING_INSIGHTS.get(selected_profile.name)
        if insights:
            st.markdown("### 💡 資深韌體工程師實戰指引與排查注意事項")
            for title, content in insights.items():
                st.markdown(f"- **{title}**：{content}")
        else:
            st.caption("尚無專屬韌體工程指引。")

    render_page_footer()


__all__ = ["render"]
