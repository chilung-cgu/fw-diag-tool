from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .models import AckType, I2CAnalysisReport


class I2CTimingCharts:
    """Generates rich interactive Plotly timing and bus health analytics charts."""

    @staticmethod
    def create_frequency_distribution(report: I2CAnalysisReport) -> go.Figure:
        bitrates: list[float] = []
        for tx in report.transactions:
            for p in tx.byte_packets:
                if p.bit_rate_khz and p.bit_rate_khz > 0:
                    bitrates.append(p.bit_rate_khz)

        if not bitrates:
            # Fallback based on average frequency
            avg_f = report.timing_stats.avg_frequency_khz
            bitrates = [avg_f] if avg_f > 0 else [100.0]

        df = pd.DataFrame({"SCL Clock Frequency (kHz)": bitrates})
        fig = px.histogram(
            df,
            x="SCL Clock Frequency (kHz)",
            nbins=30,
            title=f"<b>SCL Clock Frequency Distribution</b> (Avg: {report.timing_stats.avg_frequency_khz:.1f} kHz, Jitter: {report.timing_stats.frequency_jitter_pct:.1f}%)",
            template="plotly_dark",
            color_discrete_sequence=["#00CC96"],
        )
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=30))
        return fig

    @staticmethod
    def create_bus_activity_timeline(report: I2CAnalysisReport) -> go.Figure:
        data: list[dict[str, Any]] = []
        for tx in report.transactions:
            status = "ACK" if tx.address_ack == AckType.ACK else "ADDR NAK"
            if any(p.ack == AckType.NACK for p in tx.byte_packets if not p.is_address):
                status = "DATA NAK"
            data.append(
                {
                    "Transaction ID": f"#{tx.id}",
                    "Device": tx.device_name or f"0x{tx.address_7bit:02X}",
                    "Start Time (s)": tx.start_time,
                    "Duration (ms)": max(0.01, tx.duration_us / 1000.0),
                    "Direction": tx.direction.value,
                    "Status": status,
                    "Bytes": len(tx.data_bytes),
                }
            )

        df = pd.DataFrame(data)
        if df.empty:
            fig = go.Figure()
            fig.update_layout(title="No transactions to display", template="plotly_dark")
            return fig

        fig = px.scatter(
            df,
            x="Start Time (s)",
            y="Device",
            size="Duration (ms)",
            color="Status",
            color_discrete_map={"ACK": "#00CC96", "ADDR NAK": "#EF553B", "DATA NAK": "#FFA15A"},
            hover_data=["Transaction ID", "Direction", "Bytes", "Duration (ms)"],
            title="<b>Bus Transaction Timeline & Active Device Map</b>",
            template="plotly_dark",
        )
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=30))
        return fig

    @staticmethod
    def get_device_health_summary(report: I2CAnalysisReport) -> pd.DataFrame:
        summary_rows: list[dict[str, Any]] = []
        for addr_str, dev in report.devices_detected.items():
            addr_int = int(addr_str, 16)
            dev_txs = [t for t in report.transactions if t.address_7bit == addr_int]
            nack_count = sum(
                1
                for t in dev_txs
                if t.address_ack == AckType.NACK
                or any(p.ack == AckType.NACK for p in t.byte_packets if not p.is_address)
            )
            stretch_count = sum(len(t.clock_stretching_events) for t in dev_txs)
            total_tx = len(dev_txs)
            success_rate = (total_tx - nack_count) / total_tx * 100.0 if total_tx > 0 else 0.0

            grade = "A (Excellent)"
            if success_rate < 50.0 or stretch_count >= 5:
                grade = "F (Critical Fault)"
            elif success_rate < 80.0:
                grade = "D (High NACK Rate)"
            elif success_rate < 95.0 or stretch_count > 0:
                grade = "B (Minor Jitter / Retries)"

            summary_rows.append(
                {
                    "Slave Address": addr_str,
                    "Device Name": dev.get("name", "Unknown"),
                    "Category": dev.get("category", "General I2C"),
                    "Total Transactions": total_tx,
                    "NACK Count": nack_count,
                    "Success Rate": f"{success_rate:.1f} %",
                    "Clock Stretches": stretch_count,
                    "Health Grade": grade,
                }
            )

        return pd.DataFrame(summary_rows)
