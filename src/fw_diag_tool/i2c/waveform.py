from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import AckType, I2CDirection, I2CTransaction


@dataclass
class ProtocolAnnotation:
    start_time: float
    end_time: float
    label: str
    annotation_type: str  # "START", "ADDRESS", "ACK", "NACK", "DATA", "STRETCH", "STOP"
    color: str
    details: str = ""


@dataclass
class I2CWaveformData:
    time_us: list[float] = field(default_factory=list)
    scl: list[int] = field(default_factory=list)
    sda: list[int] = field(default_factory=list)
    annotations: list[ProtocolAnnotation] = field(default_factory=list)


class I2CWaveformReconstructor:
    """Reconstructs microsecond-level SCL/SDA digital waveforms and protocol overlays."""

    ANNOTATION_COLORS = {
        "START": "#00CC96",          # Emerald Green
        "ADDRESS": "#636EFA",        # Electric Blue
        "ACK": "#00FA9A",            # Medium Spring Green
        "NACK": "#EF553B",           # Coral Red
        "DATA": "#AB63FA",           # Royal Purple
        "STRETCH": "#FFA15A",        # Amber Warning
        "STOP": "#FF6692",           # Vibrant Pink
        "IDLE": "#7F7F7F",           # Gray
    }

    def __init__(self, default_clock_khz: float = 100.0):
        self.default_clock_khz = default_clock_khz

    def reconstruct_transaction_waveform(
        self,
        tx: I2CTransaction,
        clock_khz: float | None = None,
        t_offset_us: float = 0.0
    ) -> I2CWaveformData:
        clk_khz = clock_khz or self.default_clock_khz
        t_half_period_us = max(0.5, 500.0 / clk_khz)  # 5µs for 100kHz, 1.25µs for 400kHz

        time_us: list[float] = []
        scl: list[int] = []
        sda: list[int] = []
        annotations: list[ProtocolAnnotation] = []

        cur_t = t_offset_us

        def add_point(t: float, scl_v: int, sda_v: int):
            time_us.append(round(t, 4))
            scl.append(scl_v)
            sda.append(sda_v)

        # 1. Bus Idle State (SCL=1, SDA=1)
        add_point(cur_t, 1, 1)
        cur_t += t_half_period_us
        add_point(cur_t, 1, 1)

        # 2. START Condition (SDA goes 1->0 while SCL is 1)
        start_t_begin = cur_t
        cur_t += t_half_period_us * 0.5
        add_point(cur_t, 1, 0)
        cur_t += t_half_period_us * 0.5
        add_point(cur_t, 0, 0)
        annotations.append(ProtocolAnnotation(
            start_time=start_t_begin,
            end_time=cur_t,
            label="START" if not tx.is_repeated_start else "Sr",
            annotation_type="START",
            color=self.ANNOTATION_COLORS["START"],
            details="I2C Start Condition (SDA falling edge while SCL is High)"
        ))

        # Helper to emit 8-bit byte + 1 ACK/NACK clock cycle
        def emit_byte(byte_val: int, is_addr: bool, ack: AckType, stretch_ms: float = 0.0, label_override: str | None = None):
            nonlocal cur_t
            byte_begin_t = cur_t

            # 8 Data Bits (MSB to LSB)
            for bit_pos in range(7, -1, -1):
                bit_val = (byte_val >> bit_pos) & 0x01
                # SCL Low -> Setup SDA
                add_point(cur_t, 0, bit_val)
                cur_t += t_half_period_us
                # SCL High -> Sample SDA
                add_point(cur_t, 1, bit_val)
                cur_t += t_half_period_us
                # SCL Low -> Hold complete
                add_point(cur_t, 0, bit_val)

            byte_end_t = cur_t
            if is_addr:
                rw_str = "R" if (byte_val & 0x01) else "W"
                addr_7b = byte_val >> 1
                ann_label = f"0x{addr_7b:02X} ({rw_str})"
                ann_type = "ADDRESS"
            else:
                ann_label = label_override or f"0x{byte_val:02X}"
                ann_type = "DATA"

            annotations.append(ProtocolAnnotation(
                start_time=byte_begin_t,
                end_time=byte_end_t,
                label=ann_label,
                annotation_type=ann_type,
                color=self.ANNOTATION_COLORS[ann_type],
                details=f"Byte: 0x{byte_val:02X} (binary: {byte_val:08b})"
            ))

            # Optional Clock Stretching before/during ACK
            if stretch_ms > 0:
                stretch_us = stretch_ms * 1000.0
                str_begin = cur_t
                add_point(cur_t, 0, 1)
                cur_t += stretch_us
                add_point(cur_t, 0, 1)
                annotations.append(ProtocolAnnotation(
                    start_time=str_begin,
                    end_time=cur_t,
                    label=f"Stretch {stretch_ms:.1f}ms",
                    annotation_type="STRETCH",
                    color=self.ANNOTATION_COLORS["STRETCH"],
                    details=f"Slave SCL Clock Stretching: {stretch_ms:.3f} ms"
                ))

            # 9th Clock Cycle: ACK / NACK
            ack_begin_t = cur_t
            ack_bit = 0 if ack == AckType.ACK else 1
            add_point(cur_t, 0, ack_bit)
            cur_t += t_half_period_us
            add_point(cur_t, 1, ack_bit)
            cur_t += t_half_period_us
            add_point(cur_t, 0, ack_bit)

            ack_type = "ACK" if ack == AckType.ACK else "NACK"
            annotations.append(ProtocolAnnotation(
                start_time=ack_begin_t,
                end_time=cur_t,
                label=ack_type,
                annotation_type=ack_type,
                color=self.ANNOTATION_COLORS[ack_type],
                details="Acknowledge bit: 0 (ACK)" if ack == AckType.ACK else "Not-Acknowledge bit: 1 (NACK)"
            ))

        # 3. Emit Address Byte (7-bit address + R/W bit)
        addr_8b = (tx.address_7bit << 1) | (1 if tx.direction == I2CDirection.READ else 0)
        # Find any clock stretching associated with address
        addr_stretch_ms = 0.0
        if tx.clock_stretching_events:
            addr_stretch_ms = tx.clock_stretching_events[0].get("duration_ms", 0.0)
        emit_byte(addr_8b, is_addr=True, ack=tx.address_ack, stretch_ms=addr_stretch_ms)

        # 4. Emit Data Bytes
        if tx.address_ack == AckType.ACK:
            data_pkts = [p for p in tx.byte_packets if not p.is_address]
            for idx, data_b in enumerate(tx.data_bytes):
                pkt_ack = data_pkts[idx].ack if idx < len(data_pkts) else AckType.ACK
                # Label detail
                lbl = f"0x{data_b:02X}"
                if idx == 0 and tx.command_code is not None:
                    lbl = f"Cmd:0x{data_b:02X}"
                emit_byte(data_b, is_addr=False, ack=pkt_ack, label_override=lbl)

        # 5. STOP Condition (SDA goes 0->1 while SCL is 1)
        if tx.has_stop:
            stop_begin_t = cur_t
            add_point(cur_t, 0, 0)
            cur_t += t_half_period_us * 0.5
            add_point(cur_t, 1, 0)
            cur_t += t_half_period_us * 0.5
            add_point(cur_t, 1, 1)
            cur_t += t_half_period_us
            add_point(cur_t, 1, 1)
            annotations.append(ProtocolAnnotation(
                start_time=stop_begin_t,
                end_time=cur_t,
                label="STOP",
                annotation_type="STOP",
                color=self.ANNOTATION_COLORS["STOP"],
                details="I2C Stop Condition (SDA rising edge while SCL is High)"
            ))

        return I2CWaveformData(
            time_us=time_us,
            scl=scl,
            sda=sda,
            annotations=annotations
        )

    @classmethod
    def create_plotly_figure(
        cls,
        waveform: I2CWaveformData,
        title: str = "I2C Interactive Digital Waveform & Protocol Overlay"
    ) -> go.Figure:
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.35, 0.32, 0.33],
            subplot_titles=("Protocol Annotation Track", "SDA (Serial Data)", "SCL (Serial Clock)")
        )

        # 1. Protocol Annotation Track (Horizontal colored boxes)
        for ann in waveform.annotations:
            fig.add_trace(
                go.Scatter(
                    x=[ann.start_time, ann.end_time, ann.end_time, ann.start_time, ann.start_time],
                    y=[0.1, 0.1, 0.9, 0.9, 0.1],
                    fill="toself",
                    fillcolor=ann.color,
                    line=dict(color=ann.color, width=1.5),
                    mode="lines+text",
                    text=["", f"<b>{ann.label}</b>", "", "", ""],
                    textposition="middle center",
                    textfont=dict(color="#FFFFFF", size=11),
                    name=ann.annotation_type,
                    hoverinfo="text",
                    hovertext=f"{ann.label} ({ann.annotation_type})<br>Time: {ann.start_time:.1f}µs - {ann.end_time:.1f}µs (Δ={(ann.end_time - ann.start_time):.1f}µs)<br>{ann.details}",
                    showlegend=False,
                ),
                row=1, col=1
            )

        # 2. SDA Digital Waveform (Step line)
        fig.add_trace(
            go.Scatter(
                x=waveform.time_us,
                y=waveform.sda,
                mode="lines",
                line=dict(shape="hv", color="#00F0FF", width=2.5),
                name="SDA",
                hoverinfo="x+y",
            ),
            row=2, col=1
        )

        # 3. SCL Digital Waveform (Step line)
        fig.add_trace(
            go.Scatter(
                x=waveform.time_us,
                y=waveform.scl,
                mode="lines",
                line=dict(shape="hv", color="#FFFF00", width=2.5),
                name="SCL",
                hoverinfo="x+y",
            ),
            row=3, col=1
        )

        fig.update_layout(
            title=dict(text=f"<b>{title}</b>", font=dict(size=16, color="#FFFFFF")),
            template="plotly_dark",
            height=420,
            margin=dict(l=50, r=30, t=50, b=40),
            hovermode="x unified",
            showlegend=False,
        )

        fig.update_yaxes(range=[-0.1, 1.1], tickvals=[0, 1], ticktext=["LOW (0V)", "HIGH (3.3V)"], row=2, col=1)
        fig.update_yaxes(range=[-0.1, 1.1], tickvals=[0, 1], ticktext=["LOW (0V)", "HIGH (3.3V)"], row=3, col=1)
        fig.update_yaxes(showticklabels=False, showgrid=False, range=[0.0, 1.0], row=1, col=1)
        fig.update_xaxes(title_text="Time (µs)", row=3, col=1)

        return fig