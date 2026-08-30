"""Tests for global search, breadcrumb, and keyboard shortcuts in shared.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fw_diag_tool.gui.shared import (
    PAGE_INDEX,
    render_breadcrumb,
    render_global_search,
    render_keyboard_shortcuts,
)


class TestPageIndex:
    """Validate the PAGE_INDEX data structure."""

    def test_page_index_entries(self) -> None:
        assert len(PAGE_INDEX) == 26

    def test_all_entries_have_required_keys(self) -> None:
        required = {"title", "url", "category", "keywords"}
        for entry in PAGE_INDEX:
            assert required.issubset(entry.keys()), f"Missing keys in {entry}"

    def test_unique_urls(self) -> None:
        urls = [e["url"] for e in PAGE_INDEX]
        assert len(urls) == len(set(urls)), "Duplicate URLs found"

    def test_unique_titles(self) -> None:
        titles = [e["title"] for e in PAGE_INDEX]
        assert len(titles) == len(set(titles)), "Duplicate titles found"

    def test_search_finds_i2c_pages(self) -> None:
        matches = [p for p in PAGE_INDEX if "i2c" in p["keywords"]]
        assert len(matches) >= 2

    def test_search_finds_spi(self) -> None:
        matches = [p for p in PAGE_INDEX if "spi" in p["keywords"] or "spi" in p["title"].lower()]
        assert len(matches) >= 1

    def test_all_categories_non_empty(self) -> None:
        categories = {e["category"] for e in PAGE_INDEX}
        assert len(categories) >= 4


class TestRenderFunctions:
    """Test render functions don't raise when called with mocked st."""

    @patch("fw_diag_tool.gui.page_index.st")
    def test_render_breadcrumb_no_error(self, mock_st: MagicMock) -> None:
        render_breadcrumb("Protocol Analysis", "I2C Diagnosis")
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args
        html = call_args[0][0]
        assert "Protocol Analysis" in html
        assert "I2C Diagnosis" in html

    @patch("fw_diag_tool.gui.page_index.st")
    def test_render_global_search_empty(self, mock_st: MagicMock) -> None:
        mock_st.sidebar.text_input.return_value = ""
        render_global_search()
        mock_st.sidebar.text_input.assert_called_once()

    @patch("fw_diag_tool.gui.page_index.st")
    def test_render_global_search_with_query(self, mock_st: MagicMock) -> None:
        mock_st.sidebar.text_input.return_value = "i2c"
        render_global_search()
        assert mock_st.sidebar.markdown.called

    @patch("fw_diag_tool.gui.page_index.st")
    def test_render_global_search_no_results(self, mock_st: MagicMock) -> None:
        mock_st.sidebar.text_input.return_value = "zzzznonexistent"
        render_global_search()
        mock_st.sidebar.caption.assert_called_once()

    @patch("fw_diag_tool.gui.page_index.st")
    def test_render_keyboard_shortcuts_no_error(self, mock_st: MagicMock) -> None:
        expander_ctx = MagicMock()
        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=expander_ctx)
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        render_keyboard_shortcuts()
        mock_st.sidebar.expander.assert_called_once()
