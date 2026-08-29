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


def test_canonical_guide_indexes_all_gui_pages() -> None:
    guide = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    page_rows = re.findall(r"^\|\s*(\d{1,2})\s*\|", guide, flags=re.MULTILINE)
    assert page_rows == [str(page_id) for page_id in range(1, 13)]
    assert "[ch12_sop.md](chapters/ch12_sop.md)" in guide


def test_gui_reading_map_covers_all_pages_and_evidence_levels() -> None:
    reading_map = (ROOT / "docs" / "chapters" / "appendix_gui_reading_guide.md").read_text(
        encoding="utf-8"
    )
    for page_id in range(1, 13):
        assert f"### {page_id}." in reading_map
    for term in ("Measured", "Inferred", "Reconstructed", "Unavailable", "不能證明什麼"):
        assert term in reading_map


def test_sop_teaches_evidence_boundaries() -> None:
    sop = (ROOT / "docs" / "chapters" / "ch12_sop.md").read_text(encoding="utf-8")
    for term in ("Measured", "Inferred", "Reconstructed", "Hypothesis", "Unavailable"):
        assert term in sop
    for layer in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        assert layer in sop
    assert "不能量類比電壓" in sop


def test_mctp_tutorial_matches_gui_sample_and_uses_valid_ipmb_checksum() -> None:
    chapter = (ROOT / "docs" / "chapters" / "ch05_mctp_ipmb.md").read_text(encoding="utf-8")
    assert "01 08 00 C0 01 00 02 01 00" in chapter
    assert "01 08 00 C0 01 80 02 01 00" not in chapter
    assert "20 18 C8 81 00 01 7E" in chapter
    assert "20 18 67 20 00 01 5F" not in chapter


def test_readme_does_not_overstate_unverified_capabilities() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "真實故障波形" not in readme
    assert "56 項測試" not in readme
    assert "MISRA-C CodeGen" not in readme


def test_register_codegen_chapter_meaning_table_uses_localized_labels() -> None:
    chapter = (ROOT / "docs" / "chapters" / "ch09_register_codegen.md").read_text(encoding="utf-8")
    assert "輸出過電壓故障（Vout Overvoltage Fault）" in chapter
    assert "正常（Normal）" in chapter
    assert "過溫警報（Overtemperature Alarm）" in chapter
