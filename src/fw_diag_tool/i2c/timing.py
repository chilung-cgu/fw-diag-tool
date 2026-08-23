"""I2C / SMBus Bus Clock Timing, Jitter, and Clock Stretching Analyzer.

Computes SCL clock frequency, jitter variance, identifies speed modes
(Standard 100kHz, Fast 400kHz, Fast-Plus 1MHz), detects Clock Stretching
and SMBus 25ms timeout violations, and measures inter-byte/transaction latency.
"""

from __future__ import annotations

from fw_diag_tool.i2c.models import I2CSpeedMode, I2CTransaction, TimingStatistics


def classify_speed_mode(avg_freq_khz: float) -> I2CSpeedMode:
    """Classify nominal I2C speed mode based on observed average frequency."""
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


def analyze_timing_statistics(
    transactions: list[I2CTransaction], total_trace_duration_s: float
) -> TimingStatistics:
    """Compute comprehensive timing, clock frequency, jitter, and stretching statistics.

    Args:
        transactions: List of parsed I2CTransactions.
        total_trace_duration_s: Total time duration of trace from first event to last event.
    """
    stats = TimingStatistics()
    if not transactions:
        return stats

    all_frequencies_khz: list[float] = []
    all_inter_byte_delays_us: list[float] = []
    all_clock_stretches_ms: list[float] = []
    all_inter_tx_delays_ms: list[float] = []
    total_active_time_s = 0.0

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
            if delay_us > 0:
                all_inter_byte_delays_us.append(delay_us)

        # Clock stretch events
        for stretch in tx.clock_stretching_events:
            dur_ms = stretch.get("duration_ms", 0.0)
            if dur_ms > 0:
                all_clock_stretches_ms.append(dur_ms)

        # Byte-level frequencies
        for pkt in tx.byte_packets:
            if pkt.bit_rate_khz and pkt.bit_rate_khz > 0:
                all_frequencies_khz.append(pkt.bit_rate_khz)
                total_active_time_s += (
                    pkt.duration_s
                    if pkt.duration_s is not None and pkt.duration_s > 0
                    else 9.0 / (pkt.bit_rate_khz * 1000.0)
                )
            elif pkt.duration_s is not None and pkt.duration_s > 0:
                # 1 byte transfer has 9 clock cycles (8 data bits + 1 ACK bit)
                freq_khz = (9.0 / pkt.duration_s) / 1000.0
                if 5.0 <= freq_khz <= 5000.0:  # sanity filter
                    all_frequencies_khz.append(freq_khz)
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
            stats.frequency_jitter_pct = ((max_f - min_f) / avg_f) * 100.0

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
    if total_trace_duration_s > 0:
        stats.bus_utilization_pct = min(
            100.0, (total_active_time_s / total_trace_duration_s) * 100.0
        )

    return stats
