"""韌體訊號與協定診斷套件 — 跨協定時間線關聯分析頁面。

提供多協定（I2C、SPI、UART、PCIe、MCTP）時間線對齊視覺化，自動偵測跨協定
異常叢集（cross-protocol anomaly clusters），幫助工程師定位系統級
連鎖故障的根因（root-cause）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    _localize_mctp_error,
    _localize_pcie_input_error,
    analyze_i2c_input,
    analyze_mctp_input,
    analyze_pcie_input,
    analyze_spi_input,
    render_guide_expander,
    render_page_footer,
    render_session_controls,
)
from fw_diag_tool.resources import (
    load_i2c_sample,
    load_mctp_sample,
    load_pcie_sample,
    load_spi_sample,
    load_uart_sample,
)
from fw_diag_tool.uart.parser import parse_uart_log

# ---------------------------------------------------------------------------
# Core analysis helpers
# ---------------------------------------------------------------------------


def build_timeline_events(
    *,
    i2c_report: Any | None = None,
    spi_report: Any | None = None,
    uart_report: Any | None = None,
    pcie_report: Any | None = None,
    mctp_report: Any | None = None,
) -> list[dict[str, Any]]:
    """Extract timestamped events from one or more protocol reports.

    Each returned dict contains:
      - protocol: str  ("I2C" | "SPI" | "UART" | "PCIe" | "MCTP")
      - timestamp: float  (seconds)
      - label: str  (human-readable event description)
      - anomaly: bool  (True if the event represents an issue/error)
    """
    events: list[dict[str, Any]] = []

    # --- I2C events ---
    if i2c_report is not None:
        transactions = getattr(i2c_report, "transactions", None) or []
        for txn in transactions:
            ts = getattr(txn, "start_time", None)
            if ts is None:
                continue
            addr = getattr(txn, "address_7bit", None)
            label = f"I2C Txn 0x{addr:02X}" if addr is not None else "I2C Txn"
            events.append(
                {
                    "protocol": "I2C",
                    "timestamp": float(ts),
                    "label": label,
                    "anomaly": False,
                }
            )

        issues = getattr(i2c_report, "issues", None) or []
        for issue in issues:
            ts = getattr(issue, "timestamp", None)
            if ts is None:
                continue
            events.append(
                {
                    "protocol": "I2C",
                    "timestamp": float(ts),
                    "label": getattr(issue, "title", "I2C Issue"),
                    "anomaly": True,
                }
            )

    # --- SPI events ---
    if spi_report is not None:
        transactions = (
            getattr(spi_report, "transactions", None)
            or getattr(spi_report, "operations", None)
            or []
        )
        for op in transactions:
            ts = getattr(op, "start_time", None) or getattr(op, "timestamp", None)
            if ts is None:
                continue
            opcode_name = getattr(op, "opcode_name", None)
            opcode = getattr(op, "opcode", None)
            label = opcode_name or (f"SPI {opcode}" if opcode is not None else "SPI Op")
            events.append(
                {
                    "protocol": "SPI",
                    "timestamp": float(ts),
                    "label": label,
                    "anomaly": False,
                }
            )

        spi_issues = getattr(spi_report, "issues", None) or []
        for issue in spi_issues:
            ts = getattr(issue, "timestamp", None)
            if ts is None:
                continue
            events.append(
                {
                    "protocol": "SPI",
                    "timestamp": float(ts),
                    "label": getattr(issue, "title", "SPI Issue"),
                    "anomaly": True,
                }
            )

    # --- UART events ---
    if uart_report is not None:
        ts_base = 0.0
        crash_type_val = getattr(getattr(uart_report, "crash_type", None), "value", None)
        if crash_type_val:
            events.append(
                {
                    "protocol": "UART",
                    "timestamp": ts_base,
                    "label": getattr(uart_report, "summary_title", "UART Crash"),
                    "anomaly": True,
                }
            )

    # --- PCIe events ---
    if pcie_report is not None:
        pcie_items: list[Any] = pcie_report if isinstance(pcie_report, list) else [pcie_report]
        for item in pcie_items:
            if isinstance(item, dict):
                if item.get("protocol") == "PCIe":
                    events.append(
                        {
                            "protocol": "PCIe",
                            "timestamp": float(item.get("timestamp", 0.0)),
                            "label": str(item.get("label", "PCIe Event")),
                            "anomaly": bool(item.get("anomaly", False)),
                        }
                    )
                else:
                    ts = float(item.get("timestamp", 0.0))
                    label = str(
                        item.get("label") or item.get("title") or item.get("name") or "PCIe Event"
                    )
                    anomaly = bool(item.get("anomaly", False) or item.get("is_degraded", False))
                    events.append(
                        {
                            "protocol": "PCIe",
                            "timestamp": ts,
                            "label": label,
                            "anomaly": anomaly,
                        }
                    )
            elif hasattr(item, "error_name"):  # DmesgAEREvent
                raw_ts = getattr(item, "timestamp", None)
                ts = 0.0
                if raw_ts is not None:
                    try:
                        ts = float(raw_ts)
                    except (ValueError, TypeError):
                        ts = 0.0
                bdf = getattr(item, "bdf", None)
                sev = getattr(item, "severity", "AER")
                err_name = getattr(item, "error_name", "Error")
                bdf_str = f" ({bdf})" if bdf else ""
                label = f"PCIe AER {sev}{bdf_str}: {err_name}"
                events.append(
                    {
                        "protocol": "PCIe",
                        "timestamp": ts,
                        "label": label,
                        "anomaly": True,
                    }
                )
            else:  # PCIeConfigSpace or similar
                bdf = getattr(item, "bdf", None) or "00:00.0"
                vid = getattr(item, "vendor_id", 0)
                did = getattr(item, "device_id", 0)
                ts_raw = getattr(item, "timestamp", 0.0)
                ts = float(ts_raw) if ts_raw is not None else 0.0

                events.append(
                    {
                        "protocol": "PCIe",
                        "timestamp": ts,
                        "label": f"PCIe Dev {bdf} (0x{vid:04X}:0x{did:04X})",
                        "anomaly": False,
                    }
                )

                link_info = getattr(item, "link_info", None)
                if link_info and getattr(link_info, "is_degraded", False):
                    speed = getattr(link_info, "current_speed_str", "Unknown")
                    width = getattr(link_info, "current_width", 0)
                    events.append(
                        {
                            "protocol": "PCIe",
                            "timestamp": ts,
                            "label": f"PCIe Link Degraded ({bdf}): {speed} x{width}",
                            "anomaly": True,
                        }
                    )

                aer = getattr(item, "aer_analysis", None)
                if aer:
                    for uncorr in getattr(aer, "uncorr_errors", []):
                        if getattr(uncorr, "is_active", False) and not getattr(
                            uncorr, "is_masked", False
                        ):
                            name = getattr(uncorr, "name", "Uncorr Error")
                            events.append(
                                {
                                    "protocol": "PCIe",
                                    "timestamp": ts,
                                    "label": f"PCIe AER Uncorr ({bdf}): {name}",
                                    "anomaly": True,
                                }
                            )
                    for corr in getattr(aer, "corr_errors", []):
                        if getattr(corr, "is_active", False) and not getattr(
                            corr, "is_masked", False
                        ):
                            name = getattr(corr, "name", "Corr Error")
                            events.append(
                                {
                                    "protocol": "PCIe",
                                    "timestamp": ts,
                                    "label": f"PCIe AER Corr ({bdf}): {name}",
                                    "anomaly": True,
                                }
                            )

                for q_issue in getattr(item, "data_quality_issues", []):
                    events.append(
                        {
                            "protocol": "PCIe",
                            "timestamp": ts,
                            "label": f"PCIe Data Issue ({bdf}): {q_issue}",
                            "anomaly": True,
                        }
                    )

    # --- MCTP events ---
    if mctp_report is not None:
        if isinstance(mctp_report, list):
            for item in mctp_report:
                if isinstance(item, dict):
                    events.append(
                        {
                            "protocol": "MCTP",
                            "timestamp": float(item.get("timestamp", 0.0)),
                            "label": str(item.get("label") or item.get("summary") or "MCTP Event"),
                            "anomaly": bool(item.get("anomaly", False)),
                        }
                    )
                elif hasattr(item, "dest_eid"):  # MCTPPacket
                    ts = float(getattr(item, "timestamp", 0.0) or 0.0)
                    events.append(
                        {
                            "protocol": "MCTP",
                            "timestamp": ts,
                            "label": getattr(item, "summary", "MCTP Packet"),
                            "anomaly": False,
                        }
                    )
                elif hasattr(item, "rs_addr"):  # IPMBFrame
                    ts = float(getattr(item, "timestamp", 0.0) or 0.0)
                    chk1 = getattr(item, "checksum1_valid", True)
                    chk2 = getattr(item, "checksum2_valid", True)
                    events.append(
                        {
                            "protocol": "MCTP",
                            "timestamp": ts,
                            "label": getattr(item, "summary", "IPMB Frame"),
                            "anomaly": not (chk1 and chk2),
                        }
                    )
        else:
            messages = getattr(mctp_report, "mctp_messages", None) or []
            packets = getattr(mctp_report, "mctp_packets", None) or []
            ipmb_frames = getattr(mctp_report, "ipmb_frames", None) or []
            source_errors = (
                getattr(mctp_report, "source_errors", None)
                or getattr(mctp_report, "errors", None)
                or []
            )

            if messages:
                for msg in messages:
                    raw_ts = getattr(msg, "timestamp", 0.0)
                    ts = float(raw_ts) if raw_ts is not None else 0.0
                    err = getattr(msg, "error", None)
                    is_complete = getattr(msg, "is_complete", True)
                    has_err = bool(err) or not is_complete
                    summary = (
                        getattr(msg, "summary", None)
                        or getattr(msg, "pldm_command", None)
                        or f"MCTP Msg (Tag {getattr(msg, 'msg_tag', 0)})"
                    )
                    label = f"MCTP Error: {err}" if err else summary
                    events.append(
                        {
                            "protocol": "MCTP",
                            "timestamp": ts,
                            "label": label,
                            "anomaly": has_err,
                        }
                    )
            elif packets:
                for pkt in packets:
                    raw_ts = getattr(pkt, "timestamp", 0.0)
                    ts = float(raw_ts) if raw_ts is not None else 0.0
                    summary = (
                        getattr(pkt, "summary", None)
                        or getattr(pkt, "pldm_command", None)
                        or f"MCTP Pkt (Tag {getattr(pkt, 'msg_tag', 0)})"
                    )
                    events.append(
                        {
                            "protocol": "MCTP",
                            "timestamp": ts,
                            "label": summary,
                            "anomaly": False,
                        }
                    )

            for frame in ipmb_frames:
                raw_ts = getattr(frame, "timestamp", 0.0)
                ts = float(raw_ts) if raw_ts is not None else 0.0
                chk1 = getattr(frame, "checksum1_valid", True)
                chk2 = getattr(frame, "checksum2_valid", True)
                has_err = not (chk1 and chk2)
                summary = (
                    getattr(frame, "summary", None)
                    or f"IPMB {getattr(frame, 'netfn_name', '')} {getattr(frame, 'cmd_name', '')}"
                )
                label = f"IPMB Checksum Error: {summary}" if has_err else summary
                events.append(
                    {
                        "protocol": "MCTP",
                        "timestamp": ts,
                        "label": label,
                        "anomaly": has_err,
                    }
                )

            for err in source_errors:
                events.append(
                    {
                        "protocol": "MCTP",
                        "timestamp": 0.0,
                        "label": f"MCTP Error: {err}",
                        "anomaly": True,
                    }
                )

    # Sort by timestamp
    events.sort(key=lambda e: e["timestamp"])
    return events


def detect_cross_protocol_clusters(
    events: list[dict[str, Any]],
    window_s: float = 0.002,
) -> list[dict[str, Any]]:
    """Detect clusters of anomaly events spanning multiple protocols within a time window.

    Returns a list of dicts, each with:
      - protocols: list[str]  (sorted unique protocol names in the cluster)
      - summary: str  (human-readable description of the cluster)
    """
    anomalies = [e for e in events if e.get("anomaly")]
    if not anomalies:
        return []

    anomalies.sort(key=lambda e: e["timestamp"])

    clusters: list[dict[str, Any]] = []
    i = 0
    while i < len(anomalies):
        cluster_events = [anomalies[i]]
        j = i + 1
        while j < len(anomalies):
            if any(
                abs(anomalies[j]["timestamp"] - ce["timestamp"]) <= window_s
                for ce in cluster_events
            ):
                cluster_events.append(anomalies[j])
                j += 1
            else:
                break

        protocols = sorted({e["protocol"] for e in cluster_events})
        if len(protocols) >= 2:
            labels = [e["label"] for e in cluster_events]
            summary = " + ".join(labels)
            clusters.append(
                {
                    "protocols": protocols,
                    "summary": summary,
                }
            )

        i = max(i + 1, j)

    return clusters


# ---------------------------------------------------------------------------
# Plotly timeline chart
# ---------------------------------------------------------------------------

_PROTOCOL_COLORS: dict[str, str] = {
    "I2C": "#0ea5e9",
    "SPI": "#a855f7",
    "UART": "#f97316",
    "PCIe": "#10b981",
    "MCTP": "#eab308",
}

_PROTOCOL_Y: dict[str, int] = {
    "MCTP": 1,
    "PCIe": 2,
    "UART": 3,
    "SPI": 4,
    "I2C": 5,
}


def _build_timeline_chart(events: list[dict[str, Any]]) -> go.Figure:
    """Build a Plotly scatter chart showing multi-protocol timeline events."""
    fig = go.Figure()

    for proto in ("I2C", "SPI", "UART", "PCIe", "MCTP"):
        proto_events = [e for e in events if e.get("protocol") == proto]
        if not proto_events:
            continue

        xs = [e["timestamp"] * 1000 for e in proto_events]
        ys = [_PROTOCOL_Y.get(proto, 1)] * len(proto_events)
        texts = [e["label"] for e in proto_events]
        markers = ["star" if e.get("anomaly") else "circle" for e in proto_events]
        sizes = [14 if e.get("anomaly") else 8 for e in proto_events]
        colors = [
            "#ef4444" if e.get("anomaly") else _PROTOCOL_COLORS.get(proto, "#64748b")
            for e in proto_events
        ]

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers+text",
                name=proto,
                text=texts,
                textposition="top center",
                textfont=dict(size=9, color="#94a3b8"),
                marker=dict(
                    symbol=markers,
                    size=sizes,
                    color=colors,
                    line=dict(width=1, color="#334155"),
                ),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Time: %{x:.3f} ms<br>"
                    "Protocol: " + proto + "<br>"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        title=dict(
            text="跨協定時間線對齊圖（Multi-Protocol Timeline）",
            font=dict(color="#e2e8f0", size=16),
        ),
        xaxis=dict(
            title="時間 (ms)",
            gridcolor="#1e293b",
            zeroline=False,
        ),
        yaxis=dict(
            tickvals=[1, 2, 3, 4, 5],
            ticktext=["MCTP", "PCIe", "UART", "SPI", "I2C"],
            gridcolor="#1e293b",
            zeroline=False,
        ),
        legend=dict(
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor="#334155",
            borderwidth=1,
        ),
        margin=dict(l=60, r=20, t=50, b=40),
        height=400,
    )

    return fig


# ---------------------------------------------------------------------------
# Streamlit page render
# ---------------------------------------------------------------------------


def render() -> None:
    """Main render function for the cross-protocol correlation analysis page."""
    st.header("跨協定時間線關聯分析")
    st.caption(
        "上傳多組協定追蹤資料（I2C、SPI、UART、PCIe、MCTP），自動對齊時間線並偵測跨協定異常叢集，"
        "幫助定位系統級連鎖故障的根因（Root Cause）。"
    )

    render_guide_expander(
        "chapters/ch17_correlation.md",
        label="📖 點擊展開：跨協定關聯分析使用指南",
        fallback_title="📖 跨協定關聯分析使用指南",
        fallback_body=(
            "### 使用場景\n\n"
            "當系統發生難以單一協定解釋的故障時（例如 I2C NACK、SPI 寫入失敗、PCIe AER 錯誤或 MCTP 丟包同時出現），"
            "跨協定時間線能幫助工程師觀察事件發生順序，判定哪個事件是因、哪個是果。\n\n"
            "### 操作步驟\n\n"
            "1. 在下方分別上傳 I2C CSV、SPI CSV、UART 日誌、PCIe lspci/dmesg 及/或 MCTP/IPMB Hex。\n"
            "2. 系統自動解析各協定、對齊到同一時間軸。\n"
            "3. 檢視時間線圖表，紅色星號標記異常事件。\n"
            "4. 下方叢集分析表格會列出時間窗口內的跨協定異常群組。"
        ),
    )

    st.subheader("📂 上傳追蹤資料")

    sample_col1, _ = st.columns([2, 1])
    with sample_col1:
        if st.button(
            "📋 載入三協定範例資料",
            key="corr_load_all_examples",
            help="一鍵載入 I2C、SPI、UART、PCIe 與 MCTP 範例資料以體驗跨協定時間線關聯分析",
        ):
            st.session_state["corr_i2c_text"] = load_i2c_sample("address-nack")
            st.session_state["corr_spi_text"] = load_spi_sample()
            st.session_state["corr_uart_text"] = load_uart_sample("kernel-panic")
            st.session_state["corr_pcie_text"] = load_pcie_sample("lspci")
            st.session_state["corr_mctp_text"] = load_mctp_sample("mctp-pldm")
            st.rerun()

    col_i2c, col_spi, col_uart, col_pcie, col_mctp = st.columns(5)

    i2c_report = None
    spi_report = None
    uart_report = None
    pcie_report = None
    mctp_report = None

    with col_i2c:
        st.markdown("**I2C / PMBus CSV**")
        i2c_file = st.file_uploader(
            "上傳 I2C CSV", type=["csv"], key="corr_i2c_upload", label_visibility="collapsed"
        )
        if st.button("📋 載入 I2C 範例", key="corr_load_i2c_sample"):
            st.session_state["corr_i2c_text"] = load_i2c_sample("address-nack")
            st.rerun()
        i2c_text = st.text_area("或貼上 I2C CSV 內容", key="corr_i2c_text", height=120)
        i2c_input = None
        if i2c_file is not None:
            i2c_input = i2c_file.getvalue().decode("utf-8", errors="replace")
        elif i2c_text.strip():
            i2c_input = i2c_text.strip()

        if i2c_input:
            try:
                i2c_report, _ = analyze_i2c_input(i2c_input, "decoded_csv", 25.0)
                st.success(f"I2C: 解析完成 ({len(getattr(i2c_report, 'transactions', []))} 筆交易)")
            except Exception as exc:
                st.error(f"無法解析 I2C 輸入：{exc}")

    with col_spi:
        st.markdown("**SPI Flash CSV**")
        spi_file = st.file_uploader(
            "上傳 SPI CSV", type=["csv"], key="corr_spi_upload", label_visibility="collapsed"
        )
        if st.button("📋 載入 SPI 範例", key="corr_load_spi_sample"):
            st.session_state["corr_spi_text"] = load_spi_sample()
            st.rerun()
        spi_text = st.text_area("或貼上 SPI CSV 內容", key="corr_spi_text", height=120)
        spi_input = None
        if spi_file is not None:
            spi_input = spi_file.getvalue().decode("utf-8", errors="replace")
        elif spi_text.strip():
            spi_input = spi_text.strip()

        if spi_input:
            try:
                spi_report = analyze_spi_input(spi_input)
                st.success(f"SPI: 解析完成 ({len(getattr(spi_report, 'transactions', []))} 筆操作)")
            except Exception as exc:
                st.error(
                    f"無法解析 SPI 追蹤記錄（trace）：{_localize_gui_error(exc, domain='spi')}"
                )

    with col_uart:
        st.markdown("**UART Crash Log**")
        uart_file = st.file_uploader(
            "上傳 UART Log",
            type=["log", "txt"],
            key="corr_uart_upload",
            label_visibility="collapsed",
        )
        if st.button("📋 載入 UART 範例", key="corr_load_uart_sample"):
            st.session_state["corr_uart_text"] = load_uart_sample("kernel-panic")
            st.rerun()
        uart_text = st.text_area("或貼上 UART 日誌內容", key="corr_uart_text", height=120)
        uart_input = None
        if uart_file is not None:
            uart_input = uart_file.getvalue().decode("utf-8", errors="replace")
        elif uart_text.strip():
            uart_input = uart_text.strip()

        if uart_input:
            try:
                uart_report = parse_uart_log(uart_input)
                crash_type = getattr(getattr(uart_report, "crash_type", None), "value", "Unknown")
                st.success(f"UART: 解析完成 (類型: {crash_type})")
            except Exception as exc:
                st.error(f"UART 輸入錯誤：{_localize_gui_error(exc, domain='uart')}")

    with col_pcie:
        st.markdown("**PCIe lspci / AER**")
        pcie_file = st.file_uploader(
            "上傳 PCIe 日誌",
            type=["txt", "log", "dmesg"],
            key="corr_pcie_upload",
            label_visibility="collapsed",
        )
        if st.button("📋 載入 PCIe 範例", key="corr_load_pcie_sample"):
            st.session_state["corr_pcie_text"] = load_pcie_sample("lspci")
            st.rerun()
        pcie_text = st.text_area("或貼上 PCIe lspci/AER 內容", key="corr_pcie_text", height=120)
        pcie_input = None
        if pcie_file is not None:
            pcie_input = pcie_file.getvalue().decode("utf-8", errors="replace")
        elif pcie_text.strip():
            pcie_input = pcie_text.strip()

        if pcie_input:
            try:
                pcie_report = analyze_pcie_input(pcie_input)
                if (
                    isinstance(pcie_report, list)
                    and pcie_report
                    and hasattr(pcie_report[0], "error_name")
                ):
                    st.success(f"PCIe: 解析完成 ({len(pcie_report)} 個 AER 事件)")
                else:
                    dev_count = len(pcie_report) if isinstance(pcie_report, list) else 1
                    st.success(f"PCIe: 解析完成 ({dev_count} 個裝置設定空間)")
            except Exception as exc:
                st.error(f"無法解析 PCIe 輸入：{_localize_pcie_input_error(exc)}")

    with col_mctp:
        st.markdown("**MCTP / IPMB Hex**")
        mctp_file = st.file_uploader(
            "上傳 MCTP Hex",
            type=["hex", "txt", "log"],
            key="corr_mctp_upload",
            label_visibility="collapsed",
        )
        if st.button("📋 載入 MCTP 範例", key="corr_load_mctp_sample"):
            st.session_state["corr_mctp_text"] = load_mctp_sample("mctp-pldm")
            st.rerun()
        mctp_text = st.text_area("或貼上 MCTP/IPMB Hex 內容", key="corr_mctp_text", height=120)
        mctp_input = None
        if mctp_file is not None:
            mctp_input = mctp_file.getvalue().decode("utf-8", errors="replace")
        elif mctp_text.strip():
            mctp_input = mctp_text.strip()

        if mctp_input:
            try:
                mctp_report = analyze_mctp_input(mctp_input)
                st.success(f"MCTP: 解析完成 ({getattr(mctp_report, 'total_frames', 0)} 筆框架)")
            except Exception as exc:
                st.error(f"無法解析 MCTP 輸入：{_localize_mctp_error(exc)}")

    # --- Analysis ---
    has_any = (
        i2c_report is not None
        or spi_report is not None
        or uart_report is not None
        or pcie_report is not None
        or mctp_report is not None
    )

    if not has_any:
        st.info("👆 請至少上傳一組協定追蹤資料以啟動關聯分析。")
        render_session_controls(protocol="correlation", report_data=None)
        render_page_footer()
        return

    st.divider()
    st.subheader("📈 跨協定時間線")

    events = build_timeline_events(
        i2c_report=i2c_report,
        spi_report=spi_report,
        uart_report=uart_report,
        pcie_report=pcie_report,
        mctp_report=mctp_report,
    )

    if not events:
        st.warning("未偵測到有效的時間戳事件。請確認上傳的追蹤資料包含時間欄位。")
        render_session_controls(protocol="correlation", report_data=None)
        render_page_footer()
        return

    fig = _build_timeline_chart(events)
    st.plotly_chart(fig, key="corr_timeline_chart")

    # --- Statistics ---
    total_events = len(events)
    anomaly_count = sum(1 for e in events if e.get("anomaly"))
    protocols_seen = sorted({e["protocol"] for e in events})

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("總事件數", total_events)
    col_m2.metric("異常事件", anomaly_count)
    col_m3.metric("涵蓋協定", ", ".join(protocols_seen))

    # --- Cluster analysis ---
    st.subheader("🔗 跨協定異常叢集偵測")

    window_ms = st.slider(
        "叢集時間窗口 (ms)",
        min_value=0.1,
        max_value=50.0,
        value=2.0,
        step=0.1,
        help="在此時間窗口內出現的異常事件若涵蓋 >= 2 種協定，將被歸為同一叢集。",
        key="corr_cluster_window",
    )

    clusters = detect_cross_protocol_clusters(events, window_s=window_ms / 1000.0)

    if clusters:
        st.error(f"⚠️ 偵測到 {len(clusters)} 個跨協定異常叢集")
        for idx, cluster in enumerate(clusters, 1):
            with st.expander(
                f"叢集 #{idx} — 涉及協定: {', '.join(cluster['protocols'])}",
                expanded=True,
            ):
                st.markdown(f"**涉及協定**: {', '.join(cluster['protocols'])}")
                st.markdown(f"**事件摘要**: {cluster['summary']}")
                st.markdown(
                    "**可能意義**: 這些異常在極短時間內跨協定同時發生，"
                    "暗示可能存在共同根因（如電源異常、匯流排干擾或系統重置）。"
                )
    else:
        st.success("✅ 未偵測到跨協定異常叢集。各協定異常事件在時間上未呈現顯著關聯。")

    # --- Event table ---
    st.subheader("📋 事件明細")

    df = pd.DataFrame(events)
    if not df.empty:
        df["timestamp_ms"] = df["timestamp"] * 1000
        display_cols = ["protocol", "timestamp_ms", "label", "anomaly"]
        display_df = df[display_cols].rename(
            columns={
                "protocol": "協定",
                "timestamp_ms": "時間 (ms)",
                "label": "事件說明",
                "anomaly": "異常",
            }
        )
        st.dataframe(display_df, hide_index=True)

    corr_payload = {
        "total_events": total_events,
        "anomaly_count": anomaly_count,
        "protocols_seen": protocols_seen,
        "clusters": clusters,
        "events": events,
    }
    render_session_controls(
        protocol="correlation",
        report_data=corr_payload,
        config_data={"window_ms": window_ms},
    )

    render_page_footer()
