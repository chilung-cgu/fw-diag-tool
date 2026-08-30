from __future__ import annotations

import importlib

from typer.testing import CliRunner

from fw_diag_tool import cli

runner = CliRunner()


def test_doctor_reports_required_checks_and_versions() -> None:
    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "環境健康檢查" in result.output
    for package in ("streamlit", "plotly", "pandas", "rich", "typer", "pyyaml", "pydantic"):
        assert package in result.output
    assert "pytest" in result.output
    assert "fpdf2" in result.output
    assert "fw-diag-tool" in result.output
    assert "✓" in result.output


def test_doctor_returns_failure_for_missing_core_dependency(monkeypatch) -> None:
    original_import_module = importlib.import_module

    def import_without_streamlit(name: str, package: str | None = None):
        if name == "streamlit":
            raise ModuleNotFoundError("No module named 'streamlit'")
        return original_import_module(name, package)

    monkeypatch.setattr(cli.importlib, "import_module", import_without_streamlit)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "streamlit" in result.output
    assert "✗" in result.output


def test_doctor_warns_but_does_not_fail_without_optional_pdf_dependency(monkeypatch) -> None:
    original_import_module = importlib.import_module

    def import_without_fpdf(name: str, package: str | None = None):
        if name == "fpdf":
            raise ModuleNotFoundError("No module named 'fpdf'")
        return original_import_module(name, package)

    monkeypatch.setattr(cli.importlib, "import_module", import_without_fpdf)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "fpdf2" in result.output
    assert "⚠" in result.output


def test_doctor_returns_failure_when_examples_are_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_find_examples_dir", lambda: None)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "範例資料" in result.output
    assert "✗" in result.output


def test_doctor_returns_failure_for_unsupported_python(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_doctor_python_version", lambda: ((3, 9), "3.9.0"))

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "Python" in result.output
    assert "✗" in result.output
