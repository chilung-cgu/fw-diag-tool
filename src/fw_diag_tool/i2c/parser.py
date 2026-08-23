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

from fw_diag_tool.i2c.models import (
    AckType,
    I2CDirection,
    RawEventType,
    RawI2CEvent,
)


def parse_hex_or_int(val: Any) -> int | None:
    """Parse integer from hex string (0x50, 50h), decimal ('80'), or numeric type."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
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
    def parse_csv_stream(cls, f: TextIO) -> list[RawI2CEvent]:
        """Parse CSV data from an open text stream (e.g. Saleae Logic 2 or Generic CSV)."""
        if not hasattr(f, "read") or not hasattr(f, "seek"):
            raise TypeError("CSV input must be a seekable text stream")
        events: list[RawI2CEvent] = []

        # Read header and detect delimiter
        sample = f.read(4096)
        f.seek(0)
        delimiter = ","
        if ";" in sample and sample.count(";") > sample.count(","):
            delimiter = ";"
        elif "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"

        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader, None)
        if not header:
            return []

        # Normalize headers
        col_map: dict[str, int] = {}
        for idx, col in enumerate(header):
            c = col.strip().lower().replace(" ", "_").replace("[s]", "").replace('"', "").strip("_")
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

        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue

            source_error: str | None = None

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
                pass

            packet_id = (
                parse_hex_or_int(row[packet_id_idx])
                if packet_id_idx is not None and packet_id_idx < len(row)
                else None
            )
            raw_type_str = (
                row[type_idx].strip().upper()
                if type_idx is not None and type_idx < len(row)
                else ""
            )

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
            if raw_addr is not None and not 0 <= raw_addr <= 0xFF:
                source_error = (
                    f"address {raw_addr} is outside the supported 7-bit/8-bit range 0..0xFF"
                )
                raw_addr = None

            # Parse direction
            raw_rw = (
                parse_direction(row[rw_idx]) if rw_idx is not None and rw_idx < len(row) else None
            )

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
                    # Likely 8-bit address: extract top 7 bits and R/W bit if direction missing
                    addr_7bit = (raw_addr >> 1) & 0x7F
                    if raw_rw is None:
                        raw_rw = I2CDirection.READ if (raw_addr & 0x01) else I2CDirection.WRITE
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
                if any(
                    token is not None and not 0 <= token <= 0xFF for token in parsed_data_tokens
                ):
                    invalid = next(
                        token
                        for token in parsed_data_tokens
                        if token is not None and not 0 <= token <= 0xFF
                    )
                    source_error = source_error or f"data byte {invalid} is outside 0..0xFF"
                raw_data_tokens = [
                    token
                    for token in parsed_data_tokens
                    if token is not None and 0 <= token <= 0xFF
                ]
                if source_error:
                    # Do not allow a malformed combined row to become a plausible
                    # partial transaction. Preserve the row as quality evidence.
                    raw_data_tokens = []
            raw_data = raw_data_tokens[0] if len(raw_data_tokens) == 1 else None

            # Parse ACK
            ack_val = (
                parse_ack(row[ack_idx])
                if ack_idx is not None and ack_idx < len(row)
                else AckType.NONE
            )

            # Duration & Bitrate
            dur = (
                _positive_finite_float(row[duration_idx].strip())
                if duration_idx is not None and duration_idx < len(row)
                else None
            )
            bitrate = None
            if bitrate_idx is not None and bitrate_idx < len(row):
                b_val = _positive_finite_float(row[bitrate_idx].strip())
                if b_val is not None:
                    bitrate = b_val / 1000.0 if b_val > 10000 else b_val

            # Determine event type
            if "START" in raw_type_str and "REPEATED" not in raw_type_str:
                ev_type = RawEventType.START
            elif "REPEATED" in raw_type_str or "SR" in raw_type_str:
                ev_type = RawEventType.REPEATED_START
            elif "STOP" in raw_type_str:
                ev_type = RawEventType.STOP
            elif addr_7bit is not None and raw_data is None:
                ev_type = RawEventType.ADDRESS
            elif raw_data is not None:
                ev_type = RawEventType.DATA
            else:
                ev_type = RawEventType.UNKNOWN

            if raw_data_tokens and addr_7bit is not None:
                # Analyzer summary rows can combine address and one or more data bytes.
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
                        extra={"source_error": source_error} if source_error else {},
                        raw_text=",".join(row),
                    )
                )
                for b_idx, b_val in enumerate(raw_data_tokens):
                    events.append(
                        RawI2CEvent(
                            timestamp=timestamp,
                            event_type=RawEventType.DATA,
                            timestamp_available=timestamp_available,
                            packet_id=packet_id,
                            address_7bit=addr_7bit,
                            direction=raw_rw,
                            data_byte=b_val,
                            ack=ack_val
                            if b_idx == len(raw_data_tokens) - 1
                            else (AckType.ACK if ack_val != AckType.NONE else AckType.NONE),
                            duration_s=None,
                            bit_rate_khz=bitrate,
                            extra={"source_error": source_error} if source_error else {},
                            raw_text=",".join(row),
                        )
                    )
            else:
                if source_error:
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
                        extra={"source_error": source_error} if source_error else {},
                        raw_text=",".join(row),
                    )
                )

        return events

    @classmethod
    def parse_csv_string(cls, csv_text: str) -> list[RawI2CEvent]:
        """Parse CSV formatted string into RawI2CEvents."""
        if not isinstance(csv_text, str):
            raise TypeError("CSV input must be text")
        return cls.parse_csv_stream(io.StringIO(csv_text.strip()))

    @classmethod
    def parse_text_trace(cls, text: str) -> list[RawI2CEvent]:
        """Parse simple text trace logs (e.g. '[0.001] S 0x50 W 0x00 A Sr 0x50 R 0x12 A P')."""
        events: list[RawI2CEvent] = []
        lines = [
            line.strip()
            for line in text.strip().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

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
                    if val is not None:
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
                            else:
                                current_rw = current_rw or I2CDirection.WRITE

                            events.append(
                                RawI2CEvent(
                                    timestamp=timestamp,
                                    event_type=RawEventType.ADDRESS,
                                    timestamp_available=timestamp_available,
                                    packet_id=packet_id,
                                    address_7bit=current_addr,
                                    direction=current_rw,
                                    ack=AckType.NONE,
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
                                )
                            )
                idx += 1

        return events

    @classmethod
    def parse_raw_records(cls, records: list[dict[str, Any]]) -> list[RawI2CEvent]:
        """Convert raw Python dictionary list into normalized RawI2CEvents."""
        if not isinstance(records, list):
            raise TypeError("raw I2C records must be provided as a list")

        events: list[RawI2CEvent] = []
        for index, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise TypeError(f"raw I2C record {index} must be a mapping")

            raw_timestamp = rec.get("timestamp", rec.get("time"))
            parsed_timestamp = _nonnegative_finite_float(raw_timestamp)
            timestamp_available = parsed_timestamp is not None
            ts = parsed_timestamp if parsed_timestamp is not None else 0.0
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

            addr = parse_hex_or_int(rec.get("address", rec.get("address_7bit", rec.get("addr"))))
            if addr is not None and not 0 <= addr <= 0xFF:
                raise ValueError(
                    f"raw I2C record {index} address must be a 7-bit or 8-bit value (0..0xFF), got {addr}"
                )
            addr_7bit = ((addr >> 1) & 0x7F) if (addr is not None and addr > 0x7F) else addr

            rw = parse_direction(rec.get("direction", rec.get("rw", rec.get("read_write"))))
            data_val = parse_hex_or_int(rec.get("data", rec.get("data_byte", rec.get("byte"))))
            if data_val is not None and not 0 <= data_val <= 0xFF:
                raise ValueError(
                    f"raw I2C record {index} data byte must be in range 0..0xFF, got {data_val}"
                )
            ack_val = parse_ack(rec.get("ack", rec.get("ack_nak")))

            duration_s = _positive_finite_float(rec.get("duration_s"))
            bit_rate_khz = _positive_finite_float(rec.get("bit_rate_khz"))

            events.append(
                RawI2CEvent(
                    timestamp=ts,
                    event_type=ev_type,
                    timestamp_available=timestamp_available,
                    packet_id=rec.get("packet_id"),
                    address_7bit=addr_7bit,
                    direction=rw,
                    data_byte=data_val,
                    ack=ack_val,
                    duration_s=duration_s,
                    bit_rate_khz=bit_rate_khz,
                    extra=rec,
                )
            )
        return events
