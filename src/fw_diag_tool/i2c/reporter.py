"""I2C / SMBus Diagnostic Report Generator with Rich Terminal UI & Markdown Exporter.

Generates clean, interactive terminal tables and comprehensive Markdown reports
complete with peripheral device maps, decoded transaction telemetry, timing graphs,
and actionable root-cause troubleshooting checklists for junior firmware engineers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fw_diag_tool.i2c.localization import (
    format_summary_text_zh,
    localize_category,
    localize_device_name,
    localize_direction,
    localize_input_format,
    localize_issue_advice,
    localize_issue_category,
    localize_issue_description,
    localize_issue_root_cause,
    localize_issue_title,
    localize_quality_message,
    localize_semantic_summary,
    localize_severity,
    localize_speed_mode,
    localize_status,
)
from fw_diag_tool.i2c.models import I2CAnalysisReport, I2CDirection, Severity
from fw_diag_tool.i2c.status import get_transaction_status


class I2CReporter:
    """Formats and exports I2CAnalysisReports into Rich UI and Markdown formats."""

    @classmethod
    def render_terminal(cls, report: I2CAnalysisReport, console: Console | None = None) -> None:
        """Render colorized diagnostic report in the terminal using Rich."""
        console = console or Console()

        # 1. Header Banner
        status_color = (
            "red"
            if any(i.severity in (Severity.CRITICAL, Severity.ERROR) for i in report.issues)
            else ("yellow" if report.issues or report.data_quality_issues else "green")
        )
        title_text = Text(
            "I2C / SMBus / PMBus 協定診斷報告（Protocol Diagnostic Report）", style="bold cyan"
        )
        subtitle_text = Text(
            format_summary_text_zh(
                report.total_events,
                report.total_transactions,
                len(report.devices_detected),
                len(report.issues),
            ),
            style="dim",
        )
        console.print(
            Panel(
                Text.assemble(title_text, "\n", subtitle_text),
                border_style=status_color,
                expand=False,
            )
        )

        # 2. Timing & Bus Health Summary Table
        timing_tbl = Table(
            title="匯流排時序與健康指標（Bus Timing & Health Metrics）",
            show_header=True,
            header_style="bold magenta",
        )
        timing_tbl.add_column("指標（Metric）", style="cyan")
        timing_tbl.add_column("數值（Value）", style="bold white")
        timing_tbl.add_column("標準／評估（Standard / Evaluation）", style="dim")

        t = report.timing_stats
        timing_tbl.add_row(
            "標稱速度模式", localize_speed_mode(t.speed_mode), "規格分類（Spec Class）"
        )
        if t.frequency_sample_count:
            timing_tbl.add_row(
                "平均 SCL 時鐘頻率",
                f"{t.avg_frequency_khz:.2f} kHz",
                f"最小：{t.min_frequency_khz:.1f} kHz；最大：{t.max_frequency_khz:.1f} kHz",
            )
        else:
            timing_tbl.add_row(
                "平均 SCL 時鐘頻率",
                "不可用（Unavailable）",
                "來源未提供位元率或位元組持續時間",
            )

        if t.frequency_sample_count:
            jitter_style = (
                "red"
                if t.frequency_jitter_pct > 35
                else ("yellow" if t.frequency_jitter_pct > 15 else "green")
            )
            timing_tbl.add_row(
                "時鐘頻率抖動",
                f"[{jitter_style}]{t.frequency_jitter_pct:.1f} %[/]",
                "< 15% 通常穩定；> 35% 可能表示電容過大或 ISR 干擾",
            )
            timing_tbl.add_row(
                "頻率分佈跨度（peak-to-peak）",
                f"{t.frequency_spread_pct:.1f} %",
                "相容別名：時鐘頻率抖動",
            )
        else:
            timing_tbl.add_row(
                "時鐘頻率抖動",
                "不可用（Unavailable）",
                "沒有頻率樣本",
            )
            timing_tbl.add_row(
                "頻率分佈跨度（peak-to-peak）",
                "不可用（Unavailable）",
                "沒有頻率樣本",
            )

        stretch_style = (
            "red"
            if t.max_clock_stretch_ms >= 25.0
            else ("yellow" if t.clock_stretch_count > 0 else "green")
        )
        timing_tbl.add_row(
            "時鐘延展事件",
            f"[{stretch_style}]{t.clock_stretch_count} 筆（最大：{t.max_clock_stretch_ms:.3f} ms）[/]",
            "SMBus 門檻：25 ms 逾時",
        )
        timing_tbl.add_row(
            "位元組間平均延遲",
            f"{t.avg_inter_byte_delay_us:.2f} µs",
            f"最大：{t.max_inter_byte_delay_us:.2f} µs（ISR 延遲）",
        )
        timing_tbl.add_row(
            "交易間平均間隔",
            f"{t.avg_inter_transaction_delay_ms:.2f} ms",
            f"最大：{t.max_inter_transaction_delay_ms:.2f} ms",
        )
        timing_tbl.add_row(
            "匯流排使用率",
            (
                f"{t.bus_utilization_pct:.2f} %"
                if t.bus_utilization_evidence != "unavailable"
                else "不可用（Unavailable）"
            ),
            (
                "主動傳輸時間／實測總持續時間"
                if t.bus_utilization_evidence != "unavailable"
                else "總追蹤持續時間不可用"
            ),
        )
        console.print(timing_tbl)
        console.print()

        # 3. Peripheral Device Map Table
        dev_tbl = Table(
            title="偵測到的週邊裝置分佈（Detected Peripheral Device Map）",
            show_header=True,
            header_style="bold blue",
        )
        dev_tbl.add_column("7-bit 位址", style="yellow")
        dev_tbl.add_column("8-bit（W/R）", style="dim")
        dev_tbl.add_column("識別裝置／晶片設定檔", style="bold white")
        dev_tbl.add_column("裝置類別", style="cyan")
        dev_tbl.add_column("協定", style="green")
        dev_tbl.add_column("交易次數", justify="right")

        for dev in report.devices_detected.values():
            address = dev.get("address_7bit", "unknown")
            device_name = dev.get("name") or f"Unknown Device ({address})"
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "; ".join(dev.get("candidates", []))
            dev_tbl.add_row(
                str(address),
                str(dev.get("address_8bit", "unknown")),
                localize_device_name(device_name),
                localize_category(dev.get("category")),
                str(dev.get("protocol") or "I2C"),
                str(dev.get("transaction_count", 0)),
            )
        console.print(dev_tbl)
        console.print()

        # 4. Decoded Transaction Table
        tx_tbl = Table(
            title="交易序列與解碼遙測（Transaction Sequence & Decoded Telemetry）",
            show_header=True,
            header_style="bold green",
        )
        tx_tbl.add_column("#", justify="right", style="dim")
        tx_tbl.add_column("時間（s）", style="dim")
        tx_tbl.add_column("位址", style="yellow")
        tx_tbl.add_column("方向（R/W）", style="bold")
        tx_tbl.add_column("原始十六進位資料", style="white")
        tx_tbl.add_column("解碼語意／遙測資料", style="bold cyan")
        tx_tbl.add_column("狀態", justify="center")

        for index, tx in enumerate(report.transactions):
            if tx.direction_available and isinstance(tx.direction, I2CDirection):
                rw_color = "cyan" if tx.direction == I2CDirection.READ else "magenta"
                rw_text = f"[{rw_color}]{localize_direction(tx.direction)}[/]"
            else:
                rw_text = "[yellow]UNKNOWN（未知）[/]"

            next_tx = (
                report.transactions[index + 1] if index + 1 < len(report.transactions) else None
            )
            status = get_transaction_status(tx, next_transaction=next_tx).value
            status_style = {
                "ACK": "green",
                "ADDR NAK": "red",
                "DATA NAK": "red",
                "READ END NAK": "blue",
                "ACK UNKNOWN": "yellow",
                "EVIDENCE INCOMPLETE": "yellow",
                "NO STOP": "bold red",
                "ABORTED": "bold red",
            }.get(status, "white")
            status_text = f"[{status_style}]{localize_status(status)}[/]"

            summary_str = localize_semantic_summary(tx.semantic_summary) or "-"
            if tx.decoded_values.get("rollover_hazard"):
                summary_str = f"[bold red]⚠️ {summary_str}[/]"

            tx_tbl.add_row(
                str(tx.id),
                f"{tx.start_time:.6f}" if tx.timestamp_available else "不可用",
                f"0x{tx.address_7bit:02X}" if tx.address_available else "不可用",
                rw_text,
                tx.hex_dump,
                summary_str,
                status_text,
            )
        console.print(tx_tbl)
        console.print()

        # 5. Diagnostic Findings & Junior Engineer Troubleshooting Advice
        if report.issues:
            console.print(
                Panel(
                    Text(
                        "異常診斷與逐步排查建議（Diagnostic Anomalies & Debugging Advice）",
                        style="bold white on red",
                    ),
                    expand=False,
                )
            )
            for issue in report.issues:
                sev_color = {
                    Severity.CRITICAL: "bold red",
                    Severity.ERROR: "red",
                    Severity.WARNING: "yellow",
                    Severity.INFO: "blue",
                }.get(issue.severity, "white")

                header = Text(
                    f"[{localize_severity(issue.severity)}] {issue.code}: "
                    f"{localize_issue_title(issue.code, issue.title)}",
                    style=sev_color,
                )

                body = Text()
                body.append(
                    f"\n● 異常現象描述：\n  {localize_issue_description(issue.description)}\n",
                    style="white",
                )
                body.append(
                    "\n● 可能原因假設（Hypotheses；不是已證明的根因）：\n",
                    style="bold yellow",
                )
                for rc_line in localize_issue_root_cause(issue.root_cause_analysis).split("\n"):
                    if rc_line.strip():
                        body.append(f"  {rc_line.strip()}\n", style="yellow")

                body.append("\n● 新手排查行動清單（Actionable Checklist）：\n", style="bold green")
                for advice in issue.actionable_advice:
                    body.append(f"  ✔ {localize_issue_advice(advice)}\n", style="green")

                console.print(
                    Panel(body, title=header.plain, title_align="left", border_style=sev_color)
                )
        if report.data_quality_issues:
            quality_lines = ["[bold yellow]來源證據與限制（不是協定異常）：[/]"]
            quality_lines.extend(
                f"• {issue.code}（{issue.count} 筆）："
                f"{localize_quality_message(issue.code, issue.message)}"
                for issue in report.data_quality_issues
            )
            console.print(
                Panel(
                    "\n".join(quality_lines), title="資料證據與品質限制（Data Quality Limitations）"
                )
            )

        if not report.issues and report.data_quality_issues:
            console.print(
                Panel(
                    "[bold yellow]⚠ 在現有證據下未證明有協定異常，但來源證據不完整；"
                    "宣稱追蹤記錄正常前，請先檢視資料證據與品質限制。[/]",
                    border_style="yellow",
                )
            )
        elif not report.issues:
            console.print(
                Panel(
                    "[bold green]✔ 未偵測到協定或時序異常；所有交易均通過目前可用的證據檢查。[/]",
                    border_style="green",
                )
            )

    @classmethod
    def generate_markdown(
        cls,
        report: I2CAnalysisReport,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Generate comprehensive Markdown diagnostic report."""
        lines: list[str] = []
        lines.append("# I2C / SMBus / PMBus 協定診斷報告（Protocol Diagnostic Report）")
        lines.append("")
        summary_zh = format_summary_text_zh(
            report.total_events,
            report.total_transactions,
            len(report.devices_detected),
            len(report.issues),
        )
        lines.append(f"> **總結摘要（Summary）**：{summary_zh}")
        lines.append("")

        if metadata:
            if not isinstance(metadata, Mapping):
                to_dict = getattr(metadata, "to_dict", None)
                metadata = to_dict() if callable(to_dict) else vars(metadata)
            lines.append("## 詮釋資料（Metadata）")
            lines.append("")
            metadata_values = {
                "分析工具（Tool）": metadata.get("tool", metadata.get("tool_name", "-")),
                "輸入檔名（Input name）": metadata.get("input_name", "-"),
                "輸入 SHA-256 雜湊（Input SHA-256）": metadata.get(
                    "input_sha256", metadata.get("input_hash", metadata.get("capture_sha256", "-"))
                ),
                "輸入格式（Input format）": localize_input_format(
                    metadata.get("input_format", metadata.get("input_mode", "-"))
                ),
                "SMBus 逾時門檻（SMBus timeout ms）": metadata.get(
                    "smbus_timeout_ms", metadata.get("timeout_ms", metadata.get("timeout", "-"))
                ),
                "板級設定檔（Board profile）": metadata.get(
                    "board_profile",
                    metadata.get("profile", metadata.get("board_profile_name", "-")),
                ),
                "時序證據樣本數（Evidence sample count）": metadata.get(
                    "evidence_sample_count",
                    metadata.get(
                        "evidence_samples",
                        metadata.get("sample_count", report.timing_stats.frequency_sample_count),
                    ),
                ),
            }
            if str(metadata_values["板級設定檔（Board profile）"]).lower() in {"none", "null", "-"}:
                metadata_values["板級設定檔（Board profile）"] = "未套用（none）"
            for label, value in metadata_values.items():
                lines.append(f"- **{label}**: `{value}`")
            lines.append("")

        # Summary Card
        lines.append("## 1. 匯流排時序與交易健康啟發評等（Bus Timing & Health）")
        lines.append("")
        lines.append("> 本健康度摘要為協定層證據之啟發式統計，非實體電氣特性或晶片良率之通過判定。")
        lines.append("")
        t = report.timing_stats
        lines.append(
            f"- **標準速度模式（Nominal Speed Mode）**：`{localize_speed_mode(t.speed_mode)}`"
        )
        if t.frequency_sample_count:
            lines.append(
                f"- **平均 SCL 時鐘頻率（Average Clock Frequency）**: `{t.avg_frequency_khz:.2f} kHz` "
                f"（最小：`{t.min_frequency_khz:.1f} kHz`；最大：`{t.max_frequency_khz:.1f} kHz`）"
            )
            lines.append(
                f"- **時鐘頻率抖動（Clock Frequency Jitter）**：`{t.frequency_jitter_pct:.1f} %`"
            )
            lines.append(
                f"- **頻率分佈跨度（Frequency Spread p-p）**：`{t.frequency_spread_pct:.1f} %`"
            )
        else:
            lines.append(
                "- **平均 SCL 時鐘頻率（Average Clock Frequency）**: `不可用（Unavailable）`（來源沒有每位元組時序或位元率證據）"
            )
            lines.append("- **時鐘頻率抖動（Clock Frequency Jitter）**: `不可用（Unavailable）`")
            lines.append("- **頻率分佈跨度（Frequency Spread p-p）**: `不可用（Unavailable）`")
        lines.append(
            f"- **時鐘延展事件（Clock Stretching Events）**：`{t.clock_stretch_count}` 筆（最大持續時間：`{t.max_clock_stretch_ms:.3f} ms`）"
        )
        lines.append(
            f"- **位元組間平均延遲（Avg Inter-byte Delay）**：`{t.avg_inter_byte_delay_us:.2f} µs`（最大值：`{t.max_inter_byte_delay_us:.2f} µs`）"
        )
        lines.append(
            f"- **交易間平均間隔（Avg Inter-transaction Delay）**：`{t.avg_inter_transaction_delay_ms:.2f} ms`"
        )
        if t.bus_utilization_evidence != "unavailable":
            lines.append(f"- **匯流排使用率（Bus Utilization）**：`{t.bus_utilization_pct:.2f} %`")
        else:
            lines.append(
                "- **匯流排使用率（Bus Utilization）**：`不可用（Unavailable）`（總捕捉時間不可用）"
            )
        lines.append("")

        # Device Map Table
        lines.append("## 2. 偵測到的從裝置分佈表（Detected Peripheral Device Map）")
        lines.append("")
        lines.append(
            "| 7-bit 位址 | 8-bit 位址（W/R） | 識別晶片型號（Device Profile） | 裝置類別（Category） | 協定（Protocol） | 交易次數 |"
        )
        lines.append("|---|---|---|---|---|---|")
        for dev in report.devices_detected.values():
            address = dev.get("address_7bit", "unknown")
            device_name = dev.get("name") or f"Unknown Device ({address})"
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "Possible: " + "; ".join(dev.get("candidates", []))
            lines.append(
                f"| `{address}` | `{dev.get('address_8bit', 'unknown')}` | **{localize_device_name(device_name)}** | "
                f"{localize_category(dev.get('category'))} | {dev.get('protocol') or 'I2C'} | {dev.get('transaction_count', 0)} |"
            )
        lines.append("")

        # Transaction Sequence Table
        lines.append("## 3. 封包交易序列與解碼明細（Transaction Sequence & Decoded Telemetry）")
        lines.append("")
        lines.append(
            "| # | 時間（s） | 位址 | 方向（R/W） | 原始資料（Raw Hex） | 協定語意與遙測解碼（Decoded Telemetry） | 狀態（Status） |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for index, tx in enumerate(report.transactions):
            next_tx = (
                report.transactions[index + 1] if index + 1 < len(report.transactions) else None
            )
            status = get_transaction_status(tx, next_transaction=next_tx).value

            summary = localize_semantic_summary(tx.semantic_summary) or "-"
            if tx.decoded_values.get("rollover_hazard"):
                summary = f"⚠️ **{summary}**"

            addr_text = f"0x{tx.address_7bit:02X}" if tx.address_available else "不可用"
            direction_text = localize_direction(
                tx.direction
                if tx.direction_available and isinstance(tx.direction, I2CDirection)
                else None
            )

            lines.append(
                f"| {tx.id} | {tx.start_time:.6f} | `{addr_text}` | `{direction_text}` | `{tx.hex_dump}` | {summary} | {localize_status(status)} |"
                if tx.timestamp_available
                else f"| {tx.id} | 不可用 | `{addr_text}` | `{direction_text}` | `{tx.hex_dump}` | {summary} | {localize_status(status)} |"
            )
        lines.append("")

        if report.data_quality_issues:
            lines.append("## ⚠ 資料證據與品質限制（Data Quality Limitations）")
            lines.append("")
            for quality_issue in report.data_quality_issues:
                zh_msg = localize_quality_message(quality_issue.code, quality_issue.message)
                lines.append(f"- **{quality_issue.code}** ({quality_issue.count} 筆): {zh_msg}")
            lines.append("")

        # Diagnostic Issues & Advice
        lines.append("## 4. 異常診斷與排查行動建議（Diagnostic Issues & Debugging Advice）")
        lines.append("")
        if not report.issues and report.data_quality_issues:
            lines.append(
                "⚠ **在現有證據下未發現違規規則，但來源資料品質不完整；在確認通訊正常前請先檢視上方資料限制。**"
            )
        elif not report.issues:
            lines.append("✔ **所有交易均順利完成，未偵測到任何 I2C/SMBus 協定或時序異常。**")
        else:
            for idx, diagnostic_issue in enumerate(report.issues, 1):
                lines.append(
                    f"### 4.{idx} [{localize_severity(diagnostic_issue.severity)}] "
                    f"{diagnostic_issue.code}: {localize_issue_title(diagnostic_issue.code, diagnostic_issue.title)}"
                )
                lines.append("")
                lines.append(
                    f"- **異常分類（Category）**: `{localize_issue_category(diagnostic_issue.category)}`"
                )
                if diagnostic_issue.address_7bit is not None:
                    lines.append(
                        f"- **從裝置位址（Device Address）**：`0x{diagnostic_issue.address_7bit:02X}`"
                    )
                lines.append(
                    f"- **現象描述（Description）**: "
                    f"{localize_issue_description(diagnostic_issue.description)}"
                )
                lines.append("")
                lines.append("**可能原因假設（Hypotheses；不是已證明的根因）**:")
                for rc_line in localize_issue_root_cause(
                    diagnostic_issue.root_cause_analysis
                ).split("\n"):
                    if rc_line.strip():
                        lines.append(f"- {rc_line.strip()}")
                lines.append("")
                lines.append("**新手排查行動建議（Actionable Debug Checklist）**：")
                for advice in diagnostic_issue.actionable_advice:
                    lines.append(f"- [ ] {localize_issue_advice(advice)}")
                lines.append("")

        return "\n".join(lines)

    @classmethod
    def to_markdown(
        cls,
        report: I2CAnalysisReport,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Backward-compatible report export alias."""
        return cls.generate_markdown(report, metadata=metadata)
