from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from examples import demo_i2c_diag
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.reporter import I2CReporter

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "examples" / "demo_normal_report.md"
SOURCE = ROOT / "tests" / "data" / "saleae_normal_pmbus_eeprom.csv"


def test_demo_report_fixture_matches_current_reporter() -> None:
    engine = I2CDiagnosticEngine(default_eeprom_page_size=8, smbus_timeout_ms=25.0)
    report = engine.analyze_csv_file(str(SOURCE))

    assert FIXTURE.read_text(encoding="utf-8").rstrip("\n") == I2CReporter.generate_markdown(report)


def test_demo_writes_generated_report_outside_tracked_fixture(tmp_path: Path, monkeypatch) -> None:
    fixture_before = FIXTURE.read_bytes()
    monkeypatch.setattr(demo_i2c_diag, "console", Console(file=StringIO()))

    demo_i2c_diag.run_demo(tmp_path)

    assert FIXTURE.read_bytes() == fixture_before
    assert (tmp_path / "demo_normal_report.md").read_text(
        encoding="utf-8"
    ) == fixture_before.decode("utf-8").rstrip("\n")
