from __future__ import annotations

from pathlib import Path
from typing import Protocol

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class UploadedTextFile(Protocol):
    name: str
    size: int

    def getvalue(self) -> bytes: ...


def decode_uploaded_text(
    uploaded_file: UploadedTextFile,
    *,
    allowed_extensions: set[str],
) -> str:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"不支援的檔案格式；允許格式：{allowed}")
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError("檔案超過 20 MiB 上限；請先裁切 trace 再分析")

    content = uploaded_file.getvalue()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("檔案超過 20 MiB 上限；請先裁切 trace 再分析")
    if not content.strip():
        raise ValueError("檔案是空的")
    if b"\x00" in content:
        raise ValueError("檔案包含二進位資料，請匯出為文字 CSV 或 log")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("檔案不是有效的 UTF-8 文字") from exc


__all__ = ["MAX_UPLOAD_BYTES", "decode_uploaded_text"]
