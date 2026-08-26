from __future__ import annotations

from pathlib import Path

import pytest

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import I2CDirection
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.resources import load_i2c_sample

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs" / "chapters"
EXAMPLES = ROOT / "examples" / "data"


def read_doc(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def test_i2c_chapter_is_task_oriented_and_uses_current_contracts() -> None:
    chapter = read_doc("ch01_i2c_pmbus.md")

    for term in (
        "builtin:saleae_normal_pmbus_eeprom.csv",
        "18 transactions",
        "53 physical events",
        "i2c_golden.csv",
        "i2c_failing_nack.csv",
        "I2C_ACK_AGGREGATE_UNATTRIBUTABLE",
        "I2C_TIMING_AGGREGATE_UNATTRIBUTABLE",
        "I2C_SMBUS_TIMEOUT",
        "I2C_LONG_CLOCK_STRETCH",
        "I2C_MISSING_STOP",
        "I2C_SOURCE_NO_TRANSACTIONS",
        "I2C_BOARD_PROFILE_ADDRESS_AMBIGUOUS",
        "46 行",
        "45 筆 transition samples",
        "100.0 kHz",
        "aggregate（一列多 byte）不會把單一 `Duration` 猜分",
        "display-only marker",
        "quality panel **不會顯示資料品質 issue**",
        "appendix_chart_guide.md",
        "board_yv4.yaml",
        "i2c_analysis.fwsession.json",
    ):
        assert term in chapter

    assert "I2C_CLOCK_STRETCH_TIMEOUT" not in chapter
    assert "I2C_BUS_HANG_NO_STOP" not in chapter
    assert "Grade A" not in chapter


def test_chart_appendix_owns_axes_thresholds_and_evidence_semantics() -> None:
    chart = read_doc("appendix_chart_guide.md")

    for term in (
        "SCL Clock Frequency (kHz)",
        "Start Time (s)",
        "Duration (ms)",
        "READ END NAK",
        "ACK UNKNOWN",
        "Health Grade",
        "I2C_SMBUS_TIMEOUT",
        "I2C_LONG_CLOCK_STRETCH",
        "I2C_MISSING_STOP",
        "I2C_HIGH_CLOCK_JITTER",
        "35%",
        "0.1 ms",
        "physical health grade",
        "I2C_ACK_AGGREGATE_UNATTRIBUTABLE",
        "I2C_TIMING_AGGREGATE_UNATTRIBUTABLE",
        "aggregate（一列多 byte）不會把單一 `Duration` 猜分",
        "Raw STOP overlay",
    ):
        assert term in chart

    assert "I2C_CLOCK_STRETCH_TIMEOUT" not in chart
    assert "I2C_BUS_HANG_NO_STOP" not in chart


def test_gui_map_has_exactly_twelve_page_entries_and_direct_links() -> None:
    guide = read_doc("appendix_gui_reading_guide.md")
    for page_id in range(1, 13):
        assert f"### {page_id}." in guide
    for target in (
        "ch01_i2c_pmbus.md",
        "ch02_packet_builder.md",
        "ch03_waveform_diff.md",
        "ch04_uart_crash.md",
        "ch05_mctp_ipmb.md",
        "ch06_dts_generator.md",
        "ch07_pcie_aer.md",
        "ch08_spi_flash.md",
        "ch09_register_codegen.md",
        "ch10_fault_arena.md",
        "ch12_sop.md",
    ):
        assert target in guide

    assert "## 圖表的共同閱讀順序" not in guide
    assert "## 文件怎麼維護才不會失控" not in guide
    assert "## 文件分工（避免同一規則散落多處）" in guide


def test_packet_builder_docs_cover_canonical_operations_and_safety() -> None:
    chapter = read_doc("ch02_packet_builder.md")
    for term in (
        "Register write",
        "Direct write",
        "Register read",
        "Direct read",
        "8-bit",
        "16-bit",
        "MSB first",
        "big-endian",
        "bus number",
        "100 kHz",
        "25 ms",
        "I2C_RDWR",
        "HAL_I2C_Mem_Read",
        "Wire.endTransmission(false)",
        "i2ctransfer 2 w2@0x50 0x12 0x34 r4",
        "不要把 waveform 或生成的 `rx_buf` 當成裝置回應",
        "硬體安全",
    ):
        assert term in chapter


@pytest.mark.parametrize(
    ("filename", "expected_code"),
    [
        ("i2c_address_nack.csv", "I2C_ADDR_NACK"),
        ("i2c_data_nack.csv", "I2C_DATA_NACK"),
        ("i2c_missing_stop.csv", "I2C_MISSING_STOP"),
    ],
)
def test_documented_decoded_anomaly_fixtures_execute(
    filename: str, expected_code: str
) -> None:
    content = (EXAMPLES / filename).read_text(encoding="utf-8")
    report = I2CDiagnosticEngine().analyze_csv_content(content)
    assert expected_code in {issue.code for issue in report.issues}


def test_documented_clock_stretch_fixture_exercises_current_codes() -> None:
    content = (EXAMPLES / "i2c_clock_stretch.csv").read_text(encoding="utf-8")
    report = I2CDiagnosticEngine(smbus_timeout_ms=25.0).analyze_csv_content(content)
    issue_codes = {issue.code for issue in report.issues}
    assert {"I2C_LONG_CLOCK_STRETCH", "I2C_SMBUS_TIMEOUT"} <= issue_codes


def test_builtin_fixture_expected_output_is_not_golden_csv() -> None:
    report = I2CDiagnosticEngine().analyze_csv_content(load_i2c_sample())
    assert report.total_transactions == 18
    assert report.total_events == 53
    assert not report.issues
    assert {
        "I2C_EEPROM_PROFILE_UNAVAILABLE",
        "I2C_PMBUS_PAYLOAD_TRUNCATED",
        "I2C_TIMING_UNAVAILABLE",
    } <= {issue.code for issue in report.data_quality_issues}


def test_aggregate_golden_and_failing_nack_withhold_semantics_without_issue() -> None:
    golden = I2CDiagnosticEngine().analyze_csv_content(
        (EXAMPLES / "i2c_golden.csv").read_text(encoding="utf-8")
    )
    failing = I2CDiagnosticEngine().analyze_csv_content(
        (EXAMPLES / "i2c_failing_nack.csv").read_text(encoding="utf-8")
    )
    assert golden.total_transactions == failing.total_transactions == 5
    assert not golden.issues
    assert not failing.issues
    assert all(tx.status == "ACK UNKNOWN" for tx in golden.transactions)
    assert not any(
        issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in golden.data_quality_issues
    )
    assert any(
        issue.code == "I2C_ACK_AGGREGATE_UNATTRIBUTABLE"
        for issue in failing.data_quality_issues
    )
    assert any("withheld" in (tx.semantic_summary or "") for tx in failing.transactions)
    health = I2CTimingCharts.get_device_health_summary(golden)
    assert health["Device Name"].notna().all()
    assert health["Category"].notna().all()


def test_waveform_diff_doc_matches_current_cli_example_output() -> None:
    chapter = read_doc("ch03_waveform_diff.md")
    engine = I2CDiagnosticEngine()
    golden = engine.analyze_csv_content(
        (EXAMPLES / "i2c_golden.csv").read_text(encoding="utf-8")
    )
    failing = engine.analyze_csv_content(
        (EXAMPLES / "i2c_failing_nack.csv").read_text(encoding="utf-8")
    )
    diff = WaveformDiffEngine.compare_reports(golden, failing)

    assert diff.summary in chapter
    assert len(diff.divergence_points) == 1
    divergence = diff.divergence_points[0]
    assert f"Type: {divergence.mismatch_type}" in chapter
    assert divergence.description in chapter
    assert f"Hint: {divergence.root_cause_hint}" in chapter


def test_split_final_read_nack_is_normal_and_raw_fixture_is_measured() -> None:
    split = I2CDiagnosticEngine().analyze_csv_content(
        (EXAMPLES / "i2c_split_decoded.csv").read_text(encoding="utf-8")
    )
    assert split.total_transactions == 5
    assert not any(issue.code == "I2C_DATA_NACK" for issue in split.issues)
    read_tx = next(
        tx
        for tx in split.transactions
        if tx.address_7bit == 0x48 and tx.direction == I2CDirection.READ
    )
    assert read_tx.has_normal_read_termination_nack
    assert "25.50" in (read_tx.semantic_summary or "")

    raw_text = (EXAMPLES / "i2c_raw_100khz.csv").read_text(encoding="utf-8")
    assert len(raw_text.splitlines()) == 46
    raw = analyze_raw_i2c_csv(raw_text)
    # The file has 46 physical lines (header + 45 data rows); the parser
    # retains 45 transitions and derives the measured timing samples from
    # complete SCL cycles.
    assert len(raw.capture.transitions) == 45
    assert raw.timing.average_frequency_hz == pytest.approx(100_000, rel=1e-3)
