from __future__ import annotations

import ipaddress
import json
from dataclasses import replace
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from fw_diag_tool import __version__
from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog
from fw_diag_tool.board_profile import SchemaError, load_board_profile
from fw_diag_tool.cli_extra import register_extra_commands
from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.limits import DEFAULT_ANALYSIS_LIMITS, AnalysisLimits
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter

app = typer.Typer(
    name="fw-diag",
    help="Firmware Diagnostic Suite for I2C/PMBus, PCIe AER, SPI Flash, UART Crash Dump, MCTP, and CodeGen",
    add_completion=False,
)
i2c_app = typer.Typer(name="i2c", help="I2C / SMBus / PMBus Trace & Protocol Diagnostic Tools")
pcie_app = typer.Typer(
    name="pcie", help="PCIe Config Space, Capabilities, AER & TLP Header Diagnostics"
)
spi_app = typer.Typer(name="spi", help="SPI / QSPI Flash Protocol & Sequence Diagnostic Tools")
uart_app = typer.Typer(name="uart", help="UART Serial Crash Dump & ARM HardFault Diagnostic Tools")
mctp_app = typer.Typer(name="mctp", help="MCTP & IPMB Server Management Protocol Tools")
reg_app = typer.Typer(name="reg", help="Hardware & Chip Register Bitfield Decoder")
gen_app = typer.Typer(name="gen", help="Firmware C Header, Device Tree & Driver Code Generator")

app.add_typer(i2c_app)
app.add_typer(pcie_app)
app.add_typer(spi_app)
app.add_typer(uart_app)
app.add_typer(mctp_app)
app.add_typer(reg_app)
app.add_typer(gen_app)

console = Console()
register_extra_commands(app, i2c_app, console)
MAX_CLI_RECORDS = 250_000


def _analysis_limits(max_records: int) -> AnalysisLimits:
    if isinstance(max_records, bool) or not 1 <= max_records <= MAX_CLI_RECORDS:
        raise ValueError(f"--max-records must be between 1 and {MAX_CLI_RECORDS}")
    return replace(
        DEFAULT_ANALYSIS_LIMITS,
        max_records=max_records,
        max_transitions=max_records,
    )


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def root_options(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the fw-diag version and exit.",
    ),
) -> None:
    """Firmware diagnostic suite."""


@i2c_app.command("analyze")
def analyze_i2c_trace(
    file_path: Path = typer.Argument(
        ..., help="Path to Saleae Logic 2 CSV, generic CSV, or text trace log"
    ),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    json_out: Path | None = typer.Option(
        None, "--json", "-j", help="Export JSON structured report to file"
    ),
    smbus_timeout: float = typer.Option(
        25.0, "--smbus-timeout", help="SMBus clock stretching timeout in ms (default: 25.0)"
    ),
    raw_digital: bool = typer.Option(
        False,
        "--raw-digital",
        help="Parse a raw digital transition CSV with Time/SCL/SDA columns instead of an analyzer table.",
    ),
    time_column: str | None = typer.Option(
        None,
        "--time-column",
        help="Explicit raw-capture timestamp column (use with --raw-digital).",
    ),
    scl_column: str | None = typer.Option(
        None, "--scl-column", help="Explicit raw-capture SCL column (use with --raw-digital)."
    ),
    sda_column: str | None = typer.Option(
        None, "--sda-column", help="Explicit raw-capture SDA column (use with --raw-digital)."
    ),
    board_profile: Path | None = typer.Option(
        None, "--board-profile", "-b", help="Path to board profile YAML/JSON file."
    ),
    fail_on: str | None = typer.Option(
        None, "--fail-on", help="Exit with code 1 if issues meet threshold (warning|error|critical)."
    ),
    max_records: int = typer.Option(
        DEFAULT_ANALYSIS_LIMITS.max_records,
        "--max-records",
        help=f"Maximum source rows/transitions (1..{MAX_CLI_RECORDS}).",
    ),
) -> None:
    """Analyze an I2C / SMBus / PMBus trace, decode transactions, check timing, and diagnose faults."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)
    try:
        limits = _analysis_limits(max_records)
        profile = load_board_profile(board_profile) if board_profile else None
        engine = I2CDiagnosticEngine(
            smbus_timeout_ms=smbus_timeout, board_profile=profile, limits=limits
        )
        if raw_digital:
            result = analyze_raw_i2c_csv(
                file_path.read_bytes(),
                time_column=time_column,
                scl_column=scl_column,
                sda_column=sda_column,
                limits=limits,
            )
            report = engine.analyze(raw_decode_to_events(result, limits=limits))
        else:
            report = engine.analyze_csv_file(str(file_path))
        I2CReporter.render_terminal(report, console=console)
        if markdown_out:
            md_text = I2CReporter.generate_markdown(report)
            markdown_out.write_text(md_text, encoding="utf-8")
            console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
        if json_out:
            json_out.write_text(report.to_json(indent=2), encoding="utf-8")
            console.print(f"[green]✔ JSON report exported to {json_out}[/]")
        if fail_on:
            thresholds = {
                "warning": ["WARNING", "ERROR", "CRITICAL"],
                "error": ["ERROR", "CRITICAL"],
                "critical": ["CRITICAL"],
            }
            allowed = thresholds.get(fail_on.lower())
            if not allowed:
                console.print(f"[bold red]Error: invalid --fail-on level {fail_on!r}; choose: warning, error, critical[/]")
                raise typer.Exit(code=2)
            if any(issue.severity.value in allowed for issue in report.issues):
                raise typer.Exit(code=1)
    except (OSError, UnicodeError, TypeError, ValueError, SchemaError) as exc:
        label = "raw digital capture" if raw_digital else "I2C trace"
        console.print(f"[bold red]Error: {label} or report generation failed: {exc}[/]")
        raise typer.Exit(code=2) from exc


@pcie_app.command("analyze")
def analyze_pcie(
    file_or_dump: str = typer.Argument(
        ..., help="Path to lspci text / hex dump file, dmesg log file, or raw hex string"
    ),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
) -> None:
    """Analyze PCIe Config Space, Capability list, AER errors, and decode faulting TLP Headers."""
    try:
        content = file_or_dump
        if "\n" not in file_or_dump and len(file_or_dump) < 256:
            p = Path(file_or_dump)
            if p.exists():
                content = p.read_text(encoding="utf-8")
        if "PCIe Bus Error:" in content or (
            "AER:" in content
            and "lspci" not in content.lower()
            and not any(line.strip().startswith("00:") for line in content.splitlines())
        ):
            events = PCIeAnalyzer.parse_dmesg_aer(content)
            report_md = PCIeReporter.format_dmesg_events(events)
            console.print(
                Panel(
                    f"[bold cyan]Kernel dmesg AER Diagnostic Report[/]\nFound {len(events)} AER event(s)"
                )
            )
            console.print(report_md)
            if markdown_out:
                markdown_out.write_text(report_md, encoding="utf-8")
                console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
        else:
            devices = PCIeAnalyzer.parse_multi_lspci_text(content)
            if not devices:
                bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(content)
                devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
            all_mds = []
            for cfg in devices:
                report_md = PCIeReporter.to_markdown(cfg)
                all_mds.append(report_md)
                console.print(
                    Panel(
                        f"[bold green]PCIe Device Config Space Decoded (BDF: {cfg.bdf or 'N/A'})[/]"
                    )
                )
                table = Table(title="Device Overview", show_header=True)
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="yellow")
                table.add_row(
                    "Vendor / Device ID", f"0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}"
                )
                table.add_row(
                    "Class",
                    f"{cfg.class_name} (0x{cfg.base_class:02X}{cfg.sub_class:02X}{cfg.prog_if:02X})",
                )
                table.add_row("Header Type", f"{cfg.header_type.name}")
                table.add_row("Standard Capabilities", str(len(cfg.standard_capabilities)))
                table.add_row("Extended Capabilities", str(len(cfg.extended_capabilities)))
                if cfg.link_info:
                    status_color = "red" if cfg.link_info.is_degraded else "green"
                    table.add_row(
                        "Link Negotiation",
                        f"[{status_color}]{cfg.link_info.current_speed_str} x{cfg.link_info.current_width}[/] (Max: {cfg.link_info.max_speed_str} x{cfg.link_info.max_width})",
                    )
                if cfg.aer_analysis:
                    table.add_row(
                        "AER Fatal / Non-Fatal / Corr",
                        f"{cfg.aer_analysis.active_uncorr_fatal_count} / {cfg.aer_analysis.active_uncorr_nonfatal_count} / {cfg.aer_analysis.active_corr_count}",
                    )
                console.print(table)
                if cfg.link_info and cfg.link_info.is_degraded:
                    console.print(
                        Panel(
                            f"[bold red]🚨 {cfg.link_info.degradation_reason}[/]\n\n{cfg.link_info.root_cause_guide}",
                            border_style="red",
                        )
                    )
            if markdown_out:
                markdown_out.write_text("\n\n---\n\n".join(all_mds), encoding="utf-8")
                console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: PCIe input is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc


@spi_app.command("analyze")
def analyze_spi_trace(
    file_path: Path = typer.Argument(..., help="Path to Saleae Logic 2 SPI CSV export"),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    max_records: int = typer.Option(
        DEFAULT_ANALYSIS_LIMITS.max_records,
        "--max-records",
        help=f"Maximum source rows (1..{MAX_CLI_RECORDS}).",
    ),
) -> None:
    """Analyze SPI / QSPI NOR Flash trace, decode JEDEC opcodes, and detect write/erase hazards."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)
    try:
        report = SPIDiagnosticEngine(limits=_analysis_limits(max_records)).analyze_csv_file(
            file_path
        )
        SPIReporter.render_terminal(report, console=console)
        if markdown_out:
            markdown_out.write_text(SPIReporter.to_markdown(report), encoding="utf-8")
            console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: SPI CSV or report export is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc


@uart_app.command("analyze")
def analyze_uart_crash(
    file_or_text: str = typer.Argument(
        ..., help="Path to UART crash log file or raw crash dump string"
    ),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
) -> None:
    """Analyze Linux Kernel Panic or ARM Cortex-M HardFault crash dumps."""
    try:
        content = file_or_text
        if "\n" not in file_or_text and len(file_or_text) < 256:
            p = Path(file_or_text)
            if p.exists():
                content = p.read_text(encoding="utf-8")
        report = UARTCrashParser.parse_log_text(content)
        UARTReporter.render_terminal(report, console=console)
        if markdown_out:
            markdown_out.write_text(UARTReporter.to_markdown(report), encoding="utf-8")
            console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: UART crash log or report export is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc


@mctp_app.command("analyze")
def analyze_mctp(
    file_or_dump: str = typer.Argument(..., help="Path to MCTP / IPMB hex dump file or text line"),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    json_out: Path | None = typer.Option(
        None, "--json", "-j", help="Export JSON structured report to file"
    ),
    protocol_mode: str = typer.Option(
        "auto",
        "--protocol",
        "-p",
        help="Protocol demultiplexing mode (auto, mctp, ipmb).",
    ),
) -> None:
    """Decode MCTP (DSP0236/PLDM/SPDM) packets and IPMB server management frames."""
    try:
        content = file_or_dump
        if "\n" not in file_or_dump and len(file_or_dump) < 256:
            p = Path(file_or_dump)
            if p.exists():
                content = p.read_text(encoding="utf-8")
        report = ServerMgmtParser.parse_text_dump(content, protocol_mode=protocol_mode)
        ServerMgmtReporter.render_terminal(report, console=console)
        if markdown_out:
            markdown_out.write_text(ServerMgmtReporter.to_markdown(report), encoding="utf-8")
            console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
        if json_out:
            json_out.write_text(json.dumps({
                "mctp_packets": [p.__dict__ for p in report.mctp_packets],
                "ipmb_frames": [f.__dict__ for f in report.ipmb_frames],
                "unparsed_lines": report.unparsed_lines,
                "source_errors": report.source_errors,
            }, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: MCTP/IPMB input or report export is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc


@reg_app.command("decode")
def decode_register(
    yaml_file: Path = typer.Argument(..., help="Path to register definition YAML file"),
    reg_name_or_offset: str = typer.Argument(..., help="Register name or offset (e.g. CTRL, 0x10)"),
    raw_value: str = typer.Argument(..., help="Hex raw register value (e.g. 0x00040000)"),
) -> None:
    """Decode a hardware register value based on YAML bitfield definitions."""
    if not yaml_file.exists():
        console.print(f"[bold red]Error: YAML file {yaml_file} not found![/]")
        raise typer.Exit(code=1)
    catalog = RegisterMapCatalog()
    try:
        catalog.load_from_yaml(yaml_file.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
        yaml.YAMLError,
    ) as exc:
        console.print(f"[bold red]Error: Register YAML is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc
    try:
        val = int(raw_value, 0)
    except ValueError:
        console.print(
            f"[bold red]Error: Invalid raw value '{raw_value}' (must be integer or hex format like 0x10)![/]"
        )
        raise typer.Exit(code=1)
    try:
        result = catalog.decode_register(reg_name_or_offset, val)
    except (TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: Cannot decode register value: {exc}[/]")
        raise typer.Exit(code=2) from exc
    table = Table(title=f"Register Decode: {result.reg_name} ({result.hex_val})", show_header=True)
    table.add_column("Bits", style="cyan", width=10)
    table.add_column("Field Name", style="bold green", width=20)
    table.add_column("Value", style="yellow", width=12)
    table.add_column("Meaning / Status", style="magenta")
    for f in result.fields:
        meaning_str = f.meaning
        if f.is_warning:
            meaning_str = f"[bold red]⚠ {meaning_str}[/]"
        table.add_row(f.bit_range, f.name, f.hex_val, meaning_str)
    console.print(table)


@gen_app.command("c-header")
def generate_c_header(
    yaml_file: Path = typer.Argument(..., help="Path to register definition YAML file"),
    output_header: Path | None = typer.Option(
        None, "--out", "-o", help="Output C header file path"
    ),
    module_name: str = typer.Option(
        "CHIP_REGS", "--name", "-n", help="C header module name / guard prefix"
    ),
) -> None:
    """Generate MISRA-compliant C header definitions and RMW bitfield macros from YAML."""
    if not yaml_file.exists():
        console.print(f"[bold red]Error: YAML file {yaml_file} not found![/]")
        raise typer.Exit(code=1)
    try:
        gen = CHeaderGenerator.from_yaml_file(yaml_file)
        header_text = gen.generate_header(module_name=module_name)
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
        yaml.YAMLError,
    ) as exc:
        console.print(f"[bold red]Error: C header input is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc
    if output_header:
        try:
            output_header.write_text(header_text, encoding="utf-8")
        except OSError as exc:
            console.print(f"[bold red]Error: cannot write C header: {exc}[/]")
            raise typer.Exit(code=2) from exc
        console.print(f"[green]✔ C Header generated and saved to {output_header}[/]")
    else:
        console.print(Panel(header_text, title=f"Generated C Header: {module_name}.h"))


@gen_app.command("dts")
def generate_dts(
    bus_num: int = typer.Option(1, "--bus", "-b", help="I2C Bus index"),
    mux_addr: str = typer.Option("0x70", "--mux", "-m", help="PCA9548A MUX I2C address"),
    output_dts: Path | None = typer.Option(None, "--out", "-o", help="Output .dts file path"),
) -> None:
    """Generate Linux Kernel & OpenBMC compliant Device Tree Source (.dts) from topology."""
    try:
        m_addr = int(mux_addr, 0)
    except ValueError:
        console.print(
            f"[bold red]Error: Invalid MUX address '{mux_addr}' (must be hex like 0x70)![/]"
        )
        raise typer.Exit(code=1)
    try:
        dts_text = DeviceTreeGenerator.generate_dts_from_topology(bus_num=bus_num, mux_addr=m_addr)
    except (TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: Device Tree input is invalid: {exc}[/]")
        raise typer.Exit(code=2) from exc
    if output_dts:
        try:
            output_dts.write_text(dts_text, encoding="utf-8")
        except OSError as exc:
            console.print(f"[bold red]Error: cannot write Device Tree: {exc}[/]")
            raise typer.Exit(code=2) from exc
        console.print(f"[green]✔ Device Tree generated and saved to {output_dts}[/]")
    else:
        console.print(Panel(dts_text, title="Generated Device Tree Source (.dts)"))


@app.command("gui")
def launch_gui(
    port: int = typer.Option(8501, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Allow a non-loopback bind. The dashboard has no built-in authentication or TLS.",
    ),
) -> None:
    """Launch the interactive Web GUI dashboard."""
    import subprocess
    import sys

    normalized_host = host.strip("[]")
    try:
        is_loopback = ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        is_loopback = normalized_host.lower() == "localhost"
    if not is_loopback and not allow_remote:
        console.print(
            "[bold red]Error: non-loopback GUI binds require --allow-remote. "
            "Use a trusted reverse proxy for authentication and TLS.[/]"
        )
        raise typer.Exit(code=2)
    if not is_loopback:
        console.print(
            "[bold yellow]Warning: remote mode has no built-in authentication and TLS; "
            "protect it with a trusted reverse proxy.[/]"
        )

    app_path = Path(__file__).parent / "gui" / "app.py"
    console.print(f"[bold green]🚀 Launching Web GUI on http://{host}:{port}...[/]")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            f"--server.port={port}",
            f"--server.address={host}",
            "--server.maxUploadSize=20",
            "--server.maxMessageSize=20",
            "--browser.gatherUsageStats=false",
        ],
        check=False,
    )
    if result.returncode:
        raise typer.Exit(code=result.returncode)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
