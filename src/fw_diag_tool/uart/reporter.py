from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import UARTReport


class UARTReporter:
    @staticmethod
    def render_terminal(report: UARTReport, console: Console | None = None) -> None:
        c = console or Console()
        c.print(Panel(f"[bold red]⚡ UART Crash & HardFault Diagnostic Report[/]\
Type: [yellow]{report.crash_type.value}[/]"))

        if report.kernel_panic:
            kp = report.kernel_panic
            sum_tbl = Table(title="Kernel Panic Summary", show_header=True)
            sum_tbl.add_column("Field", style="cyan")
            sum_tbl.add_column("Value", style="bold white")
            sum_tbl.add_row("Architecture", kp.architecture)
            sum_tbl.add_row("Panic Reason", kp.panic_reason)
            if kp.faulting_ip:
                sum_tbl.add_row("Faulting IP / RIP", kp.faulting_ip)
            if kp.faulting_func:
                sum_tbl.add_row("Faulting Function", kp.faulting_func)
            if kp.faulting_address:
                sum_tbl.add_row("Faulting Memory Address", kp.faulting_address)
            if kp.modules_linked:
                sum_tbl.add_row("Modules Linked In", ", ".join(kp.modules_linked))
            c.print(sum_tbl)

            if kp.call_trace:
                trace_tbl = Table(title="Call Trace / Stack Frames", show_header=True)
                trace_tbl.add_column("#", justify="right", style="dim")
                trace_tbl.add_column("Function", style="bold cyan")
                trace_tbl.add_column("Offset", style="yellow")
                trace_tbl.add_column("Module", style="green")
                for frame in kp.call_trace:
                    trace_tbl.add_row(str(frame.index), frame.function_name, frame.offset, frame.module or "[kernel]")
                c.print(trace_tbl)

            c.print(Panel(f"[bold yellow]Root Cause Analysis:[/]\
{kp.root_cause_analysis}\
\
[bold green]Actionable Debug Checklist:[/]\
" + "\
".join(f"- ✔ {chk}" for chk in kp.actionable_checklist), border_style="red"))

        elif report.arm_hardfault:
            hf = report.arm_hardfault
            hf_tbl = Table(title="ARM Cortex-M HardFault Registers", show_header=True)
            hf_tbl.add_column("Register", style="cyan")
            hf_tbl.add_column("Hex Value", style="bold white")
            hf_tbl.add_row("HFSR", f"0x{hf.hfsr_raw:08X}")
            hf_tbl.add_row("CFSR (UFSR/BFSR/MMFSR)", f"0x{hf.cfsr_raw:08X} (U:0x{hf.ufsr_raw:04X} B:0x{hf.bfsr_raw:02X} M:0x{hf.mmfsr_raw:02X})")
            if hf.pc_faulting is not None:
                hf_tbl.add_row("Faulting PC", f"0x{hf.pc_faulting:08X}")
            if hf.lr_exc_return is not None:
                hf_tbl.add_row("LR (EXC_RETURN)", f"0x{hf.lr_exc_return:08X}")
            if hf.bfar_raw is not None:
                hf_tbl.add_row("BFAR", f"0x{hf.bfar_raw:08X}")
            if hf.mmfar_raw is not None:
                hf_tbl.add_row("MMFAR", f"0x{hf.mmfar_raw:08X}")
            c.print(hf_tbl)

            c.print(Panel(f"[bold yellow]Root Cause Analysis:[/]\
{hf.root_cause_analysis}\
\
[bold green]Actionable Checklist:[/]\
" + "\
".join(f"- ✔ {chk}" for chk in hf.actionable_checklist), border_style="red"))

    @staticmethod
    def to_markdown(report: UARTReport) -> str:
        lines = [f"# UART Crash Dump Analysis: {report.crash_type.value}\
"]
        if report.kernel_panic:
            kp = report.kernel_panic
            lines.append("## 1. Crash Summary")
            lines.append(f"- **Architecture**: `{kp.architecture}`")
            lines.append(f"- **Panic Reason**: `{kp.panic_reason}`")
            if kp.faulting_ip:
                lines.append(f"- **Faulting IP**: `{kp.faulting_ip}` ({kp.faulting_func or 'N/A'})")
            if kp.faulting_address:
                lines.append(f"- **Faulting Address**: `{kp.faulting_address}`")
            if kp.modules_linked:
                lines.append(f"- **Modules Linked In**: `{', '.join(kp.modules_linked)}`")
            lines.append("")
            if kp.call_trace:
                lines.append("## 2. Call Trace")
                lines.append("| # | Function | Offset | Module |")
                lines.append("|---|---|---|---|")
                for f in kp.call_trace:
                    lines.append(f"| #{f.index} | `{f.function_name}` | `{f.offset}` | `{f.module or 'kernel'}` |")
                lines.append("")
            lines.append("## 3. Root Cause Analysis & Debug Checklist")
            lines.append(f"```text\
{kp.root_cause_analysis}\
```\
")
            for chk in kp.actionable_checklist:
                lines.append(f"- [ ] {chk}")
        elif report.arm_hardfault:
            hf = report.arm_hardfault
            lines.append("## 1. HardFault Registers")
            lines.append(f"- **HFSR**: `0x{hf.hfsr_raw:08X}`")
            lines.append(f"- **CFSR**: `0x{hf.cfsr_raw:08X}` (UFSR: `0x{hf.ufsr_raw:04X}`, BFSR: `0x{hf.bfsr_raw:02X}`, MMFSR: `0x{hf.mmfsr_raw:02X}`)")
            if hf.pc_faulting is not None:
                lines.append(f"- **Faulting PC**: `0x{hf.pc_faulting:08X}`")
            if hf.bfar_raw is not None:
                lines.append(f"- **BFAR**: `0x{hf.bfar_raw:08X}`")
            if hf.mmfar_raw is not None:
                lines.append(f"- **MMFAR**: `0x{hf.mmfar_raw:08X}`")
            lines.append("")
            lines.append("## 2. Fault Flags & Root Cause")
            for fl in hf.fault_flags:
                lines.append(f"- ⚠️ {fl}")
            lines.append(f"\
```text\
{hf.root_cause_analysis}\
```\
")
            for chk in hf.actionable_checklist:
                lines.append(f"- [ ] {chk}")
        return "\
".join(lines)