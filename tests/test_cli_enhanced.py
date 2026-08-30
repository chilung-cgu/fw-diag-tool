from typer.testing import CliRunner

from fw_diag_tool.cli import app

runner = CliRunner()


def test_info_command():
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "fw-diag-tool" in result.output
    assert "支援協定" in result.output
    assert "I2C / SMBus / PMBus" in result.output


def test_check_command():
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "環境與依賴健康檢查" in result.output
    assert "Python 版本" in result.output
    assert "所有環境與依賴檢查均正常運作" in result.output


def test_help_contains_new_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "info" in result.output
    assert "check" in result.output
