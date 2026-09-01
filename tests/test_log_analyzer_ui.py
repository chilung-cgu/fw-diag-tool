"""Unit tests and Streamlit AppTest coverage for System Log Analyzer UI."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from fw_diag_tool.gui.pages import log_analyzer_ui
from fw_diag_tool.gui.pages.log_analyzer_ui import format_log_markdown, render
from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.i18n.domains.gui import GUI_TRANSLATIONS
from fw_diag_tool.log.models import (
    Incident,
    LogEvent,
    LogReport,
    LogSourceType,
    LogSummary,
    Subsystem,
)


def test_log_analyzer_exports() -> None:
    """Verify module exports and callables."""
    assert callable(render)
    assert callable(format_log_markdown)
    assert hasattr(log_analyzer_ui, "format_log_markdown")
    assert hasattr(log_analyzer_ui, "render")


def test_format_log_markdown_empty() -> None:
    """Verify markdown output when no incidents exist."""
    report = LogReport(
        source_type=LogSourceType.DMESG,
        summary=LogSummary(total_lines=5, total_events=0, total_incidents=0),
    )
    md = format_log_markdown(report)
    assert "# System Log Diagnostic Report" in md
    assert "- **Source Type**: `dmesg`" in md
    assert "- **Total Lines**: 5" in md
    assert "- **Detected Events**: 0" in md
    assert "- **Correlated Incidents**: 0" in md
    assert "No incidents detected." in md


def test_format_log_markdown_populated() -> None:
    """Verify markdown output with incidents and actions."""
    ev = LogEvent(
        timestamp=10.5,
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        message="i2c-1: client at 0x50: -ENXIO",
        bus=1,
        address=0x50,
        pattern_id="I2C_SLAVE_ENXIO",
    )
    inc = Incident(
        id="INC-001",
        title="I2C Bus 1 NAK",
        subsystem=Subsystem.I2C,
        severity=Severity.ERROR,
        events=[ev],
        root_cause_hypothesis="Target device at 0x50 unpowered or disconnected",
        board_context="Baseboard EEPROM at Bus 1 0x50",
        recommended_actions=["Check 3.3V rail", "Verify I2C pullup resistors"],
        related_tool_page="i2c-diagnosis",
    )
    summary = LogSummary(
        total_lines=10,
        total_events=1,
        total_incidents=1,
        subsystem_counts={"i2c": 1},
        severity_counts={"ERROR": 1},
        time_span_seconds=2.5,
    )
    report = LogReport(
        source_type=LogSourceType.DMESG,
        events=[ev],
        incidents=[inc],
        summary=summary,
    )
    md = format_log_markdown(report, title="Custom Diagnostic Header")
    assert "# Custom Diagnostic Header" in md
    assert "- **Time Span**: 2.500 s" in md
    assert "### Subsystems" in md
    assert "- **i2c**: 1" in md
    assert "### Severities" in md
    assert "- **ERROR**: 1" in md
    assert "### [ERROR] INC-001: I2C Bus 1 NAK" in md
    assert "- **Root Cause Hypothesis**: Target device at 0x50 unpowered or disconnected" in md
    assert "- **Board Context**: Baseboard EEPROM at Bus 1 0x50" in md
    assert "  - Check 3.3V rail" in md
    assert "  - Verify I2C pullup resistors" in md


def test_i18n_gui_keys_exist() -> None:
    """Verify that all required log analyzer i18n keys are registered in the GUI domain."""
    required_keys = [
        "nav_category_system_log",
        "title_log_analyzer",
        "log_analyzer_title",
        "log_sample_i2c",
        "log_sample_pcie",
        "log_sample_bmc",
        "log_uploader_label",
        "log_text_label",
        "log_tab_incidents",
        "log_tab_timeline",
        "log_tab_distribution",
    ]
    for key in required_keys:
        assert key in GUI_TRANSLATIONS, f"Missing i18n key: {key}"
        assert "zh-TW" in GUI_TRANSLATIONS[key]
        assert "en-US" in GUI_TRANSLATIONS[key]


def _log_app() -> None:
    from fw_diag_tool.gui.pages.log_analyzer_ui import render

    render()


def test_apptest_log_analyzer_empty_render() -> None:
    """Test initial render of log_analyzer_ui via AppTest in empty state."""
    at = AppTest.from_function(_log_app, default_timeout=15).run()
    assert not at.exception
    # Verify header is present
    assert any(
        "Linux Kernel（dmesg）與 OpenBMC（journalctl）日誌關聯診斷" in h.value for h in at.header
    )
    # Verify empty prompt info
    assert any("請上傳日誌檔案" in info.value for info in at.info)


def test_apptest_log_analyzer_sample_i2c_button() -> None:
    """Test clicking I2C sample button and verifying parsed output."""
    at = AppTest.from_function(_log_app, default_timeout=15).run()
    assert not at.exception

    # Find the I2C sample button
    btn_i2c = next((b for b in at.button if "I2C" in b.label), None)
    assert btn_i2c is not None
    btn_i2c.click().run()

    assert not at.exception
    # Verify metrics appear
    metric_labels = [m.label for m in at.metric]
    assert any("總事件數" in lbl for lbl in metric_labels)
    assert any("關聯異常群組" in lbl for lbl in metric_labels)
    assert any("涉及子系統數" in lbl for lbl in metric_labels)

    # Verify download buttons
    dl_labels = [d.label for d in at.download_button]
    assert any("Markdown" in lbl for lbl in dl_labels)
    assert any("JSON" in lbl for lbl in dl_labels)


def test_apptest_log_analyzer_sample_pcie_button() -> None:
    """Test clicking PCIe AER sample button and verifying incident display."""
    at = AppTest.from_function(_log_app, default_timeout=15).run()
    assert not at.exception

    btn_pcie = next((b for b in at.button if "PCIe" in b.label), None)
    assert btn_pcie is not None
    btn_pcie.click().run()

    assert not at.exception
    # Should have parsed events
    metric_values = [str(m.value) for m in at.metric]
    assert any(val != "0" for val in metric_values)


def test_apptest_log_analyzer_sample_bmc_button() -> None:
    """Test clicking OpenBMC sensor sample button."""
    at = AppTest.from_function(_log_app, default_timeout=15).run()
    assert not at.exception

    btn_bmc = next((b for b in at.button if "OpenBMC" in b.label), None)
    assert btn_bmc is not None
    btn_bmc.click().run()

    assert not at.exception
    assert any("總事件數" in m.label for m in at.metric)


def _diff_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.log_analyzer_ui import render

    st.session_state["log_analyzer_raw_text"] = (
        "[ 10.000000] pcieport 0000:00:01.0: AER: Uncorrectable error received\n"
    )
    st.session_state["log_diff_baseline_text"] = (
        "[ 10.000000] i2c-1: client at 0x50: No such device or address (-ENXIO)\n"
    )
    render()


def test_apptest_log_analyzer_with_diff_input() -> None:
    """Test A/B diff comparison within log_analyzer_ui."""
    at = AppTest.from_function(_diff_app, default_timeout=15).run()
    assert not at.exception
    # Metrics from both candidate and diff should be rendered
    metric_labels = [m.label for m in at.metric]
    assert any("Baseline 事件數" in lbl for lbl in metric_labels)
    assert any("Candidate 事件數" in lbl for lbl in metric_labels)
    assert any("事件數變化" in lbl for lbl in metric_labels)


def _profile_app() -> None:
    import streamlit as st

    from fw_diag_tool.gui.pages.log_analyzer_ui import render

    st.session_state["log_board_profile_text"] = (
        'board_name: "Test-Board"\n'
        'version: "1.0"\n'
        "i2c_buses:\n"
        "  - bus_num: 1\n"
        '    speed_mode: "standard"\n'
        "    devices:\n"
        "      - address_7bit: 0x50\n"
        '        name: "baseboard-fru-eeprom"\n'
        '        category: "EEPROM"\n'
        '        protocol: "I2C"\n'
        '        compatible: "atmel,24c64"\n'
        "        register_width: 8\n"
    )
    st.session_state["log_analyzer_raw_text"] = (
        "[ 10.000000] i2c-1: client at 0x50: No such device or address (-ENXIO)\n"
    )
    render()


def test_apptest_log_analyzer_with_board_profile() -> None:
    """Test log analyzer rendering with board profile topology enrichment."""
    at = AppTest.from_function(_profile_app, default_timeout=15).run()
    assert not at.exception
    assert any("板級拓撲對照" in info.value for info in at.info)
    assert any("baseboard-fru-eeprom" in info.value for info in at.info)
