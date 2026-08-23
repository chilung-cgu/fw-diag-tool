"""I2C / SMBus Diagnostic Report Generator with Rich Terminal UI & Markdown Exporter.

Generates clean, interactive terminal tables and comprehensive Markdown reports
complete with peripheral device maps, decoded transaction telemetry, timing graphs,
and actionable root-cause troubleshooting checklists for junior firmware engineers.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fw_diag_tool.i2c.models import (
    AckType,
    I2CAnalysisReport,
    I2CDirection,
    Severity,
)


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
        else:
            timing_tbl.add_row(
                "Clock Frequency Jitter",
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
            device_name = dev["name"]
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "; ".join(dev.get("candidates", []))
            dev_tbl.add_row(
                dev["address_7bit"],
                dev["address_8bit"],
                device_name,
                dev["category"],
                dev["protocol"],
                str(dev["transaction_count"]),
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

        for tx in report.transactions:
            if tx.direction_available and isinstance(tx.direction, I2CDirection):
                rw_color = "cyan" if tx.direction == I2CDirection.READ else "magenta"
                rw_text = f"[{rw_color}]{tx.direction.value}[/]"
            else:
                rw_text = "[yellow]UNKNOWN[/]"

            status_text = "[green]ACK[/]"
            if tx.address_ack == AckType.NACK:
                status_text = "[red]ADDR NAK[/]"
            elif tx.address_ack == AckType.NONE:
                status_text = "[yellow]ACK UNKNOWN[/]"
            elif tx.has_unexpected_data_nack:
                status_text = "[red]DATA NAK[/]"
            elif tx.has_normal_read_termination_nack:
                status_text = "[blue]READ END NAK[/]"
            elif any(p.ack == AckType.NONE for p in tx.byte_packets if not p.is_address):
                status_text = "[yellow]ACK UNKNOWN[/]"
            elif not tx.has_stop and not tx.is_repeated_start:
                status_text = "[bold red]HANG/NO STOP[/]"

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
    def generate_markdown(cls, report: I2CAnalysisReport) -> str:
        """Generate comprehensive Markdown diagnostic report."""
        lines: list[str] = []
        lines.append("# I2C / SMBus / PMBus Protocol Diagnostic Report")
        lines.append("")
        lines.append(f"> **Summary**: {report.summary_text}")
        lines.append("")

        # Summary Card
        lines.append("## 1. Bus Timing & Physical Health")
        lines.append("")
        t = report.timing_stats
        lines.append(f"- **Nominal Speed Mode**: `{t.speed_mode.value}`")
        if t.frequency_sample_count:
            lines.append(
                f"- **Average Clock Frequency**: `{t.avg_frequency_khz:.2f} kHz` (Min: `{t.min_frequency_khz:.1f} kHz`, Max: `{t.max_frequency_khz:.1f} kHz`)"
            )
            lines.append(f"- **Clock Frequency Jitter**: `{t.frequency_jitter_pct:.1f} %`")
        else:
            lines.append(
                "- **Average Clock Frequency**: `Unavailable` (no bitrate or byte-duration evidence)"
            )
            lines.append("- **Clock Frequency Jitter**: `Unavailable`")
        lines.append(
            f"- **Clock Stretching Events**: `{t.clock_stretch_count}` (Max duration: `{t.max_clock_stretch_ms:.3f} ms`)"
        )
        lines.append(
            f"- **Average Inter-byte Delay**: `{t.avg_inter_byte_delay_us:.2f} µs` (Max: `{t.max_inter_byte_delay_us:.2f} µs`)"
        )
        lines.append(
            f"- **Average Inter-transaction Delay**: `{t.avg_inter_transaction_delay_ms:.2f} ms`"
        )
        if t.bus_utilization_evidence != "unavailable":
            lines.append(f"- **Bus Utilization**: `{t.bus_utilization_pct:.2f} %`")
        else:
            lines.append("- **Bus Utilization**: `Unavailable` (total trace duration is unavailable)")
        lines.append("")

        # Device Map Table
        lines.append("## 2. Detected Peripheral Device Map")
        lines.append("")
        lines.append(
            "| 7-bit Addr | 8-bit (W/R) | Identified Device / Chip Profile | Category | Protocol | Transactions |"
        )
        lines.append("|---|---|---|---|---|---|")
        for dev in report.devices_detected.values():
            device_name = dev["name"]
            if dev.get("identity_confidence") == "ambiguous":
                device_name = "Possible: " + "; ".join(dev.get("candidates", []))
            lines.append(
                f"| `{dev['address_7bit']}` | `{dev['address_8bit']}` | **{device_name}** | {dev['category']} | {dev['protocol']} | {dev['transaction_count']} |"
            )
        lines.append("")

        # Transaction Sequence Table
        lines.append("## 3. Transaction Sequence & Decoded Telemetry")
        lines.append("")
        lines.append(
            "| # | Time (s) | Addr | R/W | Raw Hex Bytes | Decoded Semantic Meaning / Telemetry | Status |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for tx in report.transactions:
            status = "ACK"
            if tx.address_ack == AckType.NACK:
                status = "**ADDR NAK**"
            elif tx.address_ack == AckType.NONE:
                status = "ACK UNKNOWN"
            elif tx.has_unexpected_data_nack:
                status = "**DATA NAK**"
            elif tx.has_normal_read_termination_nack:
                status = "READ END NAK"
            elif any(p.ack == AckType.NONE for p in tx.byte_packets if not p.is_address):
                status = "ACK UNKNOWN"
            elif not tx.has_stop and not tx.is_repeated_start:
                status = "**NO STOP**"

            summary = tx.semantic_summary or "-"
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
            lines.append("## Data Quality Limitations")
            lines.append("")
            for quality_issue in report.data_quality_issues:
                lines.append(
                    f"- **{quality_issue.code}** ({quality_issue.count}): {quality_issue.message}"
                )
            lines.append("")

        # Diagnostic Issues & Advice
        lines.append("## 4. Diagnostic Issues & Junior Debugging Advice")
        lines.append("")
        if not report.issues and report.data_quality_issues:
            lines.append(
                "⚠ **No protocol anomaly was proven, but source evidence is incomplete; review the data-quality section before calling this trace clean.**"
            )
        elif not report.issues:
            lines.append(
                "✔ **All transactions completed cleanly with no protocol or timing violations.**"
            )
        else:
            for idx, diagnostic_issue in enumerate(report.issues, 1):
                lines.append(
                    f"### 4.{idx} [{diagnostic_issue.severity.value}] {diagnostic_issue.code}: {diagnostic_issue.title}"
                )
                lines.append("")
                lines.append(f"- **Category**: `{diagnostic_issue.category}`")
                if diagnostic_issue.address_7bit is not None:
                    lines.append(f"- **Device Address**: `0x{diagnostic_issue.address_7bit:02X}`")
                lines.append(f"- **Description**: {diagnostic_issue.description}")
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
    def to_markdown(cls, report: I2CAnalysisReport) -> str:
        """Backward-compatible report export alias."""
        return cls.generate_markdown(report)
