from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fw_diag_tool import __version__
from fw_diag_tool.reporting.html_report import build_html_report


@dataclass(frozen=True)
class ProtocolResult:
    """Diagnostic outcome for an individual hardware or firmware protocol."""

    protocol: str  # "I2C", "SPI", "UART", "PCIe", "MCTP"
    summary: str
    anomaly_count: int
    total_items: int  # transactions/commands/lines/devices/packets
    status: str  # "success" / "warning" / "error"
    markdown_report: str  # the full per-protocol report markdown


@dataclass(frozen=True)
class UnifiedReport:
    """Aggregated diagnostic report across multiple hardware/firmware protocols."""

    results: list[ProtocolResult]
    overall_health_score: float  # 0-100
    overall_status: str  # "success" / "warning" / "error"
    generated_at: str
    tool_version: str

    def to_markdown(self) -> str:
        """Render the unified diagnostic report into GitHub-flavored Markdown."""
        lines: list[str] = [
            "# 韌體診斷統一報告",
            "",
            f"- **產出時間 (Generated At)**: {self.generated_at}",
            f"- **工具版本 (Tool Version)**: fw-diag-tool v{self.tool_version}",
            f"- **整體狀態 (Overall Status)**: {self._format_status_badge(self.overall_status)}",
            f"- **整體健康分數 (Overall Health Score)**: **{self.overall_health_score:.1f} / 100.0**",
            "",
            "---",
            "",
            "## 執行摘要 (Executive Summary)",
            "",
        ]

        if not self.results:
            lines.append("未包含任何協定分析結果（No protocol results included）。\n")
        else:
            lines.extend(
                [
                    "| 協定 (Protocol) | 狀態 (Status) | 總項目數 (Total Items) | 異常數 (Anomalies) | 摘要說明 (Summary) |",
                    "|---|---|---|---|---|",
                ]
            )
            for r in self.results:
                status_str = self._format_status_badge(r.status)
                escaped_summary = r.summary.replace("|", "\\|")
                lines.append(
                    f"| **{r.protocol}** | {status_str} | {r.total_items} | {r.anomaly_count} | {escaped_summary} |"
                )
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 跨協定異常摘要 (Cross-Protocol Anomaly Summary)",
                "",
            ]
        )

        total_anomalies = sum(r.anomaly_count for r in self.results)
        affected_protocols = [
            r for r in self.results if r.anomaly_count > 0 or r.status != "success"
        ]

        if total_anomalies == 0 and not affected_protocols:
            lines.append(
                "✔ **無跨協定異常檢出**：所有已分析協定均處於正常狀態，未發現故障或異常指標。\n"
            )
        else:
            lines.extend(
                [
                    f"- **累計異常總數**: {total_anomalies}",
                    f"- **受影響協定數**: {len(affected_protocols)} / {len(self.results)}",
                    "",
                    "| 協定 (Protocol) | 狀態 (Status) | 異常數 (Anomalies) | 重點摘要 (Key Finding) |",
                    "|---|---|---|---|",
                ]
            )
            for r in affected_protocols:
                status_str = self._format_status_badge(r.status)
                escaped_summary = r.summary.replace("|", "\\|")
                lines.append(
                    f"| **{r.protocol}** | {status_str} | {r.anomaly_count} | {escaped_summary} |"
                )
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 簽核檢查清單 (Sign-off Checklist)",
                "",
            ]
        )

        # Sign-off conditions
        has_results = len(self.results) > 0
        no_fatal = self.overall_status != "error"
        anomaly_controlled = total_anomalies == 0
        health_passed = self.overall_health_score >= 80.0

        all_passed = (
            has_results and no_fatal and health_passed and (self.overall_status == "success")
        )

        check_icon = lambda ok: "x" if ok else " "

        lines.extend(
            [
                (
                    f"- [{check_icon(has_results)}] **協定分析完整性 (Protocol Coverage)**: "
                    f"{'PASS (已分析 ' + str(len(self.results)) + ' 項協定)' if has_results else 'FAIL (未包含分析資料)'}"
                ),
                (
                    f"- [{check_icon(no_fatal)}] **無嚴重致命錯誤 (No Critical Errors)**: "
                    f"{'PASS (無 Fatal/Panic 錯誤)' if no_fatal else 'FAIL (檢測到嚴重系統錯誤)'}"
                ),
                (
                    f"- [{check_icon(anomaly_controlled)}] **異常數量受控 (Anomaly Controlled)**: "
                    f"{'PASS (零異常)' if anomaly_controlled else f'FAIL (共 {total_anomalies} 個異常)'}"
                ),
                (
                    f"- [{check_icon(health_passed)}] **健康分數達標 (Health Score >= 80.0)**: "
                    f"{'PASS' if health_passed else 'FAIL'} ({self.overall_health_score:.1f} / 100.0)"
                ),
                "",
                f"**簽核結論 (Sign-off Verdict)**: {'✔ **PASS (核准簽核 / APPROVED)**' if all_passed else '✖ **FAIL (未通過 / REJECTED)**'}",
                "",
                "---",
                "",
                "## 協定詳細報告 (Protocol Detailed Reports)",
                "",
            ]
        )

        if not self.results:
            lines.append("無詳細報告內容。\n")
        else:
            for r in self.results:
                lines.extend(
                    [
                        f"### {r.protocol} 詳細報告",
                        "",
                        r.markdown_report.strip(),
                        "",
                        "---",
                        "",
                    ]
                )

        return "\n".join(lines)

    def to_html(self) -> str:
        """Convert the unified report into self-contained styled HTML."""
        return build_html_report(
            self.to_markdown(),
            title="韌體診斷統一報告 (Unified Firmware Diagnostic Report)",
            tool_version=self.tool_version,
            timestamp=self.generated_at,
        )

    @staticmethod
    def _format_status_badge(status: str) -> str:
        s = status.lower()
        if s == "success":
            return "✔ 正常 (Success)"
        elif s == "warning":
            return "⚠ 警告 (Warning)"
        elif s == "error":
            return "✖ 錯誤 (Error)"
        return status


def _compute_protocol_score(result: ProtocolResult) -> float:
    """Compute individual protocol score between 0.0 and 100.0."""
    if result.total_items > 0:
        rate = min(1.0, result.anomaly_count / result.total_items)
        base = max(0.0, 100.0 - rate * 500.0)
        if result.status == "error":
            return min(base, 40.0) if result.anomaly_count > 0 else 50.0
        elif result.status == "warning":
            return min(base, 80.0) if result.anomaly_count > 0 else 80.0
        return base
    else:
        if result.status == "error":
            return 0.0
        elif result.status == "warning":
            return 70.0
        return 100.0


def build_unified_report(
    results: list[ProtocolResult],
    *,
    generated_at: str | None = None,
    tool_version: str | None = None,
) -> UnifiedReport:
    """Build a UnifiedReport from a list of per-protocol diagnostic results."""
    if not results:
        return UnifiedReport(
            results=[],
            overall_health_score=100.0,
            overall_status="success",
            generated_at=generated_at
            or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            tool_version=tool_version or __version__,
        )

    scores = [_compute_protocol_score(r) for r in results]
    overall_health_score = round(sum(scores) / len(scores), 1)

    if any(r.status == "error" for r in results):
        overall_status = "error"
    elif any(r.status == "warning" for r in results):
        overall_status = "warning"
    else:
        overall_status = "success"

    timestamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    version = tool_version or __version__

    return UnifiedReport(
        results=list(results),
        overall_health_score=overall_health_score,
        overall_status=overall_status,
        generated_at=timestamp,
        tool_version=version,
    )


def detect_file_protocol(file_path: Path | str, content: str = "") -> str:
    """Detect hardware/firmware protocol based on file suffix and content cues."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if not content:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[:4096]
        except Exception:
            content = ""
    normalized = content.lower()

    if suffix == ".csv":
        first_line = normalized.splitlines()[0] if normalized.splitlines() else ""
        if any(col in first_line for col in ["scl", "sda", "packet id", "address", "pmbus"]):
            return "I2C"
        if any(col in first_line for col in ["mosi", "miso", "cs", "enable"]):
            return "SPI"
        if "time" in first_line:
            return "I2C"
        return "I2C"

    if suffix in {".log", ".txt"}:
        if any(
            kw in normalized
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
            return "UART"
        if any(
            kw in normalized
            for kw in [
                "pcie bus error",
                "dmesg aer",
                "correctable error status",
                "uncorrectable error status",
                "lspci",
                "aer:",
                "pcieport",
            ]
        ) or any(re.match(r"^\s*[0-9a-fA-F]{2}:", line) for line in content.splitlines()[:10]):
            return "PCIe"
        if any(kw in normalized for kw in ["dsp0236", "mctp", "ipmb"]):
            return "MCTP"
        if re.search(r"\b(s|sr)\s+0x[0-9a-fA-F]{2}\b", normalized):
            return "I2C"
        return "UART"

    if suffix == ".hex":
        if any(kw in normalized for kw in ["dsp0236", "mctp", "ipmb"]):
            return "MCTP"
        return "PCIe"

    return "I2C"


def analyze_file_for_unified_report(
    file_path: Path | str,
    protocol: str = "auto",
) -> ProtocolResult:
    """Analyze a single trace or log file and return a ProtocolResult."""
    path = Path(file_path)
    if not path.exists():
        return ProtocolResult(
            protocol=protocol.upper() if protocol != "auto" else "UNKNOWN",
            summary=f"檔案不存在: {path}",
            anomaly_count=1,
            total_items=0,
            status="error",
            markdown_report=f"# 錯誤 (Error)\n\n找不到檔案: `{path}`\n",
        )

    resolved_proto = protocol.upper() if protocol != "auto" else detect_file_protocol(path)

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

    try:
        if resolved_proto == "I2C":
            engine = I2CDiagnosticEngine()
            if path.suffix.lower() == ".csv":
                report = engine.analyze_csv_file(str(path))
            else:
                report = engine.analyze_text(path.read_text(encoding="utf-8", errors="replace"))
            md_text = I2CReporter.generate_markdown(
                report,
                metadata={"tool": f"fw-diag-tool {__version__}", "input_name": path.name},
            )
            anomaly_count = len(report.issues)
            total_items = report.total_transactions
            if any(i.severity.value in ("CRITICAL", "ERROR") for i in report.issues):
                status = "error"
            elif report.issues or report.data_quality_issues:
                status = "warning"
            else:
                status = "success"
            summary = f"{total_items} 筆交易，{anomaly_count} 個問題"
            return ProtocolResult(
                protocol="I2C",
                summary=summary,
                anomaly_count=anomaly_count,
                total_items=total_items,
                status=status,
                markdown_report=md_text,
            )

        elif resolved_proto == "SPI":
            spi_report = SPIDiagnosticEngine().analyze_csv_file(path)
            md_text = SPIReporter.to_markdown(spi_report)
            anomaly_count = len(spi_report.anomalies)
            total_items = len(spi_report.transactions)
            if any(
                getattr(i.severity, "value", str(i.severity)) in ("CRITICAL", "ERROR")
                for i in spi_report.anomalies
            ):
                status = "error"
            elif spi_report.anomalies or spi_report.data_quality_issues:
                status = "warning"
            else:
                status = "success"
            summary = f"{total_items} 個指令，{anomaly_count} 個異常"
            return ProtocolResult(
                protocol="SPI",
                summary=summary,
                anomaly_count=anomaly_count,
                total_items=total_items,
                status=status,
                markdown_report=md_text,
            )

        elif resolved_proto == "UART":
            content = path.read_text(encoding="utf-8", errors="replace")
            uart_report = UARTCrashParser.parse_log_text(content)
            md_text = UARTReporter.to_markdown(uart_report)
            anomaly_count = 0
            if uart_report.kernel_panic:
                anomaly_count += 1
            if uart_report.arm_hardfault:
                anomaly_count += len(uart_report.arm_hardfault.fault_flags) or 1
            if uart_report.crash_type.value == "Hardware Watchdog Timeout Reset":
                anomaly_count += 1

            total_items = len(content.splitlines())
            if uart_report.kernel_panic or uart_report.arm_hardfault:
                status = "error"
            elif anomaly_count > 0:
                status = "warning"
            else:
                status = "success"
            summary = f"{uart_report.crash_type.value}，{anomaly_count} 個異常標記"
            return ProtocolResult(
                protocol="UART",
                summary=summary,
                anomaly_count=anomaly_count,
                total_items=total_items,
                status=status,
                markdown_report=md_text,
            )

        elif resolved_proto == "PCIE":
            content = path.read_text(encoding="utf-8", errors="replace")
            if "PCIe Bus Error:" in content or (
                "AER:" in content
                and "lspci" not in content.lower()
                and not any(line.strip().startswith("00:") for line in content.splitlines())
            ):
                events = PCIeAnalyzer.parse_dmesg_aer(content)
                md_text = PCIeReporter.format_dmesg_events(events)
                anomaly_count = len(events)
                total_items = len(events)
                has_fatal = any(ev.severity.lower() == "fatal" for ev in events)
                status = "error" if has_fatal else ("warning" if events else "success")
                summary = f"{len(events)} 筆 AER 事件"
            else:
                devices = PCIeAnalyzer.parse_multi_lspci_text(content)
                if not devices:
                    bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(content)
                    devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
                md_text = "\n\n---\n\n".join(PCIeReporter.to_markdown(d) for d in devices)
                total_items = len(devices)
                uncorr_count = 0
                corr_count = 0
                for d in devices:
                    if d.aer_analysis:
                        uncorr_count += sum(1 for e in d.aer_analysis.uncorr_errors if e.is_active)
                        corr_count += sum(1 for e in d.aer_analysis.corr_errors if e.is_active)
                anomaly_count = uncorr_count + corr_count
                if uncorr_count > 0:
                    status = "error"
                elif corr_count > 0 or any(
                    d.link_info and d.link_info.is_degraded for d in devices
                ):
                    status = "warning"
                else:
                    status = "success"
                summary = f"{total_items} 個裝置，{anomaly_count} 個異常"

            return ProtocolResult(
                protocol="PCIe",
                summary=summary,
                anomaly_count=anomaly_count,
                total_items=total_items,
                status=status,
                markdown_report=md_text,
            )

        elif resolved_proto == "MCTP":
            content = path.read_text(encoding="utf-8", errors="replace")
            mctp_report = ServerMgmtParser.parse_text_dump(content)
            md_text = ServerMgmtReporter.to_markdown(mctp_report)
            anomaly_count = len(mctp_report.source_errors)
            total_items = len(mctp_report.mctp_packets)
            status = "warning" if anomaly_count > 0 else "success"
            summary = f"{total_items} 個封包，{anomaly_count} 個錯誤"
            return ProtocolResult(
                protocol="MCTP",
                summary=summary,
                anomaly_count=anomaly_count,
                total_items=total_items,
                status=status,
                markdown_report=md_text,
            )

        else:
            return ProtocolResult(
                protocol=resolved_proto,
                summary="未支援或未知的協定類型",
                anomaly_count=1,
                total_items=0,
                status="error",
                markdown_report=f"# 錯誤 (Error)\n\n未支援的協定類型: `{resolved_proto}`\n",
            )

    except Exception as exc:
        return ProtocolResult(
            protocol=resolved_proto,
            summary=f"分析失敗: {exc}",
            anomaly_count=1,
            total_items=0,
            status="error",
            markdown_report=f"# 診斷失敗 (Analysis Failed)\n\n**錯誤訊息**: {exc}\n",
        )


def generate_unified_report_from_files(
    files: list[Path | str],
    protocols: list[str] | None = None,
) -> UnifiedReport:
    """Generate a UnifiedReport by analyzing a list of files."""
    results: list[ProtocolResult] = []
    for idx, f in enumerate(files):
        proto = "auto"
        if protocols and idx < len(protocols):
            proto = protocols[idx]
        res = analyze_file_for_unified_report(f, protocol=proto)
        results.append(res)
    return build_unified_report(results)
