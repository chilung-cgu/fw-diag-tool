from __future__ import annotations

import time
from typing import Any

import streamlit as st

from fw_diag_tool.fuzz.fuzzer import FuzzingGenerator
from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser

PROTOCOLS = {
    "I2C 匯流排 CSV（I2C Decoded CSV）": "i2c",
    "SPI Flash 匯流排 CSV（SPI CSV）": "spi",
    "PCIe lspci 設定空間（PCIe lspci Output）": "pcie",
    "UART 崩潰日誌（UART Crash Log）": "uart",
    "原始十六進位傾印（Raw Hex Dump）": "hex_dump",
}

DEFAULT_COUNTS = {
    "i2c": 50,
    "spi": 40,
    "pcie": 0,
    "uart": 0,
    "hex_dump": 20,
}


def _generate_fuzz_data(proto_key: str, seed: int | None, count: int) -> str:
    """依指定協定與參數產生隨機畸形或邊界 Fuzz 測試資料。"""
    if proto_key == "i2c":
        return FuzzingGenerator.fuzz_i2c_csv(seed=seed, num_rows=count)
    if proto_key == "spi":
        return FuzzingGenerator.fuzz_spi_csv(seed=seed, num_rows=count)
    if proto_key == "pcie":
        return FuzzingGenerator.fuzz_pcie_lspci(seed=seed)
    if proto_key == "uart":
        return FuzzingGenerator.fuzz_uart_log(seed=seed)
    if proto_key == "hex_dump":
        return FuzzingGenerator.fuzz_hex_dump(seed=seed, num_lines=count)
    raise ValueError(f"不支援的協定類型：{proto_key}")


def _analyze_single_fuzz(proto_key: str, data: str) -> tuple[str, str, dict[str, Any]]:
    """執行單次 Fuzz 資料解析並分類結果為 success / handled_error / crash。"""
    if proto_key == "i2c":
        try:
            i2c_report = I2CDiagnosticEngine().analyze_csv_content(data)
            return (
                "success",
                f"成功解析 {i2c_report.total_transactions} 筆交易，發現 {len(i2c_report.anomalies)} 個異常事件。",
                {
                    "總交易數": i2c_report.total_transactions,
                    "異常事件數": len(i2c_report.anomalies),
                    "偵測裝置位址數": len(i2c_report.devices_detected),
                    "資料品質警告數": len(i2c_report.data_quality_issues),
                },
            )
        except (ValueError, KeyError, TypeError) as exc:
            return (
                "handled_error",
                f"輸入驗證攔截（Handled Error）：{exc}",
                {"錯誤類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )
        except Exception as exc:
            return (
                "crash",
                f"未預期崩潰（Unhandled Crash）：{exc}",
                {"崩潰類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )

    if proto_key == "spi":
        try:
            spi_report = SPIDiagnosticEngine().analyze_csv_content(data)
            return (
                "success",
                f"成功解析 {len(spi_report.transactions)} 筆交易，發現 {len(spi_report.anomalies)} 個異常事件。",
                {
                    "總交易數": len(spi_report.transactions),
                    "異常事件數": len(spi_report.anomalies),
                    "資料品質警告數": len(spi_report.data_quality_issues),
                },
            )
        except (ValueError, KeyError, TypeError) as exc:
            return (
                "handled_error",
                f"輸入驗證攔截（Handled Error）：{exc}",
                {"錯誤類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )
        except Exception as exc:
            return (
                "crash",
                f"未預期崩潰（Unhandled Crash）：{exc}",
                {"崩潰類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )

    if proto_key == "pcie":
        try:
            bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(data)
            cfg = PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)
            return (
                "success",
                f"成功解碼 PCIe 設定空間（Vendor ID: 0x{cfg.vendor_id:04X}, Device ID: 0x{cfg.device_id:04X}）。",
                {
                    "匯流排編號 (BDF)": cfg.bdf or "未指定",
                    "廠商 ID (Vendor ID)": f"0x{cfg.vendor_id:04X}",
                    "裝置 ID (Device ID)": f"0x{cfg.device_id:04X}",
                    "裝置類別 (Class Name)": cfg.class_name,
                    "標準能力 (Caps)": len(cfg.standard_capabilities),
                },
            )
        except (ValueError, TypeError) as exc:
            return (
                "handled_error",
                f"輸入驗證攔截（Handled Error）：{exc}",
                {"錯誤類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )
        except Exception as exc:
            return (
                "crash",
                f"未預期崩潰（Unhandled Crash）：{exc}",
                {"崩潰類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )

    if proto_key == "uart":
        try:
            uart_report = UARTCrashParser.parse_log_text(data)
            return (
                "success",
                f"成功解析 UART 日誌（類型：{uart_report.crash_type.name}，共 {uart_report.raw_log_lines} 行）。",
                {
                    "崩潰類型 (Crash Type)": uart_report.crash_type.name,
                    "摘要標題 (Summary Title)": uart_report.summary_title,
                    "原始日誌行數 (Lines)": uart_report.raw_log_lines,
                },
            )
        except (ValueError, TypeError) as exc:
            return (
                "handled_error",
                f"輸入驗證攔截（Handled Error）：{exc}",
                {"錯誤類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )
        except Exception as exc:
            return (
                "crash",
                f"未預期崩潰（Unhandled Crash）：{exc}",
                {"崩潰類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )

    if proto_key == "hex_dump":
        try:
            lines = [line.strip() for line in data.strip().splitlines() if line.strip()]
            total_bytes = 0
            byte_values: list[int] = []
            for line in lines:
                tokens = line.split()
                for tok in tokens:
                    val = int(tok, 16)
                    if not (0 <= val <= 255):
                        raise ValueError(f"數值超出 8-bit 位元組範圍 (0x00~0xFF)：{tok}")
                    byte_values.append(val)
                    total_bytes += 1
            non_zero = sum(1 for b in byte_values if b != 0)
            return (
                "success",
                f"成功解析 Hex Dump（共 {len(lines)} 行，{total_bytes} 位元組）。",
                {
                    "總行數 (Lines)": len(lines),
                    "總位元組數 (Total Bytes)": total_bytes,
                    "非零位元組數 (Non-zero Bytes)": non_zero,
                    "零值位元組數 (Zero Bytes)": total_bytes - non_zero,
                },
            )
        except (ValueError, TypeError) as exc:
            return (
                "handled_error",
                f"輸入驗證攔截（Handled Error）：{exc}",
                {"錯誤類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )
        except Exception as exc:
            return (
                "crash",
                f"未預期崩潰（Unhandled Crash）：{exc}",
                {"崩潰類型": type(exc).__name__, "錯誤訊息": str(exc)},
            )

    return "crash", "未知的協定類型", {}


def render() -> None:
    st.header("協定解析器 Fuzz 測試實驗室")

    with st.expander(
        "📖 點擊展開：什麼是 Fuzzing 與解析器穩健性（Robustness）測試？", expanded=False
    ):
        st.markdown(
            "### 1. 什麼是模糊測試（Fuzzing）？\n"
            "模糊測試（Fuzzing）是一種自動化的軟體測試技術，透過隨機產生大量非預期、極限邊界（Edge Cases）"
            "或格式畸形（Malformed）的輸入資料，持續衝擊目標解析器（Parser）與狀態機，以發掘潛在的崩潰漏洞與死鎖狀態。\n\n"
            "### 2. 為什麼韌體協定解析器需要 Robustness 測試？\n"
            "- **雜訊與不完整封包**：實體匯流排（I2C / SPI / UART）常面臨訊號干擾、電源抖動、電平浮接或意外斷電，"
            "擷取到的資料常包含截斷字元、非法十六進位值或長度不符的欄位。\n"
            "- **避免未捕捉例外（Unhandled Crashes）**：解析器若遇到異常資料時拋出未捕捉的例外"
            "（例如 IndexError、ZeroDivisionError、NoneType 屬性存取），可能直接導致整個診斷工具或 BMC 服務當機。\n"
            "- **三種結果判定標準**：\n"
            "  1. **解析成功（Parsed OK）**：資料符合結構，Parser 成功提取交易與狀態。\n"
            "  2. **防禦攔截（Handled Error）**：資料嚴重畸形，Parser 正確拋出已知驗證錯誤（如 ValueError）並優雅拒絕，符合預期。\n"
            "  3. **未預期崩潰（Unhandled Crash）**：Parser 發生未處理例外，代表存在需修復的 Robustness 漏洞。\n"
        )

    tab_single, tab_batch = st.tabs(
        [
            "🔬 單次 Fuzz 產生與即時分析",
            "⚡ 批次壓力測試與統計",
        ]
    )

    with tab_single:
        st.subheader("單次 Fuzz 測試資料產生與診斷")

        col_proto, col_seed = st.columns([2, 2])
        with col_proto:
            sel_label = st.selectbox(
                "選擇測試協定（Target Protocol）",
                list(PROTOCOLS.keys()),
                key="fuzz_proto_select",
            )
            proto_key = PROTOCOLS[sel_label]

        with col_seed:
            use_fixed_seed = st.checkbox(
                "指定隨機種子（Deterministic Seed）", value=False, key="fuzz_use_seed"
            )
            if use_fixed_seed:
                seed_val: int | None = st.number_input(
                    "Seed 數值（整數）",
                    min_value=0,
                    max_value=2147483647,
                    value=42,
                    step=1,
                    key="fuzz_seed_input",
                )
            else:
                seed_val = None
                st.caption("目前為隨機模式（每次產生均不同）。")

        if proto_key in {"i2c", "spi", "hex_dump"}:
            default_cnt = DEFAULT_COUNTS[proto_key]
            label_cnt = (
                "資料列數（Row Count）" if proto_key != "hex_dump" else "資料行數（Line Count）"
            )
            row_count = st.slider(
                label_cnt,
                min_value=5,
                max_value=200,
                value=default_cnt,
                step=5,
                key="fuzz_count_slider",
            )
        else:
            row_count = 0
            if proto_key == "pcie":
                st.caption("PCIe 模式固定產生 256-byte lspci 設定空間傾印結構。")
            elif proto_key == "uart":
                st.caption("UART 模式隨機產生 Linux Kernel Panic 或 ARM HardFault 格式之日誌。")

        if st.button("🎲 產生 Fuzz 測試資料", type="primary", key="fuzz_btn_generate"):
            generated_data = _generate_fuzz_data(proto_key, seed_val, row_count)
            st.session_state["fuzz_current_data"] = generated_data
            st.session_state["fuzz_current_proto"] = proto_key
            st.session_state["fuzz_current_seed"] = seed_val

        current_data = st.session_state.get("fuzz_current_data")
        current_proto = st.session_state.get("fuzz_current_proto")

        if current_data is not None and current_proto == proto_key:
            st.markdown("#### 產生的 Fuzz 資料內容")
            lang_code = "csv" if proto_key in {"i2c", "spi"} else "text"
            st.code(current_data, language=lang_code)

            ext_map = {"i2c": "csv", "spi": "csv", "pcie": "txt", "uart": "log", "hex_dump": "txt"}
            file_ext = ext_map.get(proto_key, "txt")
            st.download_button(
                "💾 下載此 Fuzz 測試資料",
                data=current_data,
                file_name=f"fuzz_{proto_key}_{st.session_state.get('fuzz_current_seed') or 'random'}.{file_ext}",
                mime="text/plain",
                key="fuzz_btn_download",
            )

            st.markdown("---")
            st.markdown("#### 🔍 即時解析分析結果（Live Analysis Result）")

            status, msg, details = _analyze_single_fuzz(proto_key, current_data)

            if status == "success":
                st.success(f"✅ 【解析成功 (Parsed OK)】{msg}")
            elif status == "handled_error":
                st.warning(f"🛡️ 【輸入驗證攔截 (Handled Error)】{msg}")
            else:
                st.error(f"🚨 【未預期崩潰 (Unhandled Crash)】{msg}")

            if details:
                st.markdown("**詳細解析指標／欄位摘要：**")
                cols = st.columns(len(details))
                for col, (k, v) in zip(cols, details.items()):
                    col.metric(k, str(v))

    with tab_batch:
        st.subheader("批次 Fuzz 壓力測試與穩健性統計")
        st.markdown(
            "執行多輪 Fuzz 測試，針對不同隨機種子持續衝擊解析器，統計成功解析率、"
            "輸入防禦攔截率與未預期崩潰率。"
        )

        batch_col1, batch_col2, batch_col3 = st.columns(3)
        with batch_col1:
            batch_proto_label = st.selectbox(
                "測試目標協定",
                ["全部協定混合測試（All Protocols）"] + list(PROTOCOLS.keys()),
                key="batch_fuzz_proto",
            )
        with batch_col2:
            batch_iterations = st.selectbox(
                "執行次數（Iterations）",
                [10, 20, 50, 100, 200],
                index=2,
                key="batch_fuzz_iterations",
            )
        with batch_col3:
            batch_start_seed = st.number_input(
                "起始隨機種子（Base Seed）",
                min_value=0,
                max_value=2147483647,
                value=0,
                step=1,
                key="batch_fuzz_base_seed",
            )

        if st.button("🚀 啟動批次 Fuzz 壓力測試", type="primary", key="btn_run_batch"):
            target_protos = (
                list(PROTOCOLS.values())
                if batch_proto_label == "全部協定混合測試（All Protocols）"
                else [PROTOCOLS[batch_proto_label]]
            )

            total_runs = len(target_protos) * batch_iterations
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            results_log: list[dict[str, Any]] = []
            success_count = 0
            handled_count = 0
            crash_count = 0

            start_time = time.perf_counter()
            current_run = 0

            for p_key in target_protos:
                for idx in range(batch_iterations):
                    seed = int(batch_start_seed) + idx
                    cnt = DEFAULT_COUNTS[p_key]
                    fuzz_input = _generate_fuzz_data(p_key, seed, cnt)
                    res_status, res_msg, _ = _analyze_single_fuzz(p_key, fuzz_input)

                    if res_status == "success":
                        success_count += 1
                    elif res_status == "handled_error":
                        handled_count += 1
                    else:
                        crash_count += 1

                    results_log.append(
                        {
                            "測試編號": current_run + 1,
                            "協定": p_key.upper(),
                            "種子 (Seed)": seed,
                            "結果狀態": "✅ 成功"
                            if res_status == "success"
                            else ("🛡️ 攔截" if res_status == "handled_error" else "🚨 崩潰"),
                            "詳細摘要": res_msg,
                        }
                    )

                    current_run += 1
                    progress_bar.progress(current_run / total_runs)
                    status_text.text(
                        f"正在執行第 {current_run}/{total_runs} 次 Fuzz 測試（{p_key.upper()} seed={seed}）…"
                    )

            elapsed_s = time.perf_counter() - start_time
            progress_bar.progress(1.0)
            status_text.empty()

            st.markdown("### 📊 批次測試統計成果")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("總測試次數 (Total Runs)", f"{total_runs} 次")
            success_pct = (success_count / total_runs) * 100
            m2.metric("解析成功率 (Parsed OK)", f"{success_count} ({success_pct:.1f}%)")
            handled_pct = (handled_count / total_runs) * 100
            m3.metric("輸入驗證攔截 (Handled)", f"{handled_count} ({handled_pct:.1f}%)")
            crash_pct = (crash_count / total_runs) * 100
            m4.metric(
                "未預期崩潰 (Unhandled)",
                f"{crash_count} ({crash_pct:.1f}%)",
                delta=None if crash_count == 0 else f"+{crash_count} 異常",
                delta_color="inverse",
            )

            st.caption(
                f"總耗時：{elapsed_s:.3f} 秒（平均每筆測試 {elapsed_s / total_runs * 1000:.2f} ms）。"
            )

            if crash_count == 0:
                st.success(
                    "🎉 **解析器穩健性表現優異！** "
                    f"在 {total_runs} 次壓力測試中，Parser 未發生任何未預期的崩潰或 unhandled exceptions。"
                )
            else:
                st.error(
                    f"⚠️ **檢測到 {crash_count} 次未預期崩潰！** "
                    "請於下方紀錄清單中檢查發生崩潰之特定 Seed 與輸入格式，並補強解析器邊界防禦。"
                )

            with st.expander(
                f"📋 檢視完整 {total_runs} 筆測試歷程紀錄", expanded=(crash_count > 0)
            ):
                st.dataframe(results_log)

    render_page_footer()


__all__ = ["render"]
