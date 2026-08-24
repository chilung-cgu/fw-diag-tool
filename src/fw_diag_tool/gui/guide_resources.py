from __future__ import annotations

import posixpath
import re
from importlib.resources import files
from pathlib import Path, PurePosixPath

LOCAL_MARKDOWN_LINK = re.compile(r"\[([^]]+)]\((?!https?://)([^)#]+\.md)(#[^)]*)?\)")


def load_guide_text(chapter_rel_path: str) -> str | None:
    path = PurePosixPath(chapter_rel_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("guide path must stay inside the documentation directory")

    packaged = files("fw_diag_tool").joinpath("docs", *path.parts)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")

    source_path = Path(__file__).resolve().parents[3] / "docs" / Path(*path.parts)
    if source_path.is_file():
        return source_path.read_text(encoding="utf-8")
    return None


def prepare_guide_markdown(markdown: str, chapter_rel_path: str) -> str:
    parent = PurePosixPath(chapter_rel_path).parent

    def replace_link(match: re.Match[str]) -> str:
        label, target, anchor = match.groups()
        resolved = posixpath.normpath(str(parent / target))
        suffix = anchor or ""
        return f"**{label}**（本機文件：`docs/{resolved}{suffix}`）"

    return LOCAL_MARKDOWN_LINK.sub(replace_link, markdown)


__all__ = ["load_guide_text", "prepare_guide_markdown"]
