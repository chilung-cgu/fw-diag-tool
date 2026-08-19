from .models import DmesgAEREvent, HeaderType, PCIeConfigSpace


class PCIeReporter:
    @staticmethod
    def to_markdown(cfg: PCIeConfigSpace) -> str:
        lines: list[str] = []
        bdf_str = cfg.bdf or "N/A"
        lines.append(f"# PCIe Diagnostic Report (BDF: {bdf_str})\n")
        lines.append("## 1. Device Identification & Base Configuration")
        lines.append(f"- **Vendor ID / Device ID**: `0x{cfg.vendor_id:04X}` / `0x{cfg.device_id:04X}`")
        lines.append(f"- **Class Code**: `0x{cfg.base_class:02X}{cfg.sub_class:02X}{cfg.prog_if:02X}` ({cfg.class_name})")
        lines.append(f"- **Revision ID**: `0x{cfg.revision_id:02X}`")
        lines.append(f"- **Header Type**: `{cfg.header_type.name}` (Multi-Function: `{cfg.is_multi_function}`)")
        lines.append(f"- **Command Register**: `0x{cfg.command:04X}` (MSE: `{bool(cfg.command & 0x02)}`, BME: `{bool(cfg.command & 0x04)}`, IOSE: `{bool(cfg.command & 0x01)}`)")
        lines.append(f"- **Status Register**: `0x{cfg.status:04X}` (CapList: `{bool(cfg.status & 0x10)}`, MasterDataParity: `{bool(cfg.status & 0x8000)}`)")
        lines.append("")
        if cfg.header_type == HeaderType.TYPE_0_ENDPOINT:
            lines.append("## 2. Base Address Registers (BAR 0 - 5)")
            lines.append("| BAR Index | Type | 64-bit | Prefetchable | Base Address | Raw Hex |")
            lines.append("|---|---|---|---|---|---|")
            for bar in cfg.bars:
                type_str = "I/O Space" if bar.is_io else "Memory Space"
                lines.append(f"| BAR{bar.index} | {type_str} | {bar.is_64bit} | {bar.is_prefetchable} | `0x{bar.base_address:016X}` | `0x{bar.raw_value:08X}` |")
            lines.append("")
        elif cfg.header_type == HeaderType.TYPE_1_BRIDGE and cfg.bridge_bus:
            b = cfg.bridge_bus
            lines.append("## 2. Type 1 PCI-to-PCI Bridge Configuration")
            lines.append(f"- **Primary / Secondary / Subordinate Bus**: `{b.primary_bus}` / `{b.secondary_bus}` / `{b.subordinate_bus}`")
            lines.append(f"- **Memory Window**: `0x{b.mem_base:08X}` - `0x{b.mem_limit:08X}`")
            lines.append(f"- **Prefetchable Memory Window**: `0x{b.pref_mem_base:08X}` - `0x{b.pref_mem_limit:08X}`")
            lines.append(f"- **I/O Window**: `0x{b.io_base:04X}` - `0x{b.io_limit:04X}`")
            lines.append("")
        lines.append("## 3. Standard PCI Capabilities (0x34 Linked List)")
        if cfg.standard_capabilities:
            lines.append("| Offset | Cap ID | Name | Next Offset | Key Parameters |")
            lines.append("|---|---|---|---|---|")
            for cap in cfg.standard_capabilities:
                info_summary = ', '.join(f"{k}: {v}" for k, v in cap.decoded_info.items()) or "N/A"
                lines.append(f"| `0x{cap.offset:02X}` | `0x{cap.cap_id:02X}` | {cap.name} | `0x{cap.next_offset:02X}` | {info_summary} |")
        else:
            lines.append("*No Standard Capabilities found.*")
        lines.append("")
        lines.append("## 4. PCI Express Extended Capabilities (0x100 Linked List)")
        if cfg.extended_capabilities:
            lines.append("| Offset | Ext Cap ID | Version | Name | Next Offset |")
            lines.append("|---|---|---|---|---|")
            for ext in cfg.extended_capabilities:
                lines.append(f"| `0x{ext.offset:03X}` | `0x{ext.ext_cap_id:04X}` | v{ext.version} | {ext.name} | `0x{ext.next_offset:03X}` |")
        else:
            lines.append("*No Extended Capabilities found.*")
        lines.append("")
        lines.append("## 5. AER (Advanced Error Reporting) In-Depth Analysis")
        if cfg.aer_analysis:
            aer = cfg.aer_analysis
            lines.append(f"- **AER Capability Offset**: `0x{aer.offset:03X}`")
            lines.append(f"- **Uncorrectable Error Status / Mask / Severity**: `0x{aer.uncorr_status_raw:08X}` / `0x{aer.uncorr_mask_raw:08X}` / `0x{aer.uncorr_severity_raw:08X}`")
            lines.append(f"- **Correctable Error Status / Mask**: `0x{aer.corr_status_raw:08X}` / `0x{aer.corr_mask_raw:08X}`")
            lines.append(f"- **Active Uncorrectable Errors**: Fatal: `{aer.active_uncorr_fatal_count}`, Non-Fatal: `{aer.active_uncorr_nonfatal_count}`")
            lines.append(f"- **Active Correctable Errors**: `{aer.active_corr_count}`")
            lines.append("")
            active_uncorr = [e for e in aer.uncorr_errors if e.is_active]
            if active_uncorr:
                lines.append("### Active Uncorrectable Errors & Root Cause Guidance")
                for err in active_uncorr:
                    masked_tag = " (MASKED)" if err.is_masked else ""
                    lines.append(f"#### [{err.severity}] {err.name} (Bit {err.bit_pos}){masked_tag}")
                    if err.root_cause_guide:
                        lines.append(f"```text\n{err.root_cause_guide}\n```")
                lines.append("")
            active_corr = [e for e in aer.corr_errors if e.is_active]
            if active_corr:
                lines.append("### Active Correctable Errors")
                for err in active_corr:
                    masked_tag = " (MASKED)" if err.is_masked else ""
                    lines.append(f"#### {err.name} (Bit {err.bit_pos}){masked_tag}")
                    if err.root_cause_guide:
                        lines.append(f"```text\n{err.root_cause_guide}\n```")
                lines.append("")
            if aer.decoded_tlp:
                tlp = aer.decoded_tlp
                lines.append("### TLP Header Log Decoded (Faulting Transaction)")
                lines.append(f"- **Raw DW[0..3]**: `0x{tlp.raw_dw[0]:08X}` `0x{tlp.raw_dw[1]:08X}` `0x{tlp.raw_dw[2]:08X}` `0x{tlp.raw_dw[3]:08X}`")
                lines.append(f"- **TLP Packet Type**: `{tlp.type_name}` (Fmt: `0x{tlp.fmt:X}`, Type: `0x{tlp.type_:02X}`)")
                lines.append(f"- **Length**: `{tlp.length}` DW ({tlp.length * 4} Bytes)")
                lines.append(f"- **Traffic Class (TC)**: `{tlp.tc}`, **Digest (TD)**: `{tlp.td}`, **Poisoned (EP)**: `{tlp.ep}`")
                if tlp.requester_id is not None:
                    req_b = (tlp.requester_id >> 8) & 0xFF
                    req_df = tlp.requester_id & 0xFF
                    lines.append(f"- **Requester ID**: `0x{tlp.requester_id:04X}` (Bus:{req_b:02X}, Dev:{req_df>>3:02X}, Func:{req_df&0x7:X}), **Tag**: `0x{tlp.tag:02X}`")
                if tlp.address is not None:
                    lines.append(f"- **Target Address**: `0x{tlp.address:016X}`")
                if tlp.completer_id is not None:
                    lines.append(f"- **Completer ID**: `0x{tlp.completer_id:04X}`, **Completion Status**: `{tlp.completion_status}`")
                lines.append("")
        else:
            lines.append("*AER Extended Capability not detected in Configuration Space.*\n")
        return "\n".join(lines)

    @staticmethod
    def format_dmesg_events(events: list[DmesgAEREvent]) -> str:
        if not events:
            return "No PCIe AER error events found in dmesg log."
        lines = ["# Linux Kernel dmesg AER Diagnostic Report\n"]
        for idx, ev in enumerate(events, 1):
            ts_str = f"[{ev.timestamp}] " if ev.timestamp else ""
            lines.append(f"## Event {idx}: {ts_str}Device {ev.bdf} - {ev.error_name} ({ev.severity})")
            lines.append(f"- **Raw Log**: `{ev.raw_line}`")
            if ev.tlp_header:
                lines.append(f"- **Captured TLP Header**: `{ev.tlp_header}`")
            lines.append(f"\n```text\n{ev.root_cause_guide}\n```\n")
        return "\n".join(lines)