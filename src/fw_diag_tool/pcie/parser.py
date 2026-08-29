import re
import struct
from typing import Any

from .constants import (
    AER_CORR_BITS,
    AER_UNCORR_BITS,
    PCI_BASE_CLASSES,
    PCI_CAP_ID_EXP,
    PCI_CAP_ID_MSI,
    PCI_CAP_ID_MSIX,
    PCI_CAP_NAMES,
    PCI_EXT_CAP_ID_AER,
    PCI_EXT_CAP_NAMES,
)
from .diagnostics import get_root_cause_guide
from .models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    BARInfo,
    BridgeBusInfo,
    DmesgAEREvent,
    ExtendedCapability,
    HeaderType,
    PCIeConfigSpace,
    StandardCapability,
    TLPHeaderDecoded,
)


class PCIeAnalyzer:
    @classmethod
    def parse_multi_lspci_text(cls, text: str) -> list[PCIeConfigSpace]:
        chunks: list[str] = []
        current_lines: list[str] = []
        bdf_pattern = re.compile(r"^[0-9a-fA-F]{2,4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]")
        for line in text.splitlines():
            if bdf_pattern.match(line.strip()) and current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
            current_lines.append(line)
        if current_lines:
            chunks.append("\n".join(current_lines))
        decoded_results: list[PCIeConfigSpace] = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            try:
                bdf, raw_bytes = cls.parse_lspci_text(chunk)
                cfg = cls.decode_config_space(raw_bytes, bdf=bdf)
                decoded_results.append(cfg)
            except Exception as exc:
                bdf_label = bdf_pattern.search(chunk)
                label = bdf_label.group(0).strip() if bdf_label else chunk.splitlines()[0].strip()
                failed_cfg = PCIeConfigSpace(raw_data=b"", bdf=label or None)
                failed_cfg.data_quality_issues.append(
                    f"Device dump could not be decoded: {exc} "
                    "The source bytes were not interpreted as a clean config space."
                )
                decoded_results.append(failed_cfg)
        return decoded_results

    @staticmethod
    def parse_raw_hex(hex_input: str | bytes) -> bytes:
        if isinstance(hex_input, bytes):
            return hex_input
        text = hex_input.strip()
        lines = text.splitlines()
        byte_values: list[int] = []
        offset_rows: list[tuple[int, list[int]]] = []

        # Check if lines have offset patterns like "00: ..." or "0000:01:00.0 ..."
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # If line is header like "0000:01:00.0 ...", skip it
            if re.match(r"^[0-9a-fA-F]{2,4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", line):
                continue
            # Match offset like "00:" or "100:" or "0000:"
            m = re.match(r"^[0-9a-fA-F]{2,8}:\s*(.*)$", line)
            if m:
                rest = m.group(1)
                tokens = re.findall(r"\b[0-9a-fA-F]{2}\b", rest)
                offset = int(line[: line.index(":")], 16)
                offset_rows.append((offset, [int(t, 16) for t in tokens]))
            else:
                tokens = re.findall(r"\b[0-9a-fA-F]{2}\b", line)
                for t in tokens:
                    byte_values.append(int(t, 16))

        if offset_rows:
            positioned_data = bytearray()
            for offset, row_bytes in offset_rows:
                end = offset + len(row_bytes)
                if end > len(positioned_data):
                    positioned_data.extend(bytes(end - len(positioned_data)))
                positioned_data[offset:end] = bytes(row_bytes)
            has_config_start = any(offset == 0 and row_bytes for offset, row_bytes in offset_rows)
            if has_config_start and len(positioned_data) >= 64:
                return bytes(positioned_data)

        if len(byte_values) >= 64:
            return bytes(byte_values)
        if not offset_rows:
            all_tokens = re.findall(r"\b[0-9a-fA-F]{2}\b", text)
            if len(all_tokens) >= 64:
                return bytes([int(t, 16) for t in all_tokens])
        raise ValueError(
            "Invalid hex input: cannot extract at least 64 bytes of PCI configuration space."
        )

    @staticmethod
    def parse_lspci_text(lspci_text: str) -> tuple[str | None, bytes]:
        bdf_match = re.search(
            r"([0-9a-fA-F]{2,4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7])", lspci_text
        )
        bdf = bdf_match.group(1) if bdf_match else None
        data = PCIeAnalyzer.parse_raw_hex(lspci_text)
        return bdf, data

    @classmethod
    def decode_config_space(cls, raw_data: bytes, bdf: str | None = None) -> PCIeConfigSpace:
        if not isinstance(raw_data, (bytes, bytearray)):
            raise TypeError("PCIe config space must be bytes-like")
        source_length = len(raw_data)
        if len(raw_data) < 64:
            raise ValueError(
                f"Config space size {len(raw_data)} bytes is smaller than minimum 64 bytes."
            )
        if len(raw_data) < 4096:
            raw_data = raw_data + bytes(4096 - len(raw_data))

        vendor_id, device_id, command, status, rev_id, prog_if, sub_class, base_class = (
            struct.unpack_from("<HHHHBBBB", raw_data, 0x00)
        )
        cache_line, latency_timer, header_type_raw, bist = struct.unpack_from(
            "<BBBB", raw_data, 0x0C
        )
        is_multi_func = bool(header_type_raw & 0x80)
        h_type_val = header_type_raw & 0x7F
        if h_type_val == 0:
            h_type = HeaderType.TYPE_0_ENDPOINT
        elif h_type_val == 1:
            h_type = HeaderType.TYPE_1_BRIDGE
        elif h_type_val == 2:
            h_type = HeaderType.TYPE_2_CARDBUS
        else:
            h_type = HeaderType.UNKNOWN

        class_name = PCI_BASE_CLASSES.get(base_class, f"Unknown Class 0x{base_class:02X}")

        cfg = PCIeConfigSpace(
            raw_data=raw_data,
            bdf=bdf,
            vendor_id=vendor_id,
            device_id=device_id,
            command=command,
            status=status,
            revision_id=rev_id,
            prog_if=prog_if,
            sub_class=sub_class,
            base_class=base_class,
            class_name=class_name,
            cache_line_size=cache_line,
            latency_timer=latency_timer,
            header_type=h_type,
            is_multi_function=is_multi_func,
            bist=bist,
        )

        if h_type == HeaderType.TYPE_0_ENDPOINT:
            bar_idx = 0
            while bar_idx < 6:
                bar_offset = 0x10 + bar_idx * 4
                raw_bar = struct.unpack_from("<I", raw_data, bar_offset)[0]
                is_io = bool(raw_bar & 0x01)
                if raw_bar == 0:
                    bar_idx += 1
                    continue
                if is_io:
                    base_addr = raw_bar & ~0x03
                    cfg.bars.append(
                        BARInfo(
                            index=bar_idx, raw_value=raw_bar, is_io=True, base_address=base_addr
                        )
                    )
                    bar_idx += 1
                else:
                    is_64bit = ((raw_bar >> 1) & 0x03) == 0x02
                    is_pref = bool(raw_bar & 0x08)
                    if is_64bit and bar_idx < 5:
                        raw_bar_high = struct.unpack_from("<I", raw_data, bar_offset + 4)[0]
                        full_addr = (raw_bar_high << 32) | (raw_bar & ~0x0F)
                        cfg.bars.append(
                            BARInfo(
                                index=bar_idx,
                                raw_value=raw_bar,
                                is_io=False,
                                is_64bit=True,
                                is_prefetchable=is_pref,
                                base_address=full_addr,
                            )
                        )
                        bar_idx += 2
                    else:
                        base_addr = raw_bar & ~0x0F
                        cfg.bars.append(
                            BARInfo(
                                index=bar_idx,
                                raw_value=raw_bar,
                                is_io=False,
                                is_64bit=False,
                                is_prefetchable=is_pref,
                                base_address=base_addr,
                            )
                        )
                        bar_idx += 1

            cfg.subsystem_vendor_id = struct.unpack_from("<H", raw_data, 0x2C)[0]
            cfg.subsystem_device_id = struct.unpack_from("<H", raw_data, 0x2E)[0]
            cfg.expansion_rom_bar = struct.unpack_from("<I", raw_data, 0x30)[0]
            cfg.capabilities_ptr = raw_data[0x34]
            cfg.interrupt_line = raw_data[0x3C]
            cfg.interrupt_pin = raw_data[0x3D]

        elif h_type == HeaderType.TYPE_1_BRIDGE:
            pri_bus, sec_bus, sub_bus, sec_latency = struct.unpack_from("<BBBB", raw_data, 0x18)
            io_base_low, io_limit_low, _sec_status = struct.unpack_from("<BBH", raw_data, 0x1C)
            mem_base_raw, mem_limit_raw = struct.unpack_from("<HH", raw_data, 0x20)
            pref_mem_base_raw, pref_mem_limit_raw = struct.unpack_from("<HH", raw_data, 0x24)

            mem_base = (mem_base_raw & 0xFFF0) << 16
            mem_limit = ((mem_limit_raw & 0xFFF0) << 16) | 0xFFFFF
            pref_mem_base = (pref_mem_base_raw & 0xFFF0) << 16
            pref_mem_limit = ((pref_mem_limit_raw & 0xFFF0) << 16) | 0xFFFFF
            io_base = (io_base_low & 0xF0) << 8
            io_limit = ((io_limit_low & 0xF0) << 8) | 0xFFF

            cfg.bridge_bus = BridgeBusInfo(
                primary_bus=pri_bus,
                secondary_bus=sec_bus,
                subordinate_bus=sub_bus,
                secondary_latency_timer=sec_latency,
                io_base=io_base,
                io_limit=io_limit,
                mem_base=mem_base,
                mem_limit=mem_limit,
                pref_mem_base=pref_mem_base,
                pref_mem_limit=pref_mem_limit,
            )
            cfg.capabilities_ptr = raw_data[0x34]
            cfg.interrupt_line = raw_data[0x3C]
            cfg.interrupt_pin = raw_data[0x3D]

        # Traverse standard capabilities list (offset 0x34)
        if cfg.status & 0x0010:  # Capabilities bit
            ptr = cfg.capabilities_ptr & ~0x03
            visited = set()
            while 0x40 <= ptr <= 0xFC and ptr not in visited:
                visited.add(ptr)
                cap_id = raw_data[ptr]
                next_ptr = raw_data[ptr + 1] & ~0x03
                cap_name = PCI_CAP_NAMES.get(cap_id, f"Unknown Cap (0x{cap_id:02X})")
                decoded_details: dict[str, Any] = {}

                if cap_id == PCI_CAP_ID_EXP:
                    pcie_cap_reg = struct.unpack_from("<H", raw_data, ptr + 2)[0]
                    dev_type = (pcie_cap_reg >> 4) & 0x0F
                    dev_type_names = {
                        0x0: "PCI Express Endpoint",
                        0x1: "Legacy PCI Express Endpoint",
                        0x4: "Root Port of PCI Express Root Complex",
                        0x5: "Upstream Port of PCI Express Switch",
                        0x6: "Downstream Port of PCI Express Switch",
                        0x7: "PCI Express to PCI/PCI-X Bridge",
                        0x8: "PCI/PCI-X to PCI Express Bridge",
                        0x9: "Root Complex Integrated Endpoint",
                        0xA: "Root Complex Event Collector",
                    }
                    decoded_details["device_type"] = dev_type_names.get(
                        dev_type, f"Unknown (0x{dev_type:X})"
                    )
                    decoded_details["cap_version"] = pcie_cap_reg & 0x0F
                    dev_ctl, dev_sta = struct.unpack_from("<HH", raw_data, ptr + 8)
                    decoded_details["dev_ctl"] = dev_ctl
                    decoded_details["dev_sta"] = dev_sta
                    decoded_details["max_payload_size"] = 128 << ((dev_ctl >> 5) & 0x07)
                    decoded_details["max_read_request_size"] = 128 << ((dev_ctl >> 12) & 0x07)

                    link_cap = struct.unpack_from("<I", raw_data, ptr + 12)[0]
                    link_ctl, link_sta = struct.unpack_from("<HH", raw_data, ptr + 16)
                    speed_map = {
                        1: "2.5 GT/s (Gen1)",
                        2: "5.0 GT/s (Gen2)",
                        3: "8.0 GT/s (Gen3)",
                        4: "16.0 GT/s (Gen4)",
                        5: "32.0 GT/s (Gen5)",
                        6: "64.0 GT/s (Gen6)",
                    }
                    max_speed_code = link_cap & 0x0F
                    max_width = (link_cap >> 4) & 0x3F
                    curr_speed_code = link_sta & 0x0F
                    curr_width = (link_sta >> 4) & 0x3F

                    max_speed_str = speed_map.get(max_speed_code, f"Unknown ({max_speed_code})")
                    curr_speed_str = speed_map.get(curr_speed_code, f"Unknown ({curr_speed_code})")

                    is_degraded = False
                    degradation_reason = ""
                    guide = ""
                    if (
                        max_speed_code > 0
                        and curr_speed_code > 0
                        and (curr_speed_code < max_speed_code or curr_width < max_width)
                    ):
                        is_degraded = True
                        degradation_reason = (
                            f"PCIe Link Degraded: Operating at {curr_speed_str} x{curr_width} "
                            f"(Max Capable: {max_speed_str} x{max_width})"
                        )
                        guide = (
                            "【PCIe Link 降級排查指引】\n"
                            "1. 檢查 PCIe 插槽金手指是否有髒污、金屬氧化或接觸不良，嘗試重新插拔或清潔插槽。\n"
                            "2. 檢查 Riser 轉接卡與高速差分線路之訊號完整性 (SI Jitter / Loss)。\n"
                            "3. 檢查主機供電 (12V / 3.3V AUX) 是否有瞬間壓降導致 PHY PLL 無法鎖定最高速率。\n"
                            "4. 檢查 BIOS/UEFI PCIe Link Speed 設定是否被手動限制為較低世代 (Gen3/Gen2)。"
                        )

                    from .models import PCIeLinkInfo

                    cfg.link_info = PCIeLinkInfo(
                        max_speed_code=max_speed_code,
                        max_speed_str=max_speed_str,
                        max_width=max_width,
                        current_speed_code=curr_speed_code,
                        current_speed_str=curr_speed_str,
                        current_width=curr_width,
                        is_degraded=is_degraded,
                        degradation_reason=degradation_reason,
                        root_cause_guide=guide,
                    )

                    decoded_details["max_link_speed"] = max_speed_str
                    decoded_details["max_link_width"] = f"x{max_width}"
                    decoded_details["current_link_speed"] = curr_speed_str
                    decoded_details["current_link_width"] = f"x{curr_width}"
                    decoded_details["is_link_degraded"] = is_degraded
                    decoded_details["link_retrain"] = bool(link_ctl & 0x0020)

                elif cap_id == PCI_CAP_ID_MSI:
                    msg_ctrl = struct.unpack_from("<H", raw_data, ptr + 2)[0]
                    decoded_details["is_64bit"] = bool(msg_ctrl & 0x0080)
                    decoded_details["enabled"] = bool(msg_ctrl & 0x0001)
                    decoded_details["multiple_msg_enable"] = 1 << ((msg_ctrl >> 4) & 0x07)
                    decoded_details["multiple_msg_capable"] = 1 << ((msg_ctrl >> 1) & 0x07)

                elif cap_id == PCI_CAP_ID_MSIX:
                    msg_ctrl = struct.unpack_from("<H", raw_data, ptr + 2)[0]
                    decoded_details["enabled"] = bool(msg_ctrl & 0x8000)
                    decoded_details["function_mask"] = bool(msg_ctrl & 0x4000)
                    decoded_details["table_size"] = (msg_ctrl & 0x07FF) + 1

                cap = StandardCapability(
                    cap_id=cap_id,
                    name=cap_name,
                    offset=ptr,
                    next_offset=next_ptr,
                    raw_bytes=raw_data[ptr : ptr + 16],
                    decoded_info=decoded_details,
                )
                cfg.standard_capabilities.append(cap)
                ptr = next_ptr

        # Traverse extended capabilities list (starting at offset 0x100)
        ext_ptr = 0x100
        ext_visited = set()
        while 0x100 <= ext_ptr <= 0xFFC and ext_ptr + 4 <= source_length and ext_ptr not in ext_visited:
            ext_visited.add(ext_ptr)
            header_dw = struct.unpack_from("<I", raw_data, ext_ptr)[0]
            if header_dw == 0 or header_dw == 0xFFFFFFFF:
                break
            ext_cap_id = header_dw & 0xFFFF
            cap_ver = (header_dw >> 16) & 0x0F
            next_ext_ptr = (header_dw >> 20) & 0xFFF
            cap_name = PCI_EXT_CAP_NAMES.get(ext_cap_id, f"Extended Cap 0x{ext_cap_id:04X}")

            decoded_ext: dict[str, Any] = {}
            if ext_cap_id == PCI_EXT_CAP_ID_AER:
                if ext_ptr + 0x2C > source_length:
                    message = (
                        f"AER capability at 0x{ext_ptr:03X} is truncated: "
                        "the 0x2C-byte AER structure is not fully present in the source dump"
                    )
                    cfg.data_quality_issues.append(message)
                    decoded_ext["evidence"] = "truncated"
                    decoded_ext["message"] = message
                else:
                    aer_res = cls.decode_aer(raw_data, ext_ptr)
                    cfg.aer_analysis = aer_res
                    decoded_ext["aer_summary"] = {
                        "active_fatal": aer_res.active_uncorr_fatal_count,
                        "active_nonfatal": aer_res.active_uncorr_nonfatal_count,
                        "active_correctable": aer_res.active_corr_count,
                    }

            ext_cap = ExtendedCapability(
                ext_cap_id=ext_cap_id,
                version=cap_ver,
                name=cap_name,
                offset=ext_ptr,
                next_offset=next_ext_ptr,
                raw_bytes=raw_data[ext_ptr : ext_ptr + 32],
                decoded_info=decoded_ext,
            )
            cfg.extended_capabilities.append(ext_cap)
            if next_ext_ptr < 0x100:
                break
            ext_ptr = next_ext_ptr

        return cfg

    @classmethod
    def decode_tlp_header(cls, dw0: int, dw1: int, dw2: int, dw3: int) -> TLPHeaderDecoded:
        for name, dw in (("dw0", dw0), ("dw1", dw1), ("dw2", dw2), ("dw3", dw3)):
            if isinstance(dw, bool) or not isinstance(dw, int) or not 0 <= dw <= 0xFFFFFFFF:
                raise ValueError(f"{name} must be an unsigned 32-bit integer (0..0xFFFFFFFF)")
        fmt = (dw0 >> 29) & 0x07
        type_ = (dw0 >> 24) & 0x1F
        tc = (dw0 >> 20) & 0x07
        td = bool(dw0 & (1 << 15))
        ep = bool(dw0 & (1 << 14))
        attr = ((dw0 >> 12) & 0x03) | (((dw0 >> 18) & 0x01) << 2)
        length = dw0 & 0x3FF
        if length == 0:
            length = 1024  # 1024 DW in PCIe spec

        is_3dw = (fmt & 0x01) == 0
        is_4dw = (fmt & 0x01) == 1
        has_data = bool(fmt & 0x02)

        fmt_type = (fmt << 5) | type_
        type_names = {
            0b00000000: "MRd (Memory Read 3DW)",
            0b00100000: "MRd (Memory Read 4DW)",
            0b00000001: "MRdLk (Memory Read Lock 3DW)",
            0b00100001: "MRdLk (Memory Read Lock 4DW)",
            0b01000000: "MWr (Memory Write 3DW)",
            0b01100000: "MWr (Memory Write 4DW)",
            0b00000010: "IORd (I/O Read)",
            0b01000010: "IOWr (I/O Write)",
            0b00000100: "CfgRd0 (Config Read Type 0)",
            0b01000100: "CfgWr0 (Config Write Type 0)",
            0b00000101: "CfgRd1 (Config Read Type 1)",
            0b01000101: "CfgWr1 (Config Write Type 1)",
            0b00001010: "Cpl (Completion without Data)",
            0b01001010: "CplD (Completion with Data)",
            0b00001011: "CplLk (Completion Lock without Data)",
            0b01001011: "CplDLk (Completion Lock with Data)",
            0b00110000: "Msg (Message routed to RC)",
            0b01110000: "MsgD (Message with Data routed to RC)",
        }
        type_name = type_names.get(fmt_type, f"TLP Fmt:0x{fmt:X} Type:0x{type_:02X}")

        requester_id = None
        tag = None
        completer_id = None
        completion_status = None
        address = None
        first_dw_be = None
        last_dw_be = None
        byte_count = None
        lower_address = None

        if type_ in (0x00, 0x01, 0x02, 0x0C, 0x0D, 0x0E):  # Memory / IO / AtomicOp Requests
            requester_id = (dw1 >> 16) & 0xFFFF
            tag = (dw1 >> 8) & 0xFF
            last_dw_be = (dw1 >> 4) & 0x0F
            first_dw_be = dw1 & 0x0F
            if is_4dw:
                address = (dw2 << 32) | (dw3 & ~0x03)
            else:
                address = dw2 & ~0x03
        elif type_ in (0x04, 0x05):  # Config Requests
            requester_id = (dw1 >> 16) & 0xFFFF
            tag = (dw1 >> 8) & 0xFF
            last_dw_be = (dw1 >> 4) & 0x0F
            first_dw_be = dw1 & 0x0F
            target_bus = (dw2 >> 24) & 0xFF
            target_dev = (dw2 >> 19) & 0x1F
            target_func = (dw2 >> 16) & 0x07
            ext_reg = (dw2 >> 8) & 0x0F
            reg_num = (dw2 & 0xFC) | (ext_reg << 8)
            address = (target_bus << 20) | (target_dev << 15) | (target_func << 12) | reg_num
        elif type_ in (0x0A, 0x0B):  # Completions
            completer_id = (dw1 >> 16) & 0xFFFF
            completion_status = (dw1 >> 13) & 0x07
            requester_id = (dw2 >> 16) & 0xFFFF
            tag = (dw2 >> 8) & 0xFF
            byte_count = dw1 & 0x0FFF
            lower_address = dw2 & 0x7F

        return TLPHeaderDecoded(
            fmt=fmt,
            type_=type_,
            length=length,
            is_3dw=is_3dw,
            is_4dw=is_4dw,
            has_data=has_data,
            tc=tc,
            td=td,
            ep=ep,
            attr=attr,
            type_name=type_name,
            requester_id=requester_id,
            tag=tag,
            completer_id=completer_id,
            completion_status=completion_status,
            address=address,
            first_dw_be=first_dw_be,
            last_dw_be=last_dw_be,
            byte_count=byte_count,
            lower_address=lower_address,
            raw_dw=[dw0, dw1, dw2, dw3],
        )

    @classmethod
    def decode_aer(cls, raw_data: bytes, aer_offset: int) -> AERAnalysisResult:
        if not isinstance(raw_data, (bytes, bytearray)):
            raise TypeError("PCIe config space must be bytes-like")
        if not isinstance(aer_offset, int) or isinstance(aer_offset, bool) or aer_offset < 0:
            raise ValueError("AER capability offset must be a non-negative integer")
        if aer_offset + 0x2C > len(raw_data):
            raise ValueError(
                f"AER capability at 0x{aer_offset:03X} is truncated; expected at least 0x2C bytes"
            )
        uncorr_status = struct.unpack_from("<I", raw_data, aer_offset + 0x04)[0]
        uncorr_mask = struct.unpack_from("<I", raw_data, aer_offset + 0x08)[0]
        uncorr_severity = struct.unpack_from("<I", raw_data, aer_offset + 0x0C)[0]
        corr_status = struct.unpack_from("<I", raw_data, aer_offset + 0x10)[0]
        corr_mask = struct.unpack_from("<I", raw_data, aer_offset + 0x14)[0]
        cap_ctrl = struct.unpack_from("<I", raw_data, aer_offset + 0x18)[0]
        h_dw0, h_dw1, h_dw2, h_dw3 = struct.unpack_from("<IIII", raw_data, aer_offset + 0x1C)
        header_log = [h_dw0, h_dw1, h_dw2, h_dw3]

        uncorr_errors = []
        fatal_count = 0
        nonfatal_count = 0
        for bit_pos, (name, short_code) in AER_UNCORR_BITS.items():
            is_active = bool(uncorr_status & (1 << bit_pos))
            is_masked = bool(uncorr_mask & (1 << bit_pos))
            is_fatal = bool(uncorr_severity & (1 << bit_pos))
            sev_str = "Fatal" if is_fatal else "Non-Fatal"
            guide = get_root_cause_guide(short_code) if is_active else None

            if is_active and not is_masked:
                if is_fatal:
                    fatal_count += 1
                else:
                    nonfatal_count += 1

            uncorr_errors.append(
                AERUncorrectableError(
                    bit_pos=bit_pos,
                    name=name,
                    short_code=short_code,
                    is_active=is_active,
                    is_masked=is_masked,
                    severity=sev_str,
                    root_cause_guide=guide,
                )
            )

        corr_errors = []
        corr_count = 0
        for bit_pos, (name, short_code) in AER_CORR_BITS.items():
            is_active = bool(corr_status & (1 << bit_pos))
            is_masked = bool(corr_mask & (1 << bit_pos))
            guide = get_root_cause_guide(short_code) if is_active else None

            if is_active and not is_masked:
                corr_count += 1

            corr_errors.append(
                AERCorrectableError(
                    bit_pos=bit_pos,
                    name=name,
                    short_code=short_code,
                    is_active=is_active,
                    is_masked=is_masked,
                    root_cause_guide=guide,
                )
            )

        decoded_tlp = None
        if any(h != 0 for h in header_log):
            decoded_tlp = cls.decode_tlp_header(h_dw0, h_dw1, h_dw2, h_dw3)

        return AERAnalysisResult(
            offset=aer_offset,
            uncorr_status_raw=uncorr_status,
            uncorr_mask_raw=uncorr_mask,
            uncorr_severity_raw=uncorr_severity,
            corr_status_raw=corr_status,
            corr_mask_raw=corr_mask,
            cap_control_raw=cap_ctrl,
            header_log_raw=header_log,
            uncorr_errors=uncorr_errors,
            corr_errors=corr_errors,
            decoded_tlp=decoded_tlp,
            active_uncorr_fatal_count=fatal_count,
            active_uncorr_nonfatal_count=nonfatal_count,
            active_corr_count=corr_count,
        )

    @classmethod
    def parse_dmesg_aer(cls, dmesg_text: str) -> list[DmesgAEREvent]:
        events = []
        lines = dmesg_text.splitlines()

        aer_header_pattern = re.compile(
            r"(?:\[\s*([0-9\.]+)\]\s*)?pcieport\s+([0-9a-fA-F:\.]+):\s+AER:\s+(Correctable|Fatal|Non-Fatal|Uncorrected)\s+error\s+received"
        )
        error_name_pattern = re.compile(
            r"(?:\[\s*([0-9\.]+)\]\s*)?([0-9a-fA-F:\.]+):\s+PCIe\s+Bus\s+Error:\s+severity=([^,]+),\s+type=([^,]+),\s+id=([0-9a-fA-F]+)\(([^)]+)\)"
        )
        sub_err_pattern = re.compile(
            r"(?:\[\s*([0-9\.]+)\]\s*)?(?:pcieport\s+)?([0-9a-fA-F:\.]+):\s+\[\s*\d+\]\s+([A-Za-z0-9_]+)"
        )
        tlp_hdr_pattern = re.compile(
            r"(?:\[\s*([0-9\.]+)\]\s*)?(?:pcieport\s+)?([0-9a-fA-F:\.]+):\s+TLP\s+Header:\s+([0-9a-fA-F\s]+)"
        )

        _current_bdf = "Unknown"
        current_sev = "Uncorrected"
        _current_timestamp = None

        for line in lines:
            m_hdr = aer_header_pattern.search(line)
            if m_hdr:
                _timestamp = m_hdr.group(1)
                _bdf = m_hdr.group(2)
                current_sev = m_hdr.group(3)
                continue

            m_err = error_name_pattern.search(line)
            if m_err:
                ts, bdf, sev, _err_type, _dev_id, err_name = m_err.groups()
                guide = (
                    get_root_cause_guide(err_name) or f"Linux Kernel AER error event: {err_name}"
                )
                events.append(
                    DmesgAEREvent(
                        timestamp=ts,
                        bdf=bdf,
                        severity=sev,
                        error_name=err_name,
                        tlp_header=None,
                        raw_line=line.strip(),
                        root_cause_guide=guide,
                    )
                )
                continue

            m_sub = sub_err_pattern.search(line)
            if m_sub:
                ts, bdf, err_name = m_sub.groups()
                guide = get_root_cause_guide(err_name) or f"Specific error flag: {err_name}"
                events.append(
                    DmesgAEREvent(
                        timestamp=ts,
                        bdf=bdf,
                        severity=current_sev,
                        error_name=err_name,
                        tlp_header=None,
                        raw_line=line.strip(),
                        root_cause_guide=guide,
                    )
                )
                continue

            m_tlp = tlp_hdr_pattern.search(line)
            if m_tlp and events:
                events[-1].tlp_header = m_tlp.group(3).strip()

        return events
