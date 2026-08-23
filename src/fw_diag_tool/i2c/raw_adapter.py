"""Adapters from raw digital I2C captures to the existing diagnostic/UI models.

The raw decoder intentionally owns only physical edge validation and protocol
decoding.  This module bridges that typed result into the long-standing
``I2CDiagnosticEngine`` event model and the Plotly waveform model without
claiming that a reconstructed analyzer-table waveform was measured.
"""

from __future__ import annotations

from itertools import pairwise
from statistics import median
from typing import TYPE_CHECKING

from fw_diag_tool.i2c.models import (
    AckType,
    I2CDirection,
    RawEventType,
    RawI2CEvent,
)
from fw_diag_tool.i2c.raw_capture import (
    RawAck,
    RawByteKind,
    RawConditionKind,
    RawI2CByteSample,
    RawI2CDecodeResult,
    RawI2CDirection,
)

if TYPE_CHECKING:
    from fw_diag_tool.i2c.waveform import I2CWaveformData


def raw_decode_to_events(result: RawI2CDecodeResult) -> list[RawI2CEvent]:
    """Convert a validated raw capture into events accepted by the main engine.

    Byte duration is derived only from the measured rising-edge period and is
    therefore source-backed.  No timestamps or ACK values are synthesized.
    """
    events: list[RawI2CEvent] = []
    all_periods = [
        period
        for transaction in result.transactions
        for sample in (transaction.address_sample, *transaction.data_samples)
        for period in _sample_periods(sample)
    ]
    nominal_period_s = median(all_periods) if all_periods else None
    for packet_id, transaction in enumerate(result.transactions):
        start_type = (
            RawEventType.REPEATED_START
            if transaction.start_kind == RawConditionKind.REPEATED_START
            else RawEventType.START
        )
        events.append(
            RawI2CEvent(
                timestamp=transaction.start_time_s,
                event_type=start_type,
                packet_id=packet_id,
                timestamp_available=True,
            )
        )
        events.append(
            _byte_to_event(
                transaction.address_sample,
                packet_id,
                True,
                nominal_period_s=nominal_period_s,
            )
        )
        for sample in transaction.data_samples:
            events.append(
                _byte_to_event(sample, packet_id, False, nominal_period_s=nominal_period_s)
            )

        if transaction.end_kind == RawConditionKind.STOP:
            events.append(
                RawI2CEvent(
                    timestamp=transaction.end_time_s,
                    event_type=RawEventType.STOP,
                    packet_id=packet_id,
                    timestamp_available=True,
                )
            )
    return events


def _byte_to_event(
    sample: RawI2CByteSample,
    packet_id: int,
    is_address: bool,
    *,
    nominal_period_s: float | None = None,
) -> RawI2CEvent:
    # The sample's first rising edge and ACK rising edge cover eight periods;
    # append one measured period to cover the complete 8-bit + ACK byte.
    ack = AckType.ACK if sample.ack == RawAck.ACK else AckType.NACK
    if is_address:
        address_7bit = sample.value >> 1
        event_type = RawEventType.ADDRESS
        data_byte = None
        direction = I2CDirection.READ if sample.value & 1 else I2CDirection.WRITE
    else:
        address_7bit = None
        event_type = RawEventType.DATA
        data_byte = sample.value
        direction = None

    start = sample.bit_timestamps_s[0]
    periods = _sample_periods(sample)
    period = median(periods) if periods else None
    duration_s = (sample.ack_timestamp_s - start) + period if period is not None else None
    bit_rate_khz = median(1.0 / period for period in periods) / 1000.0 if periods else None
    reference_period = nominal_period_s if nominal_period_s is not None else period
    extra_stretch_us = (
        max(0.0, max(periods) - reference_period) * 1_000_000.0
        if periods and reference_period is not None
        else 0.0
    )
    if extra_stretch_us < 1e-3:  # Ignore CSV floating-point noise below 1 ns.
        extra_stretch_us = 0.0
    return RawI2CEvent(
        timestamp=start,
        event_type=event_type,
        packet_id=packet_id,
        address_7bit=address_7bit,
        direction=direction,
        data_byte=data_byte,
        ack=ack,
        duration_s=duration_s,
        bit_rate_khz=bit_rate_khz,
        extra={
            "clock_stretch_us": extra_stretch_us,
            "timing_evidence": "raw_scl_period_delta",
        },
        timestamp_available=True,
    )


def _sample_periods(sample: RawI2CByteSample) -> list[float]:
    timestamps = (*sample.bit_timestamps_s, sample.ack_timestamp_s)
    periods = [second - first for first, second in pairwise(timestamps)]
    return [period for period in periods if period > 0]


def raw_decode_to_waveform(result: RawI2CDecodeResult) -> I2CWaveformData:
    """Build a measured digital-level waveform with protocol annotations."""
    from fw_diag_tool.i2c.waveform import I2CWaveformData, ProtocolAnnotation

    time_us = [transition.timestamp_s * 1_000_000.0 for transition in result.capture.transitions]
    scl = [transition.scl for transition in result.capture.transitions]
    sda = [transition.sda for transition in result.capture.transitions]
    annotations: list[ProtocolAnnotation] = []

    colors = {
        "START": "#00CC96",
        "ADDRESS": "#636EFA",
        "ACK": "#00FA9A",
        "NACK": "#EF553B",
        "DATA": "#AB63FA",
        "STOP": "#FF6692",
        "UNKNOWN": "#7F7F7F",
    }
    transition_times = [transition.timestamp_s for transition in result.capture.transitions]

    for condition in result.conditions:
        start = condition.timestamp_s * 1_000_000.0
        end = _next_transition_us(transition_times, condition.timestamp_s)
        label = (
            "Sr"
            if condition.kind == RawConditionKind.REPEATED_START
            else condition.kind.value.upper()
        )
        annotations.append(
            ProtocolAnnotation(
                start_time=start,
                end_time=end,
                label=label,
                annotation_type="START" if condition.kind != RawConditionKind.STOP else "STOP",
                color=colors["START" if condition.kind != RawConditionKind.STOP else "STOP"],
                details=f"Measured raw digital {condition.kind.value} condition.",
            )
        )

    for transaction in result.transactions:
        samples = (transaction.address_sample, *transaction.data_samples)
        for sample in samples:
            start = sample.bit_timestamps_s[0] * 1_000_000.0
            end = _next_transition_us(transition_times, sample.ack_timestamp_s)
            if sample.kind == RawByteKind.ADDRESS:
                direction = "R" if transaction.direction == RawI2CDirection.READ else "W"
                label = f"0x{transaction.address_7bit:02X} ({direction})"
                annotation_type = "ADDRESS"
            else:
                label = f"0x{sample.value:02X}"
                annotation_type = "DATA"
            annotations.append(
                ProtocolAnnotation(
                    start_time=start,
                    end_time=end,
                    label=label,
                    annotation_type=annotation_type,
                    color=colors[annotation_type],
                    details=f"Measured raw byte 0x{sample.value:02X} ({sample.ack_role.value}).",
                )
            )
            ack_start = sample.ack_timestamp_s * 1_000_000.0
            ack_end = _next_transition_us(transition_times, sample.ack_timestamp_s)
            ack_type = "ACK" if sample.ack == RawAck.ACK else "NACK"
            annotations.append(
                ProtocolAnnotation(
                    start_time=ack_start,
                    end_time=ack_end,
                    label=ack_type,
                    annotation_type=ack_type,
                    color=colors[ack_type],
                    details=f"Measured ACK role: {sample.ack_role.value}.",
                )
            )

    return I2CWaveformData(time_us=time_us, scl=scl, sda=sda, annotations=annotations)


def _next_transition_us(times: list[float], timestamp_s: float) -> float:
    for candidate in times:
        if candidate > timestamp_s:
            return candidate * 1_000_000.0
    return timestamp_s * 1_000_000.0


__all__ = ["raw_decode_to_events", "raw_decode_to_waveform"]
