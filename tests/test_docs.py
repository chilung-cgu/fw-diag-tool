from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import yaml

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
    assert page_rows == [str(page_id) for page_id in range(1, 21)]
    assert "[ch11_board_profile.md](chapters/ch11_board_profile.md)" in guide
    assert "[ch12_sop.md](chapters/ch12_sop.md)" in guide


def test_gui_reading_map_covers_all_pages_and_evidence_levels() -> None:
    reading_map = (ROOT / "docs" / "chapters" / "appendix_gui_reading_guide.md").read_text(
        encoding="utf-8"
    )
    for page_id in range(1, 21):
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


def test_dashboard_documents_cumulative_release_history_and_nav() -> None:
    chapter_path = ROOT / "docs" / "chapters" / "ch16_dashboard.md"
    chapter = chapter_path.read_text(encoding="utf-8")
    assert "release-history" in chapter.lower() or "release history" in chapter.lower()
    assert "v1.7.0" in chapter
    assert "累積歷史" in chapter
    assert "cumulative history" in chapter
    assert "證據邊界" in chapter
    assert "evidence boundary" in chapter

    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    def nav_contains_path(node: object) -> bool:
        if isinstance(node, str):
            return node == "chapters/ch16_dashboard.md"
        if isinstance(node, dict):
            return any(nav_contains_path(value) for value in node.values())
        if isinstance(node, list):
            return any(nav_contains_path(value) for value in node)
        return False

    assert nav_contains_path(config.get("nav", []))


def test_mctp_tutorial_matches_gui_sample_and_uses_valid_ipmb_checksum() -> None:
    chapter = (ROOT / "docs" / "chapters" / "ch05_mctp_ipmb.md").read_text(encoding="utf-8")
    assert "01 08 00 C0 01 00 02 01 00" in chapter
    assert "01 08 00 C0 01 80 02 01 00" not in chapter
    assert "20 18 C8 81 00 01 7E" in chapter
    assert "20 18 67 20 00 01 5F" not in chapter


def test_mctp_tutorial_matches_gui_labels_and_localizes_protocol_fields() -> None:
    chapter = (ROOT / "docs" / "chapters" / "ch05_mctp_ipmb.md").read_text(encoding="utf-8")

    assert "執行 MCTP／IPMB 伺服器管理協定解碼" in chapter
    assert "執行伺服器協定解碼" not in chapter
    for token in ("MCTP", "IPMB", "PLDM", "SPDM", "Header Version"):
        assert token in chapter
    for label in (
        "標頭版本（Header Version）",
        "目的端點識別碼（Dest EID）",
        "來源端點識別碼（Src EID）",
        "訊息類型（Msg Type）",
        "PLDM 命令（PLDM Command）",
        "請求位址（Rq Addr）",
        "回應位址（Rs Addr）",
        "網路功能（NetFn）",
        "命令（Command）",
        "狀態（Status）",
    ):
        assert label in chapter


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
