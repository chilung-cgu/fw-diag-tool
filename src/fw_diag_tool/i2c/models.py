"""I2C, SMBus, and PMBus Data Models and Diagnostic Dataclasses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class I2CDirection(str, Enum):
    """I2C Bus Transfer Direction."""
    WRITE = "WRITE"
    READ = "READ"

    @property
    def bit(self) -> int:
        return 1 if self == I2CDirection.READ else 0


class AckType(str, Enum):
    """Acknowledge bit state."""
    ACK = "ACK"      # 0 on SDA (Acknowledge)
    NACK = "NACK"    # 1 on SDA (Not Acknowledge)
    NONE = "NONE"    # Missing or unknown (e.g. bus hang)


class I2CSpeedMode(str, Enum):
    """I2C / SMBus nominal clock frequency class."""
    STANDARD_100K = "Standard-mode (100 kHz)"
    FAST_400K = "Fast-mode (400 kHz)"
    FAST_PLUS_1M = "Fast-mode Plus (1 MHz)"
    HIGH_SPEED_3M4 = "High-speed mode (3.4 MHz)"
    UNKNOWN = "Custom / Unknown Speed"


class Severity(str, Enum):
    """Diagnostic anomaly severity level."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class RawEventType(str, Enum):
    """Type of raw I2C physical/protocol event."""
    START = "START"
    REPEATED_START = "REPEATED_START"
    STOP = "STOP"
    ADDRESS = "ADDRESS"
    DATA = "DATA"
    BUS_HANG = "BUS_HANG"
    UNKNOWN = "UNKNOWN"


@dataclass
class RawI2CEvent:
    """Raw I2C event extracted directly from Logic Analyzer or trace."""
    timestamp: float
    event_type: RawEventType
    packet_id: int | None = None
    address_7bit: int | None = None
    direction: I2CDirection | None = None
    data_byte: int | None = None
    ack: AckType | None = None
    duration_s: float | None = None
    bit_rate_khz: float | None = None
    raw_text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class I2CBytePacket:
    """Single byte transfer with timing and ACK context."""
    timestamp: float
    byte_val: int
    is_address: bool
    direction: I2CDirection | None
    ack: AckType
    duration_s: float = 0.0
    bit_rate_khz: float | None = None
    inter_byte_delay_us: float = 0.0
    clock_stretch_us: float = 0.0


@dataclass
class I2CTransaction:
    """Complete logical I2C transaction bounded by Start/Repeated-Start and Stop."""
    id: int
    start_time: float
    end_time: float
    address_7bit: int
    address_8bit: int
    direction: I2CDirection
    data_bytes: list[int] = field(default_factory=list)
    byte_packets: list[I2CBytePacket] = field(default_factory=list)
    address_ack: AckType = AckType.ACK
    is_repeated_start: bool = False
    has_stop: bool = False
    is_aborted: bool = False
    duration_us: float = 0.0
    
    # Peripheral & Protocol Semantic Decoding
    device_name: str | None = None
    device_category: str | None = None
    protocol: str | None = None  # "I2C", "SMBus", "PMBus", "EEPROM"
    command_name: str | None = None
    command_code: int | None = None
    semantic_summary: str | None = None
    decoded_values: dict[str, Any] = field(default_factory=dict)
    
    # Diagnostics & Timing
    anomalies: list[str] = field(default_factory=list)
    inter_byte_delays_us: list[float] = field(default_factory=list)
    clock_stretching_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hex_dump(self) -> str:
        """Format data bytes as readable hex string."""
        if not self.data_bytes:
            return "[]"
        return "[" + ", ".join(f"0x{b:02X}" for b in self.data_bytes) + "]"


@dataclass
class I2CDiagnosticIssue:
    """Diagnostic issue identified with root-cause analysis and actionable advice."""
    code: str
    title: str
    severity: Severity
    category: str  # "Physical/Timing", "Protocol", "Semantic/Data", "Hardware"
    description: str
    root_cause_analysis: str
    actionable_advice: list[str]
    timestamp: float | None = None
    transaction_id: int | None = None
    address_7bit: int | None = None
    affected_bytes: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity.value,
            "category": self.category,
            "timestamp": self.timestamp,
            "transaction_id": self.transaction_id,
            "address_7bit": f"0x{self.address_7bit:02X}" if self.address_7bit is not None else None,
            "description": self.description,
            "root_cause_analysis": self.root_cause_analysis,
            "actionable_advice": self.actionable_advice,
            "affected_bytes": [f"0x{b:02X}" for b in self.affected_bytes] if self.affected_bytes else None,
        }


@dataclass
class TimingStatistics:
    """Bus clock frequency and timing jitter profile."""
    avg_frequency_khz: float = 0.0
    min_frequency_khz: float = 0.0
    max_frequency_khz: float = 0.0
    frequency_jitter_pct: float = 0.0
    speed_mode: I2CSpeedMode = I2CSpeedMode.UNKNOWN
    clock_stretch_count: int = 0
    max_clock_stretch_ms: float = 0.0
    avg_clock_stretch_ms: float = 0.0
    avg_inter_byte_delay_us: float = 0.0
    max_inter_byte_delay_us: float = 0.0
    avg_inter_transaction_delay_ms: float = 0.0
    max_inter_transaction_delay_ms: float = 0.0
    bus_utilization_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_frequency_khz": round(self.avg_frequency_khz, 2),
            "min_frequency_khz": round(self.min_frequency_khz, 2),
            "max_frequency_khz": round(self.max_frequency_khz, 2),
            "frequency_jitter_pct": round(self.frequency_jitter_pct, 2),
            "speed_mode": self.speed_mode.value,
            "clock_stretch_count": self.clock_stretch_count,
            "max_clock_stretch_ms": round(self.max_clock_stretch_ms, 3),
            "avg_clock_stretch_ms": round(self.avg_clock_stretch_ms, 3),
            "avg_inter_byte_delay_us": round(self.avg_inter_byte_delay_us, 2),
            "max_inter_byte_delay_us": round(self.max_inter_byte_delay_us, 2),
            "avg_inter_transaction_delay_ms": round(self.avg_inter_transaction_delay_ms, 3),
            "max_inter_transaction_delay_ms": round(self.max_inter_transaction_delay_ms, 3),
            "bus_utilization_pct": round(self.bus_utilization_pct, 2),
        }


@dataclass
class I2CAnalysisReport:
    """Comprehensive structured report containing all transactions and diagnostic findings."""
    total_events: int
    total_transactions: int
    total_duration_s: float
    devices_detected: dict[str, dict[str, Any]]
    transactions: list[I2CTransaction]
    timing_stats: TimingStatistics
    issues: list[I2CDiagnosticIssue]
    summary_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                 "total_events": self.total_events,
                 "total_transactions": self.total_transactions,
                 "total_duration_s": round(self.total_duration_s, 6),
                 "devices_count": len(self.devices_detected),
                 "issues_count": len(self.issues),
                 "summary_text": self.summary_text,
            },
            "timing_stats": self.timing_stats.to_dict(),
            "devices_detected": self.devices_detected,
            "issues": [issue.to_dict() for issue in self.issues],
            "transactions": [
                 {
                     "id": tx.id,
                     "start_time": round(tx.start_time, 6),
                     "end_time": round(tx.end_time, 6),
                     "duration_us": round(tx.duration_us, 2),
                     "address_7bit": f"0x{tx.address_7bit:02X}",
                     "address_8bit": f"0x{tx.address_8bit:02X}",
                     "direction": tx.direction.value,
                     "address_ack": tx.address_ack.value,
                     "data_hex": tx.hex_dump,
                     "byte_count": len(tx.data_bytes),
                     "has_stop": tx.has_stop,
                     "is_repeated_start": tx.is_repeated_start,
                     "device_name": tx.device_name,
                     "protocol": tx.protocol,
                     "semantic_summary": tx.semantic_summary,
                     "decoded_values": tx.decoded_values,
                     "anomalies": tx.anomalies,
                 }
                 for tx in self.transactions
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
