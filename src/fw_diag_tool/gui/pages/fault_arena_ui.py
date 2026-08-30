from __future__ import annotations

import streamlit as st

from fw_diag_tool.fault_arena.fixtures import FaultArenaFixtures
from fw_diag_tool.gui.shared import (
    _FAULT_ARENA_CASES_ZH,
    render_guide_expander,
)
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def render() -> None:
    st.header("初階韌體工程師 20 大經典硬韌體故障演練場（Fault Arena）")
    render_guide_expander(
        "chapters/ch10_fault_arena.md", "📖 點擊展開：故障演練場實戰除錯手冊（Fault Arena）"
    )
    arena_cases = [case["label"] for case in _FAULT_ARENA_CASES_ZH]
    sel_case = st.selectbox("選擇實戰演練案例", arena_cases)
    st.info(f"【案例分析】{sel_case}")
    st.caption(
        "案例資料是可重現的合成教學資料（synthetic training artifact），用來練習觀察、"
        "假設與驗證步驟；不代表真實公司 capture（擷取資料），也不保證單一根因。"
    )
    case_detail = next(case for case in _FAULT_ARENA_CASES_ZH if case["label"] == sel_case)
    fixture = FaultArenaFixtures.get_case(case_detail["case_id"])
    case_idx = int(fixture.case_id)
    if st.button("🚀 載入此案例模擬資料並自動分析", key=f"run_arena_{case_idx}"):
        data_content = fixture.builder()
        with st.expander("📄 檢視案例合成測試資料", expanded=False):
            st.code(data_content, language="csv" if ".csv" in fixture.filename else "text")
        st.markdown("### 🔍 自動診斷分析結果（Automated Diagnostic Result）")
        arena_report_md: str | None = None
        if fixture.kind == "i2c":
            i2c_engine = (
                I2CDiagnosticEngine(eeprom_profile="24C02")
                if case_idx == 4
                else I2CDiagnosticEngine()
            )
            rep_i2c = i2c_engine.analyze_csv_content(data_content)
            arena_report_md = I2CReporter.generate_markdown(rep_i2c)
        elif fixture.kind == "spi":
            rep_spi = SPIDiagnosticEngine().analyze_csv_content(data_content)
            arena_report_md = SPIReporter.to_markdown(rep_spi)
        elif fixture.kind == "pcie":
            bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(data_content)
            cfg = PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)
            arena_report_md = PCIeReporter.to_markdown(cfg)
        elif fixture.kind == "uart":
            rep_uart = UARTCrashParser.parse_log_text(data_content)
            arena_report_md = UARTReporter.to_markdown(rep_uart)
        elif fixture.kind in {"server_mgmt", "mctp"}:
            rep_mctp = ServerMgmtParser.parse_text_dump(data_content)
            arena_report_md = ServerMgmtReporter.to_markdown(rep_mctp)
        if arena_report_md is not None:
            st.markdown(arena_report_md)
            st.download_button(
                "下載案例 Markdown 診斷報告",
                data=arena_report_md,
                file_name=f"fault_arena_case_{case_idx:02d}.md",
                mime="text/markdown",
                key=f"arena_download_report_{case_idx}",
            )
    st.markdown("**【標準排查流程（SOP）與根因診斷（Root Cause）】**：")
    st.markdown(
        f"**故障現象（Observed symptom）**：{case_detail['symptom']}\n\n"
        f"**練習假設（Hypothesis）**：{case_detail['hypothesis']}\n\n"
        f"**區分測試／排查關鍵字（Discriminating test）**：{case_detail['check']}"
    )


__all__ = ["render"]
