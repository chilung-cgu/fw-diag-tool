from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    _localize_register_description,
    _localize_register_meaning,
    render_guide_expander,
)
from fw_diag_tool.gui.uploads import decode_uploaded_text

CUSTOM_YAML_OPTION = "上傳自訂暫存器定義 YAML"


def render() -> None:
    st.header("硬體／晶片暫存器 Bitfield 視覺化解碼器（Register Decoder）")
    render_guide_expander(
        "chapters/ch09_register_codegen.md", "📖 點擊展開：暫存器 Bitfield 解碼教學"
    )
    builtin_map = {
        "PMBus 標準狀態暫存器（PMBus STATUS_WORD）": "pmbus_standard.yaml",
        "PCIe AER 不可修正錯誤暫存器（Uncorrectable Error）": "pcie_aer_registers.yaml",
    }
    choice = st.selectbox(
        "選擇預設暫存器定義檔",
        list(builtin_map.keys()) + [CUSTOM_YAML_OPTION],
    )
    catalog = RegisterMapCatalog()

    if choice == CUSTOM_YAML_OPTION:
        uploaded_yaml = st.file_uploader("上傳自訂 YAML 定義檔", type=["yaml", "yml"])
        if uploaded_yaml is not None:
            try:
                content = decode_uploaded_text(uploaded_yaml, allowed_extensions={".yaml", ".yml"})
                catalog.load_from_yaml(content)
            except Exception as exc:
                st.error(f"自訂 YAML 載入失敗：{_localize_gui_error(exc, domain='register')}")
        else:
            st.info("請上傳 YAML 暫存器定義檔以開始解碼。")
    else:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        if not data_dir.exists():
            data_dir = Path(__file__).resolve().parent.parent / "data"
        yaml_file = data_dir / builtin_map[choice]
        if yaml_file.exists():
            try:
                catalog.load_from_yaml(yaml_file.read_text(encoding="utf-8"))
            except Exception as exc:
                st.error(f"暫存器定義檔載入失敗：{_localize_gui_error(exc, domain='register')}")

    reg_names = list(catalog.name_map.keys())
    if reg_names:
        r1, r2 = st.columns(2)
        with r1:
            sel_reg = st.selectbox("選擇暫存器", [r.upper() for r in reg_names])
        with r2:
            raw_val_str = st.text_input(
                "輸入暫存器原始十六進位值（Raw Hex；例如 0x8400、0x00040000）",
                value="0x8400",
            )
        try:
            cur_val = int(raw_val_str, 0)
        except ValueError:
            st.error("暫存器值格式錯誤；請輸入整數或 0x 開頭的十六進位值。")
        else:
            try:
                res = catalog.decode_register(sel_reg, cur_val)
            except (TypeError, ValueError) as exc:
                st.error(f"暫存器值無法解碼：{_localize_gui_error(exc, domain='register')}")
            else:
                st.subheader(f"{res.reg_name} (0x{cur_val:08X})")
                if res.description:
                    st.caption(
                        f"暫存器說明（Description）：{_localize_register_description(res.description)}"
                    )
                st.table(
                    pd.DataFrame(
                        [
                            {
                                "位元範圍（Bit Range）": f.bit_range,
                                "欄位（Field）": f.name,
                                "值（Value）": f.hex_val,
                                "存取權限（Access）": f.access,
                                "意義（Meaning）": (
                                    f"⚠ {_localize_register_meaning(f.meaning)}"
                                    if f.is_warning
                                    else _localize_register_meaning(f.meaning)
                                ),
                            }
                            for f in res.fields
                        ]
                    )
                )
                unmapped_text = f"0x{res.unmapped_bits:08X}"
                if res.unmapped_bits:
                    st.warning(
                        f"有未對應位元（Unmapped bits）：{unmapped_text}；"
                        "這些位元沒有出現在目前 YAML 定義，請回到 datasheet 確認。"
                    )
                else:
                    st.caption("未對應位元（Unmapped bits）：0x00000000")


__all__ = ["render"]
