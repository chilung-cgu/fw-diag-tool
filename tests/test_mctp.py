import pytest
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter

def test_mctp_dsp0236_header_version_and_pldm():
    # Standard 4-byte transport header with Header Version 0x01: [0x01, Dest 0x08, Src 0x00, Flags 0xC0, MsgType 0x01 (PLDM)]
    hex_dump = "01 08 00 C0 01 00 02 01 00"
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

def test_mctp_som_zero_continuation_packet():
    # Continuation segment (SOM=0, EOM=1, Seq=1): Flags 0x50 -> no Message Type byte
    hex_dump = "01 08 00 50 11 22 33 44"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.mctp_packets) == 1
    pkt = report.mctp_packets[0]
    assert pkt.som is False and pkt.eom is True
    assert pkt.payload == [0x11, 0x22, 0x33, 0x44]

def test_ipmb_response_frame_decoding():
    # IPMB Response: rsSA=0x81, NetFn=0x07 (App Response = 0x06 + 1), Chk1, rqSA=0x20, rqSeq=0x20, Cmd=0x01, CC=0x00 (Success)
    # Checksum 1: (0x81 + 0x1C + 0x63) % 256 == 0
    hex_dump = "81 1C 63 20 20 01 00 3F"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    assert len(report.ipmb_frames) == 1
    frame = report.ipmb_frames[0]
    assert frame.netfn == 0x07
    assert "Response" in frame.netfn_name
    assert frame.cmd_name == "Get Device ID"
    assert frame.checksum1_valid is True
    assert frame.data == [0x00]  # Completion Code 0x00