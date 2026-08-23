from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CAnalysisReport,
    I2CBytePacket,
    I2CDirection,
    I2CTransaction,
    TimingStatistics,
)
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine


def _tx(
    tx_id: int,
    address: int,
    data: tuple[int, ...] = (),
    ack: AckType = AckType.ACK,
    *,
    repeated_start: bool = False,
    has_stop: bool = True,
) -> I2CTransaction:
    return I2CTransaction(
        id=tx_id,
        start_time=float(tx_id),
        end_time=float(tx_id) + 0.001,
        address_7bit=address,
        address_8bit=address << 1,
        direction=I2CDirection.WRITE,
        data_bytes=list(data),
        address_ack=ack,
        is_repeated_start=repeated_start,
        has_stop=has_stop,
    )


def _report(transactions: list[I2CTransaction]) -> I2CAnalysisReport:
    return I2CAnalysisReport(
        total_events=0,
        total_transactions=len(transactions),
        total_duration_s=0.0,
        devices_detected={},
        transactions=transactions,
        timing_stats=TimingStatistics(),
        issues=[],
    )


def test_waveform_diff_divergence_detection():
    golden_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,,ACK
0.0011,0,,Write,0x00,ACK
0.002,1,0x50,Write,,ACK
0.0021,1,,Write,0x12,ACK
0.0022,1,,Write,0x34,ACK
"""
    failing_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,,ACK
0.0011,0,,Write,0x00,ACK
0.002,1,0x50,Write,,ACK
0.0021,1,,Write,0x12,ACK
0.0022,1,,Write,0x34,NACK
"""
    eng = I2CDiagnosticEngine()
    g_rep = eng.analyze_csv_content(golden_csv)
    f_rep = eng.analyze_csv_content(failing_csv)
    diff = WaveformDiffEngine.compare_reports(g_rep, f_rep)
    assert diff.is_identical is False
    assert len(diff.divergence_points) == 1
    assert diff.divergence_points[0].tx_index == 2
    assert diff.divergence_points[0].mismatch_type == "NACK_MISMATCH"
    fig = WaveformDiffEngine.create_comparison_figure(diff)
    assert fig is not None


def test_waveform_diff_does_not_call_normal_read_final_nack_a_failure():
    golden_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x48,Read,0x19 0x20,NACK
"""
    failing_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x48,Read,0x19 0x20,NACK
"""

    engine = I2CDiagnosticEngine()
    diff = WaveformDiffEngine.compare_reports(
        engine.analyze_csv_content(golden_csv), engine.analyze_csv_content(failing_csv)
    )

    assert diff.is_identical


def test_waveform_diff_empty_inputs_are_insufficient_evidence_not_identical():
    engine = I2CDiagnosticEngine()
    empty = engine.analyze([])

    diff = WaveformDiffEngine.compare_reports(empty, empty)

    assert diff.is_identical is False
    assert diff.total_compared == 0
    assert "Insufficient evidence" in diff.summary


def test_waveform_diff_does_not_call_source_error_identical():
    good = """Time,Address,Read/Write,Data,ACK/NACK
0.001,0x50,Write,,ACK
0.0011,,Write,0x00,ACK
"""
    malformed = good.replace(",ACK\n", ",WHAT\n")
    engine = I2CDiagnosticEngine()
    diff = WaveformDiffEngine.compare_reports(
        engine.analyze_csv_content(good), engine.analyze_csv_content(malformed)
    )

    assert diff.is_identical is False
    assert "source/parser errors" in diff.summary


def test_waveform_diff_does_not_call_unterminated_traces_identical():
    golden = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,,ACK
0.0011,0,,Write,0x33,ACK
"""
    failing = """Time,Address,Read/Write,Data,ACK/NACK
0.001,0x50,Write,,ACK
0.0011,,Write,0x33,ACK
"""
    engine = I2CDiagnosticEngine()
    diff = WaveformDiffEngine.compare_reports(
        engine.analyze_csv_content(golden), engine.analyze_csv_content(failing)
    )

    assert diff.is_identical is False
    assert "incomplete" in diff.summary


def test_waveform_diff_aligns_failed_retry_before_successful_command():
    golden = [_tx(1, 0x50, (0x10,)), _tx(2, 0x51, (0x20,))]
    failing = [
        _tx(1, 0x50, (0x10,), AckType.NACK),
        _tx(2, 0x50, (0x10,)),
        _tx(3, 0x51, (0x20,)),
    ]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    kinds = [point.mismatch_type for point in diff.divergence_points]
    assert kinds == ["RETRY_SEQUENCE", "PHASE_SHIFT"]
    assert "NACK_MISMATCH" not in kinds
    assert diff.alignment == [(None, 0), (0, 1), (1, 2)]
    retry = diff.divergence_points[0]
    assert retry.golden_index == 0
    assert retry.failing_index == 0
    assert retry.failing_tx is failing[0]
    assert retry.alignment_offset == 0
    assert diff.divergence_points[1].alignment_offset == 1


def test_waveform_diff_accepts_address_nack_without_payload_as_retry_attempt():
    golden = [_tx(1, 0x50, (0x10,)), _tx(2, 0x51, (0x20,))]
    failing = [
        _tx(1, 0x50, (), AckType.NACK),
        _tx(2, 0x50, (0x10,)),
        _tx(3, 0x51, (0x20,)),
    ]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    assert [point.mismatch_type for point in diff.divergence_points] == [
        "RETRY_SEQUENCE",
        "PHASE_SHIFT",
    ]
    assert diff.alignment == [(None, 0), (0, 1), (1, 2)]


def test_waveform_diff_marks_dropped_transaction_and_resumes_alignment():
    golden = [_tx(1, 0x50, (0x10,)), _tx(2, 0x51, (0x20,)), _tx(3, 0x52, (0x30,))]
    failing = [_tx(1, 0x50, (0x10,)), _tx(3, 0x52, (0x30,))]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    kinds = [point.mismatch_type for point in diff.divergence_points]
    assert kinds == ["DROPPED_TRANSACTION", "PHASE_SHIFT"]
    assert diff.alignment == [(0, 0), (1, None), (2, 1)]
    dropped = diff.divergence_points[0]
    assert dropped.golden_tx is golden[1]
    assert dropped.failing_tx is None
    assert diff.divergence_points[1].alignment_offset == -1


def test_waveform_diff_equal_length_substitution_is_not_called_dropped():
    golden = [_tx(1, 0x50, (0x10,)), _tx(2, 0x51, (0x20,))]
    failing = [_tx(1, 0x53, (0x10,)), _tx(2, 0x51, (0x20,))]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    assert [point.mismatch_type for point in diff.divergence_points] == ["ADDRESS_MISMATCH"]
    assert diff.alignment == [(0, 0), (1, 1)]


def test_waveform_diff_repeated_start_transactions_remain_aligned():
    golden = [
        _tx(1, 0x50, (0x10,)),
        _tx(2, 0x50, (0x20,), repeated_start=True, has_stop=False),
        _tx(3, 0x51, (0x30,)),
    ]
    failing = [
        _tx(8, 0x50, (0x10,)),
        _tx(9, 0x50, (0x20,), repeated_start=True, has_stop=False),
        _tx(10, 0x51, (0x30,)),
    ]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    assert diff.is_identical
    assert diff.alignment == [(0, 0), (1, 1), (2, 2)]


def test_waveform_diff_repeated_protocol_keys_keep_order_after_drop():
    golden = [
        _tx(1, 0x50, (0x10,)),
        _tx(2, 0x51, (0x20,)),
        _tx(3, 0x50, (0x10,)),
        _tx(4, 0x51, (0x20,)),
    ]
    failing = [
        _tx(1, 0x50, (0x10,)),
        _tx(3, 0x50, (0x10,)),
        _tx(4, 0x51, (0x20,)),
    ]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    assert [point.mismatch_type for point in diff.divergence_points] == [
        "DROPPED_TRANSACTION",
        "PHASE_SHIFT",
    ]
    assert diff.alignment == [(0, 0), (1, None), (2, 1), (3, 2)]


def test_waveform_diff_partial_packet_loss_is_insufficient_evidence():
    partial = _tx(1, 0x50, (0x10,))
    partial.byte_packets.append(
        I2CBytePacket(
            timestamp=1.0,
            byte_val=0,
            is_address=False,
            direction=I2CDirection.WRITE,
            ack=AckType.NONE,
            byte_available=False,
        )
    )
    complete = _tx(1, 0x50, (0x10,))

    diff = WaveformDiffEngine.compare_reports(_report([partial]), _report([complete]))

    assert diff.is_identical is False
    assert diff.divergence_points == []
    assert "Insufficient evidence" in diff.summary


def test_waveform_diff_long_trace_does_not_require_quadratic_matrix():
    golden = [_tx(index, 0x50, (index & 0xFF,)) for index in range(1, 2001)]
    failing = [_tx(index, 0x50, (index & 0xFF,)) for index in range(1, 2001)]

    diff = WaveformDiffEngine.compare_reports(_report(golden), _report(failing))

    assert diff.is_identical
    assert len(diff.alignment) == 2000
