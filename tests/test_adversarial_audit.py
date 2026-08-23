import pytest

from fw_diag_tool.analyzers.register_mapper import BitField
from fw_diag_tool.i2c.eeprom import decode_eeprom_write
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import RawEventType, RawI2CEvent
from fw_diag_tool.i2c.parser import I2CParser, parse_hex_or_int
from fw_diag_tool.i2c.pmbus import decode_linear16, decode_pmbus_payload, encode_linear11
from fw_diag_tool.pcie.diagnostics import diagnose_pcie_device
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.spi.engine import SPIDiagnosticEngine


def test_pcie_diagnostics_no_attribute_error():
    raw = bytearray(4096)
    raw[0:4] = bytes([0xEE, 0x10, 0x24, 0x70])
    raw[6] = 0x10
    raw[0x34] = 0x40
    raw[0x40] = 0x10
    raw[0x41] = 0x00
    raw[0x100:0x104] = bytes([0x01, 0x00, 0x01, 0x00])  # AER Ext Cap
    raw[0x104] = 0x10  # Uncorr Error: DLP Error (Bit 4)
    raw[0x110] = 0x01  # Corr Error (Offset 0x10 in AER): Receiver Error (Bit 0)
    cfg = PCIeAnalyzer.decode_config_space(bytes(raw), bdf="0000:01:00.0")
    findings = diagnose_pcie_device(cfg)
    assert len(findings) >= 2
    assert any(f["type"] == "AER_UNCORRECTABLE" for f in findings)
    assert any(f["type"] == "AER_CORRECTABLE" for f in findings)


def test_pcie_config_tlp_dw2_ext_register():
    dw0 = 0x04000001
    dw1 = 0x0010010F
    dw2 = (0x01 << 24) | (0x01 << 8)
    tlp = PCIeAnalyzer.decode_tlp_header(dw0, dw1, dw2, 0)
    assert tlp.type_name == "CfgRd0 (Config Read Type 0)"
    assert (tlp.address & 0xFFF) == 0x100


def test_pmbus_linear16_signed_trim():
    raw_word = 0xFFE6  # -26 in 16-bit 2s complement
    val_signed = decode_linear16(raw_word, vout_mode_exponent=-9, signed=True)
    assert -0.06 < val_signed < -0.04
    val_unsigned = decode_linear16(raw_word, vout_mode_exponent=-9, signed=False)
    assert val_unsigned > 100.0
    res = decode_pmbus_payload(0x22, [0xE6, 0xFF], vout_exponent=-9)
    assert res["value"] < 0.0


def test_pmbus_vout_mode_read_dynamic_update():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x58,Write,0x20,ACK
0.002,1,0x58,Read,0x14,ACK
0.003,2,0x58,Write,0x8B,ACK
0.004,3,0x58,Read,0x00 0x10,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    tx_vout = report.transactions[-1]
    assert tx_vout.command_name == "READ_VOUT"
    assert tx_vout.decoded_values.get("value") == 1.0


def test_spi_volatile_wren_and_chip_erase_alt():
    csv_data = """Time [s],MOSI,MISO,Enable
0.001,0x50,0x00,0
0.002,0x00,0x00,1
0.003,0x01,0x00,0
0.004,0x00,0x00,0
0.005,0x00,0x00,1
0.010,0x60,0x00,0
0.011,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.anomaly_count == 1
    assert report.anomalies[0].code == "SPI_WRITE_NO_WREN"
    assert report.anomalies[0].transaction_id == 3


def test_spi_jedec_line_fault():
    # MISO all 0xFF -> floating line
    csv_data = """Time [s],MOSI,MISO,Enable
0.001,0x9F,0x00,0
0.002,0x00,0xFF,0
0.003,0x00,0xFF,0
0.004,0x00,0xFF,0
0.005,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert any(a.code == "SPI_JEDEC_LINE_FAULT" for a in report.anomalies)


def test_eeprom_zero_page_size_guard():
    res = decode_eeprom_write([0x00, 0x12, 0x34], page_size=0)
    assert res["page_size"] == 1
    assert res["rollover_hazard"] is True
    assert "1 byte(s) will WRAP AROUND" in res["rollover_details"]


def test_linear11_nan_inf_guard():
    with pytest.raises(ValueError):
        encode_linear11(float("nan"))
    with pytest.raises(ValueError):
        encode_linear11(float("inf"))
    assert encode_linear11(0.0) == 0x0000


def test_bitfield_bracket_and_reverse_range():
    bf1 = BitField(name="TEST1", bit_range="[15:0]")
    assert bf1.high_bit == 15 and bf1.low_bit == 0
    bf2 = BitField(name="TEST2", bit_range="0:7")
    assert bf2.high_bit == 7 and bf2.low_bit == 0
    assert bf2.bit_mask == 0xFF


def test_i2c_raw_record_boundaries_are_rejected_not_reinterpreted():
    assert parse_hex_or_int("#50") == 0x50
    with pytest.raises(TypeError, match="mapping"):
        I2CParser.parse_raw_records([None])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="unknown event_type"):
        I2CParser.parse_raw_records([{"type": "GARBAGE"}])
    with pytest.raises(ValueError, match="address"):
        I2CParser.parse_raw_records([{"type": "ADDRESS", "address": -1}])
    with pytest.raises(ValueError, match="data byte"):
        I2CParser.parse_raw_records([{"type": "DATA", "data": 256}])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"smbus_timeout_ms": None},
        {"smbus_timeout_ms": "25"},
        {"smbus_timeout_ms": 0},
        {"smbus_timeout_ms": float("nan")},
        {"high_jitter_threshold_pct": 0},
        {"default_eeprom_page_size": 0},
        {"default_vout_exponent": 1024},
    ],
)
def test_i2c_engine_rejects_invalid_configuration(kwargs):
    with pytest.raises((TypeError, ValueError)):
        I2CDiagnosticEngine(**kwargs)


def test_ambiguous_eeprom_requires_explicit_profile_before_offset_decode():
    csv_data = """Time,Address,Read/Write,Data,ACK/NACK
0.001,0x50,Write,0x01 0x23 0xAA,ACK
"""
    ambiguous = I2CDiagnosticEngine().analyze_csv_content(csv_data)
    tx = ambiguous.transactions[0]
    assert tx.decoded_values["evidence"] == "ambiguous-address-profile"
    assert tx.decoded_values["address_bytes"] is None
    assert any(
        issue.code == "I2C_EEPROM_PROFILE_UNAVAILABLE" for issue in ambiguous.data_quality_issues
    )

    identified = I2CDiagnosticEngine(eeprom_profile="24C64").analyze_csv_content(csv_data)
    decoded = identified.transactions[0].decoded_values
    assert decoded["address_bytes"] == 2
    assert decoded["offset"] == 0x0123
    assert decoded["payload"] == ["0xAA"]


def test_pmbus_linear_formats_reject_unrepresentable_values_and_exponents():
    with pytest.raises(ValueError, match="representable"):
        encode_linear11(1e300)
    with pytest.raises(ValueError, match="representable"):
        encode_linear11(1e-300)
    with pytest.raises(ValueError, match="-16..15"):
        decode_linear16(1, 1024)


def test_engine_rejects_malformed_direct_event_and_reports_unknown_csv_rows():
    with pytest.raises(ValueError, match="timestamp"):
        I2CDiagnosticEngine().analyze(
            [RawI2CEvent(timestamp=None, event_type=RawEventType.DATA)]  # type: ignore[arg-type]
        )

    report = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Type,Address,Data\n0,GARBAGE,not-an-address,not-a-byte\n"
    )
    assert report.total_transactions == 0
    assert {issue.code for issue in report.data_quality_issues} >= {
        "I2C_UNKNOWN_EVENT_TYPE",
        "I2C_SOURCE_PARSE_ERROR",
    }
    invalid_address = I2CDiagnosticEngine().analyze_csv_content(
        "Time,Address,Data\n0,invalid,0x12\n"
    )
    assert any(
        issue.code == "I2C_SOURCE_PARSE_ERROR" for issue in invalid_address.data_quality_issues
    )


def test_reused_engine_does_not_leak_mux_state_between_captures():
    engine = I2CDiagnosticEngine()
    first = engine.analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x70,Write,0x01,ACK\n"
    )
    assert "MUX 0x70" in first.transactions[0].semantic_summary

    second = engine.analyze_csv_content(
        "Time,Address,Read/Write,Data,ACK/NACK\n0.001,0x50,Write,0x10,ACK\n"
    )
    assert second.transactions[0].mux_topology is None


from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.i2c.waveform_diff import DivergencePoint, WaveformDiffEngine, WaveformDiffReport
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.uart.models import CrashType
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def test_uart_arm64_kernel_panic_parsing():
    arm64_log = """Internal error: Oops: 96000005 [#1] SMP
Modules linked in: nvme nvme_core pci_hyperv
CPU: 2 PID: 1234 Comm: kworker/u8:2 Not tainted 5.15.0-arm64
Hardware name: Wiwynn Yosemite V4 (DT)
pstate: 60400005 (nZCv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
pc : [<ffff800008123456>] nvme_pci_complete_rq+0x38/0x120 [nvme]
lr : [<ffff800008123418>] nvme_irq_handler+0x8c/0x100 [nvme]
sp : ffff80000a113bc0
x0 : 0000000000000000 x1 : ffff000082345000 x2 : 0000000000000000
FAR_EL1: 0000000000000010
Call trace:
 [<ffff800008123456>] nvme_pci_complete_rq+0x38/0x120 [nvme]
 [<ffff800008123418>] nvme_irq_handler+0x8c/0x100 [nvme]
 [<ffff800008012340>] handle_irq_event+0x4c/0x90
---[ end trace 0000000000000000 ]---
"""
    report = UARTCrashParser.parse_log_text(arm64_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "ARM64"
    assert report.kernel_panic.faulting_func == "nvme_pci_complete_rq"
    assert report.kernel_panic.faulting_address == "0x0000000000000010"
    assert "nvme" in report.kernel_panic.modules_linked
    assert len(report.kernel_panic.call_trace) == 3
    assert "NULL Pointer Dereference" in report.kernel_panic.root_cause_analysis
    md = UARTReporter.to_markdown(report)
    assert "ARM64" in md
    assert "nvme, nvme_core, pci_hyperv" in md


def test_uart_riscv_kernel_panic_parsing():
    riscv_log = """Kernel panic - not syncing: Fatal exception in interrupt
epc : [<ffffffe000012345>] faulting_driver_isr+0x14/0x30 [riscv_drv]
ra : [<ffffffe000012300>] generic_irq_handler+0x20/0x40
sstatus: 0000000200000100
Call Trace:
 [<ffffffe000012345>] faulting_driver_isr+0x14/0x30 [riscv_drv]
 [<ffffffe000012300>] generic_irq_handler+0x20/0x40
Code: 01 02 03 04
"""
    report = UARTCrashParser.parse_log_text(riscv_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "RISC-V"
    assert report.kernel_panic.faulting_func == "faulting_driver_isr"


def test_uart_arm_hardfault_all_flags_and_zero_address():
    # CFSR: MMFSR has MMARVALID (0x80) and DACCVIOL (0x02) -> 0x82
    # BFSR has BFARVALID (0x80) and PRECISERR (0x02) -> 0x82
    # UFSR has DIVBYZERO (0x0200) and UNALIGNED (0x0100) -> 0x0300
    # CFSR = 0x03008282
    # MMFAR = 0x00000000, BFAR = 0x00000000
    hardfault_log = """HardFault Exception!
HFSR: 0x40000000
CFSR: 0x03008282
MMFAR: 0x00000000
BFAR: 0x00000000
Stacked PC: 0x08001000
Stacked LR: 0xFFFFFFF9
"""
    report = UARTCrashParser.parse_log_text(hardfault_log)
    assert report.crash_type == CrashType.ARM_HARDFAULT
    assert report.arm_hardfault is not None
    hf = report.arm_hardfault
    assert hf.mmfar_raw == 0x00000000
    assert hf.bfar_raw == 0x00000000
    assert any("MMFSR.MMARVALID (Fault Address: 0x00000000)" in f for f in hf.fault_flags)
    assert any("BFSR.BFARVALID (Fault Address: 0x00000000)" in f for f in hf.fault_flags)
    assert any("DIVBYZERO" in f for f in hf.fault_flags)
    assert any("UNALIGNED" in f for f in hf.fault_flags)
    md = UARTReporter.to_markdown(report)
    assert "0x00000000" in md
    assert "MMFAR" in md


def test_mctp_ipmb_checksum_corruption_disambiguation():
    # IPMB frame with corrupted Checksum 1 (Chk1 = 0x00 instead of valid sum)
    # rsSA=0x20, NetFn=0x18, Chk1=0x00 (Corrupted), rqSA=0x81, rqSeq=0x20, Cmd=0x01, Chk2=0x5E
    hex_dump = "20 18 00 81 20 01 5E"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.ipmb_frames) == 1
    assert len(report.mctp_packets) == 0
    assert report.ipmb_frames[0].checksum1_valid is False
    assert report.ipmb_frames[0].cmd_name == "Get Device ID"


def test_mctp_som_zero_no_pldm_decode():
    # Multi-packet continuation segment where SOM=0, Flags = 0x40 (SOM=0, EOM=1, Seq=0, Tag=0)
    # Even if payload bytes resemble PLDM, it should NOT decode as PLDM command
    hex_dump = "01 08 00 40 80 02 01 00"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.mctp_packets) == 1
    pkt = report.mctp_packets[0]
    assert pkt.som is False
    assert pkt.pldm_command is None
    assert pkt.msg_type_name == "Continuation Segment (SOM=0)"


def test_dts_gen_empty_devices_list():
    # Explicitly passing devices=[] should NOT fallback to default mock devices
    dts = DeviceTreeGenerator.generate_dts_from_topology(bus_num=1, mux_addr=0x70, devices=[])
    assert "&i2c1 {" in dts
    assert "i2c-mux@70 {" in dts
    assert 'compatible = "atmel,24c64";' not in dts
    assert 'compatible = "national,lm75";' not in dts


def test_dts_gen_rejects_duplicate_address_on_same_channel():
    # String addresses are accepted, but duplicate unit addresses are invalid Device Tree.
    devices = [
        {
            "addr": "0x50",
            "channel": "0",
            "name": "eeprom",
            "compatible": "atmel,24c64",
        },
        {
            "addr": "0x50",
            "channel": "0",
            "name": "eeprom-copy",
            "compatible": "atmel,24c64",
        },
    ]
    with pytest.raises(ValueError, match="duplicate I2C address"):
        DeviceTreeGenerator.generate_dts_from_topology(bus_num=2, mux_addr="0x70", devices=devices)


def test_waveform_diff_identical_traces_figure():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    diff = WaveformDiffReport(
        is_identical=True,
        total_compared=1,
        divergence_points=[],
        summary="Identical",
        golden_first_tx=tx,
        failing_first_tx=tx,
    )
    fig = WaveformDiffEngine.create_comparison_figure(diff)
    assert len(fig.data) >= 2  # Has traces in subplots


def test_waveform_diff_missing_tx_figure():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    dp = DivergencePoint(
        tx_index=1,
        golden_tx=tx,
        failing_tx=None,
        mismatch_type="MISSING_TX",
        description="Premature termination",
        root_cause_hint="Check driver",
    )
    diff = WaveformDiffReport(
        is_identical=False, total_compared=1, divergence_points=[dp], summary="Diverged"
    )
    fig = WaveformDiffEngine.create_comparison_figure(diff)
    assert fig is not None


def test_waveform_reconstructor_zero_clock_guard():
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    rec = I2CWaveformReconstructor(default_clock_khz=0.0)
    wave = rec.reconstruct_transaction_waveform(tx, clock_khz=-10.0)
    assert len(wave.time_us) > 0
