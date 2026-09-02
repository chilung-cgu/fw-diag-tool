from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fw_diag_tool.reporting.pdf_report import (
    _clean_markdown_text,
    _find_cjk_font_paths,
    _sanitize_for_font,
    build_pdf_report,
    is_fpdf_available,
    write_pdf_report,
)


def test_is_fpdf_available_boolean() -> None:
    """Ensure is_fpdf_available returns a boolean."""
    assert isinstance(is_fpdf_available(), bool)


def test_clean_markdown_text_formatting() -> None:
    """Test inline markdown stripping in _clean_markdown_text."""
    assert _clean_markdown_text("**bold text**") == "bold text"
    assert _clean_markdown_text("__bold text__") == "bold text"
    assert _clean_markdown_text("*italic text*") == "italic text"
    assert _clean_markdown_text("`inline code`") == "inline code"
    assert _clean_markdown_text("[Link Title](https://example.com)") == "Link Title"
    assert _clean_markdown_text("  **mixed** `code` *test*  ") == "mixed code test"


def test_sanitize_for_font_symbols() -> None:
    """Test unicode symbol substitution in _sanitize_for_font."""
    raw = "⚡ 狀態 📜 日誌 🚨 報警 ✔ 通過 ✖ 失敗 • 項目\x01\x02\n\t正常"
    sanitized = _sanitize_for_font(raw)
    assert "[fw-diag]" in sanitized
    assert "[Log]" in sanitized
    assert "[ALERT]" in sanitized
    assert "[PASS]" in sanitized
    assert "[FAIL]" in sanitized
    assert "-" in sanitized
    assert "\x01" not in sanitized
    assert "\x02" not in sanitized
    assert "正常" in sanitized


def test_find_cjk_font_paths_all_combinations() -> None:
    """Test font candidate path resolution with different file availability."""
    this_file = str(Path(__file__).resolve())

    # 1. Simulate all fonts absent
    with (
        patch("fw_diag_tool.reporting.pdf_report._CJK_REGULAR_CANDIDATES", []),
        patch("fw_diag_tool.reporting.pdf_report._CJK_BOLD_CANDIDATES", []),
        patch("fw_diag_tool.reporting.pdf_report._FALLBACK_UNICODE_CANDIDATES", []),
    ):
        cjk_reg, cjk_bold, fallback = _find_cjk_font_paths()
        assert cjk_reg is None
        assert cjk_bold is None
        assert fallback is None

    # 2. Simulate only fallback font present
    with (
        patch("fw_diag_tool.reporting.pdf_report._CJK_REGULAR_CANDIDATES", []),
        patch("fw_diag_tool.reporting.pdf_report._CJK_BOLD_CANDIDATES", []),
        patch("fw_diag_tool.reporting.pdf_report._FALLBACK_UNICODE_CANDIDATES", [this_file]),
    ):
        cjk_reg, cjk_bold, fallback = _find_cjk_font_paths()
        assert cjk_reg is None
        assert cjk_bold is None
        assert fallback == this_file

    # 3. Simulate CJK regular present but bold absent
    with (
        patch("fw_diag_tool.reporting.pdf_report._CJK_REGULAR_CANDIDATES", [this_file]),
        patch("fw_diag_tool.reporting.pdf_report._CJK_BOLD_CANDIDATES", []),
        patch("fw_diag_tool.reporting.pdf_report._FALLBACK_UNICODE_CANDIDATES", []),
    ):
        cjk_reg, cjk_bold, fallback = _find_cjk_font_paths()
        assert cjk_reg == this_file
        assert cjk_bold is None
        assert fallback is None

    # 4. Simulate CJK regular and bold present
    with (
        patch("fw_diag_tool.reporting.pdf_report._CJK_REGULAR_CANDIDATES", [this_file]),
        patch("fw_diag_tool.reporting.pdf_report._CJK_BOLD_CANDIDATES", [this_file]),
        patch("fw_diag_tool.reporting.pdf_report._FALLBACK_UNICODE_CANDIDATES", []),
    ):
        cjk_reg, cjk_bold, fallback = _find_cjk_font_paths()
        assert cjk_reg == this_file
        assert cjk_bold == this_file
        assert fallback is None


def test_build_pdf_report_cjk_reg_without_bold() -> None:
    """Test PDF generation when CJK regular is available but CJK bold is absent."""
    reg_font, _, _ = _find_cjk_font_paths()
    if reg_font is None:
        pytest.skip("System CJK font not present")
    with patch(
        "fw_diag_tool.reporting.pdf_report._find_cjk_font_paths",
        return_value=(reg_font, None, None),
    ):
        md = "# 診斷報告標題\n\n- 狀態: 正常\n- 頻率: 100 kHz\n"
        pdf_bytes = build_pdf_report(
            title="單一字體 CJK 測試",
            markdown_content=md,
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_fallback_font_only() -> None:
    """Test PDF generation when CJK font is absent but Unicode fallback font is configured."""
    cjk_reg, _, fallback = _find_cjk_font_paths()
    fallback_candidate = cjk_reg or fallback
    if fallback_candidate is None:
        pytest.skip("Unicode test font not present")
    with patch(
        "fw_diag_tool.reporting.pdf_report._find_cjk_font_paths",
        return_value=(None, None, fallback_candidate),
    ):
        # With CJK text removed from footer/banner when no CJK font is present,
        # the fallback Unicode font should produce a valid PDF without encoding errors.
        pdf_bytes = build_pdf_report(
            title="Fallback Font Report",
            markdown_content="# Diagnostic Report\n\n- Status: PASS\n",
            timestamp="2026-08-30 12:00:00 UTC",
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_all_heading_levels() -> None:
    """Test markdown headings level 1 to 6 in PDF generation."""
    md = (
        "# Heading 1: System Health\n\n"
        "## Heading 2: I2C Bus Status\n\n"
        "### Heading 3: Voltage Regulators\n\n"
        "#### Heading 4: Rail 1.8V Details\n\n"
        "##### Heading 5: Sub-rail telemetry\n\n"
        "###### Heading 6: Microvolt sensor\n\n"
    )
    pdf_bytes = build_pdf_report(
        title="Heading Levels Test",
        markdown_content=md,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_tables_and_mismatched_cells() -> None:
    """Test table rendering with missing cells and different row lengths."""
    md = (
        "| Parameter | Value | Limit | Status |\n"
        "|:---|:---:|---:|---|\n"
        "| VDD | 3.3V | 3.6V | PASS |\n"
        "| IDD | 150mA | 200mA |\n"
        "| Temp | 45 C |\n"
        "\n\n"
        "| Single Col |\n"
        "|---|\n"
        "| Only Value |\n"
    )
    pdf_bytes = build_pdf_report(
        title="Table Test Report",
        markdown_content=md,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_code_blocks_and_quotes() -> None:
    """Test multi-line code blocks and multi-line blockquotes in PDF."""
    md = (
        "> Line 1 of blockquote summary.\n"
        "> Line 2 of blockquote explanation.\n\n"
        "```c\n"
        "#include <stdio.h>\n"
        "int main(void) {\n"
        '    printf("Hello, Firmware Diagnostics!\\n");\n'
        "    return 0;\n"
        "}\n"
        "```\n\n"
        "```\n"
        "Generic log output without syntax tag\n"
        "Line 2 of log output\n"
        "```\n"
    )
    pdf_bytes = build_pdf_report(
        title="Code and Quotes Report",
        markdown_content=md,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_horizontal_rules_and_lists() -> None:
    """Test horizontal rules (---, ***, ___) and lists (ordered & unordered)."""
    md = (
        "Paragraph before separator 1.\n\n"
        "---\n\n"
        "Paragraph before separator 2.\n\n"
        "***\n\n"
        "Paragraph before separator 3.\n\n"
        "___\n\n"
        "- Unordered item A\n"
        "- Unordered item B\n"
        "* Bullet with asterisk\n\n"
        "1. First ordered step\n"
        "2. Second ordered step\n"
        "3. Third ordered step\n"
    )
    pdf_bytes = build_pdf_report(
        title="Rules and Lists Report",
        markdown_content=md,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_multipage_header_footer() -> None:
    """Test multi-page document to trigger _DiagPDF.header() on page 2+ and footer()."""
    paragraphs = [
        f"## Section {i}\n\n"
        f"This is paragraph {i} providing detailed diagnostic telemetry. "
        "The firmware diagnostic tool analyzes multi-bus communications including I2C, SPI, UART, "
        "PCIe AER, and MCTP protocol traces with timing jitter and waveform reconstruction.\n\n"
        f"| Step {i} | Metric | Measured | Target |\n"
        "|---|---|---|---|\n"
        f"| Check A | Voltage | {3.3 + i * 0.01:.2f} V | 3.30 V |\n"
        f"| Check B | Jitter | {12 + i:.1f} ns | < 25 ns |\n"
        for i in range(1, 25)
    ]
    md = "\n".join(paragraphs)
    pdf_bytes = build_pdf_report(
        title="Large Multi-Page Firmware Diagnostic Report",
        markdown_content=md,
        metadata={"DUT": "BMC-Yosemite-V4", "Environment": "Lab-Bench-03"},
        tool_version="1.5.0",
        timestamp="2026-08-30 08:30:00 UTC",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")


def test_build_pdf_report_metadata_filtering() -> None:
    """Test metadata banner when empty, None, or containing empty/dash values."""
    # 1. Empty metadata dict
    pdf1 = build_pdf_report("Empty Meta", "Short content", metadata={})
    assert pdf1.startswith(b"%PDF-")

    # 2. Metadata with ignored values (None, empty string, '-')
    pdf2 = build_pdf_report(
        "Ignored Meta",
        "Short content",
        metadata={"valid_key": "valid_val", "empty_key": "", "dash_key": "-", "none_key": None},
    )
    assert pdf2.startswith(b"%PDF-")

    # 3. None metadata
    pdf3 = build_pdf_report("None Meta", "Short content", metadata=None)
    assert pdf3.startswith(b"%PDF-")


def test_build_pdf_report_empty_content() -> None:
    """Test empty or whitespace-only markdown content."""
    pdf_bytes = build_pdf_report(
        title="Blank Report",
        markdown_content="   \n\n\t\n   ",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_write_pdf_report_nested_directory(tmp_path: Path) -> None:
    """Test write_pdf_report creating parent directories automatically."""
    out_dir = tmp_path / "deep" / "nested" / "output"
    out_file = out_dir / "diag_report.pdf"
    written_path = write_pdf_report(
        markdown_content="# Diagnostic Log\n\nOperation completed successfully.",
        output_path=out_file,
        title="Nested Output Test",
        metadata={"Board": "EVB-STM32H7"},
        tool_version="1.5.0",
        timestamp="2026-08-30 15:00:00 UTC",
    )
    assert written_path == out_file
    assert out_file.is_file()
    assert out_file.read_bytes().startswith(b"%PDF-")
