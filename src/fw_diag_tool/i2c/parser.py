"""I2C Protocol Data Parser supporting Saleae Logic 2, Generic CSV, and Raw Traces.

Parses logic analyzer CSV exports, text traces, and raw Python structures into
normalized RawI2CEvent sequences ready for transaction grouping and semantic analysis.
"""

from __future__ import annotations

import csv
import io
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
        return AckType.ACK
    s = str(val).strip().strip("'").strip('"').upper()
    if s in ("NAK", "NACK", "1", "FALSE", "NO", "N"):
        return AckType.NACK
    elif s in ("ACK", "0", "TRUE", "YES", "A", "Y"):
        return AckType.ACK
    return AckType.NONE


class I2CParser:
    """Universal I2C trace parser."""

    @classmethod
    def parse_csv_stream(cls, f: TextIO) -> list[RawI2CEvent]:
        """Parse CSV data from an open text stream (e.g. Saleae Logic 2 or Generic CSV)."""
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
            
        # Map common column aliases
        time_idx = col_map.get("time") or col_map.get("timestamp") or col_map.get("start_time") or 0
        packet_id_idx = col_map.get("packet_id") or col_map.get("packet") or col_map.get("transaction_id")
        type_idx = col_map.get("type") or col_map.get("event") or col_map.get("event_type")
        addr_idx = col_map.get("address") or col_map.get("addr") or col_map.get("slave_address")
        data_idx = col_map.get("data") or col_map.get("byte") or col_map.get("value")
        rw_idx = col_map.get("read/write") or col_map.get("rw") or col_map.get("read_write") or col_map.get("r/w") or col_map.get("direction")
        ack_idx = col_map.get("ack/nak") or col_map.get("ack") or col_map.get("ack_nak") or col_map.get("ack/nack")
        duration_idx = col_map.get("duration") or col_map.get("duration_s")
        bitrate_idx = col_map.get("bit_rate") or col_map.get("bitrate") or col_map.get("frequency")
        
        for row_idx, row in enumerate(reader):
            if not row or not any(cell.strip() for cell in row):
                continue
                
            # Parse timestamp
            try:
                t_str = row[time_idx].strip().strip("'").strip('"')
                timestamp = float(t_str)
            except (IndexError, ValueError):
                timestamp = float(row_idx) * 0.0001
                
            packet_id = parse_hex_or_int(row[packet_id_idx]) if packet_id_idx is not None and packet_id_idx < len(row) else None
            raw_type_str = row[type_idx].strip().upper() if type_idx is not None and type_idx < len(row) else ""
            
            # Parse address
            raw_addr = parse_hex_or_int(row[addr_idx]) if addr_idx is not None and addr_idx < len(row) else None
            
            # Parse direction
            raw_rw = parse_direction(row[rw_idx]) if rw_idx is not None and rw_idx < len(row) else None
            
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
            raw_data_cell = str(row[data_idx]).strip() if data_idx is not None and data_idx < len(row) else ""
            raw_data_tokens = []
            if raw_data_cell and raw_data_cell.lower() not in ("-", "none", "null", ""):
                raw_data_tokens = [parse_hex_or_int(tok) for tok in re.split(r"[ ,;]+", raw_data_cell) if tok.strip()]
                raw_data_tokens = [tok for tok in raw_data_tokens if tok is not None]
            raw_data = raw_data_tokens[0] if len(raw_data_tokens) == 1 else None
            
            # Parse ACK
            ack_val = parse_ack(row[ack_idx]) if ack_idx is not None and ack_idx < len(row) else AckType.ACK
            
            # Duration & Bitrate
            dur = None
            if duration_idx is not None and duration_idx < len(row):
                try:
                    dur = float(row[duration_idx].strip())
                except ValueError:
                    pass
            bitrate = None
            if bitrate_idx is not None and bitrate_idx < len(row):
                try:
                    b_val = float(row[bitrate_idx].strip())
                    bitrate = b_val / 1000.0 if b_val > 10000 else b_val  # convert Hz to kHz if necessary
                except ValueError:
                    pass
                    
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
                
            if len(raw_data_tokens) > 1:
                # Multi-byte packet row: emit ADDRESS first then DATA for each byte
                if addr_7bit is not None:
                    events.append(RawI2CEvent(
                        timestamp=timestamp,
                        event_type=RawEventType.ADDRESS,
                        packet_id=packet_id,
                        address_7bit=addr_7bit,
                        direction=raw_rw,
                        data_byte=None,
                        ack=AckType.ACK,
                        duration_s=dur,
                        bit_rate_khz=bitrate,
                        raw_text=",".join(row),
                    ))
                for b_idx, b_val in enumerate(raw_data_tokens):
                    events.append(RawI2CEvent(
                        timestamp=timestamp + (b_idx + 1) * 0.00001,
                        event_type=RawEventType.DATA,
                        packet_id=packet_id,
                        address_7bit=addr_7bit,
                        direction=raw_rw,
                        data_byte=b_val,
                        ack=ack_val,
                        duration_s=dur,
                        bit_rate_khz=bitrate,
                        raw_text=",".join(row),
                    ))
            else:
                events.append(RawI2CEvent(
                    timestamp=timestamp,
                    event_type=ev_type,
                    packet_id=packet_id,
                    address_7bit=addr_7bit,
                    direction=raw_rw,
                    data_byte=raw_data,
                    ack=ack_val,
                    duration_s=dur,
                    bit_rate_khz=bitrate,
                    raw_text=",".join(row),
                ))
            
        return events

    @classmethod
    def parse_csv_string(cls, csv_text: str) -> list[RawI2CEvent]:
        """Parse CSV formatted string into RawI2CEvents."""
        return cls.parse_csv_stream(io.StringIO(csv_text.strip()))

    @classmethod
    def parse_text_trace(cls, text: str) -> list[RawI2CEvent]:
        """Parse simple text trace logs (e.g. '[0.001] S 0x50 W 0x00 A Sr 0x50 R 0x12 A P')."""
        events: list[RawI2CEvent] = []
        lines = [line.strip() for line in text.strip().splitlines() if line.strip() and not line.strip().startswith("#")]
        
        time_counter = 0.001000
        packet_id = 0
        
        for line in lines:
            # Extract optional timestamp prefix like [0.001234] or 0.001234:
            m_time = re.match(r"^\[?([0-9]+\.?[0-9]*)\]?[:\s]+(.*)$", line)
            if m_time:
                try:
                    time_counter = float(m_time.group(1))
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
                    events.append(RawI2CEvent(timestamp=time_counter, event_type=RawEventType.START, packet_id=packet_id))
                    time_counter += 0.000005
                elif tok_upper in ("SR", "REPEATED_START", "REP_START"):
                    events.append(RawI2CEvent(timestamp=time_counter, event_type=RawEventType.REPEATED_START, packet_id=packet_id))
                    time_counter += 0.000005
                elif tok_upper in ("P", "STOP"):
                    events.append(RawI2CEvent(timestamp=time_counter, event_type=RawEventType.STOP, packet_id=packet_id))
                    time_counter += 0.000010
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
                                current_rw = I2CDirection.READ if (val & 0x01) else I2CDirection.WRITE
                            else:
                                current_rw = current_rw or I2CDirection.WRITE
                                
                            events.append(RawI2CEvent(
                                timestamp=time_counter,
                                event_type=RawEventType.ADDRESS,
                                packet_id=packet_id,
                                address_7bit=current_addr,
                                direction=current_rw,
                                ack=AckType.ACK
                            ))
                        else:
                            # This is a Data byte
                            events.append(RawI2CEvent(
                                timestamp=time_counter,
                                event_type=RawEventType.DATA,
                                packet_id=packet_id,
                                address_7bit=current_addr,
                                direction=current_rw,
                                data_byte=val,
                                ack=AckType.ACK
                            ))
                        time_counter += 0.000025  # ~40kHz nominal increment
                idx += 1
                
        return events

    @classmethod
    def parse_raw_records(cls, records: list[dict[str, Any]]) -> list[RawI2CEvent]:
        """Convert raw Python dictionary list into normalized RawI2CEvents."""
        events: list[RawI2CEvent] = []
        for idx, rec in enumerate(records):
            ts = float(rec.get("timestamp", rec.get("time", idx * 0.0001)))
            ev_type_str = str(rec.get("event_type", rec.get("type", "DATA"))).upper()
            ev_type = RawEventType(ev_type_str) if ev_type_str in RawEventType._value2member_map_ else RawEventType.DATA
            
            addr = parse_hex_or_int(rec.get("address", rec.get("address_7bit", rec.get("addr"))))
            addr_7bit = ((addr >> 1) & 0x7F) if (addr is not None and addr > 0x7F) else addr
            
            rw = parse_direction(rec.get("direction", rec.get("rw", rec.get("read_write"))))
            data_val = parse_hex_or_int(rec.get("data", rec.get("data_byte", rec.get("byte"))))
            ack_val = parse_ack(rec.get("ack", rec.get("ack_nak")))
            
            events.append(RawI2CEvent(
                timestamp=ts,
                event_type=ev_type,
                packet_id=rec.get("packet_id"),
                address_7bit=addr_7bit,
                direction=rw,
                data_byte=data_val,
                ack=ack_val,
                duration_s=rec.get("duration_s"),
                bit_rate_khz=rec.get("bit_rate_khz"),
                extra=rec
            ))
        return events
