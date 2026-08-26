"""I2C Protocol Data Parser supporting Saleae Logic 2, Generic CSV, and Raw Traces.

Parses logic analyzer CSV exports, text traces, and raw Python structures into
normalized RawI2CEvent sequences ready for transaction grouping and semantic analysis.
"""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Any, TextIO

from fw_diag_tool.errors import InputFormatError, ResourceLimitError
from fw_diag_tool.i2c.models import (
    AckType,
    I2CDirection,
    RawEventType,
    RawI2CEvent,
)
from fw_diag_tool.limits import AnalysisLimits, coerce_limits


def _iter_csv_rows(reader: Any) -> Any:
    try:
        while True:
            try:
                yield next(reader)
            except StopIteration:
                return
    except csv.Error as exc:
        raise InputFormatError(f"invalid CSV input: {exc}") from exc


def _check_text_size(text: str, limits: AnalysisLimits, *, label: str = "text input") -> None:
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise InputFormatError(f"{label} must be valid UTF-8 text") from exc
    if size > limits.max_upload_bytes:
        raise ResourceLimitError(
            f"{label} exceeds the {limits.max_upload_bytes}-byte safety limit",
            resource=label,
            limit=limits.max_upload_bytes,
            observed=size,
        )


def parse_hex_or_int(val: Any) -> int | None:
    """Parse integer from hex string (0x50, 50h), decimal ('80'), or numeric type."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if not math.isfinite(val) or not val.is_integer():
            return None
        return int(val)

    s = str(val).strip().strip("'").strip('"')
    if not s or s.lower() in ("none", "null", "n/a", "-"):
        return None

    # Hex formats: 0x50, 0X50, 50h, #50
    if s.startswith(("0x", "0X")):
        try:
            return int(s, 16)
        except ValueError:
            pass
    if s.startswith("#") and len(s) > 1:
        try:
            return int(s[1:], 16)
        except ValueError:
            pass
    if s.endswith(("h", "H")) and len(s) > 1:
        try:
            return int(s[:-1], 16)
        except ValueError:
            pass

    # Try base 10 then base 16
    try:
        return int(s, 10)
    except ValueError:
        try:
            return int(s, 16)
        except ValueError:
            return None


def parse_direction(val: Any) -> I2CDirection | None:
    """Parse Read/Write direction from string or bit representation."""
    if val is None:
        return None
    s = str(val).strip().strip("'").strip('"').upper()
    if s in ("READ", "R", "RD", "1", "TRUE"):
        return I2CDirection.READ
    elif s in ("WRITE", "W", "WR", "0", "FALSE"):
        return I2CDirection.WRITE
    return None


def parse_ack(val: Any) -> AckType:
    """Parse ACK/NACK status."""
    if val is None:
        return AckType.NONE
    s = str(val).strip().strip("'").strip('"').upper()
    if s in ("NAK", "NACK", "1", "FALSE", "NO", "N"):
        return AckType.NACK
    elif s in ("ACK", "0", "TRUE", "YES", "A", "Y"):
        return AckType.ACK
    return AckType.NONE


def _positive_finite_float(value: Any) -> float | None:
    """Return a positive finite float, treating malformed values as unavailable."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _nonnegative_finite_float(value: Any) -> float | None:
    """Return a finite nonnegative float, treating malformed values as unavailable."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


class I2CParser:
    """Universal I2C trace parser."""

    @classmethod
    def parse_csv_stream(
        cls, f: TextIO, *, limits: AnalysisLimits | None = None
    ) -> list[RawI2CEvent]:
        """Parse CSV data from an open text stream (e.g. Saleae Logic 2 or Generic CSV)."""
        limits = coerce_limits(limits)
        if not hasattr(f, "read") or not hasattr(f, "seek"):
            raise TypeError("CSV input must be a seekable text stream")
        try:
            current_position = f.tell()
            f.seek(0, 2)
            stream_size = f.tell()
            f.seek(current_position)
        except (OSError, ValueError):
            stream_size = None
        if stream_size is not None and stream_size > limits.max_upload_bytes:
            raise ResourceLimitError(
                f"CSV input exceeds the {limits.max_upload_bytes}-byte safety limit",
                resource="CSV input",
                limit=limits.max_upload_bytes,
                observed=stream_size,
            )
        events: list[RawI2CEvent] = []
        record_count = 0

        # Read header and detect delimiter
        sample = f.read(4096)
        f.seek(0)
        delimiter = ","
        if ";" in sample and sample.count(";") > sample.count(","):
            delimiter = ";"
        elif "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"

        reader = csv.reader(f, delimiter=delimiter)
        try:
            header = next(reader, None)
        except (csv.Error, StopIteration) as exc:
            raise InputFormatError(f"invalid CSV input: {exc}") from exc
        if not header:
            return []
        # Logic 2 and spreadsheet exports may include a UTF-8 BOM on the
        # first header cell.  Remove it before alias matching; otherwise the
        # timestamp column becomes invisible and every row loses timing
        # evidence even though the CSV is otherwise valid.
        header[0] = header[0].lstrip("\ufeff")

        # Normalize headers
        col_map: dict[str, int] = {}
        for idx, col in enumerate(header):
            c = col.strip().lower().replace(" ", "_").replace("[s]", "").replace('"', "").strip("_")
            if c in col_map:
                raise InputFormatError(
                    f"duplicate CSV column name after normalization: {col!r}"
                )
            col_map[c] = idx

        def first_column(*names: str) -> int | None:
            return next((col_map[name] for name in names if name in col_map), None)

        # Map common column aliases
        time_idx = first_column("time", "timestamp", "start_time")
        packet_id_idx = first_column("packet_id", "packet", "transaction_id")
        type_idx = first_column("type", "event", "event_type")
        addr_idx = first_column("address", "addr", "slave_address")
        data_idx = first_column("data", "byte", "value")
        rw_idx = first_column("read/write", "rw", "read_write", "r/w", "direction")
        ack_idx = first_column("ack/nak", "ack", "ack_nak", "ack/nack")
        duration_idx = first_column("duration", "duration_s")
        bitrate_idx = first_column("bit_rate", "bitrate", "frequency")
        # A whole-byte Duration is sufficient for a frequency estimate but
        # cannot identify which portion of the byte held SCL low. Accept a
        # separate source column when an analyzer/export explicitly provides
        # measured clock-stretch duration.
        clock_stretch_idx = first_column(
            "clock_stretch",
            "clock_stretch_s",
            "scl_low_duration",
            "scl_low_duration_s",
            "stretch_duration",
            "stretch_duration_s",
        )

        for row in _iter_csv_rows(reader):
            if not row or not any(cell.strip() for cell in row):
                continue
            record_count += 1
            if record_count > limits.max_records:
                raise ResourceLimitError(
                    f"CSV input exceeds the {limits.max_records}-record safety limit",
                    resource="records",
                    limit=limits.max_records,
                    observed=record_count,
                )

            source_error: str | None = None
            structural_source_error = len(row) != len(header)
            if len(row) != len(header):
                source_error = f"row has {len(row)} fields but header declares {len(header)} fields"

            timestamp = 0.0
            timestamp_available = False
            try:
                if time_idx is None:
                    raise IndexError
                t_str = row[time_idx].strip().strip("'").strip('"')
                timestamp = float(t_str)
                timestamp_available = True
                timestamp_available = math.isfinite(timestamp) and timestamp >= 0
                if not timestamp_available:
                    timestamp = 0.0
            except (IndexError, TypeError, ValueError):
                if time_idx is not None and time_idx < len(row) and row[time_idx].strip():
                    source_error = source_error or "timestamp token is not finite and non-negative"

            raw_type_str = (
                row[type_idx].strip().upper()
                if type_idx is not None and type_idx < len(row)
                else ""
            )
            type_token = raw_type_str.replace(" ", "_").replace("-", "_")
            allowed_type_tokens = {
                "START",
                "REPEATED_START",
                "SR",
                "STOP",
                "ADDRESS",
                "DATA",
                "BUS_HANG",
                "UNKNOWN",
                "READ",
                "WRITE",
            }
            if type_idx is not None and raw_type_str and type_token not in allowed_type_tokens:
                source_error = f"event type token {raw_type_str!r} is not recognized"
                structural_source_error = True

            packet_id = None
            if packet_id_idx is not None and packet_id_idx < len(row):
                packet_cell = row[packet_id_idx].strip()
                if packet_cell and packet_cell.lower() not in ("none", "null", "n/a", "-"):
                    parsed_packet_id = parse_hex_or_int(packet_cell)
                    if parsed_packet_id is None or parsed_packet_id < 0:
                        source_error = source_error or (
                            f"packet id token {packet_cell!r} is not a non-negative integer"
                        )
                        structural_source_error = True
                    else:
                        packet_id = parsed_packet_id

            # Parse address
            raw_addr_cell = (
                row[addr_idx].strip().strip("'").strip('"')
                if addr_idx is not None and addr_idx < len(row)
                else ""
            )
            raw_addr = (
                parse_hex_or_int(row[addr_idx])
                if addr_idx is not None and addr_idx < len(row)
                else None
            )
            if raw_addr is None and raw_addr_cell.lower() not in ("", "-", "none", "null", "n/a"):
                source_error = f"address token {raw_addr_cell!r} is not a numeric byte"
                structural_source_error = True
            if raw_addr is not None and not 0 <= raw_addr <= 0xFF:
                source_error = (
                    f"address {raw_addr} is outside the supported 7-bit/8-bit range 0..0xFF"
                )
                structural_source_error = True
                raw_addr = None

            # Parse direction
            raw_rw = (
                parse_direction(row[rw_idx]) if rw_idx is not None and rw_idx < len(row) else None
            )
            if rw_idx is not None and rw_idx < len(row):
                rw_cell = row[rw_idx].strip()
                if (
                    rw_cell
                    and rw_cell.lower() not in ("none", "null", "n/a", "-")
                    and raw_rw is None
                ):
                    source_error = source_error or f"direction token {rw_cell!r} is not READ/WRITE"
                    structural_source_error = True

            # If direction not separate column, check if raw_type_str or address embeds it
            if raw_rw is None:
                if "READ" in raw_type_str:
                    raw_rw = I2CDirection.READ
                elif "WRITE" in raw_type_str:
                    raw_rw = I2CDirection.WRITE

            # 7-bit vs 8-bit Address Normalization
            addr_7bit = None
            if raw_addr is not None:
                if raw_addr > 0x7F:
                    # Likely 8-bit address: extract top 7 bits and R/W bit if
                    # direction is missing.  If both forms are present they
                    # must agree; silently preferring the explicit column can
                    # turn 0xA1, WRITE into a different bus transaction.
                    implied_rw = I2CDirection.READ if (raw_addr & 0x01) else I2CDirection.WRITE
                    if raw_rw is not None and raw_rw != implied_rw:
                        source_error = (
                            f"8-bit address {raw_addr:#04x} conflicts with explicit direction "
                            f"{raw_rw.value}; implied direction is {implied_rw.value}"
                        )
                        structural_source_error = True
                    addr_7bit = (raw_addr >> 1) & 0x7F
                    if raw_rw is None:
                        raw_rw = implied_rw
                else:
                    addr_7bit = raw_addr

            # Parse data (support single byte or multi-byte space/comma separated)
            raw_data_cell = (
                str(row[data_idx]).strip() if data_idx is not None and data_idx < len(row) else ""
            )
            raw_data_tokens: list[int] = []
            if raw_data_cell and raw_data_cell.lower() not in ("-", "none", "null", ""):
                parsed_data_tokens = [
                    parse_hex_or_int(tok)
                    for tok in re.split(r"[ ,;]+", raw_data_cell)
                    if tok.strip()
                ]
                if any(token is None for token in parsed_data_tokens):
                    source_error = source_error or "one or more data tokens are not numeric bytes"
                    structural_source_error = True
                if any(
                    token is not None and not 0 <= token <= 0xFF for token in parsed_data_tokens
                ):
                    invalid = next(
                        token
                        for token in parsed_data_tokens
                        if token is not None and not 0 <= token <= 0xFF
                    )
                    source_error = source_error or f"data byte {invalid} is outside 0..0xFF"
                    structural_source_error = True
                raw_data_tokens = [
                    token
                    for token in parsed_data_tokens
                    if token is not None and 0 <= token <= 0xFF
                ]
                if structural_source_error:
                    # Do not allow a malformed combined row to become a plausible
                    # partial transaction. Preserve the row as quality evidence.
                    raw_data_tokens = []
            raw_data = raw_data_tokens[0] if len(raw_data_tokens) == 1 else None

            if structural_source_error:
                # Do not let a row with a malformed schema or address/data field
                # seed a plausible transaction. Keep the row below as UNKNOWN
                # evidence so the report can count the source failure.
                addr_7bit = None
                raw_rw = None
                raw_data_tokens = []
                raw_data = None

            # Parse ACK
            ack_val = (
                parse_ack(row[ack_idx])
                if ack_idx is not None and ack_idx < len(row)
                else AckType.NONE
            )
            if ack_idx is not None and ack_idx < len(row):
                ack_cell = row[ack_idx].strip()
                if (
                    ack_cell
                    and ack_cell.lower() not in ("none", "null", "n/a", "-")
                    and ack_val == AckType.NONE
                ):
                    source_error = source_error or f"ACK token {ack_cell!r} is not ACK/NACK"

            # Duration & Bitrate
            dur = (
                _positive_finite_float(row[duration_idx].strip())
                if duration_idx is not None and duration_idx < len(row)
                else None
            )
            if duration_idx is not None and duration_idx < len(row):
                duration_cell = row[duration_idx].strip()
                if duration_cell and _positive_finite_float(duration_cell) is None:
                    source_error = source_error or "duration is not a positive finite number"
            bitrate = None
            if bitrate_idx is not None and bitrate_idx < len(row):
                b_val = _positive_finite_float(row[bitrate_idx].strip())
                if b_val is not None:
                    bitrate = b_val / 1000.0 if b_val > 10000 else b_val
                elif row[bitrate_idx].strip():
                    source_error = source_error or "bitrate is not a positive finite number"

            clock_stretch_s = None
            if clock_stretch_idx is not None and clock_stretch_idx < len(row):
                stretch_cell = row[clock_stretch_idx].strip()
                if stretch_cell:
                    clock_stretch_s = _positive_finite_float(stretch_cell)
                    if clock_stretch_s is None:
                        source_error = source_error or (
                            "clock stretch duration is not a positive finite number"
                        )

            timing_extra: dict[str, Any] = {}
            if clock_stretch_s is not None:
                timing_extra.update(
                    {
                        "clock_stretch_us": clock_stretch_s * 1_000_000.0,
                        "timing_evidence": "source_clock_stretch",
                    }
                )

            # Determine event type
            if type_token == "START":
                ev_type = RawEventType.START
            elif type_token in ("REPEATED_START", "SR"):
                ev_type = RawEventType.REPEATED_START
            elif type_token == "STOP":
                ev_type = RawEventType.STOP
            elif type_token == "ADDRESS":
                ev_type = RawEventType.ADDRESS
            elif type_token == "DATA":
                ev_type = RawEventType.DATA
            elif type_token == "BUS_HANG":
                ev_type = RawEventType.BUS_HANG
            elif type_token == "UNKNOWN":
                ev_type = RawEventType.UNKNOWN
            elif addr_7bit is not None and raw_data is None:
                ev_type = RawEventType.ADDRESS
            elif raw_data is not None:
                ev_type = RawEventType.DATA
            else:
                ev_type = RawEventType.UNKNOWN

            if raw_data_tokens and addr_7bit is not None:
                # Analyzer summary rows can combine address and one or more data bytes.
                # A row that carries both an address and data does not identify
                # which byte owns its single ACK/NACK, even when there is only
                # one data token.  Preserve the bytes, but keep ACK attribution
                # unknown and let the engine withhold accepted-payload semantics.
                aggregate_ack = ack_val != AckType.NONE
                # Attribution ambiguity is a data-evidence limitation, not a
                # malformed CSV field.  Keep it in the dedicated aggregate
                # marker so status remains ``ACK UNKNOWN`` rather than the
                # stronger ``EVIDENCE INCOMPLETE``/parse-error classification.
                aggregate_extra: dict[str, Any] = (
                    {
                        "aggregate_ack": True,
                        "aggregate_ack_value": ack_val.value,
                    }
                    if aggregate_ack
                    else {}
                )
                if source_error:
                    aggregate_extra["source_error"] = source_error
                aggregate_extra.update(timing_extra)
                if dur is not None:
                    # A summary row has one timing value for address plus all
                    # payload bytes; retain the fact that it could not be
                    # attributed to a single byte without turning it into a
                    # frequency sample.
                    aggregate_extra["aggregate_duration_unattributable"] = True
                    aggregate_extra["aggregate_duration_s"] = dur
                events.append(
                    RawI2CEvent(
                        timestamp=timestamp,
                        event_type=RawEventType.ADDRESS,
                        timestamp_available=timestamp_available,
                        packet_id=packet_id,
                        address_7bit=addr_7bit,
                        direction=raw_rw,
                        data_byte=None,
                        # A combined analyzer row does not identify whether its
                        # ACK/NACK belongs to the address or the final data byte.
                        # Keep address evidence unknown instead of inventing ACK.
                        ack=AckType.NONE,
                        duration_s=None,
                        bit_rate_khz=bitrate,
                        extra=aggregate_extra,
                        raw_text=",".join(row),
                    )
                )
                for b_idx, b_val in enumerate(raw_data_tokens):
                    data_extra = aggregate_extra.copy()
                    data_extra.pop("aggregate_duration_unattributable", None)
                    data_extra.pop("aggregate_duration_s", None)
                    events.append(
                        RawI2CEvent(
                            timestamp=timestamp,
                            event_type=RawEventType.DATA,
                            timestamp_available=timestamp_available,
                            packet_id=packet_id,
                            address_7bit=addr_7bit,
                            direction=raw_rw,
                            data_byte=b_val,
                            # A multi-byte summary row provides at most one
                            # aggregate ACK/NACK.  Preserve it as unknown for
                            # every byte rather than inventing ACKs for the
                            # middle bytes (or guessing which byte was NACKed).
                            ack=AckType.NONE if aggregate_ack else (
                                ack_val if b_idx == len(raw_data_tokens) - 1
                                else (AckType.ACK if ack_val != AckType.NONE else AckType.NONE)
                            ),
                            duration_s=None,
                            bit_rate_khz=bitrate,
                            extra=data_extra,
                            raw_text=",".join(row),
                        )
                    )
            else:
                if structural_source_error:
                    ev_type = RawEventType.UNKNOWN
                events.append(
                    RawI2CEvent(
                        timestamp=timestamp,
                        event_type=ev_type,
                        timestamp_available=timestamp_available,
                        packet_id=packet_id,
                        address_7bit=addr_7bit,
                        direction=raw_rw,
                        data_byte=raw_data,
                        ack=ack_val,
                        duration_s=dur,
                        bit_rate_khz=bitrate,
                        extra={
                            **timing_extra,
                            **({"source_error": source_error} if source_error else {}),
                        },
                        raw_text=",".join(row),
                    )
                )

        if len(events) > limits.max_records:
            raise ResourceLimitError(
                f"parsed I2C events exceed the {limits.max_records}-record safety limit",
                resource="records",
                limit=limits.max_records,
                observed=len(events),
            )
        return events

    @classmethod
    def parse_csv_string(
        cls, csv_text: str, *, limits: AnalysisLimits | None = None
    ) -> list[RawI2CEvent]:
        """Parse CSV formatted string into RawI2CEvents."""
        limits = coerce_limits(limits)
        if not isinstance(csv_text, str):
            raise TypeError("CSV input must be text")
        _check_text_size(csv_text, limits, label="CSV input")
        return cls.parse_csv_stream(io.StringIO(csv_text.strip()), limits=limits)

    @classmethod
    def parse_text_trace(
        cls, text: str, *, limits: AnalysisLimits | None = None
    ) -> list[RawI2CEvent]:
        """Parse simple text trace logs (e.g. '[0.001] S 0x50 W 0x00 A Sr 0x50 R 0x12 A P')."""
        limits = coerce_limits(limits)
        if not isinstance(text, str):
            raise TypeError("text trace input must be text")
        _check_text_size(text, limits, label="text trace")
        events: list[RawI2CEvent] = []
        lines = [
            line.strip()
            for line in text.strip().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if len(lines) > limits.max_records:
            raise ResourceLimitError(
                f"text trace exceeds the {limits.max_records}-record safety limit",
                resource="records",
                limit=limits.max_records,
                observed=len(lines),
            )

        packet_id = 0

        for line in lines:
            # Extract optional timestamp prefix like [0.001234] or 0.001234:
            m_time = re.match(r"^\[?([0-9]+\.?[0-9]*)\]?[:\s]+(.*)$", line)
            timestamp = 0.0
            timestamp_available = False
            if m_time:
                try:
                    timestamp = float(m_time.group(1))
                    timestamp_available = True
                    line_body = m_time.group(2).strip()
                except ValueError:
                    line_body = line
            else:
                line_body = line

            # Tokenize line
            tokens = re.split(r"[\s,]+", line_body)
            idx = 0
            current_addr: int | None = None
            current_rw: I2CDirection | None = None

            while idx < len(tokens):
                tok = tokens[idx].strip()
                if not tok:
                    idx += 1
                    continue
                tok_upper = tok.upper()

                if tok_upper in ("S", "START"):
                    events.append(
                        RawI2CEvent(
                            timestamp=timestamp,
                            event_type=RawEventType.START,
                            timestamp_available=timestamp_available,
                            packet_id=packet_id,
                        )
                    )
                elif tok_upper in ("SR", "REPEATED_START", "REP_START"):
                    events.append(
                        RawI2CEvent(
                            timestamp=timestamp,
                            event_type=RawEventType.REPEATED_START,
                            timestamp_available=timestamp_available,
                            packet_id=packet_id,
                        )
                    )
                    # A repeated START begins a new address phase.  Do not let
                    # a following byte inherit the previous transaction's
                    # address/direction when the trace omits the new address.
                    current_addr = None
                    current_rw = None
                elif tok_upper in ("P", "STOP"):
                    events.append(
                        RawI2CEvent(
                            timestamp=timestamp,
                            event_type=RawEventType.STOP,
                            timestamp_available=timestamp_available,
                            packet_id=packet_id,
                        )
                    )
                    packet_id += 1
                    # Bytes after STOP are outside this transaction until a
                    # new START/address is observed.  Reset parser context so
                    # malformed text cannot be promoted to a valid DATA row.
                    current_addr = None
                    current_rw = None
                elif tok_upper in ("W", "WRITE", "WR"):
                    current_rw = I2CDirection.WRITE
                elif tok_upper in ("R", "READ", "RD"):
                    current_rw = I2CDirection.READ
                elif tok_upper in ("A", "ACK"):
                    if events and events[-1].ack == AckType.NONE:
                        events[-1].ack = AckType.ACK
                elif tok_upper in ("N", "NACK", "NAK"):
                    if events and events[-1].ack == AckType.NONE:
                        events[-1].ack = AckType.NACK
                else:
                    # Numeric byte token (address or data)
                    val = parse_hex_or_int(tok)
                    if val is None:
                        events.append(
                            RawI2CEvent(
                                timestamp=timestamp,
                                event_type=RawEventType.UNKNOWN,
                                packet_id=packet_id,
                                timestamp_available=timestamp_available,
                                raw_text=tok,
                                extra={"source_error": f"unknown text token {tok!r}"},
                            )
                        )
                    elif not 0 <= val <= 0xFF:
                        events.append(
                            RawI2CEvent(
                                timestamp=timestamp,
                                event_type=RawEventType.UNKNOWN,
                                packet_id=packet_id,
                                timestamp_available=timestamp_available,
                                raw_text=tok,
                                extra={"source_error": f"text byte {val} is outside 0..0xFF"},
                            )
                        )
                    else:
                        # Look ahead for R/W or ACK token
                        next_rw = None
                        if idx + 1 < len(tokens):
                            next_rw = parse_direction(tokens[idx + 1])

                        if current_addr is None or next_rw is not None:
                            # This is an Address byte
                            current_addr = val if val <= 0x7F else ((val >> 1) & 0x7F)
                            if next_rw is not None:
                                current_rw = next_rw
                                idx += 1
                            elif val > 0x7F:
                                current_rw = (
                                    I2CDirection.READ if (val & 0x01) else I2CDirection.WRITE
                                )

                            address_extra = {}
                            if val > 0x7F and next_rw is not None:
                                implied_direction = (
                                    I2CDirection.READ if (val & 0x01) else I2CDirection.WRITE
                                )
                                if next_rw != implied_direction:
                                    address_extra = {
                                        "source_error": (
                                            f"8-bit address {val:#04x} conflicts with explicit "
                                            f"direction {next_rw.value}; implied direction is "
                                            f"{implied_direction.value}"
                                        )
                                    }
                            if current_rw is None:
                                address_extra = {
                                    "source_error": "7-bit address is missing a READ/WRITE token"
                                }

                            events.append(
                                RawI2CEvent(
                                    timestamp=timestamp,
                                    event_type=RawEventType.ADDRESS,
                                    timestamp_available=timestamp_available,
                                    packet_id=packet_id,
                                    address_7bit=current_addr,
                                    direction=current_rw,
                                    ack=AckType.NONE,
                                    extra=address_extra,
                                )
                            )
                        else:
                            # This is a Data byte
                            events.append(
                                RawI2CEvent(
                                    timestamp=timestamp,
                                    event_type=RawEventType.DATA,
                                    timestamp_available=timestamp_available,
                                    packet_id=packet_id,
                                    address_7bit=current_addr,
                                    direction=current_rw,
                                    data_byte=val,
                                    ack=AckType.NONE,
                                    extra=(
                                        {"source_error": "data direction is unavailable"}
                                        if current_rw is None
                                        else {}
                                    ),
                                )
                            )
                idx += 1

        if len(events) > limits.max_records:
            raise ResourceLimitError(
                f"parsed I2C events exceed the {limits.max_records}-record safety limit",
                resource="records",
                limit=limits.max_records,
                observed=len(events),
            )
        return events

    @classmethod
    def parse_raw_records(
        cls, records: list[dict[str, Any]], *, limits: AnalysisLimits | None = None
    ) -> list[RawI2CEvent]:
        """Convert raw Python dictionary list into normalized RawI2CEvents."""
        limits = coerce_limits(limits)
        if not isinstance(records, list):
            raise TypeError("raw I2C records must be provided as a list")
        if len(records) > limits.max_records:
            raise ResourceLimitError(
                f"raw I2C records exceed the {limits.max_records}-record safety limit",
                resource="records",
                limit=limits.max_records,
                observed=len(records),
            )

        events: list[RawI2CEvent] = []
        for index, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise TypeError(f"raw I2C record {index} must be a mapping")

            raw_timestamp = rec.get("timestamp", rec.get("time"))
            parsed_timestamp = _nonnegative_finite_float(raw_timestamp)
            timestamp_available = parsed_timestamp is not None
            ts = parsed_timestamp if parsed_timestamp is not None else 0.0
            source_errors: list[str] = []

            def has_value(value: Any) -> bool:
                return value is not None and str(value).strip().lower() not in {
                    "",
                    "-",
                    "none",
                    "null",
                    "n/a",
                }

            if has_value(raw_timestamp) and not timestamp_available:
                source_errors.append("timestamp is not finite and non-negative")
            raw_event_type = rec.get("event_type", rec.get("type", "DATA"))
            if isinstance(raw_event_type, RawEventType):
                ev_type = raw_event_type
            else:
                ev_type_str = str(raw_event_type).strip().strip("'").strip('"').upper()
                try:
                    ev_type = RawEventType(ev_type_str)
                except ValueError as exc:
                    raise ValueError(
                        f"raw I2C record {index} has unknown event_type {raw_event_type!r}"
                    ) from exc

            raw_address = rec.get("address", rec.get("address_7bit", rec.get("addr")))
            addr = parse_hex_or_int(raw_address)
            if has_value(raw_address) and addr is None:
                source_errors.append("address is not a numeric 7-bit/8-bit value")
            if addr is not None and not 0 <= addr <= 0xFF:
                raise ValueError(
                    f"raw I2C record {index} address must be a 7-bit or 8-bit value (0..0xFF), got {addr}"
                )
            addr_7bit = ((addr >> 1) & 0x7F) if (addr is not None and addr > 0x7F) else addr

            raw_direction = rec.get("direction", rec.get("rw", rec.get("read_write")))
            rw = parse_direction(raw_direction)
            if has_value(raw_direction) and rw is None:
                source_errors.append("direction is not READ/WRITE")
            if addr is not None and addr > 0x7F and rw is not None:
                implied_direction = I2CDirection.READ if (addr & 0x01) else I2CDirection.WRITE
                if rw != implied_direction:
                    source_errors.append(
                        f"8-bit address {addr:#04x} conflicts with explicit direction {rw.value}; "
                        f"implied direction is {implied_direction.value}"
                    )
            raw_data = rec.get("data", rec.get("data_byte", rec.get("byte")))
            data_val = parse_hex_or_int(raw_data)
            if has_value(raw_data) and data_val is None:
                source_errors.append("data byte is not numeric")
            if data_val is not None and not 0 <= data_val <= 0xFF:
                raise ValueError(
                    f"raw I2C record {index} data byte must be in range 0..0xFF, got {data_val}"
                )
            raw_ack = rec.get("ack", rec.get("ack_nak"))
            ack_val = parse_ack(raw_ack)
            if has_value(raw_ack) and ack_val == AckType.NONE:
                source_errors.append("ACK is not ACK/NACK")

            raw_packet_id = rec.get("packet_id")
            packet_id = None
            if raw_packet_id is not None:
                packet_id = parse_hex_or_int(raw_packet_id)
                if packet_id is None or packet_id < 0:
                    raise ValueError(
                        f"raw I2C record {index} packet_id must be a non-negative integer"
                    )

            raw_duration = rec.get("duration_s")
            duration_s = _positive_finite_float(raw_duration)
            if has_value(raw_duration) and duration_s is None:
                source_errors.append("duration_s is not positive and finite")
            raw_bit_rate = rec.get("bit_rate_khz")
            bit_rate_khz = _positive_finite_float(raw_bit_rate)
            if has_value(raw_bit_rate) and bit_rate_khz is None:
                source_errors.append("bit_rate_khz is not positive and finite")

            extra = dict(rec)
            if source_errors:
                extra["source_error"] = "; ".join(source_errors)

            events.append(
                RawI2CEvent(
                    timestamp=ts,
                    event_type=ev_type,
                    timestamp_available=timestamp_available,
                    packet_id=packet_id,
                    address_7bit=addr_7bit,
                    direction=rw,
                    data_byte=data_val,
                    ack=ack_val,
                    duration_s=duration_s,
                    bit_rate_khz=bit_rate_khz,
                    extra=extra,
                )
            )
        if len(events) > limits.max_records:
            raise ResourceLimitError(
                f"parsed I2C events exceed the {limits.max_records}-record safety limit",
                resource="records",
                limit=limits.max_records,
                observed=len(events),
            )
        return events
