from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from fw_diag_tool.errors import ResourceLimitError

from .localization import localize_waveform_detail, localize_waveform_label
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
    source_transition_count: int = 0
    rendered_transition_count: int = 0
    downsampled: bool = False


class I2CWaveformReconstructor:
    """Reconstructs microsecond-level SCL/SDA digital waveforms and protocol overlays."""

    ANNOTATION_COLORS = {
        "START": "#00CC96",  # Emerald Green
        "ADDRESS": "#636EFA",  # Electric Blue
        "ACK": "#00FA9A",  # Medium Spring Green
        "NACK": "#EF553B",  # Coral Red
        "UNKNOWN": "#7F7F7F",  # Evidence not present in source trace
        "DATA": "#AB63FA",  # Royal Purple
        "STRETCH": "#FFA15A",  # Amber Warning
        "STOP": "#FF6692",  # Vibrant Pink
        "IDLE": "#7F7F7F",  # Gray
    }

    def __init__(self, default_clock_khz: float = 100.0):
        self._validate_clock(default_clock_khz, "default_clock_khz")
        self.default_clock_khz = default_clock_khz

    @staticmethod
    def _validate_clock(clock_khz: float, name: str) -> None:
        if (
            isinstance(clock_khz, bool)
            or not isinstance(clock_khz, (int, float))
            or not math.isfinite(float(clock_khz))
            or clock_khz <= 0
        ):
            raise ValueError(f"{name} must be a positive finite number")

    def reconstruct_transaction_waveform(
        self,
        tx: I2CTransaction,
        clock_khz: float | None = None,
        t_offset_us: float = 0.0,
        max_points: int | None = None,
    ) -> I2CWaveformData:
        if not isinstance(tx, I2CTransaction):
            raise TypeError("tx must be an I2CTransaction")
        if (
            not tx.address_available
            or not tx.direction_available
            or not isinstance(tx.direction, I2CDirection)
        ):
            raise ValueError(
                "cannot reconstruct a protocol waveform without trustworthy address and direction evidence"
            )
        if any(not packet.byte_available for packet in tx.byte_packets if not packet.is_address):
            raise ValueError("cannot reconstruct a protocol waveform with unavailable data bytes")
        if max_points is not None:
            if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points <= 0:
                raise ValueError("max_points must be a positive integer or None")
            # The renderer emits three samples for each of the eight data bits
            # and three for the ACK clock, plus framing points. This is a
            # conservative pre-flight estimate: reject before allocating large
            # Plotly arrays rather than discovering the limit after expansion.
            byte_count = 1 + len(tx.data_bytes)
            estimated_points = (
                4
                + (4 if tx.has_stop else 0)
                + (27 * byte_count)
                + (2 * len(tx.clock_stretching_events))
            )
            if estimated_points > max_points:
                raise ResourceLimitError(
                    f"I2C transaction waveform requires about {estimated_points} points; "
                    f"limit is {max_points}",
                    resource="i2c_waveform_points",
                    limit=max_points,
                    observed=estimated_points,
                )
        if clock_khz is not None:
            self._validate_clock(clock_khz, "clock_khz")
        clk_khz = self.default_clock_khz if clock_khz is None else clock_khz
        if (
            isinstance(t_offset_us, bool)
            or not isinstance(t_offset_us, (int, float))
            or not math.isfinite(float(t_offset_us))
            or t_offset_us < 0
        ):
            raise ValueError("t_offset_us must be finite and non-negative")
        t_half_period_us = max(0.5, 500.0 / clk_khz)  # 5µs for 100kHz, 1.25µs for 400kHz

        time_us: list[float] = []
        scl: list[int] = []
        sda: list[int] = []
        annotations: list[ProtocolAnnotation] = []

        cur_t = t_offset_us

        def add_point(t: float, scl_v: int, sda_v: int) -> None:
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
        annotations.append(
            ProtocolAnnotation(
                start_time=start_t_begin,
                end_time=cur_t,
                label="START" if not tx.is_repeated_start else "Sr",
                annotation_type="START",
                color=self.ANNOTATION_COLORS["START"],
                details="I2C Start Condition (SDA falling edge while SCL is High)",
            )
        )

        # Helper to emit 8-bit byte + 1 ACK/NACK clock cycle
        def emit_byte(
            byte_val: int,
            is_addr: bool,
            ack: AckType,
            stretch_ms: float = 0.0,
            label_override: str | None = None,
        ) -> None:
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

            annotations.append(
                ProtocolAnnotation(
                    start_time=byte_begin_t,
                    end_time=byte_end_t,
                    label=ann_label,
                    annotation_type=ann_type,
                    color=self.ANNOTATION_COLORS[ann_type],
                    details=f"Byte: 0x{byte_val:02X} (binary: {byte_val:08b})",
                )
            )

            # Optional Clock Stretching before/during ACK
            if stretch_ms > 0:
                stretch_us = stretch_ms * 1000.0
                str_begin = cur_t
                add_point(cur_t, 0, 1)
                cur_t += stretch_us
                add_point(cur_t, 0, 1)
                annotations.append(
                    ProtocolAnnotation(
                        start_time=str_begin,
                        end_time=cur_t,
                        label=f"Stretch {stretch_ms:.1f}ms",
                        annotation_type="STRETCH",
                        color=self.ANNOTATION_COLORS["STRETCH"],
                        details=f"Slave SCL Clock Stretching: {stretch_ms:.3f} ms",
                    )
                )

            # 9th Clock Cycle: ACK / NACK
            ack_begin_t = cur_t
            ack_bit = 0 if ack == AckType.ACK else 1
            add_point(cur_t, 0, ack_bit)
            cur_t += t_half_period_us
            add_point(cur_t, 1, ack_bit)
            cur_t += t_half_period_us
            add_point(cur_t, 0, ack_bit)

            if ack == AckType.ACK:
                ack_type = "ACK"
                ack_details = "Acknowledge bit: 0 (ACK)"
            elif ack == AckType.NACK:
                ack_type = "NACK"
                ack_details = "Not-Acknowledge bit: 1 (NACK)"
            else:
                ack_type = "UNKNOWN"
                ack_details = "ACK/NACK was not present in the source trace; SDA level is reconstructed as high."
            annotations.append(
                ProtocolAnnotation(
                    start_time=ack_begin_t,
                    end_time=cur_t,
                    label=ack_type,
                    annotation_type=ack_type,
                    color=self.ANNOTATION_COLORS[ack_type],
                    details=ack_details,
                )
            )

        # 3. Emit Address Byte (7-bit address + R/W bit)
        addr_8b = (tx.address_7bit << 1) | (1 if tx.direction == I2CDirection.READ else 0)
        # Find any clock stretching associated with address
        addr_stretch_ms = 0.0
        if tx.clock_stretching_events:
            addr_stretch_ms = tx.clock_stretching_events[0].get("duration_ms", 0.0)
        emit_byte(addr_8b, is_addr=True, ack=tx.address_ack, stretch_ms=addr_stretch_ms)

        # 4. Emit Data Bytes
        # Aggregate analyzer rows can preserve known payload bytes while the
        # single ACK/NACK cannot be attributed to a particular byte. Render
        # that protocol shape with UNKNOWN ACK slots instead of silently
        # dropping the data from the waveform.
        if tx.address_ack == AckType.ACK or tx.aggregate_ack != AckType.NONE:
            data_pkts = [p for p in tx.byte_packets if not p.is_address and p.byte_available]
            for idx, data_b in enumerate(tx.data_bytes):
                pkt_ack = data_pkts[idx].ack if idx < len(data_pkts) else AckType.NONE
                if tx.aggregate_ack != AckType.NONE:
                    pkt_ack = AckType.NONE
                # Label detail
                lbl = f"0x{data_b:02X}"
                if idx == 0 and tx.command_code is not None and (
                    data_b == tx.command_code or tx.command_code > 0xFF
                ):
                    lbl = f"Reg:0x{data_b:02X}"
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
            annotations.append(
                ProtocolAnnotation(
                    start_time=stop_begin_t,
                    end_time=cur_t,
                    label="STOP",
                    annotation_type="STOP",
                    color=self.ANNOTATION_COLORS["STOP"],
                    details="I2C Stop Condition (SDA rising edge while SCL is High)",
                )
            )

        rendered_count = len(time_us)
        return I2CWaveformData(
            time_us=time_us,
            scl=scl,
            sda=sda,
            annotations=annotations,
            source_transition_count=rendered_count,
            rendered_transition_count=rendered_count,
        )

    def reconstruct_transfer_spec_waveform(
        self,
        spec: Any,
        *,
        clock_khz: float | None = None,
        t_offset_us: float = 0.0,
    ) -> I2CWaveformData:
        """Render a validated canonical transfer, retaining unknown RX bytes.

        This path is deliberately separate from measured-transaction
        reconstruction.  The canonical spec describes protocol intent; read
        payload values are either ``Unknown`` or explicitly marked expected
        and are never presented as captured measurements.
        """

        from .transfer_spec import UNKNOWN_BYTE, I2CTransferSpec

        if not isinstance(spec, I2CTransferSpec):
            raise TypeError("spec must be an I2CTransferSpec")
        spec.validate()
        if clock_khz is not None:
            self._validate_clock(clock_khz, "clock_khz")
            if not 1.0 <= float(clock_khz) <= 1000.0:
                raise ValueError("clock_khz must be between 1 and 1000 kHz")
        clk_khz = spec.clock_khz if clock_khz is None else float(clock_khz)
        if not 1.0 <= clk_khz <= 1000.0:
            raise ValueError("clock_khz must be between 1 and 1000 kHz")
        if (
            isinstance(t_offset_us, bool)
            or not isinstance(t_offset_us, (int, float))
            or not math.isfinite(float(t_offset_us))
            or t_offset_us < 0
        ):
            raise ValueError("t_offset_us must be finite and non-negative")

        t_half_period_us = max(0.5, 500.0 / clk_khz)
        time_us: list[float] = []
        scl: list[int] = []
        sda: list[int] = []
        annotations: list[ProtocolAnnotation] = []
        cur_t = float(t_offset_us)

        def add_point(scl_v: int, sda_v: int) -> None:
            time_us.append(round(cur_t, 4))
            scl.append(scl_v)
            sda.append(sda_v)

        add_point(1, 1)
        cur_t += t_half_period_us
        add_point(1, 1)

        def emit_start(repeated: bool) -> None:
            nonlocal cur_t
            if repeated:
                # Release SDA while SCL is still low before raising SCL.  A
                # direct (0,0)->(1,1) jump would look like simultaneous SCL
                # and SDA edges to a strict raw-transition decoder.
                cur_t += t_half_period_us * 0.5
                add_point(0, 1)
                cur_t += t_half_period_us * 0.5
                add_point(1, 1)
            begin = cur_t
            cur_t += t_half_period_us * 0.5
            add_point(1, 0)
            cur_t += t_half_period_us * 0.5
            add_point(0, 0)
            annotations.append(
                ProtocolAnnotation(
                    start_time=begin,
                    end_time=cur_t,
                    label="Sr" if repeated else "START",
                    annotation_type="START",
                    color=self.ANNOTATION_COLORS["START"],
                    details=(
                        "I2C Repeated START (SDA falling edge while SCL is High)"
                        if repeated
                        else "I2C Start Condition (SDA falling edge while SCL is High)"
                    ),
                )
            )

        def emit_byte(
            value: int | None,
            *,
            is_address: bool,
            read_byte: bool,
            expected: bool = False,
            ack_controller_nack: bool = False,
        ) -> None:
            nonlocal cur_t
            begin = cur_t
            known = value is not None
            rendered_value = 0xFF if value is None else value
            for bit_pos in range(7, -1, -1):
                bit = (rendered_value >> bit_pos) & 1
                add_point(0, bit)
                cur_t += t_half_period_us
                add_point(1, bit)
                cur_t += t_half_period_us
                add_point(0, bit)
            end = cur_t
            if is_address:
                rw = "R" if (rendered_value & 1) else "W"
                label = f"0x{rendered_value >> 1:02X} ({rw})"
                annotation_type = "ADDRESS"
                details = f"Address byte: 0x{rendered_value:02X}"
            elif not known:
                label = "Unknown"
                annotation_type = "UNKNOWN"
                details = "Unknown read byte placeholder; value is not measured"
            elif expected:
                label = f"Expected 0x{rendered_value:02X}"
                annotation_type = "UNKNOWN"
                details = "Expected/assumed read byte; not measured from a device or capture"
            else:
                label = f"0x{rendered_value:02X}"
                annotation_type = "DATA"
                details = f"Byte: 0x{rendered_value:02X}"
            annotations.append(
                ProtocolAnnotation(
                    start_time=begin,
                    end_time=end,
                    label=label,
                    annotation_type=annotation_type,
                    color=self.ANNOTATION_COLORS[annotation_type],
                    details=details,
                )
            )
            ack_begin = cur_t
            ack_bit = 1 if ack_controller_nack else 0
            add_point(0, ack_bit)
            cur_t += t_half_period_us
            add_point(1, ack_bit)
            cur_t += t_half_period_us
            add_point(0, ack_bit)
            ack_type = "NACK" if ack_controller_nack else "ACK"
            ack_details = (
                "Controller NACK terminates the final read byte"
                if ack_controller_nack
                else ("Slave ACK" if read_byte else "Acknowledge bit: 0 (ACK)")
            )
            annotations.append(
                ProtocolAnnotation(
                    start_time=ack_begin,
                    end_time=cur_t,
                    label=ack_type,
                    annotation_type=ack_type,
                    color=self.ANNOTATION_COLORS[ack_type],
                    details=ack_details,
                )
            )

        for segment in spec.segments:
            emit_start(segment.repeated_start)
            address_byte = (spec.address_7bit << 1) | (1 if segment.is_read else 0)
            emit_byte(address_byte, is_address=True, read_byte=segment.is_read)
            payload = list(segment.bytes)
            for byte_index, byte in enumerate(payload):
                is_unknown = byte == UNKNOWN_BYTE
                expected = False
                value: int | None
                if is_unknown:
                    value = None
                    if spec.expected_read_data and segment.is_read:
                        # The expected sequence is only used for visual
                        # labelling; the segment and code generators retain
                        # Unknown so it cannot be mistaken for measured data.
                        read_index = byte_index
                        value = spec.expected_read_data[read_index]
                        expected = True
                else:
                    value = int(byte)
                final_read = segment.is_read and byte_index == len(payload) - 1
                emit_byte(
                    value,
                    is_address=False,
                    read_byte=segment.is_read,
                    expected=expected,
                    ack_controller_nack=final_read,
                )

        stop_begin = cur_t
        add_point(0, 0)
        cur_t += t_half_period_us * 0.5
        add_point(1, 0)
        cur_t += t_half_period_us * 0.5
        add_point(1, 1)
        cur_t += t_half_period_us
        add_point(1, 1)
        annotations.append(
            ProtocolAnnotation(
                start_time=stop_begin,
                end_time=cur_t,
                label="STOP",
                annotation_type="STOP",
                color=self.ANNOTATION_COLORS["STOP"],
                details="I2C Stop Condition (SDA rising edge while SCL is High)",
            )
        )

        rendered_count = len(time_us)
        return I2CWaveformData(
            time_us=time_us,
            scl=scl,
            sda=sda,
            annotations=annotations,
            source_transition_count=spec.estimated_waveform_points,
            rendered_transition_count=rendered_count,
            downsampled=False,
        )

    # Friendly aliases used by callers that treat the spec as the input type.
    reconstruct_spec_waveform = reconstruct_transfer_spec_waveform
    waveform_from_spec = reconstruct_transfer_spec_waveform

    @classmethod
    def create_plotly_figure(
        cls,
        waveform: I2CWaveformData,
        title: str = "I2C 互動式數位波形與協定疊加（Protocol Overlay）",
    ) -> go.Figure:
        if title == "I2C Interactive Digital Waveform & Protocol Overlay":
            title = "I2C 互動式數位波形與協定疊加（Protocol Overlay）"
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.35, 0.32, 0.33],
            subplot_titles=("協定標註軌（Protocol Annotation Track）", "SDA（串列資料）", "SCL（串列時鐘）"),
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
                    text=["", f"<b>{localize_waveform_label(ann.label)}</b>", "", "", ""],
                    textposition="middle center",
                    textfont=dict(color="#FFFFFF", size=11),
                    name=ann.annotation_type,
                    hoverinfo="text",
                    hovertext=(
                        f"{localize_waveform_label(ann.label)}（{ann.annotation_type}）<br>"
                        f"時間：{ann.start_time:.1f} µs～{ann.end_time:.1f} µs "
                        f"（Δ={ann.end_time - ann.start_time:.1f} µs）<br>"
                        f"{localize_waveform_detail(ann.details)}"
                    ),
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

        # 2. SDA Digital Waveform (Step line)
        fig.add_trace(
            go.Scatter(
                x=waveform.time_us,
                y=waveform.sda,
                mode="lines",
                    line=dict(shape="hv", color="#00F0FF", width=2.5),
                    name="SDA",
                    hovertemplate="時間：%{x:.1f} µs<br>邏輯電位：%{y}<extra>SDA</extra>",
            ),
            row=2,
            col=1,
        )

        # 3. SCL Digital Waveform (Step line)
        fig.add_trace(
            go.Scatter(
                x=waveform.time_us,
                y=waveform.scl,
                mode="lines",
                    line=dict(shape="hv", color="#FFFF00", width=2.5),
                    name="SCL",
                    hovertemplate="時間：%{x:.1f} µs<br>邏輯電位：%{y}<extra>SCL</extra>",
            ),
            row=3,
            col=1,
        )

        # Add one compact legend entry per annotation kind.  The filled
        # protocol boxes themselves remain hidden from the legend so a long
        # capture does not create one legend item per byte.
        annotation_types = dict.fromkeys(annotation.annotation_type for annotation in waveform.annotations)
        for annotation_type in annotation_types:
            color = next(
                annotation.color
                for annotation in waveform.annotations
                if annotation.annotation_type == annotation_type
            )
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(size=10, color=color),
                    name=annotation_type,
                    legendgroup=annotation_type,
                    showlegend=True,
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )

        fig.update_layout(
            title=dict(text=f"<b>{title}</b>", font=dict(size=16, color="#FFFFFF")),
            template="plotly_dark",
            height=420,
            margin=dict(l=50, r=30, t=50, b=40),
            hovermode="x unified",
            showlegend=True,
        )

        fig.update_yaxes(
            range=[-0.1, 1.1], tickvals=[0, 1], ticktext=["低電位 LOW (0)", "高電位 HIGH (1)"], row=2, col=1
        )
        fig.update_yaxes(
            range=[-0.1, 1.1], tickvals=[0, 1], ticktext=["低電位 LOW (0)", "高電位 HIGH (1)"], row=3, col=1
        )
        fig.update_yaxes(showticklabels=False, showgrid=False, range=[0.0, 1.0], row=1, col=1)
        fig.update_xaxes(title_text="時間（µs）", row=3, col=1)

        return fig
