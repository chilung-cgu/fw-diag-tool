"""Extra CLI commands for fuzzing and waveform diff."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from fw_diag_tool.fuzz.fuzzer import FuzzingGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine


def register_extra_commands(app: typer.Typer, i2c_app: typer.Typer, console: Console) -> None:
    """Register fuzz and diff commands on existing Typer apps."""

    @i2c_app.command("diff")
    def diff_i2c_traces(
        golden: Path = typer.Argument(..., help="Golden trace CSV"),
        failing: Path = typer.Argument(..., help="Failing trace CSV"),
    ) -> None:
        """Compare Golden vs Failing I2C traces."""
        if not golden.exists() or not failing.exists():
            console.print("[bold red]Error: Both files must exist![/]")
            raise typer.Exit(code=1)
        try:
            engine = I2CDiagnosticEngine()
            g_rep = engine.analyze_csv_file(str(golden))
            f_rep = engine.analyze_csv_file(str(failing))
            diff_result = WaveformDiffEngine.compare_reports(g_rep, f_rep)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            console.print(f"[bold red]Error: I2C diff input is invalid: {exc}[/]")
            raise typer.Exit(code=2) from exc
        if diff_result.is_identical:
            console.print("[bold green]Traces are identical.[/]")
        else:
            console.print(f"[bold red]{diff_result.summary}[/]")
            for dp in diff_result.divergence_points:
                console.print(
                    Panel(
                        f"[bold]Type:[/] {dp.mismatch_type}\n[bold]Description:[/] {dp.description}",
                        title=f"Divergence at Tx #{dp.tx_index}",
                    )
                )
                console.print(f"[bold]Hint:[/] {dp.root_cause_hint}")

    @app.command("fuzz")
    def run_fuzzing(
        seeds: int = typer.Option(50, "--seeds", "-s", help="Number of test cases"),
    ) -> None:
        """Run parser stress tests with randomly generated malformed inputs."""
        from fw_diag_tool.uart.parser import UARTCrashParser

        if seeds <= 0:
            console.print("[bold red]Error: --seeds must be a positive integer.[/]")
            raise typer.Exit(code=2)

        passed = 0
        failed = 0
        total = seeds * 2
        for seed in range(seeds):
            csv_data = FuzzingGenerator.fuzz_i2c_csv(seed=seed, num_rows=20)
            try:
                I2CDiagnosticEngine().analyze_csv_content(csv_data)
                passed += 1
            except Exception as e:
                failed += 1
                console.print(f"[red]I2C crash seed={seed}: {e}[/]")
            log_text = FuzzingGenerator.fuzz_uart_log(seed=seed)
            try:
                UARTCrashParser.parse_log_text(log_text)
                passed += 1
            except Exception as e:
                failed += 1
                console.print(f"[red]UART crash seed={seed}: {e}[/]")
        if failed == 0:
            console.print(f"[bold green]Fuzzing: {passed}/{total} passed. All robust.[/]")
        else:
            console.print(f"[bold red]Fuzzing: {failed}/{total} crashes![/]")
