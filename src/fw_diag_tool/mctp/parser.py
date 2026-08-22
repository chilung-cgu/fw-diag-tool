from __future__ import annotations

import re

from .models import IPMBFrame, MCTPPacket, ServerMgmtReport

MCTP_MSG_TYPES = {
    0x00: "MCTP Control Message (DSP0236)",
    0x01: "PLDM (Platform Level Data Model, DSP0240)",
    0x02: "NC-SI over MCTP (DSP0222)",
    0x03: "Ethernet over MCTP (DSP0261)",
    0x04: "NVMe-MI over MCTP (NVM Express)",
    0x05: "SPDM (Security Protocol and Data Model, DSP0274)",
    0x7E: "VDPCI (Vendor-Defined PCI, DSP0236)",
    0x7F: "VDIANA (Vendor-Defined IANA, DSP0236)",
}

PLDM_TYPES = {
    0x00: "Base",
    0x01: "SMBIOS",
    0x02: "Platform Monitoring & Control (Sensors)",
    0x03: "BIOS Control & Configuration",
    0x04: "FRU Data",
    0x05: "Firmware Update (DSP0267)",
    0x06: "Redfish Device Enablement",
}

IPMB_NETFNS = {
    0x00: "Chassis",
    0x02: "Bridge",
    0x04: "Sensor / Event",
    0x06: "App",
    0x08: "Firmware",
    0x0A: "Storage",
    0x2C: "Group Extension",
    0x30: "OEM / Board Management",
}

IPMB_COMMANDS = {
    (0x06, 0x01): "Get Device ID",
    (0x06, 0x02): "Cold Reset",
    (0x06, 0x04): "Get Self Test Results",
    (0x06, 0x24): "Set Event Receiver",
    (0x04, 0x2D): "Get Sensor Reading",
    (0x04, 0x20): "Get Sensor Reading Factors",
    (0x0A, 0x10): "Get FRU Inventory Area Info",
    (0x0A, 0x11): "Read FRU Data",
    (0x0A, 0x12): "Write FRU Data",
}


class ServerMgmtParser:
    # Parses MCTP transport packets and IPMB frame hex dumps

    @classmethod
    def parse_hex_tokens(cls, text: str) -> list[int]:
        tokens = re.findall(r"(?:0x)?([0-9a-fA-F]{2})", text)
        return [int(t, 16) for t in tokens]

    @classmethod
    def decode_mctp_packet(cls, raw_bytes: list[int]) -> MCTPPacket | None:
        if len(raw_bytes) < 4:
            return None

        # Check if raw starts with DSP0236 Header Version (0x01)
        if len(raw_bytes) >= 5 and (raw_bytes[0] & 0x0F) == 0x01:
            dest_eid = raw_bytes[1]
            src_eid = raw_bytes[2]
            hdr_flags = raw_bytes[3]
            payload_start = 4
        else:
            dest_eid = raw_bytes[0]
            src_eid = raw_bytes[1]
            hdr_flags = raw_bytes[2]
            payload_start = 3

        som = bool(hdr_flags & (1 << 7))
        eom = bool(hdr_flags & (1 << 6))
        pkt_seq = (hdr_flags >> 4) & 0x03
        to = bool(hdr_flags & (1 << 3))
        msg_tag = hdr_flags & 0x07

        msg_type = 0
        type_name = "Continuation Segment (SOM=0)"
        pldm_info = None

        if som and len(raw_bytes) > payload_start:
            type_byte = raw_bytes[payload_start]
            msg_type = type_byte & 0x7F
            type_name = MCTP_MSG_TYPES.get(msg_type, f"Type 0x{msg_type:02X}")
            payload = raw_bytes[payload_start + 1:]
            # Decode PLDM payload if Type 0x01
            if msg_type == 0x01 and len(payload) >= 3:
                is_rq = bool(payload[0] & 0x80)
                inst_id = payload[0] & 0x1F
                pldm_type = payload[1] & 0x3F
                pldm_cmd = payload[2]
                pldm_t_name = PLDM_TYPES.get(pldm_type, f"Type 0x{pldm_type:02X}")
                rq_str = "Request" if is_rq else "Response"
                pldm_info = f"PLDM {pldm_t_name} {rq_str}: Cmd 0x{pldm_cmd:02X} (Instance {inst_id})"
                if not is_rq and len(payload) >= 4:
                    cc_code = payload[3]
                    pldm_info += f" [CC: 0x{cc_code:02X}]"
        else:
            payload = raw_bytes[payload_start:]

        payload_hex = " ".join(f"{b:02X}" for b in payload)
        summary = f"MCTP: EID 0x{src_eid:02X} -> 0x{dest_eid:02X} [{type_name}] Tag:0x{msg_tag:X}"
        if pldm_info:
            summary += f" ({pldm_info})"

        return MCTPPacket(
            dest_eid=dest_eid,
            src_eid=src_eid,
            som=som,
            eom=eom,
            pkt_seq=pkt_seq,
            to=to,
            msg_tag=msg_tag,
            msg_type=msg_type,
            msg_type_name=type_name,
            payload=payload,
            payload_hex=payload_hex,
            summary=summary,
            pldm_command=pldm_info
        )

    @classmethod
    def decode_ipmb_frame(cls, raw_bytes: list[int]) -> IPMBFrame | None:
        if len(raw_bytes) < 7:
            return None
        rs_addr = raw_bytes[0]
        netfn_raw = raw_bytes[1]
        netfn = netfn_raw >> 2
        rs_lun = netfn_raw & 0x03
        chk1 = raw_bytes[2]
        chk1_valid = ((rs_addr + netfn_raw + chk1) & 0xFF) == 0

        rq_addr = raw_bytes[3]
        rq_seq_raw = raw_bytes[4]
        rq_seq = rq_seq_raw >> 2
        rq_lun = rq_seq_raw & 0x03
        cmd = raw_bytes[5]
        data = raw_bytes[6:-1] if len(raw_bytes) > 7 else []
        chk2 = raw_bytes[-1]
        chk2_valid = ((sum(raw_bytes[3:-1]) + chk2) & 0xFF) == 0

        # Support both Request (even NetFn) and Response (odd NetFn = Request + 1)
        is_response = bool(netfn & 0x01)
        base_netfn = netfn & ~0x01
        base_netfn_name = IPMB_NETFNS.get(base_netfn, f"NetFn 0x{netfn:02X}")
        netfn_name = base_netfn_name + (" (Response)" if is_response else " (Request)")
        cmd_name = IPMB_COMMANDS.get((base_netfn, cmd), f"Cmd 0x{cmd:02X}")

        summary = f"IPMB: 0x{rq_addr:02X} -> 0x{rs_addr:02X} [{netfn_name}: {cmd_name}]"
        if is_response and data:
            summary += f" [CC: 0x{data[0]:02X}]"

        return IPMBFrame(
            rs_addr=rs_addr,
            netfn=netfn,
            netfn_name=netfn_name,
            rs_lun=rs_lun,
            checksum1_valid=chk1_valid,
            rq_addr=rq_addr,
            rq_seq=rq_seq,
            rq_lun=rq_lun,
            cmd=cmd,
            cmd_name=cmd_name,
            data=data,
            checksum2_valid=chk2_valid,
            summary=summary
        )

    @classmethod
    def parse_text_dump(cls, text: str) -> ServerMgmtReport:
        lines = text.strip().splitlines()
        mctp_list = []
        ipmb_list = []

        for line in lines:
            raw = cls.parse_hex_tokens(line)
            if len(raw) < 4:
                continue
            # Check if this line is an IPMB frame
            # IPMB frames have length >= 7 and valid checksum 1 or IPMB slave address (0x20, 0x81, etc.)
            chk1_calc = ((raw[0] + raw[1] + raw[2]) & 0xFF) == 0 if len(raw) >= 3 else False
            chk2_calc = ((sum(raw[3:-1]) + raw[-1]) & 0xFF) == 0 if len(raw) >= 7 else False
            is_ipmb_candidate = len(raw) >= 7 and (
                chk1_calc
                or chk2_calc
                or (raw[0] in (0x20, 0x81, 0x2C, 0x82, 0x24, 0x28, 0x2E, 0x30, 0x40))
                or (raw[0] % 2 == 0 and raw[3] % 2 == 0 and raw[0] != 0x01)
            )
            if is_ipmb_candidate:
                ipmb = cls.decode_ipmb_frame(raw)
                if ipmb:
                    ipmb_list.append(ipmb)
                    continue

            mctp = cls.decode_mctp_packet(raw)
            if mctp:
                mctp_list.append(mctp)

        summary_str = f"Decoded {len(mctp_list)} MCTP packet(s) and {len(ipmb_list)} IPMB frame(s). "
        return ServerMgmtReport(
            mctp_packets=mctp_list,
            ipmb_frames=ipmb_list,
            total_frames=len(mctp_list) + len(ipmb_list),
            summary_text=summary_str
        )
