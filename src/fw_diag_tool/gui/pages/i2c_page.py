from __future__ import annotations

from typing import Any

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.input import (
    I2CInputFormat,
    dispatch_i2c_input,
    normalize_i2c_input_format,
)
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
    csv_content: str | bytes,
    input_mode: I2CInputFormat | str | None = None,
    smbus_timeout_ms: float = 25.0,
    *,
    input_format: I2CInputFormat | str | None = None,
    board_profile: BoardProfile | None = None,
    limits: AnalysisLimits | None = None,
) -> tuple[I2CAnalysisReport, Any]:
    if input_mode is None and input_format is None:
        selected_format: I2CInputFormat | str = I2CInputFormat.DECODED_CSV
    elif input_mode is None:
        selected_format = input_format  # type: ignore[assignment]
    elif input_format is None:
        selected_format = input_mode
    else:
        selected_mode = normalize_i2c_input_format(input_mode)
        selected_format = normalize_i2c_input_format(input_format)
        if selected_mode is not selected_format:
            raise ValueError("input_mode and input_format identify different I2C formats")

    engine = build_i2c_engine(smbus_timeout_ms, board_profile=board_profile, limits=limits)
    return dispatch_i2c_input(engine, csv_content, selected_format, limits=limits)


analyze_i2c_input = analyze_i2c


__all__ = [
    "I2CInputFormat",
    "analyze_i2c",
    "analyze_i2c_input",
    "build_i2c_engine",
    "load_board_profile_from_text",
]
