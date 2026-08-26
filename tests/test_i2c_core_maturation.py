from __future__ import annotations

import hashlib
import json

import pytest

from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.gui.pages.i2c_page import I2CInputFormat, analyze_i2c
from fw_diag_tool.gui.session_io import (
    replay_i2c_session,
    restore_i2c_board_profile,
    serialize_i2c_session,
)
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CBytePacket,
    I2CDirection,
    I2CTransaction,
    RawEventType,
    RawI2CEvent,
)
from fw_diag_tool.i2c.parser import I2CParser
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.status import TransactionStatus, get_transaction_status
from fw_diag_tool.i2c.timing import analyze_timing_statistics
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts
from fw_diag_tool.session.session_manager import SessionManager


def _transaction(
    *,
    address_ack: AckType = AckType.ACK,
    data_ack: AckType | None = None,
    direction: I2CDirection = I2CDirection.WRITE,
    has_stop: bool = True,
    source_error: bool = False,
    is_aborted: bool = False,
    ended_by_repeated_start: bool = False,
) -> I2CTransaction:
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=direction,
        address_ack=address_ack,
        has_stop=has_stop,
        source_error=source_error,
        is_aborted=is_aborted,
        ended_by_repeated_start=ended_by_repeated_start,
    )
    tx.byte_packets.append(
        I2CBytePacket(
            timestamp=0.0,
            byte_val=0xA0,
            is_address=True,
            direction=direction,
            ack=address_ack,
        )
    )
    if data_ack is not None:
        tx.byte_packets.append(
            I2CBytePacket(
                timestamp=0.0001,
                byte_val=0x01,
                is_address=False,
                direction=direction,
                ack=data_ack,
            )
        )
        tx.data_bytes.append(0x01)
    return tx


def test_explicit_input_formats_dispatch_and_legacy_label_remains_compatible() -> None:
    csv_content = "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n"
    legacy_report, legacy_raw = analyze_i2c(
        csv_content, "Saleae Analyzer table / text trace", 25.0
    )
    explicit_report, explicit_raw = analyze_i2c(
        csv_content, I2CInputFormat.DECODED_CSV, 25.0
    )
    text_report, text_raw = analyze_i2c("[0.001] S 0xA0 W A P", I2CInputFormat.TEXT_TRACE, 25.0)

    assert legacy_report.total_transactions == explicit_report.total_transactions == 1
    assert legacy_raw is explicit_raw is text_raw is None
    assert text_report.total_transactions == 1


def test_transaction_statuses_are_shared_and_structure_wins_over_unknown_ack() -> None:
    statuses = {
        get_transaction_status(_transaction()): TransactionStatus.ACK,
        get_transaction_status(_transaction(address_ack=AckType.NACK)): TransactionStatus.ADDR_NAK,
        get_transaction_status(_transaction(data_ack=AckType.NACK)): TransactionStatus.DATA_NAK,
        get_transaction_status(
            _transaction(data_ack=AckType.NACK, direction=I2CDirection.READ)
        ): TransactionStatus.READ_END_NAK,
        get_transaction_status(_transaction(address_ack=AckType.NONE)): TransactionStatus.ACK_UNKNOWN,
        get_transaction_status(_transaction(has_stop=False)): TransactionStatus.NO_STOP,
        get_transaction_status(_transaction(source_error=True)): TransactionStatus.EVIDENCE_INCOMPLETE,
        get_transaction_status(_transaction(is_aborted=True)): TransactionStatus.ABORTED,
    }

    assert set(statuses.values()) == set(TransactionStatus)
    assert (
        get_transaction_status(_transaction(address_ack=AckType.NONE, has_stop=False))
        is TransactionStatus.NO_STOP
    )

    first = _transaction(has_stop=False, ended_by_repeated_start=True)
    following = _transaction(has_stop=True)
    assert get_transaction_status(first, next_transaction=following) is TransactionStatus.ACK


def test_health_summary_uses_repeated_start_boundary_for_no_stop_transaction() -> None:
    first = _transaction(has_stop=False)
    second = _transaction(has_stop=True)
    second.is_repeated_start = True
    report = type(
        "Report",
        (),
        {
            "transactions": [first, second],
            "devices_detected": {
                "0x50": {"name": "Unknown Device (0x50)", "category": "General I2C Peripheral"}
            },
        },
    )()

    summary = I2CTimingCharts.get_device_health_summary(report)
    assert summary.iloc[0]["Health Grade"] == "A (Excellent)"


def test_health_summary_counts_nack_even_when_missing_stop_is_display_status() -> None:
    tx = _transaction(has_stop=False, data_ack=AckType.NACK)
    report = type(
        "Report",
        (),
        {
            "transactions": [tx],
            "devices_detected": {
                "0x50": {"name": "Unknown Device (0x50)", "category": "General I2C Peripheral"}
            },
        },
    )()

    summary = I2CTimingCharts.get_device_health_summary(report)
    assert summary.iloc[0]["NACK Count"] == 1
    assert summary.iloc[0]["Success Rate"] == "0.0 %"
    assert summary.iloc[0]["Health Grade"] == "F (Critical Fault)"


def test_framing_only_source_is_not_reported_as_clean() -> None:
    report = analyze_i2c("[0.001] S P", I2CInputFormat.TEXT_TRACE, 25.0)[0]

    assert report.total_events == 2
    assert report.total_transactions == 0
    assert not report.issues
    assert any(
        issue.code == "I2C_SOURCE_NO_TRANSACTIONS"
        for issue in report.data_quality_issues
    )


def test_board_profile_duplicate_address_is_withheld_without_bus_context() -> None:
    profile = load_board_profile(
        {
            "board_name": "multi-bus",
            "version": "1",
            "i2c_buses": [
                {
                    "bus_num": 0,
                    "speed_mode": "standard",
                    "devices": [
                        {
                            "address_7bit": "0x50",
                            "name": "EEPROM on bus 0",
                            "category": "EEPROM",
                            "protocol": "EEPROM",
                            "compatible": "vendor,eeprom0",
                            "register_width": 8,
                        }
                    ],
                },
                {
                    "bus_num": 1,
                    "speed_mode": "standard",
                    "devices": [
                        {
                            "address_7bit": "0x50",
                            "name": "EEPROM on bus 1",
                            "category": "EEPROM",
                            "protocol": "EEPROM",
                            "compatible": "vendor,eeprom1",
                            "register_width": 8,
                        }
                    ],
                },
            ],
        }
    )
    report, _ = analyze_i2c(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n"
        "0.001,0,0x50,,Write,ACK\n"
        "0.001025,0,,0x00,Write,ACK\n",
        I2CInputFormat.DECODED_CSV,
        25.0,
        board_profile=profile,
    )

    tx = report.transactions[0]
    assert tx.identity_confidence == "ambiguous"
    assert tx.decoded_values["evidence"] == "ambiguous-board-profile"
    assert tx.device_candidates == ["EEPROM on bus 0", "EEPROM on bus 1"]
    assert any(
        issue.code == "I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS"
        for issue in report.data_quality_issues
    )


def test_devices_detected_upgrades_unknown_to_later_board_profile_identity() -> None:
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [
                {
                    "bus_num": 0,
                    "speed_mode": "standard",
                    "devices": [
                        {
                            "address_7bit": "0x50",
                            "name": "board-eeprom",
                            "category": "EEPROM",
                            "protocol": "EEPROM",
                            "compatible": "vendor,eeprom",
                            "register_width": 8,
                        }
                    ],
                }
            ],
        }
    )
    report = I2CDiagnosticEngine(board_profile=profile).analyze(
        [
            RawI2CEvent(
                0.0,
                RawEventType.ADDRESS,
                packet_id=0,
                address_7bit=0x50,
                direction=I2CDirection.WRITE,
                ack=AckType.ACK,
                extra={"aggregate_ack": True, "aggregate_ack_value": "ACK"},
            ),
            RawI2CEvent(
                0.001,
                RawEventType.ADDRESS,
                packet_id=1,
                address_7bit=0x50,
                direction=I2CDirection.WRITE,
                ack=AckType.ACK,
            ),
            RawI2CEvent(
                0.0011,
                RawEventType.DATA,
                packet_id=1,
                direction=I2CDirection.WRITE,
                data_byte=0x10,
                ack=AckType.ACK,
            ),
        ]
    )

    assert report.transactions[0].identity_confidence == "unknown"
    assert report.transactions[1].identity_confidence == "board-profile"
    device = report.devices_detected["0x50"]
    assert device["name"] == "board-eeprom"
    assert device["identity_confidence"] == "board-profile"
    assert device["candidates"] == ["board-eeprom"]
    assert device["transaction_count"] == 2


def test_frequency_filter_is_shared_and_utilization_needs_active_duration() -> None:
    tx = _transaction()
    tx.byte_packets.extend(
        [
            I2CBytePacket(0.0002, 0x01, False, I2CDirection.WRITE, AckType.ACK, bit_rate_khz=400.0),
            I2CBytePacket(0.0003, 0x02, False, I2CDirection.WRITE, AckType.ACK, bit_rate_khz=1.0),
            I2CBytePacket(0.0004, 0x03, False, I2CDirection.WRITE, AckType.ACK, bit_rate_khz=6000.0),
        ]
    )
    stats = analyze_timing_statistics([tx], 1.0)
    chart = I2CTimingCharts.create_frequency_distribution(
        type("Report", (), {"transactions": [tx], "timing_stats": stats})()
    )

    assert stats.frequency_sample_count == 1
    assert stats.frequency_spread_pct == stats.frequency_jitter_pct == 0.0
    assert stats.bus_utilization_evidence == "unavailable"
    assert len(chart.data) == 1


def test_session_profile_config_and_replay_are_complete() -> None:
    capture = b"Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n"
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [{"bus_num": 0, "speed_mode": "standard", "devices": []}],
        }
    )
    session_text = serialize_i2c_session(
        {"total_transactions": 1},
        input_name="capture.csv",
        input_bytes=capture,
        input_mode=I2CInputFormat.DECODED_CSV,
        smbus_timeout_ms=12.5,
        board_profile=profile,
    )
    document = SessionManager.deserialize_session(session_text)

    assert document.config["input_format"] == "decoded_csv"
    assert document.config["smbus_timeout_ms"] == 12.5
    assert document.config["board_profile_name"] == "board-a"
    assert document.config["board_profile_content"]
    report, raw = replay_i2c_session(document, capture)
    assert report.total_transactions == 1
    assert raw is None


def test_session_rejects_conflicting_duplicate_format_or_profile_metadata() -> None:
    capture = b"Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n"
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [{"bus_num": 0, "speed_mode": "standard", "devices": []}],
        }
    )
    with pytest.raises(ValueError, match="different I2C formats"):
        serialize_i2c_session(
            {"total_transactions": 1},
            input_name="capture.csv",
            input_bytes=capture,
            input_mode="decoded_csv",
            input_format="text_trace",
        )

    payload = json.loads(
        serialize_i2c_session(
            {"total_transactions": 1},
            input_name="capture.csv",
            input_bytes=capture,
            input_mode=I2CInputFormat.DECODED_CSV,
            board_profile=profile,
        )
    )
    payload["board_profile_name"] = "attacker"
    with pytest.raises(ValueError, match="top-level board profile name"):
        restore_i2c_board_profile(SessionManager.deserialize_session(json.dumps(payload)))

    payload = json.loads(
        serialize_i2c_session(
            {"total_transactions": 1},
            input_name="capture.csv",
            input_bytes=capture,
            input_mode=I2CInputFormat.DECODED_CSV,
            board_profile=profile,
        )
    )
    payload["config"]["board_profile_hash"] = "0" * 64
    with pytest.raises(ValueError, match="board_profile_hash"):
        replay_i2c_session(SessionManager.deserialize_session(json.dumps(payload)), capture)


def test_session_rejects_embedded_profile_without_identity_metadata() -> None:
    capture = b"Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n"
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [{"bus_num": 0, "speed_mode": "standard", "devices": []}],
        }
    )
    payload = json.loads(
        serialize_i2c_session(
            {"total_transactions": 1},
            input_name="capture.csv",
            input_bytes=capture,
            input_mode=I2CInputFormat.DECODED_CSV,
            board_profile=profile,
        )
    )
    payload["board_profile_name"] = None
    for key in (
        "board_profile_name",
        "board_profile_version",
        "board_profile_sha256",
        "board_profile_hash",
    ):
        payload["config"].pop(key, None)

    with pytest.raises(ValueError, match="board profile name is required"):
        restore_i2c_board_profile(SessionManager.deserialize_session(json.dumps(payload)))


def test_legacy_session_replay_uses_default_timeout_when_metadata_is_missing() -> None:
    capture = b"Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n"
    legacy_payload = {
        "version": "1.0",
        "data": {"total_transactions": 1},
        "provenance": {
            "input_sha256": hashlib.sha256(capture).hexdigest(),
            "input_mode": "upload",
        },
    }

    document = SessionManager.deserialize_session(json.dumps(legacy_payload))
    report, raw = replay_i2c_session(document, capture)

    assert report.total_transactions == 1
    assert raw is None


def test_session_replay_requires_capture_sha256_for_verification() -> None:
    document = SessionManager.deserialize_session(
        '{"schema_version":"2.0","config":{},"report":{},"capture_sha256":null}'
    )

    with pytest.raises(ValueError, match="no capture SHA-256"):
        replay_i2c_session(document, b"capture")


def test_session_replay_rejects_missing_capture_sha256_field() -> None:
    document = SessionManager.deserialize_session(
        '{"schema_version":"2.0","config":{},"report":{}}'
    )

    with pytest.raises(ValueError, match="no capture SHA-256"):
        replay_i2c_session(document, b"capture")


def test_markdown_metadata_is_optional_and_explicit() -> None:
    report, _ = analyze_i2c(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,,ACK\n",
        I2CInputFormat.DECODED_CSV,
        25.0,
    )
    markdown = I2CReporter.generate_markdown(
        report,
        metadata={
            "tool": "fw-diag-tool",
            "input_name": "capture.csv",
            "input_sha256": "abc123",
            "input_format": "decoded_csv",
            "smbus_timeout_ms": 25.0,
            "board_profile": "board-a@1",
            "evidence_sample_count": 7,
        },
    )

    assert "Input SHA-256" in markdown
    assert "decoded_csv" in markdown
    assert "Evidence sample count" in markdown
    assert "7" in markdown


def test_text_and_mapping_parsers_reject_conflicting_wire_address_direction() -> None:
    text_events = I2CParser.parse_text_trace("S 0xA1 W A P")
    address_event = next(event for event in text_events if event.event_type.value == "ADDRESS")
    assert "conflicts with explicit direction" in str(address_event.extra.get("source_error"))

    mapping_events = I2CParser.parse_raw_records(
        [{"event_type": "ADDRESS", "address": "0xA1", "direction": "WRITE", "ack": "ACK"}]
    )
    assert "conflicts with explicit direction" in str(
        mapping_events[0].extra.get("source_error")
    )


def test_reserved_decoded_address_is_retained_but_explicitly_warned() -> None:
    report, _ = analyze_i2c(
        "Time,Packet ID,Address,Read/Write,Data,ACK/NACK\n"
        "0.001,0,0x00,Write,,ACK\n",
        I2CInputFormat.DECODED_CSV,
        25.0,
    )

    assert report.transactions[0].address_7bit == 0x00
    assert any(
        issue.code == "I2C_RESERVED_ADDRESS_CANDIDATE"
        for issue in report.data_quality_issues
    )
