from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import ServerMgmtReport


class ServerMgmtReporter:
    @staticmethod
    def render_terminal(report: ServerMgmtReport, console: Console | None = None) -> None:
        c = console or Console()
        c.print(
            Panel(
                f"[bold cyan]⚡ Server Management Protocol Diagnostic Report[/]\n{report.summary_text}"
            )
        )

        if report.source_errors:
            errors = Table(title="Input Lines Not Decoded", show_header=True)
            errors.add_column("Source", style="yellow")
            errors.add_column("Reason", style="red")
            for source, reason in zip(report.unparsed_lines, report.source_errors, strict=False):
                errors.add_row(source.strip(), reason)
                c.print(errors)

        if report.ambiguous_lines:
            amb_table = Table(title="Ambiguous Frames (protocol cannot be determined)", show_header=True)
            amb_table.add_column("Source Line", style="red")
            for line in report.ambiguous_lines:
                amb_table.add_row(line)
                c.print(amb_table)

        if report.mctp_packets:
            mctp_tbl = Table(title="MCTP Packets", show_header=True)
            mctp_tbl.add_column("#", justify="right", style="dim")
            mctp_tbl.add_column("Src -> Dest", style="cyan")
            mctp_tbl.add_column("Msg Type", style="bold yellow")
            mctp_tbl.add_column("Flags", style="dim")
            mctp_tbl.add_column("Payload Hex", style="white")
            mctp_tbl.add_column("Details", style="green")
            for idx, p in enumerate(report.mctp_packets, 1):
                flags_str = f"SOM:{int(p.som)} EOM:{int(p.eom)} Seq:{p.pkt_seq} Tag:{p.msg_tag}"
                mctp_tbl.add_row(
                    str(idx),
                    f"0x{p.src_eid:02X} -> 0x{p.dest_eid:02X}",
                    p.msg_type_name,
                    flags_str,
                    p.payload_hex,
                    p.pldm_command or "-",
                )
            c.print(mctp_tbl)

        multi_pkt_msgs = [m for m in report.mctp_messages if m.packets_count > 1 or not m.is_complete]
        if multi_pkt_msgs:
            msg_tbl = Table(title="Reassembled MCTP Messages", show_header=True)
            msg_tbl.add_column("#", justify="right", style="dim")
            msg_tbl.add_column("Type", style="cyan")
            msg_tbl.add_column("Pkts", justify="right", style="yellow")
            msg_tbl.add_column("Bytes", justify="right", style="yellow")
            msg_tbl.add_column("Status", style="bold")
            msg_tbl.add_column("Summary", style="green")
            for idx, msg in enumerate(multi_pkt_msgs, 1):
                status = "[green]Complete[/]" if msg.is_complete else f"[red]{msg.error}[/]"
                msg_tbl.add_row(
                    str(idx),
                    msg.msg_type_name,
                    str(msg.packets_count),
                    str(len(msg.payload)),
                    status,
                    msg.summary,
                )
            c.print(msg_tbl)

        if report.ipmb_frames:
            ipmb_tbl = Table(title="IPMB Frames", show_header=True)
            ipmb_tbl.add_column("#", justify="right", style="dim")
            ipmb_tbl.add_column("Rq -> Rs", style="cyan")
            ipmb_tbl.add_column("NetFn", style="yellow")
            ipmb_tbl.add_column("Command", style="bold white")
            ipmb_tbl.add_column("Checksums", style="dim")
            for idx, f in enumerate(report.ipmb_frames, 1):
                chk1_s = "OK" if f.checksum1_valid else "FAIL"
                chk2_s = "OK" if f.checksum2_valid else "FAIL"
                chk_str = f"CHK1:{chk1_s} CHK2:{chk2_s}"
                ipmb_tbl.add_row(
                    str(idx),
                    f"0x{f.rq_addr:02X} -> 0x{f.rs_addr:02X}",
                    f.netfn_name,
                    f.cmd_name,
                    chk_str,
                )
            c.print(ipmb_tbl)

    @staticmethod
    def to_markdown(report: ServerMgmtReport) -> str:
        lines = ["# Server Management Protocol Diagnostic Report (MCTP / IPMB)\n"]
        lines.append(f"> **Summary**: {report.summary_text}\n")

        if report.source_errors:
            lines.append("## 0. Input Lines Not Decoded")
            lines.append("| Source | Reason |")
            lines.append("|---|---|")
            for source, reason in zip(report.unparsed_lines, report.source_errors, strict=False):
                lines.append(f"| `{source.strip()}` | {reason} |")
            lines.append("")

        if report.mctp_packets:
            lines.append("## 1. MCTP Packets (DSP0236)")
            lines.append("| # | Src EID | Dest EID | Message Type | Flags | Payload | Details |")
            lines.append("|---|---|---|---|---|---|---|")
            for idx, p in enumerate(report.mctp_packets, 1):
                flags_str = f"SOM:{int(p.som)} EOM:{int(p.eom)} Seq:{p.pkt_seq} Tag:{p.msg_tag}"
                lines.append(
                    f"| #{idx} | `0x{p.src_eid:02X}` | `0x{p.dest_eid:02X}` | {p.msg_type_name} | {flags_str} | `{p.payload_hex}` | {p.pldm_command or '-'} |"
                )
            lines.append("")

        multi_pkt_msgs = [m for m in report.mctp_messages if m.packets_count > 1 or not m.is_complete]
        if multi_pkt_msgs:
            lines.append("## 1.1 Reassembled MCTP Messages")
            lines.append("| # | Type | Packets | Bytes | Status | Summary |")
            lines.append("|---|---|---|---|---|---|")
            for idx, msg in enumerate(multi_pkt_msgs, 1):
                status = "Complete" if msg.is_complete else f"Error: {msg.error}"
                lines.append(
                    f"| {idx} | {msg.msg_type_name} | {msg.packets_count} | {len(msg.payload)} | {status} | {msg.summary} |"
                )
            lines.append("")

        if report.ipmb_frames:
            lines.append("## 2. IPMB Frames")
            lines.append("| # | Rq Addr | Rs Addr | NetFn | Command | Data | Status |")
            lines.append("|---|---|---|---|---|---|---|")
            for idx, f in enumerate(report.ipmb_frames, 1):
                data_str = " ".join(f"{b:02X}" for b in f.data) if f.data else "-"
                status_str = "OK" if (f.checksum1_valid and f.checksum2_valid) else "Checksum ERROR"
                lines.append(
                    f"| #{idx} | `0x{f.rq_addr:02X}` | `0x{f.rs_addr:02X}` | {f.netfn_name} | {f.cmd_name} | `{data_str}` | {status_str} |"
                )
            lines.append("")

        return "\n".join(lines)
