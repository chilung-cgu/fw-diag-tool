from io import StringIO

import pytest
from rich.console import Console

from fw_diag_tool.i2c.chip_db import get_all_matching_devices, lookup_device
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CBytePacket,
    I2CDirection,
    I2CSpeedMode,
    RawEventType,
    RawI2CEvent,
)
from fw_diag_tool.i2c.parser import I2CParser, parse_ack
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts


def test_missing_csv_evidence_remains_unknown_and_timing_unavailable():
    csv_data = """Packet ID,Address,Read/Write,Data
0,0x50,Write,
0,,Write,0x10
"""

    events = I2CParser.parse_csv_string(csv_data)
    report = I2CDiagnosticEngine().analyze(events)

    assert parse_ack(None) == AckType.NONE
    assert all(not event.timestamp_available for event in events)
    assert all(event.ack == AckType.NONE for event in events)
    assert report.total_duration_s == 0.0
    assert report.timing_stats.avg_frequency_khz == 0.0
    assert report.timing_stats.frequency_sample_count == 0
    assert report.timing_stats.frequency_evidence == "unavailable"
    assert report.timing_stats.speed_mode == I2CSpeedMode.UNKNOWN
    assert {issue.code for issue in report.data_quality_issues} >= {
        "I2C_TIMESTAMP_UNAVAILABLE",
        "I2C_ACK_UNAVAILABLE",
        "I2C_TIMING_UNAVAILABLE",
    }

    tx = report.transactions[0]
    assert tx.address_ack == AckType.NONE
    assert all(packet.duration_s is None for packet in tx.byte_packets)
    assert report.to_dict()["transactions"][0]["start_time"] is None

    health = I2CTimingCharts.get_device_health_summary(report)
    assert health.iloc[0]["Unknown ACK Count"] == 1
    assert health.iloc[0]["Success Rate"] == "N/A"
    assert health.iloc[0]["Health Grade"] == "N/A (ACK unavailable)"

    figure = I2CTimingCharts.create_frequency_distribution(report)
    assert len(figure.data) == 0
    assert "unavailable" in figure.layout.title.text.lower()

    timeline = I2CTimingCharts.create_bus_activity_timeline(report)
    assert all(value is None for trace in timeline.data for value in trace.x)
    assert "timestamps unavailable" in timeline.layout.title.text
    assert "| 1 | n/a |" in I2CReporter.generate_markdown(report)


def test_missing_timestamp_is_not_attached_to_diagnostic_issue():
    csv_data = """Packet ID,Address,Read/Write,Data,ACK/NACK
0,0x3A,Write,,NACK
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)
    issue = next(issue for issue in report.issues if issue.code == "I2C_ADDR_NACK")

    assert issue.timestamp is None


def test_terminal_report_shows_quality_limits_even_with_protocol_findings():
    report = I2CDiagnosticEngine().analyze_csv_string(
        "Time,Type,Address,Data,ACK/NACK\n0,DATA,0x50,0x01,\n"
    )
    output = StringIO()
    I2CReporter.render_terminal(
        report, console=Console(file=output, force_terminal=False, color_system=None)
    )

    rendered = output.getvalue()
    assert report.issues
    assert report.data_quality_issues
    assert "Data Quality Limitations" in rendered
    assert "I2C_ACK_UNAVAILABLE" in rendered


def test_empty_i2c_sources_are_insufficient_evidence_not_clean():
    engine = I2CDiagnosticEngine()
    for source in ("", "   \n# Saleae export had no rows\n", "Time,Address,Data\n"):
        report = engine.analyze_csv_content(source)
        assert report.total_events == 0
        assert report.total_transactions == 0
        assert any(issue.code == "I2C_SOURCE_EMPTY" for issue in report.data_quality_issues)
        output = StringIO()
        I2CReporter.render_terminal(
            report, console=Console(file=output, force_terminal=False, color_system=None)
        )
        rendered = output.getvalue()
        assert "Data Quality Limitations" in rendered
        assert "All Transactions Passed Cleanly" not in rendered


def test_i2c_csv_string_requires_text_input():
    with pytest.raises(TypeError, match="text"):
        I2CParser.parse_csv_string(None)  # type: ignore[arg-type]


def test_multibyte_summary_row_does_not_invent_per_byte_timestamps():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,7,0x48,Read,0x19 0x20,NACK
"""

    events = I2CParser.parse_csv_string(csv_data)

    assert [event.timestamp for event in events] == [0.001, 0.001, 0.001]
    # A combined multi-byte row does not identify which byte owns the single
    # ACK/NACK.  Keep every per-byte ACK unknown instead of inventing a
    # successful middle-byte acknowledgement.
    assert [event.ack for event in events] == [AckType.NONE, AckType.NONE, AckType.NONE]
    assert all(event.extra.get("aggregate_ack") for event in events)
    assert all(event.duration_s is None for event in events)


def test_multibyte_aggregate_ack_withholds_eeprom_semantics():
    report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n"
        '0.001,0x50,Write,"0x00 0x01",ACK\n'
    )
    tx = report.transactions[0]
    assert tx.decoded_values["evidence"] == "source-error"
    assert "withheld" in (tx.semantic_summary or "")
    assert any(
        issue.code == "I2C_ACK_AGGREGATE_UNATTRIBUTABLE"
        for issue in report.data_quality_issues
    )


def test_source_provided_byte_duration_produces_frequency_measurement():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK,Duration
0.001000,0,0x50,Write,,ACK,0.0000225
0.001025,0,,Write,0x10,ACK,0.0000225
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)

    assert report.timing_stats.avg_frequency_khz == 400.0
    assert report.timing_stats.frequency_sample_count == 2
    assert report.timing_stats.frequency_evidence == "source-provided"
    assert not any(issue.code == "I2C_TIMING_UNAVAILABLE" for issue in report.data_quality_issues)
    frequency_figure = I2CTimingCharts.create_frequency_distribution(report)
    assert len(frequency_figure.data) == 1
    assert "Samples: 2" in frequency_figure.layout.title.text


def test_final_controller_read_nack_is_neutral_in_timeline_and_health():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001000,0,0x48,Read,,ACK
0.001025,0,,Read,0x19,ACK
0.001050,0,,Read,0x20,NACK
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)
    tx = report.transactions[0]

    assert tx.direction == I2CDirection.READ
    assert not tx.has_unexpected_data_nack
    assert not any(issue.code == "I2C_DATA_NACK" for issue in report.issues)

    timeline = I2CTimingCharts.create_bus_activity_timeline(report)
    trace_names = {trace.name for trace in timeline.data}
    assert "DATA NAK" not in trace_names
    assert "READ END NAK" in trace_names

    health = I2CTimingCharts.get_device_health_summary(report)
    row = health.iloc[0]
    assert row["NACK Count"] == 0
    assert row["Success Rate"] == "100.0 %"
    assert row["Health Grade"] == "A (Excellent)"


def test_address_and_write_data_nacks_remain_failures():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001000,0,0x3A,Write,,NACK
0.002000,1,0x58,Write,,ACK
0.002025,1,,Write,0x10,ACK
0.002050,1,,Write,0xFF,NACK
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)
    issue_codes = {issue.code for issue in report.issues}

    assert "I2C_ADDR_NACK" in issue_codes
    assert "I2C_DATA_NACK" in issue_codes


def test_nacked_address_or_payload_is_not_decoded_as_accepted_semantics():
    events = [
        RawI2CEvent(0.0, RawEventType.START),
        RawI2CEvent(
            0.00001,
            RawEventType.ADDRESS,
            address_7bit=0x50,
            direction=I2CDirection.WRITE,
            ack=AckType.NACK,
        ),
        RawI2CEvent(0.00002, RawEventType.STOP),
        RawI2CEvent(0.001, RawEventType.START),
        RawI2CEvent(
            0.00101,
            RawEventType.ADDRESS,
            address_7bit=0x50,
            direction=I2CDirection.WRITE,
            ack=AckType.ACK,
        ),
        RawI2CEvent(
            0.00102,
            RawEventType.DATA,
            address_7bit=0x50,
            direction=I2CDirection.WRITE,
            data_byte=0x00,
            ack=AckType.NACK,
        ),
        RawI2CEvent(0.00103, RawEventType.STOP),
    ]

    report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze(events)

    assert report.transactions[0].decoded_values["evidence"] == "address-nack"
    assert report.transactions[1].decoded_values["evidence"] == "data-nack-present"
    assert "Address Probe" not in (report.transactions[0].semantic_summary or "")
    assert "EEPROM" not in (report.transactions[1].semantic_summary or "")
    assert {
        issue.code for issue in report.data_quality_issues
    } >= {
        "I2C_ADDRESS_NACK_SEMANTIC_UNAVAILABLE",
        "I2C_DATA_NACK_SEMANTIC_UNAVAILABLE",
    }


def test_text_trace_resets_context_after_repeated_start_and_stop():
    events = I2CParser.parse_text_trace("S 0x50 W 0x00 A Sr 0x12 A P 0x01")

    address_events = [event for event in events if event.event_type == RawEventType.ADDRESS]
    assert len(address_events) == 3
    assert address_events[0].address_7bit == 0x50
    assert address_events[1].address_7bit == 0x12
    assert address_events[1].direction is None
    assert address_events[1].extra.get("source_error")
    assert address_events[2].address_7bit == 0x01
    assert address_events[2].direction is None
    assert address_events[2].extra.get("source_error")

    report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze(events)
    assert any(issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in report.data_quality_issues)
    assert all(
        tx.direction_available is False
        and "withheld" in (tx.semantic_summary or "")
        for tx in report.transactions[1:]
    )


def test_implicit_address_change_does_not_fabricate_stop():
    events = [
        RawI2CEvent(0.0, RawEventType.ADDRESS, address_7bit=0x50, direction=I2CDirection.WRITE),
        RawI2CEvent(
            0.00001,
            RawEventType.DATA,
            address_7bit=0x50,
            direction=I2CDirection.WRITE,
            data_byte=0x00,
        ),
        RawI2CEvent(0.00002, RawEventType.ADDRESS, address_7bit=0x60, direction=I2CDirection.WRITE),
        RawI2CEvent(
            0.00003,
            RawEventType.DATA,
            address_7bit=0x60,
            direction=I2CDirection.WRITE,
            data_byte=0x01,
        ),
    ]

    report = I2CDiagnosticEngine().analyze(events)

    assert len(report.transactions) == 2
    assert report.transactions[0].has_stop is False
    assert report.transactions[0].source_error is True
    assert any(
        issue.code == "I2C_MISSING_STOP" and issue.transaction_id == report.transactions[0].id
        for issue in report.issues
    )


def test_direct_i2c_event_shape_mismatch_is_rejected():
    with pytest.raises(ValueError, match="ADDRESS cannot carry data_byte"):
        I2CDiagnosticEngine().analyze(
            [
                RawI2CEvent(
                    0.0,
                    RawEventType.ADDRESS,
                    address_7bit=0x50,
                    direction=I2CDirection.WRITE,
                    data_byte=0x12,
                )
            ]
        )

    with pytest.raises(ValueError, match="STOP cannot carry"):
        I2CDiagnosticEngine().analyze(
            [RawI2CEvent(0.0, RawEventType.STOP, address_7bit=0x50)]
        )


def test_ambiguous_address_is_presented_as_candidates_not_exact_identity():
    candidates = get_all_matching_devices(0x50)
    assert len(candidates) > 1
    assert lookup_device(0x50) is candidates[0]

    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,,ACK
0.002,0,,Write,0x00,ACK
"""
    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)
    device = report.devices_detected["0x50"]

    assert device["identity_confidence"] == "ambiguous"
    assert len(device["candidates"]) == len(candidates)
    assert report.transactions[0].device_name.startswith("Possible devices (")


def test_single_database_match_is_still_only_an_address_candidate():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x70,Write,,ACK
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)
    device = report.devices_detected["0x70"]

    assert device["identity_confidence"] == "single-address-candidate"
    assert len(device["candidates"]) == 1
    assert device["name"].startswith("Possible:")


def test_additive_evidence_fields_preserve_legacy_positional_model_arguments():
    event = RawI2CEvent(1.0, RawEventType.DATA, 7)
    packet = I2CBytePacket(
        1.0,
        0x12,
        False,
        I2CDirection.WRITE,
        AckType.ACK,
        0.000025,
    )

    assert event.packet_id == 7
    assert event.timestamp_available
    assert packet.duration_s == 0.000025
    assert packet.timestamp_available


def test_nonfinite_source_measurements_are_unavailable_and_timestamp_regression_is_reported():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK,Duration,Bit Rate
0.002,0,0x50,Write,,ACK,nan,inf
0.001,0,,Write,0x10,ACK,0.0000225,400
"""

    report = I2CDiagnosticEngine().analyze_csv_string(csv_data)

    assert report.timing_stats.frequency_sample_count == 1
    assert {issue.code for issue in report.data_quality_issues} >= {
        "I2C_TIMESTAMP_OUT_OF_ORDER",
        "I2C_TIMING_PARTIAL",
    }
