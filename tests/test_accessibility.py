"""Tests for GUI accessibility helpers."""

from __future__ import annotations

from fw_diag_tool.gui.accessibility import (
    __all__,
    generate_chart_alt_text,
    render_aria_live_region,
    render_skip_nav_link,
)


def test_generate_chart_alt_text_includes_chart_type() -> None:
    text = generate_chart_alt_text("line chart", "Three sessions", ["Anomalies decreased"])
    assert "Chart type: line chart." in text


def test_generate_chart_alt_text_includes_data_summary() -> None:
    text = generate_chart_alt_text("bar", "Five transactions", ["No faults"])
    assert "Data summary: Five transactions." in text


def test_generate_chart_alt_text_lists_multiple_findings() -> None:
    text = generate_chart_alt_text("scatter", "Voltage samples", ["Peak at 3.3V", "No dropouts"])
    assert "Key findings: Peak at 3.3V; No dropouts." in text


def test_generate_chart_alt_text_handles_empty_values() -> None:
    text = generate_chart_alt_text("", "", [])
    assert text == (
        "Chart type: Unknown. Data summary: No data summary available. Key findings: None."
    )


def test_generate_chart_alt_text_ignores_blank_findings() -> None:
    text = generate_chart_alt_text("line", "Summary", ["", "  ", "Useful finding"])
    assert text.endswith("Key findings: Useful finding.")


def test_render_skip_nav_link_targets_main_content() -> None:
    html = render_skip_nav_link()
    assert 'href="#main-content"' in html
    assert "Skip to main content" in html


def test_render_skip_nav_link_has_css_hook() -> None:
    assert 'class="skip-nav-link"' in render_skip_nav_link()


def test_render_aria_live_region_has_status_attributes() -> None:
    html = render_aria_live_region("Analysis complete")
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-atomic="true"' in html
    assert "Analysis complete" in html


def test_render_aria_live_region_escapes_message() -> None:
    html = render_aria_live_region('<script>alert("x")</script>')
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_public_exports_are_defined() -> None:
    assert set(__all__) == {
        "generate_chart_alt_text",
        "render_aria_live_region",
        "render_skip_nav_link",
    }
