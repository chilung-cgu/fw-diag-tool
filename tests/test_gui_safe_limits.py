from __future__ import annotations

from fw_diag_tool.gui.shared import GUI_ANALYSIS_LIMITS
from fw_diag_tool.limits import DEFAULT_ANALYSIS_LIMITS


def test_gui_limits_are_independent_instance():
    """GUI must use its own AnalysisLimits instance, not the shared default."""
    assert GUI_ANALYSIS_LIMITS is not DEFAULT_ANALYSIS_LIMITS


def test_gui_upload_limit_matches_streamlit_server_cap():
    assert GUI_ANALYSIS_LIMITS.max_upload_bytes == 20 * 1024 * 1024
    assert GUI_ANALYSIS_LIMITS.max_text_bytes == 2 * 1024 * 1024
