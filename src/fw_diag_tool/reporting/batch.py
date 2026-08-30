from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fw_diag_tool import __version__
from fw_diag_tool.reporting.html_report import write_html_report
from fw_diag_tool.reporting.pdf_report import is_fpdf_available, write_pdf_report
from fw_diag_tool.reporting.sarif import build_sarif_report


def build_batch_manifest(entries: list[dict[str, Any]]) -> str:
    """Build a batch manifest JSON for CI pipelines.

    Each entry must contain at minimum: file, protocol, and status.
    Optional: findings_count, output_path.
    """
    manifest = {
        "schema_version": "1.0",
        "entries": entries,
        "total": len(entries),
        "passed": sum(1 for e in entries if e.get("status") == "success"),
        "failed": sum(1 for e in entries if e.get("status") not in ("success", "warning")),
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def write_batch_manifest(entries: list[dict[str, Any]], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_batch_manifest(entries), encoding="utf-8")
    return output_path


def _detect_protocol_for_file(file_path: Path) -> str:
    """Detect hardware/firmware protocol based on file suffix and content cues."""
    suffix = file_path.suffix.lower()
    try:
        text_head = file_path.read_text(encoding="utf-8", errors="replace")[:4096]
    except Exception:
        text_head = ""
    normalized_head = text_head.lower()

    if suffix == ".csv":
        first_line = normalized_head.splitlines()[0] if normalized_head.splitlines() else ""
        if any(col in first_line for col in ["scl", "sda", "packet id", "address", "pmbus"]):
            return "i2c"
        if any(col in first_line for col in ["mosi", "miso", "cs", "enable"]):
            return "spi"
        if "time" in first_line:
            return "i2c"
        return "i2c"

    if suffix in {".log", ".txt"}:
        if any(
            kw in normalized_head
            for kw in [
                "kernel panic",
                "oops:",
                "hardfault",
                "hfsr",
                "cfsr",
                "bfsr",
                "ufsr",
                "call trace:",
                "watchdog",
            ]
        ):
            return "uart"
        if any(
            kw in normalized_head
            for kw in [
                "pcie bus error",
                "dmesg aer",
                "correctable error status",
                "uncorrectable error status",
                "lspci",
                "aer:",
                "pcieport",
            ]
        ) or any(re.match(r"^\s*[0-9a-fA-F]{2}:", line) for line in text_head.splitlines()[:10]):
            return "pcie"
        if any(kw in normalized_head for kw in ["dsp0236", "mctp", "ipmb"]):
            return "mctp"
        if re.search(r"\b(s|sr)\s+0x[0-9a-fA-F]{2}\b", normalized_head):
            return "i2c"
        return "uart"

    if suffix == ".hex":
        if any(kw in normalized_head for kw in ["dsp0236", "mctp", "ipmb"]):
            return "mctp"
        return "pcie"

    return "i2c"


def batch_analyze_directory(
    directory: Path | str,
    protocols: list[str] | None = None,
    output_dir: Path | str | None = None,
    formats: list[str] | str | None = None,
) -> list[dict[str, Any]]:
    """Scan a directory for trace/dump files, analyze each with its protocol engine, and collect results."""
    dir_p = Path(directory)
    if not dir_p.exists() or not dir_p.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    allowed_protocols = None
    if protocols:
        cleaned = [p.lower().strip() for p in protocols if p.lower().strip() != "auto"]
        if cleaned:
            allowed_protocols = set(cleaned)

    # Resolve requested output formats
    export_formats: set[str] = set()
    if formats is not None:
        if isinstance(formats, str):
            if formats.lower() == "all":
                export_formats = {"markdown", "html", "sarif"}
            else:
                export_formats = {formats.lower()}
        else:
            for fmt in formats:
                if fmt.lower() == "all":
                    export_formats = {"markdown", "html", "sarif"}
                    break
                export_formats.add(fmt.lower())
    elif output_dir is not None:
        export_formats = {"markdown", "html", "sarif"}

    # Supported file extensions
    valid_suffixes = {".csv", ".log", ".txt", ".hex"}
    files = sorted(
        [f for f in dir_p.iterdir() if f.is_file() and f.suffix.lower() in valid_suffixes]
    )

    from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
    from fw_diag_tool.i2c.reporter import I2CReporter
    from fw_diag_tool.mctp.parser import ServerMgmtParser
    from fw_diag_tool.mctp.reporter import ServerMgmtReporter
    from fw_diag_tool.pcie.parser import PCIeAnalyzer
    from fw_diag_tool.pcie.reporter import PCIeReporter
    from fw_diag_tool.spi.engine import SPIDiagnosticEngine
    from fw_diag_tool.spi.reporter import SPIReporter
    from fw_diag_tool.uart.parser import UARTCrashParser
    from fw_diag_tool.uart.reporter import UARTReporter

    entries: list[dict[str, Any]] = []
    out_p = Path(output_dir) if output_dir else None
    if out_p:
        out_p.mkdir(parents=True, exist_ok=True)

    for file_path in files:
        protocol = _detect_protocol_for_file(file_path)
        if allowed_protocols and protocol not in allowed_protocols:
            continue

        findings: list[dict[str, Any]] = []
        md_text = ""
        status = "success"
        error_msg = None

        try:
            if protocol == "i2c":
                engine = I2CDiagnosticEngine()
                if file_path.suffix.lower() == ".csv":
                    report = engine.analyze_csv_file(str(file_path))
                else:
                    report = engine.analyze_text(
                        file_path.read_text(encoding="utf-8", errors="replace")
                    )
                md_text = I2CReporter.generate_markdown(
                    report,
                    metadata={"tool": f"fw-diag-tool {__version__}", "input_name": file_path.name},
                )
                findings = [
                    {
                        "code": i.code,
                        "title": i.title,
                        "severity": i.severity.value
                        if hasattr(i.severity, "value")
                        else str(i.severity),
                        "message": i.description,
                        "file": str(file_path),
                    }
                    for i in report.issues
                ]
                if any(i.severity.value in ("CRITICAL", "ERROR") for i in report.issues):
                    status = "error"
                elif report.issues or report.data_quality_issues:
                    status = "warning"

            elif protocol == "spi":
                spi_report = SPIDiagnosticEngine().analyze_csv_file(file_path)
                md_text = SPIReporter.to_markdown(spi_report)
                findings = [
                    {
                        "code": i.code,
                        "title": i.title,
                        "severity": i.severity.value
                        if hasattr(i.severity, "value")
                        else str(i.severity),
                        "message": i.description,
                        "file": str(file_path),
                    }
                    for i in spi_report.anomalies
                ]
                if any(
                    getattr(i.severity, "value", str(i.severity)) in ("CRITICAL", "ERROR")
                    for i in spi_report.anomalies
                ):
                    status = "error"
                elif spi_report.anomalies or spi_report.data_quality_issues:
                    status = "warning"

            elif protocol == "uart":
                content = file_path.read_text(encoding="utf-8", errors="replace")
                uart_report = UARTCrashParser.parse_log_text(content)
                md_text = UARTReporter.to_markdown(uart_report)
                if uart_report.kernel_panic:
                    findings.append(
                        {
                            "code": "KERNEL_PANIC",
                            "title": "Linux Kernel Panic",
                            "severity": "CRITICAL",
                            "message": uart_report.kernel_panic.panic_reason,
                            "file": str(file_path),
                        }
                    )
                    status = "error"
                if uart_report.arm_hardfault:
                    for flag in uart_report.arm_hardfault.fault_flags:
                        findings.append(
                            {
                                "code": "ARM_HARDFAULT",
                                "title": "ARM HardFault",
                                "severity": "CRITICAL",
                                "message": flag,
                                "file": str(file_path),
                            }
                        )
                    status = "error"
                if uart_report.crash_type.value == "Hardware Watchdog Timeout Reset":
                    findings.append(
                        {
                            "code": "WATCHDOG_RESET",
                            "title": "Watchdog Reset",
                            "severity": "WARNING",
                            "message": "Watchdog timeout reset detected",
                            "file": str(file_path),
                        }
                    )
                    if status != "error":
                        status = "warning"

            elif protocol == "pcie":
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if "PCIe Bus Error:" in content or (
                    "AER:" in content
                    and "lspci" not in content.lower()
                    and not any(line.strip().startswith("00:") for line in content.splitlines())
                ):
                    events = PCIeAnalyzer.parse_dmesg_aer(content)
                    md_text = PCIeReporter.format_dmesg_events(events)
                    for ev in events:
                        is_fatal = ev.severity.lower() == "fatal"
                        findings.append(
                            {
                                "code": f"AER_{ev.error_name.upper().replace(' ', '_')}",
                                "title": ev.error_name,
                                "severity": "ERROR" if is_fatal else "WARNING",
                                "message": ev.raw_line,
                                "file": str(file_path),
                            }
                        )
                    if any(ev.severity.lower() == "fatal" for ev in events):
                        status = "error"
                    elif events:
                        status = "warning"
                else:
                    devices = PCIeAnalyzer.parse_multi_lspci_text(content)
                    if not devices:
                        bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(content)
                        devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
                    md_text = "\n\n---\n\n".join(PCIeReporter.to_markdown(d) for d in devices)
                    for cfg in devices:
                        if cfg.aer_analysis:
                            for err in cfg.aer_analysis.uncorr_errors:
                                if not err.is_active:
                                    continue
                                findings.append(
                                    {
                                        "code": "AER_UNCORRECTABLE",
                                        "title": err.name,
                                        "severity": "CRITICAL"
                                        if err.severity == "Fatal"
                                        else "ERROR",
                                        "message": err.root_cause_guide or err.name,
                                        "file": str(file_path),
                                    }
                                )
                            for corr_err in cfg.aer_analysis.corr_errors:
                                if not corr_err.is_active:
                                    continue
                                findings.append(
                                    {
                                        "code": "AER_CORRECTABLE",
                                        "title": corr_err.name,
                                        "severity": "WARNING",
                                        "message": corr_err.root_cause_guide or corr_err.name,
                                        "file": str(file_path),
                                    }
                                )
                        if cfg.link_info and cfg.link_info.is_degraded:
                            findings.append(
                                {
                                    "code": "PCIE_LINK_DEGRADED",
                                    "title": "PCIe Link Degraded",
                                    "severity": "WARNING",
                                    "message": f"{cfg.link_info.degradation_reason}",
                                    "file": str(file_path),
                                }
                            )
                    if any(f["severity"] in ("CRITICAL", "ERROR") for f in findings):
                        status = "error"
                    elif findings or any(cfg.data_quality_issues for cfg in devices):
                        status = "warning"

            elif protocol == "mctp":
                content = file_path.read_text(encoding="utf-8", errors="replace")
                mctp_report = ServerMgmtParser.parse_text_dump(content)
                md_text = ServerMgmtReporter.to_markdown(mctp_report)
                findings = [
                    {
                        "code": "SOURCE_ERROR",
                        "title": "Source Error",
                        "severity": "WARNING",
                        "message": err,
                        "file": str(file_path),
                    }
                    for err in mctp_report.source_errors
                ]
                if mctp_report.source_errors:
                    status = "warning"

        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            md_text = f"# 診斷失敗（Analysis Failed）\n\n**錯誤訊息**: {exc}\n"

        entry_output_paths: list[str] = []
        if out_p and md_text:
            stem = file_path.stem
            if "markdown" in export_formats or "md" in export_formats:
                md_file = out_p / f"{stem}_report.md"
                md_file.write_text(md_text, encoding="utf-8")
                entry_output_paths.append(str(md_file))
            if "html" in export_formats:
                html_file = out_p / f"{stem}_report.html"
                write_html_report(
                    md_text,
                    html_file,
                    title=f"韌體診斷報告（{protocol.upper()} Diagnostic Report）: {file_path.name}",
                )
                entry_output_paths.append(str(html_file))
            if "pdf" in export_formats and is_fpdf_available():
                pdf_file = out_p / f"{stem}_report.pdf"
                write_pdf_report(
                    md_text,
                    pdf_file,
                    title=f"韌體診斷報告（{protocol.upper()} Diagnostic Report）: {file_path.name}",
                )
                entry_output_paths.append(str(pdf_file))
            if "sarif" in export_formats:
                sarif_file = out_p / f"{stem}.sarif.json"
                sarif_json = build_sarif_report(
                    tool_name=f"fw-diag-tool ({protocol})",
                    tool_version=__version__,
                    findings=findings,
                )
                sarif_file.write_text(sarif_json, encoding="utf-8")
                entry_output_paths.append(str(sarif_file))

        entry = {
            "file": str(file_path),
            "filename": file_path.name,
            "protocol": protocol,
            "status": status,
            "findings_count": len(findings),
            "findings": findings,
            "output_paths": entry_output_paths,
        }
        if error_msg:
            entry["error"] = error_msg
        entries.append(entry)

    if out_p:
        write_batch_manifest(entries, out_p / "batch_manifest.json")

    return entries


__all__ = [
    "batch_analyze_directory",
    "build_batch_manifest",
    "write_batch_manifest",
]
