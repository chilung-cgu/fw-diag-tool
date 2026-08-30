from __future__ import annotations

import pandas as pd
import streamlit as st

from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.gui.pages.i2c_builder import (
    I2C_BUILDER_PRESETS,
    MAX_BUILDER_DATA_BYTES,
    MAX_BUILDER_WAVEFORM_POINTS,
    build_i2c_bundle,
    max_write_data_bytes,
    parse_hex_bytes,
    parse_hex_integer,
    preset_widget_state,
)
from fw_diag_tool.gui.shared import (
    MAX_PACKET_HEX_CHARS,
    _localize_gui_error,
    render_guide_expander,
)
from fw_diag_tool.i2c.localization import localize_direction, localize_platform, localize_preset
from fw_diag_tool.i2c.transfer_spec import Endianness, I2CTransferOperation, I2CTransferSpec
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor


def render() -> None:
    st.header("I2C 封包自訂建構、理想波形生成與多平台 C 驅動產出")
    st.caption(
        "這一頁由同一份已驗證的傳輸規格（transfer spec）產生協定示意與程式碼模板；"
        "它不會連線或執行硬體命令，也不是硬體量測。"
    )
    render_guide_expander(
        "chapters/ch02_packet_builder.md", "📖 點擊展開：I2C 封包模擬器與 C 驅動產出教學"
    )

    default_preset_name = next(iter(I2C_BUILDER_PRESETS))
    for state_key, state_value in preset_widget_state(
        I2C_BUILDER_PRESETS[default_preset_name]
    ).items():
        if state_key not in st.session_state:
            st.session_state[state_key] = state_value
    preset_col, apply_col = st.columns([3, 1])
    with preset_col:
        selected_preset_name = st.selectbox(
            "教學預設組（Preset）",
            list(I2C_BUILDER_PRESETS),
            format_func=localize_preset,
            help="預設組只填入可重現的範例值；仍須以目標裝置 datasheet 核對。",
        )
    with apply_col:
        if st.button("套用 Preset", key="i2c_builder_apply_preset"):
            for state_key, state_value in preset_widget_state(
                I2C_BUILDER_PRESETS[selected_preset_name]
            ).items():
                st.session_state[state_key] = state_value

    operation_labels = {
        I2CTransferOperation.REGISTER_WRITE.value: "暫存器寫入（Register Write）",
        I2CTransferOperation.COMBINED_REGISTER_READ.value: (
            "複合暫存器讀取（Combined Register Read；Repeated START）"
        ),
        I2CTransferOperation.DIRECT_WRITE.value: "直接寫入（Direct Write；無暫存器階段）",
        I2CTransferOperation.DIRECT_READ.value: "直接讀取（Direct Read；無暫存器階段）",
    }
    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        builder_operation_value = st.selectbox(
            "操作類型（Operation）",
            list(operation_labels),
            format_func=lambda value: operation_labels[value],
            key="i2c_builder_operation",
        )
    with b_col2:
        builder_addr_str = st.text_input(
            "從裝置 7-bit 位址（Slave 7-bit Address）",
            key="i2c_builder_address",
            help="合法範圍 0x08～0x77。",
        )
    with b_col3:
        builder_bus_num = st.number_input(
            "I2C 匯流排編號（I2C Bus Number）",
            min_value=0,
            max_value=0xFFFF,
            step=1,
            key="i2c_builder_bus",
        )

    builder_operation = I2CTransferOperation.coerce(builder_operation_value)
    is_register_op = builder_operation in {
        I2CTransferOperation.REGISTER_WRITE,
        I2CTransferOperation.COMBINED_REGISTER_READ,
    }
    is_read_op = builder_operation in {
        I2CTransferOperation.COMBINED_REGISTER_READ,
        I2CTransferOperation.DIRECT_READ,
    }
    builder_reg_str = ""
    builder_register_width = int(st.session_state["i2c_builder_register_width"])
    builder_endianness = str(st.session_state["i2c_builder_endianness"])
    if is_register_op:
        reg_col, width_col, endian_col = st.columns(3)
        with reg_col:
            builder_reg_str = st.text_input(
                "暫存器位移（Register Offset）",
                key="i2c_builder_register",
                help="例如 0x10 或 0x1234。",
            )
        with width_col:
            builder_register_width = int(
                st.selectbox(
                    "暫存器寬度（Register Width，bits）",
                    [8, 16],
                    key="i2c_builder_register_width",
                )
            )
        with endian_col:
            if builder_register_width == 16:
                builder_endianness = st.selectbox(
                    "暫存器位元組順序（Register Byte Order）",
                    [Endianness.BIG.value, Endianness.LITTLE.value],
                    format_func=lambda value: (
                        "大端序（Big-endian；MSB first）"
                        if value == "big"
                        else "小端序（Little-endian；LSB first）"
                    ),
                    key="i2c_builder_endianness",
                )
            else:
                st.caption("8-bit 暫存器只有一個位元組，不受 byte order 影響。")

    builder_data_str = ""
    builder_read_length: int | None = None
    builder_expected_read = ""
    if is_read_op:
        read_col, expected_col = st.columns(2)
        with read_col:
            builder_read_length = int(
                st.number_input(
                    "讀取長度（Read Length；位元組）",
                    min_value=1,
                    max_value=255,
                    step=1,
                    key="i2c_builder_read_length",
                )
            )
        with expected_col:
            builder_expected_read = st.text_input(
                "預期讀回資料（Expected Read Bytes；選填、僅假設）",
                key="i2c_builder_expected_read_data",
                max_chars=MAX_PACKET_HEX_CHARS,
                help="若填寫，位元組數必須等於 Read Length；只標在波形上，不會送到裝置。",
            )
    else:
        write_data_limit = max_write_data_bytes(
            register_operation=is_register_op,
            register_width=builder_register_width,
        )
        builder_data_str = st.text_input(
            "寫入資料位元組（Write Data Bytes；Hex）",
            key="i2c_builder_write_data",
            max_chars=MAX_PACKET_HEX_CHARS,
            help=(
                f"此操作／寬度最多 {write_data_limit} 個資料位元組（總 Payload 解析器上限 "
                f"{MAX_BUILDER_DATA_BYTES}；波形點數上限 {MAX_BUILDER_WAVEFORM_POINTS}）。"
            ),
        )

    clock_col, timeout_col = st.columns(2)
    with clock_col:
        builder_clock_khz = st.number_input(
            "理想時鐘頻率（Ideal Clock；kHz）",
            min_value=1.0,
            max_value=1000.0,
            step=10.0,
            key="i2c_builder_clock_khz",
        )
    with timeout_col:
        builder_timeout_ms = st.number_input(
            "模板逾時門檻（Template Timeout；ms）",
            min_value=0.001,
            max_value=60_000.0,
            step=1.0,
            key="i2c_builder_timeout_ms",
            help="程式碼模板的 API timeout；不是實測 SMBus tTIMEOUT。",
        )

    try:
        b_addr = parse_hex_integer(
            builder_addr_str, label="從裝置 7-bit 位址（Slave 7-bit Address）"
        )
        b_reg = (
            parse_hex_integer(builder_reg_str, label="暫存器位移（Register Offset）")
            if is_register_op
            else None
        )
        b_data = parse_hex_bytes(
            builder_data_str,
            label="寫入資料位元組（Write Data Bytes）",
            required=not is_read_op,
            max_bytes=(
                max_write_data_bytes(
                    register_operation=is_register_op,
                    register_width=builder_register_width,
                )
                if not is_read_op
                else MAX_BUILDER_DATA_BYTES
            ),
        )
        expected_read_data = parse_hex_bytes(
            builder_expected_read,
            label="預期讀回資料（Expected Read Bytes）",
            max_bytes=255,
        )
        spec = I2CTransferSpec(
            address_7bit=b_addr,
            bus=int(builder_bus_num),
            operation=builder_operation,
            register=b_reg,
            register_width=builder_register_width,
            endianness=builder_endianness,
            data_bytes=b_data,
            read_length=builder_read_length,
            expected_read_data=expected_read_data,
            clock_khz=float(builder_clock_khz),
            timeout_ms=float(builder_timeout_ms),
            max_payload_bytes=MAX_BUILDER_DATA_BYTES,
            max_waveform_points=MAX_BUILDER_WAVEFORM_POINTS,
        )

        st.subheader("標準交易預覽（Canonical Transaction Preview）")
        preview_rows = []
        for index, segment in enumerate(spec.segments, 1):
            payload_labels = [
                ("未知值" if str(getattr(byte, "value", "")).lower() == "unknown" else byte.value)
                if hasattr(byte, "value")
                else f"0x{byte:02X}"
                for byte in segment.bytes
            ]
            if segment.is_read and spec.expected_read_data:
                payload_labels = [f"預期 0x{byte:02X}（假設）" for byte in spec.expected_read_data]
            preview_rows.append(
                {
                    "段落（Segment）": index,
                    "起始（Start）": "重複 START（Sr）" if segment.repeated_start else "START",
                    "方向（Direction）": localize_direction(segment.direction),
                    "7-bit 位址（Address）": f"0x{spec.address_7bit:02X}",
                    "線路位址（Wire Byte）": (
                        f"0x{((spec.address_7bit << 1) | int(segment.is_read)):02X}"
                    ),
                    "負載資料（Payload）": " ".join(payload_labels) or "無（none）",
                    "最終 ACK Slot": (
                        "主機 NACK（Controller NACK；正常讀取結束）"
                        if segment.final_controller_nack
                        else "ACK（理想應答假設）"
                    ),
                    "結束（End）": "STOP 結束條件"
                    if index == len(spec.segments)
                    else "保持連線至 Repeated START（Sr）",
                }
            )
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

        reconstructor = I2CWaveformReconstructor(default_clock_khz=spec.clock_khz)
        wave_data = reconstructor.reconstruct_transfer_spec_waveform(spec)
        st.plotly_chart(
            reconstructor.create_plotly_figure(
                wave_data,
                title=(
                    "理想協定波形模型 (Ideal I2C Transfer Waveform): "
                    f"{operation_labels[spec.operation.value]}"
                ),
            ),
            width="stretch",
        )
        if is_read_op:
            if spec.expected_read_data:
                st.caption(
                    "預期位元組只以假設（assumed）標籤顯示，不是裝置回傳值，也不會寫入生成程式碼。"
                )
            else:
                st.caption(
                    "讀取 Payload 顯示 Unknown；長度已知，但回傳值必須由硬體或 capture 提供。"
                )

        st.subheader("多平台程式碼模板（Driver Templates）")
        st.info(
            "GUI 只產生與下載模板，不會執行任何命令。使用前需補齊 include、handle、"
            "錯誤處理、資源歸屬（ownership）與目標平台初始化。"
        )
        if spec.operation in {
            I2CTransferOperation.REGISTER_WRITE,
            I2CTransferOperation.DIRECT_WRITE,
        }:
            st.warning(
                "寫入操作可能改變 PMBus 電源設定、GPIO、感測器設定（sensor configuration）或 EEPROM。"
                "複製後執行前，必須再次確認匯流排、7-bit address、register、byte order、data、"
                "裝置電源／重設（power/reset）狀態與核心驅動程式資源歸屬（kernel driver ownership）。"
            )
        snippets = I2CDriverCodeGenerator.generate_from_spec(spec)
        for plat, code_txt in snippets.items():
            with st.expander(f"💻 {localize_platform(plat)}", expanded=False):
                st.code(
                    code_txt,
                    language=("bash" if "CLI" in plat else ("cpp" if "Arduino" in plat else "c")),
                )
        bundle, bundle_sha256, spec_sha256 = build_i2c_bundle(spec, snippets)
        hash_col, download_col = st.columns([3, 1])
        with hash_col:
            st.code(
                f"規格 Spec SHA-256：{spec_sha256}\n套件 Bundle SHA-256：{bundle_sha256}",
                language="text",
            )
        with download_col:
            st.download_button(
                "下載傳輸規格與程式碼模板（.zip）",
                bundle,
                file_name="i2c_transfer_bundle.zip",
                mime="application/zip",
            )
    except ResourceLimitError as exc:
        st.error(f"輸入超過安全資源上限：{_localize_gui_error(exc, domain='i2c_builder')}")
    except (TypeError, ValueError) as exc:
        st.error(f"輸入格式錯誤：{_localize_gui_error(exc, domain='i2c_builder')}")
