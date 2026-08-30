from __future__ import annotations

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import (
    AckType,
    I2CDirection,
    I2CTransaction,
)
from fw_diag_tool.i2c.waveform_diff import (
    DivergencePoint,
    WaveformDiffEngine,
    WaveformDiffReport,
)
from fw_diag_tool.i2c.waveform_diff_report import (
    format_waveform_diff_markdown,
    localize_diff_description,
    localize_diff_hint,
    localize_diff_summary,
    localize_diff_type,
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


def test_waveform_diff_summary_localizes_source_parser_error() -> None:
    value = (
        "Insufficient evidence: at least one trace contains source/parser errors; "
        "protocol identity and waveform equivalence cannot be established."
    )

    localized = localize_diff_summary(value)

    assert "至少一份 trace 含有來源／解析器錯誤" in localized
    assert value in localized


def test_waveform_diff_summary_identical_and_passthrough() -> None:
    identical_val = "Golden and Failing traces are 100% identical in protocol sequence."
    assert "協定序列完全一致" in localize_diff_summary(identical_val)
    assert identical_val in localize_diff_summary(identical_val)

    unrecognized_insufficient = "Insufficient evidence: custom reason here"
    assert (
        localize_diff_summary(unrecognized_insufficient)
        == "證據不足：custom reason here（Insufficient evidence: custom reason here）"
    )

    other_text = "Some random summary string"
    assert localize_diff_summary(other_text) == other_text


def test_localize_diff_type_all_known_keys() -> None:
    known = [
        "NACK_MISMATCH",
        "ADDRESS_MISMATCH",
        "DIRECTION_MISMATCH",
        "DATA_MISMATCH",
        "RETRY_SEQUENCE",
        "DROPPED_TRANSACTION",
        "UNEXPECTED_EXTRA_TX",
        "PHASE_SHIFT",
    ]
    for key in known:
        result = localize_diff_type(key)
        assert key in result
        assert "（" in result


def test_localize_diff_type_unknown_passthrough() -> None:
    assert localize_diff_type("UNKNOWN_TYPE") == "UNKNOWN_TYPE"


def test_localize_diff_description_all_patterns() -> None:
    # _ADDRESS_RE
    addr_desc = "Address mismatch: Golden sent 0x50, Failing sent 0x48"
    loc_addr = localize_diff_description(addr_desc)
    assert "Golden 送出 0x50，Failing 送出 0x48" in loc_addr
    assert addr_desc in loc_addr

    # _ACK_RE
    ack_desc = (
        "ACK outcome mismatch on 0x50: Golden=ok, Failing=address_nack. "
        "A final controller NACK on a read is treated as normal termination."
    )
    loc_ack = localize_diff_description(ack_desc)
    assert "位址 0x50 的 ACK 結果不一致：Golden=ok、Failing=address_nack" in loc_ack
    assert ack_desc in loc_ack

    # _DIRECTION_RE
    dir_desc = "Direction mismatch: Golden=WRITE, Failing=READ"
    loc_dir = localize_diff_description(dir_desc)
    assert "讀寫方向不一致：Golden=WRITE（寫入）、Failing=READ（讀取）" in loc_dir
    assert dir_desc in loc_dir

    # _DATA_RE
    data_desc = "Data payload divergence on 0x50: Golden=0x12 0x34, Failing=0x56 0x78"
    loc_data = localize_diff_description(data_desc)
    assert "位址 0x50 的資料 Payload 不一致：Golden=0x12 0x34、Failing=0x56 0x78" in loc_data
    assert data_desc in loc_data

    # _DROPPED_RE
    drop_desc = (
        "Dropped Transaction: golden transaction #3 to 0x48 was not observed in the failing trace."
    )
    loc_drop = localize_diff_description(drop_desc)
    assert "Golden 的交易 #3（位址 0x48）沒有在 Failing trace 中觀察到" in loc_drop
    assert drop_desc in loc_drop

    # _RETRY_RE
    retry_desc = "Retry Sequence: failing transaction #1 failed; the same command is retried at transaction #2."
    loc_retry = localize_diff_description(retry_desc)
    assert "Failing 的交易 #1 失敗後，在交易 #2 重試同一 command" in loc_retry
    assert retry_desc in loc_retry

    # _FAILED_ATTEMPT_RE
    failed_desc = "Failing transaction #2 is a failed attempt for golden transaction #1."
    loc_failed = localize_diff_description(failed_desc)
    assert "Failing 的交易 #2 是 Golden 交易 #1 的失敗嘗試" in loc_failed
    assert failed_desc in loc_failed

    # _EXTRA_RE
    extra_desc = "Failing trace has unexpected extra transaction #5 to 0x50 WRITE"
    loc_extra = localize_diff_description(extra_desc)
    assert "Failing 多出交易 #5（位址 0x50，WRITE（寫入））" in loc_extra
    assert extra_desc in loc_extra

    # _PHASE_RE
    phase_desc = (
        "Phase Shift: transaction alignment moved by +1 after an insertion or dropped transaction."
    )
    loc_phase = localize_diff_description(phase_desc)
    assert "交易對齊在插入或遺失交易後偏移 +1" in loc_phase
    assert phase_desc in loc_phase

    # fallback
    fallback_desc = "Unmatched generic description"
    assert localize_diff_description(fallback_desc) == fallback_desc


def test_localize_diff_hint() -> None:
    assert localize_diff_hint("檢查晶片 Address Pin") == "檢查晶片 Address Pin"
    assert localize_diff_hint("先確認 NACK 原因") == "先確認 NACK 原因"
    assert localize_diff_hint("將同一 command 比對") == "將同一 command 比對"
    assert localize_diff_hint("Verify pullup resistor") == "排查提示：Verify pullup resistor"


def test_format_waveform_diff_markdown_empty_divergences_and_offsets() -> None:
    empty_report = WaveformDiffReport(
        is_identical=True,
        total_compared=0,
        divergence_points=[],
        summary="Golden and Failing traces are 100% identical in protocol sequence.",
    )
    md_empty = format_waveform_diff_markdown(empty_report)
    assert "未產生可列出的分歧點" in md_empty
    assert "判定**：協定序列一致" in md_empty

    tx_golden = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        address_ack=AckType.ACK,
        data_bytes=[0x12],
    )
    point = DivergencePoint(
        tx_index=1,
        golden_tx=tx_golden,
        failing_tx=None,
        mismatch_type="DROPPED_TRANSACTION",
        description="Dropped Transaction: golden transaction #1 to 0x50 was not observed in the failing trace.",
        root_cause_hint="檢查 timeout",
        alignment_offset=-1,
    )
    report_with_offset = WaveformDiffReport(
        is_identical=False,
        total_compared=1,
        divergence_points=[point],
        summary="Found 1 divergence point(s). First mismatch at Transaction #1.",
    )
    md_offset = format_waveform_diff_markdown(report_with_offset)
    assert "對齊偏移（Alignment Offset）**：`-1`" in md_offset
    assert "（無對應交易）" in md_offset


def test_format_waveform_diff_markdown_with_divergence_point_none_offset() -> None:
    tx_golden = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[],
        address_available=False,
    )
    tx_failing = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction="CUSTOM",  # type: ignore[arg-type]
        data_bytes=[0x34],
    )
    point = DivergencePoint(
        tx_index=1,
        golden_tx=tx_golden,
        failing_tx=tx_failing,
        mismatch_type="ADDRESS_MISMATCH",
        description="Address mismatch: Golden sent 0x50, Failing sent 0x48",
        root_cause_hint="檢查晶片",
        alignment_offset=None,
    )
    report = WaveformDiffReport(
        is_identical=False,
        total_compared=1,
        divergence_points=[point],
        summary="Found 1 divergence point(s). First mismatch at Transaction #1.",
    )
    md = format_waveform_diff_markdown(report)
    assert "未知位址" in md
    assert "CUSTOM" in md
    assert "對齊偏移" not in md
