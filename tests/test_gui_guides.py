from __future__ import annotations

import pytest

from fw_diag_tool.gui.guide_resources import load_guide_text, prepare_guide_markdown


def test_source_guide_resource_loads_without_built_wheel():
    text = load_guide_text("chapters/ch01_i2c_pmbus.md")

    assert text is not None
    assert "I2C" in text


def test_local_markdown_links_are_rendered_without_broken_browser_urls():
    rendered = prepare_guide_markdown(
        "請讀[能力與限制](../LIMITATIONS.md#輸入限制)。",
        "chapters/ch01_i2c_pmbus.md",
    )

    assert "](../LIMITATIONS.md" not in rendered
    assert "`docs/LIMITATIONS.md#輸入限制`" in rendered


def test_guide_resource_rejects_path_traversal():
    with pytest.raises(ValueError, match="documentation directory"):
        load_guide_text("../README.md")
