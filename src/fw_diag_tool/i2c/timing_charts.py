from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .localization import localize_device_name, localize_direction, localize_status
from .models import AckType, I2CAnalysisReport, I2CDirection
from .status import TransactionStatus, get_transaction_status
from .timing import frequency_samples_khz

HEALTH_SUMMARY_COLUMNS = (
    "Slave Address",
    "Device Name",
    "Category",
    "Total Transactions",
    "NACK Count",
    "Unknown ACK Count",
    "Success Rate",
    "Clock Stretches",
    "Health Grade",
)


class I2CTimingCharts:
    """Generates rich interactive Plotly timing and bus health analytics charts."""

    @staticmethod
    def create_frequency_distribution(report: I2CAnalysisReport) -> go.Figure:
        bitrates = frequency_samples_khz(report.transactions)

        if not bitrates:
            fig = go.Figure()
            fig.update_layout(
                title="<b>SCL 時鐘頻率分佈（SCL Clock Frequency Distribution）</b>（不可用／unavailable）",
                template="plotly_dark",
                height=320,
                margin=dict(l=40, r=20, t=50, b=30),
            )
            fig.add_annotation(
                text="來源未提供位元率或位元組持續時間證據（bitrate／byte-duration evidence）",
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
            )
            return fig

        df = pd.DataFrame({"SCL Clock Frequency (kHz)": bitrates})
        fig = px.histogram(
            df,
            x="SCL Clock Frequency (kHz)",
            nbins=30,
            title=(
                "<b>SCL 時鐘頻率分佈（SCL Clock Frequency Distribution）</b> "
                f"（平均：{report.timing_stats.avg_frequency_khz:.1f} kHz；"
                f"跨度：{report.timing_stats.frequency_spread_pct:.1f}%（抖動："
                f"{report.timing_stats.frequency_jitter_pct:.1f}%）；樣本數：{len(bitrates)}）"
            ),
            template="plotly_dark",
            color_discrete_sequence=["#00CC96"],
            labels={"SCL Clock Frequency (kHz)": "SCL 時鐘頻率（kHz）"},
        )
        for trace in fig.data:
            trace.hovertemplate = "SCL 時鐘頻率（kHz）=%{x}<br>筆數=%{y}<extra></extra>"
        fig.update_yaxes(title_text="筆數")
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=30))
        return fig

    @staticmethod
    def create_bus_activity_timeline(report: I2CAnalysisReport) -> go.Figure:
        data: list[dict[str, Any]] = []
        for index, tx in enumerate(report.transactions):
            next_tx = (
                report.transactions[index + 1] if index + 1 < len(report.transactions) else None
            )
            status = get_transaction_status(tx, next_transaction=next_tx).value
            device_label = (
                localize_device_name(tx.device_name)
                if tx.device_name
                else (
                    f"0x{tx.address_7bit:02X}"
                    if tx.address_available
                    else "位址不可用（Address unavailable）"
                )
            )
            data.append(
                {
                    "Transaction ID": f"#{tx.id}",
                    "Device": device_label,
                    "Start Time (s)": tx.start_time if tx.timestamp_available else None,
                    "Duration (ms)": tx.duration_us / 1000.0 if tx.timestamp_available else None,
                    "Direction": localize_direction(
                        tx.direction
                        if tx.direction_available and isinstance(tx.direction, I2CDirection)
                        else None
                    ),
                    "Status": localize_status(status),
                    "Bytes": len(tx.data_bytes),
                }
            )

        df = pd.DataFrame(data)
        if df.empty:
            fig = go.Figure()
            fig.update_layout(
                title="沒有可顯示的交易（No transactions to display）", template="plotly_dark"
            )
            return fig

        timestamp_count = sum(1 for tx in report.transactions if tx.timestamp_available)
        if timestamp_count == 0:
            timeline_title = (
                "<b>匯流排交易時間軸與裝置活動圖（Bus Transaction Timeline & Active Device Map）</b> "
                "（時間戳記不可用／timestamps unavailable）"
            )
        elif timestamp_count < len(report.transactions):
            timeline_title = (
                "<b>匯流排交易時間軸與裝置活動圖（Bus Transaction Timeline & Active Device Map）</b> "
                "（時間戳記不完整／partial timestamps）"
            )
        else:
            timeline_title = "<b>匯流排交易時間軸與裝置活動圖（Bus Transaction Timeline & Active Device Map）</b>"

        scatter_args: dict[str, Any] = {
            "data_frame": df,
            "x": "Start Time (s)",
            "y": "Device",
            "color": "Status",
            "color_discrete_map": {
                localize_status("ACK"): "#00CC96",
                localize_status("ADDR NAK"): "#EF553B",
                localize_status("DATA NAK"): "#FFA15A",
                localize_status("READ END NAK"): "#636EFA",
                localize_status("ACK UNKNOWN"): "#7F7F7F",
                localize_status("EVIDENCE INCOMPLETE"): "#7F7F7F",
                localize_status("NO STOP"): "#EF553B",
                localize_status("ABORTED"): "#AB63FA",
            },
            "hover_data": ["Transaction ID", "Direction", "Bytes", "Duration (ms)"],
            "title": timeline_title,
            "template": "plotly_dark",
            "labels": {
                "Transaction ID": "交易 ID",
                "Device": "裝置",
                "Start Time (s)": "開始時間（s）",
                "Duration (ms)": "持續時間（ms）",
                "Direction": "方向",
                "Status": "狀態",
                "Bytes": "位元組數",
            },
        }
        if any(tx.timestamp_available and tx.duration_us > 0 for tx in report.transactions):
            scatter_args["size"] = "Duration (ms)"
        fig = px.scatter(**scatter_args)
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=30))
        return fig

    @staticmethod
    def get_device_health_summary(report: I2CAnalysisReport) -> pd.DataFrame:
        summary_rows: list[dict[str, Any]] = []
        for addr_str, dev in report.devices_detected.items():
            addr_int = int(addr_str, 16)
            dev_txs = [t for t in report.transactions if t.address_7bit == addr_int]
            statuses = [
                get_transaction_status(
                    t,
                    next_transaction=(
                        report.transactions[index + 1]
                        if index + 1 < len(report.transactions)
                        else None
                    ),
                )
                for index, t in enumerate(report.transactions)
                if t.address_7bit == addr_int
            ]
            # The display status has a single canonical label, so a missing
            # STOP can legitimately take precedence over a data NACK.  Health
            # counters must still reflect the independent ACK evidence rather
            # than treating that transaction as a successful ACK.
            nack_count = sum(
                t.address_ack == AckType.NACK or t.has_unexpected_data_nack for t in dev_txs
            )
            unknown_ack_count = sum(
                status == TransactionStatus.EVIDENCE_INCOMPLETE
                or status == TransactionStatus.ACK_UNKNOWN
                or t.address_ack in (AckType.NONE, None)
                or any(
                    packet.ack in (AckType.NONE, None)
                    for packet in t.byte_packets
                    if not packet.is_address
                )
                for t, status in zip(dev_txs, statuses, strict=True)
            )
            stretch_count = sum(len(t.clock_stretching_events) for t in dev_txs)
            total_tx = len(dev_txs)
            known_tx = total_tx - unknown_ack_count
            success_rate = (known_tx - nack_count) / known_tx * 100.0 if known_tx > 0 else None

            grade = "N/A (ACK unavailable)" if success_rate is None else "A (Excellent)"
            if success_rate is not None and (success_rate < 50.0 or stretch_count >= 5):
                grade = "F (Critical Fault)"
            elif success_rate is not None and success_rate < 80.0:
                grade = "D (High NACK Rate)"
            elif success_rate is not None and (success_rate < 95.0 or stretch_count > 0):
                grade = "B (Minor Jitter / Retries)"

            summary_rows.append(
                {
                    "Slave Address": addr_str,
                    "Device Name": dev.get("name") or f"Unknown Device ({addr_str})",
                    "Category": dev.get("category") or "General I2C Peripheral",
                    "Total Transactions": total_tx,
                    "NACK Count": nack_count,
                    "Unknown ACK Count": unknown_ack_count,
                    "Success Rate": f"{success_rate:.1f} %" if success_rate is not None else "N/A",
                    "Clock Stretches": stretch_count,
                    "Health Grade": grade,
                }
            )

        return pd.DataFrame(summary_rows, columns=HEALTH_SUMMARY_COLUMNS)
