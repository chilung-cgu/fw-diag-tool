import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog

st.set_page_config(page_title='FW Diagnostic Toolkit', page_icon='⚡', layout='wide')
st.title('⚡ Firmware Signal & Protocol Diagnostic Toolkit')
st.caption('Cross-platform Logic Analyzer & System Trace RCA Assistant for Junior Firmware Engineers')

menu = st.sidebar.radio('功能導覽', ['📊 I2C / PMBus 波形診斷', '🚀 PCIe Config & AER 診斷', '🎛 晶片暫存器 Bitfield 解碼器', '📚 韌體除錯指南 & SOP'])

if menu == '📊 I2C / PMBus 波形診斷':
    st.header('I2C / SMBus / PMBus 波形異常與協定分析')
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader('選擇或拖放 Saleae CSV / Trace 檔案', type=['csv', 'txt', 'log'])
    with col2:
        smbus_timeout = st.number_input('SMBus Clock Stretching Timeout (ms)', min_value=1.0, max_value=100.0, value=25.0, step=1.0)
        use_sample = st.button('載入內建測試波形')
    csv_content = None
    if uploaded_file is not None:
        csv_content = uploaded_file.getvalue().decode('utf-8')
    elif use_sample:
        sample_path = Path(__file__).parent.parent.parent.parent / 'tests' / 'data' / 'saleae_normal_pmbus_eeprom.csv'
        if sample_path.exists():
            csv_content = sample_path.read_text(encoding='utf-8')
            st.info('已載入內建範例 CSV！')
    if csv_content:
        engine = I2CDiagnosticEngine(smbus_timeout_ms=smbus_timeout)
        report = engine.analyze_csv_content(csv_content)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric('總傳輸次數', report.summary.total_transactions)
        kpi1.metric('異常事件數', report.summary.anomaly_count)
        kpi3.metric('Address NACK', report.summary.addr_nack_count)
        kpi4.metric('Data NACK', report.summary.data_nack_count)
        st.divider()
        tab1, tab2, tab3 = st.tabs(['🚨 異常診斷', '📜 交易列表', '📝 Markdown 報告'])
        with tab1:
            if not report.anomalies:
                st.success('🎉 未偵測到任何 I2C/SMBus 時序與通訊異常！')
            else:
                for idx, a in enumerate(report.anomalies, 1):
                    with st.expander(f'[{a.severity.value}] #{idx}: {a.anomaly_type.value} @ {a.timestamp_start:.6f}s', expanded=True):
                        st.markdown(f'**描述**: {a.description}')
                        st.markdown('**排查指引**: ' + a.recommendation)
        with tab2:
            tx_data = [{'Index': t.index, 'Time (s)': f'{t.start_time:.6f}', 'Address': f'0x{t.address:02X}', 'Op': t.operation.value, 'ACK': t.address_ack, 'Bytes': len(t.data_bytes), 'Data': ' '.join(f'{b:02X}' for b in t.data_bytes), 'Semantic': str(t.decoded_semantic) if t.decoded_semantic else ''} for t in report.transactions]
            st.dataframe(pd.DataFrame(tx_data), use_container_width=True)
        with tab3:
            md_out = I2CReporter.generate_markdown(report)
            st.code(md_out, language='markdown')
            st.download_button('下載 Markdown 報告', md_out, file_name='i2c_report.md')

elif menu == '🚀 PCIe Config & AER 診斷':
    st.header('PCIe 配置空間、Capability 鏈表與 AER 嚴重錯誤診斷')
    input_mode = st.radio('輸入方式', ['貼上 lspci -xxxx / Hex Dump', '貼上 Linux dmesg AER Error Log'])
    raw_input = st.text_area('輸入 Log 或 Dump 內容：', height=200)
    if st.button('執行 PCIe 分析') and raw_input.strip():
        if 'PCIe Bus Error:' in raw_input or ('AER:' in raw_input and '00:' not in raw_input):
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(f'Kernel dmesg AER 診斷結果 (共 {len(events)} 個事件)')
            for idx, ev in enumerate(events, 1):
                with st.expander(f'事件 #{idx}: {ev.bdf} - {ev.error_name} ({ev.severity})', expanded=True):
                    st.markdown(f'**原始日誌**: ')
                    st.markdown('**排查 SOP**: ' + ev.root_cause_guide)
        else:
            bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(raw_input)
            cfg = PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)
            c1, c2, c3 = st.columns(3)
            c1.metric('Vendor / Device ID', f'0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}')
            c2.metric('Header Type', cfg.header_type.name)
            c3.metric('Capabilities', len(cfg.standard_capabilities) + len(cfg.extended_capabilities))
            st.markdown(PCIeReporter.to_markdown(cfg))

elif menu == '🎛 晶片暫存器 Bitfield 解碼器':
    st.header('硬體 / 晶片暫存器 Bitfield 視覺化解碼器')
    builtin_map = {'PMBus 標準狀態暫存器 (PMBus STATUS_WORD)': 'pmbus_standard.yaml', 'PCIe AER Uncorrectable Error 暫存器': 'pcie_aer_registers.yaml'}
    choice = st.selectbox('選擇預設暫存器定義檔', list(builtin_map.keys()))
    data_dir = Path(__file__).parent.parent / 'data'
    yaml_file = data_dir / builtin_map[choice]
    catalog = RegisterMapCatalog()
    if yaml_file.exists():
        catalog.load_from_yaml(yaml_file.read_text(encoding='utf-8'))
    reg_names = list(catalog.name_map.keys())
    if reg_names:
        r1, r2 = st.columns(2)
        with r1:
            sel_reg = st.selectbox('選擇暫存器', [r.upper() for r in reg_names])
        with r2:
            raw_val = st.text_input('輸入暫存器 Raw Hex (如 0x8400)', value='0x8400')
        if st.button('解碼暫存器'):
            res = catalog.decode_register(sel_reg, int(raw_val, 0))
            st.subheader(f'{res.reg_name} ({res.hex_val})')
            st.table(pd.DataFrame([{'Bit Range': f.bit_range, 'Field': f.name, 'Value': f.hex_val, 'Meaning': f'⚠ {f.meaning}' if f.is_warning else f.meaning} for f in res.fields]))

elif menu == '📚 韌體除錯指南 & SOP':
    st.header('Junior Firmware 工程師硬韌體除錯 SOP')
    st.markdown('### 💡 I2C NACK 排查 SOP\n1. **Address NACK**: Slave 供電未開 / Address Pin 浮接 / 7-bit 位址未對齊。\n2. **Data NACK**: EEPROM 正在執行內部寫入 (tWR 5ms) / 暫存器 Offset 越界。\n3. **Clock Stretching 逾時**: Slave MCU 卡在中斷中超過 SMBus 25ms 限制。')
