"""PDF report generator for firmware diagnostic suite.

Converts Markdown diagnostic reports into clean, standalone PDF documents
using pure Python (fpdf2) without external binary dependencies.
Supports headings, metadata banners, tables, code blocks, blockquotes,
badges, and Traditional Chinese (CJK) Unicode text rendering.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from fw_diag_tool import __version__

try:
    from fpdf import FPDF
    from fpdf.enums import TableCellFillMode
    from fpdf.fonts import FontFace

    _FPDF_AVAILABLE = True
except ImportError:
    _FPDF_AVAILABLE = False


def is_fpdf_available() -> bool:
    """Return whether fpdf2 package is installed and available."""
    return _FPDF_AVAILABLE


_CJK_REGULAR_CANDIDATES = [
    # Linux standard paths
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    # macOS standard paths
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    # Windows standard paths
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/arialuni.ttf",
]

_CJK_BOLD_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/msjhbd.ttc",
]

_FALLBACK_UNICODE_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _find_cjk_font_paths() -> tuple[str | None, str | None, str | None]:
    """Find installed CJK regular, bold, and fallback Unicode fonts on the current system."""
    cjk_reg: str | None = None
    for p in _CJK_REGULAR_CANDIDATES:
        if Path(p).is_file():
            cjk_reg = p
            break

    cjk_bold: str | None = None
    for p in _CJK_BOLD_CANDIDATES:
        if Path(p).is_file():
            cjk_bold = p
            break

    fallback: str | None = None
    for p in _FALLBACK_UNICODE_CANDIDATES:
        if Path(p).is_file():
            fallback = p
            break

    return cjk_reg, cjk_bold, fallback


def _clean_markdown_text(text: str) -> str:
    """Clean markdown inline formatting for standard plain text cells."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _sanitize_for_font(text: str) -> str:
    """Sanitize unsupported control chars or rare symbols that lack glyphs."""
    text = text.replace("⚡", "[fw-diag]").replace("📜", "[Log]").replace("🚨", "[ALERT]")
    text = text.replace("✔", "[PASS]").replace("✖", "[FAIL]").replace("•", "-")
    return "".join(ch for ch in text if ch in ("\n", "\t") or ord(ch) >= 32)


if _FPDF_AVAILABLE:

    class _DiagPDF(FPDF):
        """Custom FPDF document with firmware suite branding, headers, and footers."""

        def __init__(
            self,
            title_text: str = "Firmware Diagnostic Report",
            tool_version_str: str = __version__,
            timestamp_str: str = "",
            font_family_name: str = "Helvetica",
        ) -> None:
            super().__init__(orientation="portrait", unit="mm", format="A4")
            self.title_text = title_text
            self.tool_version_str = tool_version_str
            self.timestamp_str = timestamp_str
            self.font_family_name = font_family_name
            self.set_auto_page_break(auto=True, margin=15)
            self.set_margins(15, 15, 15)

        def header(self) -> None:
            if self.page_no() > 1:
                self.set_font(self.font_family_name, size=8)
                self.set_text_color(100, 116, 139)
                self.set_x(self.l_margin)
                self.cell(
                    self.epw,
                    6,
                    f"{_sanitize_for_font(self.title_text)}  |  fw-diag-tool v{self.tool_version_str}",
                    align="L",
                )
                self.ln(7)
                self.set_draw_color(226, 232, 240)
                self.set_line_width(0.2)
                self.line(self.l_margin, 20, 210 - self.r_margin, 20)
                self.set_x(self.l_margin)
                self.ln(2)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_x(self.l_margin)
            self.set_font(self.font_family_name, size=8)
            self.set_text_color(148, 163, 184)
            page_label = "頁碼" if self.font_family_name == "CustomCJK" else "Page"
            footer_text = (
                f"fw-diag-tool v{self.tool_version_str}  -  "
                f"{self.timestamp_str}  -  "
                f"{page_label} {self.page_no()}/{{nb}}"
            )
            self.cell(self.epw, 8, _sanitize_for_font(footer_text), align="C")


def build_pdf_report(
    title: str,
    markdown_content: str,
    metadata: dict[str, Any] | None = None,
    *,
    tool_version: str | None = None,
    timestamp: str | None = None,
) -> bytes:
    """Build a standalone PDF report binary from Markdown diagnostic text and metadata.

    Args:
        title: Title of the diagnostic report.
        markdown_content: Markdown content from diagnostic engines / reporters.
        metadata: Optional dictionary of metadata (e.g. input_name, board_profile, etc.).
        tool_version: Optional override for fw-diag-tool version.
        timestamp: Optional override for generation timestamp string.

    Returns:
        Raw PDF document bytes.

    Raises:
        RuntimeError: If fpdf2 is not installed.
    """
    if not _FPDF_AVAILABLE:
        raise RuntimeError(
            "PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf] "
            "(fpdf2 package is required for PDF report generation)"
        )

    version_str = tool_version or __version__
    ts_str = timestamp or time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    cjk_reg, cjk_bold, fallback = _find_cjk_font_paths()

    font_family = "Helvetica"
    font_bold_family = "Helvetica"

    pdf = _DiagPDF(
        title_text=title,
        tool_version_str=version_str,
        timestamp_str=ts_str,
        font_family_name="CustomCJK" if cjk_reg else "Helvetica",
    )

    if cjk_reg:
        font_family = "CustomCJK"
        pdf.add_font("CustomCJK", "", cjk_reg)
        if cjk_bold:
            pdf.add_font("CustomCJK", "B", cjk_bold)
            font_bold_family = "CustomCJK"
        else:
            pdf.add_font("CustomCJK", "B", cjk_reg)
            font_bold_family = "CustomCJK"
        if fallback:
            pdf.add_font("FallbackUnicode", "", fallback)
            pdf.set_fallback_fonts(["FallbackUnicode"])
    elif fallback:
        font_family = "FallbackUnicode"
        font_bold_family = "FallbackUnicode"
        pdf.add_font("FallbackUnicode", "", fallback)
        pdf.set_fallback_fonts(["FallbackUnicode"])

    pdf.add_page()
    pdf.set_font(font_family, size=10)

    # 1. Top Report Header Banner Box
    pdf.set_fill_color(241, 245, 249)  # Slate 100
    pdf.set_draw_color(203, 213, 225)  # Slate 300
    pdf.set_line_width(0.3)

    start_y = pdf.get_y()
    pdf.rect(pdf.l_margin, start_y, pdf.epw, 24, style="FD")

    # Banner Title
    pdf.set_xy(pdf.l_margin + 3, start_y + 3)
    pdf.set_font(
        font_bold_family, style="B" if font_bold_family != font_family or cjk_bold else "", size=13
    )
    pdf.set_text_color(14, 116, 144)  # Cyan 700 / Slate
    pdf.cell(pdf.epw - 6, 7, _sanitize_for_font(f"{title}"), align="L")
    pdf.ln(7)

    # Metadata Grid in Header Box
    pdf.set_xy(pdf.l_margin + 3, start_y + 11)
    pdf.set_font(font_family, size=8.5)
    pdf.set_text_color(71, 85, 105)  # Slate 600

    col_w = (pdf.epw - 6) / 3
    if cjk_reg:
        pdf.cell(col_w, 5, _sanitize_for_font(f"診斷套件: fw-diag-tool v{version_str}"), align="L")
        pdf.cell(col_w, 5, _sanitize_for_font(f"產生時間: {ts_str}"), align="L")
        pdf.cell(col_w, 5, _sanitize_for_font("格式: Standalone PDF Report"), align="L")
    else:
        pdf.cell(col_w, 5, _sanitize_for_font(f"fw-diag-tool v{version_str}"), align="L")
        pdf.cell(col_w, 5, _sanitize_for_font(f"Generated: {ts_str}"), align="L")
        pdf.cell(col_w, 5, _sanitize_for_font("Format: Standalone PDF Report"), align="L")
    pdf.ln(5)

    if metadata:
        extra_meta = [f"{k}: {v}" for k, v in metadata.items() if v not in (None, "", "-")]
        if extra_meta:
            pdf.set_xy(pdf.l_margin + 3, start_y + 16)
            summary_str = " | ".join(extra_meta[:3])
            pdf.cell(pdf.epw - 6, 5, _sanitize_for_font(summary_str), align="L")

    pdf.set_y(start_y + 28)
    pdf.set_x(pdf.l_margin)

    # 2. Parse and render markdown body
    lines = markdown_content.splitlines()
    idx = 0
    total_lines = len(lines)

    while idx < total_lines:
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        # Code block
        if stripped.startswith("```"):
            code_lines: list[str] = []
            idx += 1
            while idx < total_lines and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < total_lines:
                idx += 1

            code_text = "\n".join(code_lines)
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.set_fill_color(248, 250, 252)
            pdf.set_draw_color(226, 232, 240)
            pdf.set_text_color(30, 41, 59)
            pdf.set_font(font_family, size=8)

            safe_code = _sanitize_for_font(code_text)
            pdf.multi_cell(
                pdf.epw,
                4.5,
                safe_code,
                border=1,
                fill=True,
                align="L",
            )
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)
            continue

        # Markdown Table
        if (
            "|" in stripped
            and idx + 1 < total_lines
            and re.match(r"^\s*\|?[-:\s|]+\|?\s*$", lines[idx + 1])
        ):
            table_lines: list[str] = []
            while idx < total_lines and "|" in lines[idx].strip():
                table_lines.append(lines[idx].strip())
                idx += 1

            if len(table_lines) >= 2:
                header_cells = [
                    _clean_markdown_text(c) for c in table_lines[0].strip("|").split("|")
                ]
                data_rows: list[list[str]] = []
                for t_line in table_lines[2:]:
                    if not t_line.strip():
                        continue
                    r_cells = [_clean_markdown_text(c) for c in t_line.strip("|").split("|")]
                    while len(r_cells) < len(header_cells):
                        r_cells.append("-")
                    data_rows.append(r_cells[: len(header_cells)])

                col_lens = [max(len(h), 5) for h in header_cells]
                for r in data_rows:
                    for c_idx, val in enumerate(r):
                        col_lens[c_idx] = max(col_lens[c_idx], min(len(val), 40))

                total_len = sum(col_lens) or 1
                col_widths = tuple((l / total_len) * pdf.epw for l in col_lens)

                pdf.ln(2)
                pdf.set_x(pdf.l_margin)
                pdf.set_font(font_family, size=8)

                headings_style = FontFace(
                    family=font_bold_family,
                    emphasis="B" if font_bold_family != font_family or cjk_bold else None,
                    fill_color=(226, 232, 240),
                    color=(15, 23, 42),
                )

                with pdf.table(
                    col_widths=col_widths,
                    first_row_as_headings=True,
                    headings_style=headings_style,
                    cell_fill_mode=TableCellFillMode.ROWS,
                    cell_fill_color=(248, 250, 252),
                    line_height=4.5,
                    padding=(1.5, 1.5, 1.5, 1.5),
                ) as tbl:
                    h_row = tbl.row()
                    for h in header_cells:
                        h_row.cell(_sanitize_for_font(h))
                    for r_cells in data_rows:
                        row = tbl.row()
                        for c in r_cells:
                            row.cell(_sanitize_for_font(c))

                pdf.set_x(pdf.l_margin)
                pdf.ln(3)
                continue

        # Headings
        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            level = len(header_match.group(1))
            heading_text = _clean_markdown_text(header_match.group(2))
            pdf.ln(3 if level > 1 else 4)
            pdf.set_x(pdf.l_margin)

            if level == 1:
                pdf.set_font(
                    font_bold_family,
                    style="B" if font_bold_family != font_family or cjk_bold else "",
                    size=13,
                )
                pdf.set_text_color(2, 132, 199)
                pdf.cell(
                    pdf.epw, 7, _sanitize_for_font(heading_text), new_x="LMARGIN", new_y="NEXT"
                )
                pdf.set_draw_color(2, 132, 199)
                pdf.set_line_width(0.3)
                pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
                pdf.set_x(pdf.l_margin)
                pdf.ln(2)
            elif level == 2:
                pdf.set_font(
                    font_bold_family,
                    style="B" if font_bold_family != font_family or cjk_bold else "",
                    size=11,
                )
                pdf.set_text_color(15, 23, 42)
                pdf.cell(
                    pdf.epw, 6, _sanitize_for_font(heading_text), new_x="LMARGIN", new_y="NEXT"
                )
                pdf.set_draw_color(203, 213, 225)
                pdf.set_line_width(0.2)
                pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
                pdf.set_x(pdf.l_margin)
                pdf.ln(2)
            elif level == 3:
                pdf.set_font(
                    font_bold_family,
                    style="B" if font_bold_family != font_family or cjk_bold else "",
                    size=10,
                )
                pdf.set_text_color(3, 105, 161)
                pdf.cell(
                    pdf.epw, 5.5, _sanitize_for_font(heading_text), new_x="LMARGIN", new_y="NEXT"
                )
                pdf.set_x(pdf.l_margin)
                pdf.ln(1)
            else:
                pdf.set_font(
                    font_bold_family,
                    style="B" if font_bold_family != font_family or cjk_bold else "",
                    size=9.5,
                )
                pdf.set_text_color(51, 65, 85)
                pdf.cell(
                    pdf.epw, 5, _sanitize_for_font(heading_text), new_x="LMARGIN", new_y="NEXT"
                )
                pdf.set_x(pdf.l_margin)
                pdf.ln(1)

            idx += 1
            continue

        # Horizontal Rule
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.set_draw_color(203, 213, 225)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)
            idx += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while idx < total_lines and lines[idx].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[idx].strip()))
                idx += 1
            quote_text = _clean_markdown_text(" ".join(quote_lines))

            pdf.ln(1)
            pdf.set_fill_color(248, 250, 252)
            pdf.set_draw_color(14, 165, 233)
            pdf.set_line_width(0.8)
            pdf.set_font(font_family, size=8.5)
            pdf.set_text_color(51, 65, 85)

            y_before = pdf.get_y()
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(
                pdf.epw - 3,
                4.8,
                _sanitize_for_font(quote_text),
                fill=True,
                align="L",
            )
            y_after = pdf.get_y()
            pdf.line(pdf.l_margin, y_before, pdf.l_margin, y_after)
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)
            continue

        # List items
        list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.+)$", line)
        if list_match:
            is_ordered = bool(re.match(r"^\d+\.", list_match.group(2)))
            bullet = f"{list_match.group(2)} " if is_ordered else "-  "
            item_text = _clean_markdown_text(list_match.group(3))

            pdf.set_font(font_family, size=9)
            pdf.set_text_color(30, 41, 59)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(
                pdf.epw - 3,
                4.8,
                _sanitize_for_font(f"{bullet}{item_text}"),
                align="L",
            )
            pdf.set_x(pdf.l_margin)
            idx += 1
            continue

        # Normal Paragraph
        para_lines: list[str] = []
        while idx < total_lines:
            p_line = lines[idx]
            p_strip = p_line.strip()
            if (
                not p_strip
                or p_strip.startswith(("#", ">", "```", "---", "***"))
                or re.match(r"^\s*([*-]|\d+\.)\s+", p_line)
                or (
                    "|" in p_strip
                    and idx + 1 < total_lines
                    and re.match(r"^\s*\|?[-:\s|]+\|?\s*$", lines[idx + 1])
                )
            ):
                break
            para_lines.append(p_strip)
            idx += 1

        if para_lines:
            para_text = _clean_markdown_text(" ".join(para_lines))
            pdf.set_font(font_family, size=9)
            pdf.set_text_color(30, 41, 59)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                pdf.epw,
                5.0,
                _sanitize_for_font(para_text),
                align="L",
            )
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)

    return bytes(pdf.output())


def write_pdf_report(
    markdown_content: str,
    output_path: Path | str,
    *,
    title: str = "Firmware Diagnostic Report",
    metadata: dict[str, Any] | None = None,
    tool_version: str | None = None,
    timestamp: str | None = None,
) -> Path:
    """Convert Markdown diagnostic report into a PDF file and save to disk."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = build_pdf_report(
        title=title,
        markdown_content=markdown_content,
        metadata=metadata,
        tool_version=tool_version,
        timestamp=timestamp,
    )
    out_p.write_bytes(pdf_bytes)
    return out_p


__all__ = [
    "build_pdf_report",
    "is_fpdf_available",
    "write_pdf_report",
]
