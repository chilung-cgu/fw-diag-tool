from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine


def test_waveform_diff_divergence_detection():
    golden_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,0x00,ACK
0.002,1,0x50,Write,0x12 0x34,ACK
"""
    failing_csv = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,0x00,ACK
0.002,1,0x50,Write,0x12 0x34,NACK
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
