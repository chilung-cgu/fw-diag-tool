from __future__ import annotations

import re
from typing import Any

import streamlit as st

from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.gui.guide_resources import load_guide_text, prepare_guide_markdown
from fw_diag_tool.gui.pages.i2c_page import analyze_i2c as analyze_i2c_controller
from fw_diag_tool.i2c.input import I2CInputFormat
from fw_diag_tool.limits import AnalysisLimits
from fw_diag_tool.spi.engine import SPIDiagnosticEngine

DEFAULT_I2C_TIMEOUT_MS = 25.0

# GUI uses fixed safe limits independent of CLI overrides.
GUI_ANALYSIS_LIMITS = AnalysisLimits()
MAX_PACKET_HEX_CHARS = 64 * 1024


def _reset_i2c_session_state() -> None:
    st.session_state["i2c_input_format"] = I2CInputFormat.DECODED_CSV.value
    st.session_state["i2c_smbus_timeout"] = DEFAULT_I2C_TIMEOUT_MS
    st.session_state["i2c_board_profile_yaml"] = ""
    # A session upload supersedes any previously selected teaching sample.
    # Leaving the sample active would analyze the old decoded bytes using the
    # restored raw/text mode when the session is uploaded without its capture.
    st.session_state["i2c_sample_active"] = False
    st.session_state.pop("i2c_sample_content", None)
    st.session_state.pop("i2c_sample_key", None)
    st.session_state.pop("i2c_loaded_session_identity", None)


@st.cache_data(show_spinner="正在解析 I2C 輸入資料…")
def analyze_i2c_input(
    csv_content: str,
    input_mode: str,
    smbus_timeout_ms: float,
    board_profile_yaml: str | None = None,
) -> tuple[Any, Any]:
    profile = load_board_profile(board_profile_yaml) if board_profile_yaml else None
    return analyze_i2c_controller(
        csv_content,
        input_mode=input_mode,
        input_format=None,
        smbus_timeout_ms=smbus_timeout_ms,
        board_profile=profile,
        limits=GUI_ANALYSIS_LIMITS,
    )


@st.cache_data(show_spinner="正在解析 SPI 輸入資料…")
def analyze_spi_input(csv_content: str, max_page_size: int = 256) -> Any:
    return SPIDiagnosticEngine(max_page_size=max_page_size).analyze_csv_content(csv_content)


_REGISTER_MEANING_ZH = {
    "OK": "正常（OK）",
    "Normal": "正常（Normal）",
    "Ready": "就緒（Ready）",
    "Busy": "忙碌（Busy）",
    "Unit On": "裝置開啟（Unit On）",
    "Unit Off": "裝置關閉（Unit Off）",
    "Unit is Outputting Power": "裝置正在輸出電力（Unit is Outputting Power）",
    "Unit is Off": "裝置已關閉（Unit is Off）",
    "Vout Overvoltage Fault": "輸出過電壓故障（Vout Overvoltage Fault）",
    "Iout Overcurrent Fault": "輸出過電流故障（Iout Overcurrent Fault）",
    "Vin Undervoltage Fault": "輸入欠電壓故障（Vin Undervoltage Fault）",
    "Overtemperature Alarm": "過溫警報（Overtemperature Alarm）",
    "CML Error": "CML 通訊／記憶體／邏輯錯誤（CML Error）",
    "VOUT Fault/Warning occurred": "發生 VOUT 故障／警告（VOUT Fault/Warning occurred）",
    "IOUT Fault/Warning occurred": "發生 IOUT 故障／警告（IOUT Fault/Warning occurred）",
    "Input Voltage/Current/Power Fault occurred": "發生輸入電壓／電流／功率故障（Input Voltage/Current/Power Fault occurred）",
    "Manufacturer Specific Fault": "製造商專屬故障（Manufacturer Specific Fault）",
    "POWER_GOOD Asserted (Normal)": "POWER_GOOD 有效（正常）（POWER_GOOD Asserted）",
    "POWER_GOOD Negated (Power Rail Down)": "POWER_GOOD 無效（電源軌關閉）（POWER_GOOD Negated）",
    "Overtemperature Fault/Warning occurred": "發生過溫故障／警告（Overtemperature Fault/Warning occurred）",
    "Communication, Memory or Logic (CML) Fault": "通訊／記憶體／邏輯（CML）故障（Communication, Memory or Logic Fault）",
    "Device Busy / Packet Rejected": "裝置忙碌／封包被拒絕（Device Busy / Packet Rejected）",
    "Data Link Protocol Error (Active)": "Data Link Protocol 錯誤（作用中）（Data Link Protocol Error）",
    "Surprise Down Error (Active)": "Surprise Down 錯誤（作用中）（Surprise Down Error）",
    "Poisoned TLP Received (Active)": "收到 Poisoned TLP（作用中）（Poisoned TLP Received）",
    "Flow Control Protocol Error (Active)": "Flow Control Protocol 錯誤（作用中）（Flow Control Protocol Error）",
    "Completion Timeout (Active)": "Completion Timeout（作用中）（Completion Timeout）",
    "Completer Abort (Active)": "Completer Abort（作用中）（Completer Abort）",
    "Unexpected Completion (Active)": "非預期 Completion（作用中）（Unexpected Completion）",
    "Receiver Overflow (Active)": "Receiver Overflow（作用中）（Receiver Overflow）",
    "Malformed TLP (Active)": "Malformed TLP（作用中）（Malformed TLP）",
    "ECRC Error (Active)": "ECRC 錯誤（作用中）（ECRC Error）",
    "Unsupported Request (Active)": "Unsupported Request（作用中）（Unsupported Request）",
    "ACS Violation (Active)": "ACS 違規（作用中）（ACS Violation）",
    "Uncorrectable Internal Error (Active)": "不可修正內部錯誤（作用中）（Uncorrectable Internal Error）",
}

_REGISTER_DESCRIPTION_ZH = {
    "PMBus Standard Status Word (Fault and Warning summary)": (
        "PMBus 標準狀態字（故障與警告摘要；PMBus Standard Status Word；Fault and Warning summary）"
    ),
    "PMBus Standard Status Byte": "PMBus 標準狀態位元組（PMBus Standard Status Byte）",
    "PCIe AER Uncorrectable Error Status Register (Offset 0x04 in AER Capability)": (
        "PCIe AER 不可修正錯誤狀態暫存器（AER Capability 位移 0x04；"
        "PCIe AER Uncorrectable Error Status Register）"
    ),
}

_PCIE_INPUT_ERROR_ZH = {
    "Invalid hex input: cannot extract at least 64 bytes of PCI configuration space.": (
        "十六進位輸入無效：無法擷取至少 64 bytes 的 PCIe 設定空間。"
    ),
    "PCIe config space must be bytes-like": "PCIe 設定空間必須是 bytes-like 資料。",
    "AER capability offset must be a non-negative integer": "AER Capability 位移必須是非負整數。",
}

_FAULT_ARENA_CASES_ZH = [
    {
        "case_id": "01",
        "label": "Case 01: I2C 位址 NACK（從裝置 Slave 未上電／Address Pin 浮接）",
        "symptom": "位址 NACK（Address NACK）",
        "hypothesis": "Slave 未上電、A0A1A2 浮接，或混用 7-bit／8-bit 位址。",
        "check": "量測 VCC，查位址腳位與 bus 設定。",
    },
    {
        "case_id": "02",
        "label": "Case 02: I2C 資料 NACK（EEPROM 內部寫入週期 tWR 忙碌）",
        "symptom": "資料 NACK（Data NACK）",
        "hypothesis": "EEPROM 正在執行內部 tWR 寫入週期，暫時不接受資料。",
        "check": "等待 5 ms，或使用 ACK Polling 確認 EEPROM 完成寫入。",
    },
    {
        "case_id": "03",
        "label": "Case 03: I2C 時鐘延展逾時（Clock Stretching > 25ms；SMBus Hang）",
        "symptom": "Clock Stretching 超過 25 ms（Clock Stretching > 25ms）。",
        "hypothesis": "Slave MCU 卡在中斷處理，持續拉低 SCL 並造成 SMBus Hang。",
        "check": "執行 SCL 9-Clock Reset，並保留 reset log。",
    },
    {
        "case_id": "04",
        "label": "Case 04: I2C EEPROM Page Boundary 跨頁覆蓋風險（Page Rollover）",
        "symptom": "EEPROM Page Rollover（頁面回繞）：寫入跨頁後覆蓋同一頁的既有資料。",
        "hypothesis": "寫入跨越 Page Boundary，硬體位址計數器回繞而非前進到下一頁。",
        "check": "依 datasheet 的 Page Size 分段寫入。",
    },
    {
        "case_id": "05",
        "label": "Case 05: I2C PCA9548A MUX 多通道同時開啟造成匯流排衝突",
        "symptom": "MUX 多通道衝突（MUX conflict）。",
        "hypothesis": "PCA9548A 同時開啟多個下游通道。",
        "check": "切換為 1-hot 模式並確認每個 channel。",
    },
    {
        "case_id": "06",
        "label": "Case 06: PMBus VOUT_TRIM signed decode（-0.25V；READ_VOUT 12.0V）",
        "symptom": "VOUT_TRIM 負值補碼解碼錯誤（VOUT_TRIM signed decode）。",
        "hypothesis": "Linear16 有號補碼未處理，將負的 trim word 當成 unsigned 值。",
        "check": "以 signed=True 解碼，並對照 READ_VOUT 與 PMBus exponent。",
    },
    {
        "case_id": "07",
        "label": "Case 07: PCIe Gen4→Gen1 降速（金手指髒污／SI 劣化）",
        "symptom": "PCIe Gen4 降為 Gen1（Link degradation）。",
        "hypothesis": "金手指髒污或 SI 劣化。",
        "check": "檢查金手指與 REFCLK，再查看 Link status。",
    },
    {
        "case_id": "08",
        "label": "Case 08: PCIe AER Completion Timeout（目標設備 AXI 狀態機死鎖）",
        "symptom": "完成逾時（Completion Timeout）。",
        "hypothesis": "目標設備 AXI 狀態機死鎖。",
        "check": "檢查 CTO 設定、Requester／Completer 與 kernel log。",
    },
    {
        "case_id": "09",
        "label": "Case 09: PCIe AER Malformed TLP（封包長度違反 Max Payload Size）",
        "symptom": "格式錯誤 TLP（Malformed TLP）。",
        "hypothesis": "封包長度超過 MPS。",
        "check": "檢查 Max Payload Size 與 TLP header。",
    },
    {
        "case_id": "10",
        "label": "Case 10: PCIe AER Poisoned TLP（上游主記憶體 ECC 錯誤）",
        "symptom": "毒化 TLP（Poisoned TLP）。",
        "hypothesis": "上游記憶體 ECC 錯誤。",
        "check": "排查 DRAM ECC、poison 產生端與資料路徑。",
    },
    {
        "case_id": "11",
        "label": "Case 11: SPI NOR Flash Page Program 遺漏 0x06 WREN 導致寫入無效",
        "symptom": "Page Program 無效（Page Program rejected）。",
        "hypothesis": "擷取範圍內未觀察到 0x06 WREN 或 status-read，WEL 狀態未知。",
        "check": "擴大 capture window，確認 0x06 WREN／RDSR（0x05）與 WEL=1。",
    },
    {
        "case_id": "12",
        "label": "Case 12: SPI NOR Flash Page Buffer 256B Wrap-Around 覆蓋",
        "symptom": "資料覆蓋（Page Buffer Wrap-Around）。",
        "hypothesis": "單次 payload 超過 256B Page Buffer 可用的剩餘空間。",
        "check": "依 Page Size 計算 chunk 大小。",
    },
    {
        "case_id": "13",
        "label": "Case 13: SPI JEDEC 讀回全 0xFF（MISO 線路浮接／供電中斷）",
        "symptom": "JEDEC 全 0xFF（JEDEC all 0xFF）。",
        "hypothesis": "MISO 浮接或 Flash 未上電。",
        "check": "量測 VCC，檢查 CS#、MISO 與供電。",
    },
    {
        "case_id": "14",
        "label": "Case 14: SPI JEDEC 讀回全 0x00（MISO 對地短路／匯流排被鉗位）",
        "symptom": "JEDEC 全 0x00（JEDEC all 0x00）。",
        "hypothesis": "MISO 對地短路或匯流排被箝位。",
        "check": "檢查走線短路、箝位與 CS#。",
    },
    {
        "case_id": "15",
        "label": "Case 15: Linux Kernel Panic：NULL Pointer Dereference（Offset 0x10）",
        "symptom": "Kernel NULL Pointer（核心 NULL 指標）。",
        "hypothesis": "kzalloc 失敗未檢查。",
        "check": "使用 addr2line -e vmlinux 對照 RIP 與 symbols。",
    },
    {
        "case_id": "16",
        "label": "Case 16: ARM Cortex-M HardFault：DIVBYZERO（除以零中斷陷阱）",
        "symptom": "除以零（DIVBYZERO）。",
        "hypothesis": "計算分母為 0，未在除法前執行輸入或狀態檢查。",
        "check": "加入 if (denom == 0) 防護並遵循錯誤契約。",
    },
    {
        "case_id": "17",
        "label": "Case 17: ARM Cortex-M HardFault：UNALIGNED（未對齊 32-bit 指標存取）",
        "symptom": "未對齊存取（UNALIGNED）。",
        "hypothesis": "以 uint32_t* 讀取奇數位址，違反平台的 32-bit 對齊要求。",
        "check": "改用 memcpy 或符合專案規範的 packed 存取。",
    },
    {
        "case_id": "18",
        "label": "Case 18: ARM Cortex-M HardFault：IMPRECISERR（異步總線寫入錯誤）",
        "symptom": "非精確匯流排錯誤（IMPRECISERR）。",
        "hypothesis": "周邊時鐘尚未開啟就寫入暫存器，Write Buffer 延後回報錯誤。",
        "check": "依 MCU 能力評估 Write Buffer 設定並保留 fault frame。",
    },
    {
        "case_id": "19",
        "label": "Case 19: MCTP PLDM 感測器數值傳輸異常與封包順序錯亂",
        "symptom": "PLDM 封包順序錯亂（PLDM sequence error）。",
        "hypothesis": "PktSeq 未正確管理。",
        "check": "檢查 SOM／EOM／Seq 與重組順序。",
    },
    {
        "case_id": "20",
        "label": "Case 20: IPMB Checksum 1/2 校驗碼錯誤引發封包丟棄",
        "symptom": "IPMB Checksum 失敗（Checksum FAIL）。",
        "hypothesis": "資料損毀或位址錯誤。",
        "check": "檢查 (sum+chk)&0xFF==0 並重新計算兩段 checksum。",
    },
]


def _localize_register_meaning(value: object) -> str:
    """Make built-in YAML meanings readable while preserving source wording."""
    text = str(value)
    if text in _REGISTER_MEANING_ZH:
        return _REGISTER_MEANING_ZH[text]
    if text.startswith("Raw value: "):
        return f"原始值：{text.removeprefix('Raw value: ')}（Raw value）"
    return text


def _localize_register_description(value: object) -> str:
    text = str(value)
    return _REGISTER_DESCRIPTION_ZH.get(text, _localize_register_meaning(text))


def _localize_pcie_input_error(value: object) -> str:
    text = str(value)
    if text.startswith("Device dump could not be decoded: "):
        detail = text.removeprefix("Device dump could not be decoded: ")
        detail = detail.split(" The source bytes", 1)[0]
        return f"裝置傾印無法解碼：{_localize_pcie_input_error(detail)}"
    if text in _PCIE_INPUT_ERROR_ZH:
        return _PCIE_INPUT_ERROR_ZH[text]
    if text.startswith("Config space size ") and "smaller than minimum 64 bytes" in text:
        return f"PCIe 設定空間長度不足：{text}（Config space size）"
    if text.startswith("AER capability at ") and " is truncated" in text:
        return f"AER Capability 結構不完整：{text}（AER capability truncated）"
    if "must be an unsigned 32-bit integer" in text:
        return f"PCIe 欄位必須是無號 32-bit 整數：{text}"
    return f"PCIe 解析失敗：{text}"


def _localize_gui_error(value: object, *, domain: str) -> str:
    text = str(value)
    if domain == "i2c_builder":
        if text == "address_7bit must be between 8 and 119":
            return "從裝置 7-bit 位址必須介於 0x08～0x77。"
        if text.endswith(" must be an integer such as 0x50"):
            label = text[: -len(" must be an integer such as 0x50")]
            return f"{label} 必須是整數，例如 0x50。"
        if text.endswith(" is required"):
            return f"{text[:-len(' is required')]} 為必填。"
        match = re.fullmatch(r"(.+) has (\d+) bytes; limit is (\d+)", text)
        if match:
            return f"{match.group(1)} 有 {match.group(2)} 個位元組，超過 {match.group(3)} 個位元組上限。"
        match = re.fullmatch(r"(.+) byte #(\d+) is not an integer: (.+)", text)
        if match:
            return f"{match.group(1)} 第 {match.group(2)} 個位元組不是整數：{match.group(3)}。"
        match = re.fullmatch(r"(.+) byte #(\d+) must be between 0x00 and 0xFF", text)
        if match:
            return f"{match.group(1)} 第 {match.group(2)} 個位元組必須介於 0x00～0xFF。"
        match = re.fullmatch(r"I2C transfer payload has (\d+) bytes; limit is (\d+)", text)
        if match:
            return f"I2C 傳輸 Payload 有 {match.group(1)} 個位元組，超過 {match.group(2)} 個位元組上限。"
        match = re.fullmatch(r"I2C waveform requires (\d+) points; limit is (\d+)", text)
        if match:
            return f"I2C 波形需要約 {match.group(1)} 個點，超過 {match.group(2)} 個點上限。"
        return f"I2C 封包輸入格式錯誤：{text}"

    if domain == "spi":
        exact = {
            "SPI CSV must provide an explicit timestamp column": "SPI CSV 必須提供明確的 timestamp 欄位。",
            "SPI CSV must provide an explicit MOSI column": "SPI CSV 必須提供明確的 MOSI 欄位。",
            "SPI CSV must provide an explicit MISO column": "SPI CSV 必須提供明確的 MISO 欄位。",
            "SPI CSV must provide an explicit CS/Enable column": "SPI CSV 必須提供明確的 CS/Enable 欄位。",
            "SPI CSV header contains duplicate column names": "SPI CSV 標頭含有重複的欄位名稱。",
            "page_size must be a positive integer": "頁面大小必須是正整數。",
        }
        if text in exact:
            return exact[text]
        if text.startswith("invalid SPI CSV input: "):
            return f"SPI CSV 格式無效：{text.removeprefix('invalid SPI CSV input: ')}"
        match = re.fullmatch(r"SPI CSV contains ambiguous (.+) columns", text)
        if match:
            return f"SPI CSV 含有多組可能的 {match.group(1)} 欄位，無法判定。"
        match = re.fullmatch(r"CSV row (\d+) has (\d+) fields; expected (\d+)", text)
        if match:
            return f"CSV 第 {match.group(1)} 列有 {match.group(2)} 個欄位，預期 {match.group(3)} 個。"
        match = re.fullmatch(r"invalid timestamp at CSV row (\d+): (.+)", text)
        if match:
            return f"CSV 第 {match.group(1)} 列的 timestamp 無效：{match.group(2)}。"
        match = re.fullmatch(r"timestamp at CSV row (\d+) must be finite and non-negative", text)
        if match:
            return f"CSV 第 {match.group(1)} 列的 timestamp 必須是有限且非負數值。"
        match = re.fullmatch(r"timestamps decrease at CSV row (\d+)", text)
        if match:
            return f"CSV 第 {match.group(1)} 列的 timestamp 倒退。"
        match = re.fullmatch(r"invalid (MOSI|MISO) byte at CSV row (\d+): (.+); expected 0\.\.255 or 0x00\.\.0xFF", text)
        if match:
            return f"CSV 第 {match.group(2)} 列的 {match.group(1)} 位元組無效：{match.group(3)}；預期 0..255 或 0x00..0xFF。"
        match = re.fullmatch(r"CSV row (\d+) must provide both MOSI and MISO bytes; empty channel data is incomplete evidence", text)
        if match:
            return f"CSV 第 {match.group(1)} 列必須同時提供 MOSI 與 MISO 位元組；空白通道屬於不完整證據。"
        match = re.fullmatch(r"invalid chip-select state at CSV row (\d+): (.+)", text)
        if match:
            return f"CSV 第 {match.group(1)} 列的 CS/Enable 狀態無效：{match.group(2)}。"
        return f"SPI 追蹤記錄格式錯誤：{text}"

    if domain == "register":
        exact = {
            "register value must be an integer": "暫存器值必須是整數。",
            "register value must be between 0 and 0xFFFFFFFF": "暫存器值必須介於 0 和 0xFFFFFFFF。",
            "register offset must be between 0 and 0xFFFFFFFF": "暫存器位移必須介於 0 和 0xFFFFFFFF。",
            "register offset/name must not be boolean": "暫存器位移或名稱不可為布林值。",
            "register offset/name must be an integer offset or string name": "暫存器必須以整數位移或字串名稱指定。",
        }
        if text in exact:
            return exact[text]
        match = re.fullmatch(r"value (0x[0-9A-Fa-f]+) exceeds (\d+)-bit register (.+)", text)
        if match:
            return f"暫存器 {match.group(3)} 的值 {match.group(1)} 超過 {match.group(2)}-bit 寬度。"
        match = re.fullmatch(r"register (.+) size must be 8, 16, or 32 bits before decoding", text)
        if match:
            return f"暫存器 {match.group(1)} 的寬度必須是 8、16 或 32 bits。"
        return f"暫存器值無法解碼：{text}"

    if domain == "c_header":
        if text.endswith(" must be a string"):
            kind = text[: -len(" must be a string")]
            return f"{kind} 必須是字串。"
        if text.endswith(" must produce a C identifier beginning with a letter"):
            kind = text[: -len(" must produce a C identifier beginning with a letter")]
            label = "模組名稱" if kind == "module_name" else "名稱"
            return f"{label}必須可轉換成以英文字母開頭的 C identifier。"
        if text.startswith("duplicate generated register name: "):
            return f"產生的暫存器名稱重複：{text.removeprefix('duplicate generated register name: ')}。"
        return f"C 標頭檔輸入錯誤：{text}"

    if domain == "dts":
        match = re.fullmatch(r"devices\[(\d+)\] is missing addr", text)
        if match:
            return f"devices[{match.group(1)}] 缺少 addr（I2C 位址）。"
        match = re.fullmatch(r"devices\[(\d+)\] must be a mapping", text)
        if match:
            return f"devices[{match.group(1)}] 必須是 YAML mapping。"
        match = re.fullmatch(r"devices\[(\d+)\]\.channel must be between 0 and 7", text)
        if match:
            return f"devices[{match.group(1)}].channel 必須介於 0 和 7。"
        if text == "devices must be a list of mappings":
            return "devices 必須是 mapping 清單。"
        if text.endswith(" must be a non-reserved 7-bit I2C address (0x08..0x77)"):
            return f"{text.removesuffix(' must be a non-reserved 7-bit I2C address (0x08..0x77)')} 必須是非保留的 7-bit I2C 位址（0x08～0x77）。"
        return f"Device Tree 輸入錯誤：{text}"

    if domain == "session":
        if text == "invalid session JSON":
            return "Session JSON 格式無效。"
        if text.startswith("unsupported session version: "):
            return f"不支援的 Session 版本：{text.removeprefix('unsupported session version: ')}。"
        if text == "session smbus_timeout_ms must be a finite value between 1 and 100":
            return "Session 的 SMBus 逾時設定無效（smbus_timeout_ms）：必須是介於 1 到 100 的有限數值。"
        if text.startswith("session smbus_timeout_ms"):
            return f"Session 的 SMBus 逾時設定無效（smbus_timeout_ms）：{text.removeprefix('session smbus_timeout_ms ')}"
        if text.startswith("session input_mode and input_format"):
            return "Session 的 I2C 輸入格式設定互相衝突。"
        if text.startswith(("session board profile", "session board_profile")):
            return f"Session 的 Board Profile 設定無效：{text.removeprefix('session ')}"
        return f"Session 輸入錯誤：{text}"

    return text


def _localize_mctp_error(value: object) -> str:
    text = str(value)
    if text.endswith(" must be text"):
        return f"{text[: -len(' must be text')]} 必須是文字。"

    match = re.fullmatch(
        r"line (\d+): cannot determine protocol from structural evidence "
        r"\(checksums=(True|False),(True|False), versioned_mctp=(True|False)\)",
        text,
    )
    if match:
        return (
            f"第 {match.group(1)} 行無法依結構證據判定 MCTP 或 IPMB 協定；"
            f"校驗碼（checksums）={match.group(2)},{match.group(3)}、"
            f"MCTP Header Version={match.group(4)}。"
            "請改選強制 MCTP 或強制 IPMB 模式，或補上完整封包。"
        )

    match = re.fullmatch(r"line (\d+): incomplete byte token (.+)", text)
    if match:
        return f"第 {match.group(1)} 行的十六進位位元組不完整（byte token）：{match.group(2)}。"

    if text.startswith("MCTP/IPMB 十六進位輸入") and "超過" in text:
        return text
    return "MCTP/IPMB 輸入格式錯誤：無法完成解碼；請確認十六進位位元組、封包邊界與協定模式。"


def render_guide_expander(
    chapter_rel_path: str, label: str = "📖 點擊展開本功能詳細實戰教學手冊"
) -> None:
    markdown = load_guide_text(chapter_rel_path)
    if markdown is not None:
        with st.expander(label, expanded=False):
            st.markdown(prepare_guide_markdown(markdown, chapter_rel_path))



__all__ = [
    "DEFAULT_I2C_TIMEOUT_MS",
    "GUI_ANALYSIS_LIMITS",
    "MAX_PACKET_HEX_CHARS",
    "_FAULT_ARENA_CASES_ZH",
    "_PCIE_INPUT_ERROR_ZH",
    "_REGISTER_DESCRIPTION_ZH",
    "_REGISTER_MEANING_ZH",
    "_localize_gui_error",
    "_localize_mctp_error",
    "_localize_pcie_input_error",
    "_localize_register_description",
    "_localize_register_meaning",
    "_reset_i2c_session_state",
    "analyze_i2c_input",
    "analyze_spi_input",
    "render_guide_expander",
]
