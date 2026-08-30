from __future__ import annotations

import streamlit as st
import yaml

from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    render_guide_expander,
    render_page_footer,
)
from fw_diag_tool.gui.uploads import (
    MAX_TEXT_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)


def render() -> None:
    st.header("Linux Kernel／OpenBMC Device Tree Source（.dts）自動產生")
    render_guide_expander("chapters/ch06_dts_generator.md", "📖 點擊展開：Device Tree 產生器教學")
    dt_b1, dt_b2, dt_b3 = st.columns(3)
    with dt_b1:
        dts_bus = st.number_input(
            "I2C 匯流排編號（Bus Number；&i2c...）", min_value=0, max_value=65535, value=1
        )
    with dt_b2:
        dts_mux = st.text_input("PCA9548A MUX 位址（MUX Address）", value="0x70")
    with dt_b3:
        dts_clock = st.number_input(
            "時鐘頻率（clock-frequency；Hz）", min_value=1, value=400000, step=10000
        )
    dts_mux_compatible = st.text_input("多工器相容字串（MUX compatible）", value="nxp,pca9548")
    uploaded_dts = st.file_uploader(
        "上傳裝置清單 YAML 檔案",
        type=["yaml", "yml"],
    )
    dts_pasted_text = st.text_area(
        "裝置清單（YAML；每個 device 必須有 addr/channel/name/compatible）",
        value=(
            "- addr: 0x50\n"
            "  channel: 0\n"
            "  name: eeprom\n"
            "  compatible: atmel,24c64\n"
            "- addr: 0x48\n"
            "  channel: 1\n"
            "  name: temp-sensor\n"
            "  compatible: national,lm75\n"
        ),
        height=180,
        max_chars=MAX_TEXT_BYTES,
    )
    dts_devices_text = dts_pasted_text
    if uploaded_dts is not None:
        try:
            dts_devices_text = decode_uploaded_text(
                uploaded_dts,
                allowed_extensions={".yaml", ".yml"},
            )
        except ValueError as exc:
            st.error(f"YAML 檔案讀取錯誤：{exc}")
    if st.button("產生 Device Tree（.dts）"):
        try:
            devices = (
                yaml.safe_load(validate_pasted_text(dts_devices_text, label="Device Tree YAML"))
                or []
            )
            dts_code = DeviceTreeGenerator.generate_dts_from_topology(
                bus_num=int(dts_bus),
                mux_addr=dts_mux,
                devices=devices,
                clock_frequency=int(dts_clock),
                mux_compatible=dts_mux_compatible,
            )
            st.code(dts_code, language="dts")
            st.download_button(
                "下載 i2c_bus.dtsi",
                dts_code,
                file_name=f"i2c_bus{int(dts_bus)}.dtsi",
                mime="text/plain",
            )
        except (TypeError, ValueError, yaml.YAMLError) as exc:
            st.error(f"DTS 輸入錯誤：{_localize_gui_error(exc, domain='dts')}")

    render_page_footer()


__all__ = ["render"]
