from __future__ import annotations

import csv
import io

import pytest
from typer.testing import CliRunner

from fw_diag_tool.cli import app
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events, raw_decode_to_waveform
from fw_diag_tool.i2c.raw_capture import (
    RawAck,
    RawAckRole,
    RawCaptureColumnError,
    RawCaptureValidationError,
    RawConditionKind,
    RawI2CDecodeError,
    RawI2CDirection,
    analyze_raw_i2c_csv,
    decode_i2c_capture,
    parse_transition_csv,
)


class _CaptureBuilder:
    half_period_s = 5e-6

    def __init__(self) -> None:
        self.time_s = 0.0
        self.scl = 1
        self.sda = 1
        self.rows = [(self.time_s, self.scl, self.sda)]

    def _set_after(self, delay_s: float, *, scl: int | None = None, sda: int | None = None) -> None:
        self.time_s += delay_s
        next_scl = self.scl if scl is None else scl
        next_sda = self.sda if sda is None else sda
        if (next_scl, next_sda) != (self.scl, self.sda):
            self.scl = next_scl
            self.sda = next_sda
            self.rows.append((self.time_s, self.scl, self.sda))

    def start(self) -> None:
        self._set_after(2e-6, sda=0)

    def repeated_start(self) -> None:
        if self.sda != 1:
            self._set_after(1e-6, sda=1)
            remaining_low = self.half_period_s - 1e-6
        else:
            remaining_low = self.half_period_s
        self._set_after(remaining_low, scl=1)
        self._set_after(2e-6, sda=0)

    def stop(self) -> None:
        if self.sda != 0:
            self._set_after(1e-6, sda=0)
            remaining_low = self.half_period_s - 1e-6
        else:
            remaining_low = self.half_period_s
        self._set_after(remaining_low, scl=1)
        self._set_after(2e-6, sda=1)

    def clock(self, bit: int, *, extra_low_s: float = 0.0) -> None:
        if self.scl == 1:
            self._set_after(self.half_period_s, scl=0)
        if self.sda != bit:
            self._set_after(1e-6, sda=bit)
            remaining_low = self.half_period_s - 1e-6
        else:
            remaining_low = self.half_period_s
        self._set_after(remaining_low + extra_low_s, scl=1)
        self._set_after(self.half_period_s, scl=0)

    def byte(self, value: int, ack_bit: int, *, stretch_at: int | None = None) -> None:
        bits = [((value >> shift) & 1) for shift in range(7, -1, -1)] + [ack_bit]
        for index, bit in enumerate(bits):
            extra = 30e-6 if stretch_at == index else 0.0
            self.clock(bit, extra_low_s=extra)

    def csv(self, *, bom: bool = False, crlf: bool = False) -> str:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n" if crlf else "\n")
        writer.writerow(["Time [s]", "SCL", "SDA"])
        writer.writerows((f"{time_s:.12f}", scl, sda) for time_s, scl, sda in self.rows)
        return ("\ufeff" if bom else "") + output.getvalue()


def test_decodes_100_khz_write_and_measured_timing() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x33, 0)
    builder.stop()

    result = analyze_raw_i2c_csv(builder.csv(bom=True, crlf=True))

    assert len(result.transactions) == 1
    transaction = result.transactions[0]
    assert transaction.address_7bit == 0x50
    assert transaction.direction == RawI2CDirection.WRITE
    assert transaction.address_ack == RawAck.ACK
    assert transaction.data_bytes == (0x33,)
    assert transaction.data_samples[0].ack_role == RawAckRole.TARGET_DATA_RESPONSE
    assert result.timing.average_high_s == pytest.approx(5e-6)
    assert result.timing.average_low_s == pytest.approx(5e-6)
    assert result.timing.average_period_s == pytest.approx(10e-6)
    assert result.timing.average_frequency_hz == pytest.approx(100_000)
    assert result.timing.analog_rise_time_s is None
    assert result.timing.analog_fall_time_s is None


def test_combined_write_repeated_start_read_and_final_controller_nack() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x00, 0)
    builder.repeated_start()
    builder.byte(0xA1, 0)
    builder.byte(0xAB, 1)
    builder.stop()

    result = analyze_raw_i2c_csv(builder.csv())

    assert [condition.kind for condition in result.conditions] == [
        RawConditionKind.START,
        RawConditionKind.REPEATED_START,
        RawConditionKind.STOP,
    ]
    assert len(result.transactions) == 2
    write, read = result.transactions
    assert write.end_kind == RawConditionKind.REPEATED_START
    assert read.start_kind == RawConditionKind.REPEATED_START
    assert read.address_7bit == 0x50
    assert read.direction == RawI2CDirection.READ
    assert read.data_bytes == (0xAB,)
    assert read.data_samples[-1].ack == RawAck.NACK
    assert read.data_samples[-1].ack_role == RawAckRole.CONTROLLER_READ_TERMINATION
    assert read.controller_terminated_read is True


def test_clock_stretch_is_preserved_as_measured_low_time() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x55, 0, stretch_at=3)
    builder.stop()

    result = analyze_raw_i2c_csv(builder.csv())

    assert max(result.timing.low_durations_s) == pytest.approx(35e-6)
    assert max(result.timing.periods_s) == pytest.approx(40e-6)
    assert min(result.timing.frequencies_hz) == pytest.approx(25_000)


def test_explicit_columns_preserve_every_input_row() -> None:
    text = "t,clock,data\r\n0,1,1\r\n0.1,1,1\r\n0.2,1,0\r\n"

    capture = parse_transition_csv(
        text,
        time_column="t",
        scl_column="clock",
        sda_column="data",
    )

    assert len(capture.transitions) == 3
    assert capture.transitions[1].scl == 1
    assert capture.transitions[1].sda == 1
    assert capture.transitions[1].source_row == 3


def test_auto_detect_accepts_named_saleae_channels() -> None:
    text = "Time [s],Channel 0 (SCL),Channel 1 (SDA)\n0,1,1\n0.1,1,0\n"

    capture = parse_transition_csv(text)

    assert capture.columns.scl == "Channel 0 (SCL)"
    assert capture.columns.sda == "Channel 1 (SDA)"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Time [s],SCL,SDA\n0,1,1\n-1,1,0\n", "finite and nonnegative"),
        ("Time [s],SCL,SDA\n0,1,1\nnan,1,0\n", "finite and nonnegative"),
        ("Time [s],SCL,SDA\n1,1,1\n0,1,0\n", "strictly greater"),
        ("Time [s],SCL,SDA\n0,1,2\n", "only 0 or 1"),
        ("Time [s],SCL,SDA\n0,1,1\n0,1,0\n", "strictly greater"),
    ],
)
def test_rejects_invalid_transition_values(text: str, message: str) -> None:
    with pytest.raises(RawCaptureValidationError, match=message):
        parse_transition_csv(text)


def test_rejects_ambiguous_or_unlabeled_columns() -> None:
    ambiguous = "Time [s],SCL,SCL copy,SDA\n0,1,1,1\n"
    unlabeled = "Time [s],Channel 0,Channel 1\n0,1,1\n"

    with pytest.raises(RawCaptureColumnError, match="ambiguous SCL"):
        parse_transition_csv(ambiguous)
    with pytest.raises(RawCaptureColumnError, match="auto-detect SCL"):
        parse_transition_csv(unlabeled)


def test_rejects_incomplete_byte_when_edges_are_missing() -> None:
    builder = _CaptureBuilder()
    builder.start()
    for bit in (1, 0, 1, 0):
        builder.clock(bit)
    builder.stop()
    capture = parse_transition_csv(builder.csv())

    with pytest.raises(RawI2CDecodeError, match="incomplete byte"):
        decode_i2c_capture(capture)


def test_rejects_sda_change_on_sampling_edge() -> None:
    text = "Time [s],SCL,SDA\n0,1,1\n0.1,1,0\n0.2,0,0\n0.3,1,1\n"
    capture = parse_transition_csv(text)

    with pytest.raises(RawI2CDecodeError, match="sampling order is ambiguous"):
        decode_i2c_capture(capture)


def test_stop_setup_edge_is_not_mistaken_for_a_missing_ack_clock() -> None:
    builder = _CaptureBuilder()
    builder.start()
    for shift in range(7, -1, -1):
        builder.clock((0xA0 >> shift) & 1)
    builder.stop()

    with pytest.raises(RawI2CDecodeError, match="incomplete byte"):
        analyze_raw_i2c_csv(builder.csv())


def test_raw_capture_public_boundary_rejects_wrong_types_and_delimiters() -> None:
    with pytest.raises(RawCaptureValidationError, match="text or bytes"):
        parse_transition_csv(None)  # type: ignore[arg-type]
    with pytest.raises(RawCaptureValidationError, match="text or bytes"):
        parse_transition_csv(bytearray(b"Time,SCL,SDA\n0,1,1\n"))  # type: ignore[arg-type]
    with pytest.raises(RawCaptureValidationError, match="exactly one"):
        parse_transition_csv("Time,SCL,SDA\n0,1,1\n", delimiter="")


def test_raw_adapter_feeds_main_engine_without_losing_measured_evidence() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x33, 0)
    builder.stop()
    decoded = analyze_raw_i2c_csv(builder.csv())

    report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze(raw_decode_to_events(decoded))

    assert report.total_transactions == 1
    assert report.transactions[0].address_7bit == 0x50
    assert report.transactions[0].data_bytes == [0x33]
    assert report.timing_stats.avg_frequency_khz == pytest.approx(100.0)
    assert report.timing_stats.frequency_evidence == "source-provided"
    assert not report.data_quality_issues


def test_raw_adapter_keeps_nominal_scl_frequency_separate_from_stretch_duration() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x55, 0, stretch_at=3)
    builder.stop()
    decoded = analyze_raw_i2c_csv(builder.csv())

    report = I2CDiagnosticEngine().analyze(raw_decode_to_events(decoded))

    assert report.timing_stats.avg_frequency_khz == pytest.approx(100.0)
    assert report.timing_stats.bus_utilization_pct > 0
    assert report.timing_stats.max_clock_stretch_ms == pytest.approx(0.03, abs=1e-6)


def test_raw_adapter_preserves_address_clock_stretch_evidence() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0, stretch_at=8)
    builder.byte(0x33, 0)
    builder.stop()
    decoded = analyze_raw_i2c_csv(builder.csv())

    report = I2CDiagnosticEngine().analyze(raw_decode_to_events(decoded))

    assert report.timing_stats.clock_stretch_count == 1
    assert report.timing_stats.max_clock_stretch_ms == pytest.approx(0.03, abs=1e-6)


def test_raw_adapter_uses_per_transaction_nominal_clock_for_mixed_rates() -> None:
    slow = _CaptureBuilder()
    slow.start()
    slow.byte(0xA0, 0)
    slow.byte(0x33, 0)
    slow.stop()

    fast = _CaptureBuilder()
    fast.half_period_s = 1.25e-6
    fast.start()
    fast.byte(0xA0, 0)
    fast.byte(0x55, 0)
    fast.stop()

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Time [s]", "SCL", "SDA"])
    writer.writerows(slow.rows)
    writer.writerows((time_s + 0.01, scl, sda) for time_s, scl, sda in fast.rows)
    decoded = analyze_raw_i2c_csv(output.getvalue())

    report = I2CDiagnosticEngine().analyze(raw_decode_to_events(decoded))

    assert report.total_transactions == 2
    assert report.timing_stats.clock_stretch_count == 0
    assert not any(issue.code == "I2C_LONG_CLOCK_STRETCH" for issue in report.issues)


def test_raw_adapter_does_not_call_a_slow_nominal_bus_clock_stretching() -> None:
    builder = _CaptureBuilder()
    builder.half_period_s = 10e-6  # 50 kHz, deliberately below Standard-mode nominal.
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x33, 0)
    builder.stop()
    decoded = analyze_raw_i2c_csv(builder.csv())

    report = I2CDiagnosticEngine().analyze(raw_decode_to_events(decoded))

    assert report.timing_stats.avg_frequency_khz == pytest.approx(50.0)
    assert report.timing_stats.clock_stretch_count == 0
    assert not any(issue.code == "I2C_LONG_CLOCK_STRETCH" for issue in report.issues)


def test_raw_adapter_waveform_uses_captured_levels_and_protocol_overlay() -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA1, 0)
    builder.byte(0xAB, 1)
    builder.stop()
    decoded = analyze_raw_i2c_csv(builder.csv())

    waveform = raw_decode_to_waveform(decoded)

    assert len(waveform.time_us) == len(builder.rows)
    assert waveform.scl == [row[1] for row in builder.rows]
    assert waveform.sda == [row[2] for row in builder.rows]
    assert {annotation.annotation_type for annotation in waveform.annotations} >= {
        "START",
        "ADDRESS",
        "DATA",
        "ACK",
        "NACK",
        "STOP",
    }


def test_cli_raw_digital_mode_analyzes_file(tmp_path) -> None:
    builder = _CaptureBuilder()
    builder.start()
    builder.byte(0xA0, 0)
    builder.byte(0x33, 0)
    builder.stop()
    capture_path = tmp_path / "raw.csv"
    capture_path.write_text(builder.csv(), encoding="utf-8")

    result = CliRunner().invoke(app, ["i2c", "analyze", str(capture_path), "--raw-digital"])

    assert result.exit_code == 0, result.output
    assert "100.00 kHz" in result.output
