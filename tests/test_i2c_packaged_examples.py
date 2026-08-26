from __future__ import annotations

import pytest

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.resources import load_i2c_sample


def test_packaged_i2c_examples_cover_each_gui_input_format() -> None:
    engine = I2CDiagnosticEngine()

    decoded_report = engine.analyze_csv_content(load_i2c_sample("split-decoded"))
    text_report = engine.analyze_text(load_i2c_sample("text-trace"))
    raw_result = analyze_raw_i2c_csv(load_i2c_sample("raw-100khz"))

    assert decoded_report.total_transactions == 5
    assert text_report.total_transactions == 2
    assert len(raw_result.transactions) == 1
    assert raw_result.timing.average_frequency_hz == pytest.approx(100_000.0)


def test_packaged_i2c_example_name_must_be_explicit() -> None:
    with pytest.raises(ValueError, match="unknown I2C sample"):
        load_i2c_sample("not-a-sample")
