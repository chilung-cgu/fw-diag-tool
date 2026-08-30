"""Tests for GUI theme and CSS customization module."""

from __future__ import annotations

from typing import Any

import pytest

from fw_diag_tool.gui.theme import _CUSTOM_CSS, inject_custom_theme, render_metric_card


def test_custom_css_content() -> None:
    """Verify _CUSTOM_CSS contains essential component selectors and styling rules."""
    assert isinstance(_CUSTOM_CSS, str)
    assert "<style>" in _CUSTOM_CSS
    assert "</style>" in _CUSTOM_CSS
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
        assert selector in _CUSTOM_CSS, f"Missing CSS selector: {selector}"


def test_inject_custom_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify inject_custom_theme passes _CUSTOM_CSS to st.markdown with unsafe_allow_html=True."""
    calls: list[dict[str, Any]] = []

    import streamlit as st

    def mock_markdown(body: str, unsafe_allow_html: bool = False) -> None:
        calls.append({"body": body, "unsafe_allow_html": unsafe_allow_html})

    monkeypatch.setattr(st, "markdown", mock_markdown)
    inject_custom_theme()

    assert len(calls) == 1
    assert calls[0]["body"] == _CUSTOM_CSS
    assert calls[0]["unsafe_allow_html"] is True


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
