"""I2C, SMBus, and PMBus Diagnostic Analysis Package."""

from fw_diag_tool.i2c.anomaly import I2CAnomalyDetector
from fw_diag_tool.i2c.chip_db import CHIP_DATABASE, get_all_matching_devices, lookup_device
from fw_diag_tool.i2c.eeprom import decode_eeprom_read, decode_eeprom_write
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.input import I2CInputFormat, dispatch_i2c_input, normalize_i2c_input_format
from fw_diag_tool.i2c.models import (
    AckType,
    I2CAnalysisReport,
    I2CBytePacket,
    I2CDiagnosticIssue,
    I2CDirection,
    I2CSpeedMode,
    I2CTransaction,
    RawEventType,
    RawI2CEvent,
    Severity,
    TimingStatistics,
)
from fw_diag_tool.i2c.parser import I2CParser
from fw_diag_tool.i2c.pmbus import decode_linear11, decode_linear16, decode_pmbus_payload
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events, raw_decode_to_waveform
from fw_diag_tool.i2c.raw_capture import (
    analyze_raw_i2c_csv,
    decode_i2c_capture,
    parse_transition_csv,
)
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.status import (
    I2CTransactionStatus,
    TransactionStatus,
    classify_transaction_status,
    get_transaction_status,
    transaction_status,
)
from fw_diag_tool.i2c.timing import analyze_timing_statistics, frequency_samples_khz
from fw_diag_tool.i2c.transfer_spec import (
    UNKNOWN_BYTE,
    Endianness,
    I2CTransferOperation,
    I2CTransferSegment,
    I2CTransferSpec,
    Operation,
    TransferDirection,
    UnknownByte,
)

__all__ = [
    "CHIP_DATABASE",
    "UNKNOWN_BYTE",
    "AckType",
    "Endianness",
    "I2CAnalysisReport",
    "I2CAnomalyDetector",
    "I2CBytePacket",
    "I2CDiagnosticEngine",
    "I2CDiagnosticIssue",
    "I2CDirection",
    "I2CInputFormat",
    "I2CParser",
    "I2CReporter",
    "I2CSpeedMode",
    "I2CTransaction",
    "I2CTransactionStatus",
    "I2CTransferOperation",
    "I2CTransferSegment",
    "I2CTransferSpec",
    "Operation",
    "RawEventType",
    "RawI2CEvent",
    "Severity",
    "TimingStatistics",
    "TransactionStatus",
    "TransferDirection",
    "UnknownByte",
    "analyze_raw_i2c_csv",
    "analyze_timing_statistics",
    "classify_transaction_status",
    "decode_eeprom_read",
    "decode_eeprom_write",
    "decode_i2c_capture",
    "decode_linear11",
    "decode_linear16",
    "decode_pmbus_payload",
    "dispatch_i2c_input",
    "frequency_samples_khz",
    "get_all_matching_devices",
    "get_transaction_status",
    "lookup_device",
    "normalize_i2c_input_format",
    "parse_transition_csv",
    "raw_decode_to_events",
    "raw_decode_to_waveform",
    "transaction_status",
]
