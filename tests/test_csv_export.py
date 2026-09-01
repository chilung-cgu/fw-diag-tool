from __future__ import annotations

import csv
import io

from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction
from fw_diag_tool.mctp.models import IPMBFrame, MCTPPacket, ServerMgmtReport
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    DmesgAEREvent,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)
from fw_diag_tool.reporting.csv_export import (
    export_i2c_csv,
    export_mctp_csv,
    export_pcie_csv,
    export_spi_csv,
    export_uart_csv,
)
from fw_diag_tool.spi.models import SPIReport, SPIReportSummary, SPITransaction
from fw_diag_tool.uart.models import (
    ARMHardFaultReport,
    CallTraceFrame,
    CrashType,
    KernelPanicReport,
    UARTReport,
)


def _read_csv(csv_text: str) -> list[list[str]]:
    """Helper to parse generated CSV text with csv.reader, verifying UTF-8 BOM."""
    assert csv_text.startswith("﻿"), "CSV output must start with UTF-8 BOM"
    clean_text = csv_text.lstrip("﻿")
    reader = csv.reader(io.StringIO(clean_text))
    return list(reader)


# ==============================================================================
# I2C CSV Export Tests (3 tests)
# ==============================================================================


def test_export_i2c_csv_empty() -> None:
    """Empty transaction list outputs header only with UTF-8 BOM."""
    csv_str = export_i2c_csv([])
    rows = _read_csv(csv_str)
    assert len(rows) == 1
    header = rows[0]
    assert "ID" in header
    assert "Address 7-bit" in header
    assert "Direction" in header
    assert "Status" in header
    assert "Data Hex" in header


def test_export_i2c_csv_normal() -> None:
    """Normal I2C transactions output correct field values."""
    tx1 = I2CTransaction(
        id=1,
        start_time=0.001234,
        end_time=0.001334,
        duration_us=100.0,
        address_7bit=0x48,
        address_8bit=0x90,
        direction=I2CDirection.WRITE,
        address_ack=AckType.ACK,
        data_bytes=[0x00, 0x1A],
        device_name="TMP102",
        protocol="I2C",
        command_code=0x00,
        command_name="TEMPERATURE_REG",
        semantic_summary="Read temperature register pointer",
    )
    tx2 = I2CTransaction(
        id=2,
        start_time=0.002000,
        end_time=0.002200,
        duration_us=200.0,
        address_7bit=0x48,
        address_8bit=0x91,
        direction=I2CDirection.READ,
        address_ack=AckType.ACK,
        data_bytes=[0x19, 0x80],
        device_name="TMP102",
        protocol="I2C",
        semantic_summary="Temperature = 25.5 C",
    )
    csv_str = export_i2c_csv([tx1, tx2])
    rows = _read_csv(csv_str)
    assert len(rows) == 3
    r1, r2 = rows[1], rows[2]
    assert r1[0] == "1"
    assert r1[4] == "0x48"
    assert r1[6] == "WRITE"
    assert r1[11] == "TMP102"
    assert r2[0] == "2"
    assert r2[6] == "READ"
    assert r2[10] == "2"  # Byte Count


def test_export_i2c_csv_special_characters() -> None:
    """I2C export handles Chinese characters, commas, and quotes in fields."""
    tx = I2CTransaction(
        id=1,
        start_time=0.0,
        end_time=0.0001,
        duration_us=100.0,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        address_ack=AckType.NACK,
        data_bytes=[0xFF],
        device_name="EEPROM 儲存晶片（24C02）",
        protocol="I2C",
        semantic_summary='寫入指令, 包含 "特殊符號" 與逗號',
        anomalies=["從裝置無回應 (NACK)", "SCL 訊號異常, 發生 Clock Stretch"],
    )
    csv_str = export_i2c_csv([tx])
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    row = rows[1]
    assert "EEPROM 儲存晶片（24C02）" in row[11]
    assert '寫入指令, 包含 "特殊符號" 與逗號' in row[15]
    assert "從裝置無回應 (NACK); SCL 訊號異常, 發生 Clock Stretch" in row[16]


# ==============================================================================
# SPI CSV Export Tests (3 tests)
# ==============================================================================


def test_export_spi_csv_empty() -> None:
    """Empty SPI report outputs header only."""
    report = SPIReport(summary=SPIReportSummary(), transactions=[])
    csv_str = export_spi_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 1
    header = rows[0]
    assert "Index" in header
    assert "Opcode" in header
    assert "Opcode Name" in header
    assert "MOSI Hex" in header
    assert "MISO Hex" in header


def test_export_spi_csv_normal() -> None:
    """Normal SPI commands output correct columns and values."""
    tx1 = SPITransaction(
        index=1,
        start_time=0.0001,
        end_time=0.0002,
        duration_us=100.0,
        mosi_bytes=[0x06],
        miso_bytes=[0x00],
        opcode=0x06,
        opcode_name="Write Enable / WREN (0x06)",
        data_payload_len=0,
        wel_state_before=False,
        busy_state_after=False,
    )
    tx2 = SPITransaction(
        index=2,
        start_time=0.0003,
        end_time=0.0008,
        duration_us=500.0,
        mosi_bytes=[0x02, 0x00, 0x10, 0x00, 0xAA, 0x55],
        miso_bytes=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        opcode=0x02,
        opcode_name="Page Program (0x02)",
        address=0x001000,
        data_payload_len=2,
        wel_state_before=True,
        busy_state_after=True,
    )
    report = SPIReport(
        summary=SPIReportSummary(total_transactions=2),
        transactions=[tx1, tx2],
    )
    csv_str = export_spi_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 3
    assert rows[1][4] == "0x06"
    assert "WREN" in rows[1][5]
    assert rows[2][4] == "0x02"
    assert rows[2][6] == "0x001000"
    assert rows[2][7] == "2"


def test_export_spi_csv_special_characters() -> None:
    """SPI export handles Chinese descriptions and JSON decoded details properly."""
    tx = SPITransaction(
        index=1,
        start_time=0.0,
        end_time=0.001,
        duration_us=1000.0,
        mosi_bytes=[0x9F, 0x00, 0x00, 0x00],
        miso_bytes=[0x00, 0xEF, 0x40, 0x18],
        opcode=0x9F,
        opcode_name="讀取 JEDEC ID（Winbond 晶片, 128M-bit）",
        decoded_details={"manufacturer": "華邦電子 (Winbond)", "capacity_mb": 16},
    )
    report = SPIReport(
        summary=SPIReportSummary(total_transactions=1),
        transactions=[tx],
    )
    csv_str = export_spi_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    assert "華邦電子" in rows[1][12]
    assert "Winbond 晶片, 128M-bit" in rows[1][5]


# ==============================================================================
# UART CSV Export Tests (4 tests)
# ==============================================================================


def test_export_uart_csv_empty() -> None:
    """Empty UART report outputs header only."""
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="",
        raw_log_lines=0,
    )
    csv_str = export_uart_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 1
    header = rows[0]
    assert "Index" in header
    assert "Category" in header
    assert "Item / Function" in header
    assert "Details / Raw Line" in header


def test_export_uart_csv_kernel_panic_normal() -> None:
    """Kernel panic report exports call trace frames and registers."""
    frames = [
        CallTraceFrame(
            index=0,
            function_name="panic",
            offset="+0x120/0x150",
            module=None,
            address="0xffffffff81a1b2c3",
            raw_line="[  12.345678] ? panic+0x120/0x150",
        ),
        CallTraceFrame(
            index=1,
            function_name="do_page_fault",
            offset="+0x45/0x90",
            module="ext4",
            address="0xffffffff81045a10",
            raw_line="[  12.345680] ? do_page_fault+0x45/0x90 [ext4]",
        ),
    ]
    kp = KernelPanicReport(
        architecture="x86_64",
        panic_reason="Kernel NULL pointer dereference, address: 0000000000000000",
        faulting_ip="0xffffffff81045a10",
        faulting_func="do_page_fault",
        registers={"RIP": "0010:do_page_fault+0x45/0x90", "RSP": "0018:ffff880123456780"},
        call_trace=frames,
    )
    report = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="Linux Kernel Panic",
        kernel_panic=kp,
        raw_log_lines=100,
    )
    csv_str = export_uart_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) >= 3
    # Verify call trace rows
    assert rows[1][1] == "Call Trace"
    assert rows[1][2] == "panic"
    assert rows[2][1] == "Call Trace"
    assert rows[2][2] == "do_page_fault"
    assert rows[2][4] == "ext4"


def test_export_uart_csv_arm_hardfault_normal() -> None:
    """ARM HardFault report exports fault flags and register values."""
    hf = ARMHardFaultReport(
        hfsr_raw=0x40000000,
        cfsr_raw=0x00008200,
        bfsr_raw=0x82,
        bfar_raw=0x20001000,
        pc_faulting=0x08001234,
        lr_exc_return=0xFFFFFFF9,
        r0=0x00000000,
        r1=0x20000004,
        fault_flags=["PRECISERR: 精確資料匯流排錯誤", "BFARVALID: BFAR 暫存器有效"],
        root_cause_analysis="嘗試存取無效記憶體位址 0x20001000",
    )
    report = UARTReport(
        crash_type=CrashType.ARM_HARDFAULT,
        summary_title="ARM Cortex-M HardFault",
        arm_hardfault=hf,
    )
    csv_str = export_uart_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) >= 3
    assert rows[1][1] == "HardFault Flag"
    assert "PRECISERR" in rows[1][2]


def test_export_uart_csv_special_characters() -> None:
    """UART export preserves Chinese diagnostic notes and special symbols."""
    frames = [
        CallTraceFrame(
            index=0,
            function_name="i2c_transfer_handler",
            offset="+0x10/0x20",
            module="i2c_core",
            address="0xc0001234",
            raw_line="[ 1.0] i2c_transfer_handler: 發生超時, 重試次數=3, 錯誤碼='-ETIMEDOUT'",
        )
    ]
    kp = KernelPanicReport(
        architecture="ARM32",
        panic_reason="I2C 匯流排死鎖導致 Watchdog 逾時重置",
        call_trace=frames,
    )
    report = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="核心日誌追蹤",
        kernel_panic=kp,
    )
    csv_str = export_uart_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    assert "i2c_transfer_handler" in rows[1][2]
    assert "錯誤碼='-ETIMEDOUT'" in rows[1][6]


# ==============================================================================
# PCIe CSV Export Tests (4 tests)
# ==============================================================================


def test_export_pcie_csv_empty() -> None:
    """Empty configs and events list outputs header only."""
    csv_str = export_pcie_csv([], events=[])
    rows = _read_csv(csv_str)
    assert len(rows) == 1
    header = rows[0]
    assert "Record Type" in header
    assert "BDF" in header
    assert "Vendor / Timestamp" in header
    assert "Device / Error Name" in header
    assert "Class / Severity" in header


def test_export_pcie_csv_config_space_normal() -> None:
    """PCIe config spaces output correct fields including link info and AER."""
    link = PCIeLinkInfo(
        max_speed_str="16.0 GT/s (Gen4)",
        max_width=16,
        current_speed_str="8.0 GT/s (Gen3)",
        current_width=8,
        is_degraded=True,
        degradation_reason="Speed degraded from Gen4 to Gen3; Width degraded from x16 to x8",
    )
    aer = AERAnalysisResult(
        offset=0x100,
        uncorr_status_raw=0x00040000,
        uncorr_mask_raw=0,
        uncorr_severity_raw=0,
        corr_status_raw=0x00000001,
        corr_mask_raw=0,
        cap_control_raw=0,
        header_log_raw=[],
        uncorr_errors=[AERUncorrectableError(18, "Malformed TLP", "MTLP", True, False, "Fatal")],
        corr_errors=[AERCorrectableError(0, "Receiver Error", "RxErr", True, False)],
    )
    cfg = PCIeConfigSpace(
        raw_data=b"",
        bdf="0000:01:00.0",
        vendor_id=0x10DE,
        device_id=0x2204,
        class_name="VGA compatible controller",
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=link,
        aer_analysis=aer,
    )
    csv_str = export_pcie_csv([cfg])
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    row = rows[1]
    assert row[0] == "Config Space"
    assert row[1] == "0000:01:00.0"
    assert row[2] == "0x10DE"
    assert row[3] == "0x2204"
    assert "VGA" in row[4]
    assert "Gen3" in row[6]
    assert "Speed degraded" in row[7]
    assert "Malformed TLP" in row[8]
    assert "Receiver Error" in row[8]


def test_export_pcie_csv_dmesg_events_normal() -> None:
    """Dmesg AER events output correct fields."""
    ev1 = DmesgAEREvent(
        timestamp="[ 123.456789]",
        bdf="0000:03:00.0",
        severity="Uncorrected (Fatal)",
        error_name="Completion Timeout",
        tlp_header="0x20000000 0x00000000 0x00000000 0x00000000",
        raw_line="pcieport 0000:00:01.0: AER: Multiple Uncorrected (Fatal) error received",
        root_cause_guide="Downstream device stopped responding to memory read requests",
    )
    csv_str = export_pcie_csv([], events=[ev1])
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    row = rows[1]
    assert row[0] == "AER Event"
    assert row[1] == "0000:03:00.0"
    assert row[2] == "[ 123.456789]"
    assert row[3] == "Completion Timeout"
    assert row[4] == "Uncorrected (Fatal)"
    assert "Downstream device stopped responding" in row[8]


def test_export_pcie_csv_special_characters() -> None:
    """PCIe export handles Chinese class names, quotes, and commas."""
    cfg = PCIeConfigSpace(
        raw_data=b"",
        bdf="00:1f.3",
        vendor_id=0x8086,
        device_id=0x7A50,
        class_name="音訊/音效控制器（Audio device, HD Audio）",
        header_type=HeaderType.TYPE_0_ENDPOINT,
        data_quality_issues=['警告：暫存器 "0x40" 包含未定義值, 可能為非標準延伸'],
    )
    csv_str = export_pcie_csv([cfg])
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    assert "音訊/音效控制器" in rows[1][4]
    assert '警告：暫存器 "0x40" 包含未定義值, 可能為非標準延伸' in rows[1][9]


# ==============================================================================
# MCTP / IPMB CSV Export Tests (4 tests)
# ==============================================================================


def test_export_mctp_csv_empty() -> None:
    """Empty ServerMgmtReport outputs header only."""
    report = ServerMgmtReport()
    csv_str = export_mctp_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 1
    header = rows[0]
    assert "Index" in header
    assert "Protocol" in header
    assert "Source / Requester" in header
    assert "Destination / Responder" in header
    assert "Type / NetFn" in header
    assert "Payload / Data Hex" in header


def test_export_mctp_csv_mctp_packets_normal() -> None:
    """MCTP packets output correct fields and formatting."""
    pkt1 = MCTPPacket(
        dest_eid=0x0A,
        src_eid=0x14,
        som=True,
        eom=True,
        pkt_seq=0,
        to=True,
        msg_tag=1,
        msg_type=0x01,
        msg_type_name="PLDM",
        payload=[0x80, 0x02, 0x01],
        payload_hex="80 02 01",
        summary="PLDM GetTID Request",
        pldm_command="GetTID (0x01)",
    )
    report = ServerMgmtReport(mctp_packets=[pkt1], total_frames=1)
    csv_str = export_mctp_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    row = rows[1]
    assert row[0] == "1"
    assert row[1] == "MCTP"
    assert "0x14" in row[2]
    assert "0x0A" in row[3]
    assert "PLDM" in row[4]
    assert "GetTID" in row[5]
    assert "SOM=1, EOM=1" in row[6]
    assert row[7] == "80 02 01"
    assert row[9] == "PLDM GetTID Request"


def test_export_mctp_csv_ipmb_frames_normal() -> None:
    """IPMB frames output correct NetFn, Cmd, checksum and data."""
    frame1 = IPMBFrame(
        rs_addr=0x20,
        netfn=0x06,
        netfn_name="App",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x81,
        rq_seq=5,
        rq_lun=0,
        cmd=0x01,
        cmd_name="Get Device ID",
        data=[0x00, 0x20, 0x01],
        checksum2_valid=True,
        summary="Get Device ID Response: OK",
    )
    report = ServerMgmtReport(ipmb_frames=[frame1], total_frames=1)
    csv_str = export_mctp_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    row = rows[1]
    assert row[0] == "1"
    assert row[1] == "IPMB"
    assert row[2] == "0x81"
    assert row[3] == "0x20"
    assert "App" in row[4]
    assert "Get Device ID" in row[5]
    assert "00 20 01" in row[7]
    assert "CS1=OK, CS2=OK" in row[8]


def test_export_mctp_csv_special_characters() -> None:
    """MCTP/IPMB export properly escapes Chinese annotations and quotes."""
    pkt = MCTPPacket(
        dest_eid=0x08,
        src_eid=0x0A,
        som=True,
        eom=False,
        pkt_seq=1,
        to=False,
        msg_tag=0,
        msg_type=0x00,
        msg_type_name="MCTP Control",
        payload=[0x01, 0x02],
        payload_hex="01 02",
        summary='控制訊息回應：狀態="正常", 包含附加說明與逗號',
    )
    report = ServerMgmtReport(mctp_packets=[pkt], total_frames=1)
    csv_str = export_mctp_csv(report)
    rows = _read_csv(csv_str)
    assert len(rows) == 2
    assert '控制訊息回應：狀態="正常", 包含附加說明與逗號' in rows[1][9]
