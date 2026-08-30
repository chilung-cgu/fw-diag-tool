"""Tests for GUI theme and CSS customization module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fw_diag_tool.gui.theme import (
    _CUSTOM_CSS,
    DARK_THEME,
    LIGHT_THEME,
    get_current_theme,
    get_plotly_template,
    inject_custom_theme,
    render_metric_card,
    render_theme_toggle,
)
from fw_diag_tool.reporting.html_report import (
    build_html_report,
    convert_markdown_to_html,
    write_html_report,
)


def test_dark_and_light_theme_css_content() -> None:
    """Verify DARK_THEME and LIGHT_THEME are valid CSS strings with required palettes and selectors."""
    assert isinstance(DARK_THEME, str)
    assert isinstance(LIGHT_THEME, str)
    assert isinstance(_CUSTOM_CSS, str)
    assert _CUSTOM_CSS == DARK_THEME

    assert "<style>" in DARK_THEME and "</style>" in DARK_THEME
    assert "<style>" in LIGHT_THEME and "</style>" in LIGHT_THEME

    # Dark theme design checks (#1e293b background, #0ea5e9 accent)
    assert "#1e293b" in DARK_THEME
    assert "#0ea5e9" in DARK_THEME

    # Light theme design checks (white bg, #1e293b text, #0369a1 accent, #f1f5f9 secondary bg)
    assert "#ffffff" in LIGHT_THEME
    assert "#1e293b" in LIGHT_THEME
    assert "#0369a1" in LIGHT_THEME
    assert "#f1f5f9" in LIGHT_THEME

    expected_selectors = [
        'div[data-testid="stExpander"]',
        'div[data-testid="stMetric"]',
        "thead tr th",
        'div[data-testid="stAlert"]',
        "pre",
        'button[data-baseweb="tab"]',
        'section[data-testid="stSidebar"]',
        'button[kind="secondary"]',
    ]
    for selector in expected_selectors:
        assert selector in DARK_THEME, f"Missing CSS selector in DARK_THEME: {selector}"
        assert selector in LIGHT_THEME, f"Missing CSS selector in LIGHT_THEME: {selector}"


def test_get_current_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_current_theme reads session_state and defaults to dark."""
    import streamlit as st

    st.session_state.clear()
    assert get_current_theme() == "dark"

    st.session_state["theme"] = "dark"
    assert get_current_theme() == "dark"

    st.session_state["theme"] = "light"
    assert get_current_theme() == "light"

    st.session_state["theme"] = "Light"
    assert get_current_theme() == "light"


def test_get_plotly_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_plotly_template returns 'plotly_dark' for dark theme and 'plotly_white' for light."""
    import streamlit as st

    st.session_state["theme"] = "dark"
    assert get_plotly_template() == "plotly_dark"

    st.session_state["theme"] = "light"
    assert get_plotly_template() == "plotly_white"


def test_inject_custom_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify inject_custom_theme passes corresponding CSS to st.markdown without exception."""
    calls: list[dict[str, Any]] = []

    import streamlit as st

    def mock_markdown(body: str, unsafe_allow_html: bool = False) -> None:
        calls.append({"body": body, "unsafe_allow_html": unsafe_allow_html})

    monkeypatch.setattr(st, "markdown", mock_markdown)

    # Dark theme
    st.session_state["theme"] = "dark"
    inject_custom_theme()
    assert len(calls) == 1
    assert calls[0]["body"] == DARK_THEME
    assert calls[0]["unsafe_allow_html"] is True

    # Light theme
    st.session_state["theme"] = "light"
    inject_custom_theme()
    assert len(calls) == 2
    assert calls[1]["body"] == LIGHT_THEME
    assert calls[1]["unsafe_allow_html"] is True


def test_render_theme_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify render_theme_toggle renders in sidebar and updates session_state."""
    import streamlit as st

    radio_calls: list[dict[str, Any]] = []

    def mock_radio(label: str, options: list[str], index: int = 0, **kwargs: Any) -> str:
        radio_calls.append({"label": label, "options": options, "index": index, "kwargs": kwargs})
        return options[1]

    monkeypatch.setattr(st.sidebar, "radio", mock_radio)
    st.session_state.clear()

    chosen = render_theme_toggle()
    assert chosen == "light"
    assert st.session_state["theme"] == "light"
    assert len(radio_calls) == 1
    assert radio_calls[0]["index"] == 0

def test_render_metric_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify render_metric_card forwards arguments properly to st.metric."""
    metric_calls: list[dict[str, Any]] = []

    import streamlit as st

    def mock_metric(
        label: str,
        value: str | float,
        delta: str | None = None,
        help: str | None = None,
    ) -> None:
        metric_calls.append({"label": label, "value": value, "delta": delta, "help": help})

    monkeypatch.setattr(st, "metric", mock_metric)
    render_metric_card(label="Errors", value=5, delta="+2", help_text="Total errors detected")

    assert len(metric_calls) == 1
    call = metric_calls[0]
    assert call["label"] == "Errors"
    assert call["value"] == 5
    assert call["delta"] == "+2"
    assert call["help"] == "Total errors detected"


def test_html_report_theme_support(tmp_path: Path) -> None:
    """Verify HTML report generator supports dark and light themes."""
    sample_md = "# 診斷報告\n內文測試\n"

    dark_html = convert_markdown_to_html(sample_md, title="Dark Report", theme="dark")
    assert "#0f172a" in dark_html
    assert "#0ea5e9" in dark_html
    assert "Standalone Dark HTML" in dark_html

    light_html = convert_markdown_to_html(sample_md, title="Light Report", theme="light")
    assert "#ffffff" in light_html
    assert "#0369a1" in light_html
    assert "Standalone Light HTML" in light_html

    built_light = build_html_report(sample_md, title="Built Light", theme="light")
    assert "#0369a1" in built_light
    assert "Standalone Light HTML" in built_light

    out_file = tmp_path / "light_report.html"
    written_path = write_html_report(sample_md, out_file, title="Written Light", theme="light")
    assert written_path.is_file()
    content = written_path.read_text(encoding="utf-8")
    assert "Standalone Light HTML" in content
    assert "#0369a1" in content
