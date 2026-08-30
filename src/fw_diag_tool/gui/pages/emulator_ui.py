from __future__ import annotations

import pandas as pd
import streamlit as st

from fw_diag_tool.emulator.eeprom import VirtualEEPROM24C64
from fw_diag_tool.emulator.i2c_mux import VirtualPCA9548A
from fw_diag_tool.emulator.ina219 import VirtualINA219
from fw_diag_tool.emulator.lm75 import VirtualLM75
from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128


def parse_hex_bytes(text: str) -> list[int]:
    """將字串解析為 0..255 的整數位元組清單。

    支援以空白或逗號分隔的十六進位字串，例如：
    - "0x12 0x34 0xAB"
    - "12 34 ab cd"
    - "0x12, 0x34, 0xAB"
    """
    cleaned = text.replace(",", " ").strip()
    if not cleaned:
        return []
    tokens = cleaned.split()
    result: list[int] = []
    for idx, tok in enumerate(tokens):
        tok_clean = tok.strip()
        if not tok_clean:
            continue
        try:
            val = int(tok_clean, 0) if tok_clean.startswith(("0x", "0X")) else int(tok_clean, 16)
        except ValueError:
            raise ValueError(f"第 {idx + 1} 個輸入項目不是有效的十六進位數值：'{tok}'")
        if not 0 <= val <= 0xFF:
            raise ValueError(f"第 {idx + 1} 個位元組數值 0x{val:X} 超出範圍（必須介於 0x00～0xFF）")
        result.append(val)
    return result


def parse_hex_or_dec_int(text: str, label: str = "數值") -> int:
    """解析十進位或十六進位整數（支援 0x 前綴）。"""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{label} 不可為空。")
    try:
        val = int(cleaned, 0)
    except ValueError:
        try:
            val = int(cleaned, 16)
        except ValueError:
            raise ValueError(f"{label} 不是有效的整數或十六進位格式：'{text}'")
    if val < 0:
        raise ValueError(f"{label} 不可為負數：{val}")
    return val


def format_hex_dump(data: list[int] | bytes | bytearray, base_offset: int = 0) -> str:
    """格式化為標準十六進位傾印（Hex Dump）字串。"""
    if not data:
        return "(無資料)"
    lines: list[str] = []
    for row_start in range(0, len(data), 16):
        chunk = data[row_start : row_start + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part_padded = f"{hex_part:<47}"
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"0x{base_offset + row_start:06X}:  {hex_part_padded}  |{ascii_part}|")
    return "\n".join(lines)


def decode_lm75_temp(raw_16bit: int) -> float:
    """將 LM75 16-bit 原始暫存器數值解碼為攝氏溫度。"""
    raw_12bit = (raw_16bit >> 4) & 0xFFF
    signed_val = raw_12bit if raw_12bit < 2048 else raw_12bit - 4096
    return signed_val * 0.0625


def decode_lm75_config(config_val: int) -> dict[str, str]:
    """解碼 LM75 Configuration 暫存器各欄位意義。"""
    sd = "低功耗關機（Shutdown）" if (config_val & 0x01) else "正常工作（Normal）"
    tm = "中斷模式（Interrupt）" if (config_val & 0x02) else "比較器模式（Comparator）"
    pol = "Active High（高電位有效）" if (config_val & 0x04) else "Active Low（低電位有效）"
    fq_val = (config_val >> 3) & 0x03
    fq_map = {0: "1 次故障", 1: "2 次故障", 2: "4 次故障", 3: "6 次故障"}
    fq = fq_map.get(fq_val, f"{fq_val}")
    return {
        "Shutdown (SD)": sd,
        "Thermostat Mode (TM)": tm,
        "OS Polarity (POL)": pol,
        "Fault Queue (FQ)": fq,
    }


def _render_lm75_tab() -> None:
    if "emulator_lm75" not in st.session_state:
        st.session_state["emulator_lm75"] = VirtualLM75(addr_7bit=0x48)
    if "lm75_alert_active" not in st.session_state:
        st.session_state["lm75_alert_active"] = False

    lm75: VirtualLM75 = st.session_state["emulator_lm75"]

    st.subheader("LM75 / TMP102 數位溫度感測器模擬（I2C 7-bit Addr: 0x48）")
    st.caption(
        "LM75 是業界標準的 I2C 溫度感測器，具備 12-bit 解析度（0.0625 °C/LSB）"
        "與硬體過溫警報（Over-Temperature Shutdown, OS）引腳輸出。"
    )

    r_top1, r_top2 = st.columns([3, 1])
    with r_top1:
        current_temp_val = float(lm75.temperature_c)
        temp_input = st.slider(
            "環境溫度設定（Environment Temperature；°C）",
            min_value=-40.0,
            max_value=125.0,
            value=current_temp_val,
            step=0.5,
            help="調整實體環境溫度，即時觀察 LM75 內部暫存器與 OS 警報腳位狀態。",
            key="lm75_slider_input",
        )
        if temp_input != lm75.temperature_c:
            lm75.set_temperature(temp_input)
    with r_top2:
        st.write("")
        st.write("")
        if st.button(
            "重設 LM75 感測器",
            key="btn_reset_lm75",
            help="將溫度感測器恢復至預設狀態（25.0 °C、CONFIG 0x00）",
        ):
            st.session_state["emulator_lm75"] = VirtualLM75(addr_7bit=0x48)
            st.session_state["lm75_alert_active"] = False
            lm75 = st.session_state["emulator_lm75"]
            st.success("已重設 LM75 感測器為初始預設值（25.0 °C）。")

    # Alert threshold evaluation
    tos_temp = decode_lm75_temp(lm75.tos_raw)
    thyst_temp = decode_lm75_temp(lm75.thyst_raw)
    cur_t = float(lm75.temperature_c)

    if cur_t >= tos_temp:
        st.session_state["lm75_alert_active"] = True
    elif cur_t <= thyst_temp:
        st.session_state["lm75_alert_active"] = False

    alert_active = st.session_state["lm75_alert_active"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("當前量測溫度", f"{cur_t:.2f} °C")
    m2.metric("TOS 過溫閾值", f"{tos_temp:.1f} °C (0x{lm75.tos_raw:04X})")
    m3.metric("THYST 遲滯閾值", f"{thyst_temp:.1f} °C (0x{lm75.thyst_raw:04X})")
    if alert_active:
        m4.metric("OS 警報輸出腳位", "🚨 觸發 (Active LOW)")
    elif thyst_temp < cur_t < tos_temp:
        m4.metric("OS 警報輸出腳位", "🟡 遲滯區間 (Hysteresis)")
    else:
        m4.metric("OS 警報輸出腳位", "🟢 正常 (Inactive HIGH)")

    st.markdown("---")
    st.markdown("#### 內部暫存器狀態表（Internal Registers Status）")

    # Compute raw TEMP register
    raw_12bit = int(cur_t / 0.0625) & 0xFFF
    raw_16bit_temp = raw_12bit << 4
    ptr_names = {
        0x00: "TEMP (0x00)",
        0x01: "CONFIG (0x01)",
        0x02: "THYST (0x02)",
        0x03: "TOS (0x03)",
    }
    cur_ptr = lm75.last_cmd if lm75.last_cmd is not None else 0x00

    cfg_info = decode_lm75_config(lm75.config_reg)
    cfg_desc = f"SD={cfg_info['Shutdown (SD)']}, TM={cfg_info['Thermostat Mode (TM)']}, POL={cfg_info['OS Polarity (POL)']}, FQ={cfg_info['Fault Queue (FQ)']}"

    reg_data = [
        {
            "指標 (Pointer)": "0x00",
            "暫存器名稱": "TEMP（溫度值暫存器）",
            "寬度": "16-bit (唯讀)",
            "原始 Hex": f"0x{raw_16bit_temp:04X}",
            "解碼意義": f"溫度 = {cur_t:.4f} °C（12-bit 有效，解析度 0.0625 °C/LSB）",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x00 else "",
        },
        {
            "指標 (Pointer)": "0x01",
            "暫存器名稱": "CONFIG（組態設定暫存器）",
            "寬度": "8-bit (可讀寫)",
            "原始 Hex": f"0x{lm75.config_reg:02X}",
            "解碼意義": cfg_desc,
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x01 else "",
        },
        {
            "指標 (Pointer)": "0x02",
            "暫存器名稱": "THYST（遲滯溫度暫存器）",
            "寬度": "16-bit (可讀寫)",
            "原始 Hex": f"0x{lm75.thyst_raw:04X}",
            "解碼意義": f"遲滯溫度 = {thyst_temp:.2f} °C（警報解除門檻）",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x02 else "",
        },
        {
            "指標 (Pointer)": "0x03",
            "暫存器名稱": "TOS（過溫關閉暫存器）",
            "寬度": "16-bit (可讀寫)",
            "原始 Hex": f"0x{lm75.tos_raw:04X}",
            "解碼意義": f"過溫溫度 = {tos_temp:.2f} °C（警報觸發門檻）",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x03 else "",
        },
    ]
    st.table(pd.DataFrame(reg_data))

    st.markdown("---")
    st.markdown("#### I2C 匯流排交易模擬（I2C Transaction Simulation）")

    c_wr, c_rd = st.columns(2)

    with c_wr:
        st.markdown("##### ✍️ I2C 寫入命令（I2C Write）")
        st.caption("設定暫存器指針（Pointer Register）或寫入 CONFIG 暫存器。")
        wr_input = st.text_input(
            "寫入資料 Hex 位元組（Data Bytes）",
            value="0x00",
            key="lm75_write_hex_input",
            help="例：'0x00'（指向 TEMP）、'0x01 0x01'（進入 Shutdown 模式）、'0x01 0x00'（正常模式）",
        )
        col_btn_w1, col_btn_w2 = st.columns([1, 1])
        with col_btn_w1:
            if st.button("送出 I2C 寫入", key="btn_lm75_write"):
                try:
                    bytes_to_send = parse_hex_bytes(wr_input)
                    res = lm75.write(bytes_to_send)
                    if not bytes_to_send:
                        st.info("I2C Address Probe: 成功尋址 LM75 (0x48)，從裝置回應 ACK。")
                    else:
                        st.success(f"寫入成功！{res.get('summary', 'OK')}")
                except Exception as exc:
                    st.error(f"寫入失敗：{exc}")
        with col_btn_w2:
            preset_choice = st.selectbox(
                "快速載入指令範例",
                [
                    "自訂輸入",
                    "指標指向 TEMP (0x00)",
                    "指標指向 CONFIG (0x01)",
                    "設定 Shutdown 模式 (0x01 0x01)",
                    "設定 Normal 模式 (0x01 0x00)",
                ],
                key="lm75_preset_select",
            )
            if preset_choice == "指標指向 TEMP (0x00)":
                lm75.write([0x00])
                st.info("已設定指針為 TEMP (0x00)。")
            elif preset_choice == "指標指向 CONFIG (0x01)":
                lm75.write([0x01])
                st.info("已設定指針為 CONFIG (0x01)。")
            elif preset_choice == "設定 Shutdown 模式 (0x01 0x01)":
                lm75.write([0x01, 0x01])
                st.info("已寫入 CONFIG: 進入 Shutdown 模式。")
            elif preset_choice == "設定 Normal 模式 (0x01 0x00)":
                lm75.write([0x01, 0x00])
                st.info("已寫入 CONFIG: 恢復 Normal 模式。")

    with c_rd:
        st.markdown("##### 📖 I2C 讀取命令（I2C Read）")
        st.caption(f"由當前指針暫存器（{ptr_names.get(cur_ptr, f'0x{cur_ptr:02X}')}）讀出位元組。")
        rd_len = st.number_input(
            "讀取位元組數（Read Length）",
            min_value=1,
            max_value=2,
            value=2 if cur_ptr != 0x01 else 1,
            step=1,
            key="lm75_read_len",
            help="TEMP/THYST/TOS 為 2 bytes，CONFIG 為 1 byte。",
        )
        if st.button("執行 I2C 讀取", key="btn_lm75_read"):
            try:
                read_bytes = lm75.read(int(rd_len))
                hex_str = " ".join(f"0x{b:02X}" for b in read_bytes)
                st.success(f"讀取成功！回傳 {len(read_bytes)} 位元組：`{hex_str}`")

                if cur_ptr == 0x00 and len(read_bytes) == 2:
                    raw_val = (read_bytes[0] << 8) | read_bytes[1]
                    calc_t = decode_lm75_temp(raw_val)
                    st.info(f"解碼結果：溫度值 = {calc_t:.4f} °C (Raw: 0x{raw_val:04X})")
                elif cur_ptr == 0x01 and len(read_bytes) >= 1:
                    cfg_map = decode_lm75_config(read_bytes[0])
                    st.info(f"解碼結果：組態暫存器 = 0x{read_bytes[0]:02X} -> {cfg_map}")
                elif cur_ptr == 0x02 and len(read_bytes) == 2:
                    raw_val = (read_bytes[0] << 8) | read_bytes[1]
                    st.info(f"解碼結果：THYST 遲滯 = {decode_lm75_temp(raw_val):.2f} °C")
                elif cur_ptr == 0x03 and len(read_bytes) == 2:
                    raw_val = (read_bytes[0] << 8) | read_bytes[1]
                    st.info(f"解碼結果：TOS 過溫 = {decode_lm75_temp(raw_val):.2f} °C")
            except Exception as exc:
                st.error(f"讀取失敗：{exc}")

    with st.expander("📖 點擊展開：LM75 數位溫度感測器硬體原理與除錯教學", expanded=False):
        st.markdown(
            """
- **指標暫存器（Pointer Register）機制**：
  LM75 只有一個 8-bit 的 Pointer Register。主控端（Master）必須先執行一次 I2C Write 發送暫存器位移（`0x00` ~ `0x03`），設定指針後再發起 I2C Read 讀取資料。若未更新指針，每次 Read 會自動沿用上一次設定的暫存器。
- **12-bit 溫度編碼格式**：
  資料以 16-bit 輸出，高 12-bit 為有效溫度數據（Left-justified），低 4 位為 0。MSB 為符號位元（二補碼格式）。
  - 解析度：`0.0625 °C/LSB`（`1 / 16 °C`）。
  - 溫度計算公式：`溫度 (°C) = (Raw_16bit >> 4) * 0.0625`（負值需做符號延伸）。
- **遲滯（Hysteresis）防彈跳保護**：
  當環境溫度上升達到 `TOS`（預設 80 °C）時，`OS` 引腳被拉為 LOW（觸發警報／中斷）。只有當溫度降回 `THYST`（預設 75 °C）以下時，`OS` 引腳才會釋放恢復為 HIGH。此 5 °C 的遲滯區間可有效避免系統在臨界溫度時產生中斷信號狂震（Chattering）。
            """
        )


def _render_spi_flash_tab() -> None:
    if "emulator_spi_flash" not in st.session_state:
        st.session_state["emulator_spi_flash"] = VirtualSPIFlashW25Q128()

    flash: VirtualSPIFlashW25Q128 = st.session_state["emulator_spi_flash"]

    st.subheader("Winbond W25Q128 SPI NOR Flash 模擬器（128 Mbit / 16 MB）")
    st.caption(
        "W25Q128 是伺服器與嵌入式系統中最廣泛使用的 SPI NOR Flash，具備 16 MB 容量、"
        "256 Bytes 頁面緩衝區（Page Buffer）與 4KB 扇區擦除（Sector Erase）架構。"
    )

    # Calculate memory stats
    non_ff_bytes = flash.total_size - flash.memory.count(0xFF)

    # Top Status Bar
    st.markdown("#### 晶片狀態指示與控制（Chip Status & Control）")
    c_st1, c_st2, c_st3, c_st4 = st.columns(4)
    jedec = flash.read_jedec_id()
    jedec_str = " ".join(f"0x{b:02X}" for b in jedec)
    c_st1.metric(
        "JEDEC ID (0x9F)", jedec_str, help="0xEF=Winbond, 0x40=SPI NOR, 0x18=128Mbit (16MB)"
    )
    c_st2.metric(
        "WEL 寫入致能鎖存",
        "🟢 致能 (1)" if flash.wel_latched else "🔒 禁能 (0)",
        help="Write Enable Latch。執行寫入或擦除前必須先發送 0x06 WREN 命令將其置 1。",
    )
    c_st3.metric(
        "BUSY 狀態",
        "⏳ 忙碌中 (1)" if flash.busy else "🟢 閒置就緒 (0)",
        help="晶片正在執行內部 Program 或 Erase 操作。忙碌時拒絕新的寫入指令。",
    )
    c_st4.metric(
        "已寫入位元組",
        f"{non_ff_bytes} Bytes",
        delta=f"{(non_ff_bytes / flash.total_size) * 100:.4f}% 使用率",
    )

    # Control action buttons
    c_btn1, c_btn2, c_btn3, c_btn4 = st.columns(4)
    with c_btn1:
        if st.button(
            "寫入致能 WREN (0x06)", key="btn_spi_wren", help="發送 Write Enable 命令，將 WEL 置 1"
        ):
            if flash.busy:
                st.error("Flash 處於 Busy 忙碌狀態，無法致能寫入！")
            else:
                flash.write_enable()
                st.success("已執行 WREN (0x06)：WEL 置為 1（允許寫入）。")
    with c_btn2:
        if st.button(
            "寫入禁能 WRDI (0x04)", key="btn_spi_wrdi", help="發送 Write Disable 命令，將 WEL 置 0"
        ):
            flash.write_disable()
            st.info("已執行 WRDI (0x04)：WEL 置為 0（禁止寫入）。")
    with c_btn3:
        if st.button(
            "完成操作 / 清除 Busy",
            key="btn_spi_complete",
            help="模擬內部 Program/Erase 週期完成，將 Busy 置 0",
        ):
            flash.complete_operation()
            st.success("已完成操作：Flash 恢復為 Ready 就緒狀態。")
    with c_btn4:
        if st.button(
            "重設 Flash 記憶體", key="btn_spi_reset", help="將 16MB 記憶體全部重設為 0xFF"
        ):
            st.session_state["emulator_spi_flash"] = VirtualSPIFlashW25Q128()
            flash = st.session_state["emulator_spi_flash"]
            st.success("已重設 Flash：所有記憶體已恢復為 0xFF。")

    st.markdown("---")
    st.markdown("#### SPI Flash 操作區域（Operations）")

    op_tab1, op_tab2, op_tab3 = st.tabs(
        [
            "✍️ 頁面程式寫入（Page Program 0x02）",
            "🧹 扇區擦除（Sector Erase 0x20）",
            "📖 讀取資料（Read Data 0x03）",
        ]
    )

    with op_tab1:
        st.caption(
            "Page Program 每次最多寫入 256 位元組（1 個 Page）。"
            "NOR Flash 物理限制：**只能將 1 寫為 0**；若欲將 0 改為 1，必須先執行 Sector Erase！"
        )
        c_prog1, c_prog2 = st.columns([1, 2])
        with c_prog1:
            prog_addr_str = st.text_input(
                "目標位址（Target Address）",
                value="0x001000",
                key="spi_prog_addr",
                help="可輸入十六進位（0x001000）或十進位整數。",
            )
        with c_prog2:
            prog_data_str = st.text_input(
                "寫入資料 Hex Bytes（1～256 位元組）",
                value="0xDE 0xAD 0xBE 0xEF 0x12 0x34 0x56 0x78",
                key="spi_prog_data",
                help="支援以空白或逗號分隔的十六進位位元組，如 '0xDE 0xAD 0xBE 0xEF' 或 'AA BB CC DD'。",
            )

        col_p1, col_p2 = st.columns([1, 3])
        with col_p1:
            if st.button("執行 Page Program (0x02)", key="btn_exec_page_program"):
                try:
                    addr = parse_hex_or_dec_int(prog_addr_str, label="目標位址")
                    data = parse_hex_bytes(prog_data_str)
                    if not data:
                        st.error("請輸入至少 1 個位元組的寫入資料。")
                    elif len(data) > 256:
                        st.error(f"單次 Page Program 資料量（{len(data)}B）超過 256 位元組上限！")
                    else:
                        if not flash.wel_latched:
                            st.error(
                                "寫入被拒絕：Flash WEL (Write Enable Latch) 為 0，請先點擊『寫入致能 WREN (0x06)』！"
                            )
                        elif flash.busy:
                            st.error(
                                "寫入被拒絕：Flash 正在執行內部操作（Busy=1），請先等待或點擊『完成操作』！"
                            )
                        else:
                            ok = flash.page_program(addr, data)
                            if ok:
                                st.success(
                                    f"Page Program 執行成功！已向 0x{addr:06X} 寫入 {len(data)} 位元組。"
                                    "（注意：Flash WEL 已自動清除為 0，且進入 Busy 狀態）"
                                )
                            else:
                                st.error("Page Program 失敗：Flash 拒絕操作。")
                except Exception as exc:
                    st.error(f"操作錯誤：{exc}")

        with col_p2:
            if st.button("填入測試資料：'Firmware v1.1.1 OK'", key="btn_fill_spi_sample"):
                sample_bytes = list(b"Firmware v1.1.1 OK")
                hex_sample = " ".join(f"0x{b:02X}" for b in sample_bytes)
                st.info(
                    f"已準備測試資料（ASCII 轉 Hex）：`{hex_sample}`，請將其貼上或直接點擊執行。"
                )

    with op_tab2:
        st.caption("Sector Erase 將指定的 4KB 扇區（4096 位元組）全部擦除還原為 `0xFF`。")
        c_er1, c_er2 = st.columns([1, 2])
        with c_er1:
            erase_addr_str = st.text_input(
                "扇區內任意位址（Address in Sector）",
                value="0x001000",
                key="spi_erase_addr",
                help="輸入該 4KB 扇區內的任意位址，系統會自動對齊至扇區起始邊界（4096 的整數倍）。",
            )
        with c_er2:
            try:
                er_addr = parse_hex_or_dec_int(erase_addr_str, label="扇區位址")
                sector_start = (er_addr // 4096) * 4096
                sector_end = sector_start + 4095
                st.info(
                    f"對應 4KB 扇區範圍：`0x{sector_start:06X} ~ 0x{sector_end:06X}` (Sector #{er_addr // 4096})"
                )
            except (ValueError, TypeError):
                st.caption("請輸入有效位址以計算扇區範圍。")

        if st.button("執行 Sector Erase (0x20)", key="btn_exec_sector_erase"):
            try:
                er_addr = parse_hex_or_dec_int(erase_addr_str, label="扇區位址")
                if not flash.wel_latched:
                    st.error(
                        "擦除被拒絕：Flash WEL (Write Enable Latch) 為 0，請先點擊『寫入致能 WREN (0x06)』！"
                    )
                elif flash.busy:
                    st.error(
                        "擦除被拒絕：Flash 正在執行內部操作（Busy=1），請先等待或點擊『完成操作』！"
                    )
                else:
                    ok = flash.sector_erase(er_addr)
                    if ok:
                        sec_s = (er_addr // 4096) * 4096
                        st.success(
                            f"Sector Erase 執行成功！扇區 0x{sec_s:06X} ~ 0x{sec_s + 4095:06X} 已全部還原為 0xFF。"
                            "（WEL 已自動清除為 0，且進入 Busy 狀態）"
                        )
                    else:
                        st.error("Sector Erase 失敗：Flash 拒絕操作。")
            except Exception as exc:
                st.error(f"擦除操作錯誤：{exc}")

    with op_tab3:
        st.caption("Read Data（0x03）支援由任意位址連續讀取指定長度的資料。")
        c_rd1, c_rd2 = st.columns([1, 1])
        with c_rd1:
            rd_addr_str = st.text_input(
                "讀取起始位址（Offset）", value="0x001000", key="spi_read_addr"
            )
        with c_rd2:
            rd_len_val = st.number_input(
                "讀取長度（Bytes）",
                min_value=1,
                max_value=512,
                value=64,
                step=16,
                key="spi_read_len",
            )

        if st.button("執行讀取（Read Data 0x03）", key="btn_exec_spi_read"):
            try:
                r_addr = parse_hex_or_dec_int(rd_addr_str, label="讀取位址")
                r_len = int(rd_len_val)
                read_res = flash.read_data(r_addr, r_len)
                st.success(f"讀取成功！從位址 0x{r_addr:06X} 讀取 {len(read_res)} 位元組：")
                st.code(format_hex_dump(read_res, base_offset=r_addr), language="text")
            except Exception as exc:
                st.error(f"讀取失敗：{exc}")

    with st.expander("📖 點擊展開：SPI NOR Flash 架構與底層韌體行為教學", expanded=False):
        st.markdown(
            """
- **NOR Flash 物理改寫限制（Only 1 -> 0）**：
  NOR Flash 的記憶體浮閘（Floating Gate）單元在擦除後皆為 `1`（`0xFF`）。程式寫入（Program）只能將特定位元由 `1` 充入電子轉為 `0`，**無法直接將 0 改寫回 1**。若未經 Erase 就重複 Program，寫入的資料會與原資料產生 `Bitwise AND`（`Memory &= Data`），導致資料損毀。
- **寫入致能鎖存（WEL, Write Enable Latch）安全機制**：
  為防止雜訊或程式跑飛（Runaway code）誤觸發寫入，Flash 規定在執行 `Page Program (0x02)`、`Sector Erase (0x20)` 或 `Block Erase (0xD8)` 前，**必須先發送 `0x06 WREN` 指令**。每次寫入或擦除操作一結束，硬體會自動將 WEL 重設為 `0`，鎖定寫入權限。
- **頁面邊界回繞（Page Buffer Wrap-Around）**：
  SPI Flash 內部具備 256 位元組的 Page Buffer。若單次寫入跨越了 256-byte 邊界（例如從 `0x0010F0` 寫入 32 bytes），超出 `0x0010FF` 的資料不會寫入 `0x001100`，而是回繞（Wrap-around）覆蓋 `0x001000` 開頭！驅動程式必須嚴格依頁面邊界分段發送。
            """
        )


def _render_eeprom_tab() -> None:
    if "emulator_eeprom" not in st.session_state:
        st.session_state["emulator_eeprom"] = VirtualEEPROM24C64(
            addr_7bit=0x50, page_size=32, capacity=8192
        )

    eeprom: VirtualEEPROM24C64 = st.session_state["emulator_eeprom"]

    st.subheader("Microchip / Atmel 24C64 I2C Serial EEPROM 模擬器（8KB / 64Kbit）")
    st.caption(
        "24C64 是嵌入式系統中常用於儲存 MAC 位址、序號、校正參數與 FRU 資訊的 I2C EEPROM，"
        "具備 8192 位元組容量、32 位元組頁面大小（Page Size）與 16-bit 內部記憶體定址架構。"
    )

    st.markdown("#### 晶片狀態與 ACK Polling 監控（Chip Status & ACK Polling）")
    e_st1, e_st2, e_st3, e_st4 = st.columns(4)
    e_st1.metric("I2C 裝置位址", f"0x{eeprom.addr:02X} (7-bit)")
    e_st2.metric(
        "總容量 / 頁面大小",
        f"{eeprom.capacity}B / {eeprom.page_size}B",
        help="共 256 頁（Page 0～255），每頁 32 Bytes",
    )
    e_st3.metric(
        "寫入忙碌狀態 (BUSY)",
        "⏳ 忙碌中 (tWR 進行中)" if eeprom.is_busy else "🟢 閒置就緒 (Ready)",
        help="EEPROM 在執行內部寫入週期（tWR ~5ms）時，對 I2C 位址尋址會直接回傳 NACK。",
    )
    e_st4.metric("內部寫入耗時 (tWR)", f"{eeprom.write_cycle_ms:.1f} ms")

    col_ack1, col_ack2 = st.columns([1, 3])
    with col_ack1:
        if st.button(
            "執行 ACK Polling (0x50)",
            key="btn_eeprom_ack_poll",
            help="向 0x50 發送 I2C Address Probe 輪詢寫入是否完成",
        ):
            was_busy = eeprom.ack_polling()
            if was_busy:
                st.success(
                    "ACK Polling 成功！EEPROM 已完成內部寫入週期（tWR 結束），目前回傳 ACK，就緒接收新命令。"
                )
            else:
                st.info("ACK Polling 結果：EEPROM 目前處於閒置就緒狀態（無進行中的寫入週期）。")
    with col_ack2:
        if st.button("重設 EEPROM 記憶體（清空為 0x00）", key="btn_eeprom_reset"):
            st.session_state["emulator_eeprom"] = VirtualEEPROM24C64(
                addr_7bit=0x50, page_size=32, capacity=8192
            )
            eeprom = st.session_state["emulator_eeprom"]
            st.success("已重設 EEPROM：所有 8192 位元組已清空為 0x00。")

    st.markdown("---")
    st.markdown("#### EEPROM 讀寫操作與跨頁危害模擬（Read / Write Operations）")

    c_eep_w, c_eep_r = st.columns(2)

    with c_eep_w:
        st.markdown("##### ✍️ I2C Page Write（寫入資料）")
        st.caption("支援 2-Byte Word Address（標準 24C64 模式，高位元組先發）。")
        eep_offset_str = st.text_input(
            "寫入起始位移（Offset；0x0000～0x1FFF）",
            value="0x001E",
            key="eep_wr_offset",
            help="提示：設為 0x001E 並寫入 6 個 bytes 可觀察跨越 32-Byte 頁面邊界的 Rollover 現象！",
        )
        eep_payload_str = st.text_input(
            "寫入資料 Hex Bytes",
            value="0xAA 0xBB 0xCC 0xDD 0xEE 0xFF",
            key="eep_wr_payload",
            help="例：'0xAA 0xBB 0xCC 0xDD' 或 '01 02 03 04 05'",
        )

        # Preflight check for page rollover hazard
        try:
            cur_off = parse_hex_or_dec_int(eep_offset_str, label="Offset")
            cur_bytes = parse_hex_bytes(eep_payload_str)
            if cur_bytes:
                off_in_page = cur_off % eeprom.page_size
                if off_in_page + len(cur_bytes) > eeprom.page_size:
                    overflow_count = (off_in_page + len(cur_bytes)) - eeprom.page_size
                    page_num = cur_off // eeprom.page_size
                    page_start_addr = page_num * eeprom.page_size
                    st.warning(
                        f"⚠️ **Page Boundary Rollover 警告**：\n"
                        f"寫入起始於 Page #{page_num} 偏移 +{off_in_page}B，長度 {len(cur_bytes)}B。"
                        f"超出 32-Byte 邊界的 {overflow_count} 個位元組**不會寫入下一頁**，"
                        f"而是回繞覆蓋本頁開頭（`0x{page_start_addr:04X}`）！"
                    )
        except (ValueError, TypeError):
            pass

        if st.button("執行 EEPROM 寫入（Write）", key="btn_exec_eeprom_write"):
            try:
                offset_val = parse_hex_or_dec_int(eep_offset_str, label="Offset")
                payload_bytes = parse_hex_bytes(eep_payload_str)
                if not payload_bytes:
                    st.error("請輸入至少 1 個位元組的寫入資料。")
                else:
                    # 24C64 uses 2-byte word address
                    data_to_send = [(offset_val >> 8) & 0xFF, offset_val & 0xFF] + payload_bytes
                    res = eeprom.write(data_to_send, preferred_address_bytes=2)
                    if res.get("rollover_hazard"):
                        st.warning(
                            f"寫入完成但偵測到跨頁覆蓋！{res.get('summary')}\n"
                            "晶片已進入內部寫入週期（Busy=True），請執行 ACK Polling 確認完成。"
                        )
                    else:
                        st.success(
                            f"寫入成功！{res.get('summary')}\n"
                            "晶片已進入內部寫入週期（Busy=True），請執行 ACK Polling 確認完成。"
                        )
            except RuntimeError as r_err:
                st.error(f"寫入失敗：{r_err}（請先執行 ACK Polling）")
            except Exception as exc:
                st.error(f"操作錯誤：{exc}")

    with c_eep_r:
        st.markdown("##### 📖 I2C Read（隨機讀取 / 循序讀取）")
        st.caption("發送 16-bit Offset 設定位址指針，隨後進行 I2C Read 讀出資料。")
        eep_rd_offset_str = st.text_input(
            "讀取起始位移（Offset）", value="0x0000", key="eep_rd_offset"
        )
        eep_rd_len_val = st.number_input(
            "讀取長度（Bytes）", min_value=1, max_value=256, value=64, step=16, key="eep_rd_len"
        )

        if st.button("執行 EEPROM 讀取（Read）", key="btn_exec_eeprom_read"):
            try:
                rd_off = parse_hex_or_dec_int(eep_rd_offset_str, label="讀取 Offset")
                rd_len = int(eep_rd_len_val)
                read_data = eeprom.read(rd_off, rd_len)
                st.success(f"讀取成功！從 0x{rd_off:04X} 讀取 {len(read_data)} 位元組：")
                st.code(format_hex_dump(read_data, base_offset=rd_off), language="text")
            except RuntimeError as r_err:
                st.error(f"讀取被拒絕：{r_err}（EEPROM 忙碌中，請先執行 ACK Polling）")
            except Exception as exc:
                st.error(f"讀取失敗：{exc}")

    st.markdown("---")
    st.markdown("#### 記憶體內容檢視器（Memory Hex Viewer）")
    c_view1, c_view2 = st.columns([1, 2])
    with c_view1:
        view_page = st.selectbox(
            "選擇檢視分頁（每頁 32 Bytes）",
            [f"Page {p} (0x{p * 32:04X} ~ 0x{p * 32 + 31:04X})" for p in range(16)]
            + ["自訂區域（前 256 Bytes）", "自訂區域（前 512 Bytes）"],
            key="eep_viewer_page_select",
        )
    with c_view2:
        if view_page.startswith("Page "):
            page_idx = int(view_page.split()[1])
            dump_text = eeprom.dump_memory(start=page_idx * 32, length=32)
        elif "256" in view_page:
            dump_text = eeprom.dump_memory(start=0, length=256)
        else:
            dump_text = eeprom.dump_memory(start=0, length=512)

        st.code(dump_text, language="text")

    with st.expander("📖 點擊展開：I2C EEPROM 24C64 硬體特性與 Page Rollover 教學", expanded=False):
        st.markdown(
            """
- **內部 16-bit 定址協定（Word Address）**：
  24C64 具備 8192 Bytes（64 Kbit）容量，需要 13-bit 位址線。在發送 I2C Slave Address（`0x50`）後，Master 必須依序傳送 2 個 Bytes 的 Word Address（Address High Byte、Address Low Byte），隨後才是讀寫 Payload。
- **頁面回繞（Page Boundary Rollover）陷阱**：
  EEPROM 支援 Page Write（例如 24C64 頁面大小為 32 Bytes）。晶片內部只有低 5 位的位址計數器在連續寫入時遞增。若寫入的位元組數超過該頁剩餘空間，**高位頁位址不會進位**，而是回繞（Roll over）至該頁的第一個位元組（Offset 0），覆蓋掉原有的資料！
- **ACK Polling（確認輪詢）優化**：
  EEPROM 的內部寫入週期（`tWR`）需要約 5 ms（高壓電荷泵寫入浮閘）。若每次寫入後軟體都使用 `sleep(5ms)`，會浪費大量 CPU 週期。透過 **ACK Polling**（Master 在寫入後連續發送 I2C Start + Slave Addr(W)，若晶片忙碌則回傳 NACK；一旦完成寫入則回傳 ACK），可將寫入等待時間縮至最短，大幅提升 I2C 存取吞吐量。
            """
        )


def _render_ina219_tab() -> None:
    if "emulator_ina219" not in st.session_state:
        st.session_state["emulator_ina219"] = VirtualINA219(addr_7bit=0x40, shunt_ohms=0.1, max_expected_amps=3.2)
        st.session_state["emulator_ina219"].write_calibration(4096)

    ina: VirtualINA219 = st.session_state["emulator_ina219"]

    st.subheader("INA219 / INA226 雙向電流 / 功率 / 電壓監控晶片模擬（I2C 7-bit Addr: 0x40）")
    st.caption(
        "INA219 是一款具備 I2C 介面的高側（High-Side）電流與電源監控 IC，可量測分流電壓（Shunt Voltage ±320mV）、"
        "匯流排電壓（Bus Voltage 0~26V），並透過內部校準暫存器（Calibration Register）直接在硬體內部計算電流與功率。"
    )

    c_ina_ctrl1, c_ina_ctrl2 = st.columns([3, 1])
    with c_ina_ctrl1:
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            v_bus_in = st.slider(
                "模擬匯流排電壓 (Bus Voltage; V)",
                min_value=0.0,
                max_value=26.0,
                value=float(ina.bus_voltage_v) if ina.bus_voltage_v > 0 else 12.0,
                step=0.1,
                key="ina_slider_vbus",
            )
            ina.set_bus_voltage(v_bus_in)
        with col_s2:
            v_shunt_mv_in = st.slider(
                "模擬分流電壓 (Shunt Voltage; mV)",
                min_value=-320.0,
                max_value=320.0,
                value=float(ina.shunt_voltage_uv / 1000.0) if ina.shunt_voltage_uv != 0.0 else 25.0,
                step=0.5,
                key="ina_slider_vshunt",
            )
            ina.set_shunt_voltage(v_shunt_mv_in * 1000.0)

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            r_shunt_in = st.number_input(
                "分流電阻值 R_shunt (Ω)",
                min_value=0.001,
                max_value=10.0,
                value=float(ina.shunt_ohms),
                step=0.01,
                format="%.4f",
                key="ina_input_rshunt",
            )
            ina.set_shunt_resistance(r_shunt_in)
        with col_p2:
            c_lsb_in = st.number_input(
                "電流解析度 Current LSB (mA/bit)",
                min_value=0.001,
                max_value=100.0,
                value=float(ina.current_lsb_ma),
                step=0.01,
                format="%.4f",
                key="ina_input_clsb",
            )
            ina.set_current_lsb(c_lsb_in)

    with c_ina_ctrl2:
        st.write("")
        st.write("")
        if st.button("重設 INA219", key="btn_reset_ina219"):
            st.session_state["emulator_ina219"] = VirtualINA219(addr_7bit=0x40, shunt_ohms=0.1, max_expected_amps=3.2)
            st.session_state["emulator_ina219"].write_calibration(4096)
            ina = st.session_state["emulator_ina219"]
            st.success("已恢復 INA219 預設狀態。")

        rec_cal = ina.calculate_expected_calibration(current_lsb_ma=c_lsb_in, shunt_ohms=r_shunt_in)
        if st.button(f"寫入推薦校準值 (0x{rec_cal:04X})", key="btn_auto_cal_ina219", help="根據當前 R_shunt 與 Current LSB 自動計算並寫入校準暫存器"):
            ina.write_calibration(rec_cal)
            st.success(f"已寫入 Calibration = 0x{rec_cal:04X} ({rec_cal})")

    # Calculations & Metrics
    theo_current_ma = (v_shunt_mv_in / r_shunt_in) if r_shunt_in > 0 else 0.0
    theo_power_mw = v_bus_in * theo_current_ma
    meas_current_ma = ina.calculate_current()
    meas_power_mw = ina.calculate_power()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("匯流排電壓 (Bus V)", f"{ina.bus_voltage_v:.3f} V", delta=f"{ina.bus_voltage_v * 1000.0:.1f} mV")
    m2.metric("分流電壓 (Shunt V)", f"{ina.shunt_voltage_uv / 1000.0:.2f} mV", delta=f"{ina.shunt_voltage_uv:.0f} µV")
    if ina.cal_reg == 0:
        m3.metric("晶片讀出電流 (Current)", "0.0 mA (未校準)", delta="⚠️ Cal=0")
        m4.metric("晶片讀出功率 (Power)", "0.0 mW (未校準)", delta="⚠️ Cal=0")
    else:
        m3.metric("晶片讀出電流 (Current)", f"{meas_current_ma:.2f} mA", delta=f"理論值 {theo_current_ma:.2f} mA")
        m4.metric("晶片讀出功率 (Power)", f"{meas_power_mw:.2f} mW", delta=f"理論值 {theo_power_mw:.2f} mW")

    st.markdown("---")
    st.markdown("#### 內部暫存器狀態表（Internal Registers Status）")

    cur_ptr = ina.last_cmd
    reg_rows = [
        {
            "指標 (Pointer)": "0x00",
            "暫存器名稱": "CONFIG (組態設定)",
            "寬度": "16-bit (可讀寫)",
            "原始 Hex": f"0x{ina.read_register(0x00):04X}",
            "解碼意義": "32V FSR, ±320mV PGA, 12-bit ADC, Continuous",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x00 else "",
        },
        {
            "指標 (Pointer)": "0x01",
            "暫存器名稱": "SHUNT_V (分流電壓)",
            "寬度": "16-bit Signed (唯讀)",
            "原始 Hex": f"0x{ina.read_register(0x01):04X}",
            "解碼意義": f"原始值 {round(ina.shunt_voltage_uv / 10.0)} (LSB = 10 µV -> {ina.shunt_voltage_uv / 1000.0:.3f} mV)",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x01 else "",
        },
        {
            "指標 (Pointer)": "0x02",
            "暫存器名稱": "BUS_V (匯流排電壓)",
            "寬度": "16-bit (唯讀)",
            "原始 Hex": f"0x{ina.read_register(0x02):04X}",
            "解碼意義": f"電壓 = {ina.bus_voltage_v:.3f} V (Bits[15:3] 步長 4 mV), CNVR=1, OVF={'1' if ina.overflow else '0'}",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x02 else "",
        },
        {
            "指標 (Pointer)": "0x03",
            "暫存器名稱": "POWER (功率計算值)",
            "寬度": "16-bit (唯讀)",
            "原始 Hex": f"0x{ina.read_register(0x03):04X}",
            "解碼意義": f"功率 = {meas_power_mw:.2f} mW (LSB = 20 * Current_LSB = {20.0 * ina.current_lsb_ma:.3f} mW)",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x03 else "",
        },
        {
            "指標 (Pointer)": "0x04",
            "暫存器名稱": "CURRENT (電流計算值)",
            "寬度": "16-bit Signed (唯讀)",
            "原始 Hex": f"0x{ina.read_register(0x04):04X}",
            "解碼意義": f"電流 = {meas_current_ma:.2f} mA (LSB = {ina.current_lsb_ma:.3f} mA/bit)",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x04 else "",
        },
        {
            "指標 (Pointer)": "0x05",
            "暫存器名稱": "CALIBRATION (校準暫存器)",
            "寬度": "16-bit (可讀寫)",
            "原始 Hex": f"0x{ina.read_register(0x05):04X}",
            "解碼意義": f"數值 = {ina.cal_reg} {'(未設定校準，電流/功率暫存器將恆為 0)' if ina.cal_reg == 0 else '(校準有效)'}",
            "目前指標指向": "👉 作用中 (Active)" if cur_ptr == 0x05 else "",
        },
    ]
    st.table(pd.DataFrame(reg_rows))

    st.markdown("---")
    st.markdown("#### I2C 匯流排交易模擬（I2C Transaction Simulation）")
    c_ina_w, c_ina_r = st.columns(2)

    with c_ina_w:
        st.markdown("##### ✍️ I2C 寫入命令（I2C Write）")
        st.caption("設定暫存器指標或寫入 16-bit 暫存器（例如 CONFIG 或 CALIBRATION）。")
        ina_wr_str = st.text_input(
            "寫入 Hex 位元組 (Pointer + 2 Bytes Data)",
            value="0x05 0x10 0x00",
            key="ina_write_hex_input",
            help="例：'0x05 0x10 0x00' (寫入 Cal=0x1000)、'0x00' (指標指到 CONFIG)",
        )
        if st.button("送出 I2C 寫入", key="btn_ina_write_exec"):
            try:
                bytes_send = parse_hex_bytes(ina_wr_str)
                res = ina.write(bytes_send)
                if not bytes_send:
                    st.info("I2C Address Probe: 成功尋址 INA219 (0x40)，從裝置回應 ACK。")
                else:
                    st.success(f"寫入成功！{res.get('summary', 'OK')}")
            except Exception as exc:
                st.error(f"寫入失敗：{exc}")

    with c_ina_r:
        st.markdown("##### 📖 I2C 讀取命令（I2C Read）")
        st.caption("從當前指標指向的暫存器讀出 16-bit 數值（Big-Endian 雙位元組）。")
        if st.button("送出 I2C 讀取 (2 Bytes)", key="btn_ina_read_exec"):
            try:
                read_bytes = ina.read(2)
                val_16 = (read_bytes[0] << 8) | read_bytes[1]
                ptr_name = {0x00: "CONFIG", 0x01: "SHUNT_V", 0x02: "BUS_V", 0x03: "POWER", 0x04: "CURRENT", 0x05: "CALIBRATION"}.get(ina.last_cmd, "UNKNOWN")
                st.success(f"讀取成功！暫存器 [{ptr_name}] = 0x{val_16:04X} ({list(read_bytes)})")
            except Exception as exc:
                st.error(f"讀取失敗：{exc}")

    with st.expander("📖 點擊展開：INA219 電源監控晶片校準原理與量測精度教學", expanded=False):
        st.markdown(
            """
- **硬體架構與工作原理**：
  INA219 是一款雙向高側（High-Side）電流與電壓監控器，利用串聯在電源正極路徑上的精密分流電阻（Shunt Resistor, 例如 0.1 Ω）量測微小壓降（±320 mV），並同時量測負載對地電壓（Bus Voltage 0~26V）。
- **校準暫存器（Calibration Register）之核心公式**：
  INA219 內部具備乘法器，可直接輸出電流與功率暫存器值，但必須先由韌體寫入校準值：
  - `Current_LSB = 最大預期電流 / 32768` (例如 `0.1 mA/bit = 0.0001 A/bit`)
  - `Cal = trunc(0.04096 / (Current_LSB * R_shunt))` = `trunc(40.96 / (Current_LSB(mA) * R_shunt(Ω)))`
  - 若 `R_shunt = 0.1 Ω` 且 `Current_LSB = 0.1 mA`，則 `Cal = trunc(40.96 / 0.01) = 4096 = 0x1000`。
- **未設定 Calibration 暫存器的典型陷阱**：
  若開機時未寫入 Calibration 暫存器（預設為 0x0000），則 `CURRENT (0x04)` 與 `POWER (0x03)` 暫存器將**永遠回傳 0**！此時分流電壓 `SHUNT_V (0x01)` 與匯流排電壓 `BUS_V (0x02)` 仍可正常讀取，常導致工程師誤判硬體故障。
            """
        )


def _render_pca9548a_tab() -> None:
    if "emulator_pca9548a" not in st.session_state:
        pca = VirtualPCA9548A(addr_7bit=0x70)
        # Mount diverse virtual downstream devices on channels to demonstrate isolation and conflicts
        pca.attach_device(0, VirtualLM75(addr_7bit=0x48))  # CH0: LM75 Temp #1 (0x48)
        pca.attach_device(1, VirtualLM75(addr_7bit=0x48))  # CH1: LM75 Temp #2 (0x48) - conflict with CH0!
        pca.attach_device(2, VirtualEEPROM24C64(addr_7bit=0x50))  # CH2: EEPROM #1 (0x50)
        pca.attach_device(3, VirtualINA219(addr_7bit=0x40))  # CH3: INA219 Power Monitor (0x40)
        pca.attach_device(4, VirtualLM75(addr_7bit=0x49))  # CH4: LM75 Temp #3 (0x49)
        pca.attach_device(5, VirtualEEPROM24C64(addr_7bit=0x50))  # CH5: EEPROM #2 (0x50) - conflict with CH2!
        pca.select_channel(0)
        st.session_state["emulator_pca9548a"] = pca

    pca: VirtualPCA9548A = st.session_state["emulator_pca9548a"]

    st.subheader("PCA9548A 8-Channel I2C 匯流排多工器（Mux）模擬（I2C 7-bit Addr: 0x70）")
    st.caption(
        "PCA9548A 具備 8 個可由 I2C 控制的雙向切換開關，用於解決同位址 I2C 裝置衝突、匯流排電容隔離與分支電源管理。"
        "各通道可單獨開啟、關閉，或同時啟用多個通道。"
    )

    st.markdown("#### 通道開關控制面板（Channel Switch Control）")
    active_chs = pca.get_active_channels()

    ch_cols = st.columns(8)
    new_active_chs: list[int] = []
    for ch_idx in range(8):
        with ch_cols[ch_idx]:
            is_checked = ch_idx in active_chs
            toggle = st.checkbox(
                f"CH{ch_idx}",
                value=is_checked,
                key=f"pca_ch_toggle_{ch_idx}",
                help=f"切換 Channel {ch_idx} 導通狀態",
            )
            if toggle:
                new_active_chs.append(ch_idx)

    if set(new_active_chs) != set(active_chs):
        pca.select_channels(new_active_chs)
        st.rerun()

    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([1, 1, 1, 2])
    with btn_c1:
        if st.button("開啟全部通道 (Select All)", key="btn_pca_all_on"):
            pca.select_channels(list(range(8)))
            st.rerun()
    with btn_c2:
        if st.button("關閉全部通道 (Deselect All)", key="btn_pca_all_off"):
            pca.deselect_all()
            st.rerun()
    with btn_c3:
        if st.button("硬體 RESET# 重設", key="btn_pca_hw_reset", help="模擬拉低 RESET# 腳位復位多工器"):
            pca.reset()
            st.rerun()
    with btn_c4:
        active_str = ", ".join(f"CH{c}" for c in pca.get_active_channels()) if pca.get_active_channels() else "無 (全部隔離)"
        st.info(f"Control Register: `0x{pca.read_control():02X}` (2進位: `{pca.read_control():08b}`) | 啟用中: **{active_str}**")

    st.markdown("---")
    st.markdown("#### 下游掛載裝置與位址衝突偵測（Downstream Devices & Conflict Detector）")

    conflicts = pca.detect_address_conflicts()
    if conflicts:
        conflict_details = []
        for addr, items in conflicts.items():
            ch_list = [f"CH{ch}" for ch, _ in items]
            conflict_details.append(f"位址 `0x{addr:02X}` 同時存在於作用中通道 **{', '.join(ch_list)}**")
        st.error(
            f"🚨 **偵測到 I2C 位址衝突 (Address Conflict Hazard)！**\n\n"
            f"{'；'.join(conflict_details)}。\n\n"
            f"**風險分析**：在多個相同位址通道同時導通時，發送該位址的 I2C 訊號會導致多個從裝置同時回應 ACK 及驅動 SDA 訊號線，"
            f"引發匯流排競爭（Bus Contention）、信號波形畸變或資料損毀！"
        )
    else:
        if pca.get_active_channels():
            st.success("🟢 **匯流排狀態正常**：當前所有啟用通道之下游裝置 7-bit 位址完全獨立，無位址衝突風險。")
        else:
            st.warning("⚪ **全部通道處於隔離狀態**：上游 I2C Master 無法存取任何下游分支裝置。")

    # Downstream devices inventory table
    dev_table_rows = []
    for ch in range(8):
        devs = pca.get_devices_on_channel(ch)
        is_active = ch in pca.get_active_channels()
        if not devs:
            dev_table_rows.append({
                "通道 (Channel)": f"CH{ch}",
                "導通狀態": "🟢 導通 (Active)" if is_active else "⚪ 隔離 (Disabled)",
                "掛載虛擬裝置": "(無裝置)",
                "7-bit I2C 位址": "-",
                "衝突狀態": "正常",
            })
        else:
            for d in devs:
                d_name = d.__class__.__name__.replace("Virtual", "")
                d_addr = getattr(d, "addr", 0)
                is_conflicted = is_active and (d_addr in conflicts)
                status_str = "🚨 衝突中 (Conflict!)" if is_conflicted else ("🟢 作用中" if is_active else "⚪ 隔離中")
                dev_table_rows.append({
                    "通道 (Channel)": f"CH{ch}",
                    "導通狀態": "🟢 導通 (Active)" if is_active else "⚪ 隔離 (Disabled)",
                    "掛載虛擬裝置": d_name,
                    "7-bit I2C 位址": f"0x{d_addr:02X}",
                    "衝突狀態": status_str,
                })
    st.table(pd.DataFrame(dev_table_rows))

    st.markdown("---")
    st.markdown("#### 跨多工器 I2C 交易路由測試（I2C Transaction Routing）")
    c_rt1, c_rt2 = st.columns(2)
    with c_rt1:
        st.markdown("##### ✍️ 透過 Mux 發送 I2C Write 指令")
        rt_addr_str = st.text_input("目標 7-bit I2C 位址", value="0x48", key="pca_rt_addr_input")
        rt_data_str = st.text_input("寫入資料 Hex Bytes", value="0x00", key="pca_rt_data_input")
        if st.button("送出 I2C Write 路由", key="btn_pca_rt_write"):
            try:
                t_addr = parse_hex_or_dec_int(rt_addr_str, label="目標位址")
                t_bytes = parse_hex_bytes(rt_data_str)
                w_res = pca.route_write(t_addr, t_bytes)
                if not w_res:
                    st.warning(f"無裝置回應：在當前導通通道中未找到位址 0x{t_addr:02X} 的裝置（或通道未開啟）。")
                else:
                    st.success(f"成功路由至 {len(w_res)} 個裝置！")
                    for item in w_res:
                        st.write(f"- 通道 CH{item['channel']} 裝置 `{item['device'].__class__.__name__}`: {item['result']}")
            except Exception as exc:
                st.error(f"路由失敗：{exc}")

    with c_rt2:
        st.markdown("##### 📖 透過 Mux 發送 I2C Read 指令")
        rt_rd_addr_str = st.text_input("讀取目標 7-bit I2C 位址", value="0x48", key="pca_rt_rd_addr_input")
        rt_rd_len = st.number_input("讀取長度 (Bytes)", min_value=1, max_value=8, value=2, key="pca_rt_rd_len")
        if st.button("送出 I2C Read 路由", key="btn_pca_rt_read"):
            try:
                t_addr = parse_hex_or_dec_int(rt_rd_addr_str, label="目標位址")
                r_res = pca.route_read(t_addr, int(rt_rd_len))
                if not r_res:
                    st.warning(f"無裝置回應：在當前導通通道中未找到位址 0x{t_addr:02X} 的裝置。")
                elif len(r_res) > 1:
                    st.error(f"🚨 **多裝置同時回應碰撞！** 偵測到 {len(r_res)} 個裝置在不同通道同時回應資料：")
                    for ch, dev, data in r_res:
                        st.write(f"- CH{ch} `{dev.__class__.__name__}`: `{list(data)}` ({data.hex()})")
                else:
                    ch, dev, data = r_res[0]
                    st.success(f"讀取成功！來自 CH{ch} `{dev.__class__.__name__}`: `{list(data)}` (0x{data.hex().upper()})")
            except Exception as exc:
                st.error(f"讀取失敗：{exc}")

    with st.expander("📖 點擊展開：PCA9548A I2C 多工器設計原理與防死鎖教學", expanded=False):
        st.markdown(
            """
- **位址衝突解決方案**：
  許多 I2C 感測器（如 LM75、SFP 模組 0x50 等）的硬體位址腳位有限或固定。當單一主機板需要連接 8 個相同位址的感測器時，可透過 PCA9548A 將單一 I2C 匯流排分出 8 條獨立分支（Sub-buses）。
- **匯流排電容分割（Capacitance Splitting）**：
  I2C 規範限制標準模式與快速模式下的總匯流排電容上限為 400 pF。透過 Mux 切割分支，每條分支的走線電容與裝置負載互不疊加，可大幅提升長距離或多背板通訊之信號完整性。
- **同時開啟多通道的位址衝突陷阱**：
  PCA9548A 允許韌體同時設定多個通道導通（例如向 Control Register 寫入 `0x03` 同時開啟 CH0 與 CH1）。若這兩個通道上掛載了相同位址的周邊，Master 發起交易時兩個 Slave 會同時嘗試驅動 SDA，造成資料混淆或總線死鎖。
- **硬體 RESET# 引腳與防死鎖恢復（Bus Lockup Recovery）**：
  當某條下游分支的從裝置在 ACK 或資料傳輸途中異常卡死在 SDA=LOW（造成整個 I2C 匯流排被拉住）時，主控端可透過 GPIO 拉低 PCA9548A 的硬體 `RESET#` 引腳。復位後所有通道立即關閉（隔離故障分支），讓主匯流排立刻恢復正常通訊。
            """
        )


def render() -> None:
    st.header("虛擬設備模擬器實驗室（Emulator Playground）")
    st.caption(
        "本實驗室提供五種嵌入式系統中最核心的虛擬周邊設備（I2C LM75 溫度感測器、"
        "SPI NOR Flash W25Q128、I2C EEPROM 24C64、INA219 電源監控晶片、PCA9548A I2C 多工器）。"
        "無需實體硬體即可體驗暫存器讀寫、Page Rollover 跨頁回繞、校準計算、Mux 隔離與位址衝突偵測等底層硬體行為。"
    )

    tab_lm75, tab_flash, tab_eeprom, tab_ina, tab_mux = st.tabs(
        [
            "🌡️ LM75 溫度感測器模擬 (I2C)",
            "⚡ SPI Flash W25Q128 模擬 (16MB NOR)",
            "💾 EEPROM 24C64 模擬 (I2C 8KB)",
            "⚡ INA219 電流/功率監控 (I2C)",
            "🔀 PCA9548A 8-Ch I2C Mux",
        ]
    )

    with tab_lm75:
        _render_lm75_tab()

    with tab_flash:
        _render_spi_flash_tab()

    with tab_eeprom:
        _render_eeprom_tab()

    with tab_ina:
        _render_ina219_tab()

    with tab_mux:
        _render_pca9548a_tab()


__all__ = ["render"]
