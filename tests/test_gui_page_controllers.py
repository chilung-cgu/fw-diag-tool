from __future__ import annotations

from fw_diag_tool.gui.pages.i2c_page import analyze_i2c
from fw_diag_tool.limits import AnalysisLimits
from fw_diag_tool.resources import load_i2c_sample


def test_analyze_i2c_returns_report_and_none_for_analyzer_mode():
    limits = AnalysisLimits()
    report, raw = analyze_i2c(
        load_i2c_sample(), "Saleae Analyzer table / text trace", 25.0, limits=limits
    )
    assert report.total_transactions == 18
    assert raw is None
