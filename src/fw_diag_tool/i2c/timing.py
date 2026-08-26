"""I2C / SMBus Bus Clock Timing, Jitter, and Clock Stretching Analyzer.

Computes SCL clock frequency, jitter variance, identifies speed modes
(Standard 100kHz, Fast 400kHz, Fast-Plus 1MHz), detects Clock Stretching
and SMBus 25ms timeout violations, and measures inter-byte/transaction latency.
"""

from __future__ import annotations

import math

from fw_diag_tool.i2c.models import I2CSpeedMode, I2CTransaction, TimingStatistics

MIN_FREQUENCY_KHZ = 5.0
MAX_FREQUENCY_KHZ = 5000.0


def classify_speed_mode(avg_freq_khz: float) -> I2CSpeedMode:
    """Classify nominal I2C speed mode based on observed average frequency."""
    if isinstance(avg_freq_khz, bool) or not isinstance(avg_freq_khz, (int, float)):
        raise TypeError("avg_freq_khz must be a finite numeric value")
    if not math.isfinite(float(avg_freq_khz)):
        raise ValueError("avg_freq_khz must be a finite numeric value")
    if avg_freq_khz <= 0:
        return I2CSpeedMode.UNKNOWN
    elif avg_freq_khz <= 125.0:
        return I2CSpeedMode.STANDARD_100K
    elif avg_freq_khz <= 450.0:
        return I2CSpeedMode.FAST_400K
    elif avg_freq_khz <= 1100.0:
        return I2CSpeedMode.FAST_PLUS_1M
    elif avg_freq_khz <= 4000.0:
        return I2CSpeedMode.HIGH_SPEED_3M4
    return I2CSpeedMode.UNKNOWN


def frequency_samples_khz(transactions: list[I2CTransaction]) -> list[float]:
    """Return source-backed, sanity-bounded byte frequency samples.

    Both timing statistics and the frequency chart use this function so an
    out-of-range source value cannot appear in only one view.
    """

    if not isinstance(transactions, list):
        raise TypeError("transactions must be a list")
    samples: list[float] = []
    for tx in transactions:
        if not isinstance(tx, I2CTransaction):
            raise TypeError("transactions must contain I2CTransaction objects")
        for packet in tx.byte_packets:
            if packet.bit_rate_khz is not None and (
                isinstance(packet.bit_rate_khz, bool)
                or not isinstance(packet.bit_rate_khz, (int, float))
                or not math.isfinite(float(packet.bit_rate_khz))
                or packet.bit_rate_khz <= 0
            ):
                raise ValueError("bit_rate_khz must be a positive finite number")
            if packet.duration_s is not None and (
                isinstance(packet.duration_s, bool)
                or not isinstance(packet.duration_s, (int, float))
                or not math.isfinite(float(packet.duration_s))
                or packet.duration_s <= 0
            ):
                raise ValueError("duration_s must be a positive finite number")

            frequency: float | None = None
            if packet.bit_rate_khz is not None:
                frequency = float(packet.bit_rate_khz)
            elif packet.duration_s is not None:
                frequency = (9.0 / packet.duration_s) / 1000.0
            if frequency is not None and MIN_FREQUENCY_KHZ <= frequency <= MAX_FREQUENCY_KHZ:
                samples.append(frequency)
    return samples


def analyze_timing_statistics(
    transactions: list[I2CTransaction], total_trace_duration_s: float
) -> TimingStatistics:
    """Compute comprehensive timing, clock frequency, jitter, and stretching statistics.

    Args:
        transactions: List of parsed I2CTransactions.
        total_trace_duration_s: Total time duration of trace from first event to last event.
    """
    if (
        isinstance(total_trace_duration_s, bool)
        or not isinstance(total_trace_duration_s, (int, float))
        or not math.isfinite(float(total_trace_duration_s))
        or total_trace_duration_s < 0
    ):
        raise ValueError("total_trace_duration_s must be finite and non-negative")
    if not isinstance(transactions, list):
        raise TypeError("transactions must be a list")
    if any(not isinstance(tx, I2CTransaction) for tx in transactions):
        raise TypeError("transactions must contain I2CTransaction objects")

    stats = TimingStatistics()
    if not transactions:
        return stats

    all_frequencies_khz = frequency_samples_khz(transactions)
    all_inter_byte_delays_us: list[float] = []
    all_clock_stretches_ms: list[float] = []
    all_inter_tx_delays_ms: list[float] = []
    total_active_time_s = 0.0
    active_duration_evidence = False

    prev_tx_end_time: float | None = None

    for tx in transactions:
        # Inter-transaction delay
        if tx.timestamp_available:
            if prev_tx_end_time is not None and tx.start_time >= prev_tx_end_time:
                inter_tx_ms = (tx.start_time - prev_tx_end_time) * 1000.0
                all_inter_tx_delays_ms.append(inter_tx_ms)
            prev_tx_end_time = tx.end_time
        else:
            # Do not derive a delay from the parser's internal zero placeholder.
            prev_tx_end_time = None

        # Inter-byte delays inside transaction
        for delay_us in tx.inter_byte_delays_us:
            if (
                isinstance(delay_us, bool)
                or not isinstance(delay_us, (int, float))
                or not math.isfinite(float(delay_us))
                or delay_us < 0
            ):
                raise ValueError("inter-byte delays must be finite and non-negative")
            if delay_us > 0:
                all_inter_byte_delays_us.append(delay_us)

        # Clock stretch events
        for stretch in tx.clock_stretching_events:
            if not isinstance(stretch, dict):
                raise TypeError("clock stretching events must be mappings")
            dur_ms = stretch.get("duration_ms", 0.0)
            if (
                isinstance(dur_ms, bool)
                or not isinstance(dur_ms, (int, float))
                or not math.isfinite(float(dur_ms))
                or dur_ms < 0
            ):
                raise ValueError("clock stretch duration must be finite and non-negative")
            if dur_ms > 0:
                all_clock_stretches_ms.append(dur_ms)

        # Source-provided active transfer duration is distinct from a bitrate
        # estimate.  Utilization remains unavailable when only a bitrate is
        # present and no duration was captured.
        for pkt in tx.byte_packets:
            if pkt.duration_s is not None and pkt.duration_s > 0:
                active_duration_evidence = True
                total_active_time_s += pkt.duration_s

    # Compute frequency stats
    if all_frequencies_khz:
        avg_f = sum(all_frequencies_khz) / len(all_frequencies_khz)
        min_f = min(all_frequencies_khz)
        max_f = max(all_frequencies_khz)
        stats.avg_frequency_khz = avg_f
        stats.min_frequency_khz = min_f
        stats.max_frequency_khz = max_f
        stats.speed_mode = classify_speed_mode(avg_f)
        stats.frequency_sample_count = len(all_frequencies_khz)
        stats.frequency_evidence = "source-provided"
        if avg_f > 0:
            stats.frequency_spread_pct = ((max_f - min_f) / avg_f) * 100.0
            stats.frequency_jitter_pct = stats.frequency_spread_pct

    # Compute clock stretch stats
    stats.clock_stretch_count = len(all_clock_stretches_ms)
    if all_clock_stretches_ms:
        stats.max_clock_stretch_ms = max(all_clock_stretches_ms)
        stats.avg_clock_stretch_ms = sum(all_clock_stretches_ms) / len(all_clock_stretches_ms)

    # Compute inter-byte delay stats
    if all_inter_byte_delays_us:
        stats.avg_inter_byte_delay_us = sum(all_inter_byte_delays_us) / len(
            all_inter_byte_delays_us
        )
        stats.max_inter_byte_delay_us = max(all_inter_byte_delays_us)

    # Compute inter-transaction delay stats
    if all_inter_tx_delays_ms:
        stats.avg_inter_transaction_delay_ms = sum(all_inter_tx_delays_ms) / len(
            all_inter_tx_delays_ms
        )
        stats.max_inter_transaction_delay_ms = max(all_inter_tx_delays_ms)

    # Compute bus utilization
    if total_trace_duration_s > 0 and active_duration_evidence:
        stats.bus_utilization_pct = min(
            100.0, (total_active_time_s / total_trace_duration_s) * 100.0
        )
        stats.bus_utilization_evidence = "source-provided"

    return stats


__all__ = [
    "MAX_FREQUENCY_KHZ",
    "MIN_FREQUENCY_KHZ",
    "analyze_timing_statistics",
    "classify_speed_mode",
    "frequency_samples_khz",
]
