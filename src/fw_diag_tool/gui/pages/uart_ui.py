from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.notifications import show_error_toast, show_success_toast
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    render_guide_expander,
    render_page_footer,
    render_session_controls,
)
from fw_diag_tool.gui.uploads import (
    MAX_TEXT_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)
from fw_diag_tool.resources import load_uart_sample
from fw_diag_tool.uart.diff import UARTDiffEngine
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def render() -> None:
    st.header("UART 序列埠崩潰轉儲與 ARM Cortex-M HardFault 智慧診斷")
    render_guide_expander(
        "chapters/ch04_uart_crash.md", "📖 點擊展開：UART 崩潰與 ARM HardFault 診斷教學"
    )
    with st.expander("⚖️ UART Crash Before/After 對比", expanded=False):
        st.markdown(
            "比對修復前後或兩次不同測試的 UART 崩潰日誌，確認 Crash 類型轉移、Fault Address 偏移與 Call Trace 符號變化。"
        )
        diff_col1, diff_col2 = st.columns(2)
        with diff_col1:
            uploaded_u_base = st.file_uploader(
                "選擇 Baseline（修復前）UART 日誌",
                type=["txt", "log"],
                key="uart_diff_baseline_uploader",
            )
        with diff_col2:
            uploaded_u_cand = st.file_uploader(
                "選擇 Candidate（修復後）UART 日誌",
                type=["txt", "log"],
                key="uart_diff_candidate_uploader",
            )

        if uploaded_u_base is not None and uploaded_u_cand is not None:
            try:
                base_log = decode_uploaded_text(
                    uploaded_u_base, allowed_extensions={".txt", ".log"}
                )
                cand_log = decode_uploaded_text(
                    uploaded_u_cand, allowed_extensions={".txt", ".log"}
                )
                base_rep = UARTCrashParser.parse_log_text(base_log)
                cand_rep = UARTCrashParser.parse_log_text(cand_log)
                diff_res = UARTDiffEngine.compare(base_rep, cand_rep)

                if diff_res.is_identical:
                    st.success(f"✔ {diff_res.summary}")
                elif diff_res.crash_type_changed or diff_res.fault_address_changed:
                    st.warning(f"⚠ {diff_res.summary}")
                else:
                    st.info(f"ℹ️ {diff_res.summary}")

                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "崩潰類型變化",
                    "變更" if diff_res.crash_type_changed else "相同",
                    delta=None,
                )
                m2.metric(
                    "故障位址變化",
                    "變更" if diff_res.fault_address_changed else "相同",
                    delta=None,
                )
                m3.metric(
                    "Call Trace 符號增減",
                    f"+{len(diff_res.new_symbols)} / -{len(diff_res.resolved_symbols)}",
                )

                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    st.markdown(f"**Baseline Crash Type**: `{diff_res.baseline_crash_type}`")
                    st.markdown(
                        f"**Baseline Fault Address**: `{diff_res.baseline_fault_address or 'N/A'}`"
                    )
                with t_col2:
                    st.markdown(f"**Candidate Crash Type**: `{diff_res.candidate_crash_type}`")
                    st.markdown(
                        f"**Candidate Fault Address**: `{diff_res.candidate_fault_address or 'N/A'}`"
                    )

                if diff_res.new_symbols:
                    st.warning(
                        "🆕 **Candidate 新增之呼叫棧符號（New Symbols）**：\n"
                        + "\n".join(f"- `{s}`" for s in diff_res.new_symbols)
                    )
                if diff_res.resolved_symbols:
                    st.success(
                        "🎉 **已消除之呼叫棧符號（Resolved Symbols）**：\n"
                        + "\n".join(f"- `{s}`" for s in diff_res.resolved_symbols)
                    )

            except (TypeError, ValueError) as exc:
                st.error(f"UART 對比分析失敗：{_localize_gui_error(exc, domain='uart')}")
                show_error_toast("UART 對比分析失敗")

    u_mode = st.radio(
        "選擇輸入方式",
        [
            "貼上 UART 日誌（UART Log）／崩潰轉儲（Crash Dump）",
            "載入範例：Linux 核心 Panic 日誌（Kernel Panic Log）",
            "載入範例：ARM Cortex-M HardFault 日誌（HardFault Log）",
        ],
    )
    u_raw = ""
    u_example_name: str | None = None
    if u_mode == "貼上 UART 日誌（UART Log）／崩潰轉儲（Crash Dump）":
        u_col1, u_col2 = st.columns([3, 1])
        with u_col1:
            uploaded_uart = st.file_uploader("上傳 UART 日誌檔案", type=["txt", "log"])
        with u_col2:
            if st.button("📋 載入範例資料", key="uart_load_sample_btn"):
                st.session_state["uart_pasted_text"] = load_uart_sample("kernel-panic")
                st.rerun()
        default_uart_text = st.session_state.get("uart_pasted_text", "")
        pasted_uart = st.text_area(
            "請貼上 UART 日誌（UART Log）或崩潰轉儲（Crash Dump）：",
            value=default_uart_text,
            height=200,
            max_chars=MAX_TEXT_BYTES,
        )
        if uploaded_uart is not None:
            try:
                u_raw = decode_uploaded_text(uploaded_uart, allowed_extensions={".txt", ".log"})
            except ValueError as exc:
                st.error(f"UART 檔案讀取錯誤：{exc}")
        else:
            u_raw = pasted_uart
    elif u_mode == "載入範例：Linux 核心 Panic 日誌（Kernel Panic Log）":
        u_example_name = "uart_kernel_panic_minimal.log"
        u_raw = load_uart_sample("kernel-panic")
    else:
        u_example_name = "uart_hardfault_minimal.log"
        u_raw = load_uart_sample("hardfault")
    if u_example_name is not None:
        st.download_button(
            f"下載此 UART 範例（{u_example_name}）",
            data=u_raw,
            file_name=u_example_name,
            mime="text/plain",
            key="uart_download_example",
        )
    if st.button("執行 UART 崩潰轉儲分析（Crash Dump）") and u_raw.strip():
        try:
            u_report = UARTCrashParser.parse_log_text(
                validate_pasted_text(u_raw, label="UART 日誌（UART Log）")
            )
        except (TypeError, ValueError) as exc:
            st.error(f"UART 輸入錯誤：{_localize_gui_error(exc, domain='uart')}")
            show_error_toast("UART 分析失敗")
        else:
            st.caption(
                "證據範圍：報告只整理輸入日誌中可解析的故障欄位（fault fields）；請使用相同建置版本的 "
                "ELF（matching ELF）、符號（symbol）、核心原始碼（kernel source），並在目標板重現"
                "以確認根因（root cause）。"
            )
            show_success_toast("UART 分析完成")
            uart_md = UARTReporter.to_markdown(u_report)
            st.markdown(uart_md)
            st.download_button(
                "下載 UART Markdown 診斷報告",
                data=uart_md,
                file_name="uart_crash_report.md",
                mime="text/markdown",
                key="uart_download_report",
            )
            render_session_controls(
                protocol="UART",
                report_data=u_report.to_dict(),
                config_data={"mode": u_mode},
            )
    else:
        render_session_controls(
            protocol="UART",
            report_data=None,
            config_data={"mode": u_mode},
        )

    render_page_footer()


__all__ = ["render"]
