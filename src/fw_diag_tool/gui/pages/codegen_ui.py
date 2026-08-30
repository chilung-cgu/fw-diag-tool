from __future__ import annotations

from pathlib import Path

import streamlit as st

from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    render_guide_expander,
    render_page_footer,
)


def render() -> None:
    st.header("YAML 暫存器定義檔轉換為 C 語言標頭檔（C header；#define／RMW 巨集）")
    render_guide_expander(
        "chapters/ch09_register_codegen.md", "📖 點擊展開：C 語言 Register 巨集產生器教學"
    )
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    if not data_dir.exists():
        data_dir = Path(__file__).resolve().parent.parent / "data"
    builtin_yamls = list(data_dir.glob("*.yaml"))
    choice_yaml = st.selectbox("選擇 YAML 範本", [y.name for y in builtin_yamls])
    mod_name = st.text_input(
        "模組名稱（Module Name）",
        value=choice_yaml.replace(".yaml", "").upper() if choice_yaml else "",
    )
    try:
        if not choice_yaml:
            raise ValueError("未找到可用的 YAML 範本")
        gen = CHeaderGenerator.from_yaml_file(data_dir / choice_yaml)
        c_header = gen.generate_header(module_name=mod_name)
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"C 標頭檔輸入錯誤（C header）：{_localize_gui_error(exc, domain='c_header')}")
    else:
        st.info(
            "這是可編輯的 C 語言標頭檔起始模板（C header template）；套用到驅動程式（driver）前，"
            "請依資料表（datasheet）、暫存器存取政策（register access policy）、編譯器警告 "
            "（compiler warnings）與 MISRA checker 重新驗證；輸出不是已驗證的 production driver。"
        )
        st.code(c_header, language="c")
        header_filename = CHeaderGenerator.header_filename(mod_name)
        st.download_button(
            f"下載 {header_filename}",
            c_header,
            file_name=header_filename,
            mime="text/x-c",
        )

    render_page_footer()
