from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.resources import load_pcie_dmesg_sample, load_waveform_diff_samples

ROOT = Path(__file__).parents[1]


def test_waveform_diff_packaged_pair_matches_documented_examples() -> None:
    golden, failing = load_waveform_diff_samples()

    assert golden == (ROOT / "examples" / "data" / "i2c_golden.csv").read_text(encoding="utf-8")
    assert failing == (ROOT / "examples" / "data" / "i2c_failing_nack.csv").read_text(
        encoding="utf-8"
    )


def test_waveform_diff_gui_loads_packaged_pair_and_reports_expected_mismatch() -> None:
    def app() -> None:
        from fw_diag_tool.gui.pages.waveform_diff_ui import render

        render()

    at = AppTest.from_function(app, default_timeout=30).run()
    at.button[0].click().run()

    assert not at.exception
    assert any("已載入內建 Golden/Failing 範例" in item.value for item in at.info)
    assert any(
        "Found 1 divergence point(s). First mismatch at Transaction #3." in item.value
        for item in at.error
    )
    assert any("找到 1 個分歧點" in item.value for item in at.error)
    assert any("NACK_MISMATCH" in item.label for item in at.expander)
    assert any(button.label == "下載差分 Markdown 報告" for button in at.download_button)


def test_pcie_dmesg_packaged_sample_is_parser_compatible() -> None:
    sample = load_pcie_dmesg_sample()
    events = PCIeAnalyzer.parse_dmesg_aer(sample)

    assert events
    assert events[0].tlp_header == "00000001 0100000f fe000000 00000000"
    report = PCIeReporter.format_dmesg_events(events)
    assert "Captured TLP Header" in report


def test_pcie_gui_loads_packaged_dmesg_sample_and_renders_tlp_header() -> None:
    def app() -> None:
        from fw_diag_tool.gui.pages.pcie_ui import render

        render()

    at = AppTest.from_function(app, default_timeout=30).run()

    next(button for button in at.button if button.label == "載入內建 dmesg AER 範例").click().run()
    assert not at.exception
    assert any("已載入內建 dmesg AER 範例" in item.value for item in at.info)

    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()
    assert not at.exception
    assert any("擷取到的 TLP Header" in item.value for item in at.markdown)
    assert any("00000001 0100000f fe000000 00000000" in item.value for item in at.markdown)
    assert any(button.label == "下載 PCIe dmesg Markdown 診斷報告" for button in at.download_button)
