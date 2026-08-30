"""Cross-protocol CSV data export module for firmware diagnostic tool.

Exports structured diagnostic records (I2C, SPI, UART, PCIe, MCTP/IPMB)
to Excel-compatible CSV format with UTF-8 BOM encoding.
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fw_diag_tool.i2c.models import I2CTransaction
    from fw_diag_tool.mctp.models import ServerMgmtReport
    from fw_diag_tool.pcie.models import DmesgAEREvent, PCIeConfigSpace
    from fw_diag_tool.spi.models import SPIReport
    from fw_diag_tool.uart.models import UARTReport

UTF8_BOM = "\ufeff"


def _create_csv_writer() -> tuple[io.StringIO, Any]:
    """Create a StringIO buffer with UTF-8 BOM and a standard csv.writer."""
    buf = io.StringIO()
    buf.write(UTF8_BOM)
    writer = csv.writer(buf, dialect="excel")
    return buf, writer


def export_i2c_csv(transactions: list[I2CTransaction]) -> str:
    """Export I2C transactions to CSV format (one row per transaction)."""
    buf, writer = _create_csv_writer()
    header = [
        "ID",
        "Start Time (s)",
        "End Time (s)",
        "Duration (us)",
        "Address 7-bit",
        "Address 8-bit",
        "Direction",
        "Address ACK",
        "Status",
        "Data Hex",
        "Byte Count",
        "Device Name",
        "Protocol",
        "Command Code",
        "Command Name",
        "Semantic Summary",
        "Anomalies",
    ]
    writer.writerow(header)

    from fw_diag_tool.i2c.models import I2CDirection

    for tx in transactions:
        row = [
            str(tx.id),
            f"{tx.start_time:.6f}" if tx.timestamp_available else "",
            f"{tx.end_time:.6f}" if tx.timestamp_available else "",
            f"{tx.duration_us:.2f}",
            f"0x{tx.address_7bit:02X}" if tx.address_available else "",
            f"0x{tx.address_8bit:02X}" if tx.address_available else "",
            tx.direction.value
            if (tx.direction_available and isinstance(tx.direction, I2CDirection))
            else str(tx.direction or ""),
            tx.address_ack.value
            if hasattr(tx.address_ack, "value")
            else str(tx.address_ack or ""),
            tx.status,
            tx.hex_dump,
            str(len(tx.data_bytes)),
            tx.device_name or "",
            tx.protocol or "",
            f"0x{tx.command_code:02X}" if tx.command_code is not None else "",
            tx.command_name or "",
            tx.semantic_summary or "",
            "; ".join(tx.anomalies) if tx.anomalies else "",
        ]
        writer.writerow(row)

    return buf.getvalue()


def export_spi_csv(report: SPIReport) -> str:
    """Export SPI commands to CSV format (one row per command/transaction)."""
    buf, writer = _create_csv_writer()
    header = [
        "Index",
        "Start Time (s)",
        "End Time (s)",
        "Duration (us)",
        "Opcode",
        "Opcode Name",
        "Address",
        "Payload Length",
        "MOSI Hex",
        "MISO Hex",
        "WEL Before",
        "BUSY After",
        "Decoded Details",
    ]
    writer.writerow(header)

    for tx in report.transactions:
        mosi_str = (
            "[" + ", ".join(f"0x{b:02X}" for b in tx.mosi_bytes) + "]"
            if tx.mosi_bytes
            else "[]"
        )
        miso_str = (
            "[" + ", ".join(f"0x{b:02X}" for b in tx.miso_bytes) + "]"
            if tx.miso_bytes
            else "[]"
        )
        details_str = (
            json.dumps(tx.decoded_details, ensure_ascii=False)
            if tx.decoded_details
            else ""
        )
        row = [
            str(tx.index),
            f"{tx.start_time:.6f}",
            f"{tx.end_time:.6f}",
            f"{tx.duration_us:.2f}",
            f"0x{tx.opcode:02X}" if tx.opcode is not None else "",
            tx.opcode_name,
            f"0x{tx.address:06X}" if tx.address is not None else "",
            str(tx.data_payload_len),
            mosi_str,
            miso_str,
            str(tx.wel_state_before) if tx.wel_state_before is not None else "",
            str(tx.busy_state_after) if tx.busy_state_after is not None else "",
            details_str,
        ]
        writer.writerow(row)

    return buf.getvalue()


def export_uart_csv(report: UARTReport) -> str:
    """Export UART crash dump or trace log to CSV format (one row per frame or entry)."""
    buf, writer = _create_csv_writer()
    header = [
        "Index",
        "Category",
        "Item / Function",
        "Offset / Register",
        "Module / Flag",
        "Address / Value",
        "Details / Raw Line",
    ]
    writer.writerow(header)

    if report.kernel_panic is not None:
        kp = report.kernel_panic
        if kp.call_trace:
            for frame in kp.call_trace:
                writer.writerow(
                    [
                        str(frame.index),
                        "Call Trace",
                        frame.function_name,
                        frame.offset,
                        frame.module or "",
                        frame.address or "",
                        frame.raw_line,
                    ]
                )
        if kp.registers:
            for reg, val in kp.registers.items():
                writer.writerow(["", "Register", reg, "", "", str(val), ""])
        if not kp.call_trace and not kp.registers:
            writer.writerow(
                [
                    "0",
                    "Kernel Panic",
                    kp.faulting_func or "",
                    "",
                    kp.architecture,
                    kp.faulting_ip or kp.faulting_address or "",
                    kp.panic_reason,
                ]
            )

    elif report.arm_hardfault is not None:
        hf = report.arm_hardfault
        for idx, flag in enumerate(hf.fault_flags, 1):
            writer.writerow(
                [str(idx), "HardFault Flag", flag, "", "", "", "Active HardFault flag"]
            )
        if hf.pc_faulting is not None:
            writer.writerow(
                [
                    "",
                    "Register",
                    "PC (Faulting)",
                    "",
                    "",
                    f"0x{hf.pc_faulting:08X}",
                    hf.symbolicated_pc or "",
                ]
            )
        if hf.lr_exc_return is not None:
            writer.writerow(
                [
                    "",
                    "Register",
                    "LR",
                    "",
                    "",
                    f"0x{hf.lr_exc_return:08X}",
                    hf.symbolicated_lr or "",
                ]
            )
        for r_name, r_val in [
            ("R0", hf.r0),
            ("R1", hf.r1),
            ("R2", hf.r2),
            ("R3", hf.r3),
            ("R12", hf.r12),
            ("XPSR", hf.xpsr),
            ("HFSR", hf.hfsr_raw),
            ("CFSR", hf.cfsr_raw),
            ("BFAR", hf.bfar_raw),
            ("MMFAR", hf.mmfar_raw),
        ]:
            if r_val is not None and r_val != 0:
                writer.writerow(["", "Register", r_name, "", "", f"0x{r_val:08X}", ""])
        if not hf.fault_flags and hf.pc_faulting is None:
            writer.writerow(
                [
                    "0",
                    "ARM HardFault",
                    "HardFault",
                    "",
                    "",
                    "",
                    hf.root_cause_analysis or "ARM Cortex-M HardFault",
                ]
            )

    else:
        if report.summary_title or report.raw_log_lines > 0:
            writer.writerow(
                [
                    "1",
                    "Log Summary",
                    report.crash_type.value
                    if hasattr(report.crash_type, "value")
                    else str(report.crash_type),
                    "",
                    "",
                    "",
                    report.summary_title,
                ]
            )

    return buf.getvalue()


def export_pcie_csv(
    configs: list[PCIeConfigSpace],
    events: list[DmesgAEREvent] | None = None,
) -> str:
    """Export PCIe config spaces and/or dmesg AER events to CSV format."""
    buf, writer = _create_csv_writer()
    header = [
        "Record Type",
        "BDF",
        "Vendor / Timestamp",
        "Device / Error Name",
        "Class / Severity",
        "Header Type / TLP Header",
        "Link Speed / Width",
        "Link Degraded",
        "AER Errors / Guidance",
        "Details / Raw Line",
    ]
    writer.writerow(header)

    for cfg in configs:
        link_speed_width = (
            f"{cfg.link_info.current_speed_str} x{cfg.link_info.current_width}"
            if cfg.link_info
            else ""
        )
        link_degraded = (
            f"Yes: {cfg.link_info.degradation_reason}"
            if (cfg.link_info and cfg.link_info.is_degraded)
            else ("No" if cfg.link_info else "")
        )
        aer_errs_str = ""
        if cfg.aer_analysis:
            active_errors = [
                e.name for e in cfg.aer_analysis.uncorr_errors if e.is_active
            ] + [e.name for e in cfg.aer_analysis.corr_errors if e.is_active]
            aer_errs_str = "; ".join(active_errors)

        row = [
            "Config Space",
            cfg.bdf or "",
            f"0x{cfg.vendor_id:04X}",
            f"0x{cfg.device_id:04X}",
            cfg.class_name,
            cfg.header_type.name
            if hasattr(cfg.header_type, "name")
            else str(cfg.header_type),
            link_speed_width,
            link_degraded,
            aer_errs_str,
            "; ".join(cfg.data_quality_issues) if cfg.data_quality_issues else "",
        ]
        writer.writerow(row)

    for ev in events or []:
        row = [
            "AER Event",
            ev.bdf,
            ev.timestamp or "",
            ev.error_name,
            ev.severity,
            ev.tlp_header or "",
            "",
            "",
            ev.root_cause_guide or "",
            ev.raw_line,
        ]
        writer.writerow(row)

    return buf.getvalue()


def export_mctp_csv(report: ServerMgmtReport) -> str:
    """Export MCTP packets and IPMB frames to CSV format."""
    buf, writer = _create_csv_writer()
    header = [
        "Index",
        "Protocol",
        "Source / Requester",
        "Destination / Responder",
        "Type / NetFn",
        "Command / Tag",
        "Control / Flags",
        "Payload / Data Hex",
        "Checksum / Status",
        "Summary",
    ]
    writer.writerow(header)

    for idx, pkt in enumerate(report.mctp_packets, 1):
        payload_hex = pkt.payload_hex or " ".join(f"{b:02X}" for b in pkt.payload)
        row = [
            str(idx),
            "MCTP",
            f"0x{pkt.src_eid:02X} ({pkt.src_eid})",
            f"0x{pkt.dest_eid:02X} ({pkt.dest_eid})",
            f"0x{pkt.msg_type:02X} ({pkt.msg_type_name})",
            pkt.pldm_command or f"Tag {pkt.msg_tag}",
            f"SOM={int(pkt.som)}, EOM={int(pkt.eom)}, Seq={pkt.pkt_seq}, TO={int(pkt.to)}",
            payload_hex,
            "Valid",
            pkt.summary,
        ]
        writer.writerow(row)

    start_idx = len(report.mctp_packets) + 1
    for offset, f in enumerate(report.ipmb_frames):
        idx = start_idx + offset
        data_hex = (
            " ".join(f"{b:02X}" for b in f.data)
            if f.data
            else (f.summary if not f.summary.startswith("IPMB") else "")
        )
        cs_status = (
            f"CS1={'OK' if f.checksum1_valid else 'FAIL'}, "
            f"CS2={'OK' if f.checksum2_valid else 'FAIL'}"
        )
        row = [
            str(idx),
            "IPMB",
            f"0x{f.rq_addr:02X}",
            f"0x{f.rs_addr:02X}",
            f"0x{f.netfn:02X} ({f.netfn_name})",
            f"0x{f.cmd:02X} ({f.cmd_name})",
            f"Seq={f.rq_seq}, LUN={f.rs_lun}/{f.rq_lun}",
            data_hex,
            cs_status,
            f.summary,
        ]
        writer.writerow(row)

    return buf.getvalue()


__all__ = [
    "export_i2c_csv",
    "export_mctp_csv",
    "export_pcie_csv",
    "export_spi_csv",
    "export_uart_csv",
]
