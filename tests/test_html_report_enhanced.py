"""Tests for enhanced HTML report features: light theme, print CSS, TOC, collapsible sections."""

from __future__ import annotations

from pathlib import Path

from fw_diag_tool.reporting.html_report import (
    build_html_report,
    convert_markdown_to_html,
    write_html_report,
)

SAMPLE_MD = """# 診斷報告

## 總覽

這是一份測試報告。

### I2C 分析結果

- 交易數：10
- 異常：2

## SPI 分析結果

> 正常

### 細節

| 項目 | 值 | 狀態 |
|------|-----|------|
| 交易數 | 5 | [OK] |
| 錯誤數 | 0 | [PASS] |

## 結論

一切正常。[INFO]
"""


class TestLightTheme:
    """Tests for light theme styling and palette switches."""

    def test_light_theme_uses_white_background(self) -> None:
        """Verify that light theme sets light background CSS variables and format label."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Light Test", theme="light")
        assert "--bg-primary: #ffffff;" in html
        assert "--bg-code: #f8fafc;" in html
        assert "--text-primary: #1e293b;" in html
        assert "Standalone Light HTML" in html
        # Should not use dark theme primary background variable
        assert "--bg-primary: #0f172a;" not in html

    def test_light_theme_chinese_alias(self) -> None:
        """Verify that '亮色' theme parameter alias is properly recognized."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Light Alias Test", theme="亮色")
        assert "--bg-primary: #ffffff;" in html
        assert "Standalone Light HTML" in html

    def test_default_theme_is_dark(self) -> None:
        """Verify that default theme is dark (#0f172a)."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Dark Test")
        assert "--bg-primary: #0f172a;" in html
        assert "--text-primary: #e2e8f0;" in html
        assert "Standalone Dark HTML" in html


class TestPrintCSS:
    """Tests for print-friendly CSS stylesheet and rules."""

    def test_print_media_query_present(self) -> None:
        """Verify that @media print stylesheet rule is present."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Print Test")
        assert "@media print" in html

    def test_print_hides_non_essential_elements(self) -> None:
        """Verify that print CSS hides interactive/non-essential elements."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Print Test")
        assert "@media print" in html
        assert "display: none" in html


class TestTableOfContents:
    """Tests for Table of Contents (TOC) generation and heading anchors."""

    def test_toc_headings_rendered_in_body(self) -> None:
        """Verify that all markdown headings are rendered into appropriate HTML tags."""
        html = convert_markdown_to_html(SAMPLE_MD, title="TOC Test")
        assert "<h1>診斷報告</h1>" in html
        assert '<h2 id="總覽">總覽</h2>' in html
        assert '<h3 id="i2c-分析結果">I2C 分析結果</h3>' in html
        assert '<h2 id="spi-分析結果">SPI 分析結果</h2>' in html
        assert '<h2 id="結論">結論</h2>' in html

    def test_headings_have_id_attributes(self) -> None:
        """Verify that headings include id attributes for anchor navigation."""
        html = convert_markdown_to_html(SAMPLE_MD, title="ID Test")
        assert '<h2 id="' in html or '<h1 id="' in html


class TestCollapsibleSections:
    """Tests for collapsible sections support."""

    def test_section_content_preserved_gracefully(self) -> None:
        """Verify that structured sections remain intact in report body."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Collapse Test")
        assert "細節" in html
        assert "<table" in html

    def test_details_elements_present(self) -> None:
        """Verify that collapsible sections render as <details> elements."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Collapse Test")
        assert "<details" in html
        assert "<summary" in html


class TestMetadataHeader:
    """Tests for report metadata header grid and formatting."""

    def test_metadata_contains_version(self) -> None:
        """Verify that tool version is accurately displayed in header grid and footer."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Meta Test", tool_version="1.2.0")
        assert "fw-diag-tool v1.2.0" in html
        assert "診斷套件（Tool）" in html

    def test_metadata_contains_timestamp(self) -> None:
        """Verify that custom timestamp is embedded in header grid."""
        html = convert_markdown_to_html(
            SAMPLE_MD, title="Meta Test", timestamp="2026-08-30 12:00:00 UTC"
        )
        assert "2026-08-30 12:00:00 UTC" in html
        assert "產生時間（Generated）" in html

    def test_build_html_report_alias_works(self) -> None:
        """Verify build_html_report alias behaves identically to convert_markdown_to_html."""
        html = build_html_report(SAMPLE_MD, title="Alias Test", tool_version="1.3.0", theme="light")
        assert "<!DOCTYPE html>" in html
        assert "⚡ Alias Test" in html
        assert "fw-diag-tool v1.3.0" in html
        assert "Standalone Light HTML" in html

    def test_write_html_report_saves_file(self, tmp_path: Path) -> None:
        """Verify write_html_report writes output file to disk."""
        target_file = tmp_path / "reports" / "summary.html"
        result_path = write_html_report(SAMPLE_MD, target_file, title="Disk Test", theme="light")
        assert result_path == target_file
        assert target_file.exists()
        content = target_file.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "⚡ Disk Test" in content


class TestIntegration:
    """Integration tests for HTML report structure and Markdown parsing."""

    def test_full_report_is_valid_html_structure(self) -> None:
        """Verify document envelope, meta tags, and root wrappers."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Full Test", tool_version="1.3.0")
        assert html.startswith("<!DOCTYPE html>")
        assert '<html lang="zh-TW">' in html
        assert '<meta charset="utf-8" />' in html
        assert "<body>" in html
        assert '<div class="container">' in html
        assert '<header class="report-header">' in html
        assert '<main class="report-body">' in html
        assert '<footer class="report-footer">' in html
        assert "</body>" in html
        assert html.rstrip().endswith("</html>")

    def test_all_markdown_sections_rendered(self) -> None:
        """Verify all sections, lists, blockquotes, tables, and badges are properly rendered."""
        html = convert_markdown_to_html(SAMPLE_MD, title="Sections Test")
        for section in ["診斷報告", "總覽", "I2C 分析結果", "SPI 分析結果", "細節", "結論"]:
            assert section in html, f"Section '{section}' should appear in HTML"

        # List items
        assert "<li>交易數：10</li>" in html
        assert "<li>異常：2</li>" in html

        # Blockquote
        assert "<blockquote><p>正常</p></blockquote>" in html

        # Table & Badges
        assert "<table" in html
        assert '<span class="badge badge-success">OK</span>' in html
        assert '<span class="badge badge-success">PASS</span>' in html
        assert '<span class="badge badge-info">INFO</span>' in html
