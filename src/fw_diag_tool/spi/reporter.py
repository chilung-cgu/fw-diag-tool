from __future__ import annotations

import math
import re

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import SPIReport, SPISeverity
from .statistics import compute_spi_statistics

_JEDEC_TITLE_RE = re.compile(
    r"^JEDEC ID Read Returned All (?P<value>0x(?:FF|00)) "
    r"\((?P<reason>[^)]+)\) @ Tx #(?P<tx>\d+)$"
)
_BUSY_TITLE_RE = re.compile(r"^Command issued while Flash is BUSY \(WIP=1\) @ Tx #(?P<tx>\d+)$")
_BUSY_DESCRIPTION_RE = re.compile(
    r"^Command (?P<command>.+) was issued while the most recent observed status register "
    r"reported BUSY=1\. The internal write/erase cycle has not finished\.$"
)
_WEL_ZERO_DESCRIPTION_RE = re.compile(
    r"^Command (?P<command>.+) was issued while the most recent observed status register "
    r"reported WEL=0\. The flash may reject the operation\.$"
)
_WEL_UNKNOWN_DESCRIPTION_RE = re.compile(
    r"^No WREN or status-read evidence before (?P<command>.+) was present inside this capture; "
    r"the operation's latch state cannot be proven\.$"
)
_STATUS_NO_WREN_DESCRIPTION_RE = re.compile(
    r"^Status Register write (?P<command>.+) issued without 0x06 \(WREN\) or 0x50 "
    r"\(Volatile WREN\)\.$"
)
_STATUS_WEL_UNKNOWN_DESCRIPTION_RE = re.compile(
    r"^No WREN or status evidence was captured before (?P<command>.+); "
    r"the write-enable precondition cannot be proven\.$"
)
_PAGE_WRAP_DESCRIPTION_RE = re.compile(
    r"^Page Program started at in-page offset (?P<offset>0x[0-9A-Fa-f]+) with payload length "
    r"(?P<length>\d+) bytes\. Total (?P<total_offset>0x[0-9A-Fa-f]+) \+ (?P<length_again>\d+) = "
    r"(?P<total>\d+) exceeds (?P<page_size>\d+)-byte page boundary\.$"
)
_TRUNCATED_DESCRIPTION_RE = re.compile(
    r"^Command (?P<command>.+) requires at least (?P<minimum>\d+) bytes "
    r"\(Opcode \+ 24-bit Address\), but CS went high after (?P<received>\d+) byte\(s\)\.$"
)

_QUALITY_MESSAGE_ZH = {
    "SPI_SOURCE_EMPTY": (
        "移除標題列／註解（header/comments）後沒有資料列；無法建立 SPI 協定結論。"
    ),
    "SPI_NO_TRANSACTIONS": (
        "輸入有資料列，但未解碼出任何以 CS 框定的 SPI 交易；請檢查 CS 極性與擷取框架（framing）。"
    ),
    "SPI_CS_UNTERMINATED": ("擷取結束時 CS 仍保持 asserted（作用中）；最後一筆交易可能被截斷。"),
    "SPI_RESPONSE_TRUNCATED": (
        "一或多個 SPI 指令在擷取到可信解碼所需的最小 response／payload 位元組前結束。"
    ),
    "SPI_RESPONSE_OVERLONG": (
        "一或多個固定寬度 SPI 指令攜帶超出解碼器契約（decoder contract）的位元組；"
        "額外 status payload 不視為可信的暫存器寫入。"
    ),
}
_QUALITY_SOURCE_MESSAGES = {
    "SPI_SOURCE_EMPTY": (
        "The capture has no data rows after removing the header/comments; "
        "no SPI protocol conclusion can be established."
    ),
    "SPI_NO_TRANSACTIONS": (
        "Input rows were present but no CS-framed SPI transaction was decoded; "
        "check chip-select polarity and capture framing."
    ),
    "SPI_CS_UNTERMINATED": (
        "The capture ended while CS was still asserted; the final transaction may be truncated."
    ),
    "SPI_RESPONSE_TRUNCATED": (
        "One or more SPI commands ended before the minimum response or payload "
        "bytes required for a trustworthy decode were captured."
    ),
    "SPI_RESPONSE_OVERLONG": (
        "One or more fixed-width SPI commands carried more bytes than the "
        "decoder contract permits; the extra status payload was not treated "
        "as a trustworthy register write."
    ),
}

_OPCODE_NAME_ZH = {
    "Read JEDEC ID": "讀取 JEDEC ID",
    "Read Device ID": "讀取 Device ID",
    "Read Unique ID": "讀取 Unique ID",
    "Read SFDP Register": "讀取 SFDP Register",
    "Read Data": "讀取資料",
    "Fast Read": "快速讀取",
    "Fast Read Dual Output": "快速讀取（Dual Output）",
    "Fast Read Quad Output": "快速讀取（Quad Output）",
    "Write Enable / WREN": "寫入使能／WREN",
    "Write Disable / WRDI": "寫入停用／WRDI",
    "Volatile SR Write Enable": "易失性狀態暫存器寫入使能（Volatile SR Write Enable）",
    "Page Program": "頁面寫入",
    "Quad Page Program": "四線頁面寫入",
    "Sector Erase 4KB": "4KB 扇區抹除",
    "Block Erase 32KB": "32KB 區塊抹除",
    "Block Erase 64KB": "64KB 區塊抹除",
    "Chip Erase": "晶片抹除",
    "Chip Erase Alternate": "替代晶片抹除",
    "Read Status Register-1": "讀取 Status Register-1",
    "Write Status Register-1": "寫入 Status Register-1",
    "Read Status Register-2": "讀取 Status Register-2",
    "Write Status Register-2": "寫入 Status Register-2",
    "Read Status Register-3": "讀取 Status Register-3",
    "Write Status Register-3": "寫入 Status Register-3",
    "Deep Power-Down": "深度 Power-Down",
    "Release Deep Power-Down": "解除深度 Power-Down",
    "Enable Reset": "啟用重置",
    "Reset Device": "重置裝置",
}
_OPCODE_NAME_RE = re.compile(r"^(?P<name>.+) \((?P<opcode>0x[0-9A-Fa-f]+)\)$")
_DETAIL_KEY_ZH = {
    "mfr_id": "製造商 ID（mfr_id）",
    "mem_type": "記憶體類型（mem_type）",
    "capacity_id": "容量 ID（capacity_id）",
    "identified_chip": "識別晶片（identified_chip）",
    "read_address": "讀取位址（read_address）",
    "read_bytes": "讀取位元組數（read_bytes）",
    "program_address": "寫入位址（program_address）",
    "program_bytes": "寫入位元組數（program_bytes）",
    "page_start_offset": "頁內起點（page_start_offset）",
    "page_size": "頁面大小（page_size）",
    "erase_address": "抹除位址（erase_address）",
    "sr1_raw": "狀態暫存器 1 原始值（Status Register-1；sr1_raw）",
    "busy": "忙碌狀態（busy）",
    "wel": "寫入使能狀態（wel）",
    "block_protect": "區塊保護（block_protect）",
    "response_truncated": "回應截斷（response_truncated）",
    "response_overlong": "回應過長（response_overlong）",
    "capture_incomplete": "擷取不完整（capture_incomplete）",
    "page_wrap_hazard": "頁面回繞風險（page_wrap_hazard）",
    "required_mosi_bytes": "要求的 MOSI 位元組數（required_mosi_bytes）",
    "required_miso_bytes": "要求的 MISO 位元組數（required_miso_bytes）",
    "received_mosi_bytes": "收到的 MOSI 位元組數（received_mosi_bytes）",
    "received_miso_bytes": "收到的 MISO 位元組數（received_miso_bytes）",
    "status_write_bytes": "Status Register 寫入位元組數（status_write_bytes）",
    "wel_evidence": "WEL 證據（wel_evidence）",
    "busy_state_observed": "觀察到的忙碌狀態（busy_state_observed）",
    "wel_reset_evidence": "WEL 重設證據（wel_reset_evidence）",
    "reset_evidence": "重設證據（reset_evidence）",
}
_DETAIL_VALUE_ZH = {
    "status-read": "Status Read 證據（status-read）",
    "unobserved": "未觀察到（unobserved）",
    "device-reset": "裝置重設（device-reset）",
    "reset-enable-not-observed": "未觀察到 reset-enable（reset-enable-not-observed）",
}


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _localize_chip_name(value: str) -> str:
    if not value:
        return ""
    if value == "Unknown / Generic SPI Flash":
        return "未知／通用 SPI Flash（Unknown / Generic SPI Flash）"
    if value == "Unknown Manufacturer / Model":
        return "未知製造商／型號（Unknown Manufacturer / Model）"
    return value


def _localize_opcode_name(value: str) -> str:
    if not value:
        return "無資料（No Data）"
    match = _OPCODE_NAME_RE.fullmatch(value)
    if match:
        name = match.group("name")
        localized = _OPCODE_NAME_ZH.get(name)
        if localized:
            return f"{localized}（{name}；{match.group('opcode')}）"
        return f"未知 Opcode（{value}）"
    if value == "Unknown Opcode" or value.startswith("Unknown Opcode ("):
        return f"未知 Opcode（{value}）"
    if value == "No Data":
        return "無資料（No Data）"
    if _contains_cjk(value):
        return value
    return f"未知 Opcode（{value}）"


def _localize_detail_key(value: str) -> str:
    if value in _DETAIL_KEY_ZH:
        return _DETAIL_KEY_ZH[value]
    if _contains_cjk(value):
        return value
    return f"欄位（{value}）"


def _localize_detail_value(value: object) -> str:
    if isinstance(value, bool):
        return f"{'是' if value else '否'}（{value}）"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    translated = _DETAIL_VALUE_ZH.get(text)
    if translated:
        return translated
    if _contains_cjk(text) or re.fullmatch(r"0x[0-9A-Fa-f]+", text):
        return text
    return f"未知值（{text}）"


def _localize_detail(key: str, value: object) -> str:
    label = _localize_detail_key(key)
    if key == "identified_chip":
        shown = _localize_chip_name(str(value))
    else:
        shown = _localize_detail_value(value)
    return f"{label}: {shown}"


def _localize_severity(value: SPISeverity | str) -> str:
    text = value.value if isinstance(value, SPISeverity) else str(value)
    localized = {
        "INFO": "資訊（INFO）",
        "WARNING": "警告（WARNING）",
        "ERROR": "錯誤（ERROR）",
        "CRITICAL": "嚴重（CRITICAL）",
    }.get(text)
    if localized:
        return localized
    if _contains_cjk(text):
        return text
    return f"未知嚴重度（{text}）"


def _localize_quality_message(code: str, value: str) -> str:
    localized = _QUALITY_MESSAGE_ZH.get(code)
    if localized and value == _QUALITY_SOURCE_MESSAGES.get(code):
        return localized
    if localized:
        return f"{localized}（原始訊息：{value}）"
    if _contains_cjk(value):
        return value
    return f"未知資料品質問題（{code}）：{value}"


def _localize_issue_title(value: str) -> str:
    if not value:
        return "未知 SPI 異常（無標題）"
    match = _JEDEC_TITLE_RE.fullmatch(value)
    if match:
        reason = {
            "Floating MISO / No Power": "MISO 浮接／未供電（Floating MISO / No Power）",
            "MISO Short to GND / Bus Clamped": "MISO 對地短路／匯流排被箝位（MISO Short to GND / Bus Clamped）",
        }.get(match.group("reason"), f"未知原因（{match.group('reason')}）")
        return f"JEDEC ID 讀取回傳全為 {match.group('value')}（{reason}） @ Tx #{match.group('tx')}"
    match = _BUSY_TITLE_RE.fullmatch(value)
    if match:
        return f"Flash 忙碌（BUSY，WIP=1）時仍發送指令 @ Tx #{match.group('tx')}"
    title_translations = {
        "Write/Erase observed with WEL=0": "觀察到寫入／抹除時 WEL=0",
        "Write/Erase WEL state was not observed": "寫入／抹除的 WEL 狀態未觀察到",
        "Write Status Register without WREN (0x06 / 0x50)": "寫入 Status Register 時未先執行 WREN（0x06／0x50）",
        "Status-register write WEL state was not observed": "Status Register 寫入的 WEL 狀態未觀察到",
        "Page Program Buffer Wrap-Around Hazard": "Page Program buffer 發生 Wrap-around 風險",
        "Incomplete SPI Command / Early CS Deassertion": "SPI 指令不完整／CS 提早解除",
    }
    for prefix, localized in title_translations.items():
        if value.startswith(prefix):
            suffix = value[len(prefix) :]
            return f"{localized}{suffix}"
    if _contains_cjk(value):
        return value
    return f"未知 SPI 異常（{value}）"


def _localize_issue_description(value: str) -> str:
    if value == (
        "JEDEC ID command (0x9F) returned [0xFF, 0xFF, 0xFF]. Flash device did not drive MISO line."
    ):
        return "JEDEC ID 指令（0x9F）回傳 [0xFF, 0xFF, 0xFF]；Flash 裝置未驅動 MISO 線。"
    if value == (
        "JEDEC ID command (0x9F) returned [0x00, 0x00, 0x00]. MISO line is clamped to GND."
    ):
        return "JEDEC ID 指令（0x9F）回傳 [0x00, 0x00, 0x00]；MISO 線被箝位至 GND。"

    match = _BUSY_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"指令 {_localize_opcode_name(match.group('command'))} 發送時，最近一次觀察到的"
            "狀態暫存器（status register）顯示"
            "BUSY=1；內部寫入／抹除週期尚未完成。"
        )
    match = _WEL_ZERO_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"指令 {_localize_opcode_name(match.group('command'))} 發送時，最近一次觀察到的"
            "狀態暫存器（status register）顯示"
            "WEL=0；Flash 可能拒絕此操作。"
        )
    match = _WEL_UNKNOWN_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"本次擷取在 {_localize_opcode_name(match.group('command'))} 之前沒有 WREN 或"
            "狀態讀取（status-read）證據；"
            "無法證明操作當下的 latch（鎖存）狀態。"
        )
    match = _STATUS_NO_WREN_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"Status Register 寫入 {_localize_opcode_name(match.group('command'))} 未搭配 "
            "0x06（WREN）或 "
            "0x50（Volatile WREN）。"
        )
    match = _STATUS_WEL_UNKNOWN_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"在 {_localize_opcode_name(match.group('command'))} 之前未擷取到 WREN 或 status（狀態）"
            "證據；無法證明寫入使能前提。"
        )
    match = _PAGE_WRAP_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"Page Program 從頁內位移 {match.group('offset')} 開始，Payload 長度 "
            f"{match.group('length')} bytes（位元組）；總和 {match.group('total_offset')} + "
            f"{match.group('length_again')} = {match.group('total')}，超過 "
            f"{match.group('page_size')}-byte page boundary（頁面邊界）。"
        )
    match = _TRUNCATED_DESCRIPTION_RE.fullmatch(value)
    if match:
        return (
            f"指令 {_localize_opcode_name(match.group('command'))} 至少需要 {match.group('minimum')} bytes"
            f"（Opcode + 24-bit Address），但 CS 在收到 {match.group('received')} byte(s) 後已拉高。"
        )
    if _contains_cjk(value):
        return value
    return f"未知 SPI 異常描述（原始：{value}）"


def _localize_root_cause(value: str) -> str:
    if not value:
        return ""
    if "\n" in value:
        return "\n".join(_localize_root_cause(line) for line in value.splitlines())
    translated = value.replace("【Root Cause 排查建議】", "【根因排查建議（Root Cause）】", 1)
    if translated != value or _contains_cjk(value):
        return translated
    if value.startswith("Root Cause: "):
        return f"根因：{value.removeprefix('Root Cause: ')}（原始：{value}）"
    return f"根因排查指南（原始：{value}）"


class SPIReporter:
    @staticmethod
    def _format_time(value: object) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return f"{value:.6f}"
        return "n/a"

    @staticmethod
    def render_terminal(report: SPIReport, console: Console | None = None) -> None:
        c = console or Console()

        chip_str = _localize_chip_name(
            report.summary.detected_flash_chip or "Unknown / Generic SPI Flash"
        )
        c.print(
            Panel(
                f"[bold cyan]⚡ SPI / QSPI Flash 協定診斷報告（SPI / QSPI Flash Protocol Diagnostic Report）[/]\n"
                f"識別 Flash 晶片（Identified Chip）: [yellow]{chip_str}[/]"
            )
        )

        sum_table = Table(title="傳輸摘要（Traffic Summary）", show_header=True)
        sum_table.add_column("指標（Metric）", style="cyan")
        sum_table.add_column("數量（Count）", style="yellow")
        sum_table.add_row(
            "總交易次數（Total Transactions）", str(report.summary.total_transactions)
        )
        sum_table.add_row("讀取操作（Read Operations）", str(report.summary.read_count))
        sum_table.add_row("Page Program 次數（Page Programs）", str(report.summary.write_count))
        sum_table.add_row("抹除操作（Erase Operations）", str(report.summary.erase_count))
        sum_table.add_row("狀態輪詢（Status Polls）", str(report.summary.status_poll_count))
        sum_table.add_row(
            "偵測到的異常（Anomalies Detected）",
            f"[bold red]{report.summary.anomaly_count}[/]"
            if report.summary.anomaly_count > 0
            else "[green]0[/]",
        )
        c.print(sum_table)

        if report.data_quality_issues:
            c.print("\n[yellow]⚠ SPI 來源證據限制（SPI source evidence limitations）:[/]")
            for issue in report.data_quality_issues:
                c.print(
                    f"[yellow]• {issue.code}（{issue.count}）："
                    f"{_localize_quality_message(issue.code, issue.message)}[/]"
                )

        if report.anomalies:
            c.print(
                "\n[bold red]🚨 Flash 協定異常與風險（Detected Flash Protocol Anomalies & Hazards）:[/]"
            )
            for a in report.anomalies:
                color = (
                    "red" if a.severity in (SPISeverity.CRITICAL, SPISeverity.ERROR) else "yellow"
                )
                c.print(
                    Panel(
                        f"[{color} bold]{_localize_issue_title(a.title)}[/]\n\n"
                        f"[bold]描述（Description）:[/] {_localize_issue_description(a.description)}\n\n"
                        f"[bold]根因與除錯指南（RCA & Debug Guide）:[/]\n"
                        f"{_localize_root_cause(a.root_cause_guide)}",
                        title=(
                            f"[{color}][{_localize_severity(a.severity)}] "
                            f"異常（Anomaly）#{a.transaction_id}[/]"
                        ),
                        border_style=color,
                    )
                )
        elif not report.data_quality_issues:
            c.print(
                "\n[green]✔ 未偵測到 SPI／Flash 異常；所有交易符合規範。"
                "（No SPI / Flash anomalies detected. All transactions compliant.）[/]"
            )
        else:
            c.print(
                "\n[yellow]⚠ 未能由現有證據證明 SPI 異常；來源證據不完整。"
                "（No SPI anomaly was proven; the source evidence is incomplete.）[/]"
            )

    @staticmethod
    def to_markdown(report: SPIReport) -> str:
        lines: list[str] = []
        chip_str = _localize_chip_name(
            report.summary.detected_flash_chip or "Unknown / Generic SPI Flash"
        )
        lines.append("# SPI / QSPI Flash 診斷報告（SPI / QSPI Flash Diagnostic Report）\n")
        lines.append(f"- **識別 Flash 晶片（Identified Flash Chip）**: `{chip_str}`")
        lines.append(
            f"- **總交易次數（Total Transactions）**: `{report.summary.total_transactions}`"
        )
        lines.append(
            f"- **讀取／寫入／抹除（Read / Program / Erase）**: "
            f"`{report.summary.read_count}` / `{report.summary.write_count}` / "
            f"`{report.summary.erase_count}`"
        )
        lines.append(
            f"- **偵測到的異常（Anomalies Detected）**: `{report.summary.anomaly_count}`\n"
        )

        stats = compute_spi_statistics(report)
        lines.append("## 📊 SPI 操作統計（SPI Operation Statistics）")
        lines.append(
            f"- **總傳輸位元組數（Total Bytes Transferred）**: `{stats.total_bytes_transferred}` bytes"
        )
        throughput_str = (
            f"`{stats.throughput_bytes_per_sec:.2f}` B/s"
            if stats.throughput_bytes_per_sec is not None
            else "無時間戳資料（Unavailable）"
        )
        lines.append(f"- **傳輸吞吐量（Throughput）**: {throughput_str}")
        latency_str = (
            f"`{stats.avg_command_latency_us:.2f}` µs"
            if stats.avg_command_latency_us is not None
            else "無時間戳資料（Unavailable）"
        )
        lines.append(f"- **平均指令延遲（Avg Command Latency）**: {latency_str}")
        lines.append(f"- **BUSY 輪詢次數（BUSY Poll Count）**: `{stats.busy_poll_count}`")
        busy_wait_str = (
            f"`{stats.avg_busy_wait_us:.2f}` µs"
            if stats.avg_busy_wait_us is not None
            else "無（None）"
        )
        lines.append(f"- **平均 BUSY 等待時間（Avg BUSY Wait Duration）**: {busy_wait_str}\n")

        if stats.command_distribution:
            lines.append("### 指令頻率分佈（Command Distribution）")
            lines.append("| 指令名稱（Command Name） | 次數（Count） |")
            lines.append("|---|---|")
            for cmd_name, count in sorted(stats.command_distribution.items(), key=lambda x: -x[1]):
                lines.append(f"| {_localize_opcode_name(cmd_name)} | `{count}` |")
            lines.append("")

        if report.data_quality_issues:
            lines.append("## ⚠ 資料品質限制（Data Quality Limitations）")
            for issue in report.data_quality_issues:
                lines.append(
                    f"- **{issue.code}**（{issue.count} 筆）："
                    f"{_localize_quality_message(issue.code, issue.message)}"
                )
            lines.append("")

        if report.anomalies:
            lines.append(
                "## 🚨 協定異常與根因分析（Detected Protocol Anomalies & Root Cause Analysis）"
            )
            for idx, a in enumerate(report.anomalies, 1):
                lines.append(
                    f"### #{idx}：[{_localize_severity(a.severity)}] "
                    f"{_localize_issue_title(a.title)} @ 時間（Time）: "
                    f"{SPIReporter._format_time(a.timestamp)}s"
                )
                lines.append(
                    f"- **描述（Description）**: {_localize_issue_description(a.description)}"
                )
                lines.append(f"\n```text\n{_localize_root_cause(a.root_cause_guide)}\n```\n")

        lines.append("## 📜 SPI 交易記錄（SPI Transaction Log；範例 Sample）")
        lines.append(
            "| 索引（Index） | 時間（s） | 操作碼（Opcode） | 名稱（Name） | "
            "位址（Address） | 資料長度（Data Len） | 細節（Details） |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for tx in report.transactions[:50]:
            addr_str = f"0x{tx.address:06X}" if tx.address is not None else "-"
            detail_str = (
                ", ".join(_localize_detail(k, v) for k, v in tx.decoded_details.items())
                if tx.decoded_details
                else "-"
            )
            op_hex = f"0x{tx.opcode:02X}" if tx.opcode is not None else "-"
            lines.append(
                f"| #{tx.index} | `{SPIReporter._format_time(tx.start_time)}` | `{op_hex}` | "
                f"{_localize_opcode_name(tx.opcode_name)} | `{addr_str}` | "
                f"{tx.data_payload_len} B | {detail_str} |"
            )

        return "\n".join(lines)
