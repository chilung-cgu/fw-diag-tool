from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.mctp.models import (
    IPMBFrame,
    MCTPMessage,
    MCTPPacket,
    ServerMgmtReport,
)
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.mctp.statistics import MCTPStatistics, compute_mctp_statistics


def test_empty_report_statistics():
    report = ServerMgmtReport()
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 0
    assert stats.total_messages == 0
    assert stats.reassembly_success_rate == 0.0
    assert stats.ipmb_frame_count == 0
    assert stats.checksum_error_count == 0
    assert stats.eid_matrix == {}
    assert stats.message_type_distribution == {}
    assert stats.error_count == 0
    assert stats.warning_count == 0

    d = stats.to_dict()
    assert d["total_packets"] == 0
    assert d["total_messages"] == 0
    assert d["reassembly_success_rate"] == 0.0
    assert d["ipmb_frame_count"] == 0
    assert d["checksum_error_count"] == 0
    assert d["eid_matrix"] == {}
    assert d["message_type_distribution"] == {}
    assert d["error_count"] == 0
    assert d["warning_count"] == 0


def test_mctp_only_single_packet():
    # Single-packet PLDM message: Dest 0x08, Src 0x00, Flags 0xC0 (SOM=1, EOM=1), MsgType 0x01
    hex_dump = "01 08 00 C0 01 00 02 01 00"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 1
    assert stats.total_messages == 1
    assert stats.reassembly_success_rate == 1.0
    assert stats.ipmb_frame_count == 0
    assert stats.checksum_error_count == 0
    assert stats.eid_matrix == {"(0, 8)": 1}
    assert "PLDM" in next(iter(stats.message_type_distribution))
    assert stats.error_count == 0
    assert stats.warning_count == 0


def test_mctp_multi_packet_reassembly_success():
    # 3-packet message: SOM(seq 0) -> Middle(seq 1) -> EOM(seq 2)
    dump = "01 08 00 80 01 00 02 01 00\n01 08 00 10 11 22 33 44\n01 08 00 60 55 66 77 88\n"
    report = ServerMgmtParser.parse_text_dump(dump)
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 3
    assert stats.total_messages == 1
    assert stats.reassembly_success_rate == 1.0
    assert stats.eid_matrix == {"(0, 8)": 3}
    assert len(stats.message_type_distribution) == 1


def test_mctp_reassembly_partial_failure_rate():
    # 1 single-packet complete + 1 incomplete multi-packet (missing EOM)
    dump = "01 08 00 C0 01 00 02 01 00\n01 08 00 80 01 11 22 33\n"
    report = ServerMgmtParser.parse_text_dump(dump)
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 2
    assert stats.total_messages == 2
    assert stats.reassembly_success_rate == 0.5


def test_mctp_sequence_mismatch_failure_rate():
    # Sequence mismatch: SOM(seq 0) -> EOM(seq 2 instead of 1)
    dump = "01 08 00 80 01 00 02 01 00\n01 08 00 60 55 66 77 88\n"
    report = ServerMgmtParser.parse_text_dump(dump)
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 2
    assert stats.total_messages == 1
    assert stats.reassembly_success_rate == 0.0


def test_ipmb_only_valid_frames():
    # Valid IPMB frame
    hex_dump = "81 1C 63 20 20 01 00 BF"
    report = ServerMgmtParser.parse_text_dump(hex_dump)
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 0
    assert stats.total_messages == 0
    assert stats.reassembly_success_rate == 0.0
    assert stats.ipmb_frame_count == 1
    assert stats.checksum_error_count == 0
    assert stats.eid_matrix == {}
    assert stats.message_type_distribution == {}


def test_ipmb_checksum_error_counting():
    frame_ok = IPMBFrame(
        rs_addr=0x81,
        netfn=0x07,
        netfn_name="App (Response)",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x20,
        rq_seq=0,
        rq_lun=0,
        cmd=0x01,
        cmd_name="Get Device ID",
        data=[0x00],
        checksum2_valid=True,
    )
    frame_bad_chk1 = IPMBFrame(
        rs_addr=0x81,
        netfn=0x07,
        netfn_name="App (Response)",
        rs_lun=0,
        checksum1_valid=False,
        rq_addr=0x20,
        rq_seq=0,
        rq_lun=0,
        cmd=0x01,
        cmd_name="Get Device ID",
        data=[0x00],
        checksum2_valid=True,
    )
    frame_bad_chk2 = IPMBFrame(
        rs_addr=0x81,
        netfn=0x07,
        netfn_name="App (Response)",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x20,
        rq_seq=0,
        rq_lun=0,
        cmd=0x01,
        cmd_name="Get Device ID",
        data=[0x00],
        checksum2_valid=False,
    )
    report = ServerMgmtReport(ipmb_frames=[frame_ok, frame_bad_chk1, frame_bad_chk2])
    stats = compute_mctp_statistics(report)

    assert stats.ipmb_frame_count == 3
    assert stats.checksum_error_count == 2


def test_mixed_mctp_and_ipmb_traffic():
    mctp_hex = "01 08 00 C0 01 00 02 01 00"
    ipmb_hex = "81 1C 63 20 20 01 00 BF"
    report = ServerMgmtParser.parse_text_dump(f"{mctp_hex}\n{ipmb_hex}")
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 1
    assert stats.total_messages == 1
    assert stats.reassembly_success_rate == 1.0
    assert stats.ipmb_frame_count == 1
    assert stats.checksum_error_count == 0
    assert stats.eid_matrix == {"(0, 8)": 1}
    assert len(stats.message_type_distribution) == 1


def test_eid_matrix_multiple_endpoints():
    pkt1 = MCTPPacket(
        dest_eid=0x08,
        src_eid=0x00,
        som=True,
        eom=True,
        pkt_seq=0,
        to=False,
        msg_tag=0,
        msg_type=1,
        msg_type_name="PLDM",
    )
    pkt2 = MCTPPacket(
        dest_eid=0x08,
        src_eid=0x00,
        som=True,
        eom=True,
        pkt_seq=0,
        to=False,
        msg_tag=1,
        msg_type=1,
        msg_type_name="PLDM",
    )
    pkt3 = MCTPPacket(
        dest_eid=0x00,
        src_eid=0x08,
        som=True,
        eom=True,
        pkt_seq=0,
        to=False,
        msg_tag=0,
        msg_type=1,
        msg_type_name="PLDM",
    )
    pkt4 = MCTPPacket(
        dest_eid=0x20,
        src_eid=0x10,
        som=True,
        eom=True,
        pkt_seq=0,
        to=False,
        msg_tag=0,
        msg_type=0,
        msg_type_name="MCTP Control Message",
    )
    report = ServerMgmtReport(mctp_packets=[pkt1, pkt2, pkt3, pkt4])
    stats = compute_mctp_statistics(report)

    assert stats.total_packets == 4
    assert stats.eid_matrix == {
        "(0, 8)": 2,
        "(8, 0)": 1,
        "(16, 32)": 1,
    }


def test_message_type_distribution_multiple_types():
    msg1 = MCTPMessage(
        src_eid=0,
        dest_eid=8,
        msg_tag=0,
        msg_type=0,
        msg_type_name="MCTP Control Message",
        packets_count=1,
    )
    msg2 = MCTPMessage(
        src_eid=0,
        dest_eid=8,
        msg_tag=1,
        msg_type=1,
        msg_type_name="PLDM",
        packets_count=1,
    )
    msg3 = MCTPMessage(
        src_eid=0,
        dest_eid=8,
        msg_tag=2,
        msg_type=1,
        msg_type_name="PLDM",
        packets_count=1,
    )
    msg4 = MCTPMessage(
        src_eid=0,
        dest_eid=8,
        msg_tag=3,
        msg_type=5,
        msg_type_name="SPDM",
        packets_count=1,
    )
    report = ServerMgmtReport(mctp_messages=[msg1, msg2, msg3, msg4])
    stats = compute_mctp_statistics(report)

    assert stats.message_type_distribution == {
        "MCTP Control Message": 1,
        "PLDM": 2,
        "SPDM": 1,
    }


def test_error_and_warning_counts():
    report = ServerMgmtReport(
        errors=["Syntax error on line 1", "Invalid token on line 2"],
        warnings=["Deprecated field format"],
    )
    stats = compute_mctp_statistics(report)

    assert stats.error_count == 2
    assert stats.warning_count == 1


def test_compute_mctp_statistics_type_error():
    with pytest.raises(TypeError, match="report must be a ServerMgmtReport instance"):
        compute_mctp_statistics("invalid_report")  # type: ignore[arg-type]


def test_frozen_dataclass_immutability():
    stats = MCTPStatistics(total_packets=5)
    with pytest.raises(FrozenInstanceError):
        stats.total_packets = 10  # type: ignore[misc]


def test_markdown_report_includes_statistics_section():
    dump = "01 08 00 C0 01 00 02 01 00\n81 1C 63 20 20 01 00 BF\n"
    report = ServerMgmtParser.parse_text_dump(dump)
    md = ServerMgmtReporter.to_markdown(report)

    assert "## MCTP/IPMB 統計摘要" in md
    assert "MCTP 封包總數（Total Packets）" in md
    assert "重組訊息總數（Total Messages）" in md
    assert "訊息重組成功率（Reassembly Success Rate）" in md
    assert "IPMB 訊框數（IPMB Frame Count）" in md
    assert "端點通訊統計（EID Matrix）" in md
    assert "訊息類型分佈（Message Type Distribution）" in md
