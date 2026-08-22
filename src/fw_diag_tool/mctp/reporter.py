from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import ServerMgmtReport


class ServerMgmtReporter:
    @staticmethod
    def render_terminal(report: ServerMgmtReport, console: Console | None = None) -> None:
        c = console or Console()
        c.print(Panel(f"[bold cyan]⚡ Server Management Protocol Diagnostic Report[/]\
{report.summary_text}"))

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
                mctp_tbl.add_row(str(idx), f"0x{p.src_eid:02X} -> 0x{p.dest_eid:02X}", p.msg_type_name, flags_str, p.payload_hex, p.pldm_command or "-")
            c.print(mctp_tbl)

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
                ipmb_tbl.add_row(str(idx), f"0x{f.rq_addr:02X} -> 0x{f.rs_addr:02X}", f.netfn_name, f.cmd_name, chk_str)
            c.print(ipmb_tbl)

    @staticmethod
    def to_markdown(report: ServerMgmtReport) -> str:
        lines = ["# Server Management Protocol Diagnostic Report (MCTP / IPMB)\
"]
        lines.append(f"> **Summary**: {report.summary_text}\
")

        if report.mctp_packets:
            lines.append("## 1. MCTP Packets (DSP0236)")
            lines.append("| # | Src EID | Dest EID | Message Type | Flags | Payload | Details |")
            lines.append("|---|---|---|---|---|---|---|")
            for idx, p in enumerate(report.mctp_packets, 1):
                flags_str = f"SOM:{int(p.som)} EOM:{int(p.eom)} Seq:{p.pkt_seq} Tag:{p.msg_tag}"
                lines.append(f"| #{idx} | `0x{p.src_eid:02X}` | `0x{p.dest_eid:02X}` | {p.msg_type_name} | {flags_str} | `{p.payload_hex}` | {p.pldm_command or '-'} |")
            lines.append("")

        if report.ipmb_frames:
            lines.append("## 2. IPMB Frames")
            lines.append("| # | Rq Addr | Rs Addr | NetFn | Command | Data | Status |")
            lines.append("|---|---|---|---|---|---|---|")
            for idx, f in enumerate(report.ipmb_frames, 1):
                data_str = " ".join(f"{b:02X}" for b in f.data) if f.data else "-"
                status_str = "OK" if (f.checksum1_valid and f.checksum2_valid) else "Checksum ERROR"
                lines.append(f"| #{idx} | `0x{f.rq_addr:02X}` | `0x{f.rs_addr:02X}` | {f.netfn_name} | {f.cmd_name} | `{data_str}` | {status_str} |")
            lines.append("")

        return "\
".join(lines)