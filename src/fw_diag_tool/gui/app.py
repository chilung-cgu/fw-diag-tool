from pathlib import Path

import pandas as pd
import streamlit as st

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog
from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events, raw_decode_to_waveform
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.resources import load_i2c_sample
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)

st.set_page_config(page_title="FW Diagnostic Toolkit", page_icon="⚡", layout="wide")
st.title("⚡ Firmware Signal & Protocol Diagnostic Suite")
st.caption("Local I2C/PMBus protocol diagnostics and firmware learning workstation")

menu = st.sidebar.radio(
    "功能導覽",
    [
        "📊 I2C / PMBus 診斷與波形檢視",
        "🎨 I2C 封包模擬器與驅動產生",
        "⚖️ 雙波形對比檢視 (Waveform Diff)",
        "📟 UART Crash & HardFault 分析",
        "🌐 MCTP / IPMB 伺服器協定解析",
        "🌲 Device Tree (.dts) 產生器",
        "🚀 PCIe Config & AER 診斷",
        "⚡ SPI Flash 協定診斷",
        "🎛 晶片暫存器 Bitfield 解碼器",
        "🛠 C 語言 Register 巨集產生器",
        "🏆 Junior FW 實戰除錯實驗室 (Fault Arena)",
        "📚 韌體除錯指南 & SOP",
    ],
)

# 1. I2C / PMBus
if menu == "📊 I2C / PMBus 診斷與波形檢視":
    st.header("I2C / SMBus / PMBus 協定分析與數位波形檢視")
    input_mode = st.radio(
        "輸入資料型態",
        ["Saleae Analyzer table / text trace", "Raw digital transition (Time, SCL, SDA)"],
        horizontal=True,
        help="Analyzer table 可做協定/語意診斷；raw digital transition 才能保留實際 SCL/SDA 0/1 邊緣與量測頻率。",
    )
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader(
            "選擇或拖放 Saleae CSV / Trace 檔案",
            type=["csv", "txt", "log"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    with col2:
        smbus_timeout = st.number_input(
            "SMBus Clock Stretching Timeout (ms)",
            min_value=1.0,
            max_value=100.0,
            value=25.0,
            step=1.0,
        )
        use_sample = st.button("載入內建測試波形")

    csv_content = None
    raw_capture_result = None
    if uploaded_file is not None:
        try:
            csv_content = decode_uploaded_text(
                uploaded_file, allowed_extensions={".csv", ".txt", ".log"}
            )
        except ValueError as exc:
            st.error(f"無法讀取 trace：{exc}")
    elif use_sample:
        if input_mode == "Raw digital transition (Time, SCL, SDA)":
            st.warning(
                "內建範例是 decoded analyzer CSV；請上傳含 Time/SCL/SDA 的 raw digital CSV。"
            )
        else:
            csv_content = load_i2c_sample()
            st.info("已載入內建範例 CSV！")

    if csv_content:
        engine = I2CDiagnosticEngine(smbus_timeout_ms=smbus_timeout)
        try:
            if input_mode == "Raw digital transition (Time, SCL, SDA)":
                raw_capture_result = analyze_raw_i2c_csv(csv_content)
                report = engine.analyze(raw_decode_to_events(raw_capture_result))
            else:
                report = engine.analyze_csv_content(csv_content)
        except ValueError as exc:
            st.error(f"無法解析 I2C 輸入：{exc}")
            st.stop()
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("總傳輸次數", report.total_transactions)
        kpi2.metric(
            "異常事件數",
            len(report.issues),
            delta=f"-{len(report.issues)}" if report.issues else "0",
            delta_color="inverse",
        )
        timing = report.timing_stats
        if timing.frequency_sample_count:
            kpi3.metric(
                "平均時鐘頻率",
                f"{timing.avg_frequency_khz:.1f} kHz",
                help="由來源提供的 bitrate 或 byte duration 推算；不是從 analyzer table 的交易時間臆測。",
            )
            kpi4.metric(
                "時鐘抖動 (Jitter)",
                f"{timing.frequency_jitter_pct:.1f} %",
                help="僅對有來源 timing evidence 的頻率樣本計算。",
            )
        else:
            kpi3.metric(
                "平均時鐘頻率",
                "不可用",
                help="目前檔案沒有 per-byte bitrate/duration；請匯出 raw digital SCL/SDA transition 才能量測。",
            )
            kpi4.metric(
                "時鐘抖動 (Jitter)",
                "不可用",
                help="沒有頻率樣本，因此不顯示 0% 這種容易誤解的數字。",
            )
        if report.data_quality_issues:
            with st.expander("⚠ 資料證據與限制（先看這裡）", expanded=True):
                st.caption(
                    "診斷結果只代表檔案中實際提供的欄位；缺少 timestamp、ACK 或 SCL/SDA edge 時，工具不會把未知值當成正常。"
                )
                for quality in report.data_quality_issues:
                    st.markdown(f"- **{quality.code}**（{quality.count} 筆）：{quality.message}")
        st.divider()

        tab_wave, tab_anom, tab_timing, tab_tx, tab_md = st.tabs(
            [
                "📈 數位方波與協定軌 (Waveform)",
                "🚨 異常診斷 (Anomalies)",
                "📊 匯流排時序與健康圖表",
                "📜 封包交易列表",
                "📝 Markdown 診斷報告",
            ]
        )

        with tab_wave:
            st.subheader("I2C 互動式數位方波與協定疊加 (SCL / SDA / Protocol Overlay)")
            if report.transactions:
                tx_options = [
                    f"Tx #{t.id}: 0x{t.address_7bit:02X} ({t.direction.value}) - {t.semantic_summary or t.hex_dump}"
                    for t in report.transactions
                ]
                selected_tx_str = st.selectbox("選擇要檢視波形的交易", tx_options)
                selected_idx = (
                    tx_options.index(selected_tx_str) if selected_tx_str in tx_options else 0
                )
                selected_tx = report.transactions[selected_idx]
                if raw_capture_result is not None:
                    st.success(
                        "這是 Logic Analyzer raw digital transition 的實測 0/1 波形；"
                        "它不是類比電壓/上升時間量測。"
                    )
                    st.plotly_chart(
                        I2CWaveformReconstructor.create_plotly_figure(
                            raw_decode_to_waveform(raw_capture_result),
                            title="Measured Raw Digital I2C Waveform & Protocol Overlay",
                        ),
                        width="stretch",
                    )
                    st.caption(
                        f"目前選取 Tx #{selected_tx.id}；raw view 顯示整段 capture，"
                        "可用 hover 對照 START/byte/ACK/STOP。"
                    )
                else:
                    measured_clock_khz = (
                        timing.avg_frequency_khz if timing.frequency_sample_count else None
                    )
                    if measured_clock_khz is None:
                        st.info(
                            "目前顯示的是重建波形（Reconstructed），不是邏輯分析儀實測電壓波形。"
                            "此 CSV 沒有 SCL/SDA edge；若要看真實時序，請使用 raw digital transition 匯出。"
                        )
                    else:
                        st.caption(
                            "波形時鐘使用來源 timing evidence；仍屬協定層重建，非類比電壓量測。"
                        )
                    reconstructor = I2CWaveformReconstructor(
                        default_clock_khz=measured_clock_khz or 100.0
                    )
                    wave_data = reconstructor.reconstruct_transaction_waveform(selected_tx)
                    fig = reconstructor.create_plotly_figure(
                        wave_data,
                        title=f"Reconstructed Tx #{selected_tx.id} Waveform: 0x{selected_tx.address_7bit:02X} {selected_tx.direction.value}",
                    )
                    st.plotly_chart(fig, width="stretch")
            else:
                st.info("無交易資料可繪製波形。")

        with tab_anom:
            if not report.issues:
                if report.data_quality_issues:
                    st.warning("沒有被證明的協定異常；但資料證據不完整，不能直接視為完全正常。")
                else:
                    st.success("🎉 未偵測到任何 I2C/SMBus 時序與通訊異常！")
            else:
                for idx, issue in enumerate(report.issues, 1):
                    addr_str = (
                        f"0x{issue.address_7bit:02X}" if issue.address_7bit is not None else "N/A"
                    )
                    with st.expander(
                        f"[{issue.severity.value}] #{idx}: {issue.code} - {issue.title} (Addr: {addr_str})",
                        expanded=True,
                    ):
                        st.markdown(f"**現象描述**: {issue.description}")
                        st.markdown(
                            f"**可能原因（Hypotheses；不是已證明的根因）**:\n{issue.root_cause_analysis}"
                        )
                        st.markdown("**排查行動清單**:")
                        for adv in issue.actionable_advice:
                            st.markdown(f"- ✔ {adv}")

        with tab_timing:
            st.subheader("匯流排物理層健康評等")
            st.caption(
                "健康評等只使用已知 ACK/NACK；READ 最後一個 controller NACK 是正常結束。"
                "缺少 ACK 時顯示 N/A，不把未知當成功。"
            )
            st.table(I2CTimingCharts.get_device_health_summary(report))
            c_t1, c_t2 = st.columns(2)
            with c_t1:
                st.plotly_chart(
                    I2CTimingCharts.create_frequency_distribution(report), width="stretch"
                )
            with c_t2:
                st.plotly_chart(
                    I2CTimingCharts.create_bus_activity_timeline(report), width="stretch"
                )

        with tab_tx:
            tx_data = [
                {
                    "ID": t.id,
                    "Time (s)": f"{t.start_time:.6f}",
                    "Address": f"0x{t.address_7bit:02X}",
                    "Direction": t.direction.value,
                    "ACK": t.address_ack.value,
                    "Topology": t.mux_topology or "-",
                    "Bytes": len(t.data_bytes),
                    "Data": t.hex_dump,
                    "Semantic Meaning": t.semantic_summary or "-",
                }
                for t in report.transactions
            ]
            st.dataframe(pd.DataFrame(tx_data), width="stretch")

        with tab_md:
            md_out = I2CReporter.generate_markdown(report)
            st.code(md_out, language="markdown")
            st.download_button("下載 Markdown 報告", md_out, file_name="i2c_report.md")

# 2. Packet Builder & Driver CodeGen
elif menu == "🎨 I2C 封包模擬器與驅動產生":
    st.header("I2C 封包自訂建構、理想波形生成與多平台 C 驅動產出")
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    with b_col1:
        builder_addr_str = st.text_input("Slave 7-bit Address", value="0x50")
    with b_col2:
        builder_op = st.selectbox("Operation (R/W)", ["Write", "Read"])
    with b_col3:
        builder_reg_str = st.text_input("Register Offset", value="0x00")
    with b_col4:
        builder_data_str = st.text_input("Data Bytes (Hex)", value="0x12 0x34")
    try:
        b_addr = int(builder_addr_str, 16)
        b_reg = int(builder_reg_str, 16)
        b_data = [int(tok, 16) for tok in builder_data_str.split() if tok]
        is_read_op = builder_op == "Read"
        from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction

        mock_tx = I2CTransaction(
            id=1,
            start_time=0.0,
            end_time=0.0001,
            address_7bit=b_addr,
            address_8bit=(b_addr << 1) | (1 if is_read_op else 0),
            direction=I2CDirection.READ if is_read_op else I2CDirection.WRITE,
            data_bytes=b_data if not is_read_op else ([b_reg] if b_reg is not None else []),
            address_ack=AckType.ACK,
            has_stop=True,
            command_code=b_reg,
        )
        reconstructor = I2CWaveformReconstructor(default_clock_khz=100.0)
        wave_data = reconstructor.reconstruct_transaction_waveform(mock_tx)
        st.plotly_chart(
            reconstructor.create_plotly_figure(
                wave_data, title=f"Ideal Waveform: {builder_op} 0x{b_addr:02X} Reg: 0x{b_reg:02X}"
            ),
            width="stretch",
        )
        st.subheader("一鍵生成多平台 C 語言驅動代碼")
        snippets = I2CDriverCodeGenerator.generate_all_snippets(
            addr_7bit=b_addr, reg_offset=b_reg, data_bytes=b_data, is_read=is_read_op
        )
        for plat, code_txt in snippets.items():
            with st.expander(f"💻 {plat}", expanded=True):
                st.code(code_txt, language="c" if "CLI" not in plat else "bash")
    except Exception as e:
        st.error(f"輸入格式錯誤: {e}")

# 3. Waveform Diff
elif menu == "⚖️ 雙波形對比檢視 (Waveform Diff)":
    st.header("Golden (正常板卡) vs Failing (故障板卡) 雙波形差分對比")
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        golden_file = st.file_uploader(
            "上傳 Golden (正常) Trace CSV",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    with d_col2:
        failing_file = st.file_uploader(
            "上傳 Failing (故障) Trace CSV",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    if golden_file and failing_file:
        try:
            g_text = decode_uploaded_text(golden_file, allowed_extensions={".csv", ".txt"})
            f_text = decode_uploaded_text(failing_file, allowed_extensions={".csv", ".txt"})
        except ValueError as exc:
            st.error(f"無法讀取比較 trace：{exc}")
            st.stop()
        eng = I2CDiagnosticEngine()
        g_rep = eng.analyze_csv_content(g_text)
        f_rep = eng.analyze_csv_content(f_text)
        diff_res = WaveformDiffEngine.compare_reports(g_rep, f_rep)
        if diff_res.is_identical:
            st.success("🎉 Golden 與 Failing 兩份波形在協定層完全一致！")
        else:
            st.error(f"🚨 {diff_res.summary}")
            for dp in diff_res.divergence_points:
                with st.expander(
                    f"分歧點: 交易 #{dp.tx_index} ({dp.mismatch_type})", expanded=True
                ):
                    st.markdown(f"**現象描述**: {dp.description}")
                    st.markdown(f"**排查建議**: {dp.root_cause_hint}")
            st.plotly_chart(WaveformDiffEngine.create_comparison_figure(diff_res), width="stretch")

# 4. UART Crash Dump
elif menu == "📟 UART Crash & HardFault 分析":
    st.header("UART Serial Crash Dump & ARM Cortex-M HardFault 智慧診斷")
    u_mode = st.radio(
        "選擇輸入方式",
        [
            "貼上 UART Log / Crash Dump",
            "載入範例 Linux Kernel Panic Log",
            "載入範例 ARM HardFault Log",
        ],
    )
    u_raw = ""
    if u_mode == "貼上 UART Log / Crash Dump":
        u_raw = st.text_area("請貼上 UART 輸出內容：", height=200)
    elif u_mode == "載入範例 Linux Kernel Panic Log":
        u_raw = """BUG: unable to handle page fault for address: 0000000000000010\nRIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\nRAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000\nCR2: 0000000000000010\nCall Trace:\n <TASK>\n [ffff888100123450] blk_mq_complete_request+0x24/0x50\n [ffff8881001234a0] nvme_irq_handler+0x8c/0x100 [nvme]\n </TASK>"""
    else:
        u_raw = """HardFault Exception Occurred!\nHFSR: 0x40000000 (FORCED)\nCFSR: 0x02000000 (DIVBYZERO)\nStacked R0: 0x00000000\nStacked R1: 0x0000000A\nStacked PC: 0x08001234\nStacked LR: 0x08000456\nStacked xPSR: 0x61000000"""
    if st.button("執行 UART Crash 分析") and u_raw.strip():
        u_report = UARTCrashParser.parse_log_text(u_raw)
        st.markdown(UARTReporter.to_markdown(u_report))

# 5. MCTP / IPMB
elif menu == "🌐 MCTP / IPMB 伺服器協定解析":
    st.header("MCTP (DSP0236/PLDM/SPDM) 與 IPMB 伺服器管理協定解碼")
    m_raw = st.text_area(
        "請輸入 MCTP 或 IPMB 封包 Hex Dump (每行一封包)：",
        height=150,
        value="08 00 80 01 00 02 01 00\n20 18 C8 81 20 01 56",
    )
    if st.button("執行伺服器協定解碼") and m_raw.strip():
        m_report = ServerMgmtParser.parse_text_dump(m_raw)
        st.markdown(ServerMgmtReporter.to_markdown(m_report))

# 6. Device Tree Generator
elif menu == "🌲 Device Tree (.dts) 產生器":
    st.header("Linux Kernel & OpenBMC Device Tree Source (.dts) 自動生成")
    dt_b1, dt_b2 = st.columns(2)
    with dt_b1:
        dts_bus = st.number_input("I2C Bus Number (&i2c...)", min_value=0, max_value=32, value=1)
    with dt_b2:
        dts_mux = st.text_input("PCA9548A MUX Address", value="0x70")
    dts_code = DeviceTreeGenerator.generate_dts_from_topology(
        bus_num=dts_bus, mux_addr=int(dts_mux, 16)
    )
    st.code(dts_code, language="dts")
    st.download_button("下載 i2c_bus.dtsi", dts_code, file_name=f"i2c_bus{dts_bus}.dtsi")

# 7. PCIe
elif menu == "🚀 PCIe Config & AER 診斷":
    st.header("PCIe 配置空間、Capability 鏈表與 AER 嚴重錯誤診斷")
    input_mode = st.radio(
        "輸入方式", ["貼上 lspci -xxxx / Hex Dump", "貼上 Linux dmesg AER Error Log"]
    )
    raw_input = st.text_area("輸入 Log 或 Dump 內容：", height=200)
    if st.button("執行 PCIe 分析") and raw_input.strip():
        if input_mode == "貼上 Linux dmesg AER Error Log":
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(f"Kernel dmesg AER 診斷結果 (共 {len(events)} 個事件)")
            for idx, ev in enumerate(events, 1):
                with st.expander(
                    f"事件 #{idx}: {ev.bdf} - {ev.error_name} ({ev.severity})", expanded=True
                ):
                    st.markdown(f"**原始日誌**: `{ev.raw_line}`")
                    st.markdown("**Root Cause 排查 SOP**:\n" + ev.root_cause_guide)
        else:
            devices = PCIeAnalyzer.parse_multi_lspci_text(raw_input)
            if not devices:
                bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(raw_input)
                devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
            for cfg in devices:
                c1, c2, c3 = st.columns(3)
                c1.metric("Vendor / Device ID", f"0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}")
                c2.metric("Header Type", cfg.header_type.name)
                c3.metric(
                    "Capabilities", len(cfg.standard_capabilities) + len(cfg.extended_capabilities)
                )
                if cfg.link_info and cfg.link_info.is_degraded:
                    st.error(f"🚨 {cfg.link_info.degradation_reason}")
                st.markdown(PCIeReporter.to_markdown(cfg))

# 8. SPI Flash
elif menu == "⚡ SPI Flash 協定診斷":
    st.header("SPI / QSPI Flash 協定解析與寫入異常診斷")
    uploaded_spi = st.file_uploader(
        "選擇 Saleae SPI CSV 檔案",
        type=["csv", "txt"],
        max_upload_size=MAX_UPLOAD_MIB,
    )
    csv_text = None
    if uploaded_spi is not None:
        try:
            csv_text = decode_uploaded_text(uploaded_spi, allowed_extensions={".csv", ".txt"})
        except ValueError as exc:
            st.error(f"無法讀取 SPI trace：{exc}")
    if csv_text:
        engine = SPIDiagnosticEngine()
        rep = engine.analyze_csv_content(csv_text)
        SPIReporter.render_terminal(rep)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("總傳輸次數", rep.summary.total_transactions)
        s2.metric("讀取次數", rep.summary.read_count)
        s3.metric("Page Program 寫入", rep.summary.write_count)
        s4.metric("異常事件", rep.summary.anomaly_count)
        if rep.summary.detected_flash_chip:
            st.info(f"識別晶片型號: {rep.summary.detected_flash_chip}")
        st.markdown(SPIReporter.to_markdown(rep))

# 9. Register Decoder
elif menu == "🎛 晶片暫存器 Bitfield 解碼器":
    st.header("硬體 / 晶片暫存器 Bitfield 視覺化解碼器")
    builtin_map = {
        "PMBus 標準狀態暫存器 (PMBus STATUS_WORD)": "pmbus_standard.yaml",
        "PCIe AER Uncorrectable Error 暫存器": "pcie_aer_registers.yaml",
    }
    choice = st.selectbox("選擇預設暫存器定義檔", list(builtin_map.keys()))
    data_dir = Path(__file__).parent.parent / "data"
    yaml_file = data_dir / builtin_map[choice]
    catalog = RegisterMapCatalog()
    if yaml_file.exists():
        catalog.load_from_yaml(yaml_file.read_text(encoding="utf-8"))
    reg_names = list(catalog.name_map.keys())
    if reg_names:
        r1, r2 = st.columns(2)
        with r1:
            sel_reg = st.selectbox("選擇暫存器", [r.upper() for r in reg_names])
        with r2:
            raw_val_str = st.text_input(
                "輸入暫存器 Raw Hex (如 0x8400, 0x00040000)", value="0x8400"
            )
        try:
            cur_val = int(raw_val_str, 0)
        except ValueError:
            st.error("暫存器值格式錯誤；請輸入整數或 0x 開頭的十六進位值。")
        else:
            res = catalog.decode_register(sel_reg, cur_val)
            st.subheader(f"{res.reg_name} (0x{cur_val:08X})")
            st.table(
                pd.DataFrame(
                    [
                        {
                            "Bit Range": f.bit_range,
                            "Field": f.name,
                            "Value": f.hex_val,
                            "Meaning": f"⚠ {f.meaning}" if f.is_warning else f.meaning,
                        }
                        for f in res.fields
                    ]
                )
            )

# 10. C Codegen
elif menu == "🛠 C 語言 Register 巨集產生器":
    st.header("YAML 暫存器定義檔 -> C 語言 Header (#define / RMW 巨集) 自動生成")
    data_dir = Path(__file__).parent.parent / "data"
    builtin_yamls = list(data_dir.glob("*.yaml"))
    choice_yaml = st.selectbox("選擇 YAML 範本", [y.name for y in builtin_yamls])
    gen = CHeaderGenerator.from_yaml_file(data_dir / choice_yaml)
    mod_name = st.text_input(
        "模組名稱 (Module Name)", value=choice_yaml.replace(".yaml", "").upper()
    )
    c_header = gen.generate_header(module_name=mod_name)
    st.code(c_header, language="c")
    st.download_button(f"下載 {mod_name.lower()}.h", c_header, file_name=f"{mod_name.lower()}.h")

# 11. Fault Arena
elif menu == "🏆 Junior FW 實戰除錯實驗室 (Fault Arena)":
    st.header("Junior Firmware 工程師 20 大經典硬韌體故障演練場")
    arena_cases = [
        "Case 01: I2C Address NACK (Slave 未上電 / Address Pin 浮接)",
        "Case 02: I2C Data NACK (EEPROM 內部寫入週期 tWR 忙碌中)",
        "Case 03: I2C Clock Stretching 逾時 (> 25ms SMBus Hang)",
        "Case 04: I2C EEPROM 24C64 Page Boundary 跨頁覆蓋風險",
        "Case 05: I2C PCA9548A MUX 多通道同時開啟引發匯流排衝突",
        "Case 06: PMBus VOUT_TRIM 負值補碼計算溢位 (127V 誤報)",
        "Case 07: PCIe Gen4 x16 降速至 Gen1 x1 (金手指髒污/SI劣化)",
        "Case 08: PCIe AER Completion Timeout (目標設備 AXI 狀態機死鎖)",
        "Case 09: PCIe AER Malformed TLP (封包長度違反 Max Payload Size)",
        "Case 10: PCIe AER Poisoned TLP (上游主記憶體 ECC 錯誤)",
        "Case 11: SPI NOR Flash Page Program 遺漏 0x06 WREN 寫入無效",
        "Case 12: SPI NOR Flash Page Buffer 256B Wrap-Around 覆蓋",
        "Case 13: SPI JEDEC 讀回全 0xFF (MISO 線路浮接 / 供電斷開)",
        "Case 14: SPI JEDEC 讀回全 0x00 (MISO 對地短路 / 匯流排被鉗位)",
        "Case 15: Linux Kernel Panic: NULL Pointer Dereference at Offset 0x10",
        "Case 16: ARM Cortex-M HardFault: DIVBYZERO 除以零中斷陷阱",
        "Case 17: ARM Cortex-M HardFault: UNALIGNED 未對齊 32-bit 指標存取",
        "Case 18: ARM Cortex-M HardFault: IMPRECISERR 異步總線寫入錯誤",
        "Case 19: MCTP PLDM 感測器數值傳輸異常與封包順序錯亂",
        "Case 20: IPMB Checksum 1/2 校驗碼錯誤引發封包丟棄",
    ]
    sel_case = st.selectbox("選擇實戰演練案例", arena_cases)
    st.info(f"【案例分析】{sel_case}")
    st.markdown("**【標準排查 SOP & Root Cause 診斷】**:")
    if "01:" in sel_case:
        st.markdown(
            "1. 檢查 Slave 晶片供電 (3.3V/1.8V)。\n2. 檢查硬體 A0/A1/A2 位址設定腳位。\n3. 檢查 7-bit 位址是否未左移。"
        )
    elif "07:" in sel_case:
        st.markdown(
            "1. 檢查 PCIe 插槽金手指與 Riser 卡接觸面。\n2. 檢查 100MHz 差分時脈 (REFCLK) 抖動。\n3. 檢查主機板 BIOS Link Speed 設定。"
        )
    elif "11:" in sel_case:
        st.markdown(
            "1. 每次 Page Program 或 Erase 前必須發送 0x06 (WREN)。\n2. 檢查 Status Register 1 WEL 位元是否為 1。"
        )
    elif "15:" in sel_case:
        st.markdown(
            "1. 檢查 probe 函式中 kzalloc 是否成功。\n2. 使用 addr2line -e vmlinux <RIP> 定位原始碼行號。"
        )
    else:
        st.markdown(
            "1. 參照分層 L1~L7 診斷模型，先確認硬體電氣訊號，再分析協定 Frame 格式，最後檢查驅動狀態機。"
        )

# 12. SOP
elif menu == "📚 韌體除錯指南 & SOP":
    st.header("Junior Firmware 工程師硬韌體除錯指南與心智模型")
    st.markdown("""
### 🎯 核心原則：Layer 分層診斷心智模型

1. **L1 物理層 (PHY)**: 檢查上拉電阻 (Pull-up)、檢查 100MHz 差分時鐘、示波器 Eyes Diagram。
2. **L2 資料鏈結層 (Data Link)**: I2C ACK/NACK, Clock Stretching, PCIe DLP Error (`fw-diag i2c analyze`)。
3. **L3 傳輸/協定層 (Protocol)**: PMBus, PCIe AER, SPI Opcode (`fw-diag pcie analyze`, `fw-diag spi analyze`)。
4. **L7 應用/驅動層 (Application)**: Linux Kernel Driver, OpenBMC (`fw-diag reg decode`, `fw-diag gen c-header`)。
""")
