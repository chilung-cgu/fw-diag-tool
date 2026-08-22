from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter


def test_mctp_pldm_decoding():
    # MCTP PLDM packet: Dest=0x08, Src=0x00, SOM/EOM/Seq0=0xC0, MsgType=0x01 (PLDM), Payload=[0x00, 0x02, 0x01, 0x00] (PLDM Platform Monitoring)
    hex_dump = "08 00 C0 01 00 02 01 00"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.mctp_packets) == 1
    pkt = report.mctp_packets[0]
    assert pkt.dest_eid == 0x08
    assert pkt.src_eid == 0x00
    assert pkt.som is True and pkt.eom is True
    assert "PLDM" in pkt.msg_type_name
    assert "Platform Monitoring" in (pkt.pldm_command or "")
    md = ServerMgmtReporter.to_markdown(report)
    assert "MCTP Packets" in md

def test_ipmb_frame_decoding():
    # IPMB: rsSA=0x20, NetFn=0x06 (App), Chk1=0xD8, rqSA=0x81, rqSeq=0x20, Cmd=0x01 (Get Device ID), Chk2=0x5E
    # (0x20 + 0x18 + 0xC8 = 0x200 -> 0x00 mod 256)
    hex_dump = "20 18 C8 81 20 01 5E"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.ipmb_frames) == 1
    frame = report.ipmb_frames[0]
    assert frame.rs_addr == 0x20
    assert frame.netfn == 0x06
    assert frame.cmd == 0x01
    assert frame.cmd_name == "Get Device ID"
    assert frame.checksum1_valid is True