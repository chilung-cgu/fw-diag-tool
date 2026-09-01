"""Registered Streamlit pages used by in-app links."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_PAGES_BY_URL: dict[str, Any] = {}


def register_page(page: Any) -> Any:
    """Register a Streamlit page by its internal URL path."""
    # Streamlit's ``Page.url_path`` is populated lazily by a running
    # navigation context.  During plain module imports (for example tests
    # importing ``gui.app``), bare Page objects may not have ``_url_path``
    # yet; defer registration until the runtime context supplies metadata.
    try:
        url_path = page.url_path
    except AttributeError:
        return page
    _PAGES_BY_URL[url_path] = page
    return page


def register_pages(pages: Mapping[str, Sequence[Any]]) -> Mapping[str, Sequence[Any]]:
    """Register all pages in the structure accepted by ``st.navigation``."""
    for category_pages in pages.values():
        for page in category_pages:
            register_page(page)
    return pages


def resolve_page(url_path: str) -> Any | None:
    """Resolve an internal URL path to its registered ``st.Page`` object."""
    return _PAGES_BY_URL.get(url_path)


__all__ = ["register_page", "register_pages", "resolve_page"]
