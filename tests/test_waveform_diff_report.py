from __future__ import annotations

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.i2c.waveform_diff_report import (
    format_waveform_diff_markdown,
    localize_diff_summary,
)


def test_waveform_diff_markdown_is_chinese_first_and_keeps_canonical_tokens() -> None:
    golden = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,,ACK
0.0011,0,,Write,0x00,ACK
0.002,1,0x50,Write,,ACK
0.0021,1,,Write,0x12,ACK
"""
    failing = golden.replace("0x12,ACK", "0x12,NACK")
    engine = I2CDiagnosticEngine()
    diff = WaveformDiffEngine.compare_reports(
        engine.analyze_csv_content(golden), engine.analyze_csv_content(failing)
    )

    markdown = format_waveform_diff_markdown(
        diff, golden_name="golden.csv", failing_name="failing.csv"
    )

    assert "# I2C 雙波形差分診斷報告" in markdown
    assert "Golden（正常）輸入" in markdown
    assert "ACK／NACK 結果不一致（NACK_MISMATCH）" in markdown
    assert "找到 1 個分歧點" in markdown
    assert "Found 1 divergence point(s). First mismatch at Transaction #2." in markdown
    assert "不是類比電壓或原始 SCL/SDA edge" in markdown


def test_waveform_diff_summary_preserves_insufficient_evidence_reason() -> None:
    value = (
        "Insufficient evidence: both golden and failing traces contain no transactions; "
        "protocol identity cannot be established."
    )

    localized = localize_diff_summary(value)

    assert localized.startswith("證據不足：")
    assert "Golden 與 Failing trace 都沒有 transaction" in localized
    assert value in localized


def test_waveform_diff_summary_localizes_unknown_ack_limit() -> None:
    value = (
        "Insufficient evidence: at least one trace has unknown ACK or incomplete "
        "transaction framing; protocol identity cannot be established."
    )

    localized = localize_diff_summary(value)

    assert "ACK 未知或交易框架不完整" in localized
    assert value in localized
