"""Explicit input-format names and dispatch for I2C analysis controllers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.limits import AnalysisLimits


class I2CInputFormat(str, Enum):
    """Supported source representations for an I2C capture."""

    DECODED_CSV = "decoded_csv"
    TEXT_TRACE = "text_trace"
    RAW_DIGITAL = "raw_digital"


_FORMAT_ALIASES = {
    "decoded_csv": I2CInputFormat.DECODED_CSV,
    "decoded-csv": I2CInputFormat.DECODED_CSV,
    "decoded csv": I2CInputFormat.DECODED_CSV,
    "csv": I2CInputFormat.DECODED_CSV,
    "upload": I2CInputFormat.DECODED_CSV,
    "analyzer": I2CInputFormat.DECODED_CSV,
    "saleae analyzer table": I2CInputFormat.DECODED_CSV,
    "saleae analyzer table / text trace": I2CInputFormat.DECODED_CSV,
    "text_trace": I2CInputFormat.TEXT_TRACE,
    "text-trace": I2CInputFormat.TEXT_TRACE,
    "text trace": I2CInputFormat.TEXT_TRACE,
    "trace": I2CInputFormat.TEXT_TRACE,
    "raw_digital": I2CInputFormat.RAW_DIGITAL,
    "raw-digital": I2CInputFormat.RAW_DIGITAL,
    "raw digital": I2CInputFormat.RAW_DIGITAL,
    "raw digital transition (time, scl, sda)": I2CInputFormat.RAW_DIGITAL,
}


def normalize_i2c_input_format(value: I2CInputFormat | str) -> I2CInputFormat:
    """Normalize an explicit format or a legacy controller label."""

    if isinstance(value, I2CInputFormat):
        return value
    if not isinstance(value, str):
        raise TypeError("I2C input format must be an I2CInputFormat or string")
    normalized = " ".join(value.strip().lower().split())
    try:
        return _FORMAT_ALIASES[normalized]
    except KeyError as exc:
        allowed = ", ".join(format.value for format in I2CInputFormat)
        raise ValueError(f"unsupported I2C input format {value!r}; choose one of: {allowed}") from exc


def dispatch_i2c_input(
    engine: Any,
    content: str | bytes,
    input_format: I2CInputFormat | str,
    *,
    limits: AnalysisLimits | None = None,
) -> tuple[Any, Any]:
    """Parse and analyze content according to its declared input format.

    The second return value is the raw-capture analysis object for raw digital
    input and ``None`` for decoded CSV and text-trace sources.
    """

    selected = normalize_i2c_input_format(input_format)
    if selected is I2CInputFormat.RAW_DIGITAL:
        if not isinstance(content, (str, bytes)):
            raise TypeError("raw digital I2C input must be UTF-8 text or bytes")
        raw_capture_result = analyze_raw_i2c_csv(content, limits=limits)
        return (
            engine.analyze(raw_decode_to_events(raw_capture_result, limits=limits)),
            raw_capture_result,
        )
    if not isinstance(content, str):
        raise TypeError("decoded CSV and text-trace I2C input must be text")
    if selected is I2CInputFormat.TEXT_TRACE:
        return engine.analyze_text(content), None
    return engine.analyze_csv_content(content), None


# Short aliases keep imports readable for callers that already use the term
# ``InputFormat`` in their controller code.
InputFormat = I2CInputFormat
normalize_input_format = normalize_i2c_input_format


__all__ = [
    "I2CInputFormat",
    "InputFormat",
    "dispatch_i2c_input",
    "normalize_i2c_input_format",
    "normalize_input_format",
]
