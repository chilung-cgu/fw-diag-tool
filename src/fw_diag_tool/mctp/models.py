from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCTPPacket:
    dest_eid: int
    src_eid: int
    som: bool  # Start of Message
    eom: bool  # End of Message
    pkt_seq: int
    to: bool  # Tag Owner
    msg_tag: int
    msg_type: int
    msg_type_name: str
    payload: list[int] = field(default_factory=list)
    payload_hex: str = ""
    summary: str = ""
    pldm_command: str | None = None


@dataclass
class IPMBFrame:
    rs_addr: int
    netfn: int
    netfn_name: str
    rs_lun: int
    checksum1_valid: bool
    rq_addr: int
    rq_seq: int
    rq_lun: int
    cmd: int
    cmd_name: str
    data: list[int] = field(default_factory=list)
    checksum2_valid: bool = True
    summary: str = ""


@dataclass
class ServerMgmtReport:
    mctp_packets: list[MCTPPacket] = field(default_factory=list)
    ipmb_frames: list[IPMBFrame] = field(default_factory=list)
    total_frames: int = 0
    summary_text: str = ""