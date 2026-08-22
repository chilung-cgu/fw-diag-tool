#!/usr/bin/env python3
"""Demonstration script for fw_diag_tool I2C / SMBus / PMBus Diagnostic Engine."""

from pathlib import Path

from rich.console import Console

from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.reporter import I2CReporter

console = Console()


def run_demo():
    console.rule("[bold cyan]fw_diag_tool - I2C / SMBus / PMBus Diagnostic Engine Demo[/bold cyan]")
    engine = I2CDiagnosticEngine(default_eeprom_page_size=8, smbus_timeout_ms=25.0)
    data_dir = Path(__file__).parent.parent / "tests" / "data"

    # Demo 1: Normal Multi-Device Trace (PMBus VR + 24C02 EEPROM + LM75 Temp + PCA9555 GPIO)
    console.print(
        "\n[bold green]=== Demo 1: Normal System Trace (PMBus + EEPROM + LM75 + PCA9555) ===[/bold green]"
    )
    normal_csv = data_dir / "saleae_normal_pmbus_eeprom.csv"
    if normal_csv.exists():
        report1 = engine.analyze_csv_file(str(normal_csv))
        I2CReporter.render_terminal(report1, console=console)

        # Export Markdown
        md_path = Path(__file__).parent / "demo_normal_report.md"
        md_text = I2CReporter.generate_markdown(report1)
        md_path.write_text(md_text, encoding="utf-8")
        console.print(f"[dim]Exported sample markdown report to: {md_path}[/dim]\n")

    # Demo 2: Anomaly Trace with EEPROM Rollover Hazard & Data NACK
    console.print(
        "\n[bold red]=== Demo 2: Diagnostic Anomalies (EEPROM Page Rollover & Slave Data NACK) ===[/bold red]"
    )
    anomaly_csv = data_dir / "saleae_anomaly_eeprom_rollover_and_data_nack.csv"
    if anomaly_csv.exists():
        report2 = engine.analyze_csv_file(str(anomaly_csv))
        I2CReporter.render_terminal(report2, console=console)

    # Demo 3: Anomaly Trace with SMBus 25ms Clock Stretching Timeout
    console.print(
        "\n[bold red]=== Demo 3: Critical Timing Anomaly (SMBus 25ms Clock Stretching Timeout) ===[/bold red]"
    )
    stretch_csv = data_dir / "saleae_anomaly_clock_stretching.csv"
    if stretch_csv.exists():
        report3 = engine.analyze_csv_file(str(stretch_csv))
        I2CReporter.render_terminal(report3, console=console)

    # Demo 4: Programmatic Raw Text Trace Analysis
    console.print(
        "\n[bold yellow]=== Demo 4: Programmatic Text Trace Log Analysis ===[/bold yellow]"
    )
    text_trace = """
[0.001000] S 0x48 W 0x00 A P
[0.001150] S 0x48 R 0x1A A 0x80 N P
"""
    report4 = engine.analyze_text(text_trace)
    I2CReporter.render_terminal(report4, console=console)


if __name__ == "__main__":
    run_demo()
