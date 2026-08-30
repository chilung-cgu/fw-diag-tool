"""Board Profile 視覺化拓撲編輯器 GUI 模組。

提供表單式 I2C 匯流排、周邊晶片與 MUX 多工器拓撲定義、即時 YAML 產出、
反向 YAML 匯入解析，以及位址衝突、保留位址與時鐘速度相容性驗證。
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st
import yaml

from fw_diag_tool.board_profile import (
    BoardProfile,
    SchemaError,
    load_board_profile,
)
from fw_diag_tool.gui.shared import render_guide_expander
from fw_diag_tool.gui.uploads import MAX_TEXT_BYTES, decode_uploaded_text, validate_pasted_text
from fw_diag_tool.i2c.chip_db import CHIP_DATABASE, ChipProfile

_COMPATIBLE_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9,._+-]*,[A-Za-z0-9][A-Za-z0-9,._+-]*$")

# 7-bit I2C 保留位址定義（NXP UM10204 規範）
RESERVED_I2C_ADDRESSES: dict[int, str] = {
    0x00: "General Call / START byte",
    0x01: "CBUS address",
    0x02: "Reserved for different bus formats",
    0x03: "Reserved for future purposes",
    0x04: "Hs-mode master code (0x04)",
    0x05: "Hs-mode master code (0x05)",
    0x06: "Hs-mode master code (0x06)",
    0x07: "Hs-mode master code (0x07)",
    0x78: "10-bit slave addressing (0x78)",
    0x79: "10-bit slave addressing (0x79)",
    0x7A: "10-bit slave addressing (0x7A)",
    0x7B: "10-bit slave addressing (0x7B)",
    0x7C: "Device ID / Reserved (0x7C)",
    0x7D: "Device ID / Reserved (0x7D)",
    0x7E: "Device ID / Reserved (0x7E)",
    0x7F: "Device ID / Reserved (0x7F)",
}

# 速度模式名稱與頻率對照
SPEED_MODE_MAP: dict[str, tuple[str, int]] = {
    "standard": ("100 kHz（標準模式 Standard-mode）", 100),
    "fast": ("400 kHz（快速模式 Fast-mode）", 400),
    "fast_plus": ("1000 kHz（快速增強模式 Fast-mode Plus）", 1000),
    "high_speed": ("3400 kHz（高速模式 High-Speed）", 3400),
    "ultra_fast": ("5000 kHz（超快模式 Ultra-Fast）", 5000),
}

SPEED_MODE_OPTIONS: list[str] = ["standard", "fast", "fast_plus", "high_speed", "ultra_fast"]


class HexInt(int):
    """自訂整數類型，在 YAML dump 時以十六進位格式（0xNN）輸出。"""


def _hex_int_representer(dumper: yaml.SafeDumper, data: HexInt) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:int", f"0x{data:02X}")


yaml.add_representer(HexInt, _hex_int_representer, Dumper=yaml.SafeDumper)


def parse_address_integer(value: Any, default: int = 0x48) -> int:
    """解析位址整數，支援十進位數值或十六進位字串（如 '0x48'）。"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return default
        try:
            return int(token, 0)
        except ValueError:
            if token.isdecimal():
                return int(token, 10)
    return default


def format_hex_address(addr: int) -> str:
    """格式化 7-bit 位址為 0xNN 字串。"""
    return f"0x{addr:02X}"


def get_chip_preset_map() -> dict[str, dict[str, Any]]:
    """建立 CHIP_DATABASE 晶片型號對應之預設值對照表。"""
    presets: dict[str, dict[str, Any]] = {}
    for chip in CHIP_DATABASE:
        presets[chip.name] = _chip_to_preset_dict(chip)
    return presets


def _chip_to_preset_dict(chip: ChipProfile) -> dict[str, Any]:
    """將 ChipProfile 轉換為編輯器預設值結構。"""
    category_slug = (
        chip.category.lower()
        .replace(" / ", "-")
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
    )
    if "eeprom" in category_slug:
        compat = "atmel,24c64"
        dev_name = "eeprom-storage"
    elif "temperature" in category_slug:
        compat = "ti,tmp75"
        dev_name = "temp-sensor"
    elif "power" in category_slug:
        compat = "ti,ina219" if "ina" in chip.name.lower() else "microchip,pac1934"
        dev_name = "power-monitor"
    elif "gpio" in category_slug:
        compat = (
            "nxp,pca9555"
            if "pca9555" in chip.name.lower()
            else "nxp,pcf8574"
            if "pcf8574" in chip.name.lower()
            else "microchip,mcp23017"
        )
        dev_name = "gpio-expander"
    elif "pmbus" in category_slug:
        compat = (
            "infineon,xdpe12284"
            if "vr" in chip.name.lower() or "controller" in chip.name.lower()
            else "delta,pmbus-psu"
        )
        dev_name = "pmbus-device"
    elif "rtc" in category_slug:
        compat = "dallas,ds1307"
        dev_name = "rtc-clock"
    elif "display" in category_slug:
        compat = "solomon,ssd1306" if "oled" in chip.name.lower() else "vesa,edid"
        dev_name = "display-device"
    elif "mux" in category_slug or "switch" in category_slug:
        compat = "nxp,pca9548"
        dev_name = "i2c-mux"
    elif "special" in category_slug or "broadcast" in category_slug:
        compat = "generic,general-call"
        dev_name = "broadcast-addr"
    elif "alert" in category_slug:
        compat = "smbus,alert"
        dev_name = "smbus-alert"
    else:
        compat = "generic,i2c-dev"
        dev_name = "i2c-device"

    default_addr = chip.addr_7bit_range[0] if chip.addr_7bit_range else 0x48

    return {
        "name": dev_name,
        "category": category_slug,
        "protocol": chip.protocol,
        "compatible": compat,
        "register_width": 8 if chip.default_register_len <= 1 else 16,
        "typical_speed_khz": chip.typical_speed_khz,
        "addr_7bit_range": chip.addr_7bit_range,
        "default_addr": default_addr,
        "description": chip.description,
    }


CHIP_PRESET_MAP = get_chip_preset_map()


def get_default_editor_state() -> dict[str, Any]:
    """產出預設的 Board Profile 編輯器狀態（以 YV4 參考架構為基礎）。"""
    return {
        "board_name": "YV4-CraterLake-reference",
        "version": "1.0",
        "description": "Yosemite V4 伺服器主機板 I2C/PMBus 拓撲定義範本",
        "buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [
                    {
                        "name": "board-gpio",
                        "address_7bit": 0x20,
                        "category": "gpio-expander",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9555",
                        "register_width": 8,
                        "chip_model": "PCA9555 / TCA9539 / PCA9535 16-bit GPIO Expander",
                    }
                ],
                "muxes": [
                    {
                        "name": "board-mux",
                        "address_7bit": 0x70,
                        "category": "i2c-mux",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9548",
                        "register_width": 8,
                        "num_channels": 8,
                        "channels": [
                            {
                                "channel": 0,
                                "devices": [
                                    {
                                        "name": "inlet-temp",
                                        "address_7bit": 0x48,
                                        "category": "temperature-sensor",
                                        "protocol": "I2C",
                                        "compatible": "ti,tmp75",
                                        "register_width": 8,
                                        "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                                    }
                                ],
                            },
                            {
                                "channel": 1,
                                "devices": [
                                    {
                                        "name": "outlet-temp",
                                        "address_7bit": 0x49,
                                        "category": "temperature-sensor",
                                        "protocol": "I2C",
                                        "compatible": "ti,tmp75",
                                        "register_width": 8,
                                        "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def validate_editor_state(state: dict[str, Any]) -> list[dict[str, str]]:
    """即時驗證表單狀態，回傳錯誤與警告訊息清單。

    回傳項包含：
    - level: 'error' | 'warning' | 'info'
    - location: 發生位置描述
    - message: 繁體中文說明
    """
    messages: list[dict[str, str]] = []

    # 1. 基本資訊檢查
    board_name = str(state.get("board_name", "")).strip()
    version = str(state.get("version", "")).strip()
    if not board_name:
        messages.append(
            {
                "level": "error",
                "location": "基本資訊",
                "message": "主機板名稱（board_name）不能為空字串。",
            }
        )
    if not version:
        messages.append(
            {
                "level": "error",
                "location": "基本資訊",
                "message": "版本號（version）不能為空字串。",
            }
        )

    buses = state.get("buses", [])
    if not buses:
        messages.append(
            {
                "level": "error",
                "location": "I2C 拓撲",
                "message": "拓撲中必須至少包含一條 I2C Bus（i2c_buses）。",
            }
        )
        return messages

    # 2. Bus 編號重複檢查
    seen_bus_nums: set[int] = set()
    for b_idx, bus in enumerate(buses):
        bus_num = bus.get("bus_num")
        if not isinstance(bus_num, int) or bus_num < 0 or bus_num > 65535:
            messages.append(
                {
                    "level": "error",
                    "location": f"Bus #{b_idx + 1}",
                    "message": f"Bus 編號必須介於 0 至 65535 之間（目前值：{bus_num}）。",
                }
            )
        elif bus_num in seen_bus_nums:
            messages.append(
                {
                    "level": "error",
                    "location": f"Bus #{bus_num}",
                    "message": f"發現重複的 Bus 編號：Bus #{bus_num} 已存在。",
                }
            )
        else:
            seen_bus_nums.add(bus_num)

        speed_mode = bus.get("speed_mode", "standard")
        bus_speed_khz = SPEED_MODE_MAP.get(speed_mode, ("100 kHz", 100))[1]

        # 3. Bus 層級裝置與 Mux 位址檢查
        bus_addrs: dict[int, str] = {}

        # 檢查直連裝置
        for d_idx, dev in enumerate(bus.get("devices", [])):
            dev_name = str(dev.get("name", "")).strip() or f"Device-{d_idx + 1}"
            dev_loc = f"Bus #{bus_num} -> 直連裝置「{dev_name}」"
            addr = dev.get("address_7bit")

            # 位址數值型態檢查
            if not isinstance(addr, int):
                messages.append(
                    {
                        "level": "error",
                        "location": dev_loc,
                        "message": f"位址必須為整數（目前值：{addr}）。",
                    }
                )
                continue

            # 保留位址檢查
            if addr < 0x08 or addr > 0x77:
                res_desc = RESERVED_I2C_ADDRESSES.get(addr, "保留位址")
                messages.append(
                    {
                        "level": "error",
                        "location": dev_loc,
                        "message": f"位址 0x{addr:02X} 屬於 I2C 保留位址範圍（0x00~0x07 或 0x78~0x7F；用途：{res_desc}）。標準從裝置位址範圍為 0x08~0x77。",
                    }
                )
            elif addr in bus_addrs:
                messages.append(
                    {
                        "level": "error",
                        "location": f"Bus #{bus_num}",
                        "message": f"位址衝突！「{dev_name}」與「{bus_addrs[addr]}」皆使用相同 7-bit 位址 0x{addr:02X}。",
                    }
                )
            else:
                bus_addrs[addr] = dev_name

            # 相容字串相容性檢查
            compat = str(dev.get("compatible", "")).strip()
            if not compat:
                messages.append(
                    {
                        "level": "error",
                        "location": dev_loc,
                        "message": "相容字串（compatible）不能為空。",
                    }
                )
            elif not _COMPATIBLE_REGEX.fullmatch(compat):
                messages.append(
                    {
                        "level": "error",
                        "location": dev_loc,
                        "message": f"相容字串「{compat}」格式無效，必須為 'vendor,device' 格式（例如：ti,tmp75 或 nxp,pca9555）。",
                    }
                )

            # 速度相容性檢查
            chip_model = dev.get("chip_model")
            if chip_model and chip_model in CHIP_PRESET_MAP:
                chip_speed = CHIP_PRESET_MAP[chip_model]["typical_speed_khz"]
                if bus_speed_khz > chip_speed:
                    messages.append(
                        {
                            "level": "warning",
                            "location": dev_loc,
                            "message": f"時鐘速度相容性警示：Bus 設定速度為 {bus_speed_khz} kHz，但晶片「{chip_model}」典型最高速度為 {chip_speed} kHz，高頻下可能通訊失真或無回應。",
                        }
                    )

        # 檢查 Mux 多工器
        for m_idx, mux in enumerate(bus.get("muxes", [])):
            mux_name = str(mux.get("name", "")).strip() or f"Mux-{m_idx + 1}"
            mux_loc = f"Bus #{bus_num} -> MUX「{mux_name}」"
            mux_addr = mux.get("address_7bit")

            if not isinstance(mux_addr, int):
                messages.append(
                    {
                        "level": "error",
                        "location": mux_loc,
                        "message": f"MUX 位址必須為整數（目前值：{mux_addr}）。",
                    }
                )
                continue

            if mux_addr < 0x08 or mux_addr > 0x77:
                res_desc = RESERVED_I2C_ADDRESSES.get(mux_addr, "保留位址")
                messages.append(
                    {
                        "level": "error",
                        "location": mux_loc,
                        "message": f"MUX 位址 0x{mux_addr:02X} 屬於 I2C 保留位址範圍（0x00~0x07 或 0x78~0x7F；用途：{res_desc}）。",
                    }
                )
            elif mux_addr in bus_addrs:
                messages.append(
                    {
                        "level": "error",
                        "location": f"Bus #{bus_num}",
                        "message": f"位址衝突！MUX「{mux_name}」與「{bus_addrs[mux_addr]}」皆使用相同 7-bit 位址 0x{mux_addr:02X}。",
                    }
                )
            else:
                bus_addrs[mux_addr] = f"MUX {mux_name}"

            mux_compat = str(mux.get("compatible", "")).strip()
            if not mux_compat:
                messages.append(
                    {
                        "level": "error",
                        "location": mux_loc,
                        "message": "MUX 相容字串（compatible）不能為空。",
                    }
                )
            elif not _COMPATIBLE_REGEX.fullmatch(mux_compat):
                messages.append(
                    {
                        "level": "error",
                        "location": mux_loc,
                        "message": f"MUX 相容字串「{mux_compat}」格式無效，必須為 'vendor,device' 格式（例如：nxp,pca9548）。",
                    }
                )

            # 4. Mux 各通道下裝置檢查
            channels = mux.get("channels", [])
            seen_channels: set[int] = set()
            for ch_dict in channels:
                ch = ch_dict.get("channel")
                if not isinstance(ch, int) or ch < 0 or ch > 7:
                    messages.append(
                        {
                            "level": "error",
                            "location": f"{mux_loc} -> 通道",
                            "message": f"MUX 通道編號必須介於 0 至 7 之間（目前值：{ch}）。",
                        }
                    )
                    continue

                if ch in seen_channels:
                    messages.append(
                        {
                            "level": "error",
                            "location": f"{mux_loc} -> 通道 {ch}",
                            "message": f"MUX 通道編號 {ch} 重複定義。",
                        }
                    )
                else:
                    seen_channels.add(ch)

                ch_addrs: dict[int, str] = {}
                for cd_idx, ch_dev in enumerate(ch_dict.get("devices", [])):
                    ch_dev_name = str(ch_dev.get("name", "")).strip() or f"Ch{ch}-Dev{cd_idx + 1}"
                    ch_dev_loc = f"{mux_loc} -> Channel {ch} ->「{ch_dev_name}」"
                    c_addr = ch_dev.get("address_7bit")

                    if not isinstance(c_addr, int):
                        messages.append(
                            {
                                "level": "error",
                                "location": ch_dev_loc,
                                "message": f"位址必須為整數（目前值：{c_addr}）。",
                            }
                        )
                        continue

                    if c_addr < 0x08 or c_addr > 0x77:
                        res_desc = RESERVED_I2C_ADDRESSES.get(c_addr, "保留位址")
                        messages.append(
                            {
                                "level": "error",
                                "location": ch_dev_loc,
                                "message": f"位址 0x{c_addr:02X} 屬於 I2C 保留位址範圍（用途：{res_desc}）。",
                            }
                        )
                    elif c_addr in ch_addrs:
                        messages.append(
                            {
                                "level": "error",
                                "location": f"{mux_loc} -> Channel {ch}",
                                "message": f"通道位址衝突！「{ch_dev_name}」與「{ch_addrs[c_addr]}」在相同 MUX 通道下皆使用位址 0x{c_addr:02X}。",
                            }
                        )
                    else:
                        ch_addrs[c_addr] = ch_dev_name

                    c_compat = str(ch_dev.get("compatible", "")).strip()
                    if not c_compat or not _COMPATIBLE_REGEX.fullmatch(c_compat):
                        messages.append(
                            {
                                "level": "error",
                                "location": ch_dev_loc,
                                "message": f"相容字串「{c_compat}」無效，必須為 'vendor,device' 格式。",
                            }
                        )

                    chip_model_ch = ch_dev.get("chip_model")
                    if chip_model_ch and chip_model_ch in CHIP_PRESET_MAP:
                        chip_speed_ch = CHIP_PRESET_MAP[chip_model_ch]["typical_speed_khz"]
                        if bus_speed_khz > chip_speed_ch:
                            messages.append(
                                {
                                    "level": "warning",
                                    "location": ch_dev_loc,
                                    "message": f"時鐘速度相容性警示：上游 Bus 速度為 {bus_speed_khz} kHz，高於晶片典型速度 {chip_speed_ch} kHz。",
                                }
                            )

    return messages


def editor_state_to_board_profile(state: dict[str, Any]) -> BoardProfile:
    """將表單狀態字典轉換為標準 Pydantic BoardProfile 物件。"""
    buses_payload: list[dict[str, Any]] = []

    for bus in state.get("buses", []):
        devs_payload: list[dict[str, Any]] = []
        for dev in bus.get("devices", []):
            devs_payload.append(
                {
                    "address_7bit": parse_address_integer(dev.get("address_7bit", 0x48)),
                    "name": str(dev.get("name", "dev")).strip(),
                    "category": str(dev.get("category", "sensor")).strip(),
                    "protocol": str(dev.get("protocol", "I2C")).strip(),
                    "compatible": str(dev.get("compatible", "generic,device")).strip(),
                    "register_width": int(dev.get("register_width", 8)),
                    "registers": [],
                    "commands": [],
                }
            )

        muxes_payload: list[dict[str, Any]] = []
        for mux in bus.get("muxes", []):
            channels_payload: list[dict[str, Any]] = []
            for ch_dict in mux.get("channels", []):
                ch_devs_payload: list[dict[str, Any]] = []
                for cd in ch_dict.get("devices", []):
                    ch_devs_payload.append(
                        {
                            "address_7bit": parse_address_integer(cd.get("address_7bit", 0x48)),
                            "name": str(cd.get("name", "dev")).strip(),
                            "category": str(cd.get("category", "sensor")).strip(),
                            "protocol": str(cd.get("protocol", "I2C")).strip(),
                            "compatible": str(cd.get("compatible", "generic,device")).strip(),
                            "register_width": int(cd.get("register_width", 8)),
                            "registers": [],
                            "commands": [],
                        }
                    )
                channels_payload.append(
                    {
                        "channel": int(ch_dict.get("channel", 0)),
                        "devices": ch_devs_payload,
                    }
                )

            muxes_payload.append(
                {
                    "address_7bit": parse_address_integer(mux.get("address_7bit", 0x70)),
                    "name": str(mux.get("name", "mux")).strip(),
                    "category": str(mux.get("category", "i2c-mux")).strip(),
                    "protocol": str(mux.get("protocol", "I2C")).strip(),
                    "compatible": str(mux.get("compatible", "nxp,pca9548")).strip(),
                    "register_width": int(mux.get("register_width", 8)),
                    "registers": [],
                    "commands": [],
                    "channels": channels_payload,
                }
            )

        buses_payload.append(
            {
                "bus_num": int(bus.get("bus_num", 0)),
                "speed_mode": str(bus.get("speed_mode", "standard")),
                "devices": devs_payload,
                "muxes": muxes_payload,
            }
        )

    data = {
        "board_name": str(state.get("board_name", "MyBoard")).strip(),
        "version": str(state.get("version", "1.0")).strip(),
        "i2c_buses": buses_payload,
    }

    return BoardProfile.from_mapping(data)


def editor_state_to_yaml(state: dict[str, Any]) -> str:
    """根據編輯器狀態產生格式化且帶有十六進位位址的 YAML 字串。"""
    # 建立結構以進行十六進位包裝
    buses_list: list[dict[str, Any]] = []

    for bus in state.get("buses", []):
        dev_list: list[dict[str, Any]] = []
        for dev in bus.get("devices", []):
            addr = parse_address_integer(dev.get("address_7bit", 0x48))
            dev_entry: dict[str, Any] = {
                "address_7bit": HexInt(addr),
                "name": str(dev.get("name", "")).strip(),
                "category": str(dev.get("category", "")).strip(),
                "protocol": str(dev.get("protocol", "")).strip(),
                "compatible": str(dev.get("compatible", "")).strip(),
                "register_width": int(dev.get("register_width", 8)),
                "registers": [],
                "commands": [],
            }
            dev_list.append(dev_entry)

        mux_list: list[dict[str, Any]] = []
        for mux in bus.get("muxes", []):
            mux_addr = parse_address_integer(mux.get("address_7bit", 0x70))
            channels_list: list[dict[str, Any]] = []
            for ch in mux.get("channels", []):
                ch_dev_list: list[dict[str, Any]] = []
                for cd in ch.get("devices", []):
                    cd_addr = parse_address_integer(cd.get("address_7bit", 0x48))
                    ch_dev_list.append(
                        {
                            "address_7bit": HexInt(cd_addr),
                            "name": str(cd.get("name", "")).strip(),
                            "category": str(cd.get("category", "")).strip(),
                            "protocol": str(cd.get("protocol", "")).strip(),
                            "compatible": str(cd.get("compatible", "")).strip(),
                            "register_width": int(cd.get("register_width", 8)),
                            "registers": [],
                            "commands": [],
                        }
                    )
                channels_list.append(
                    {
                        "channel": int(ch.get("channel", 0)),
                        "devices": ch_dev_list,
                    }
                )

            mux_entry: dict[str, Any] = {
                "address_7bit": HexInt(mux_addr),
                "name": str(mux.get("name", "")).strip(),
                "category": str(mux.get("category", "i2c-mux")).strip(),
                "protocol": str(mux.get("protocol", "I2C")).strip(),
                "compatible": str(mux.get("compatible", "nxp,pca9548")).strip(),
                "register_width": int(mux.get("register_width", 8)),
                "registers": [],
                "commands": [],
                "channels": channels_list,
            }
            mux_list.append(mux_entry)

        bus_entry: dict[str, Any] = {
            "bus_num": int(bus.get("bus_num", 0)),
            "speed_mode": str(bus.get("speed_mode", "standard")),
            "devices": dev_list,
        }
        if mux_list:
            bus_entry["muxes"] = mux_list

        buses_list.append(bus_entry)

    doc: dict[str, Any] = {
        "board_name": str(state.get("board_name", "MyBoard")).strip(),
        "version": str(state.get("version", "1.0")).strip(),
        "i2c_buses": buses_list,
    }

    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def board_profile_to_editor_state(profile: BoardProfile) -> dict[str, Any]:
    """將已解析的 BoardProfile 物件反向轉換為編輯器狀態字典。"""
    buses_state: list[dict[str, Any]] = []

    for bus in profile.i2c_buses:
        devs_state: list[dict[str, Any]] = []
        for dev in bus.devices:
            # 嘗試找尋 CHIP_DATABASE 中相符的晶片
            matching_chip_name = None
            for chip_name, preset in CHIP_PRESET_MAP.items():
                if (
                    preset["compatible"] == dev.compatible
                    or dev.address_7bit in preset["addr_7bit_range"]
                ):
                    matching_chip_name = chip_name
                    break

            devs_state.append(
                {
                    "name": dev.name,
                    "address_7bit": dev.address_7bit,
                    "category": dev.category,
                    "protocol": dev.protocol,
                    "compatible": dev.compatible,
                    "register_width": dev.register_width,
                    "chip_model": matching_chip_name or "自訂裝置（Custom）",
                }
            )

        muxes_state: list[dict[str, Any]] = []
        for mux in bus.muxes:
            channels_state: list[dict[str, Any]] = []
            for ch in mux.channels:
                ch_devs_state: list[dict[str, Any]] = []
                for cd in ch.devices:
                    matching_cd_chip = None
                    for chip_name, preset in CHIP_PRESET_MAP.items():
                        if (
                            preset["compatible"] == cd.compatible
                            or cd.address_7bit in preset["addr_7bit_range"]
                        ):
                            matching_cd_chip = chip_name
                            break

                    ch_devs_state.append(
                        {
                            "name": cd.name,
                            "address_7bit": cd.address_7bit,
                            "category": cd.category,
                            "protocol": cd.protocol,
                            "compatible": cd.compatible,
                            "register_width": cd.register_width,
                            "chip_model": matching_cd_chip or "自訂裝置（Custom）",
                        }
                    )
                channels_state.append(
                    {
                        "channel": ch.channel,
                        "devices": ch_devs_state,
                    }
                )

            muxes_state.append(
                {
                    "name": mux.name,
                    "address_7bit": mux.address_7bit,
                    "category": mux.category,
                    "protocol": mux.protocol,
                    "compatible": mux.compatible,
                    "register_width": mux.register_width,
                    "num_channels": len(channels_state) if channels_state else 8,
                    "channels": channels_state,
                }
            )

        buses_state.append(
            {
                "bus_num": bus.bus_num,
                "speed_mode": bus.speed_mode,
                "devices": devs_state,
                "muxes": muxes_state,
            }
        )

    return {
        "board_name": profile.board_name,
        "version": profile.version,
        "description": "",
        "buses": buses_state,
    }


def yaml_to_editor_state(yaml_text: str) -> dict[str, Any]:
    """解析 YAML 文字並轉換為編輯器狀態字典。"""
    profile = load_board_profile(yaml_text)
    return board_profile_to_editor_state(profile)


def render() -> None:
    """Streamlit Board Profile 視覺化編輯器頁面入口。"""
    st.header("Board Profile 視覺化拓撲編輯器（Board Profile Visual Editor）")
    st.caption(
        "表單式定義硬體主機板之 I2C 匯流排、周邊晶片與 MUX 多工器拓撲，即時產生標準 YAML 設定檔，"
        "並提供位址衝突、保留位址與時鐘相容性自動防錯驗證。"
    )
    render_guide_expander(
        "chapters/ch01_i2c_pmbus.md",
        "📖 點擊展開：I2C 拓撲與 Board Profile 規範說明",
    )

    # 初始化 session_state 中的編輯器狀態
    if "board_profile_editor_state" not in st.session_state:
        st.session_state["board_profile_editor_state"] = get_default_editor_state()

    state = st.session_state["board_profile_editor_state"]

    # 頂部操作工具列（預設範本載入與重置）
    t_col1, t_col2, t_col3, t_col4 = st.columns(4)
    with t_col1:
        if st.button("📋 載入 YV4 參考範本", use_container_width=True):
            st.session_state["board_profile_editor_state"] = get_default_editor_state()
            st.rerun()
    with t_col2:
        if st.button("⚡ 載入單 Bus 簡易範本", use_container_width=True):
            st.session_state["board_profile_editor_state"] = {
                "board_name": "Simple-Carrier-Card",
                "version": "0.1",
                "description": "單 Bus 溫測與 EEPROM 簡易板卡",
                "buses": [
                    {
                        "bus_num": 0,
                        "speed_mode": "fast",
                        "devices": [
                            {
                                "name": "temp-sensor",
                                "address_7bit": 0x48,
                                "category": "temperature-sensor",
                                "protocol": "I2C",
                                "compatible": "ti,tmp75",
                                "register_width": 8,
                                "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                            },
                            {
                                "name": "board-eeprom",
                                "address_7bit": 0x50,
                                "category": "eeprom",
                                "protocol": "EEPROM",
                                "compatible": "atmel,24c64",
                                "register_width": 8,
                                "chip_model": "AT24Cxx / 24LCxx EEPROM",
                            },
                        ],
                        "muxes": [],
                    }
                ],
            }
            st.rerun()
    with t_col3:
        if st.button("➕ 新增 I2C Bus", use_container_width=True):
            existing_buses = state.get("buses", [])
            next_bus_num = (
                max([b.get("bus_num", 0) for b in existing_buses], default=-1) + 1
                if existing_buses
                else 0
            )
            existing_buses.append(
                {
                    "bus_num": next_bus_num,
                    "speed_mode": "fast",
                    "devices": [],
                    "muxes": [],
                }
            )
            st.session_state["board_profile_editor_state"]["buses"] = existing_buses
            st.rerun()
    with t_col4:
        if st.button("🗑 清空所有 Bus", use_container_width=True):
            st.session_state["board_profile_editor_state"]["buses"] = []
            st.rerun()

    st.divider()

    left_col, right_col = st.columns([3, 2])

    # ==========================
    # 左側：表單編輯區
    # ==========================
    with left_col:
        st.subheader("🛠 板卡基本資訊與 I2C 拓撲表單")

        # 1. 基本資訊區塊
        with st.container(border=True):
            st.markdown("##### 📌 基本資訊（Board Metadata）")
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                state["board_name"] = st.text_input(
                    "主機板名稱（Board Name）",
                    value=state.get("board_name", "MyBoard"),
                    help="建議使用英數字與減號命名，例如 YV4-CraterLake-reference",
                )
            with m_col2:
                state["version"] = st.text_input(
                    "設定檔版本（Version）",
                    value=state.get("version", "1.0"),
                    help="例如 1.0 或 2.1",
                )
            state["description"] = st.text_input(
                "描述備註（Description；選填）",
                value=state.get("description", ""),
                help="板卡用途說明，僅供 UI 與註解參考",
            )

        # 2. I2C Bus 清單
        buses = state.get("buses", [])
        if not buses:
            st.info("目前尚無任何 I2C Bus，請點擊上方「➕ 新增 I2C Bus」按鈕開始建立拓撲。")

        for b_idx, bus in enumerate(buses):
            with st.container(border=True):
                b_head_col1, b_head_col2 = st.columns([4, 1])
                with b_head_col1:
                    st.markdown(f"#### 🌐 I2C Bus #{bus.get('bus_num', b_idx)}")
                with b_head_col2:
                    if st.button(
                        "🗑 刪除 Bus",
                        key=f"del_bus_{b_idx}",
                        use_container_width=True,
                    ):
                        buses.pop(b_idx)
                        st.session_state["board_profile_editor_state"]["buses"] = buses
                        st.rerun()

                # Bus 設定
                b_cfg1, b_cfg2 = st.columns(2)
                with b_cfg1:
                    bus["bus_num"] = int(
                        st.number_input(
                            "Bus 編號（bus_num）",
                            min_value=0,
                            max_value=65535,
                            value=int(bus.get("bus_num", b_idx)),
                            step=1,
                            key=f"bus_num_{b_idx}",
                        )
                    )
                with b_cfg2:
                    current_speed = bus.get("speed_mode", "fast")
                    speed_idx = (
                        SPEED_MODE_OPTIONS.index(current_speed)
                        if current_speed in SPEED_MODE_OPTIONS
                        else 1
                    )
                    bus["speed_mode"] = st.selectbox(
                        "匯流排速度模式（speed_mode）",
                        SPEED_MODE_OPTIONS,
                        index=speed_idx,
                        format_func=lambda s: SPEED_MODE_MAP.get(s, (s, 0))[0],
                        key=f"speed_mode_{b_idx}",
                    )

                st.divider()

                # 直連裝置（Direct Devices）
                st.markdown("##### 🔌 直連周邊裝置（Direct Devices）")
                devices = bus.get("devices", [])

                for d_idx, dev in enumerate(devices):
                    with st.container(border=True):
                        d_head1, d_head2 = st.columns([4, 1])
                        with d_head1:
                            st.markdown(
                                f"**裝置 #{d_idx + 1}：{dev.get('name', '未命名')}（{format_hex_address(parse_address_integer(dev.get('address_7bit', 0x48)))}）**"
                            )
                        with d_head2:
                            if st.button(
                                "🗑 移除",
                                key=f"del_dev_{b_idx}_{d_idx}",
                                use_container_width=True,
                            ):
                                devices.pop(d_idx)
                                bus["devices"] = devices
                                st.session_state["board_profile_editor_state"]["buses"] = buses
                                st.rerun()

                        # 晶片型號選擇
                        chip_options = ["自訂裝置（Custom）"] + list(CHIP_PRESET_MAP.keys())
                        cur_chip = dev.get("chip_model", "自訂裝置（Custom）")
                        c_idx = chip_options.index(cur_chip) if cur_chip in chip_options else 0

                        selected_chip = st.selectbox(
                            "常用晶片型號（從資料庫載入預設）",
                            chip_options,
                            index=c_idx,
                            key=f"chip_select_{b_idx}_{d_idx}",
                        )

                        # 當切換晶片時更新預設值
                        if selected_chip != cur_chip and selected_chip != "自訂裝置（Custom）":
                            preset = CHIP_PRESET_MAP[selected_chip]
                            dev["chip_model"] = selected_chip
                            dev["name"] = preset["name"]
                            dev["category"] = preset["category"]
                            dev["protocol"] = preset["protocol"]
                            dev["compatible"] = preset["compatible"]
                            dev["register_width"] = preset["register_width"]
                            dev["address_7bit"] = preset["default_addr"]
                            st.rerun()

                        d_row1_1, d_row1_2 = st.columns(2)
                        with d_row1_1:
                            dev["name"] = st.text_input(
                                "裝置識別名稱（name）",
                                value=dev.get("name", "sensor"),
                                key=f"dev_name_{b_idx}_{d_idx}",
                            )
                        with d_row1_2:
                            addr_raw = st.text_input(
                                "7-bit I2C 位址（address_7bit；支援 0xNN 或十進位）",
                                value=format_hex_address(
                                    parse_address_integer(dev.get("address_7bit", 0x48))
                                ),
                                key=f"dev_addr_{b_idx}_{d_idx}",
                            )
                            dev["address_7bit"] = parse_address_integer(
                                addr_raw, dev.get("address_7bit", 0x48)
                            )

                        d_row2_1, d_row2_2 = st.columns(2)
                        with d_row2_1:
                            dev["category"] = st.text_input(
                                "類別（category）",
                                value=dev.get("category", "temperature-sensor"),
                                key=f"dev_cat_{b_idx}_{d_idx}",
                            )
                        with d_row2_2:
                            proto_opts = ["I2C", "SMBus", "PMBus", "EEPROM"]
                            cur_p = dev.get("protocol", "I2C")
                            p_idx = proto_opts.index(cur_p) if cur_p in proto_opts else 0
                            dev["protocol"] = st.selectbox(
                                "協定（protocol）",
                                proto_opts,
                                index=p_idx,
                                key=f"dev_proto_{b_idx}_{d_idx}",
                            )

                        d_row3_1, d_row3_2 = st.columns(2)
                        with d_row3_1:
                            dev["compatible"] = st.text_input(
                                "相容字串（compatible；vendor,device）",
                                value=dev.get("compatible", "ti,tmp75"),
                                key=f"dev_compat_{b_idx}_{d_idx}",
                            )
                        with d_row3_2:
                            w_opts = [8, 16]
                            cur_w = dev.get("register_width", 8)
                            w_idx = w_opts.index(cur_w) if cur_w in w_opts else 0
                            dev["register_width"] = st.selectbox(
                                "暫存器寬度（register_width；bits）",
                                w_opts,
                                index=w_idx,
                                key=f"dev_regw_{b_idx}_{d_idx}",
                            )

                if st.button("➕ 新增直連裝置", key=f"add_dev_{b_idx}"):
                    devices.append(
                        {
                            "name": f"sensor-{len(devices) + 1}",
                            "address_7bit": 0x48,
                            "category": "temperature-sensor",
                            "protocol": "I2C",
                            "compatible": "ti,tmp75",
                            "register_width": 8,
                            "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                        }
                    )
                    bus["devices"] = devices
                    st.session_state["board_profile_editor_state"]["buses"] = buses
                    st.rerun()

                st.divider()

                # I2C Mux 多工器
                st.markdown("##### 🔀 I2C MUX 多工器（例如 PCA9548A）")
                muxes = bus.get("muxes", [])

                for m_idx, mux in enumerate(muxes):
                    with st.container(border=True):
                        m_head1, m_head2 = st.columns([4, 1])
                        with m_head1:
                            st.markdown(
                                f"**MUX #{m_idx + 1}：{mux.get('name', '未命名')}（{format_hex_address(parse_address_integer(mux.get('address_7bit', 0x70)))}）**"
                            )
                        with m_head2:
                            if st.button(
                                "🗑 移除 MUX",
                                key=f"del_mux_{b_idx}_{m_idx}",
                                use_container_width=True,
                            ):
                                muxes.pop(m_idx)
                                bus["muxes"] = muxes
                                st.session_state["board_profile_editor_state"]["buses"] = buses
                                st.rerun()

                        m_row1_1, m_row1_2 = st.columns(2)
                        with m_row1_1:
                            mux["name"] = st.text_input(
                                "MUX 名稱（name）",
                                value=mux.get("name", "board-mux"),
                                key=f"mux_name_{b_idx}_{m_idx}",
                            )
                        with m_row1_2:
                            m_addr_raw = st.text_input(
                                "MUX 7-bit 位址（address_7bit）",
                                value=format_hex_address(
                                    parse_address_integer(mux.get("address_7bit", 0x70))
                                ),
                                key=f"mux_addr_{b_idx}_{m_idx}",
                            )
                            mux["address_7bit"] = parse_address_integer(
                                m_addr_raw, mux.get("address_7bit", 0x70)
                            )

                        m_row2_1, m_row2_2 = st.columns(2)
                        with m_row2_1:
                            mux["compatible"] = st.text_input(
                                "MUX 相容字串（compatible）",
                                value=mux.get("compatible", "nxp,pca9548"),
                                key=f"mux_compat_{b_idx}_{m_idx}",
                            )
                        with m_row2_2:
                            ch_count = int(
                                st.number_input(
                                    "通道數量（Channels 1~8）",
                                    min_value=1,
                                    max_value=8,
                                    value=int(mux.get("num_channels", 8)),
                                    step=1,
                                    key=f"mux_ch_count_{b_idx}_{m_idx}",
                                )
                            )
                            mux["num_channels"] = ch_count

                        # Mux 通道編輯
                        channels = mux.get("channels", [])
                        channel_map = {c.get("channel"): c for c in channels if "channel" in c}

                        st.caption("MUX 下游各通道裝置配置：")
                        for ch_num in range(ch_count):
                            with st.expander(
                                f"📍 通道 {ch_num}（Channel {ch_num}）", expanded=False
                            ):
                                if ch_num not in channel_map:
                                    channel_map[ch_num] = {
                                        "channel": ch_num,
                                        "devices": [],
                                    }
                                ch_entry = channel_map[ch_num]
                                ch_devs = ch_entry.get("devices", [])

                                for cd_idx, cd in enumerate(ch_devs):
                                    with st.container(border=True):
                                        cd_h1, cd_h2 = st.columns([4, 1])
                                        with cd_h1:
                                            st.markdown(
                                                f"**裝置：{cd.get('name', '未命名')}（{format_hex_address(parse_address_integer(cd.get('address_7bit', 0x48)))}）**"
                                            )
                                        with cd_h2:
                                            if st.button(
                                                "🗑",
                                                key=f"del_ch_dev_{b_idx}_{m_idx}_{ch_num}_{cd_idx}",
                                            ):
                                                ch_devs.pop(cd_idx)
                                                st.session_state["board_profile_editor_state"][
                                                    "buses"
                                                ] = buses
                                                st.rerun()

                                        cd_c1, cd_c2 = st.columns(2)
                                        with cd_c1:
                                            cd["name"] = st.text_input(
                                                "名稱",
                                                value=cd.get("name", f"temp-ch{ch_num}"),
                                                key=f"cd_name_{b_idx}_{m_idx}_{ch_num}_{cd_idx}",
                                            )
                                        with cd_c2:
                                            cd_addr_raw = st.text_input(
                                                "位址（0xNN）",
                                                value=format_hex_address(
                                                    parse_address_integer(
                                                        cd.get("address_7bit", 0x48)
                                                    )
                                                ),
                                                key=f"cd_addr_{b_idx}_{m_idx}_{ch_num}_{cd_idx}",
                                            )
                                            cd["address_7bit"] = parse_address_integer(
                                                cd_addr_raw, cd.get("address_7bit", 0x48)
                                            )

                                        cd_c3, cd_c4 = st.columns(2)
                                        with cd_c3:
                                            cd["category"] = st.text_input(
                                                "類別",
                                                value=cd.get("category", "temperature-sensor"),
                                                key=f"cd_cat_{b_idx}_{m_idx}_{ch_num}_{cd_idx}",
                                            )
                                        with cd_c4:
                                            cd["compatible"] = st.text_input(
                                                "相容字串",
                                                value=cd.get("compatible", "ti,tmp75"),
                                                key=f"cd_compat_{b_idx}_{m_idx}_{ch_num}_{cd_idx}",
                                            )

                                if st.button(
                                    f"➕ 新增裝置至通道 {ch_num}",
                                    key=f"add_ch_dev_{b_idx}_{m_idx}_{ch_num}",
                                ):
                                    ch_devs.append(
                                        {
                                            "name": f"dev-ch{ch_num}-{len(ch_devs) + 1}",
                                            "address_7bit": 0x48,
                                            "category": "temperature-sensor",
                                            "protocol": "I2C",
                                            "compatible": "ti,tmp75",
                                            "register_width": 8,
                                            "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                                        }
                                    )
                                    ch_entry["devices"] = ch_devs
                                    st.session_state["board_profile_editor_state"]["buses"] = buses
                                    st.rerun()

                        # 僅保留有效通道清單
                        mux["channels"] = [
                            channel_map[i]
                            for i in range(ch_count)
                            if i in channel_map and channel_map[i].get("devices")
                        ]

                if st.button("➕ 新增 I2C MUX 多工器", key=f"add_mux_{b_idx}"):
                    muxes.append(
                        {
                            "name": f"mux-{len(muxes) + 1}",
                            "address_7bit": 0x70 + len(muxes),
                            "category": "i2c-mux",
                            "protocol": "I2C",
                            "compatible": "nxp,pca9548",
                            "register_width": 8,
                            "num_channels": 8,
                            "channels": [
                                {
                                    "channel": 0,
                                    "devices": [
                                        {
                                            "name": "inlet-temp",
                                            "address_7bit": 0x48,
                                            "category": "temperature-sensor",
                                            "protocol": "I2C",
                                            "compatible": "ti,tmp75",
                                            "register_width": 8,
                                            "chip_model": "LM75 / TMP75 / TMP102 Temperature Sensor",
                                        }
                                    ],
                                }
                            ],
                        }
                    )
                    bus["muxes"] = muxes
                    st.session_state["board_profile_editor_state"]["buses"] = buses
                    st.rerun()

    # ==========================
    # 右側：即時驗證、YAML 預覽與匯入
    # ==========================
    with right_col:
        st.subheader("🔍 即時拓撲驗證與 YAML 產出")

        # 1. 驗證與健康檢查面板
        with st.container(border=True):
            st.markdown("##### 🛡 拓撲相容性與位址防錯檢查")
            validation_messages = validate_editor_state(state)

            errors = [m for m in validation_messages if m["level"] == "error"]
            warnings = [m for m in validation_messages if m["level"] == "warning"]

            if not errors and not warnings:
                st.success("✅ 拓撲驗證通過！無位址衝突、無保留位址濫用、時鐘相容性正常。")
            else:
                if errors:
                    st.error(f"❌ 發現 {len(errors)} 個嚴重錯誤（YAML 無法通過 Pydantic 驗證）：")
                    for err in errors:
                        st.markdown(f"- **[{err['location']}]**：{err['message']}")
                if warnings:
                    st.warning(f"⚠️ 發現 {len(warnings)} 個相容性警示：")
                    for w in warnings:
                        st.markdown(f"- **[{w['location']}]**：{w['message']}")

        # 2. 即時 YAML 預覽與下載
        with st.container(border=True):
            st.markdown("##### 📄 即時 Board Profile YAML")
            yaml_content = editor_state_to_yaml(state)

            st.code(yaml_content, language="yaml")

            # 下載按鈕
            filename = f"{state.get('board_name', 'board_profile')}.yaml"
            st.download_button(
                "💾 下載 board_profile.yaml",
                data=yaml_content,
                file_name=filename,
                mime="application/x-yaml",
                use_container_width=True,
                disabled=bool(errors),
            )
            if errors:
                st.caption("⚠️ 拓撲存在錯誤時仍可複製預覽，但建議修正錯誤後再下載使用。")

        # 3. YAML 匯入與反向解析
        with st.container(border=True):
            st.markdown("##### 📥 既有 YAML 匯入（反向解析填入表單）")
            uploaded_yaml = st.file_uploader(
                "上傳 board_profile.yaml 檔案",
                type=["yaml", "yml", "json"],
                key="bp_upload_file",
            )
            pasted_yaml = st.text_area(
                "或貼上 YAML 文字內容",
                height=120,
                max_chars=MAX_TEXT_BYTES,
                key="bp_paste_text",
            )

            if st.button("📥 執行匯入並套用至表單", use_container_width=True):
                target_text = ""
                if uploaded_yaml is not None:
                    try:
                        target_text = decode_uploaded_text(
                            uploaded_yaml, allowed_extensions={".yaml", ".yml", ".json"}
                        )
                    except ValueError as exc:
                        st.error(f"檔案讀取失敗：{exc}")
                elif pasted_yaml.strip():
                    try:
                        target_text = validate_pasted_text(pasted_yaml, label="Board Profile YAML")
                    except ValueError as exc:
                        st.error(f"貼上文字錯誤：{exc}")

                if target_text:
                    try:
                        parsed_state = yaml_to_editor_state(target_text)
                        st.session_state["board_profile_editor_state"] = parsed_state
                        st.success("🎉 成功匯入並解析 Board Profile！表單已更新。")
                        st.rerun()
                    except (SchemaError, ValueError, yaml.YAMLError) as exc:
                        st.error(f"YAML 解析失敗：{exc}")


__all__ = ["render"]
