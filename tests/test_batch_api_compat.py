from __future__ import annotations

from pathlib import Path

from fw_diag_tool.reporting.batch import _detect_protocol_for_file, batch_analyze_directory


def test_batch_directory_accepts_positional_protocols_and_output_dir(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / "trace.csv").write_text(
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK\n0.001,1,0x50,0x00,Write,ACK\n",
        encoding="utf-8",
    )

    entries = batch_analyze_directory(input_dir, ["i2c"], output_dir)

    assert len(entries) == 1
    assert entries[0]["protocol"] == "i2c"
    assert (output_dir / "trace_report.md").exists()


def test_protocol_detection_prefers_i2c_columns_and_is_case_insensitive(tmp_path: Path) -> None:
    mixed_csv = tmp_path / "mixed.CSV"
    mixed_csv.write_text("TIME,SCL,SDA,MOSI,MISO,CS\n0.1,1,1,0x00,0x00,0\n", encoding="utf-8")
    assert _detect_protocol_for_file(mixed_csv) == "i2c"

    crash_log = tmp_path / "CRASH.LOG"
    crash_log.write_text("KERNEL PANIC - not syncing: fatal exception\n", encoding="utf-8")
    assert _detect_protocol_for_file(crash_log) == "uart"


def test_batch_handles_pcie_reports_and_dmesg_detection() -> None:
    examples = Path(__file__).resolve().parents[1] / "examples/data"
    assert _detect_protocol_for_file(examples / "pcie_aer_dmesg.log") == "pcie"

    entries = batch_analyze_directory(examples, protocols=["pcie"])

    by_name = {Path(entry["file"]).name: entry for entry in entries}
    assert "error" not in by_name["pcie_aer_lspci.txt"]
    assert by_name["pcie_aer_dmesg.log"]["status"] == "warning"
