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
    localize_quality_message,
    localize_semantic_summary,
    localize_speed_mode,
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
        title_text = Text("I2C / SMBus / PMBus Protocol Diagnostic Report", style="bold cyan")
        subtitle_text = Text(report.summary_text, style="dim")
        console.print(
            Panel(
                Text.assemble(title_text, "\n", subtitle_text),
                border_style=status_color,
                expand=False,
            )
        )

        # 2. Timing & Bus Health Summary Table
        timing_tbl = Table(
            title="Bus Timing & Health Metrics", show_header=True, header_style="bold magenta"
        )
        timing_tbl.add_column("Metric", style="cyan")
        timing_tbl.add_column("Value", style="bold white")
        timing_tbl.add_column("Standard / Evaluation", style="dim")

        t = report.timing_stats
        timing_tbl.add_row("Nominal Speed Mode", t.speed_mode.value, "Spec Class")
        if t.frequency_sample_count:
            timing_tbl.add_row(
                "Avg SCL Clock Frequency",
                f"{t.avg_frequency_khz:.2f} kHz",
                f"Min: {t.min_frequency_khz:.1f}k, Max: {t.max_frequency_khz:.1f}k",
            )
        else:
            timing_tbl.add_row(
                "Avg SCL Clock Frequency",
                "Unavailable",
                "No source-provided bitrate or byte duration",
            )

        if t.frequency_sample_count:
            jitter_style = (
                "red"
                if t.frequency_jitter_pct > 35
                else ("yellow" if t.frequency_jitter_pct > 15 else "green")
            )
            timing_tbl.add_row(
                "Clock Frequency Jitter",
                f"[{jitter_style}]{t.frequency_jitter_pct:.1f} %[/]",
                "< 15% is stable; > 35% indicates high capacitance/ISR",
            )
            timing_tbl.add_row(
                "Frequency Spread (peak-to-peak)",
                f"{t.frequency_spread_pct:.1f} %",
                "Compatibility alias: Clock Frequency Jitter",
            )
        else:
            timing_tbl.add_row(
                "Clock Frequency Jitter",
                "Unavailable",
                "No frequency samples",
            )
            timing_tbl.add_row(
                "Frequency Spread (peak-to-peak)",
                "Unavailable",
                "No frequency samples",
            )

        stretch_style = (
            "red"
            if t.max_clock_stretch_ms >= 25.0
            else ("yellow" if t.clock_stretch_count > 0 else "green")
        )
        timing_tbl.add_row(
            "Clock Stretching Events",
            f"[{stretch_style}]{t.clock_stretch_count} event(s) (Max: {t.max_clock_stretch_ms:.3f} ms)[/]",
            "SMBus limit: 25ms timeout",
        )
        timing_tbl.add_row(
            "Avg Inter-byte Delay",
            f"{t.avg_inter_byte_delay_us:.2f} µs",
            f"Max: {t.max_inter_byte_delay_us:.2f} µs (ISR latency)",
        )
        timing_tbl.add_row(
            "Avg Inter-transaction Delay",
            f"{t.avg_inter_transaction_delay_ms:.2f} ms",
            f"Max: {t.max_inter_transaction_delay_ms:.2f} ms",
        )
        timing_tbl.add_row(
            "Bus Utilization",
            (
                f"{t.bus_utilization_pct:.2f} %"
                if t.bus_utilization_evidence != "unavailable"
                else "Unavailable"
            ),
            (
                "Active transfer time / measured total duration"
                if t.bus_utilization_evidence != "unavailable"
                else "Total trace duration is unavailable"
            ),
        )
        console.print(timing_tbl)
        console.print()

        # 3. Peripheral Device Map Table
        dev_tbl = Table(
            title="Detected Peripheral Device Map", show_header=True, header_style="bold blue"
        )
        dev_tbl.add_column("7-bit Addr", style="yellow")
        dev_tbl.add_column("8-bit (W/R)", style="dim")
        dev_tbl.add_column("Identified Device / Chip Profile", style="bold white")
        dev_tbl.add_column("Category", style="cyan")
        dev_tbl.add_column("Protocol", style="green")
        dev_tbl.add_column("Transactions", justify="right")

        for dev in report.devices_detected.values():
            address = dev.get("address_7bit", "unknown")
            device_name = dev.get("name") or f"Unknown Device ({address})"
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "; ".join(dev.get("candidates", []))
            dev_tbl.add_row(
                str(address),
                str(dev.get("address_8bit", "unknown")),
                device_name,
                str(dev.get("category") or "General I2C Peripheral"),
                str(dev.get("protocol") or "I2C"),
                str(dev.get("transaction_count", 0)),
            )
        console.print(dev_tbl)
        console.print()

        # 4. Decoded Transaction Table
        tx_tbl = Table(
            title="Transaction Sequence & Decoded Telemetry",
            show_header=True,
            header_style="bold green",
        )
        tx_tbl.add_column("#", justify="right", style="dim")
        tx_tbl.add_column("Time (s)", style="dim")
        tx_tbl.add_column("Addr", style="yellow")
        tx_tbl.add_column("R/W", style="bold")
        tx_tbl.add_column("Raw Hex Bytes", style="white")
        tx_tbl.add_column("Decoded Semantic Meaning / Telemetry", style="bold cyan")
        tx_tbl.add_column("Status", justify="center")

        for index, tx in enumerate(report.transactions):
            if tx.direction_available and isinstance(tx.direction, I2CDirection):
                rw_color = "cyan" if tx.direction == I2CDirection.READ else "magenta"
                rw_text = f"[{rw_color}]{tx.direction.value}[/]"
            else:
                rw_text = "[yellow]UNKNOWN[/]"

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
            status_text = f"[{status_style}]{status}[/]"

            summary_str = tx.semantic_summary or "-"
            if tx.decoded_values.get("rollover_hazard"):
                summary_str = f"[bold red]⚠️ {summary_str}[/]"

            tx_tbl.add_row(
                str(tx.id),
                f"{tx.start_time:.6f}" if tx.timestamp_available else "n/a",
                f"0x{tx.address_7bit:02X}" if tx.address_available else "n/a",
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
                        "Diagnostic Anomalies & Step-by-Step Debugging Advice",
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
                    f"[{issue.severity.value}] {issue.code}: {issue.title}", style=sev_color
                )

                body = Text()
                body.append(f"\n● 異常現象描述:\n  {issue.description}\n", style="white")
                body.append(
                    "\n● 可能原因假設 (Hypotheses; not proven root cause):\n", style="bold yellow"
                )
                for rc_line in issue.root_cause_analysis.split("\n"):
                    if rc_line.strip():
                        body.append(f"  {rc_line.strip()}\n", style="yellow")

                body.append("\n● 新手排查行動清單 (Actionable Checklist):\n", style="bold green")
                for advice in issue.actionable_advice:
                    body.append(f"  ✔ {advice}\n", style="green")

                console.print(
                    Panel(body, title=header.plain, title_align="left", border_style=sev_color)
                )
        if report.data_quality_issues:
            quality_lines = [
                "[bold yellow]Source evidence limitations (these are not protocol findings):[/]"
            ]
            quality_lines.extend(
                f"• {issue.code} ({issue.count}): {issue.message}"
                for issue in report.data_quality_issues
            )
            console.print(Panel("\n".join(quality_lines), title="Data Quality Limitations"))

        if not report.issues and report.data_quality_issues:
            console.print(
                Panel(
                    "[bold yellow]⚠ No protocol anomaly was proven, but source evidence is incomplete. "
                    "Review the Data Quality Limitations before calling the trace clean.[/]",
                    border_style="yellow",
                )
            )
        elif not report.issues:
            console.print(
                Panel(
                    "[bold green]✔ No Protocol or Timing Anomalies Detected. All Transactions Passed Cleanly.[/]",
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
        lines.append("# I2C / SMBus / PMBus Protocol Diagnostic Report (協定診斷報告)")
        lines.append("")
        summary_zh = format_summary_text_zh(
            report.total_events,
            report.total_transactions,
            len(report.devices_detected),
            len(report.issues),
        )
        lines.append(f"> **總結摘要 (Summary)**: {summary_zh}")
        lines.append("")

        if metadata:
            if not isinstance(metadata, Mapping):
                to_dict = getattr(metadata, "to_dict", None)
                metadata = to_dict() if callable(to_dict) else vars(metadata)
            lines.append("## 詮釋資料 (Metadata)")
            lines.append("")
            metadata_values = {
                "分析工具 (Tool)": metadata.get("tool", metadata.get("tool_name", "-")),
                "輸入檔名 (Input name)": metadata.get("input_name", "-"),
                "輸入 SHA-256 雜湊 (Input SHA-256)": metadata.get(
                    "input_sha256", metadata.get("input_hash", metadata.get("capture_sha256", "-"))
                ),
                "輸入格式 (Input format)": metadata.get(
                    "input_format", metadata.get("input_mode", "-")
                ),
                "SMBus 逾時門檻 (SMBus timeout ms)": metadata.get(
                    "smbus_timeout_ms", metadata.get("timeout_ms", metadata.get("timeout", "-"))
                ),
                "板級設定檔 (Board profile)": metadata.get(
                    "board_profile",
                    metadata.get("profile", metadata.get("board_profile_name", "-")),
                ),
                "時序證據樣本數 (Evidence sample count)": metadata.get(
                    "evidence_sample_count",
                    metadata.get(
                        "evidence_samples",
                        metadata.get("sample_count", report.timing_stats.frequency_sample_count),
                    ),
                ),
            }
            for label, value in metadata_values.items():
                lines.append(f"- **{label}**: `{value}`")
            lines.append("")

        # Summary Card
        lines.append("## 1. 匯流排時序與交易健康啟發評等 (Bus Timing & Health)")
        lines.append("")
        lines.append("> 本健康度摘要為協定層證據之啟發式統計，非實體電氣特性或晶片良率之通過判定。")
        lines.append("")
        t = report.timing_stats
        lines.append(
            f"- **標準速度模式 (Nominal Speed Mode)**: `{localize_speed_mode(t.speed_mode)}`"
        )
        if t.frequency_sample_count:
            lines.append(
                f"- **Average Clock Frequency**: `{t.avg_frequency_khz:.2f} kHz` (Min: `{t.min_frequency_khz:.1f} kHz`, Max: `{t.max_frequency_khz:.1f} kHz`)"
            )
            lines.append(
                f"- **時鐘頻率抖動 (Clock Frequency Jitter)**: `{t.frequency_jitter_pct:.1f} %`"
            )
            lines.append(
                f"- **頻率分佈跨度 (Frequency Spread p-p)**: `{t.frequency_spread_pct:.1f} %`"
            )
        else:
            lines.append(
                "- **平均 SCL 時鐘頻率 (Average Clock Frequency)**: `不可用 (Unavailable)` (來源無每位元組時序或位元率證據)"
            )
            lines.append("- **時鐘頻率抖動 (Clock Frequency Jitter)**: `不可用 (Unavailable)`")
            lines.append("- **頻率分佈跨度 (Frequency Spread p-p)**: `不可用 (Unavailable)`")
        lines.append(
            f"- **時鐘延展事件 (Clock Stretching Events)**: `{t.clock_stretch_count}` 筆 (最大持續時間: `{t.max_clock_stretch_ms:.3f} ms`)"
        )
        lines.append(
            f"- **位元組間平均延遲 (Avg Inter-byte Delay)**: `{t.avg_inter_byte_delay_us:.2f} µs` (最大值: `{t.max_inter_byte_delay_us:.2f} µs`)"
        )
        lines.append(
            f"- **交易間平均間隔 (Avg Inter-transaction Delay)**: `{t.avg_inter_transaction_delay_ms:.2f} ms`"
        )
        if t.bus_utilization_evidence != "unavailable":
            lines.append(f"- **匯流排使用率 (Bus Utilization)**: `{t.bus_utilization_pct:.2f} %`")
        else:
            lines.append(
                "- **匯流排使用率 (Bus Utilization)**: `不可用 (Unavailable)` (總捕捉時間不可用)"
            )
        lines.append("")

        # Device Map Table
        lines.append("## 2. 偵測之從裝置分佈表 (Detected Peripheral Device Map)")
        lines.append("")
        lines.append(
            "| 7-bit 位址 | 8-bit 位址 (W/R) | 識別晶片型號 (Device Profile) | 裝置類別 (Category) | 協定 (Protocol) | 交易次數 |"
        )
        lines.append("|---|---|---|---|---|---|")
        for dev in report.devices_detected.values():
            address = dev.get("address_7bit", "unknown")
            device_name = dev.get("name") or f"Unknown Device ({address})"
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "Possible: " + "; ".join(dev.get("candidates", []))
            lines.append(
                f"| `{address}` | `{dev.get('address_8bit', 'unknown')}` | **{device_name}** | {localize_category(dev.get('category'))} | {dev.get('protocol') or 'I2C'} | {dev.get('transaction_count', 0)} |"
            )
        lines.append("")

        # Transaction Sequence Table
        lines.append("## 3. 封包交易序列與解碼明細 (Transaction Sequence & Decoded Telemetry)")
        lines.append("")
        lines.append(
            "| # | 時間 Time (s) | 位址 Addr | 方向 R/W | 原始資料 (Raw Hex) | 協定語意與遙測解碼 (Decoded Telemetry) | 狀態 (Status) |"
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

            addr_text = f"0x{tx.address_7bit:02X}" if tx.address_available else "n/a"
            direction_text = (
                tx.direction.value
                if tx.direction_available and isinstance(tx.direction, I2CDirection)
                else "UNKNOWN"
            )

            lines.append(
                f"| {tx.id} | {tx.start_time:.6f} | `{addr_text}` | `{direction_text}` | `{tx.hex_dump}` | {summary} | {status} |"
                if tx.timestamp_available
                else f"| {tx.id} | n/a | `{addr_text}` | `{direction_text}` | `{tx.hex_dump}` | {summary} | {status} |"
            )
        lines.append("")

        if report.data_quality_issues:
            lines.append("## ⚠ 資料證據與品質限制 (Data Quality Limitations)")
            lines.append("")
            for quality_issue in report.data_quality_issues:
                zh_msg = localize_quality_message(quality_issue.code, quality_issue.message)
                lines.append(f"- **{quality_issue.code}** ({quality_issue.count} 筆): {zh_msg}")
            lines.append("")

        # Diagnostic Issues & Advice
        lines.append("## 4. 異常診斷與排查行動建議 (Diagnostic Issues & Debugging Advice)")
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
                    f"### 4.{idx} [{diagnostic_issue.severity.value}] {diagnostic_issue.code}: {diagnostic_issue.title}"
                )
                lines.append("")
                lines.append(f"- **異常分類 (Category)**: `{diagnostic_issue.category}`")
                if diagnostic_issue.address_7bit is not None:
                    lines.append(
                        f"- **從裝置位址 (Device Address)**: `0x{diagnostic_issue.address_7bit:02X}`"
                    )
                lines.append(f"- **現象描述 (Description)**: {diagnostic_issue.description}")
                lines.append("")
                lines.append("**可能原因假設（Hypotheses；不是已證明的根因）**:")
                for rc_line in diagnostic_issue.root_cause_analysis.split("\n"):
                    if rc_line.strip():
                        lines.append(f"- {rc_line.strip()}")
                lines.append("")
                lines.append("**新手排查行動建議 (Actionable Debug Checklist)**:")
                for advice in diagnostic_issue.actionable_advice:
                    lines.append(f"- [ ] {advice}")
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
