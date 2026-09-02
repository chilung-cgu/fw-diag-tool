"""Tests for CLI log (analyze, diff) and em (validate) subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fw_diag_tool.cli import app

runner = CliRunner()

SAMPLE_DMESG_FAILURES = """
[   10.123456] i2c i2c-1: controller timed out
[   10.124000] i2c 1-0048: Failed to probe device (-ENXIO)
[   15.500000] pcieport 0000:00:01.0: AER: Uncorrectable error received
"""

SAMPLE_CLEAN_LOG = """
[    0.000000] Linux version 6.6.0 (builder@buildhost)
[    0.000001] Command line: BOOT_IMAGE=/vmlinuz root=/dev/sda1
[    0.050000] ACPI: Core revision 20230628
"""

SAMPLE_CANDIDATE_LOG = """
[   10.123456] i2c i2c-1: controller timed out
[   10.124000] i2c 1-0048: Failed to probe device (-ENXIO)
[   20.000000] watchdog: watchdog0: watchdog did not stop!
"""

SAMPLE_BOARD_PROFILE = """
board_name: "TestServer_V1"
version: "1.0.0"
i2c_buses:
  - bus_num: 1
    speed_mode: "standard"
    devices:
      - address_7bit: 0x48
        name: "TMP75_Inlet"
        category: "sensor"
        protocol: "i2c"
        compatible: "ti,tmp75"
        register_width: 8
"""

SAMPLE_VALID_EM_JSON = json.dumps(
    {
        "Name": "Server_Mainboard",
        "Probe": "TRUE",
        "Exposes": [
            {
                "Address": "0x48",
                "Bus": 1,
                "Name": "Inlet Temp Sensor",
                "Type": "TMP75",
            }
        ],
    },
    indent=2,
)

SAMPLE_INVALID_EM_JSON = json.dumps(
    {
        "Name": "Server_Mainboard",
        "Exposes": [
            {
                "Address": "0x02",
                "Bus": 1,
                "Name": "Invalid Address Sensor",
                "Type": "TMP75",
            }
        ],
    },
    indent=2,
)

SAMPLE_WARNING_EM_JSON = json.dumps(
    {
        "Exposes": [
            {
                "Address": "0x48",
                "Bus": 1,
                "Name": "TMP75 Sensor",
                "Type": "TMP75",
            }
        ]
    },
    indent=2,
)


def test_cli_log_analyze_sample_dmesg(tmp_path: Path) -> None:
    """Test log analyze on a log file with failures."""
    log_file = tmp_path / "dmesg.log"
    log_file.write_text(SAMPLE_DMESG_FAILURES, encoding="utf-8")

    result = runner.invoke(app, ["log", "analyze", str(log_file)])
    assert result.exit_code == 0
    assert "System Log Diagnostic Summary" in result.output
    assert "Correlated Diagnostic Incidents" in result.output
    assert "INC-" in result.output


def test_cli_log_analyze_clean_log(tmp_path: Path) -> None:
    """Test log analyze on a clean log file."""
    log_file = tmp_path / "clean.log"
    log_file.write_text(SAMPLE_CLEAN_LOG, encoding="utf-8")

    result = runner.invoke(app, ["log", "analyze", str(log_file)])
    assert result.exit_code == 0
    assert "System Log Diagnostic Summary" in result.output
    assert "No diagnostic incidents or anomalies detected in log." in result.output


def test_cli_log_analyze_exports_md_and_json(tmp_path: Path) -> None:
    """Test log analyze exporting markdown and JSON reports."""
    log_file = tmp_path / "dmesg.log"
    log_file.write_text(SAMPLE_DMESG_FAILURES, encoding="utf-8")

    md_out = tmp_path / "report.md"
    json_out = tmp_path / "report.json"

    result = runner.invoke(
        app,
        ["log", "analyze", str(log_file), "--md", str(md_out), "--json", str(json_out)],
    )
    assert result.exit_code == 0
    assert md_out.exists()
    assert json_out.exists()

    md_content = md_out.read_text(encoding="utf-8")
    assert "# System Log Diagnostic Report" in md_content
    assert "## Incidents" in md_content

    json_data = json.loads(json_out.read_text(encoding="utf-8"))
    assert "summary" in json_data
    assert "incidents" in json_data
    assert json_data["summary"]["total_events"] > 0


def test_cli_log_analyze_with_board_profile(tmp_path: Path) -> None:
    """Test log analyze with board profile enrichment."""
    log_file = tmp_path / "dmesg.log"
    log_file.write_text(SAMPLE_DMESG_FAILURES, encoding="utf-8")

    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE, encoding="utf-8")

    result = runner.invoke(
        app,
        ["log", "analyze", str(log_file), "-b", str(profile_file)],
    )
    assert result.exit_code == 0
    assert "Board Profile Topology Context" in result.output or "TMP75_Inlet" in result.output


def test_cli_log_analyze_fail_on_thresholds(tmp_path: Path) -> None:
    """Test log analyze --fail-on options."""
    log_file = tmp_path / "dmesg.log"
    log_file.write_text(SAMPLE_DMESG_FAILURES, encoding="utf-8")

    # Fail on error should exit 1 because errors exist
    res_error = runner.invoke(app, ["log", "analyze", str(log_file), "--fail-on", "error"])
    assert res_error.exit_code == 1

    # Fail on critical should exit 1 because AER is critical
    res_crit = runner.invoke(app, ["log", "analyze", str(log_file), "--fail-on", "critical"])
    assert res_crit.exit_code == 1

    # Invalid fail-on level should exit 2
    res_invalid = runner.invoke(app, ["log", "analyze", str(log_file), "--fail-on", "unknown"])
    assert res_invalid.exit_code == 2

    # Clean log with --fail-on error should exit 0
    clean_file = tmp_path / "clean.log"
    clean_file.write_text(SAMPLE_CLEAN_LOG, encoding="utf-8")
    res_clean = runner.invoke(app, ["log", "analyze", str(clean_file), "--fail-on", "error"])
    assert res_clean.exit_code == 0


def test_cli_log_analyze_missing_file() -> None:
    """Test log analyze when input file does not exist."""
    result = runner.invoke(app, ["log", "analyze", "/non/existent/log/file.log"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()


def test_cli_log_diff(tmp_path: Path) -> None:
    """Test log diff comparing baseline and candidate logs."""
    base_file = tmp_path / "base.log"
    base_file.write_text(SAMPLE_DMESG_FAILURES, encoding="utf-8")

    cand_file = tmp_path / "cand.log"
    cand_file.write_text(SAMPLE_CANDIDATE_LOG, encoding="utf-8")

    json_out = tmp_path / "diff.json"

    result = runner.invoke(
        app,
        ["log", "diff", str(base_file), str(cand_file), "-j", str(json_out)],
    )
    assert result.exit_code == 0
    assert "System Log Diff Comparison" in result.output
    assert "Summary:" in result.output
    assert json_out.exists()

    diff_data = json.loads(json_out.read_text(encoding="utf-8"))
    assert "new_incidents" in diff_data
    assert "resolved_incidents" in diff_data
    assert "event_count_delta" in diff_data


def test_cli_log_diff_missing_files(tmp_path: Path) -> None:
    """Test log diff with non-existent files."""
    valid_file = tmp_path / "exists.log"
    valid_file.write_text(SAMPLE_CLEAN_LOG, encoding="utf-8")

    result = runner.invoke(
        app,
        ["log", "diff", str(valid_file), "/non/existent/file.log"],
    )
    assert result.exit_code == 1

    result2 = runner.invoke(
        app,
        ["log", "diff", "/non/existent/file.log", str(valid_file)],
    )
    assert result2.exit_code == 1


def test_cli_em_validate_valid_json(tmp_path: Path) -> None:
    """Test em validate on a valid Entity-Manager JSON."""
    em_file = tmp_path / "valid_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    result = runner.invoke(app, ["em", "validate", str(em_file)])
    assert result.exit_code == 0
    assert "valid (0 issues found)" in result.output


def test_cli_em_validate_invalid_json(tmp_path: Path) -> None:
    """Test em validate on an invalid Entity-Manager JSON."""
    em_file = tmp_path / "invalid_em.json"
    em_file.write_text(SAMPLE_INVALID_EM_JSON, encoding="utf-8")

    json_out = tmp_path / "issues.json"

    result = runner.invoke(
        app,
        ["em", "validate", str(em_file), "--json", str(json_out)],
    )
    assert result.exit_code == 1
    assert "Entity-Manager Validation Issues" in result.output
    assert json_out.exists()

    issues_data = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(issues_data) > 0
    assert any(i["severity"] in ("ERROR", "CRITICAL") for i in issues_data)


def test_cli_em_validate_warning_only_json(tmp_path: Path) -> None:
    """Test em validate on a JSON with only warnings (e.g. missing Name), exits 0."""
    em_file = tmp_path / "warning_em.json"
    em_file.write_text(SAMPLE_WARNING_EM_JSON, encoding="utf-8")

    result = runner.invoke(app, ["em", "validate", str(em_file)])
    assert result.exit_code == 0
    assert "Entity-Manager Validation Issues" in result.output


def test_cli_em_validate_with_board_profile(tmp_path: Path) -> None:
    """Test em validate with board profile cross-referencing."""
    em_file = tmp_path / "valid_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE, encoding="utf-8")

    result = runner.invoke(
        app,
        ["em", "validate", str(em_file), "-b", str(profile_file)],
    )
    assert result.exit_code == 0


def test_cli_em_validate_missing_file() -> None:
    """Test em validate when file does not exist."""
    result = runner.invoke(app, ["em", "validate", "/non/existent/em.json"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()


def test_cli_log_help_messages() -> None:
    """Test help messages for log and em command suites."""
    res_log = runner.invoke(app, ["log", "--help"])
    assert res_log.exit_code == 0
    assert "analyze" in res_log.output
    assert "diff" in res_log.output

    res_em = runner.invoke(app, ["em", "--help"])
    assert res_em.exit_code == 0
    assert "validate" in res_em.output
    assert "generate" in res_em.output
    assert "mock" in res_em.output


def test_cli_log_analyze_fail_on_error_only(tmp_path: Path) -> None:
    """Test log analyze with error-level events but no critical-level events."""
    log_file = tmp_path / "errors_only.log"
    log_content = (
        "[ 10.0 ] i2c i2c-1: controller timed out\n"
        "[ 10.1 ] i2c 1-0048: Failed to probe device (-ENXIO)\n"
    )
    log_file.write_text(log_content, encoding="utf-8")

    # --fail-on error should trigger exit 1
    res_error = runner.invoke(app, ["log", "analyze", str(log_file), "--fail-on", "error"])
    assert res_error.exit_code == 1

    # --fail-on critical should NOT trigger exit 1 (should be exit 0)
    res_crit = runner.invoke(app, ["log", "analyze", str(log_file), "--fail-on", "critical"])
    assert res_crit.exit_code == 0


def test_cli_em_validate_malformed_syntax(tmp_path: Path) -> None:
    """Test em validate on a malformed JSON string."""
    em_file = tmp_path / "malformed.json"
    em_file.write_text("{ Name: unquoted key, Exposes: [ }", encoding="utf-8")

    result = runner.invoke(app, ["em", "validate", str(em_file)])
    assert result.exit_code == 1
    assert "JSON syntax error" in result.output or "CRITICAL" in result.output


def test_cli_em_generate_json(tmp_path: Path) -> None:
    """Test em generate command producing Entity-Manager JSON."""
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE, encoding="utf-8")

    # Test stdout output
    result = runner.invoke(app, ["em", "generate", str(profile_file), "--format", "json"])
    assert result.exit_code == 0
    assert "Exposes" in result.output
    assert "TMP75" in result.output

    # Test file output
    out_file = tmp_path / "em_out.json"
    res_file = runner.invoke(
        app,
        ["em", "generate", str(profile_file), "-f", "json", "-o", str(out_file)],
    )
    assert res_file.exit_code == 0
    assert out_file.exists()
    assert "TMP75" in out_file.read_text(encoding="utf-8")


def test_cli_em_generate_dts(tmp_path: Path) -> None:
    """Test em generate command producing Linux Device Tree."""
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE, encoding="utf-8")

    result = runner.invoke(app, ["em", "generate", str(profile_file), "--format", "dts", "-b", "1"])
    assert result.exit_code == 0
    assert "&i2c1" in result.output
    assert "compatible" in result.output


def test_cli_em_generate_both_and_invalid(tmp_path: Path) -> None:
    """Test em generate command with both format and error handling."""
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE, encoding="utf-8")

    # Test both
    res_both = runner.invoke(app, ["em", "generate", str(profile_file), "-f", "both"])
    assert res_both.exit_code == 0
    assert "Exposes" in res_both.output
    assert "i2c" in res_both.output

    # Test invalid format
    res_inv = runner.invoke(app, ["em", "generate", str(profile_file), "-f", "invalid_fmt"])
    assert res_inv.exit_code == 2

    # Test non-existent file
    res_missing = runner.invoke(app, ["em", "generate", "/non/existent/prof.yaml"])
    assert res_missing.exit_code == 1


def test_cli_em_mock_bash_and_python(tmp_path: Path) -> None:
    """Test em mock command generating Bash and Python mock scripts."""
    em_file = tmp_path / "valid_em.json"
    em_file.write_text(SAMPLE_VALID_EM_JSON, encoding="utf-8")

    # Test Bash format to stdout
    res_bash = runner.invoke(app, ["em", "mock", str(em_file), "--format", "bash"])
    assert res_bash.exit_code == 0
    assert "#!/bin/bash" in res_bash.output
    assert "busctl" in res_bash.output

    # Test Python format to file
    out_py = tmp_path / "mock.py"
    res_py = runner.invoke(app, ["em", "mock", str(em_file), "-f", "python", "-o", str(out_py)])
    assert res_py.exit_code == 0
    assert out_py.exists()
    py_content = out_py.read_text(encoding="utf-8")
    assert "class " in py_content or "xyz.openbmc_project" in py_content

    # Test invalid format
    res_inv = runner.invoke(app, ["em", "mock", str(em_file), "-f", "yaml"])
    assert res_inv.exit_code == 2

    # Test non-existent file
    res_missing = runner.invoke(app, ["em", "mock", "/non/existent/em.json"])
    assert res_missing.exit_code == 1
