"""Small HTML helpers for accessible Streamlit GUI content."""

from __future__ import annotations

from html import escape


def generate_chart_alt_text(
    chart_type: str,
    data_summary: str,
    key_findings: list[str],
) -> str:
    """Build a concise text alternative for a chart and its important findings."""
    chart_label = chart_type.strip() or "Unknown"
    summary = data_summary.strip() or "No data summary available"
    findings = [finding.strip() for finding in key_findings if finding.strip()]
    findings_text = "; ".join(findings) if findings else "None"
    return (
        f"Chart type: {chart_label}. Data summary: {summary}. "
        f"Key findings: {findings_text}."
    )


def render_skip_nav_link() -> str:
    """Return the keyboard skip link used to jump to the main content."""
    return '<a href="#main-content" class="skip-nav-link">Skip to main content</a>'


def render_aria_live_region(message: str) -> str:
    """Return a polite ARIA live region containing an escaped status message."""
    return (
        '<div role="status" aria-live="polite" aria-atomic="true">'
        f"{escape(message)}"
        "</div>"
    )


__all__ = [
    "generate_chart_alt_text",
    "render_aria_live_region",
    "render_skip_nav_link",
]
