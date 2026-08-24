from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from fw_diag_tool.cli import app, main
from fw_diag_tool.mctp.models import IPMBFrame, MCTPPacket, ServerMgmtReport
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def test_cli_pcie_analyze_dmesg_and_lspci(tmp_path: Path):
    runner = CliRunner()

    # 1. dmesg AER
    dmesg_text = "AER: Multiple Corrected error received: 0000:00:1c.0"
    dmesg_file = tmp_path / "dmesg.log"
    dmesg_file.write_text(dmesg_text, encoding="utf-8")
    out_md = tmp_path / "pcie_out.md"

    res = runner.invoke(app, ["pcie", "analyze", str(dmesg_file), "--md", str(out_md)])
    assert res.exit_code == 0
    assert out_md.exists()

    # 2. lspci text directly in argument
    lspci_text = (
        "0000:01:00.0 Processing accelerators: Xilinx Corporation Device 7024\n"
        "00: ee 10 24 70 06 00 10 00 01 00 80 12 00 00 00 00\n"
        "10: 0c 00 00 f0 00 00 00 00 00 00 00 00 00 00 00 00\n"
        "20: 00 00 00 00 00 00 00 00 00 00 00 00 ee 10 24 70\n"
        "30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
    )
    lspci_file = tmp_path / "lspci.txt"
    lspci_file.write_text(lspci_text, encoding="utf-8")
    res2 = runner.invoke(app, ["pcie", "analyze", str(lspci_file)])
    assert res2.exit_code == 0
    assert "Device Overview" in res2.output

    # 3. Invalid input
    bad_lspci = "0000:01:00.0 Memory controller: Test Device\n00: 12 34\n"
    res3 = runner.invoke(app, ["pcie", "analyze", bad_lspci])
    assert res3.exit_code == 0
    assert "Device Overview" in res3.output


def test_cli_spi_analyze_and_reporter(tmp_path: Path):
    runner = CliRunner()
    spi_csv = tmp_path / "spi.csv"
    spi_csv.write_text(
        "Time,MOSI,MISO,Enable\n0.0,0x06,0x00,1\n0.1,0x05,0x00,1\n",
        encoding="utf-8",
    )
    out_md = tmp_path / "spi_out.md"

    res = runner.invoke(app, ["spi", "analyze", str(spi_csv), "--md", str(out_md)])
    assert res.exit_code == 0
    assert out_md.exists()

    # Missing file
    res_missing = runner.invoke(app, ["spi", "analyze", str(tmp_path / "missing.csv")])
    assert res_missing.exit_code == 1

    # Reporter directly
    report = SPIDiagnosticEngine().analyze_csv_file(spi_csv)
    buf = StringIO()
    SPIReporter.render_terminal(report, console=Console(file=buf))
    assert "SPI / QSPI Flash Protocol Diagnostic Report" in buf.getvalue()


def test_cli_uart_analyze_and_reporter(tmp_path: Path):
    runner = CliRunner()
    panic_text = (
        "BUG: unable to handle page fault for address: 0000000000000010\n"
        "RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\n"
    )
    panic_file = tmp_path / "panic.log"
    panic_file.write_text(panic_text, encoding="utf-8")
    out_md = tmp_path / "uart_out.md"

    res = runner.invoke(app, ["uart", "analyze", str(panic_file), "--md", str(out_md)])
    assert res.exit_code == 0
    assert out_md.exists()

    # HardFault reporter
    hf_text = "HardFault Exception Occurred!\nHFSR: 0x40000000\nCFSR: 0x02000000\n"
    hf_report = UARTCrashParser.parse_log_text(hf_text)
    buf = StringIO()
    UARTReporter.render_terminal(hf_report, console=Console(file=buf))
    assert "UART Crash & HardFault Diagnostic Report" in buf.getvalue()

    # Panic reporter
    panic_report = UARTCrashParser.parse_log_text(panic_text)
    buf_p = StringIO()
    UARTReporter.render_terminal(panic_report, console=Console(file=buf_p))
    assert "UART Crash & HardFault Diagnostic Report" in buf_p.getvalue()


def test_cli_mctp_analyze_and_reporter(tmp_path: Path):
    runner = CliRunner()
    dump_text = (
        "# MCTP Packet & IPMB\n"
        "01 08 00 C0 01 00 02 01 00\n"
        "81 1C 63 20 20 01 00 BF\n"
        "not-a-packet\n"
    )
    dump_file = tmp_path / "mctp.hex"
    dump_file.write_text(dump_text, encoding="utf-8")
    out_md = tmp_path / "mctp_out.md"

    res = runner.invoke(app, ["mctp", "analyze", str(dump_file), "--md", str(out_md)])
    assert res.exit_code == 0
    assert out_md.exists()

    # Direct reporter tests with packets and frames
    report = ServerMgmtReport(
        mctp_packets=[
            MCTPPacket(
                dest_eid=8,
                src_eid=0,
                som=True,
                eom=True,
                pkt_seq=0,
                to=True,
                msg_tag=0,
                msg_type=1,
                msg_type_name="PLDM",
                payload=[1, 2, 3],
                summary="MCTP summary",
                pldm_command="PLDM Cmd",
            )
        ],
        ipmb_frames=[
            IPMBFrame(
                rs_addr=0x20,
                netfn=6,
                netfn_name="App",
                rs_lun=0,
                checksum1_valid=True,
                rq_addr=0x81,
                rq_seq=1,
                rq_lun=0,
                cmd=1,
                cmd_name="Get Device ID",
                data=[0],
                checksum2_valid=True,
                summary="IPMB summary",
            )
        ],
        total_frames=2,
        summary_text="Decoded 1 MCTP, 1 IPMB",
        unparsed_lines=["corrupt_line"],
        source_errors=["line 3 error"],
    )
    buf = StringIO()
    ServerMgmtReporter.render_terminal(report, console=Console(file=buf))
    assert "MCTP Packets" in buf.getvalue()
    assert "IPMB Frames" in buf.getvalue()
    assert "Input Lines Not Decoded" in buf.getvalue()


def test_cli_reg_decode_and_generators(tmp_path: Path):
    runner = CliRunner()
    yaml_content = """chip_name: TEST_CHIP
base_address: 0x1000
registers:
  - name: STATUS
    offset: 0x04
    size: 32
    reset_val: 0x00000000
    fields:
      - name: READY
        bits: "0"
        access: RO
        description: Ready bit
"""
    yaml_file = tmp_path / "regs.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # 1. reg decode success
    res_dec = runner.invoke(app, ["reg", "decode", str(yaml_file), "STATUS", "0x01"])
    assert res_dec.exit_code == 0
    assert "READY" in res_dec.output

    # 2. reg decode invalid hex
    res_bad_hex = runner.invoke(app, ["reg", "decode", str(yaml_file), "STATUS", "not-hex"])
    assert res_bad_hex.exit_code == 1

    # 3. reg decode missing file
    res_no_file = runner.invoke(app, ["reg", "decode", str(tmp_path / "none.yaml"), "STATUS", "0x01"])
    assert res_no_file.exit_code == 1

    # 4. gen c-header with file output
    out_h = tmp_path / "regs.h"
    res_hdr = runner.invoke(app, ["gen", "c-header", str(yaml_file), "--out", str(out_h)])
    assert res_hdr.exit_code == 0
    assert out_h.exists()

    # 5. gen c-header stdout
    res_hdr2 = runner.invoke(app, ["gen", "c-header", str(yaml_file)])
    assert res_hdr2.exit_code == 0
    assert "STATUS" in res_hdr2.output

    # 6. gen dts with file output
    out_dts = tmp_path / "bus.dts"
    res_dts = runner.invoke(app, ["gen", "dts", "--bus", "2", "--mux", "0x72", "--out", str(out_dts)])
    assert res_dts.exit_code == 0
    assert out_dts.exists()

    # 7. gen dts invalid mux
    res_bad_mux = runner.invoke(app, ["gen", "dts", "--mux", "bad-addr"])
    assert res_bad_mux.exit_code == 1


def test_cli_diff_and_fuzz(tmp_path: Path):
    runner = CliRunner()
    trace_a = tmp_path / "a.csv"
    trace_b = tmp_path / "b.csv"
    trace_c = tmp_path / "c.csv"

    csv_normal = "Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.0,1,0x50,0x10,Write,ACK\n"
    csv_nack = "Time,Packet ID,Address,Data,Read/Write,ACK/NAK\n0.0,1,0x50,0x10,Write,NAK\n"

    trace_a.write_text(csv_normal, encoding="utf-8")
    trace_b.write_text(csv_normal, encoding="utf-8")
    trace_c.write_text(csv_nack, encoding="utf-8")

    # 1. diff identical
    res_same = runner.invoke(app, ["i2c", "diff", str(trace_a), str(trace_b)])
    assert res_same.exit_code == 0
    assert "identical" in res_same.output

    # 2. diff divergent
    res_diff = runner.invoke(app, ["i2c", "diff", str(trace_a), str(trace_c)])
    assert res_diff.exit_code == 0
    assert "Divergence" in res_diff.output or "Found" in res_diff.output

    # 3. diff missing file
    res_missing = runner.invoke(app, ["i2c", "diff", str(trace_a), str(tmp_path / "missing.csv")])
    assert res_missing.exit_code == 1

    # 4. fuzz
    res_fuzz = runner.invoke(app, ["fuzz", "--seeds", "2"])
    assert res_fuzz.exit_code == 0
    assert "passed" in res_fuzz.output

    # 5. fuzz invalid seeds
    res_bad_fuzz = runner.invoke(app, ["fuzz", "--seeds", "0"])
    assert res_bad_fuzz.exit_code == 2


def test_main_entrypoint(monkeypatch):
    called = False

    def fake_app():
        nonlocal called
        called = True

    monkeypatch.setattr("fw_diag_tool.cli.app", fake_app)
    main()
    assert called is True
