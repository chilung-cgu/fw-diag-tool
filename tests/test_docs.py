from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").rglob("*.md"))]


def test_local_markdown_links_resolve() -> None:
    broken: list[str] = []
    for source in markdown_files():
        for target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
            raw_target = target.split(maxsplit=1)[0].strip("<>")
            if raw_target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative_target = unquote(raw_target.split("#", 1)[0])
            if relative_target and not (source.parent / relative_target).resolve().exists():
                broken.append(f"{source.relative_to(ROOT)} -> {raw_target}")
    assert not broken, "Broken local Markdown links:\n" + "\n".join(broken)


def test_junior_guide_indexes_all_gui_pages() -> None:
    guide = (ROOT / "docs" / "JUNIOR_FW_GUIDE.md").read_text(encoding="utf-8")
    page_rows = re.findall(r"^\|\s*(\d{1,2})\s*\|", guide, flags=re.MULTILINE)
    assert page_rows == [str(page_id) for page_id in range(1, 13)]
    assert "[ch12_sop.md](chapters/ch12_sop.md)" in guide


def test_sop_teaches_evidence_boundaries() -> None:
    sop = (ROOT / "docs" / "chapters" / "ch12_sop.md").read_text(encoding="utf-8")
    for term in ("Measured", "Inferred", "Reconstructed", "Hypothesis", "Unavailable"):
        assert term in sop
    for layer in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        assert layer in sop
    assert "不能量類比電壓" in sop


def test_readme_does_not_overstate_unverified_capabilities() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "真實故障波形" not in readme
    assert "56 項測試" not in readme
    assert "MISRA-C CodeGen" not in readme
