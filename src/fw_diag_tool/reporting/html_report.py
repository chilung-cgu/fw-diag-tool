"""HTML report generator for firmware diagnostic suite.

Converts Markdown diagnostic reports into self-contained, beautifully styled HTML
documents with a modern dark theme consistent with the fw-diag GUI.
No external network dependencies or third-party packages required.
"""

from __future__ import annotations

import html
import re
import time
from pathlib import Path

from fw_diag_tool import __version__

# Dark theme CSS aligned with fw-diag GUI (#0f172a, #1e293b, #0ea5e9, #e2e8f0)
_DARK_THEME_CSS = """
:root {
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-tertiary: #334155;
    --bg-code: #020617;
    --text-primary: #e2e8f0;
    --text-muted: #94a3b8;
    --accent-primary: #0ea5e9;
    --accent-secondary: #38bdf8;
    --accent-hover: #0284c7;
    --border-color: #334155;
    --border-subtle: #1e293b;
    --color-success: #10b981;
    --color-warning: #f59e0b;
    --color-error: #ef4444;
    --color-info: #3b82f6;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.6;
    padding: 2rem 1rem;
}

.container {
    max-width: 1100px;
    margin: 0 auto;
    background-color: var(--bg-primary);
}

.report-header {
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.75rem 2rem;
    margin-bottom: 2rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.3);
}

.report-header h1 {
    color: var(--accent-secondary);
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.report-meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
}

.meta-item {
    font-size: 0.875rem;
}

.meta-label {
    color: var(--text-muted);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}

.meta-value {
    color: var(--text-primary);
    font-weight: 600;
    font-family: var(--font-mono);
}

.report-body {
    background-color: transparent;
}

h1, h2, h3, h4, h5, h6 {
    color: var(--text-primary);
    font-weight: 600;
    line-height: 1.3;
}

h1 {
    font-size: 1.6rem;
    color: var(--accent-secondary);
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 0.5rem;
    margin: 2rem 0 1rem;
}

h2 {
    font-size: 1.3rem;
    color: var(--accent-primary);
    margin: 1.75rem 0 0.875rem;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 0.35rem;
}

h3 {
    font-size: 1.1rem;
    color: var(--accent-secondary);
    margin: 1.25rem 0 0.5rem;
}

h4, h5, h6 {
    font-size: 1rem;
    margin: 1rem 0 0.5rem;
}

p {
    margin-bottom: 1rem;
}

a {
    color: var(--accent-secondary);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
    color: var(--accent-hover);
}

blockquote {
    background-color: rgba(30, 41, 59, 0.6);
    border-left: 4px solid var(--accent-primary);
    border-radius: 0 8px 8px 0;
    padding: 0.875rem 1.25rem;
    margin: 1.25rem 0;
    color: var(--text-primary);
}

blockquote p:last-child {
    margin-bottom: 0;
}

ul, ol {
    margin: 0.75rem 0 1.25rem 1.75rem;
}

li {
    margin-bottom: 0.35rem;
}

li > ul, li > ol {
    margin-top: 0.35rem;
    margin-bottom: 0.35rem;
}

code {
    background-color: var(--bg-secondary);
    color: var(--accent-secondary);
    font-family: var(--font-mono);
    font-size: 0.875em;
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    border: 1px solid var(--border-color);
}

pre {
    background-color: var(--bg-code);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin: 1.25rem 0;
    overflow-x: auto;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
}

pre code {
    background-color: transparent;
    color: var(--text-primary);
    padding: 0;
    border: none;
    font-size: 0.875rem;
    line-height: 1.5;
    display: block;
}

/* Tables */
.table-wrapper {
    width: 100%;
    overflow-x: auto;
    margin: 1.25rem 0;
    border-radius: 8px;
    border: 1px solid var(--border-color);
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    text-align: left;
}

thead th {
    background-color: var(--bg-secondary);
    color: var(--accent-primary);
    font-weight: 600;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    white-space: nowrap;
}

tbody td {
    padding: 0.65rem 1rem;
    border-bottom: 1px solid var(--border-color);
    color: var(--text-primary);
}

tbody tr:last-child td {
    border-bottom: none;
}

tbody tr:nth-child(even) {
    background-color: rgba(30, 41, 59, 0.4);
}

tbody tr:hover {
    background-color: rgba(51, 65, 85, 0.4);
}

hr {
    border: none;
    border-top: 1px solid var(--border-color);
    margin: 2rem 0;
}

/* Badges */
.badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    vertical-align: middle;
}

.badge-error {
    background-color: rgba(239, 68, 68, 0.2);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.4);
}

.badge-warning {
    background-color: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.4);
}

.badge-info {
    background-color: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    border: 1px solid rgba(59, 130, 246, 0.4);
}

.badge-success {
    background-color: rgba(16, 185, 129, 0.2);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.4);
}

/* Footer */
.report-footer {
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-color);
    color: var(--text-muted);
    font-size: 0.8rem;
    text-align: center;
}
"""


def _inline_markdown_to_html(text: str) -> str:
    """Convert inline Markdown tags into HTML formatting."""
    out = html.escape(text)

    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"__(.+?)__", r"<strong>\1</strong>", out)
    out = re.sub(r"\*([^\*]+?)\*", r"<em>\1</em>", out)
    out = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<em>\1</em>", out)
    out = re.sub(r"~~(.+?)~~", r"<del>\1</del>", out)
    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        out,
    )

    out = re.sub(
        r"\[(CRITICAL|ERROR|FATAL|嚴重|錯誤)\]", r'<span class="badge badge-error">\1</span>', out
    )
    out = re.sub(r"\[(WARNING|WARN|警告)\]", r'<span class="badge badge-warning">\1</span>', out)
    out = re.sub(r"\[(INFO|NOTE|提示|資訊)\]", r'<span class="badge badge-info">\1</span>', out)
    out = re.sub(
        r"\[(OK|PASS|SUCCESS|通過|正常|成功)\]", r'<span class="badge badge-success">\1</span>', out
    )

    return out


def _parse_table(lines: list[str]) -> str:
    """Parse Markdown table lines into HTML table markup."""
    if len(lines) < 2:
        return "<p>" + "<br />".join(_inline_markdown_to_html(l) for l in lines) + "</p>"

    header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
    alignments: list[str] = []
    delim_cells = [c.strip() for c in lines[1].strip("|").split("|")]
    for cell in delim_cells:
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append("center")
        elif cell.endswith(":"):
            alignments.append("right")
        elif cell.startswith(":"):
            alignments.append("left")
        else:
            alignments.append("left")

    while len(alignments) < len(header_cells):
        alignments.append("left")

    html_parts = ['<div class="table-wrapper">', "<table>", "<thead>", "<tr>"]
    for idx, cell in enumerate(header_cells):
        align = alignments[idx] if idx < len(alignments) else "left"
        align_attr = f' style="text-align: {align}"' if align != "left" else ""
        html_parts.append(f"<th{align_attr}>{_inline_markdown_to_html(cell)}</th>")
    html_parts.extend(["</tr>", "</thead>", "<tbody>"])

    for row_line in lines[2:]:
        if not row_line.strip():
            continue
        cells = [c.strip() for c in row_line.strip("|").split("|")]
        html_parts.append("<tr>")
        for idx, cell in enumerate(cells):
            align = alignments[idx] if idx < len(alignments) else "left"
            align_attr = f' style="text-align: {align}"' if align != "left" else ""
            html_parts.append(f"<td{align_attr}>{_inline_markdown_to_html(cell)}</td>")
        html_parts.append("</tr>")

    html_parts.extend(["</tbody>", "</table>", "</div>"])
    return "\n".join(html_parts)


def convert_markdown_to_html(
    markdown_text: str,
    *,
    title: str = "Firmware Diagnostic Report",
    tool_version: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Convert Markdown diagnostic report into a standalone, styled HTML document."""
    version_str = tool_version or __version__
    ts_str = timestamp or time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    lines = markdown_text.splitlines()
    body_html: list[str] = []
    idx = 0
    total_lines = len(lines)

    while idx < total_lines:
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines: list[str] = []
            idx += 1
            while idx < total_lines and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < total_lines:
                idx += 1
            code_content = html.escape("\n".join(code_lines))
            lang_class = f' class="language-{html.escape(lang)}"' if lang else ""
            body_html.append(f"<pre><code{lang_class}>{code_content}</code></pre>")
            continue

        if (
            "|" in stripped
            and idx + 1 < total_lines
            and re.match(r"^\s*\|?[-:\s|]+\|?\s*$", lines[idx + 1])
        ):
            table_lines: list[str] = []
            while idx < total_lines and "|" in lines[idx].strip():
                table_lines.append(lines[idx])
                idx += 1
            body_html.append(_parse_table(table_lines))
            continue

        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            level = len(header_match.group(1))
            heading_content = _inline_markdown_to_html(header_match.group(2))
            body_html.append(f"<h{level}>{heading_content}</h{level}>")
            idx += 1
            continue

        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            body_html.append("<hr />")
            idx += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while idx < total_lines and lines[idx].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[idx].strip()))
                idx += 1
            quote_content = "<br />".join(_inline_markdown_to_html(q) for q in quote_lines)
            body_html.append(f"<blockquote><p>{quote_content}</p></blockquote>")
            continue

        list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.+)$", line)
        if list_match:
            list_items: list[str] = []
            is_ordered = bool(re.match(r"^\d+\.", list_match.group(2)))
            list_tag = "ol" if is_ordered else "ul"

            while idx < total_lines:
                curr_line = lines[idx]
                curr_match = re.match(r"^\s*([*-]|\d+\.)\s+(.+)$", curr_line)
                if not curr_match:
                    if curr_line.strip() == "":
                        if idx + 1 < total_lines and re.match(
                            r"^\s*([*-]|\d+\.)\s+(.+)$", lines[idx + 1]
                        ):
                            idx += 1
                            continue
                        break
                    else:
                        break
                item_content = _inline_markdown_to_html(curr_match.group(2))
                list_items.append(f"<li>{item_content}</li>")
                idx += 1

            body_html.append(f"<{list_tag}>\n" + "\n".join(list_items) + f"\n</{list_tag}>")
            continue

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
            para_content = "<br />".join(_inline_markdown_to_html(pl) for pl in para_lines)
            body_html.append(f"<p>{para_content}</p>")

    rendered_body = "\n".join(body_html)

    doc = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(title)}</title>
    <style>
{_DARK_THEME_CSS}
    </style>
</head>
<body>
    <div class="container">
        <header class="report-header">
            <h1>⚡ {html.escape(title)}</h1>
            <div class="report-meta-grid">
                <div class="meta-item">
                    <div class="meta-label">診斷套件（Tool）</div>
                    <div class="meta-value">fw-diag-tool v{html.escape(version_str)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">產生時間（Generated）</div>
                    <div class="meta-value">{html.escape(ts_str)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">報告格式（Format）</div>
                    <div class="meta-value">Standalone Dark HTML</div>
                </div>
            </div>
        </header>

        <main class="report-body">
{rendered_body}
        </main>

        <footer class="report-footer">
            <p>Generated by <strong>fw-diag-tool</strong> v{html.escape(version_str)} &bull; Diagnostic report for hardware and firmware verification.</p>
        </footer>
    </div>
</body>
</html>
"""
    return doc


def build_html_report(
    markdown_text: str,
    *,
    title: str = "Firmware Diagnostic Report",
    tool_version: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Alias for convert_markdown_to_html to provide consistent builder naming."""
    return convert_markdown_to_html(
        markdown_text,
        title=title,
        tool_version=tool_version,
        timestamp=timestamp,
    )


def write_html_report(
    markdown_text: str,
    output_path: Path | str,
    *,
    title: str = "Firmware Diagnostic Report",
    tool_version: str | None = None,
    timestamp: str | None = None,
) -> Path:
    """Convert Markdown text to HTML and save to output file."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    html_content = convert_markdown_to_html(
        markdown_text,
        title=title,
        tool_version=tool_version,
        timestamp=timestamp,
    )
    out_p.write_text(html_content, encoding="utf-8")
    return out_p


__all__ = [
    "build_html_report",
    "convert_markdown_to_html",
    "write_html_report",
]
