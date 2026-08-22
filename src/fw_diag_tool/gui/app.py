from pathlib import Path

import pandas as pd
import streamlit as st

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog
from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter

st.set_page_config(page_title="FW Diagnostic Toolkit", page_icon="⚡", layout="wide")
st.title("⚡ Firmware Signal & Protocol Diagnostic Toolkit")
st.caption("Cross-platform Logic Analyzer & System Trace RCA Assistant for Junior Firmware Engineers")

menu = st.sidebar.radio(
    "功能導覽",
    [
        "📊 I2C / PMBus 波形診斷",
        "🚀 PCIe Config & AER 診斷",
        "⚡ SPI Flash 協定診斷",
        "🎛 晶片暫存器 Bitfield 解碼器",
        "🛠 C 語言 Register 巨集產生器",
        "🧪 Junior FW 故障模擬實驗室 (Fault Lab)",
        "📚 韌體除錯指南 & SOP"
    ]
)

# -------------------------------------------------------------
# 1. I2C / PMBus
# -------------------------------------------------------------
if menu == "📊 I2C / PMBus 波形診斷":
    st.header("I2C / SMBus / PMBus 波形異常與協定分析")
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader("選擇或拖放 Saleae CSV / Trace 檔案", type=["csv", "txt", "log"])
    with col2:
        smbus_timeout = st.number_input("SMBus Clock Stretching Timeout (ms)", min_value=1.0, max_value=100.0, value=25.0, step=1.0)
        use_sample = st.button("載入內建測試波形")

    csv_content = None
    if uploaded_file is not None:
        csv_content = uploaded_file.getvalue().decode("utf-8")
    elif use_sample:
        sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "data" / "saleae_normal_pmbus_eeprom.csv"
        if sample_path.exists():
            csv_content = sample_path.read_text(encoding="utf-8")
            st.info("已載入內建範例 CSV！")

    if csv_content:
        engine = I2CDiagnosticEngine(smbus_timeout_ms=smbus_timeout)
        report = engine.analyze_csv_content(csv_content)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("總傳輸次數", report.total_transactions)
        kpi2.metric("異常事件數", len(report.issues), delta=f"-{len(report.issues)}" if report.issues else "0", delta_color="inverse")
        kpi3.metric("平均時鐘頻率", f"{report.timing_stats.avg_frequency_khz:.1f} kHz")
        kpi4.metric("時鐘抖動 (Jitter)", f"{report.timing_stats.frequency_jitter_pct:.1f} %")
        st.divider()

        tab1, tab2, tab3, tab4 = st.tabs(["🚨 異常診斷", "📈 時序與設備地圖", "📜 交易列表", "📝 Markdown 報告"])
        with tab1:
            if not report.issues:
                st.success("🎉 未偵測到任何 I2C/SMBus 時序與通訊異常！")
            else:
                for idx, issue in enumerate(report.issues, 1):
                    addr_str = f"0x{issue.address_7bit:02X}" if issue.address_7bit is not None else "N/A"
                    with st.expander(f"[{issue.severity.value}] #{idx}: {issue.code} - {issue.title} (Addr: {addr_str})", expanded=True):
                        st.markdown(f"**現象描述**: {issue.description}")
                        st.markdown(f"**根本原因 (Root Cause)**:\n{issue.root_cause_analysis}")
                        st.markdown("**排查行動清單**:")
                        for adv in issue.actionable_advice:
                            st.markdown(f"- ✔ {adv}")

        with tab2:
            if report.devices_detected:
                st.subheader("偵測到的週邊設備分佈")
                dev_df = pd.DataFrame(list(report.devices_detected.values()))
                st.dataframe(dev_df, use_container_width=True)
            st.subheader("匯流排時序與健康指標")
            st.write(f"- 速度模式: `{report.timing_stats.speed_mode.value}`")
            st.write(f"- Clock Stretching 次數: `{report.timing_stats.clock_stretch_count}` (最大時長: `{report.timing_stats.max_clock_stretch_ms:.3f} ms`)")
            st.write(f"- 匯流排使用率 (Bus Utilization): `{report.timing_stats.bus_utilization_pct:.2f} %`")

        with tab3:
            tx_data = []
            for t in report.transactions:
                tx_data.append({
                    "ID": t.id,
                    "Time (s)": f"{t.start_time:.6f}",
                    "Address": f"0x{t.address_7bit:02X}",
                    "Direction": t.direction.value,
                    "ACK": t.address_ack.value,
                    "Topology": t.mux_topology or "-",
                    "Bytes": len(t.data_bytes),
                    "Data": t.hex_dump,
                    "Semantic Meaning": t.semantic_summary or "-"
                })
            st.dataframe(pd.DataFrame(tx_data), use_container_width=True)

        with tab4:
            md_out = I2CReporter.generate_markdown(report)
            st.code(md_out, language="markdown")
            st.download_button("下載 Markdown 報告", md_out, file_name="i2c_report.md")

# -------------------------------------------------------------
# 2. PCIe & AER
# -------------------------------------------------------------
elif menu == "🚀 PCIe Config & AER 診斷":
    st.header("PCIe 配置空間、Capability 鏈表與 AER 嚴重錯誤診斷")
    input_mode = st.radio("輸入方式", ["貼上 lspci -xxxx / Hex Dump", "貼上 Linux dmesg AER Error Log"])
    raw_input = st.text_area("輸入 Log 或 Dump 內容：", height=200)
    if st.button("執行 PCIe 分析") and raw_input.strip():
        if "PCIe Bus Error:" in raw_input or ("AER:" in raw_input and "00:" not in raw_input):
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(f"Kernel dmesg AER 診斷結果 (共 {len(events)} 個事件)")
            for idx, ev in enumerate(events, 1):
                with st.expander(f"事件 #{idx}: {ev.bdf} - {ev.error_name} ({ev.severity})", expanded=True):
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
                c3.metric("Capabilities", len(cfg.standard_capabilities) + len(cfg.extended_capabilities))
                if cfg.link_info and cfg.link_info.is_degraded:
                    st.error(f"🚨 {cfg.link_info.degradation_reason}")
                st.markdown(PCIeReporter.to_markdown(cfg))

# -------------------------------------------------------------
# 3. SPI Flash
# -------------------------------------------------------------
elif menu == "⚡ SPI Flash 協定診斷":
    st.header("SPI / QSPI Flash 協定解析與寫入異常診斷")
    uploaded_spi = st.file_uploader("選擇 Saleae SPI CSV 檔案", type=["csv", "txt"])
    csv_text = None
    if uploaded_spi is not None:
        csv_text = uploaded_spi.getvalue().decode("utf-8")
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

# -------------------------------------------------------------
# 4. Register Decoder & Bit-Flipper
# -------------------------------------------------------------
elif menu == "🎛 晶片暫存器 Bitfield 解碼器":
    st.header("硬體 / 晶片暫存器 Bitfield 視覺化解碼器")
    builtin_map = {
        "PMBus 標準狀態暫存器 (PMBus STATUS_WORD)": "pmbus_standard.yaml",
        "PCIe AER Uncorrectable Error 暫存器": "pcie_aer_registers.yaml"
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
            raw_val_str = st.text_input("輸入暫存器 Raw Hex (如 0x8400, 0x00040000)", value="0x8400")
        try:
            cur_val = int(raw_val_str, 0)
        except ValueError:
            cur_val = 0
        res = catalog.decode_register(sel_reg, cur_val)
        st.subheader(f"{res.reg_name} (0x{cur_val:08X})")
        st.table(pd.DataFrame([{"Bit Range": f.bit_range, "Field": f.name, "Value": f.hex_val, "Meaning": f"⚠ {f.meaning}" if f.is_warning else f.meaning} for f in res.fields]))

# -------------------------------------------------------------
# 5. C Code Generator
# -------------------------------------------------------------
elif menu == "🛠 C 語言 Register 巨集產生器":
    st.header("YAML 暫存器定義檔 -> C 語言 Header (#define / RMW 巨集) 自動生成")
    data_dir = Path(__file__).parent.parent / "data"
    builtin_yamls = list(data_dir.glob("*.yaml"))
    choice_yaml = st.selectbox("選擇 YAML 範本", [y.name for y in builtin_yamls])
    gen = CHeaderGenerator.from_yaml_file(data_dir / choice_yaml)
    mod_name = st.text_input("模組名稱 (Module Name)", value=choice_yaml.replace(".yaml", "").upper())
    c_header = gen.generate_header(module_name=mod_name)
    st.code(c_header, language="c")
    st.download_button(f"下載 {mod_name.lower()}.h", c_header, file_name=f"{mod_name.lower()}.h")

# -------------------------------------------------------------
# 6. Junior FW Fault Lab
# -------------------------------------------------------------
elif menu == "🧪 Junior FW 故障模擬實驗室 (Fault Lab)":
    st.header("Junior Firmware 工程師硬韌體故障模擬演練場")
    st.write("點選任一常見硬體故障案例，模擬並檢驗排查邏輯：")
    scenario = st.selectbox(
        "選擇演練案例",
        [
            "Case 1: I2C Address NACK (Slave 未上電 / 位址錯誤)",
            "Case 2: I2C Clock Stretching 逾時 (> 25ms Bus Hang)",
            "Case 3: I2C EEPROM Page Boundary 寫入覆蓋風險",
            "Case 4: PCIe AER Completion Timeout 嚴重錯誤",
            "Case 5: SPI NOR Flash 寫入無效 (未發送 0x06 WREN)"
        ]
    )
    if "Case 1" in scenario:
        st.info("【情境說明】韌體向 0x50 發出讀取指令，但硬體完全無 ACK (Address NACK)。")
        st.code("START -> 0x50 (Write) -> NACK -> STOP", language="text")
        st.markdown("**【排查 SOP】**\n1. 量測 Slave 供電電壓 (VCC/3.3V) 是否正常。\n2. 檢查晶片硬體 Address 引腳 (A0, A1, A2) 是否浮接。\n3. 檢查 I2C 7-bit 位址與 8-bit R/W 位址是否搞混。")
    elif "Case 2" in scenario:
        st.info("【情境說明】Slave MCU 在傳輸中拉低 SCL 超過 25ms，造成 Bus Hang。")
        st.markdown("**【排查 SOP】**\n1. 檢查 Slave MCU 是否死鎖在中斷 (ISR) 或進入 HardFault。\n2. Master 韌體需啟動 SMBus Timeout 超時計時器並執行 SCL 9-Clock Reset。")
    elif "Case 3" in scenario:
        st.info("【情境說明】向 24C64 (32-byte page) 從 offset 0x18 連續寫入 16 bytes，跨越 0x20 邊界。")
        st.markdown("**【排查 SOP】**\n1. EEPROM 位址指針發生 Page Rollover，覆蓋了 0x00~0x07 的資料！\n2. 韌體需以 Page Size 為單位進行 Chunk 寫入分段。")
    elif "Case 4" in scenario:
        st.info("【情境說明】PCIe Host 發出 Memory Read，目標設備超時未回傳 Completion。")
        st.markdown("**【排查 SOP】**\n1. 檢查目標設備內部 AXI / State Machine 是否卡死。\n2. 檢查 Device Control 2 中的 CTO Timeout 設定。")
    elif "Case 5" in scenario:
        st.info("【情境說明】向 SPI NOR Flash 發送 0x02 Page Program，但 Flash 內部數據完全沒變。")
        st.markdown("**【排查 SOP】**\n1. 每次 Page Program 前必須發送單獨的 0x06 WREN 封包。\n2. 檢查 Status Register 中的 WEL 位元是否為 1。")

# -------------------------------------------------------------
# 7. SOP & Guide
# -------------------------------------------------------------
elif menu == "📚 韌體除錯指南 & SOP":
    st.header("Junior Firmware 工程師硬韌體除錯指南與心智模型")
    st.markdown("""
### 🎯 核心原則：Layer 分層診斷心智模型

1. **L1 物理層 (PHY)**: 檢查上拉電阻 (Pull-up)、檢查 100MHz 差分時鐘、示波器 Eyes Diagram。
2. **L2 資料鏈結層 (Data Link)**: I2C ACK/NACK, Clock Stretching, PCIe DLP Error (`fw-diag i2c analyze`)。
3. **L3 傳輸/協定層 (Protocol)**: PMBus, PCIe AER, SPI Opcode (`fw-diag pcie analyze`, `fw-diag spi analyze`)。
4. **L7 應用/驅動層 (Application)**: Linux Kernel Driver, OpenBMC (`fw-diag reg decode`, `fw-diag gen c-header`)。
""")