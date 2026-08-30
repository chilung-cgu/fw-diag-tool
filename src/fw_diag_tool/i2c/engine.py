"""I2C / SMBus / PMBus Semantic Analysis, Grouping, and Diagnostic Engine.

Orchestrates trace parsing, transaction boundary grouping, chip identification,
protocol semantic decoding (PMBus, EEPROM, Sensors), timing health analysis,
and actionable diagnostic advice generation.
"""

from __future__ import annotations

import math
from typing import Any

from fw_diag_tool.board_profile import BoardProfile
from fw_diag_tool.errors import ResourceLimitError
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
from fw_diag_tool.limits import AnalysisLimits, coerce_limits

from .mux_tracker import I2CMuxTracker

_DEVICE_IDENTITY_CONFIDENCE_RANK = {
    "unknown": 0,
    "address-only": 1,
    "ambiguous": 2,
    "single-address-candidate": 3,
    "board-profile": 4,
}


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
        board_profile: BoardProfile | None = None,
        *,
        limits: AnalysisLimits | None = None,
    ):
        self.limits = coerce_limits(limits)
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
        if isinstance(default_eeprom_address_bytes, bool) or default_eeprom_address_bytes not in (
            None,
            1,
            2,
        ):
            raise ValueError("default_eeprom_address_bytes must be 1, 2, or None")
        if eeprom_profile is not None and eeprom_profile not in EEPROM_MODELS:
            known_profiles = ", ".join(sorted(EEPROM_MODELS))
            raise ValueError(
                f"unknown eeprom_profile {eeprom_profile!r}; choose one of: {known_profiles}"
            )
        self.default_vout_exponent = default_vout_exponent
        self.default_eeprom_address_bytes = default_eeprom_address_bytes
        self.eeprom_profile = eeprom_profile
        self.board_profile = board_profile
        self.mux_tracker = I2CMuxTracker()
        self.anomaly_detector = I2CAnomalyDetector(
            smbus_timeout_ms=self.smbus_timeout_ms,
            high_jitter_threshold_pct=self.high_jitter_threshold_pct,
            limits=self.limits,
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
        self._validate_events(events)
        if len(events) > self.limits.max_records:
            raise ResourceLimitError(
                f"I2C events exceed the {self.limits.max_records}-record safety limit",
                resource="records",
                limit=self.limits.max_records,
                observed=len(events),
            )
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
                dur = (tx.end_time - tx.start_time) * 1_000_000.0
                if math.isfinite(dur) and dur >= 0:
                    tx.duration_us = dur
                else:
                    tx.duration_us = 0.0
                    tx.timestamp_available = False
            else:
                tx.duration_us = 0.0

        for ev in events:
            event_source_error = bool(ev.extra and ev.extra.get("source_error"))
            # Non-aggregate parser errors belong to the transaction currently
            # being assembled.  Aggregate rows are applied after their
            # address/data event has selected the correct transaction below;
            # applying them here would contaminate the previous packet at a
            # packet-id boundary.
            if (
                current_tx is not None
                and event_source_error
                and not (ev.extra and ev.extra.get("aggregate_ack"))
            ):
                current_tx.source_error = True
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
                            current_tx.ended_by_repeated_start = True
                        transactions.append(current_tx)
                        self._check_transaction_limit(transactions)
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
                    address_available=ev.address_7bit is not None,
                    direction_available=ev.direction is not None,
                    source_error=event_source_error,
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
                        self._check_transaction_limit(transactions)
                    current_tx = None
                continue

            # Explicit BUS_HANG
            if ev.event_type == RawEventType.BUS_HANG:
                if current_tx is not None:
                    current_tx.is_aborted = True
                    current_tx.has_stop = False
                    finish_at_event(current_tx, ev)
                    transactions.append(current_tx)
                    self._check_transaction_limit(transactions)
                    current_tx = None
                else:
                    hang_tx = I2CTransaction(
                        id=tx_counter,
                        start_time=ev.timestamp,
                        end_time=ev.timestamp,
                        address_7bit=0x00,
                        address_8bit=0x00,
                        direction=I2CDirection.WRITE,
                        address_ack=AckType.NONE,
                        has_stop=False,
                        is_aborted=True,
                        timestamp_available=ev.timestamp_available,
                        address_available=False,
                        direction_available=False,
                        source_error=True,
                    )
                    hang_tx.semantic_summary = "Bus Hang / Clock line held low indefinitely"
                    transactions.append(hang_tx)
                    self._check_transaction_limit(transactions)
                    tx_counter += 1
                continue

            # ADDRESS Event
            if ev.event_type == RawEventType.ADDRESS or (
                ev.event_type == RawEventType.UNKNOWN
                and ev.address_7bit is not None
                and ev.data_byte is None
            ):
                addr_7b = ev.address_7bit if ev.address_7bit is not None else 0x00
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

                # A second address without a new START/repeated-START or
                # packet boundary is malformed framing.  The old code
                # overwrote the first address and merged both payloads into a
                # single transaction, which could produce a plausible but
                # false device semantic result.
                duplicate_address = (
                    current_tx is not None
                    and not is_placeholder
                    and not packet_id_changed
                    and getattr(current_tx, "_has_address", False)
                )

                if duplicate_address and current_tx is not None:
                    finish_at_event(current_tx, ev)
                    current_tx.has_stop = False
                    current_tx.source_error = True
                    transactions.append(current_tx)
                    self._check_transaction_limit(transactions)
                    current_tx = None
                    is_placeholder = False

                if current_tx is None or (not is_placeholder and packet_id_changed):
                    if current_tx is not None and (
                        current_tx.byte_packets or getattr(current_tx, "_has_address", False)
                    ):
                        finish_at_event(current_tx, ev)
                        current_tx.has_stop = (
                            True  # packet_id boundary in Saleae represents clean packet framing
                        )
                        transactions.append(current_tx)
                        self._check_transaction_limit(transactions)

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
                        address_available=ev.address_7bit is not None,
                        direction_available=ev.direction is not None,
                        source_error=event_source_error,
                    )
                    current_tx._packet_id = ev.packet_id
                    current_tx._has_address = ev.address_7bit is not None
                    current_tx._is_placeholder = False
                    tx_counter += 1
                else:
                    # Populate existing placeholder
                    current_tx.address_7bit = addr_7b
                    current_tx.address_8bit = addr_8b
                    current_tx.direction = rw
                    current_tx.address_ack = ev.ack or AckType.NONE
                    current_tx.address_available = (
                        current_tx.address_available or ev.address_7bit is not None
                    )
                    current_tx.direction_available = (
                        current_tx.direction_available or ev.direction is not None
                    )
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
                clock_stretch_us = 0.0
                aggregate_clock_stretch_us = 0.0
                if ev.extra and ev.extra.get("aggregate_clock_stretch_unattributable"):
                    aggregate_clock_stretch_us = float(
                        ev.extra.get("aggregate_clock_stretch_us", 0.0)
                    )
                    if aggregate_clock_stretch_us > 0:
                        current_tx.clock_stretching_events.append(
                            {
                                "timestamp": ev.timestamp,
                                "duration_ms": aggregate_clock_stretch_us / 1000.0,
                                "evidence": ev.extra.get(
                                    "aggregate_clock_stretch_evidence", "source_clock_stretch"
                                ),
                                "attribution": "aggregate_unattributable",
                            }
                        )
                elif ev.extra and "clock_stretch_us" in ev.extra:
                    clock_stretch_us = float(ev.extra["clock_stretch_us"])
                if clock_stretch_us > 0:
                    current_tx.clock_stretching_events.append(
                        {
                            "timestamp": ev.timestamp,
                            "duration_ms": clock_stretch_us / 1000.0,
                            "byte_val": f"0x{addr_8b:02X}",
                            "evidence": (
                                ev.extra.get("timing_evidence", "duration-threshold")
                                if ev.extra
                                else "duration-threshold"
                            ),
                        }
                    )
                pkt = I2CBytePacket(
                    timestamp=ev.timestamp,
                    byte_val=addr_8b,
                    is_address=True,
                    direction=ev.direction,
                    ack=ev.ack or AckType.NONE,
                    timestamp_available=ev.timestamp_available,
                    duration_s=dur_s,
                    bit_rate_khz=ev.bit_rate_khz,
                    clock_stretch_us=clock_stretch_us,
                    byte_available=(ev.address_7bit is not None and ev.direction is not None),
                )
                current_tx.byte_packets.append(pkt)
                if event_source_error:
                    current_tx.source_error = True
                if ev.extra and ev.extra.get("aggregate_ack"):
                    aggregate_value = ev.extra.get("aggregate_ack_value")
                    if aggregate_value in {ack.value for ack in AckType}:
                        current_tx.aggregate_ack = AckType(aggregate_value)
                if ev.timestamp_available:
                    current_tx.end_time = ev.timestamp + (dur_s or 0.0)
                    last_byte_end_time = current_tx.end_time
                else:
                    current_tx.timestamp_available = False
                    last_byte_end_time = None
                continue

            # DATA Event
            if ev.event_type == RawEventType.DATA or (
                ev.event_type == RawEventType.UNKNOWN and ev.data_byte is not None
            ):
                data_available = ev.data_byte is not None
                data_val: int = ev.data_byte if ev.data_byte is not None else 0x00

                pkt_changed = (
                    ev.packet_id is not None
                    and current_tx is not None
                    and getattr(current_tx, "_packet_id", None) is not None
                    and ev.packet_id != current_tx._packet_id
                )
                dir_changed = (
                    current_tx is not None
                    and ev.direction is not None
                    and current_tx.direction_available
                    and ev.direction != current_tx.direction
                )
                addr_changed = (
                    current_tx is not None
                    and ev.address_7bit is not None
                    and current_tx.address_available
                    and ev.address_7bit != current_tx.address_7bit
                )
                implicit_boundary = dir_changed or addr_changed
                if current_tx is None or pkt_changed or implicit_boundary:
                    if current_tx is not None and (
                        current_tx.byte_packets or getattr(current_tx, "_has_address", False)
                    ):
                        finish_at_event(current_tx, ev)
                        # A packet-id change is an explicit analyzer frame
                        # boundary.  An address/direction change without one
                        # is only an inferred boundary and must not fabricate
                        # a STOP or a clean transaction result.
                        current_tx.has_stop = not implicit_boundary
                        if implicit_boundary:
                            current_tx.source_error = True
                        transactions.append(current_tx)
                        self._check_transaction_limit(transactions)
                    # Implicit transaction start without explicit START/ADDRESS event
                    addr_7b = ev.address_7bit if ev.address_7bit is not None else 0x00
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
                        address_available=ev.address_7bit is not None,
                        direction_available=ev.direction is not None,
                        source_error=event_source_error or implicit_boundary,
                    )
                    current_tx._packet_id = ev.packet_id
                    current_tx._has_address = ev.address_7bit is not None
                    current_tx._is_placeholder = False
                    tx_counter += 1
                    last_byte_end_time = ev.timestamp if ev.timestamp_available else None
                else:
                    current_tx._is_placeholder = False
                    if ev.address_7bit is not None:
                        current_tx.address_7bit = ev.address_7bit
                        current_tx.address_8bit = (ev.address_7bit << 1) | (
                            1 if ev.direction == I2CDirection.READ else 0
                        )
                        current_tx.address_available = True
                        current_tx._has_address = True
                    if ev.direction is not None:
                        current_tx.direction = ev.direction
                        current_tx.direction_available = True
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
                if ev.extra and "clock_stretch_us" in ev.extra:
                    clock_stretch_us = float(ev.extra["clock_stretch_us"])
                if clock_stretch_us > 0:
                    current_tx.clock_stretching_events.append(
                        {
                            "timestamp": ev.timestamp,
                            "duration_ms": clock_stretch_us / 1000.0,
                            "byte_val": f"0x{data_val:02X}",
                            "evidence": (
                                ev.extra.get("timing_evidence", "duration-threshold")
                                if ev.extra
                                else "duration-threshold"
                            ),
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
                    byte_available=data_available,
                )
                current_tx.byte_packets.append(pkt)
                if event_source_error:
                    current_tx.source_error = True
                if ev.extra and ev.extra.get("aggregate_ack"):
                    aggregate_value = ev.extra.get("aggregate_ack_value")
                    if aggregate_value in {ack.value for ack in AckType}:
                        current_tx.aggregate_ack = AckType(aggregate_value)
                if data_available:
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
                dur = (current_tx.end_time - current_tx.start_time) * 1_000_000.0
                if math.isfinite(dur) and dur >= 0:
                    current_tx.duration_us = dur
                else:
                    current_tx.duration_us = 0.0
                    current_tx.timestamp_available = False
            else:
                current_tx.duration_us = 0.0
            transactions.append(current_tx)
            self._check_transaction_limit(transactions)

        return transactions

    def _check_transaction_limit(self, transactions: list[I2CTransaction]) -> None:
        if len(transactions) > self.limits.max_transactions:
            raise ResourceLimitError(
                f"I2C capture exceeds the {self.limits.max_transactions}-transaction safety limit",
                resource="transactions",
                limit=self.limits.max_transactions,
                observed=len(transactions),
            )

    def decode_semantic_layer(self, transactions: list[I2CTransaction]) -> list[DataQualityIssue]:
        """Perform chip identification and protocol semantic decoding across transactions."""
        device_context: dict[Any, dict[str, Any]] = {}
        ambiguous_eeprom_writes = 0
        eeprom_truncated = 0
        eeprom_out_of_range = 0
        pmbus_truncated = 0
        pmbus_block_mismatch = 0
        pmbus_block_invalid = 0
        pmbus_overlong = 0
        pmbus_phase_mismatch = 0
        sensor_truncated = 0
        sensor_overlong = 0
        address_nack_data = 0
        address_nack_semantic_unavailable = 0
        data_nack_semantic_unavailable = 0
        semantic_source_error = 0
        ambiguous_board_profile_addresses = 0

        for tx in transactions:
            if tx.device_category == "I2C Multiplexer (PCA9548A/PCA9546)":
                if tx.device_name is None and tx.address_available:
                    tx.device_name = f"Unknown Device (0x{tx.address_7bit:02X})"
                if tx.protocol is None:
                    tx.protocol = "I2C"
                if tx.identity_confidence is None:
                    tx.identity_confidence = "unknown"
                continue
            if not tx.address_available:
                tx.device_name = "Unknown Device (address unavailable)"
                tx.device_category = "Unknown / Incomplete Address Evidence"
                tx.protocol = "I2C"
                tx.identity_confidence = "unavailable"
                tx.semantic_summary = "Address unavailable; semantic decoding withheld"
                tx.decoded_values = {
                    "evidence": "source-error" if tx.source_error else "address-unavailable"
                }
                continue
            if not tx.direction_available:
                tx.device_name = f"Possible Device (0x{tx.address_7bit:02X})"
                tx.device_category = "Direction unavailable"
                tx.protocol = "I2C"
                tx.identity_confidence = "address-only"
                tx.semantic_summary = "Read/write direction unavailable; semantic decoding withheld"
                tx.decoded_values = {
                    "evidence": "source-error" if tx.source_error else "direction-unavailable"
                }
                continue
            # Establish explicit, non-null identity fallbacks before the
            # conservative source/aggregate-ACK exits below.  A decoded row
            # may prove only an address while still lacking per-byte ACK
            # attribution; the UI must show that as Unknown rather than an
            # empty device/category cell.
            if tx.device_name is None:
                tx.device_name = f"Unknown Device (0x{tx.address_7bit:02X})"
            if tx.device_category is None:
                tx.device_category = "General I2C Peripheral"
            if tx.protocol is None:
                tx.protocol = "I2C"
            if tx.identity_confidence is None:
                tx.identity_confidence = "unknown"
            if tx.source_error and tx.aggregate_ack == AckType.NONE:
                tx.semantic_summary = "Source field invalid; semantic decoding withheld"
                tx.decoded_values = {"evidence": "source-error"}
                semantic_source_error += 1
                continue
            if tx.aggregate_ack != AckType.NONE:
                tx.semantic_summary = "ACK attribution unavailable; semantic decoding withheld"
                tx.decoded_values = {
                    "evidence": "aggregate-ack",
                    "aggregate_ack": tx.aggregate_ack.value,
                }
                continue
            if any(
                not packet.byte_available for packet in tx.byte_packets if not packet.is_address
            ):
                tx.semantic_summary = "Data byte unavailable; semantic decoding withheld"
                tx.decoded_values = {"evidence": "data-unavailable"}
                continue
            if tx.address_ack == AckType.NACK and tx.data_bytes:
                tx.semantic_summary = (
                    "Address NACK with subsequent data; semantic decoding withheld"
                )
                tx.decoded_values = {"evidence": "address-nack-data-present"}
                address_nack_data += 1
                continue
            addr = tx.address_7bit
            profile_matches: list[Any] = []
            if self.board_profile is not None:
                for bus in self.board_profile.i2c_buses:
                    bus_matches: list[Any] = []
                    if tx.mux_channels:
                        for mux in bus.muxes:
                            for ch in mux.channels:
                                if ch.channel in tx.mux_channels:
                                    for d in ch.devices:
                                        if d.address_7bit == addr:
                                            bus_matches.append(d)
                    if not bus_matches:
                        for d in bus.devices:
                            if d.address_7bit == addr:
                                bus_matches.append(d)
                    profile_matches.extend(bus_matches)

            if len(profile_matches) > 1:
                ambiguous_board_profile_addresses += 1
                tx.device_name = f"Ambiguous Board Profile (0x{addr:02X})"
                tx.device_category = "Ambiguous Board Profile Address"
                tx.protocol = "I2C"
                tx.identity_confidence = "ambiguous"
                tx.device_candidates = [profile.name for profile in profile_matches]
                tx.semantic_summary = (
                    "Board profile maps this address to multiple buses/devices; "
                    "bus context is unavailable, so semantic decoding was withheld"
                )
                tx.decoded_values = {
                    "evidence": "ambiguous-board-profile",
                    "candidate_profiles": tx.device_candidates,
                }
                continue
            dev_profile = profile_matches[0] if profile_matches else None

            candidates = get_all_matching_devices(addr)
            chip = lookup_device(addr) if len(candidates) == 1 else None
            tx.device_candidates = [candidate.name for candidate in candidates]
            if dev_profile is not None:
                tx.device_name = dev_profile.name
                tx.device_category = dev_profile.category
                tx.protocol = dev_profile.protocol
                tx.identity_confidence = "board-profile"
                tx.device_candidates = [dev_profile.name]
            elif chip is not None:
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

            # An address NACK means the target did not accept this transfer.
            # It can still be useful evidence for address diagnostics (and the
            # anomaly detector may identify EEPROM ACK polling), but it is not
            # evidence of a valid command/probe payload.  Do not label it as a
            # successful "address probe" or feed it into device context.
            if tx.address_ack == AckType.NACK:
                tx.semantic_summary = (
                    "Address NACK; target did not acknowledge the address; "
                    "semantic decoding withheld"
                )
                tx.decoded_values = {
                    "evidence": "address-nack",
                    "address_accepted": False,
                }
                address_nack_semantic_unavailable += 1
                continue

            # A NACK on write data or before the final byte of a read means the
            # payload was rejected/terminated early.  The final controller
            # NACK on a read is intentionally excluded by
            # ``has_unexpected_data_nack`` and remains normal termination.
            if tx.has_unexpected_data_nack:
                tx.semantic_summary = (
                    "Unexpected data NACK; payload was not fully accepted; "
                    "semantic decoding withheld"
                )
                tx.decoded_values = {
                    "evidence": "data-nack-present",
                    "payload_accepted": False,
                }
                data_nack_semantic_unavailable += 1
                continue

            context_key = (tuple(tx.mux_channels) if tx.mux_channels else None, addr)
            ctx = device_context.setdefault(
                context_key,
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
                            cmd_code, payload, vout_exponent=ctx["vout_exp"], phase="write"
                        )
                        tx.command_name = decoded.get("command_name")
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                        if decoded.get("evidence") == "truncated":
                            pmbus_truncated += 1
                        elif decoded.get("evidence") == "block-count-mismatch":
                            pmbus_block_mismatch += 1
                        elif decoded.get("evidence") == "block-count-invalid":
                            pmbus_block_invalid += 1
                        elif decoded.get("evidence") == "overlong":
                            pmbus_overlong += 1
                        elif decoded.get("evidence") == "phase-mismatch":
                            pmbus_phase_mismatch += 1

                        # Only an accepted/complete VOUT_MODE payload may
                        # change the decoder context.  Truncated, overlong, or
                        # phase-invalid bytes are source evidence, not a new
                        # exponent to apply to later telemetry.
                        if cmd_code == 0x20 and payload and decoded.get("is_complete") is True:
                            from fw_diag_tool.i2c.pmbus import parse_vout_mode_exponent

                            ctx["vout_exp"] = parse_vout_mode_exponent(payload[0])
                        if decoded.get("evidence") not in {
                            "truncated",
                            "overlong",
                            "phase-mismatch",
                            "block-count-mismatch",
                            "block-count-invalid",
                        } or (not payload and decoded.get("evidence") == "truncated"):
                            # A command-select write (read-only command with
                            # no payload) is valid context even when a
                            # command definition also permits a write payload
                            # and the decoder reports a missing response byte.
                            ctx["last_cmd"] = cmd_code
                    else:
                        tx.semantic_summary = "PMBus Quick Command / Address Probe"
                else:
                    cmd_code = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x88
                    tx.command_code = cmd_code
                    decoded = decode_pmbus_payload(
                        cmd_code, tx.data_bytes, vout_exponent=ctx["vout_exp"], phase="read"
                    )
                    tx.command_name = decoded.get("command_name")
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded
                    if decoded.get("evidence") == "truncated":
                        pmbus_truncated += 1
                    elif decoded.get("evidence") == "block-count-mismatch":
                        pmbus_block_mismatch += 1
                    elif decoded.get("evidence") == "block-count-invalid":
                        pmbus_block_invalid += 1
                    elif decoded.get("evidence") == "overlong":
                        pmbus_overlong += 1
                    elif decoded.get("evidence") == "phase-mismatch":
                        pmbus_phase_mismatch += 1
                    if cmd_code == 0x20 and tx.data_bytes and decoded.get("is_complete") is True:
                        from fw_diag_tool.i2c.pmbus import parse_vout_mode_exponent

                        ctx["vout_exp"] = parse_vout_mode_exponent(tx.data_bytes[0])

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
                                else (chip.default_register_len if chip is not None else 1)
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
                            capacity_bytes=(profile.capacity_kbits * 128 if profile else None),
                        )
                        decoder_evidence = decoded.get("evidence")
                        if decoder_evidence not in {"truncated", "address-out-of-range"}:
                            decoded["evidence"] = (
                                "explicit-profile" if profile else "user-configured"
                            )
                        tx.semantic_summary = decoded.get("summary")
                        tx.decoded_values = decoded
                        if decoder_evidence == "truncated":
                            eeprom_truncated += 1
                        elif decoder_evidence == "address-out-of-range":
                            eeprom_out_of_range += 1
                        if (
                            decoder_evidence not in {"truncated", "address-out-of-range"}
                            and decoded.get("offset") is not None
                        ):
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
                        if decoded.get("evidence") == "truncated":
                            sensor_truncated += 1
                        elif decoded.get("evidence") == "overlong":
                            sensor_overlong += 1
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
                        if decoded.get("evidence") == "truncated":
                            sensor_truncated += 1
                        elif decoded.get("evidence") == "overlong":
                            sensor_overlong += 1
                    else:
                        tx.semantic_summary = "INA2xx Address Probe"
                else:
                    ptr = int(ctx["last_cmd"]) if ctx.get("last_cmd") is not None else 0x02
                    decoded = decode_ina2xx_power(ptr, tx.data_bytes)
                    tx.semantic_summary = decoded.get("summary")
                    tx.decoded_values = decoded
                    if decoded.get("evidence") == "truncated":
                        sensor_truncated += 1
                    elif decoded.get("evidence") == "overlong":
                        sensor_overlong += 1

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

        quality_issues: list[DataQualityIssue] = []
        if ambiguous_eeprom_writes:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_EEPROM_PROFILE_UNAVAILABLE",
                    message=(
                        "EEPROM writes at ambiguous addresses were retained, but offset/page decoding was skipped "
                        "until an explicit EEPROM profile or address-width configuration is supplied."
                    ),
                    count=ambiguous_eeprom_writes,
                )
            )
        if eeprom_truncated:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_EEPROM_ADDRESS_TRUNCATED",
                    message=(
                        "An EEPROM write selected a profile requiring a 2-byte offset, but the "
                        "capture contained only one address byte; offset and payload decoding was withheld."
                    ),
                    count=eeprom_truncated,
                )
            )
        if eeprom_out_of_range:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_EEPROM_ADDRESS_OUT_OF_RANGE",
                    message=(
                        "An EEPROM write selected a profile whose captured offset or payload exceeds the "
                        "configured memory capacity; address/payload interpretation was withheld."
                    ),
                    count=eeprom_out_of_range,
                )
            )
        if pmbus_truncated:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_PMBUS_PAYLOAD_TRUNCATED",
                    message=(
                        "A PMBus command response did not contain the number of bytes declared by "
                        "the command definition; telemetry/status interpretation was withheld."
                    ),
                    count=pmbus_truncated,
                )
            )
        if pmbus_block_mismatch:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_PMBUS_BLOCK_COUNT_MISMATCH",
                    message=(
                        "A PMBus block-read byte count disagreed with the captured payload; the "
                        "string/telemetry result is incomplete."
                    ),
                    count=pmbus_block_mismatch,
                )
            )
        if pmbus_block_invalid:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_PMBUS_BLOCK_COUNT_INVALID",
                    message=(
                        "A PMBus block-read count exceeded the SMBus/PMBus 32-byte limit; "
                        "the manufacturer data was withheld."
                    ),
                    count=pmbus_block_invalid,
                )
            )
        if pmbus_overlong:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_PMBUS_PAYLOAD_OVERLONG",
                    message=(
                        "A PMBus fixed-length command contained extra payload bytes; "
                        "telemetry/status interpretation was withheld."
                    ),
                    count=pmbus_overlong,
                )
            )
        if pmbus_phase_mismatch:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_PMBUS_PHASE_MISMATCH",
                    message=(
                        "A PMBus payload was observed in a direction where the command definition "
                        "does not permit it; semantic decoding was withheld."
                    ),
                    count=pmbus_phase_mismatch,
                )
            )
        if sensor_truncated:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_SENSOR_PAYLOAD_TRUNCATED",
                    message=(
                        "A sensor register response contained fewer bytes than its decoder requires; "
                        "the partial value is retained but not treated as a complete reading."
                    ),
                    count=sensor_truncated,
                )
            )
        if sensor_overlong:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_SENSOR_PAYLOAD_OVERLONG",
                    message=(
                        "A sensor register response contained extra bytes beyond the fixed register width; "
                        "the decoder withheld a complete sensor value."
                    ),
                    count=sensor_overlong,
                )
            )
        if address_nack_data:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_ADDRESS_NACK_DATA_PRESENT",
                    message=(
                        "Data bytes followed an address NACK; the target did not acknowledge the "
                        "transaction address, so semantic payload decoding was withheld."
                    ),
                    count=address_nack_data,
                )
            )
        if address_nack_semantic_unavailable:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_ADDRESS_NACK_SEMANTIC_UNAVAILABLE",
                    message=(
                        "Transactions whose address byte was NACKed were retained for "
                        "address diagnostics, but were not treated as accepted device or "
                        "command evidence."
                    ),
                    count=address_nack_semantic_unavailable,
                )
            )
        if data_nack_semantic_unavailable:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_DATA_NACK_SEMANTIC_UNAVAILABLE",
                    message=(
                        "A write-data NACK or an intermediate read NACK occurred; the "
                        "captured payload was not treated as a complete accepted command "
                        "or telemetry value."
                    ),
                    count=data_nack_semantic_unavailable,
                )
            )
        if semantic_source_error:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_SEMANTIC_EVIDENCE_INCOMPLETE",
                    message=(
                        "At least one transaction contains an invalid source field; protocol and "
                        "device-specific semantic decoding was withheld for that transaction."
                    ),
                    count=semantic_source_error,
                )
            )
        if ambiguous_board_profile_addresses:
            quality_issues.append(
                DataQualityIssue(
                    code="I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS",
                    message=(
                        "A board profile maps an observed address to multiple buses/devices, "
                        "but the capture has no bus identity; device-specific semantic decoding "
                        "was withheld instead of selecting an arbitrary profile."
                    ),
                    count=ambiguous_board_profile_addresses,
                )
            )
        return quality_issues

    def analyze(self, events: list[RawI2CEvent]) -> I2CAnalysisReport:
        """Execute full end-to-end diagnostic pipeline on parsed events."""
        # A diagnostic engine may be reused for multiple independent captures.  MUX
        # state belongs to one capture and must never leak into the next report.
        self.mux_tracker = I2CMuxTracker()
        transactions = self.group_events_into_transactions(events)
        mux_issues = self.mux_tracker.process_transactions(transactions)
        semantic_quality_issues = self.decode_semantic_layer(transactions)

        known_timestamps = [event.timestamp for event in events if event.timestamp_available]
        total_duration = (
            max(known_timestamps) - min(known_timestamps) if len(known_timestamps) >= 2 else 0.0
        )

        timing_stats = analyze_timing_statistics(transactions, total_duration)
        if any(
            event.extra and event.extra.get("timing_evidence") == "raw_scl_period_delta"
            for event in events
        ):
            # Raw adapter timing is derived from captured SCL edges, whereas
            # decoded analyzer timing comes from source table fields.
            if timing_stats.frequency_sample_count:
                timing_stats.frequency_evidence = "measured"
            if timing_stats.bus_utilization_evidence != "unavailable":
                timing_stats.bus_utilization_evidence = "measured"
        issues = self.anomaly_detector.analyze_transactions(transactions, timing_stats) + mux_issues
        if len(issues) > self.limits.max_findings:
            raise ResourceLimitError(
                f"I2C findings exceed the {self.limits.max_findings}-finding safety limit",
                resource="findings",
                limit=self.limits.max_findings,
                observed=len(issues),
            )
        timestamp_availability = {tx.id: tx.timestamp_available for tx in transactions}
        for issue in issues:
            if issue.transaction_id is not None and not timestamp_availability.get(
                issue.transaction_id, True
            ):
                issue.timestamp = None

        devices_detected: dict[str, dict[str, Any]] = {}
        for tx in transactions:
            if not tx.address_available:
                continue
            addr_hex = f"0x{tx.address_7bit:02X}"
            device = devices_detected.get(addr_hex)
            if device is None:
                device = {
                    "address_7bit": addr_hex,
                    "address_8bit": f"0x{tx.address_8bit:02X}",
                    "name": tx.device_name,
                    "category": tx.device_category,
                    "protocol": tx.protocol,
                    "identity_confidence": tx.identity_confidence,
                    "candidates": tx.device_candidates,
                    "transaction_count": 0,
                }
                devices_detected[addr_hex] = device
            elif _DEVICE_IDENTITY_CONFIDENCE_RANK.get(
                tx.identity_confidence or "unknown", 0
            ) > _DEVICE_IDENTITY_CONFIDENCE_RANK.get(
                device.get("identity_confidence") or "unknown", 0
            ):
                device.update(
                    {
                        "name": tx.device_name,
                        "category": tx.device_category,
                        "protocol": tx.protocol,
                        "identity_confidence": tx.identity_confidence,
                        "candidates": tx.device_candidates,
                    }
                )
            device["transaction_count"] += 1

        data_quality_issues: list[DataQualityIssue] = list(semantic_quality_issues)
        reserved_address_count = sum(
            tx.address_available and not 0x08 <= tx.address_7bit <= 0x77 for tx in transactions
        )
        if reserved_address_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_RESERVED_ADDRESS_CANDIDATE",
                    message=(
                        "Some transactions use an I2C reserved 7-bit address (outside 0x08..0x77). "
                        "The address was retained for forensic inspection, but it is not a normal device "
                        "identity candidate and the packet builder will reject it."
                    ),
                    count=reserved_address_count,
                )
            )
        if not events:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_SOURCE_EMPTY",
                    message=(
                        "The capture contains no data rows after ignoring blank/comment lines; "
                        "there is no protocol evidence to classify as clean."
                    ),
                    count=1,
                )
            )
        elif not transactions:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_SOURCE_NO_TRANSACTIONS",
                    message=(
                        "The source contained framing or unknown events but no complete logical I2C "
                        "transaction; this input cannot be classified as a clean capture."
                    ),
                    count=1,
                )
            )
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
        source_error_count = sum(
            bool(event.extra and event.extra.get("source_error")) for event in events
        )
        if source_error_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_SOURCE_PARSE_ERROR",
                    message=(
                        "Some CSV rows contained invalid or incomplete fields (schema, address/data, timing, "
                        "direction, or ACK); affected evidence was retained as unknown and excluded from "
                        "protocol conclusions."
                    ),
                    count=source_error_count,
                )
            )
        aggregate_ack_count = sum(
            bool(event.extra and event.extra.get("aggregate_ack")) for event in events
        )
        if aggregate_ack_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_ACK_AGGREGATE_UNATTRIBUTABLE",
                    message=(
                        "A multi-byte analyzer summary supplied one aggregate ACK/NACK; "
                        "per-byte ACK attribution and semantic payload acceptance were withheld."
                    ),
                    count=aggregate_ack_count,
                )
            )
        aggregate_timing_count = sum(
            bool(
                event.extra
                and (
                    event.extra.get("aggregate_duration_unattributable")
                    or event.extra.get("aggregate_clock_stretch_unattributable")
                )
            )
            for event in events
        )
        if aggregate_timing_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_TIMING_AGGREGATE_UNATTRIBUTABLE",
                    message=(
                        "An aggregate analyzer row supplied one Duration or Clock Stretch value for address "
                        "plus data bytes; the value was retained as source metadata but not attributed to "
                        "per-byte timing or waveform overlays."
                    ),
                    count=aggregate_timing_count,
                )
            )

        address_unavailable_count = sum(not tx.address_available for tx in transactions)
        if address_unavailable_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_ADDRESS_UNAVAILABLE",
                    message=(
                        "Some transactions do not contain a trustworthy 7-bit address; device mapping, "
                        "NACK attribution, and semantic decoding were withheld for those transactions."
                    ),
                    count=address_unavailable_count,
                )
            )
        direction_unavailable_count = sum(
            not tx.direction_available for tx in transactions if tx.address_available
        )
        if direction_unavailable_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_DIRECTION_UNAVAILABLE",
                    message=(
                        "Some transactions contain an address but no trustworthy READ/WRITE direction; "
                        "direction-dependent semantic conclusions were withheld."
                    ),
                    count=direction_unavailable_count,
                )
            )
        data_unavailable_count = sum(
            not packet.byte_available
            for tx in transactions
            for packet in tx.byte_packets
            if not packet.is_address
        )
        if data_unavailable_count:
            data_quality_issues.append(
                DataQualityIssue(
                    code="I2C_DATA_UNAVAILABLE",
                    message=(
                        "Some data-byte positions are present in the source but their byte value is unavailable; "
                        "they were excluded from payload and anomaly conclusions."
                    ),
                    count=data_unavailable_count,
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
            if event.event_type == RawEventType.ADDRESS and event.data_byte is not None:
                raise ValueError(
                    f"I2C event {index} ADDRESS cannot carry data_byte; use a DATA event"
                )
            if event.event_type in {
                RawEventType.START,
                RawEventType.REPEATED_START,
                RawEventType.STOP,
                RawEventType.BUS_HANG,
            } and any(
                value is not None
                for value in (
                    event.address_7bit,
                    event.direction,
                    event.data_byte,
                    event.ack if event.ack not in (None, AckType.NONE) else None,
                )
            ):
                raise ValueError(
                    f"I2C event {index} {event.event_type.value} cannot carry address, "
                    "direction, data, or ACK fields"
                )
            if not isinstance(event.timestamp_available, bool):
                raise TypeError(f"I2C event {index} timestamp_available must be boolean")
            if event.extra is not None and not isinstance(event.extra, dict):
                raise TypeError(f"I2C event {index} extra must be a mapping or None")
            if event.extra and "clock_stretch_us" in event.extra:
                stretch_us = event.extra["clock_stretch_us"]
                if (
                    isinstance(stretch_us, bool)
                    or not isinstance(stretch_us, (int, float))
                    or not math.isfinite(float(stretch_us))
                    or stretch_us < 0
                ):
                    raise ValueError(
                        f"I2C event {index} clock_stretch_us must be finite and non-negative"
                    )
            if event.direction is not None and not isinstance(event.direction, I2CDirection):
                raise TypeError(f"I2C event {index} direction must be an I2CDirection")
            if event.ack is not None and not isinstance(event.ack, AckType):
                raise TypeError(f"I2C event {index} ack must be an AckType")
            if event.address_7bit is not None and (
                isinstance(event.address_7bit, bool)
                or not isinstance(event.address_7bit, int)
                or not 0 <= event.address_7bit <= 0x7F
            ):
                raise ValueError(f"I2C event {index} address_7bit must be in range 0..0x7F")
            if event.data_byte is not None and (
                isinstance(event.data_byte, bool)
                or not isinstance(event.data_byte, int)
                or not 0 <= event.data_byte <= 0xFF
            ):
                raise ValueError(f"I2C event {index} data_byte must be in range 0..0xFF")
            if event.packet_id is not None and (
                isinstance(event.packet_id, bool)
                or not isinstance(event.packet_id, int)
                or event.packet_id < 0
            ):
                raise ValueError(f"I2C event {index} packet_id must be a non-negative integer")
            for field_name, field_value in (
                ("duration_s", event.duration_s),
                ("bit_rate_khz", event.bit_rate_khz),
            ):
                if field_value is not None and (
                    isinstance(field_value, bool)
                    or not isinstance(field_value, (int, float))
                    or not math.isfinite(float(field_value))
                    or field_value <= 0
                ):
                    raise ValueError(
                        f"I2C event {index} {field_name} must be a positive finite number"
                    )

    def analyze_csv_string(self, csv_text: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze CSV text."""
        events = I2CParser.parse_csv_string(csv_text, limits=self.limits)
        return self.analyze(events)

    def analyze_csv_file(self, file_path: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze a CSV file from disk."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            events = I2CParser.parse_csv_stream(f, limits=self.limits)
        return self.analyze(events)

    def analyze_text(self, text_trace: str) -> I2CAnalysisReport:
        """Convenience method to parse and analyze a text log trace."""
        events = I2CParser.parse_text_trace(text_trace, limits=self.limits)
        return self.analyze(events)

    def analyze_records(self, records: list[dict[str, Any]]) -> I2CAnalysisReport:
        """Convenience method to analyze raw Python dictionaries."""
        events = I2CParser.parse_raw_records(records, limits=self.limits)
        return self.analyze(events)

    def analyze_csv_content(self, csv_text: str) -> I2CAnalysisReport:
        """Backward-compatible alias for :meth:`analyze_csv_string`."""
        return self.analyze_csv_string(csv_text)
