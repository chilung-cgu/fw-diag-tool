from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, replace
from enum import Enum
from itertools import pairwise


class RawCaptureError(ValueError):
    pass


class RawCaptureColumnError(RawCaptureError):
    pass


class RawCaptureValidationError(RawCaptureError):
    pass


class RawI2CDecodeError(RawCaptureError):
    pass


class RawI2CDirection(str, Enum):
    WRITE = "write"
    READ = "read"


class RawAck(str, Enum):
    ACK = "ack"
    NACK = "nack"


class RawAckRole(str, Enum):
    TARGET_ADDRESS_RESPONSE = "target_address_response"
    TARGET_DATA_RESPONSE = "target_data_response"
    CONTROLLER_DATA_RESPONSE = "controller_data_response"
    CONTROLLER_READ_TERMINATION = "controller_read_termination"


class RawConditionKind(str, Enum):
    START = "start"
    REPEATED_START = "repeated_start"
    STOP = "stop"


class RawByteKind(str, Enum):
    ADDRESS = "address"
    DATA = "data"


@dataclass(frozen=True)
class RawCaptureColumns:
    time: str
    scl: str
    sda: str


@dataclass(frozen=True)
class RawDigitalTransition:
    timestamp_s: float
    scl: int
    sda: int
    source_row: int


@dataclass(frozen=True)
class RawDigitalCapture:
    columns: RawCaptureColumns
    transitions: tuple[RawDigitalTransition, ...]


@dataclass(frozen=True)
class RawI2CCondition:
    timestamp_s: float
    kind: RawConditionKind


@dataclass(frozen=True)
class RawI2CByteSample:
    kind: RawByteKind
    value: int
    ack: RawAck
    ack_role: RawAckRole
    bit_timestamps_s: tuple[float, ...]
    ack_timestamp_s: float


@dataclass(frozen=True)
class RawI2CTransaction:
    start_time_s: float
    end_time_s: float
    start_kind: RawConditionKind
    end_kind: RawConditionKind
    address_7bit: int
    direction: RawI2CDirection
    address_sample: RawI2CByteSample
    data_samples: tuple[RawI2CByteSample, ...]
    controller_terminated_read: bool

    @property
    def address_ack(self) -> RawAck:
        return self.address_sample.ack

    @property
    def data_bytes(self) -> tuple[int, ...]:
        return tuple(sample.value for sample in self.data_samples)


@dataclass(frozen=True)
class RawSCLTiming:
    high_durations_s: tuple[float, ...]
    low_durations_s: tuple[float, ...]
    periods_s: tuple[float, ...]
    frequencies_hz: tuple[float, ...]
    analog_rise_time_s: float | None = None
    analog_fall_time_s: float | None = None

    @property
    def average_high_s(self) -> float | None:
        return _average(self.high_durations_s)

    @property
    def average_low_s(self) -> float | None:
        return _average(self.low_durations_s)

    @property
    def average_period_s(self) -> float | None:
        return _average(self.periods_s)

    @property
    def average_frequency_hz(self) -> float | None:
        period = self.average_period_s
        return None if period is None else 1.0 / period


@dataclass(frozen=True)
class RawI2CDecodeResult:
    capture: RawDigitalCapture
    conditions: tuple[RawI2CCondition, ...]
    transactions: tuple[RawI2CTransaction, ...]
    timing: RawSCLTiming


@dataclass
class _TransactionBuilder:
    start_time_s: float
    start_kind: RawConditionKind
    samples: list[tuple[float, int]]


_TIME_HEADERS = {
    "time",
    "time s",
    "time sec",
    "time seconds",
    "timestamp",
    "timestamp s",
    "timestamp sec",
    "timestamp seconds",
}


def parse_transition_csv(
    content: str | bytes,
    *,
    time_column: str | None = None,
    scl_column: str | None = None,
    sda_column: str | None = None,
    delimiter: str = ",",
) -> RawDigitalCapture:
    if not isinstance(content, (str, bytes)):
        raise RawCaptureValidationError("raw capture must be provided as UTF-8 text or bytes")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise RawCaptureValidationError("CSV delimiter must be exactly one character")
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RawCaptureValidationError("raw capture must be UTF-8 CSV") from exc
    else:
        text = content.lstrip("\ufeff")

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise RawCaptureValidationError("raw capture CSV is empty") from exc

    header = [name.strip().lstrip("\ufeff") for name in header]
    if not header or any(not name for name in header):
        raise RawCaptureColumnError("raw capture CSV contains an empty column name")
    if len(header) != len(set(header)):
        raise RawCaptureColumnError("raw capture CSV contains duplicate column names")

    columns = _resolve_columns(header, time_column, scl_column, sda_column)
    indexes = {name: header.index(name) for name in (columns.time, columns.scl, columns.sda)}
    transitions: list[RawDigitalTransition] = []

    for source_row, row in enumerate(reader, start=2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != len(header):
            raise RawCaptureValidationError(
                f"row {source_row} has {len(row)} fields; expected {len(header)}"
            )

        timestamp = _parse_timestamp(row[indexes[columns.time]], source_row)
        scl = _parse_digital(row[indexes[columns.scl]], columns.scl, source_row)
        sda = _parse_digital(row[indexes[columns.sda]], columns.sda, source_row)

        if transitions and timestamp <= transitions[-1].timestamp_s:
            raise RawCaptureValidationError(
                f"row {source_row} timestamp must be strictly greater than the previous row"
            )
        transitions.append(RawDigitalTransition(timestamp, scl, sda, source_row))

    if not transitions:
        raise RawCaptureValidationError("raw capture CSV contains no transition rows")
    return RawDigitalCapture(columns, tuple(transitions))


def decode_i2c_capture(capture: RawDigitalCapture) -> RawI2CDecodeResult:
    if len(capture.transitions) < 2:
        raise RawI2CDecodeError("raw capture needs at least two rows to contain an edge")

    conditions: list[RawI2CCondition] = []
    transactions: list[RawI2CTransaction] = []
    active: _TransactionBuilder | None = None

    for previous, current in pairwise(capture.transitions):
        scl_changed = previous.scl != current.scl
        sda_changed = previous.sda != current.sda

        if scl_changed and sda_changed:
            raise RawI2CDecodeError(
                f"row {current.source_row} changes SCL and SDA together; sampling order is ambiguous"
            )

        is_start = not scl_changed and previous.scl == 1 and previous.sda == 1 and current.sda == 0
        is_stop = not scl_changed and previous.scl == 1 and previous.sda == 0 and current.sda == 1

        if is_start:
            kind = RawConditionKind.REPEATED_START if active else RawConditionKind.START
            conditions.append(RawI2CCondition(current.timestamp_s, kind))
            if active:
                transactions.append(
                    _finish_transaction(
                        active,
                        current.timestamp_s,
                        RawConditionKind.REPEATED_START,
                    )
                )
            active = _TransactionBuilder(current.timestamp_s, kind, [])
            continue

        if is_stop:
            conditions.append(RawI2CCondition(current.timestamp_s, RawConditionKind.STOP))
            if active:
                transactions.append(
                    _finish_transaction(active, current.timestamp_s, RawConditionKind.STOP)
                )
                active = None
            continue

        if active and previous.scl == 0 and current.scl == 1:
            active.samples.append((current.timestamp_s, current.sda))

    if active:
        raise RawI2CDecodeError(
            "capture ended before a STOP or repeated START completed the transfer"
        )
    if not transactions:
        raise RawI2CDecodeError("capture contains no complete I2C transaction")

    timing = _calculate_timing(capture.transitions, transactions)
    return RawI2CDecodeResult(capture, tuple(conditions), tuple(transactions), timing)


def analyze_raw_i2c_csv(
    content: str | bytes,
    *,
    time_column: str | None = None,
    scl_column: str | None = None,
    sda_column: str | None = None,
    delimiter: str = ",",
) -> RawI2CDecodeResult:
    capture = parse_transition_csv(
        content,
        time_column=time_column,
        scl_column=scl_column,
        sda_column=sda_column,
        delimiter=delimiter,
    )
    return decode_i2c_capture(capture)


def _resolve_columns(
    header: list[str],
    time_column: str | None,
    scl_column: str | None,
    sda_column: str | None,
) -> RawCaptureColumns:
    explicit = (time_column, scl_column, sda_column)
    if any(name is not None for name in explicit):
        if not all(name is not None for name in explicit):
            raise RawCaptureColumnError("time, SCL, and SDA columns must all be specified together")
        selected = RawCaptureColumns(time_column or "", scl_column or "", sda_column or "")
        if len({selected.time, selected.scl, selected.sda}) != 3:
            raise RawCaptureColumnError("time, SCL, and SDA columns must be distinct")
        missing = [
            name for name in (selected.time, selected.scl, selected.sda) if name not in header
        ]
        if missing:
            raise RawCaptureColumnError(
                f"raw capture CSV is missing column(s): {', '.join(missing)}"
            )
        return selected

    time_candidates = [name for name in header if _normalize_header(name) in _TIME_HEADERS]
    scl_candidates = [name for name in header if _contains_signal_name(name, "scl")]
    sda_candidates = [name for name in header if _contains_signal_name(name, "sda")]
    return RawCaptureColumns(
        _single_candidate("time", time_candidates),
        _single_candidate("SCL", scl_candidates),
        _single_candidate("SDA", sda_candidates),
    )


def _single_candidate(label: str, candidates: list[str]) -> str:
    if not candidates:
        raise RawCaptureColumnError(
            f"could not auto-detect {label} column; specify all three column names explicitly"
        )
    if len(candidates) > 1:
        raise RawCaptureColumnError(
            f"ambiguous {label} columns: {', '.join(candidates)}; specify columns explicitly"
        )
    return candidates[0]


def _normalize_header(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _contains_signal_name(value: str, signal: str) -> bool:
    return signal in _normalize_header(value).split()


def _parse_timestamp(value: str, source_row: int) -> float:
    try:
        timestamp = float(value.strip())
    except ValueError as exc:
        raise RawCaptureValidationError(f"row {source_row} has an invalid timestamp") from exc
    if not math.isfinite(timestamp) or timestamp < 0:
        raise RawCaptureValidationError(
            f"row {source_row} timestamp must be finite and nonnegative"
        )
    return timestamp


def _parse_digital(value: str, column: str, source_row: int) -> int:
    normalized = value.strip()
    if normalized not in {"0", "1"}:
        raise RawCaptureValidationError(
            f"row {source_row} column {column!r} must contain only 0 or 1"
        )
    return int(normalized)


def _finish_transaction(
    builder: _TransactionBuilder,
    end_time_s: float,
    end_kind: RawConditionKind,
) -> RawI2CTransaction:
    samples = list(builder.samples)
    if len(samples) % 9 == 1:
        samples.pop()
    if not samples or len(samples) % 9:
        raise RawI2CDecodeError(
            f"transaction at {builder.start_time_s:g}s has incomplete byte or ACK clock edges"
        )

    groups = [samples[index : index + 9] for index in range(0, len(samples), 9)]
    address_octet = _bits_to_byte(groups[0][:8])
    if address_octet & 0xF8 == 0xF0:
        raise RawI2CDecodeError("10-bit I2C addresses are not supported by this decoder")

    direction = RawI2CDirection.READ if address_octet & 1 else RawI2CDirection.WRITE
    address_sample = _make_byte_sample(
        RawByteKind.ADDRESS,
        groups[0],
        RawAckRole.TARGET_ADDRESS_RESPONSE,
    )

    data_role = (
        RawAckRole.CONTROLLER_DATA_RESPONSE
        if direction == RawI2CDirection.READ
        else RawAckRole.TARGET_DATA_RESPONSE
    )
    data_samples = tuple(
        _make_byte_sample(RawByteKind.DATA, group, data_role) for group in groups[1:]
    )
    controller_terminated = bool(
        direction == RawI2CDirection.READ and data_samples and data_samples[-1].ack == RawAck.NACK
    )
    if controller_terminated:
        data_samples = (
            *data_samples[:-1],
            replace(data_samples[-1], ack_role=RawAckRole.CONTROLLER_READ_TERMINATION),
        )

    return RawI2CTransaction(
        start_time_s=builder.start_time_s,
        end_time_s=end_time_s,
        start_kind=builder.start_kind,
        end_kind=end_kind,
        address_7bit=address_octet >> 1,
        direction=direction,
        address_sample=address_sample,
        data_samples=data_samples,
        controller_terminated_read=controller_terminated,
    )


def _bits_to_byte(samples: list[tuple[float, int]]) -> int:
    value = 0
    for _, bit in samples:
        value = (value << 1) | bit
    return value


def _make_byte_sample(
    kind: RawByteKind,
    group: list[tuple[float, int]],
    ack_role: RawAckRole,
) -> RawI2CByteSample:
    ack = RawAck.ACK if group[8][1] == 0 else RawAck.NACK
    return RawI2CByteSample(
        kind=kind,
        value=_bits_to_byte(group[:8]),
        ack=ack,
        ack_role=ack_role,
        bit_timestamps_s=tuple(timestamp for timestamp, _ in group[:8]),
        ack_timestamp_s=group[8][0],
    )


def _calculate_timing(
    transitions: tuple[RawDigitalTransition, ...],
    transactions: list[RawI2CTransaction],
) -> RawSCLTiming:
    sampled_rising_edges = {
        timestamp
        for transaction in transactions
        for sample in (transaction.address_sample, *transaction.data_samples)
        for timestamp in (*sample.bit_timestamps_s, sample.ack_timestamp_s)
    }
    scl_edges = [
        (current.timestamp_s, previous.scl, current.scl)
        for previous, current in pairwise(transitions)
        if previous.scl != current.scl
    ]
    high_durations: list[float] = []
    low_durations: list[float] = []

    for previous_edge, current_edge in pairwise(scl_edges):
        previous_time, _, previous_level = previous_edge
        current_time, _, current_level = current_edge
        if previous_level == 0 and current_level == 1 and current_time in sampled_rising_edges:
            low_durations.append(current_time - previous_time)
        elif previous_level == 1 and current_level == 0 and previous_time in sampled_rising_edges:
            high_durations.append(current_time - previous_time)

    periods: list[float] = []
    for transaction in transactions:
        periods.extend(
            second - first for first, second in pairwise(_transaction_sample_times(transaction))
        )
    return RawSCLTiming(
        high_durations_s=tuple(high_durations),
        low_durations_s=tuple(low_durations),
        periods_s=tuple(periods),
        frequencies_hz=tuple(1.0 / period for period in periods),
    )


def _transaction_sample_times(transaction: RawI2CTransaction) -> tuple[float, ...]:
    return tuple(
        timestamp
        for sample in (transaction.address_sample, *transaction.data_samples)
        for timestamp in (*sample.bit_timestamps_s, sample.ack_timestamp_s)
    )


def _average(values: tuple[float, ...]) -> float | None:
    return sum(values) / len(values) if values else None
