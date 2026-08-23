"""I2C / SMBus / PMBus Semantic Analysis, Grouping, and Diagnostic Engine.

Orchestrates trace parsing, transaction boundary grouping, chip identification,
protocol semantic decoding (PMBus, EEPROM, Sensors), timing health analysis,
and actionable diagnostic advice generation.
"""

from __future__ import annotations

import math
from typing import Any

from fw_diag_tool.i2c.anomaly import I2CAnomalyDetector
from fw_diag_tool.i2c.chip_db import get_all_matching_devices, lookup_device
from fw_diag_tool.i2c.eeprom import EEPROM_MODELS, decode_eeprom_read, decode_eeprom_write
from fw_diag_tool.i2c.models import (
    AckType,
    DataQualityIssue,
    I2CAnalysisReport,
    I2CBytePacket,
    I2CDirection,
    I2CTransaction,
    RawEventType,
    RawI2CEvent,
)
from fw_diag_tool.i2c.parser import I2CParser
from fw_diag_tool.i2c.pmbus import decode_pmbus_payload
from fw_diag_tool.i2c.sensor_decoders import (
    decode_ina2xx_power,
    decode_lm75_temperature,
    decode_pca9555_gpio,
)
from fw_diag_tool.i2c.timing import analyze_timing_statistics

from .mux_tracker import I2CMuxTracker


class I2CDiagnosticEngine:
    """High-level Diagnostic Engine for I2C, SMBus, and PMBus Traces."""

    def __init__(
        self,
        smbus_timeout_ms: float = 25.0,
        high_jitter_threshold_pct: float = 35.0,
        default_eeprom_page_size: int = 16,
        default_vout_exponent: int = -9,
        default_eeprom_address_bytes: int | None = None,
        eeprom_profile: str | None = None,
    ):
        self.smbus_timeout_ms = self._positive_finite_config(
            "smbus_timeout_ms", smbus_timeout_ms, maximum=60_000.0
        )
        self.high_jitter_threshold_pct = self._positive_finite_config(
            "high_jitter_threshold_pct", high_jitter_threshold_pct, maximum=10_000.0
        )
        self.default_eeprom_page_size = self._positive_int_config(
            "default_eeprom_page_size", default_eeprom_page_size, maximum=4096
        )
        if not isinstance(default_vout_exponent, int) or isinstance(default_vout_exponent, bool):
            raise TypeError("default_vout_exponent must be an integer in the PMBus range -16..15")
        if not -16 <= default_vout_exponent <= 15:
            raise ValueError("default_vout_exponent must be in the PMBus range -16..15")
        if default_eeprom_address_bytes not in (None, 1, 2):
            raise ValueError("default_eeprom_address_bytes must be 1, 2, or None")
        if eeprom_profile is not None and eeprom_profile not in EEPROM_MODELS:
            known_profiles = ", ".join(sorted(EEPROM_MODELS))
            raise ValueError(
                f"unknown eeprom_profile {eeprom_profile!r}; choose one of: {known_profiles}"
            )
        self.default_vout_exponent = default_vout_exponent
        self.default_eeprom_address_bytes = default_eeprom_address_bytes
        self.eeprom_profile = eeprom_profile
        self.mux_tracker = I2CMuxTracker()
        self.anomaly_detector = I2CAnomalyDetector(
            smbus_timeout_ms=self.smbus_timeout_ms,
            high_jitter_threshold_pct=self.high_jitter_threshold_pct,
        )

    @staticmethod
    def _positive_finite_config(name: str, value: Any, *, maximum: float) -> float:
        """Validate a positive finite numeric engine setting with a safe upper bound."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a finite numeric value")
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0 or parsed > maximum:
            raise ValueError(f"{name} must be > 0 and <= {maximum:g}")
        return parsed

    @staticmethod
    def _positive_int_config(name: str, value: Any, *, maximum: int) -> int:
        """Validate a bounded positive integer engine setting."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer in range 1..{maximum}")
        if not 1 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in range 1..{maximum}")
        return value

    def group_events_into_transactions(self, events: list[RawI2CEvent]) -> list[I2CTransaction]:
        """Group raw stream of physical I2C events into logical I2C Transactions."""
        transactions: list[I2CTransaction] = []
        if not events:
            return transactions

        current_tx: I2CTransaction | None = None
        tx_counter = 1
        last_byte_end_time: float | None = None

        def finish_at_event(tx: I2CTransaction, event: RawI2CEvent) -> None:
            tx.timestamp_available = tx.timestamp_available and event.timestamp_available
            if tx.timestamp_available:
                tx.end_time = event.timestamp
                tx.duration_us = max(0.0, (tx.end_time - tx.start_time) * 1_000_000.0)
            else:
                tx.duration_us = 0.0

        for ev in events:
            # Explicit START or REPEATED_START
            if ev.event_type in (RawEventType.START, RawEventType.REPEATED_START):
                if current_tx is not None:
                    if (
                        current_tx.byte_packets
                        or current_tx.data_bytes
                        or getattr(current_tx, "_has_address", False)
                    ):
                        finish_at_event(current_tx, ev)
                        if ev.event_type == RawEventType.REPEATED_START:
                            current_tx.has_stop = False
                        transactions.append(current_tx)
                    current_tx = None

                # Initialize next transaction placeholder
                current_tx = I2CTransaction(
                    id=tx_counter,
                    start_time=ev.timestamp,
                    end_time=ev.timestamp,
                    address_7bit=ev.address_7bit or 0x00,
                    address_8bit=((ev.address_7bit or 0x00) << 1)
                    | (1 if ev.direction == I2CDirection.READ else 0),
                    direction=ev.direction or I2CDirection.WRITE,
                    address_ack=AckType.NONE,
                    is_repeated_start=(ev.event_type == RawEventType.REPEATED_START),
                    has_stop=False,
                    timestamp_available=ev.timestamp_available,
                )
                current_tx._is_placeholder = True
                current_tx._has_address = ev.address_7bit is not None
                tx_counter += 1
                last_byte_end_time = ev.timestamp if ev.timestamp_available else None
                continue

            # Explicit STOP
            if ev.event_type == RawEventType.STOP:
                if current_tx is not None:
                    if (
                        current_tx.byte_packets
                        or current_tx.data_bytes
                        or getattr(current_tx, "_has_address", False)
                    ):
                        current_tx.has_stop = True
                        finish_at_event(current_tx, ev)
                        transactions.append(current_tx)
                    current_tx = None
                continue

            # ADDRESS Event
            if ev.event_type == RawEventType.ADDRESS or (
                ev.address_7bit is not None and ev.data_byte is None
            ):
                addr_7b = ev.address_7bit or 0x00
                rw = ev.direction or I2CDirection.WRITE
                addr_8b = (addr_7b << 1) | (1 if rw == I2CDirection.READ else 0)

                is_placeholder = (
                    getattr(current_tx, "_is_placeholder", False) if current_tx else False
                )
                packet_id_changed = (
                    ev.packet_id is not None
                    and current_tx is not None
                    and ev.packet_id != getattr(current_tx, "_packet_id", None)
                )

                if current_tx is None or (not is_placeholder and packet_id_changed):
                    if current_tx is not None and (
                        current_tx.byte_packets or getattr(current_tx, "_has_address", False)
                    ):
                        finish_at_event(current_tx, ev)
                        current_tx.has_stop = (
                            True  # packet_id boundary in Saleae represents clean packet framing
                        )
                        transactions.append(current_tx)

                    current_tx = I2CTransaction(
                        id=tx_counter,
                        start_time=ev.timestamp,
                        end_time=ev.timestamp,
                        address_7bit=addr_7b,
                        address_8bit=addr_8b,
                        direction=rw,
                        address_ack=ev.ack or AckType.NONE,
                        has_stop=(ev.packet_id is not None),
                        timestamp_available=ev.timestamp_available,
                    )
                    current_tx._packet_id = ev.packet_id
                    current_tx._has_address = True
                    current_tx._is_placeholder = False
                    tx_counter += 1
                else:
                    # Populate existing placeholder
                    current_tx.address_7bit = addr_7b
                    current_tx.address_8bit = addr_8b
                    current_tx.direction = rw
                    current_tx.address_ack = ev.ack or AckType.NONE
                    current_tx.timestamp_available = (
                        current_tx.timestamp_available and ev.timestamp_available
                    )
                    if ev.packet_id is not None:
                        current_tx.has_stop = True
                    current_tx._packet_id = ev.packet_id
                    current_tx._has_address = True
                    current_tx._is_placeholder = False

                # Record address byte packet
                dur_s = ev.duration_s
                pkt = I2CBytePacket(
                    timestamp=ev.timestamp,
                    byte_val=addr_8b,
                    is_address=True,
                    direction=rw,
                    ack=ev.ack or AckType.NONE,
                    timestamp_available=ev.timestamp_available,
                    duration_s=dur_s,
                    bit_rate_khz=ev.bit_rate_khz,
                )
                current_tx.byte_packets.append(pkt)
                if ev.timestamp_available:
                    current_tx.end_time = ev.timestamp + (dur_s or 0.0)
                    last_byte_end_time = current_tx.end_time
                else:
                    current_tx.timestamp_available = False
                    last_byte_end_time = None
                continue

            # DATA Event
            if ev.event_type == RawEventType.DATA or ev.data_byte is not None:
                data_val = ev.data_byte if ev.data_byte is not None else 0x00

                pkt_changed = (
                    ev.packet_id is not None
                    and current_tx is not None
                    and getattr(current_tx, "_packet_id", None) is not None
                    and ev.packet_id != current_tx._packet_id
                )
                dir_changed = (
                    current_tx is not None
                    and ev.direction is not None
                    and ev.direction != current_tx.direction
                )
                addr_changed = (
                    current_tx is not None
                    and ev.address_7bit is not None
                    and ev.address_7bit != current_tx.address_7bit
                )
                if current_tx is None or pkt_changed or dir_changed or addr_changed:
                    if current_tx is not None and (
                        current_tx.byte_packets or getattr(current_tx, "_has_address", False)
                    ):
                        finish_at_event(current_tx, ev)
                        current_tx.has_stop = True
                        transactions.append(current_tx)
                    # Implicit transaction start without explicit START/ADDRESS event
                    addr_7b = ev.address_7bit or 0x00
                    rw = ev.direction or I2CDirection.WRITE
                    current_tx = I2CTransaction(
                        id=tx_counter,
                        start_time=ev.timestamp,
                        end_time=ev.timestamp,
                        address_7bit=addr_7b,
                        address_8bit=(addr_7b << 1) | (1 if rw == I2CDirection.READ else 0),
                        direction=rw,
                        address_ack=AckType.NONE,
                        has_stop=(ev.packet_id is not None),
                        timestamp_available=ev.timestamp_available,
                    )
                    current_tx._packet_id = ev.packet_id
                    current_tx._has_address = ev.address_7bit is not None
                    current_tx._is_placeholder = False
                    tx_counter += 1
                    last_byte_end_time = ev.timestamp if ev.timestamp_available else None
                else:
                    current_tx._is_placeholder = False
                    current_tx.timestamp_available = (
                        current_tx.timestamp_available and ev.timestamp_available
                    )
                    if ev.packet_id is not None:
                        current_tx.has_stop = True

                # Compute inter-byte delay and clock stretch
                dur_s = ev.duration_s
                inter_byte_us = 0.0
                if ev.timestamp_available and last_byte_end_time is not None:
                    inter_byte_us = max(0.0, (ev.timestamp - last_byte_end_time) * 1_000_000.0)
                    current_tx.inter_byte_delays_us.append(inter_byte_us)

                # Clock stretch check on single byte transfer
                clock_stretch_us = 0.0
                if dur_s is not None and dur_s > 0.000100:  # > 100us for 1 byte
                    clock_stretch_us = dur_s * 1_000_000.0
                    current_tx.clock_stretching_events.append(
                        {
                            "timestamp": ev.timestamp,
                            "duration_ms": dur_s * 1000.0,
                            "byte_val": f"0x{data_val:02X}",
                        }
                    )

                pkt = I2CBytePacket(
                    timestamp=ev.timestamp,
                    byte_val=data_val,
                    is_address=False,
                    direction=current_tx.direction,
                    ack=ev.ack or AckType.NONE,
                    timestamp_available=ev.timestamp_available,
                    duration_s=dur_s,
                    bit_rate_khz=ev.bit_rate_khz,
                    inter_byte_delay_us=inter_byte_us,
                    clock_stretch_us=clock_stretch_us,
                )
                current_tx.byte_packets.append(pkt)
                current_tx.data_bytes.append(data_val)
                if ev.timestamp_available:
                    current_tx.end_time = ev.timestamp + (dur_s or 0.0)
                    last_byte_end_time = current_tx.end_time
                else:
                    last_byte_end_time = None

        # Flush trailing transaction
        if current_tx is not None and (
            current_tx.byte_packets or getattr(current_tx, "_has_address", False)
        ):
            if current_tx.timestamp_available:
                current_tx.duration_us = max(
                    0.0, (current_tx.end_time - current_tx.start_time) * 1_000_000.0
                )
            else:
                current_tx.duration_us = 0.0
            transactions.append(current_tx)

        return transactions

    def decode_semantic_layer(self, transactions: list[I2CTransaction]) -> list[DataQualityIssue]:
        """Perform chip identification and protocol semantic decoding across transactions."""
        device_context: dict[int, dict[str, Any]] = {}
        ambiguous_eeprom_writes = 0

        for tx in transactions:
            addr = tx.address_7bit
            candidates = get_all_matching_devices(addr)
            chip = lookup_device(addr) if len(candidates) == 1 else None
            tx.device_candidates = [candidate.name for candidate in candidates]
            if chip is not None:
                tx.device_name = f"Possible: {chip.name}"
                tx.device_category = chip.category
                tx.protocol = chip.protocol
                tx.identity_confidence = "single-address-candidate"
            elif candidates:
                categories = {candidate.category for candidate in candidates}
                protocols = {candidate.protocol for candidate in candidates}
                tx.device_name = f"Possible devices ({len(candidates)} candidates)"
                tx.device_category = (
                    next(iter(categories))
                    if len(categories) == 1
                    else (
                        f"{next(iter(protocols))} (ambiguous candidates)"
                        if len(protocols) == 1
                        else "Ambiguous I2C Address"
                    )
                )
                tx.protocol = next(iter(protocols)) if len(protocols) == 1 else "I2C"
                tx.identity_confidence = "ambiguous"
            else:
                tx.device_name = f"Unknown Device (0x{addr:02X})"
                tx.device_category = "General I2C Peripheral"
                tx.protocol = "I2C"
                tx.identity_confidence = "unknown"

            ctx = device_context.setdefault(
                addr,
                {"last_cmd": None, "last_offset": None, "vout_exp": self.default_vout_exponent},
            )

            # 1. PMBus Protocol Semantic Decoding
            if tx.protocol == "PMBus":
                if tx.direction == I2CDirection.WRITE:
                    if tx.data_bytes:
                        cmd_code = tx.data_bytes[0]
                        payload = tx.data_bytes[1:]
                        tx.command_code = cmd_code
                        decoded = decode_pmbus_payload(
                            cmd_code, payload, vout_exponent=ctx["vout_exp"]
                        )
                        tx.command_name = decoded.get("command_name")
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded

                        # If VOUT_MODE was written, update exponent in context
                        if cmd_code == 0x20 and payload:
                            from fw_diag_tool.i2c.pmbus import parse_vout_mode_exponent

                            ctx["vout_exp"] = parse_vout_mode_exponent(payload[0])
                        ctx["last_cmd"] = cmd_code
                    else:
                        tx.semantic_summary = "PMBus Quick Command / Address Probe"
                else:
                    cmd_code = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x88
                    tx.command_code = cmd_code
                    if cmd_code == 0x20 and tx.data_bytes:
                        from fw_diag_tool.i2c.pmbus import parse_vout_mode_exponent

                        ctx["vout_exp"] = parse_vout_mode_exponent(tx.data_bytes[0])
                    decoded = decode_pmbus_payload(
                        cmd_code, tx.data_bytes, vout_exponent=ctx["vout_exp"]
                    )
                    tx.command_name = decoded.get("command_name")
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded

            # 2. EEPROM Protocol Semantic Decoding
            elif tx.protocol == "EEPROM" or (chip and "EEPROM" in chip.category):
                if tx.direction == I2CDirection.WRITE:
                    profile = (
                        EEPROM_MODELS.get(self.eeprom_profile) if self.eeprom_profile else None
                    )
                    if not tx.data_bytes:
                        tx.semantic_summary = "EEPROM Write Polling / Address Probe"
                        tx.decoded_values = {
                            "type": "Write Polling / Address Probe",
                            "summary": tx.semantic_summary,
                            "evidence": "address-probe",
                        }
                    elif (
                        chip is None
                        and profile is None
                        and self.default_eeprom_address_bytes is None
                    ):
                        ambiguous_eeprom_writes += 1
                        tx.semantic_summary = (
                            "EEPROM write not decoded: address width/page size unavailable; "
                            "select an explicit EEPROM profile"
                        )
                        tx.decoded_values = {
                            "type": "EEPROM Write (profile required)",
                            "summary": tx.semantic_summary,
                            "evidence": "ambiguous-address-profile",
                            "address_bytes": None,
                            "page_size": None,
                            "candidate_profiles": tx.device_candidates,
                        }
                    else:
                        eep_addr_len = (
                            profile.address_bytes
                            if profile is not None
                            else (
                                self.default_eeprom_address_bytes
                                if self.default_eeprom_address_bytes is not None
                                else chip.default_register_len
                            )
                        )
                        eep_page_size = (
                            self.default_eeprom_page_size
                            if self.default_eeprom_page_size != 16 or profile is None
                            else (chip.extra_info.get("page_size_bytes") if chip else None)
                            or profile.page_size_bytes
                        )
                        decoded = decode_eeprom_write(
                            tx.data_bytes,
                            preferred_address_bytes=eep_addr_len,
                            page_size=eep_page_size,
                        )
                        decoded["evidence"] = "explicit-profile" if profile else "user-configured"
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                        if decoded.get("offset") is not None:
                            ctx["last_offset"] = decoded["offset"]
                else:
                    decoded = decode_eeprom_read(
                        tx.data_bytes, last_known_offset=ctx.get("last_offset")
                    )
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded

            # 3. LM75 / TMP102 / Temperature Sensors
            elif tx.device_category and "Temperature Sensor" in tx.device_category:
                if tx.direction == I2CDirection.WRITE:
                    if tx.data_bytes:
                        ptr = tx.data_bytes[0]
                        ctx["last_cmd"] = ptr
                        ptr_names = {
                            0x00: "TEMP_REG",
                            0x01: "CONFIG_REG",
                            0x02: "THYST_REG",
                            0x03: "TOS_REG",
                        }
                        name = ptr_names.get(ptr, f"PTR_0x{ptr:02X}")
                        tx.semantic_summary = f"Set Register Pointer to {name} (0x{ptr:02X})"
                    else:
                        tx.semantic_summary = "Temperature Sensor Address Probe"
                else:
                    ptr = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x00
                    if ptr == 0x00:
                        decoded = decode_lm75_temperature(tx.data_bytes)
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                    else:
                        tx.semantic_summary = f"Read Register 0x{ptr:02X}: " + " ".join(
                            f"0x{b:02X}" for b in tx.data_bytes
                        )

            # 4. INA219 / INA226 Power Monitors
            elif tx.device_category and "Power Monitor" in tx.device_category:
                if tx.direction == I2CDirection.WRITE:
                    if tx.data_bytes:
                        ptr = tx.data_bytes[0]
                        ctx["last_cmd"] = ptr
                        payload = tx.data_bytes[1:]
                        decoded = decode_ina2xx_power(ptr, payload)
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                    else:
                        tx.semantic_summary = "INA2xx Address Probe"
                else:
                    ptr = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x02
                    decoded = decode_ina2xx_power(ptr, tx.data_bytes)
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded

            # 5. PCA9555 GPIO Expanders
            elif tx.device_category and "GPIO Expander" in tx.device_category:
                if tx.direction == I2CDirection.WRITE:
                    if tx.data_bytes:
                        ptr = tx.data_bytes[0]
                        ctx["last_cmd"] = ptr
                        payload = tx.data_bytes[1:]
                        decoded = decode_pca9555_gpio(ptr, payload)
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                    else:
                        tx.semantic_summary = "GPIO Expander Address Probe"
                else:
                    ptr = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x00
                    decoded = decode_pca9555_gpio(ptr, tx.data_bytes)
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded

            # 6. Generic I2C fallback
            else:
                rw_str = "Write" if tx.direction == I2CDirection.WRITE else "Read"
                tx.semantic_summary = f"{rw_str} {len(tx.data_bytes)} byte(s): {tx.hex_dump}"

        if ambiguous_eeprom_writes:
            return [
                DataQualityIssue(
                    code="I2C_EEPROM_PROFILE_UNAVAILABLE",
                    message=(
                        "EEPROM writes at ambiguous addresses were retained, but offset/page decoding was skipped "
                        "until an explicit EEPROM profile or address-width configuration is supplied."
                    ),
                    count=ambiguous_eeprom_writes,
                )
            ]
        return []

    def analyze(self, events: list[RawI2CEvent]) -> I2CAnalysisReport:
        """Execute full end-to-end diagnostic pipeline on parsed events."""
        self._validate_events(events)
        # A diagnostic engine may be reused for multiple independent captures.  MUX
        # state belongs to one capture and must never leak into the next report.
        self.mux_tracker = I2CMuxTracker()
        transactions = self.group_events_into_transactions(events)
        semantic_quality_issues = self.decode_semantic_layer(transactions)

        known_timestamps = [event.timestamp for event in events if event.timestamp_available]
        total_duration = (
            max(known_timestamps) - min(known_timestamps) if len(known_timestamps) >= 2 else 0.0
        )

        timing_stats = analyze_timing_statistics(transactions, total_duration)
        mux_issues = self.mux_tracker.process_transactions(transactions)
        issues = self.anomaly_detector.analyze_transactions(transactions, timing_stats) + mux_issues
        timestamp_availability = {tx.id: tx.timestamp_available for tx in transactions}
        for issue in issues:
            if issue.transaction_id is not None and not timestamp_availability.get(
                issue.transaction_id, True
            ):
                issue.timestamp = None

        devices_detected: dict[str, dict[str, Any]] = {}
        for tx in transactions:
            addr_hex = f"0x{tx.address_7bit:02X}"
            if addr_hex not in devices_detected:
                devices_detected[addr_hex] = {
                    "address_7bit": addr_hex,
                    "address_8bit": f"0x{tx.address_8bit:02X}",
                    "name": tx.device_name,
                    "category": tx.device_category,
                    "protocol": tx.protocol,
                    "identity_confidence": tx.identity_confidence,
                    "candidates": tx.device_candidates,
                    "transaction_count": 0,
                }
            devices_detected[addr_hex]["transaction_count"] += 1

        data_quality_issues: list[DataQualityIssue] = list(semantic_quality_issues)
        unknown_event_count = sum(event.event_type == RawEventType.UNKNOWN for event in events)
        if unknown_event_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_UNKNOWN_EVENT_TYPE",
                    message=(
                        "Some source rows could not be classified as START/STOP/ADDRESS/DATA; they were "
                        "retained as unknown evidence and excluded from transaction conclusions."
                    ),
                    count=unknown_event_count,
                )
            )
        source_error_count = sum(bool(event.extra.get("source_error")) for event in events)
        if source_error_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_SOURCE_PARSE_ERROR",
                    message=(
                        "Some CSV rows contained invalid address/data tokens; the affected evidence was retained "
                        "as unknown and excluded from protocol conclusions."
                    ),
                    count=source_error_count,
                )
            )
        missing_timestamp_count = sum(not event.timestamp_available for event in events)
        if missing_timestamp_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_TIMESTAMP_UNAVAILABLE",
                    message="Source rows without valid timestamps were retained without timing measurements.",
                    count=missing_timestamp_count,
                )
            )

        timestamp_regressions = 0
        previous_timestamp: float | None = None
        for event in events:
            if not event.timestamp_available:
                continue
            if previous_timestamp is not None and event.timestamp < previous_timestamp:
                timestamp_regressions += 1
            previous_timestamp = event.timestamp
        if timestamp_regressions:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_TIMESTAMP_OUT_OF_ORDER",
                    message="Source timestamps move backwards; chronological timing and transaction durations may be unreliable.",
                    count=timestamp_regressions,
                )
            )

        protocol_events = [
            event
            for event in events
            if event.event_type in (RawEventType.ADDRESS, RawEventType.DATA)
        ]
        missing_ack_count = sum(event.ack in (None, AckType.NONE) for event in protocol_events)
        if missing_ack_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_ACK_UNAVAILABLE",
                    message="Missing ACK/NACK values remain unknown and are excluded from failure rates.",
                    count=missing_ack_count,
                )
            )

        timing_evidence_count = sum(
            bool(
                (event.bit_rate_khz is not None and event.bit_rate_khz > 0)
                or (event.duration_s is not None and event.duration_s > 0)
            )
            for event in protocol_events
        )
        if protocol_events and timing_evidence_count == 0:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_TIMING_UNAVAILABLE",
                    message="No byte duration or bitrate evidence was provided; SCL frequency is unavailable.",
                    count=len(protocol_events),
                )
            )
        elif timing_evidence_count < len(protocol_events):
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_TIMING_PARTIAL",
                    message="Only some protocol events include byte duration or bitrate evidence.",
                    count=len(protocol_events) - timing_evidence_count,
                )
            )

        summary_text = (
            f"Analyzed {len(events)} physical events grouped into {len(transactions)} logical transactions "
            f"across {len(devices_detected)} peripheral device(s). Detected {len(issues)} diagnostic issue(s)."
        )

        return I2CAnalysisReport(
            total_events=len(events),
            total_transactions=len(transactions),
            total_duration_s=total_duration,
            devices_detected=devices_detected,
            transactions=transactions,
            timing_stats=timing_stats,
            issues=issues,
            summary_text=summary_text,
            data_quality_issues=data_quality_issues,
        )

    @staticmethod
    def _validate_events(events: list[RawI2CEvent]) -> None:
        """Reject malformed direct model inputs before timing/grouping can fail ambiguously."""
        if not isinstance(events, list):
            raise TypeError("I2C events must be provided as a list")
        for index, event in enumerate(events):
            if not isinstance(event, RawI2CEvent):
                raise TypeError(f"I2C event {index} must be a RawI2CEvent")
            if (
                isinstance(event.timestamp, bool)
                or not isinstance(event.timestamp, (int, float))
                or not math.isfinite(float(event.timestamp))
                or event.timestamp < 0
            ):
                raise ValueError(f"I2C event {index} timestamp must be finite and non-negative")
            if not isinstance(event.event_type, RawEventType):
                raise TypeError(f"I2C event {index} event_type must be a RawEventType")
            if event.address_7bit is not None and not 0 <= event.address_7bit <= 0x7F:
                raise ValueError(f"I2C event {index} address_7bit must be in range 0..0x7F")
            if event.data_byte is not None and not 0 <= event.data_byte <= 0xFF:
                raise ValueError(f"I2C event {index} data_byte must be in range 0..0xFF")

    def analyze_csv_string(self, csv_text: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze CSV text."""
        events = I2CParser.parse_csv_string(csv_text)
        return self.analyze(events)

    def analyze_csv_file(self, file_path: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze a CSV file from disk."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            events = I2CParser.parse_csv_stream(f)
        return self.analyze(events)

    def analyze_text(self, text_trace: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze a text log trace."""
        events = I2CParser.parse_text_trace(text_trace)
        return self.analyze(events)

    def analyze_records(self, records: list[dict[str, Any]]) -> I2CAnalysisReport:
        """Convenience method to analyze raw Python dictionaries."""
        events = I2CParser.parse_raw_records(records)
        return self.analyze(events)

    def analyze_csv_content(self, csv_text: str) -> I2CAnalysisReport:
        """Backward-compatible alias for :meth:`analyze_csv_string`."""
        return self.analyze_csv_string(csv_text)
