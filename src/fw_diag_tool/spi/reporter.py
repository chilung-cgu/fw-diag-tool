from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import SPIReport, SPISeverity


class SPIReporter:
    @staticmethod
    def render_terminal(report: SPIReport, console: Console | None = None) -> None:
        c = console or Console()

        chip_str = report.summary.detected_flash_chip or "Unknown / Generic SPI Flash"
        c.print(Panel(f"[bold cyan]⚡ SPI / QSPI Flash Protocol Diagnostic Report[/]\nIdentified Chip: [yellow]{chip_str}[/]"))

        sum_table = Table(title="Traffic Summary", show_header=True)
        sum_table.add_column("Metric", style="cyan")
        sum_table.add_column("Count", style="yellow")
        sum_table.add_row("Total Transactions", str(report.summary.total_transactions))
        sum_table.add_row("Read Operations", str(report.summary.read_count))
        sum_table.add_row("Page Programs", str(report.summary.write_count))
        sum_table.add_row("Erase Operations", str(report.summary.erase_count))
        sum_table.add_row("Status Polls", str(report.summary.status_poll_count))
        sum_table.add_row("Anomalies Detected", f"[bold red]{report.summary.anomaly_count}[/]" if report.summary.anomaly_count > 0 else "[green]0[/]")
        c.print(sum_table)

        if report.anomalies:
            c.print("\n[bold red]🚨 Detected Flash Protocol Anomalies & Hazards:[/]")
            for a in report.anomalies:
                color = "red" if a.severity in (SPISeverity.CRITICAL, SPISeverity.ERROR) else "yellow"
                c.print(Panel(
                    f"[{color} bold]{a.title}[/]\n\n"
                    f"[bold]Description:[/] {a.description}\n\n"
                    f"[bold]RCA & Debug Guide:[/]\n{a.root_cause_guide}",
                    title=f"[{color}][{a.severity.value}] Anomaly #{a.transaction_id}[/]",
                    border_style=color
                ))
        else:
            c.print("\n[green]✔ No SPI / Flash anomalies detected. All transactions compliant.[/]")

    @staticmethod
    def to_markdown(report: SPIReport) -> str:
        lines: list[str] = []
        chip_str = report.summary.detected_flash_chip or "Unknown / Generic SPI Flash"
        lines.append(f"# SPI / QSPI Flash Diagnostic Report\n")
        lines.append(f"- **Identified Flash Chip**: `{chip_str}`")
        lines.append(f"- **Total Transactions**: `{report.summary.total_transactions}`")
        lines.append(f"- **Read / Program / Erase**: `{report.summary.read_count}` / `{report.summary.write_count}` / `{report.summary.erase_count}`")
        lines.append(f"- **Anomalies Detected**: `{report.summary.anomaly_count}`\n")

        if report.anomalies:
            lines.append("## 🚨 Detected Protocol Anomalies & Root Cause Analysis")
            for idx, a in enumerate(report.anomalies, 1):
                lines.append(f"### #{idx}: [{a.severity.value}] {a.title} @ Time: {a.timestamp:.6f}s")
                lines.append(f"- **Description**: {a.description}")
                lines.append(f"\n```text\n{a.root_cause_guide}\n```\n")

        lines.append("## 📜 SPI Transaction Log (Sample)")
        lines.append("| Index | Time (s) | Opcode | Name | Address | Data Len | Details |")
        lines.append("|---|---|---|---|---|---|---|")
        for tx in report.transactions[:50]:
            addr_str = f"0x{tx.address:06X}" if tx.address is not None else "-"
            detail_str = ", ".join(f"{k}: {v}" for k, v in tx.decoded_details.items()) if tx.decoded_details else "-"
            op_hex = f"0x{tx.opcode:02X}" if tx.opcode is not None else "-"
            lines.append(f"| #{tx.index} | `{tx.start_time:.6f}` | `{op_hex}` | {tx.opcode_name} | `{addr_str}` | {tx.data_payload_len} B | {detail_str} |")

        return "\n".join(lines)
