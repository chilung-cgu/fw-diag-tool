"""Firmware diagnostic toolkit."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fw-diag-tool")
except PackageNotFoundError:
    __version__ = "0+unknown"

from fw_diag_tool.envelope import DiagnosticReportEnvelope
from fw_diag_tool.errors import InputFormatError, ResourceLimitError
from fw_diag_tool.limits import AnalysisLimits

__all__ = [
    "AnalysisLimits",
    "DiagnosticReportEnvelope",
    "InputFormatError",
    "ResourceLimitError",
    "__version__",
]
