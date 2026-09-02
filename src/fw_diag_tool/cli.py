from __future__ import annotations

import hashlib
import importlib
import ipaddress
import json
import platform
import sys
from dataclasses import asdict, replace
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
from fw_diag_tool.em.bridge import EMBridge
from fw_diag_tool.em.builder import EMBuilder
from fw_diag_tool.em.mock_gen import EMMockGenerator
from fw_diag_tool.em.validator import EMValidator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import Severity
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_events
from fw_diag_tool.i2c.raw_capture import analyze_raw_i2c_csv
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.limits import DEFAULT_ANALYSIS_LIMITS, AnalysisLimits
from fw_diag_tool.log.diff import LogDiffEngine
from fw_diag_tool.log.models import LogReport
from fw_diag_tool.log.parser import LogParser
from fw_diag_tool.mctp.diff import MCTPDiffEngine
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.pcie.diff import PCIeDiffEngine
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.reporting.pdf_report import is_fpdf_available, write_pdf_report
from fw_diag_tool.session.comparator import compare_sessions
from fw_diag_tool.spi.diff import SPIDiffEngine
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.diff import UARTDiffEngine
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter
from fw_diag_tool.uart.timing import analyze_uart_timing

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
log_app = typer.Typer(
    name="log",
    help="Linux kernel (dmesg) and BMC (journalctl) log diagnostics and correlation.",
    add_completion=False,
)
em_app = typer.Typer(
    name="em", help="OpenBMC Entity-Manager JSON configuration tools.", add_completion=False
)

app.add_typer(i2c_app)
app.add_typer(pcie_app)
app.add_typer(spi_app)
app.add_typer(uart_app)
app.add_typer(mctp_app)
app.add_typer(reg_app)
app.add_typer(gen_app)
app.add_typer(log_app)
app.add_typer(em_app)

console = Console()
register_extra_commands(app, i2c_app, console)
MAX_CLI_RECORDS = 250_000


def _session_metric(report: dict[str, object], keys: tuple[str, ...], list_key: str) -> int:
    for key in keys:
        value = report.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    values = report.get(list_key)
    return len(values) if isinstance(values, list) else 0


@app.command("compare")
def compare_session_files(
    baseline: Path = typer.Argument(..., help="Path to baseline session JSON"),
    candidate: Path = typer.Argument(..., help="Path to candidate session JSON"),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown comparison report to file"
    ),
    json_out: Path | None = typer.Option(
        None, "--json", "-j", help="Export JSON comparison result to file"
    ),
) -> None:
    """Compare two saved diagnostic sessions."""
    if not baseline.exists() or not candidate.exists():
        console.print(
            "[bold red]錯誤：Baseline 與 Candidate 檔案都必須存在。"
            "（Error: Both files must exist!）[/]"
        )
        raise typer.Exit(code=1)
    try:
        baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
        candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
        result = compare_sessions(baseline_payload, candidate_payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：Session compare 執行失敗（Error: session compare failed）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc

    table = Table(title="Session Before/After 對比摘要（Session Comparison）", show_header=True)
    table.add_column("指標 / 項目（Metric）", style="cyan")
    table.add_column("Baseline（基準）", style="magenta")
    table.add_column("Candidate（待測）", style="yellow")
    table.add_column("差異（Delta / Status）")
    anomaly_delta = result.metric_deltas["anomaly_count"]
    transaction_delta = result.metric_deltas["total_transactions"]
    baseline_report = baseline_payload.get("report", baseline_payload)
    candidate_report = candidate_payload.get("report", candidate_payload)
    if not isinstance(baseline_report, dict):
        baseline_report = {}
    if not isinstance(candidate_report, dict):
        candidate_report = {}
    baseline_anomaly = _session_metric(
        baseline_report, ("anomaly_count", "anomalies_count"), "anomalies"
    )
    candidate_anomaly = _session_metric(
        candidate_report, ("anomaly_count", "anomalies_count"), "anomalies"
    )
    baseline_transactions = _session_metric(
        baseline_report,
        ("total_transactions", "transaction_count", "transactions"),
        "transactions",
    )
    candidate_transactions = _session_metric(
        candidate_report,
        ("total_transactions", "transaction_count", "transactions"),
        "transactions",
    )
    protocol = result.metric_deltas["protocol"]
    table.add_row(
        "異常總數（Anomaly Count）",
        str(baseline_anomaly),
        str(candidate_anomaly),
        f"{anomaly_delta:+d}",
    )
    table.add_row(
        "交易總數（Total Transactions）",
        str(baseline_transactions),
        str(candidate_transactions),
        f"{transaction_delta:+d}",
    )
    table.add_row(
        "協定（Protocol）",
        protocol["baseline"],
        protocol["candidate"],
        "[bold red]變更（Changed）[/]" if protocol["changed"] else "[green]一致（Same）[/]",
    )
    table.add_row("判定（Verdict）", "", "", result.verdict)
    console.print(table)
    console.print(Panel(result.summary, title="[bold cyan]對比結論[/]"))

    if markdown_out:
        md_text = (
            "# Session Comparison\n\n"
            "| Metric | Baseline | Candidate | Delta / Status |\n"
            "|---|---:|---:|---|\n"
            f"| Anomaly Count | {baseline_anomaly} | {candidate_anomaly} | {anomaly_delta:+d} |\n"
            f"| Total Transactions | {baseline_transactions} | {candidate_transactions} | {transaction_delta:+d} |\n"
            f"| Protocol | {protocol['baseline']} | {protocol['candidate']} | {'changed' if protocol['changed'] else 'same'} |\n"
            f"| Verdict | | | {result.verdict} |\n\n{result.summary}\n"
        )
        markdown_out.write_text(md_text, encoding="utf-8")
        console.print(
            f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
        )
    if json_out:
        json_out.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        console.print(f"[green]✔ JSON 結果已匯出（JSON result exported to）: {json_out}[/]")


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
    pdf_out: Path | None = typer.Option(None, "--pdf", help="Export PDF diagnostic report to file"),
    smbus_timeout: float = typer.Option(
        25.0, "--smbus-timeout", help="SMBus clock stretching timeout in ms (default: 25.0)"
    ),
    raw_digital: bool = typer.Option(
        False,
        "--raw-digital",
        help="Parse a raw digital transition CSV with Time/SCL/SDA columns instead of an analyzer table.",
    ),
    text_trace: bool = typer.Option(
        False,
        "--text-trace",
        help="Parse a tokenized text trace (S/Sr/P, W/R, ACK/NACK, 0xNN).",
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
        None,
        "--fail-on",
        help="Exit with code 1 if issues meet threshold (warning|error|critical).",
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
        if raw_digital and text_trace:
            raise ValueError("--raw-digital and --text-trace are mutually exclusive")
        if raw_digital:
            result = analyze_raw_i2c_csv(
                file_path.read_bytes(),
                time_column=time_column,
                scl_column=scl_column,
                sda_column=sda_column,
                limits=limits,
            )
            report = engine.analyze(raw_decode_to_events(result, limits=limits))
        elif text_trace:
            report = engine.analyze_text(file_path.read_text(encoding="utf-8"))
        else:
            report = engine.analyze_csv_file(str(file_path))
            if report.total_transactions == 0 and file_path.suffix.lower() in {".txt", ".log"}:
                raise ValueError(
                    "decoded CSV input produced no transactions; use --text-trace for tokenized text logs"
                )
        I2CReporter.render_terminal(report, console=console)
        if markdown_out or pdf_out:
            input_format = (
                "raw_digital" if raw_digital else ("text_trace" if text_trace else "decoded_csv")
            )
            profile_metadata = "none"
            if profile is not None:
                profile_metadata = (
                    f"{profile.board_name}@{profile.version}; "
                    f"sha256={hashlib.sha256(profile.to_yaml().encode('utf-8')).hexdigest()}"
                )
            md_text = I2CReporter.generate_markdown(
                report,
                metadata={
                    "tool": f"fw-diag-tool {__version__}",
                    "input_name": str(file_path),
                    "input_sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                    "input_format": input_format,
                    "smbus_timeout_ms": smbus_timeout,
                    "board_profile": profile_metadata,
                    "evidence_sample_count": report.timing_stats.frequency_sample_count,
                },
            )
            if markdown_out:
                markdown_out.write_text(md_text, encoding="utf-8")
                console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
            if pdf_out:
                if not is_fpdf_available():
                    console.print(
                        "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                    )
                else:
                    write_pdf_report(
                        md_text,
                        pdf_out,
                        title="I2C / SMBus / PMBus 協定診斷報告",
                        metadata={
                            "tool": f"fw-diag-tool {__version__}",
                            "input_name": str(file_path),
                            "input_format": input_format,
                        },
                    )
                    console.print(
                        f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]"
                    )
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
                console.print(
                    f"[bold red]Error: invalid --fail-on level {fail_on!r}; choose: warning, error, critical[/]"
                )
                raise typer.Exit(code=2)
            if any(issue.severity.value in allowed for issue in report.issues):
                raise typer.Exit(code=1)
    except (OSError, UnicodeError, TypeError, ValueError, SchemaError) as exc:
        label = (
            "raw digital capture" if raw_digital else ("text trace" if text_trace else "I2C trace")
        )
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
    pdf_out: Path | None = typer.Option(None, "--pdf", help="Export PDF diagnostic report to file"),
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
                    "[bold cyan]Linux 核心 dmesg AER 診斷報告（Kernel dmesg AER Diagnostic Report）[/]\n"
                    f"找到 {len(events)} 個 AER 事件（Found {len(events)} AER event(s)）"
                )
            )
            console.print(report_md)
            if markdown_out:
                markdown_out.write_text(report_md, encoding="utf-8")
                console.print(
                    f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
                )
            if pdf_out:
                if not is_fpdf_available():
                    console.print(
                        "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                    )
                else:
                    write_pdf_report(
                        report_md,
                        pdf_out,
                        title="Linux 核心 dmesg AER 診斷報告",
                    )
                    console.print(
                        f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]"
                    )
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
                        "[bold green]PCIe 設定空間已解碼（PCIe Device Config Space Decoded；"
                        f"BDF: {cfg.bdf or 'N/A'}）[/]"
                    )
                )
                table = Table(title="裝置總覽（Device Overview）", show_header=True)
                table.add_column("屬性（Property）", style="cyan")
                table.add_column("數值（Value）", style="yellow")
                table.add_row(
                    "廠商／裝置 ID（Vendor / Device ID）",
                    f"0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}",
                )
                table.add_row(
                    "類別（Class）",
                    f"{PCIeReporter.localize_class_name(cfg.class_name)} "
                    f"(0x{cfg.base_class:02X}{cfg.sub_class:02X}{cfg.prog_if:02X})",
                )
                table.add_row(
                    "標頭類型（Header Type）",
                    PCIeReporter.localize_header_type(cfg.header_type),
                )
                table.add_row(
                    "標準能力（Standard Capabilities）", str(len(cfg.standard_capabilities))
                )
                table.add_row(
                    "延伸能力（Extended Capabilities）", str(len(cfg.extended_capabilities))
                )
                if cfg.link_info:
                    status_color = "red" if cfg.link_info.is_degraded else "green"
                    table.add_row(
                        "連線協商（Link Negotiation）",
                        f"[{status_color}]{cfg.link_info.current_speed_str} x{cfg.link_info.current_width}[/] "
                        f"（最大（Max）: {cfg.link_info.max_speed_str} x{cfg.link_info.max_width}）",
                    )
                if cfg.aer_analysis:
                    table.add_row(
                        "AER 致命／非致命／可修正（AER Fatal / Non-Fatal / Corr）",
                        f"{cfg.aer_analysis.active_uncorr_fatal_count} / {cfg.aer_analysis.active_uncorr_nonfatal_count} / {cfg.aer_analysis.active_corr_count}",
                    )
                console.print(table)
                if cfg.link_info and cfg.link_info.is_degraded:
                    console.print(
                        Panel(
                            f"[bold red]🚨 連線降級原因（Link Degradation）: "
                            f"{PCIeReporter.localize_link_reason(cfg.link_info.degradation_reason)}[/]\n\n"
                            f"根因指引（Root Cause Guide）:\n{cfg.link_info.root_cause_guide}",
                            border_style="red",
                        )
                    )
            if markdown_out:
                markdown_out.write_text("\n\n---\n\n".join(all_mds), encoding="utf-8")
                console.print(
                    f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
                )
            if pdf_out:
                if not is_fpdf_available():
                    console.print(
                        "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                    )
                else:
                    write_pdf_report(
                        "\n\n---\n\n".join(all_mds),
                        pdf_out,
                        title="PCIe 設定空間與 AER 診斷報告",
                    )
                    console.print(
                        f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]"
                    )
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]錯誤：PCIe 輸入無效（Error: PCIe input is invalid）: {exc}[/]")
        raise typer.Exit(code=2) from exc


@pcie_app.command("diff")
def diff_pcie_configs(
    baseline: Path = typer.Argument(..., help="Path to baseline PCIe lspci / hex dump file"),
    candidate: Path = typer.Argument(..., help="Path to candidate PCIe lspci / hex dump file"),
) -> None:
    """Compare baseline vs candidate PCIe configuration spaces and report link, AER & capability diffs."""
    if not baseline.exists() or not candidate.exists():
        console.print(
            "[bold red]錯誤：Baseline 與 Candidate 檔案都必須存在。"
            "（Error: Both files must exist!）[/]"
        )
        raise typer.Exit(code=1)
    try:
        b_content = baseline.read_text(encoding="utf-8")
        c_content = candidate.read_text(encoding="utf-8")
        b_devices = PCIeAnalyzer.parse_multi_lspci_text(b_content)
        b_cfg = (
            b_devices[0]
            if b_devices
            else PCIeAnalyzer.decode_config_space(PCIeAnalyzer.parse_raw_hex(b_content))
        )
        c_devices = PCIeAnalyzer.parse_multi_lspci_text(c_content)
        c_cfg = (
            c_devices[0]
            if c_devices
            else PCIeAnalyzer.decode_config_space(PCIeAnalyzer.parse_raw_hex(c_content))
        )
        diff_res = PCIeDiffEngine.compare(b_cfg, c_cfg)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]錯誤：PCIe diff 執行失敗（Error: PCIe diff failed）: {exc}[/]")
        raise typer.Exit(code=2) from exc

    table = Table(title="PCIe Before/After 對比摘要（PCIe Diff Summary）", show_header=True)
    table.add_column("項目（Field）", style="cyan")
    table.add_column("Baseline（基準）", style="magenta")
    table.add_column("Candidate（待測）", style="yellow")
    table.add_column("狀態 / 差異（Status / Delta）")

    table.add_row(
        "廠商 ID（Vendor ID）",
        f"0x{b_cfg.vendor_id:04X}",
        f"0x{c_cfg.vendor_id:04X}",
        "[bold red]變更（Changed）[/]" if diff_res.vendor_changed else "[green]相同（Same）[/]",
    )
    table.add_row(
        "裝置 ID（Device ID）",
        f"0x{b_cfg.device_id:04X}",
        f"0x{c_cfg.device_id:04X}",
        "[bold red]變更（Changed）[/]" if diff_res.device_changed else "[green]相同（Same）[/]",
    )
    link_status = (
        "[bold red]降級狀態變更（Degradation Changed）[/]"
        if diff_res.link_degradation_changed
        else (
            "[yellow]變更（Changed）[/]"
            if diff_res.baseline_link_summary != diff_res.candidate_link_summary
            else "[green]相同（Same）[/]"
        )
    )
    table.add_row(
        "連線狀態（Link Summary）",
        diff_res.baseline_link_summary,
        diff_res.candidate_link_summary,
        link_status,
    )
    table.add_row(
        "AER 錯誤差異（AER Error Delta）",
        f"修復 {len(diff_res.resolved_aer_errors)} 個",
        f"新增 {len(diff_res.new_aer_errors)} 個",
        f"+{len(diff_res.new_aer_errors)} / -{len(diff_res.resolved_aer_errors)}",
    )
    table.add_row(
        "資料品質問題（Quality Issues）",
        f"修復 {len(diff_res.resolved_quality_issues)} 個",
        f"新增 {len(diff_res.new_quality_issues)} 個",
        f"+{len(diff_res.new_quality_issues)} / -{len(diff_res.resolved_quality_issues)}",
    )
    console.print(table)

    if diff_res.new_aer_errors:
        aer_table = Table(title="新增 AER 錯誤（New AER Errors in Candidate）", show_header=True)
        aer_table.add_column("錯誤名稱（AER Error Name）", style="bold red")
        for err in diff_res.new_aer_errors:
            aer_table.add_row(err)
        console.print(aer_table)

    if diff_res.resolved_aer_errors:
        res_aer_table = Table(title="已修復 AER 錯誤（Resolved AER Errors）", show_header=True)
        res_aer_table.add_column("錯誤名稱（AER Error Name）", style="bold green")
        for err in diff_res.resolved_aer_errors:
            res_aer_table.add_row(err)
        console.print(res_aer_table)

    if diff_res.new_quality_issues:
        q_table = Table(
            title="新增資料品質問題（New Quality Issues in Candidate）", show_header=True
        )
        q_table.add_column("問題描述（Issue Description）", style="bold yellow")
        for issue in diff_res.new_quality_issues:
            q_table.add_row(issue)
        console.print(q_table)

    if diff_res.resolved_quality_issues:
        res_q_table = Table(title="已修復資料品質問題（Resolved Quality Issues）", show_header=True)
        res_q_table.add_column("問題描述（Issue Description）", style="bold green")
        for issue in diff_res.resolved_quality_issues:
            res_q_table.add_row(issue)
        console.print(res_q_table)

    if diff_res.is_identical:
        console.print("[bold green]✔ Baseline 與 Candidate PCIe 配置完全一致。[/]")
    else:
        console.print(Panel(diff_res.summary, title="[bold cyan]對比結論[/]"))


@spi_app.command("analyze")
def analyze_spi_trace(
    file_path: Path = typer.Argument(..., help="Path to Saleae Logic 2 SPI CSV export"),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    pdf_out: Path | None = typer.Option(None, "--pdf", help="Export PDF diagnostic report to file"),
    max_records: int = typer.Option(
        DEFAULT_ANALYSIS_LIMITS.max_records,
        "--max-records",
        help=f"Maximum source rows (1..{MAX_CLI_RECORDS}).",
    ),
) -> None:
    """Analyze SPI / QSPI NOR Flash trace, decode JEDEC opcodes, and detect write/erase hazards."""
    if not file_path.exists():
        console.print(f"[bold red]錯誤：找不到檔案（Error: File {file_path} not found!）[/]")
        raise typer.Exit(code=1)
    try:
        report = SPIDiagnosticEngine(limits=_analysis_limits(max_records)).analyze_csv_file(
            file_path
        )
        SPIReporter.render_terminal(report, console=console)
        if markdown_out:
            markdown_out.write_text(SPIReporter.to_markdown(report), encoding="utf-8")
            console.print(
                f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
            )
        if pdf_out:
            if not is_fpdf_available():
                console.print(
                    "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                )
            else:
                write_pdf_report(
                    SPIReporter.to_markdown(report),
                    pdf_out,
                    title="SPI / QSPI Flash 診斷報告",
                    metadata={
                        "tool": f"fw-diag-tool {__version__}",
                        "input_name": str(file_path),
                    },
                )
                console.print(f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：SPI CSV 或報告匯出無效（Error: SPI CSV or report export is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc


@spi_app.command("diff")
def diff_spi_traces(
    baseline: Path = typer.Argument(..., help="Path to baseline SPI CSV export"),
    candidate: Path = typer.Argument(..., help="Path to candidate SPI CSV export"),
    max_records: int = typer.Option(
        DEFAULT_ANALYSIS_LIMITS.max_records,
        "--max-records",
        help=f"Maximum source rows (1..{MAX_CLI_RECORDS}).",
    ),
) -> None:
    """Compare baseline vs candidate SPI traces and report anomaly & transaction diffs."""
    if not baseline.exists() or not candidate.exists():
        console.print(
            "[bold red]錯誤：Baseline 與 Candidate 檔案都必須存在。"
            "（Error: Both files must exist!）[/]"
        )
        raise typer.Exit(code=1)
    try:
        engine = SPIDiagnosticEngine(limits=_analysis_limits(max_records))
        b_rep = engine.analyze_csv_file(baseline)
        c_rep = engine.analyze_csv_file(candidate)
        diff_res = SPIDiffEngine.compare(b_rep, c_rep)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]錯誤：SPI diff 執行失敗（Error: SPI diff failed）: {exc}[/]")
        raise typer.Exit(code=2) from exc

    table = Table(title="SPI Before/After 對比摘要（SPI Diff Summary）", show_header=True)
    table.add_column("指標 / 項目（Metric）", style="cyan")
    table.add_column("Baseline（基準）", style="magenta")
    table.add_column("Candidate（待測）", style="yellow")
    table.add_column("差異（Delta / Status）")

    tx_delta_str = (
        f"{diff_res.transaction_count_delta:+d}" if diff_res.transaction_count_delta != 0 else "0"
    )
    table.add_row(
        "交易總數（Total Transactions）",
        str(b_rep.summary.total_transactions),
        str(c_rep.summary.total_transactions),
        tx_delta_str,
    )
    table.add_row(
        "異常總數（Anomaly Count）",
        str(b_rep.summary.anomaly_count),
        str(c_rep.summary.anomaly_count),
        f"{c_rep.summary.anomaly_count - b_rep.summary.anomaly_count:+d}",
    )
    table.add_row(
        "識別晶片（Detected Flash Chip）",
        str(b_rep.summary.detected_flash_chip or "N/A"),
        str(c_rep.summary.detected_flash_chip or "N/A"),
        "[bold red]變更（Changed）[/]" if diff_res.chip_changed else "[green]一致（Same）[/]",
    )
    console.print(table)

    if diff_res.new_anomalies:
        anom_table = Table(title="新增異常（New Anomalies in Candidate）", show_header=True)
        anom_table.add_column("異常名稱（Anomaly Title）", style="bold red")
        for anom in diff_res.new_anomalies:
            anom_table.add_row(anom)
        console.print(anom_table)

    if diff_res.resolved_anomalies:
        res_table = Table(title="已修復異常（Resolved Anomalies）", show_header=True)
        res_table.add_column("異常名稱（Anomaly Title）", style="bold green")
        for anom in diff_res.resolved_anomalies:
            res_table.add_row(anom)
        console.print(res_table)

    if diff_res.is_identical:
        console.print("[bold green]✔ Baseline 與 Candidate SPI 報告完全一致。[/]")
    else:
        console.print(Panel(diff_res.summary, title="[bold cyan]對比結論[/]"))


@uart_app.command("analyze")
def analyze_uart_crash(
    file_or_text: str = typer.Argument(
        ..., help="Path to UART crash log file or raw crash dump string"
    ),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    pdf_out: Path | None = typer.Option(None, "--pdf", help="Export PDF diagnostic report to file"),
) -> None:
    """Analyze Linux Kernel Panic or ARM Cortex-M HardFault crash dumps."""
    try:
        content = file_or_text
        if "\n" not in file_or_text and len(file_or_text) < 256:
            p = Path(file_or_text)
            if p.exists():
                content = p.read_text(encoding="utf-8")
        report = UARTCrashParser.parse_log_text(content)
        timing = analyze_uart_timing(report, content)
        UARTReporter.render_terminal(report, console=console, timing=timing)
        if markdown_out:
            markdown_out.write_text(
                UARTReporter.to_markdown(report, timing=timing), encoding="utf-8"
            )
            console.print(
                f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
            )
        if pdf_out:
            if not is_fpdf_available():
                console.print(
                    "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                )
            else:
                write_pdf_report(
                    UARTReporter.to_markdown(report, timing=timing),
                    pdf_out,
                    title="UART 崩潰日誌診斷報告",
                )
                console.print(f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：UART 崩潰日誌或報告匯出無效（Error: UART crash log or report export is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc


@uart_app.command("diff")
def diff_uart_crashes(
    baseline: Path = typer.Argument(..., help="Path to baseline UART crash log"),
    candidate: Path = typer.Argument(..., help="Path to candidate UART crash log"),
) -> None:
    """Compare baseline vs candidate UART crash logs and report crash type, fault address & symbol diffs."""
    if not baseline.exists() or not candidate.exists():
        console.print(
            "[bold red]錯誤：Baseline 與 Candidate 檔案都必須存在。"
            "（Error: Both files must exist!）[/]"
        )
        raise typer.Exit(code=1)
    try:
        b_content = baseline.read_text(encoding="utf-8")
        c_content = candidate.read_text(encoding="utf-8")
        b_rep = UARTCrashParser.parse_log_text(b_content)
        c_rep = UARTCrashParser.parse_log_text(c_content)
        diff_res = UARTDiffEngine.compare(b_rep, c_rep)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]錯誤：UART diff 執行失敗（Error: UART diff failed）: {exc}[/]")
        raise typer.Exit(code=2) from exc

    table = Table(title="UART Crash Before/After 對比摘要（UART Diff Summary）", show_header=True)
    table.add_column("項目（Field）", style="cyan")
    table.add_column("Baseline（基準）", style="magenta")
    table.add_column("Candidate（待測）", style="yellow")
    table.add_column("狀態（Status）")

    table.add_row(
        "崩潰類型（Crash Type）",
        diff_res.baseline_crash_type,
        diff_res.candidate_crash_type,
        "[bold red]變更（Changed）[/]" if diff_res.crash_type_changed else "[green]相同（Same）[/]",
    )
    table.add_row(
        "故障位址（Fault Address）",
        str(diff_res.baseline_fault_address or "N/A"),
        str(diff_res.candidate_fault_address or "N/A"),
        "[bold red]變更（Changed）[/]"
        if diff_res.fault_address_changed
        else "[green]相同（Same）[/]",
    )
    table.add_row(
        "呼叫棧符號差異（Symbol Delta）",
        f"消退 {len(diff_res.resolved_symbols)} 個",
        f"新增 {len(diff_res.new_symbols)} 個",
        f"+{len(diff_res.new_symbols)} / -{len(diff_res.resolved_symbols)}",
    )
    console.print(table)

    if diff_res.new_symbols:
        sym_table = Table(title="新增符號（New Symbols in Candidate Call Trace）", show_header=True)
        sym_table.add_column("符號名稱（Symbol Name）", style="bold red")
        for sym in diff_res.new_symbols:
            sym_table.add_row(sym)
        console.print(sym_table)

    if diff_res.resolved_symbols:
        res_table = Table(title="已消除符號（Resolved / Removed Symbols）", show_header=True)
        res_table.add_column("符號名稱（Symbol Name）", style="bold green")
        for sym in diff_res.resolved_symbols:
            res_table.add_row(sym)
        console.print(res_table)

    if diff_res.is_identical:
        console.print("[bold green]✔ Baseline 與 Candidate UART 崩潰報告完全一致。[/]")
    else:
        console.print(Panel(diff_res.summary, title="[bold cyan]對比結論[/]"))


@mctp_app.command("analyze")
def analyze_mctp(
    file_or_dump: str = typer.Argument(..., help="Path to MCTP / IPMB hex dump file or text line"),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export markdown diagnostic report to file"
    ),
    pdf_out: Path | None = typer.Option(None, "--pdf", help="Export PDF diagnostic report to file"),
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
            console.print(
                f"[green]✔ Markdown 報告已匯出（Markdown report exported to）: {markdown_out}[/]"
            )
        if pdf_out:
            if not is_fpdf_available():
                console.print(
                    "[bold yellow]警告：PDF 匯出需安裝 pdf 額外套件：pip install fw-diag-tool[pdf]（Warning: PDF export requires 'pdf' extra; skipping PDF generation）[/]"
                )
            else:
                write_pdf_report(
                    ServerMgmtReporter.to_markdown(report),
                    pdf_out,
                    title="MCTP / IPMB 伺服器管理協定報告",
                    metadata={
                        "protocol_mode": protocol_mode,
                    },
                )
                console.print(f"[green]✔ PDF 報告已匯出（PDF report exported to）: {pdf_out}[/]")
        if json_out:
            json_out.write_text(
                json.dumps(
                    {
                        "mctp_packets": [p.__dict__ for p in report.mctp_packets],
                        "ipmb_frames": [f.__dict__ for f in report.ipmb_frames],
                        "unparsed_lines": report.unparsed_lines,
                        "source_errors": report.source_errors,
                    },
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
            console.print(f"[green]✔ JSON 報告已匯出（JSON report exported to）: {json_out}[/]")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：MCTP/IPMB 輸入或報告匯出無效（Error: MCTP/IPMB input or report export is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc


@mctp_app.command("diff")
def diff_mctp_reports(
    baseline: Path = typer.Argument(..., help="Path to baseline MCTP / IPMB hex dump file"),
    candidate: Path = typer.Argument(..., help="Path to candidate MCTP / IPMB hex dump file"),
    protocol_mode: str = typer.Option(
        "auto",
        "--protocol",
        "-p",
        help="Protocol demultiplexing mode (auto, mctp, ipmb).",
    ),
) -> None:
    """Compare baseline vs candidate MCTP/IPMB logs and report packet, frame & error diffs."""
    if not baseline.exists() or not candidate.exists():
        console.print(
            "[bold red]錯誤：Baseline 與 Candidate 檔案都必須存在。"
            "（Error: Both files must exist!）[/]"
        )
        raise typer.Exit(code=1)
    try:
        b_content = baseline.read_text(encoding="utf-8")
        c_content = candidate.read_text(encoding="utf-8")
        b_rep = ServerMgmtParser.parse_text_dump(b_content, protocol_mode=protocol_mode)
        c_rep = ServerMgmtParser.parse_text_dump(c_content, protocol_mode=protocol_mode)
        diff_res = MCTPDiffEngine.compare(b_rep, c_rep)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]錯誤：MCTP diff 執行失敗（Error: MCTP diff failed）: {exc}[/]")
        raise typer.Exit(code=2) from exc

    table = Table(title="MCTP / IPMB Before/After 對比摘要（MCTP Diff Summary）", show_header=True)
    table.add_column("項目（Metric）", style="cyan")
    table.add_column("Baseline（基準）", style="magenta")
    table.add_column("Candidate（待測）", style="yellow")
    table.add_column("差異 / 狀態（Delta / Status）")

    table.add_row(
        "協定模式（Protocol Mode）",
        diff_res.baseline_protocol_mode,
        diff_res.candidate_protocol_mode,
        "[bold red]變更（Changed）[/]"
        if diff_res.protocol_mode_changed
        else "[green]相同（Same）[/]",
    )
    msg_delta_str = (
        f"{diff_res.message_count_delta:+d}" if diff_res.message_count_delta != 0 else "0"
    )
    table.add_row(
        "MCTP 訊息數（MCTP Messages）",
        str(len(b_rep.mctp_messages)),
        str(len(c_rep.mctp_messages)),
        msg_delta_str,
    )
    ipmb_delta_str = (
        f"{diff_res.ipmb_frame_count_delta:+d}" if diff_res.ipmb_frame_count_delta != 0 else "0"
    )
    table.add_row(
        "IPMB 訊框數（IPMB Frames）",
        str(len(b_rep.ipmb_frames)),
        str(len(c_rep.ipmb_frames)),
        ipmb_delta_str,
    )
    err_delta_str = f"{diff_res.error_count_delta:+d}" if diff_res.error_count_delta != 0 else "0"
    b_err_count = len(b_rep.errors) if b_rep.errors else len(b_rep.source_errors)
    c_err_count = len(c_rep.errors) if c_rep.errors else len(c_rep.source_errors)
    table.add_row(
        "錯誤總數（Total Errors）",
        str(b_err_count),
        str(c_err_count),
        err_delta_str,
    )
    warn_delta = len(diff_res.new_warnings) - len(diff_res.resolved_warnings)
    warn_delta_str = f"{warn_delta:+d}" if warn_delta != 0 else "0"
    table.add_row(
        "警告總數（Total Warnings）",
        str(len(b_rep.warnings)),
        str(len(c_rep.warnings)),
        warn_delta_str,
    )
    console.print(table)

    if diff_res.new_errors:
        err_table = Table(title="新增錯誤（New Errors in Candidate）", show_header=True)
        err_table.add_column("錯誤內容（Error Message）", style="bold red")
        for err in diff_res.new_errors:
            err_table.add_row(err)
        console.print(err_table)

    if diff_res.resolved_errors:
        res_err_table = Table(title="已修復錯誤（Resolved Errors）", show_header=True)
        res_err_table.add_column("錯誤內容（Error Message）", style="bold green")
        for err in diff_res.resolved_errors:
            res_err_table.add_row(err)
        console.print(res_err_table)

    if diff_res.new_warnings:
        warn_table = Table(title="新增警告（New Warnings in Candidate）", show_header=True)
        warn_table.add_column("警告內容（Warning Message）", style="bold yellow")
        for warn in diff_res.new_warnings:
            warn_table.add_row(warn)
        console.print(warn_table)

    if diff_res.resolved_warnings:
        res_warn_table = Table(title="已修復警告（Resolved Warnings）", show_header=True)
        res_warn_table.add_column("警告內容（Warning Message）", style="bold green")
        for warn in diff_res.resolved_warnings:
            res_warn_table.add_row(warn)
        console.print(res_warn_table)

    if diff_res.is_identical:
        console.print("[bold green]✔ Baseline 與 Candidate MCTP/IPMB 報告完全一致。[/]")
    else:
        console.print(Panel(diff_res.summary, title="[bold cyan]對比結論[/]"))


@reg_app.command("decode")
def decode_register(
    yaml_file: Path = typer.Argument(..., help="Path to register definition YAML file"),
    reg_name_or_offset: str = typer.Argument(..., help="Register name or offset (e.g. CTRL, 0x10)"),
    raw_value: str = typer.Argument(..., help="Hex raw register value (e.g. 0x00040000)"),
) -> None:
    """Decode a hardware register value based on YAML bitfield definitions."""
    if not yaml_file.exists():
        console.print(
            f"[bold red]錯誤：找不到 YAML 檔案（Error: YAML file {yaml_file} not found!）[/]"
        )
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
        console.print(
            f"[bold red]錯誤：Register YAML 無效（Error: Register YAML is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc
    try:
        val = int(raw_value, 0)
    except ValueError:
        console.print(
            f"[bold red]錯誤：原始值無效（Error: Invalid raw value '{raw_value}'；"
            "must be integer or hex format like 0x10）[/]"
        )
        raise typer.Exit(code=1)
    try:
        result = catalog.decode_register(reg_name_or_offset, val)
    except (TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：無法解碼暫存器值（Error: Cannot decode register value）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc
    table = Table(
        title=f"暫存器解碼（Register Decode: {result.reg_name} ({result.hex_val})）",
        show_header=True,
    )
    table.add_column("位元（Bits）", style="cyan", width=10)
    table.add_column("欄位名稱（Field Name）", style="bold green", width=20)
    table.add_column("數值（Value）", style="yellow", width=12)
    table.add_column("存取權限（Access）", style="cyan", width=18)
    table.add_column("意義／狀態（Meaning / Status）", style="magenta")
    for f in result.fields:
        meaning_str = f.meaning
        if f.is_warning:
            meaning_str = f"[bold red]⚠ {meaning_str}[/]"
        table.add_row(f.bit_range, f.name, f.hex_val, f.access, meaning_str)
    console.print(table)
    console.print(f"未對應位元：Unmapped bits: 0x{result.unmapped_bits:08X}")


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
        console.print(
            f"[bold red]錯誤：找不到 YAML 檔案（Error: YAML file {yaml_file} not found!）[/]"
        )
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
        console.print(
            f"[bold red]錯誤：C 標頭檔輸入無效（Error: C header input is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc
    if output_header:
        try:
            output_header.write_text(header_text, encoding="utf-8")
        except OSError as exc:
            console.print(
                f"[bold red]錯誤：無法寫入 C 標頭檔（Error: cannot write C header）: {exc}[/]"
            )
            raise typer.Exit(code=2) from exc
        console.print(
            f"[green]✔ C 標頭檔已產生並儲存（C Header generated and saved to）: {output_header}[/]"
        )
    else:
        console.print(
            Panel(
                header_text,
                title=f"產生的 C 標頭檔（Generated C Header: {module_name}.h）",
            )
        )


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
            f"[bold red]錯誤：MUX 位址無效（Error: Invalid MUX address '{mux_addr}'；"
            "must be hex like 0x70）[/]"
        )
        raise typer.Exit(code=1)
    try:
        dts_text = DeviceTreeGenerator.generate_dts_from_topology(bus_num=bus_num, mux_addr=m_addr)
    except (TypeError, ValueError) as exc:
        console.print(
            f"[bold red]錯誤：Device Tree 輸入無效（Error: Device Tree input is invalid）: {exc}[/]"
        )
        raise typer.Exit(code=2) from exc
    if output_dts:
        try:
            output_dts.write_text(dts_text, encoding="utf-8")
        except OSError as exc:
            console.print(
                f"[bold red]錯誤：無法寫入 Device Tree（Error: cannot write Device Tree）: {exc}[/]"
            )
            raise typer.Exit(code=2) from exc
        console.print(
            f"[green]✔ Device Tree 已產生並儲存（Device Tree generated and saved to）: {output_dts}[/]"
        )
    else:
        console.print(
            Panel(
                dts_text, title="產生的 Device Tree Source（Generated Device Tree Source (.dts)）"
            )
        )


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
            "[bold red]錯誤：非 loopback GUI 綁定位址需要 --allow-remote。"
            "（Error: non-loopback GUI binds require --allow-remote.）"
            "請使用可信任的反向代理處理驗證與 TLS（Use a trusted reverse proxy for authentication and TLS）。[/]"
        )
        raise typer.Exit(code=2)
    if not is_loopback:
        console.print(
            "[bold yellow]警告：remote 模式沒有內建驗證與 TLS；"
            "（Warning: remote mode has no built-in authentication and TLS;）"
            "請使用可信任的反向代理保護服務（protect it with a trusted reverse proxy）。[/]"
        )

    app_path = Path(__file__).parent / "gui" / "app.py"
    console.print(
        f"[bold green]🚀 正在啟動 Web GUI（Launching Web GUI）: http://{host}:{port}...[/]"
    )
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


@app.command("batch")
def batch_analyze(
    directory: Path = typer.Argument(..., help="Path to directory containing capture or log files"),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-o", help="Directory to save generated reports and batch manifest"
    ),
    format: str = typer.Option(
        "all", "--format", "-f", help="Report format to export (markdown, html, sarif, all)"
    ),
    protocol: str = typer.Option(
        "auto", "--protocol", "-p", help="Protocol filter (i2c, spi, uart, pcie, mctp, auto)"
    ),
) -> None:
    """Batch analyze all trace and dump files in a directory with automatic protocol detection."""
    if not directory.exists() or not directory.is_dir():
        console.print(f"[bold red]錯誤：找不到目錄（Error: Directory {directory} not found!）[/]")
        raise typer.Exit(code=1)

    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    from fw_diag_tool.reporting.batch import batch_analyze_directory

    protocols_arg = None if protocol.lower() == "auto" else [protocol]

    console.print(
        Panel(
            f"[bold cyan]批次韌體診斷分析（Batch Firmware Diagnostic Analysis）[/]\n"
            f"目錄（Directory）: {directory}\n"
            f"協定過濾（Protocol）: {protocol}\n"
            f"匯出格式（Format）: {format}\n"
            f"輸出目錄（Output）: {output_dir or 'None (Terminal only)'}",
            expand=False,
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("正在掃描與分析檔案…", total=None)
        try:
            entries = batch_analyze_directory(
                directory,
                protocols=protocols_arg,
                output_dir=output_dir,
                formats=format,
            )
            progress.update(task, completed=100, total=100, description="分析完成")
        except Exception as exc:
            console.print(f"[bold red]批次分析執行失敗（Batch analysis failed）: {exc}[/]")
            raise typer.Exit(code=2) from exc

    if not entries:
        console.print(
            "[bold yellow]未找到符合條件的檔案進行分析（No matching files found to analyze）。[/]"
        )
        return

    # Render summary table
    table = Table(title="批次分析結果摘要（Batch Analysis Summary）", show_header=True)
    table.add_column("檔案（File）", style="cyan")
    table.add_column("協定（Protocol）", style="magenta")
    table.add_column("狀態（Status）")
    table.add_column("異常數（Findings）", justify="right")
    table.add_column("產出報告（Outputs）", style="dim")

    for entry in entries:
        st = entry.get("status", "unknown")
        if st == "success":
            status_text = "[bold green]✔ 通過（PASS）[/]"
        elif st == "warning":
            status_text = "[bold yellow]⚠ 警告（WARN）[/]"
        else:
            status_text = "[bold red]✖ 異常／失敗（FAIL）[/]"

        out_paths = entry.get("output_paths", [])
        out_summary = f"{len(out_paths)} 個檔案" if out_paths else "-"

        table.add_row(
            entry.get("filename", entry.get("file", "-")),
            entry.get("protocol", "unknown").upper(),
            status_text,
            str(entry.get("findings_count", 0)),
            out_summary,
        )

    console.print(table)

    total_files = len(entries)
    passed_files = sum(1 for e in entries if e.get("status") == "success")
    warn_files = sum(1 for e in entries if e.get("status") == "warning")
    failed_files = sum(1 for e in entries if e.get("status") not in ("success", "warning"))

    console.print(
        f"[bold]總計（Total）: {total_files} | "
        f"[green]通過: {passed_files}[/] | "
        f"[yellow]警告: {warn_files}[/] | "
        f"[red]失敗/異常: {failed_files}[/][/]"
    )
    if output_dir:
        console.print(f"[green]✔ 所有報告與 manifest 已寫入: {output_dir}[/]")


@app.command("report")
def generate_unified_report_cli(
    files: list[Path] = typer.Argument(
        ..., help="One or more trace or log files across protocols to include in the report"
    ),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Report format to export (markdown, html, all)"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file path (e.g. report.md, report.html)"
    ),
) -> None:
    """Generate a unified multi-protocol diagnostic report from multiple files."""
    from fw_diag_tool.reporting.unified_report import (
        analyze_file_for_unified_report,
        build_unified_report,
    )

    if not files:
        console.print("[bold red]錯誤：未指定任何輸入檔案（Error: No files specified!）[/]")
        raise typer.Exit(code=1)

    results = []
    for f in files:
        if not f.exists():
            console.print(f"[bold red]錯誤：找不到檔案（File not found）: {f}[/]")
            raise typer.Exit(code=1)
        res = analyze_file_for_unified_report(f)
        results.append(res)

    report = build_unified_report(results)

    status_style = {
        "success": "[bold green]✔ 正常 (PASS)[/]",
        "warning": "[bold yellow]⚠ 警告 (WARN)[/]",
        "error": "[bold red]✖ 異常 (FAIL)[/]",
    }.get(report.overall_status, report.overall_status)

    console.print(
        Panel(
            f"[bold cyan]韌體診斷統一報告（Unified Multi-Protocol Diagnostic Report）[/]\n"
            f"整體狀態（Overall Status）: {status_style}\n"
            f"整體健康分數（Health Score）: [bold]{report.overall_health_score:.1f} / 100.0[/]\n"
            f"分析檔案數量（Total Files）: {len(files)}",
            expand=False,
        )
    )

    table = Table(title="協定分析概況（Protocol Analysis Summary）", show_header=True)
    table.add_column("檔案（File）", style="cyan")
    table.add_column("協定（Protocol）", style="magenta")
    table.add_column("狀態（Status）")
    table.add_column("項目數（Items）", justify="right")
    table.add_column("異常數（Anomalies）", justify="right")
    table.add_column("摘要（Summary）")

    for f, r in zip(files, report.results):
        r_status = {
            "success": "[green]PASS[/]",
            "warning": "[yellow]WARN[/]",
            "error": "[red]FAIL[/]",
        }.get(r.status, r.status)
        table.add_row(
            f.name,
            r.protocol,
            r_status,
            str(r.total_items),
            str(r.anomaly_count),
            r.summary,
        )

    console.print(table)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        fmt = format.lower()
        if fmt == "html" or output.suffix.lower() == ".html":
            output.write_text(report.to_html(), encoding="utf-8")
            console.print(f"[bold green]✔ HTML 統一報告已成功寫入: {output}[/]")
        elif fmt == "all":
            md_path = output if output.suffix.lower() == ".md" else output.with_suffix(".md")
            html_path = output.with_suffix(".html")
            md_path.write_text(report.to_markdown(), encoding="utf-8")
            html_path.write_text(report.to_html(), encoding="utf-8")
            console.print(f"[bold green]✔ 統一報告已成功寫入: {md_path} 與 {html_path}[/]")
        else:
            output.write_text(report.to_markdown(), encoding="utf-8")
            console.print(f"[bold green]✔ Markdown 統一報告已成功寫入: {output}[/]")
    else:
        fmt = format.lower()
        if fmt == "html":
            console.print(report.to_html())
        elif fmt != "markdown":
            console.print(report.to_markdown())


@app.command()
def info() -> None:
    """顯示 fw-diag-tool 完整系統資訊與功能模組清單。"""
    import platform
    import sys

    console.print(
        Panel(
            f"[bold cyan]fw-diag-tool[/] v{__version__}\n"
            f"Python {sys.version}\n"
            f"Platform: {platform.platform()}\n\n"
            "[bold]支援協定：[/]\n"
            "  • I2C / SMBus / PMBus — CSV decoded 與 raw digital 波形分析\n"
            "  • SPI Flash — JEDEC opcode 序列與異常偵測\n"
            "  • UART — Linux Kernel Panic 與 ARM HardFault 分析\n"
            "  • PCIe — Config Space, Capabilities, AER 診斷\n"
            "  • MCTP / IPMB — 伺服器管理協定封包解析\n"
            "  • Device Tree — Linux .dtsi 模板產生\n\n"
            f"[bold]功能模組數：[/] 20 個 GUI 頁面\n"
            f"[bold]Fault Arena：[/] 30 個實戰故障情境\n"
            f"[bold]GUI 啟動：[/] fw-diag gui",
            title="[bold cyan]系統資訊[/]",
            border_style="cyan",
        )
    )


def _doctor_python_version() -> tuple[tuple[int, int], str]:
    return (sys.version_info[:2], platform.python_version())


def _find_examples_dir() -> Path | None:
    candidates = (
        Path.cwd() / "examples" / "data",
        Path(__file__).resolve().parents[2] / "examples" / "data",
        Path(__file__).resolve().parent / "resources",
    )
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.iterdir()):
            return candidate
    return None


@app.command()
def doctor() -> None:
    """執行 fw-diag-tool 環境健康檢查。"""
    required_packages = (
        ("streamlit", "streamlit"),
        ("plotly", "plotly"),
        ("pandas", "pandas"),
        ("rich", "rich"),
        ("typer", "typer"),
        ("pyyaml", "yaml"),
        ("pydantic", "pydantic"),
    )
    table = Table(title="fw-diag-tool 環境健康檢查", show_header=True)
    table.add_column("檢查項目", style="cyan", width=18)
    table.add_column("目標 / 元件", style="magenta", width=20)
    table.add_column("狀態", width=12)
    table.add_column("詳細資訊", style="dim")

    all_passed = True
    python_info, python_version = _doctor_python_version()
    if python_info >= (3, 10):
        table.add_row(
            "Python 版本",
            ">= 3.10",
            "[bold green]✓ 通過[/]",
            f"目前: {python_version}；平台: {platform.platform()}",
        )
    else:
        table.add_row(
            "Python 版本",
            ">= 3.10",
            "[bold red]✗ 失敗[/]",
            f"目前: {python_version}",
        )
        all_passed = False

    for package_name, import_name in required_packages:
        try:
            module = importlib.import_module(import_name)
            module_version = getattr(module, "__version__", "已安裝")
            table.add_row(
                "核心依賴",
                package_name,
                "[bold green]✓ 通過[/]",
                f"版本: {module_version}",
            )
        except Exception as exc:
            table.add_row("核心依賴", package_name, "[bold red]✗ 失敗[/]", f"載入錯誤: {exc}")
            all_passed = False

    try:
        pdf_module = importlib.import_module("fpdf")
        pdf_version = getattr(pdf_module, "__version__", "已安裝")
        table.add_row("可選依賴", "fpdf2", "[bold green]✓ 通過[/]", f"版本: {pdf_version}")
    except Exception as exc:
        table.add_row("可選依賴", "fpdf2", "[bold yellow]⚠ 警告[/]", f"未安裝（可選）: {exc}")

    examples_dir = _find_examples_dir()
    if examples_dir is None:
        table.add_row("範例資料", "examples/data", "[bold red]✗ 失敗[/]", "找不到可用範例資料")
        all_passed = False
    else:
        sample_count = sum(1 for item in examples_dir.iterdir() if item.is_file())
        table.add_row(
            "範例資料",
            "examples/data",
            "[bold green]✓ 通過[/]",
            f"找到 {sample_count} 個檔案（{examples_dir}）",
        )

    try:
        pytest_module = importlib.import_module("pytest")
        pytest_version = getattr(pytest_module, "__version__", "已安裝")
        table.add_row("測試工具", "pytest", "[bold green]✓ 通過[/]", f"版本: {pytest_version}")
    except Exception as exc:
        table.add_row("測試工具", "pytest", "[bold red]✗ 失敗[/]", f"載入錯誤: {exc}")
        all_passed = False

    if __version__ != "0+unknown":
        table.add_row("版本資訊", "fw-diag-tool", "[bold green]✓ 通過[/]", f"版本: {__version__}")
    else:
        table.add_row(
            "版本資訊", "fw-diag-tool", "[bold yellow]⚠ 警告[/]", "無法取得已安裝套件版本"
        )

    console.print(table)
    if not all_passed:
        raise typer.Exit(code=1)


@app.command()
def check() -> None:
    """檢查 fw-diag-tool 環境與依賴是否正常。"""
    import importlib
    import platform
    import sys

    table = Table(title="fw-diag-tool 環境與依賴健康檢查", show_header=True)
    table.add_column("檢查項目", style="cyan", width=22)
    table.add_column("目標 / 元件", style="magenta", width=28)
    table.add_column("狀態", width=14)
    table.add_column("詳細資訊", style="dim")

    all_passed = True

    # 1. Python 版本 >= 3.10
    py_ver = sys.version.split()[0]
    if sys.version_info >= (3, 10):  # noqa: UP036
        table.add_row(
            "Python 版本",
            f">= 3.10 (目前: {py_ver})",
            "[bold green]✔ 通過[/]",
            f"平台: {platform.platform()}",
        )
    else:
        table.add_row(
            "Python 版本",
            f">= 3.10 (目前: {py_ver})",
            "[bold red]✖ 失敗[/]",
            "Python 版本低於 3.10",
        )
        all_passed = False

    # 2. 必要依賴套件
    required_packages = [
        ("streamlit", "streamlit"),
        ("plotly", "plotly"),
        ("pandas", "pandas"),
        ("rich", "rich"),
        ("typer", "typer"),
        ("pyyaml", "yaml"),
        ("pydantic", "pydantic"),
    ]
    for pkg_display, import_name in required_packages:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "已安裝")
            table.add_row("依賴套件", pkg_display, "[bold green]✔ 通過[/]", f"版本: {ver}")
        except Exception as exc:
            table.add_row("依賴套件", pkg_display, "[bold red]✖ 失敗[/]", f"載入錯誤: {exc}")
            all_passed = False

    # 3. examples/data/ 目錄
    candidates = [
        Path("examples/data"),
        Path(__file__).resolve().parents[2] / "examples" / "data",
        Path(__file__).resolve().parent / "examples" / "data",
    ]
    found_dir = None
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            found_dir = cand
            break
    if found_dir:
        sample_count = len(list(found_dir.glob("*")))
        table.add_row(
            "範例資料目錄",
            "examples/data/",
            "[bold green]✔ 通過[/]",
            f"找到 {sample_count} 個範例檔案 ({found_dir})",
        )
    else:
        table.add_row(
            "範例資料目錄", "examples/data/", "[bold red]✖ 失敗[/]", "找不到 examples/data/ 目錄"
        )
        all_passed = False

    # 4. 核心 Parser 模組載入
    parser_modules = [
        ("I2C / PMBus Parser", "fw_diag_tool.i2c.engine"),
        ("PCIe AER Parser", "fw_diag_tool.pcie.parser"),
        ("SPI Flash Parser", "fw_diag_tool.spi.engine"),
        ("UART Crash Parser", "fw_diag_tool.uart.parser"),
        ("MCTP / IPMB Parser", "fw_diag_tool.mctp.parser"),
        ("Register Mapper", "fw_diag_tool.analyzers.register_mapper"),
        ("CodeGen Engine", "fw_diag_tool.codegen.dts_gen"),
    ]
    for parser_name, mod_path in parser_modules:
        try:
            importlib.import_module(mod_path)
            table.add_row("核心 Parser", parser_name, "[bold green]✔ 通過[/]", f"模組: {mod_path}")
        except Exception as exc:
            table.add_row("核心 Parser", parser_name, "[bold red]✖ 失敗[/]", f"載入失敗: {exc}")
            all_passed = False

    console.print(table)
    if all_passed:
        console.print(
            Panel("[bold green]✔ 所有環境與依賴檢查均正常運作！[/]", border_style="green")
        )
    else:
        console.print(
            Panel("[bold red]✖ 部分環境或依賴檢查未通過，請檢查上述錯誤。[/]", border_style="red")
        )
        raise typer.Exit(code=1)


def _generate_log_markdown(report: LogReport, file_path: Path) -> str:
    lines = [
        "# System Log Diagnostic Report",
        "",
        f"- **File**: `{file_path}`",
        f"- **Source Type**: `{report.source_type.value}`",
        f"- **Total Lines**: {report.summary.total_lines}",
        f"- **Detected Events**: {report.summary.total_events}",
        f"- **Correlated Incidents**: {report.summary.total_incidents}",
    ]
    if report.summary.time_span_seconds is not None:
        lines.append(f"- **Time Span**: {report.summary.time_span_seconds:.3f} s")
    else:
        lines.append("- **Time Span**: N/A")

    lines.extend(["", "## Summary Breakdown", ""])
    if report.summary.subsystem_counts:
        lines.append("### Subsystems")
        for sub, count in report.summary.subsystem_counts.items():
            lines.append(f"- **{sub}**: {count}")
        lines.append("")

    if report.summary.severity_counts:
        lines.append("### Severities")
        for sev, count in report.summary.severity_counts.items():
            lines.append(f"- **{sev}**: {count}")
        lines.append("")

    lines.extend(["## Incidents", ""])
    if not report.incidents:
        lines.append("No incidents detected.")
    else:
        for inc in report.incidents:
            lines.append(f"### [{inc.severity.value}] {inc.id}: {inc.title}")
            lines.append(f"- **Subsystem**: {inc.subsystem.value}")
            lines.append(f"- **Events Count**: {len(inc.events)}")
            if inc.root_cause_hypothesis:
                lines.append(f"- **Root Cause Hypothesis**: {inc.root_cause_hypothesis}")
            if inc.board_context:
                lines.append(f"- **Board Context**: {inc.board_context}")
            if inc.recommended_actions:
                lines.append("- **Recommended Actions**:")
                for act in inc.recommended_actions:
                    lines.append(f"  - {act}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


@log_app.command("analyze")
def analyze_log(
    file_path: Path = typer.Argument(..., help="Path to dmesg, journalctl, or mixed log file"),
    board_profile: Path | None = typer.Option(
        None, "--board-profile", "-b", help="Board Profile YAML for topology enrichment"
    ),
    markdown_out: Path | None = typer.Option(
        None, "--md", "-m", help="Export incident report to Markdown file"
    ),
    json_out: Path | None = typer.Option(None, "--json", "-j", help="Export report to JSON file"),
    fail_on: str | None = typer.Option(
        None,
        "--fail-on",
        help="Exit with non-zero code if issues at or above severity are found (error|critical)",
    ),
) -> None:
    """Analyze Linux kernel (dmesg) and BMC (journalctl) logs for faults and correlate incidents."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)

    try:
        profile = load_board_profile(board_profile) if board_profile else None
        content = file_path.read_text(encoding="utf-8")
        report = LogParser.parse_log_text(content, board_profile=profile)
    except (OSError, UnicodeError, TypeError, ValueError, SchemaError) as exc:
        console.print(f"[bold red]Error: Log analysis failed: {exc}[/]")
        raise typer.Exit(code=2) from exc

    time_span_str = (
        f"{report.summary.time_span_seconds:.3f} s"
        if report.summary.time_span_seconds is not None
        else "N/A"
    )
    panel_text = (
        f"[bold cyan]Source Type:[/] {report.source_type.value}\n"
        f"[bold]Total Lines:[/] {report.summary.total_lines} | "
        f"[bold]Detected Events:[/] {report.summary.total_events} | "
        f"[bold]Incidents:[/] {report.summary.total_incidents}\n"
        f"[bold]Time Span:[/] {time_span_str}"
    )
    console.print(Panel(panel_text, title="[bold cyan]System Log Diagnostic Summary[/]"))

    if report.incidents:
        table = Table(title="Correlated Diagnostic Incidents", show_header=True)
        table.add_column("ID", style="bold cyan")
        table.add_column("Severity")
        table.add_column("Subsystem", style="magenta")
        table.add_column("Title")
        table.add_column("Events Count", justify="right")
        table.add_column("Triage Hint", style="dim")

        for inc in report.incidents:
            sev_style = {
                Severity.CRITICAL: "[bold red]CRITICAL[/]",
                Severity.ERROR: "[red]ERROR[/]",
                Severity.WARNING: "[yellow]WARNING[/]",
                Severity.INFO: "[blue]INFO[/]",
            }.get(
                inc.severity,
                str(inc.severity.value if hasattr(inc.severity, "value") else inc.severity),
            )
            triage_hint = inc.recommended_actions[0] if inc.recommended_actions else "-"
            table.add_row(
                inc.id,
                sev_style,
                inc.subsystem.value,
                inc.title,
                str(len(inc.events)),
                triage_hint,
            )
        console.print(table)

        board_contexts = [inc for inc in report.incidents if inc.board_context]
        if board_contexts:
            bc_table = Table(title="Board Profile Topology Context", show_header=True)
            bc_table.add_column("Incident ID", style="bold cyan")
            bc_table.add_column("Topology Enrichment Details", style="green")
            for inc in board_contexts:
                bc_table.add_row(inc.id, str(inc.board_context))
            console.print(bc_table)
    else:
        console.print("[green]✔ No diagnostic incidents or anomalies detected in log.[/]")

    if markdown_out:
        try:
            md_text = _generate_log_markdown(report, file_path)
            markdown_out.write_text(md_text, encoding="utf-8")
            console.print(f"[green]✔ Markdown report exported to {markdown_out}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write markdown report: {exc}[/]")
            raise typer.Exit(code=2) from exc

    if json_out:
        try:
            json_out.write_text(report.to_json(indent=2) + "\n", encoding="utf-8")
            console.print(f"[green]✔ JSON report exported to {json_out}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write JSON report: {exc}[/]")
            raise typer.Exit(code=2) from exc

    if fail_on:
        thresholds: dict[str, list[Severity]] = {
            "warning": [Severity.WARNING, Severity.ERROR, Severity.CRITICAL],
            "error": [Severity.ERROR, Severity.CRITICAL],
            "critical": [Severity.CRITICAL],
        }
        allowed = thresholds.get(fail_on.lower())
        if not allowed:
            console.print(
                f"[bold red]Error: invalid --fail-on level {fail_on!r}; choose: error, critical[/]"
            )
            raise typer.Exit(code=2)
        if any(inc.severity in allowed for inc in report.incidents):
            raise typer.Exit(code=1)


@log_app.command("diff")
def diff_logs(
    baseline_path: Path = typer.Argument(..., help="Path to baseline log file"),
    candidate_path: Path = typer.Argument(..., help="Path to candidate log file"),
    json_out: Path | None = typer.Option(
        None, "--json", "-j", help="Export diff result to JSON file"
    ),
) -> None:
    """Compare baseline and candidate system logs to identify new and resolved incidents."""
    if not baseline_path.exists():
        console.print(f"[bold red]Error: File {baseline_path} not found![/]")
        raise typer.Exit(code=1)
    if not candidate_path.exists():
        console.print(f"[bold red]Error: File {candidate_path} not found![/]")
        raise typer.Exit(code=1)

    try:
        base_content = baseline_path.read_text(encoding="utf-8")
        cand_content = candidate_path.read_text(encoding="utf-8")
        base_report = LogParser.parse_log_text(base_content)
        cand_report = LogParser.parse_log_text(cand_content)
        diff_result = LogDiffEngine.compare(base_report, cand_report)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        console.print(f"[bold red]Error: Log diff comparison failed: {exc}[/]")
        raise typer.Exit(code=2) from exc

    delta_str = (
        f"+{diff_result.event_count_delta}"
        if diff_result.event_count_delta > 0
        else f"{diff_result.event_count_delta}"
    )
    summary_lines = [
        f"[bold]Summary:[/] {diff_result.summary}",
        (
            f"[bold]Baseline Events:[/] {diff_result.baseline_event_count} | "
            f"[bold]Candidate Events:[/] {diff_result.candidate_event_count} | "
            f"[bold]Delta:[/] {delta_str}"
        ),
    ]
    if diff_result.new_incidents:
        summary_lines.append("\n[bold red]New Incidents:[/]")
        for inc_title in diff_result.new_incidents:
            summary_lines.append(f"  • [red]{inc_title}[/]")
    if diff_result.resolved_incidents:
        summary_lines.append("\n[bold green]Resolved Incidents:[/]")
        for inc_title in diff_result.resolved_incidents:
            summary_lines.append(f"  • [green]{inc_title}[/]")
    if diff_result.common_incidents:
        summary_lines.append("\n[bold blue]Common Incidents:[/]")
        for inc_title in diff_result.common_incidents:
            summary_lines.append(f"  • [blue]{inc_title}[/]")

    console.print(Panel("\n".join(summary_lines), title="[bold cyan]System Log Diff Comparison[/]"))

    if json_out:
        try:
            json_out.write_text(diff_result.to_json(indent=2) + "\n", encoding="utf-8")
            console.print(f"[green]✔ JSON result exported to {json_out}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write JSON result: {exc}[/]")
            raise typer.Exit(code=2) from exc


@em_app.command("validate")
def validate_em(
    file_path: Path = typer.Argument(..., help="Path to Entity-Manager JSON file"),
    board_profile: Path | None = typer.Option(
        None, "--board-profile", "-b", help="Board Profile YAML for cross-reference validation"
    ),
    json_out: Path | None = typer.Option(
        None, "--json", "-j", help="Export validation issues to JSON file"
    ),
) -> None:
    """Validate OpenBMC Entity-Manager JSON configuration syntax, schemas, and topology."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)

    try:
        profile = load_board_profile(board_profile) if board_profile else None
        content = file_path.read_text(encoding="utf-8")
        issues = EMValidator.validate(content, board_profile=profile)
    except (OSError, UnicodeError, TypeError, ValueError, SchemaError) as exc:
        console.print(f"[bold red]Error: Entity-Manager validation failed: {exc}[/]")
        raise typer.Exit(code=2) from exc

    if not issues:
        console.print(
            Panel(
                "[bold green]✔ Entity-Manager configuration is valid (0 issues found).[/]",
                title="[bold green]Entity-Manager Validation[/]",
            )
        )
    else:
        table = Table(
            title=f"Entity-Manager Validation Issues ({len(issues)} found)", show_header=True
        )
        table.add_column("Severity", style="bold")
        table.add_column("Field Path", style="cyan")
        table.add_column("Message")
        table.add_column("Suggestion", style="dim")

        for issue in issues:
            sev_style = {
                Severity.CRITICAL: "[bold red]CRITICAL[/]",
                Severity.ERROR: "[red]ERROR[/]",
                Severity.WARNING: "[yellow]WARNING[/]",
                Severity.INFO: "[blue]INFO[/]",
            }.get(
                issue.severity,
                str(issue.severity.value if hasattr(issue.severity, "value") else issue.severity),
            )
            table.add_row(
                sev_style,
                issue.field_path,
                issue.message,
                issue.suggestion or "-",
            )
        console.print(table)

    if json_out:
        try:
            issues_data = [issue.to_dict() for issue in issues]
            json_out.write_text(
                json.dumps(issues_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            console.print(f"[green]✔ JSON result exported to {json_out}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write JSON result: {exc}[/]")
            raise typer.Exit(code=2) from exc

    # If any ERROR or CRITICAL issues exist, exits with code 1
    if any(issue.severity in (Severity.ERROR, Severity.CRITICAL) for issue in issues):
        raise typer.Exit(code=1)





@em_app.command("generate")
def generate_em_or_dts(
    profile_path: Path = typer.Argument(..., help="Path to Board Profile YAML/JSON file"),
    bus: int | None = typer.Option(
        None, "--bus", "-b", help="Target I2C bus number (generates for all buses if omitted)"
    ),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json (Entity-Manager), dts (Device Tree), or both",
    ),
    output_file: Path | None = typer.Option(
        None, "--out", "-o", help="Write output to file instead of stdout"
    ),
) -> None:
    """Generate OpenBMC Entity-Manager JSON and/or Linux Device Tree (.dts) from a Board Profile."""
    if not profile_path.exists():
        console.print(f"[bold red]Error: File {profile_path} not found![/]")
        raise typer.Exit(code=1)

    fmt = output_format.strip().lower()
    if fmt not in ("json", "dts", "both"):
        console.print(
            f"[bold red]Error: Invalid format '{output_format}'. Must be json, dts, or both.[/]"
        )
        raise typer.Exit(code=2)

    try:
        profile = load_board_profile(profile_path)
    except (OSError, UnicodeError, TypeError, ValueError, SchemaError) as exc:
        console.print(f"[bold red]Error: Failed to load board profile: {exc}[/]")
        raise typer.Exit(code=2) from exc

    results: list[str] = []

    if fmt in ("json", "both"):
        try:
            em_config = EMBridge.from_board_profile(profile, bus_num=bus)
            em_json = EMBuilder.generate(em_config, indent=2)
            results.append(em_json)
        except ValueError as exc:
            console.print(f"[bold red]Error generating Entity-Manager JSON: {exc}[/]", soft_wrap=True)
            raise typer.Exit(code=2) from exc

    if fmt in ("dts", "both"):
        try:
            dts_content = EMBridge.to_dts(profile, bus_num=bus)
            results.append(dts_content)
        except ValueError as exc:
            console.print(f"[bold red]Error generating Device Tree: {exc}[/]")
            raise typer.Exit(code=2) from exc

    output_text = chr(10).join(results)

    if output_file:
        try:
            output_file.write_text(output_text + chr(10), encoding="utf-8")
            console.print(f"[green]Output exported to {output_file}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write output file: {exc}[/]")
            raise typer.Exit(code=2) from exc
    else:
        console.print(
            Panel(output_text, title=f"[bold cyan]Generated Output ({profile.board_name})[/]")
        )


@em_app.command("mock")
def mock_em(
    file_path: Path = typer.Argument(..., help="Path to Entity-Manager JSON configuration file"),
    format_type: str = typer.Option(
        "bash",
        "--format",
        "-f",
        help="Output format: bash launcher or python daemon (default: bash)",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write generated mock script to file instead of stdout"
    ),
) -> None:
    """Generate a runnable Bash or Python D-Bus mock script from an Entity-Manager JSON."""
    if not file_path.exists():
        console.print(f"[bold red]Error: File {file_path} not found![/]")
        raise typer.Exit(code=1)

    fmt_normalized = format_type.strip().lower()
    if fmt_normalized not in ("bash", "sh", "python", "py"):
        console.print(
            f"[bold red]Error: Unsupported format '{format_type}'. Supported: bash, python.[/]"
        )
        raise typer.Exit(code=2)

    try:
        em_content = file_path.read_text(encoding="utf-8")
        config = EMMockGenerator.parse_em_json(em_content)
    except Exception as exc:
        console.print(f"[bold red]Error: Failed to parse Entity-Manager JSON: {exc}[/]")
        raise typer.Exit(code=2) from exc

    if fmt_normalized in ("bash", "sh"):
        script_code = EMMockGenerator.generate_busctl_script(config)
    else:
        script_code = EMMockGenerator.generate_python_mock(config)

    if output:
        try:
            output.write_text(script_code, encoding="utf-8")
            console.print(f"[green]Mock script successfully written to {output}[/]")
        except OSError as exc:
            console.print(f"[bold red]Error: Failed to write output file: {exc}[/]")
            raise typer.Exit(code=2) from exc
    else:
        print(script_code, end="")
def main() -> None:
    app()


if __name__ == "__main__":
    main()
