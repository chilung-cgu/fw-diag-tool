"""Fuzzing 與 waveform diff 的額外 CLI 指令。"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from fw_diag_tool.fuzz.fuzzer import FuzzingGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.i2c.waveform_diff_report import (
    localize_diff_description,
    localize_diff_hint,
    localize_diff_summary,
    localize_diff_type,
)


def register_extra_commands(app: typer.Typer, i2c_app: typer.Typer, console: Console) -> None:
    """在既有 Typer app 註冊 fuzz 與 diff 指令。"""

    @i2c_app.command("diff")
    def diff_i2c_traces(
        golden: Path = typer.Argument(..., help="參考 Golden trace CSV（Golden trace CSV）"),
        failing: Path = typer.Argument(..., help="待分析 Failing trace CSV（Failing trace CSV）"),
    ) -> None:
        """比較 Golden 與 Failing I2C trace（Compare Golden vs Failing I2C traces）。"""
        if not golden.exists() or not failing.exists():
            console.print(
                "[bold red]錯誤：Golden 與 Failing 檔案都必須存在。"
                "（Error: Both files must exist!）[/]"
            )
            raise typer.Exit(code=1)
        try:
            engine = I2CDiagnosticEngine()
            g_rep = engine.analyze_csv_file(str(golden))
            f_rep = engine.analyze_csv_file(str(failing))
            diff_result = WaveformDiffEngine.compare_reports(g_rep, f_rep)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            console.print(
                f"[bold red]錯誤：I2C diff 輸入或報告產生失敗：{exc} "
                f"（Error: I2C diff input is invalid: {exc}）[/]"
            )
            raise typer.Exit(code=2) from exc
        if diff_result.is_identical:
            console.print(
                "[bold green]Golden 與 Failing trace 的協定序列完全一致。"
                "（Traces are identical.）[/]"
            )
        else:
            console.print(f"[bold red]{localize_diff_summary(diff_result.summary)}[/]")
            for dp in diff_result.divergence_points:
                console.print(
                    Panel(
                        f"[bold]類型（Type）:[/] {localize_diff_type(dp.mismatch_type)}\n"
                        f"[bold]現象描述（Description）:[/] {localize_diff_description(dp.description)}",
                        title=f"分歧位置（Divergence at Tx #{dp.tx_index}）",
                    )
                )
                console.print(f"[bold]排查提示（Hint）:[/] {localize_diff_hint(dp.root_cause_hint)}")

    @app.command("fuzz")
    def run_fuzzing(
        seeds: int = typer.Option(
            50, "--seeds", "-s", help="測試案例數量（Number of test cases）"
        ),
    ) -> None:
        """使用隨機 malformed input 執行 parser 壓力測試（Run parser stress tests with randomly generated malformed inputs）。"""
        from fw_diag_tool.uart.parser import UARTCrashParser

        if seeds <= 0:
            console.print(
                "[bold red]錯誤：--seeds 必須是正整數。"
                "（Error: --seeds must be a positive integer.）[/]"
            )
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
                console.print(
                    f"[red]I2C parser 崩潰：seed={seed}：{e} "
                    f"（I2C crash seed={seed}: {e}）[/]"
                )
            log_text = FuzzingGenerator.fuzz_uart_log(seed=seed)
            try:
                UARTCrashParser.parse_log_text(log_text)
                passed += 1
            except Exception as e:
                failed += 1
                console.print(
                    f"[red]UART parser 崩潰：seed={seed}：{e} "
                    f"（UART crash seed={seed}: {e}）[/]"
                )
        if failed == 0:
            console.print(
                f"[bold green]模糊測試完成：{passed}/{total} 通過，未發現 parser 崩潰。"
                f"（Fuzzing: {passed}/{total} passed. All robust.）[/]"
            )
        else:
            console.print(
                f"[bold red]模糊測試發現 {failed}/{total} 次崩潰！"
                f"（Fuzzing: {failed}/{total} crashes!）[/]"
            )
