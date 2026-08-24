from __future__ import annotations

from typing import Any

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import I2CAnalysisReport
from fw_diag_tool.limits import AnalysisLimits, coerce_limits


def build_i2c_engine(
    smbus_timeout_ms: float,
    *,
    board_profile: BoardProfile | None = None,
    limits: AnalysisLimits | None = None,
) -> I2CDiagnosticEngine:
    return I2CDiagnosticEngine(
        smbus_timeout_ms=smbus_timeout_ms,
        board_profile=board_profile,
        limits=coerce_limits(limits),
    )


def load_board_profile_from_text(yaml_text: str) -> BoardProfile:
    return load_board_profile(yaml_text)


def analyze_i2c(
    csv_content: str,
    input_mode: str,
    smbus_timeout_ms: float,
    *,
    limits: AnalysisLimits | None = None,
) -> tuple[I2CAnalysisReport, Any]:
    engine = build_i2c_engine(smbus_timeout_ms, limits=limits)
    if input_mode == "Raw digital transition (Time, SCL, SDA)":
        from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events
        from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv

        raw_capture_result = analyze_raw_i2c_csv(csv_content, limits=limits)
        report = engine.analyze(raw_decode_to_events(raw_capture_result))
        return report, raw_capture_result
    return engine.analyze_csv_content(csv_content), None
