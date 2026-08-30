"""Tests for MCTP and IPMB Before/After Diff Engine."""

from __future__ import annotations

import pytest

from fw_diag_tool.mctp.diff import MCTPDiffEngine, MCTPDiffResult
from fw_diag_tool.mctp.models import (
    IPMBFrame,
    MCTPMessage,
    MCTPPacket,
    ProtocolMode,
    ServerMgmtReport,
)
from fw_diag_tool.mctp.parser import ServerMgmtParser


def _make_mctp_packet(msg_type: int = 0x01, seq: int = 0) -> MCTPPacket:
    return MCTPPacket(
        dest_eid=0x08,
        src_eid=0x0A,
        som=True,
        eom=True,
        pkt_seq=seq,
        to=True,
        msg_tag=0x01,
        msg_type=msg_type,
        msg_type_name="PLDM",
    )


def _make_mctp_message(msg_type: int = 0x01, tag: int = 0x01) -> MCTPMessage:
    return MCTPMessage(
        src_eid=0x0A,
        dest_eid=0x08,
        msg_tag=tag,
        msg_type=msg_type,
        msg_type_name="PLDM",
        packets_count=1,
    )


def _make_ipmb_frame(cmd: int = 0x01) -> IPMBFrame:
    return IPMBFrame(
        rs_addr=0x20,
        netfn=0x06,
        netfn_name="App",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x2C,
        rq_seq=1,
        rq_lun=0,
        cmd=cmd,
        cmd_name="Get Device ID",
    )


def test_mctp_diff_identical():
    rep1 = ServerMgmtReport(
        mctp_packets=[_make_mctp_packet()],
        mctp_messages=[_make_mctp_message()],
        ipmb_frames=[_make_ipmb_frame()],
        protocol_mode=ProtocolMode.AUTO,
        errors=["line 1: checksum error"],
        warnings=["line 2: sequence warning"],
    )
    rep2 = ServerMgmtReport(
        mctp_packets=[_make_mctp_packet()],
        mctp_messages=[_make_mctp_message()],
        ipmb_frames=[_make_ipmb_frame()],
        protocol_mode=ProtocolMode.AUTO,
        errors=["line 1: checksum error"],
        warnings=["line 2: sequence warning"],
    )

    result = MCTPDiffEngine.compare(rep1, rep2)
    assert isinstance(result, MCTPDiffResult)
    assert result.is_identical is True
    assert result.message_count_delta == 0
    assert result.ipmb_frame_count_delta == 0
    assert result.error_count_delta == 0
    assert result.new_errors == []
    assert result.resolved_errors == []
    assert result.common_errors == ["line 1: checksum error"]
    assert result.new_warnings == []
    assert result.resolved_warnings == []
    assert result.common_warnings == ["line 2: sequence warning"]
    assert result.protocol_mode_changed is False
    assert result.baseline_protocol_mode == "auto"
    assert result.candidate_protocol_mode == "auto"
    assert "完全一致" in result.summary


def test_mctp_diff_different_errors_and_warnings():
    base = ServerMgmtReport(
        errors=["Err A", "Err B"],
        warnings=["Warn 1", "Warn 2"],
    )
    cand = ServerMgmtReport(
        errors=["Err B", "Err C"],
        warnings=["Warn 2", "Warn 3"],
    )

    result = MCTPDiffEngine.compare(base, cand)
    assert result.is_identical is False
    assert result.error_count_delta == 0
    assert result.new_errors == ["Err C"]
    assert result.resolved_errors == ["Err A"]
    assert result.common_errors == ["Err B"]
    assert result.new_warnings == ["Warn 3"]
    assert result.resolved_warnings == ["Warn 1"]
    assert result.common_warnings == ["Warn 2"]
    assert "新增 1 項錯誤" in result.summary
    assert "修復 1 項錯誤" in result.summary
    assert "新增 1 項警告" in result.summary
    assert "修復 1 項警告" in result.summary


def test_mctp_diff_message_count_delta():
    base = ServerMgmtReport(
        mctp_messages=[_make_mctp_message(tag=1)],
        ipmb_frames=[_make_ipmb_frame(cmd=1), _make_ipmb_frame(cmd=2)],
    )
    cand = ServerMgmtReport(
        mctp_messages=[_make_mctp_message(tag=1), _make_mctp_message(tag=2), _make_mctp_message(tag=3)],
        ipmb_frames=[_make_ipmb_frame(cmd=1)],
    )

    result = MCTPDiffEngine.compare(base, cand)
    assert result.is_identical is False
    assert result.message_count_delta == 2
    assert result.ipmb_frame_count_delta == -1
    assert "MCTP 訊息數變化 +2" in result.summary
    assert "IPMB 訊框數變化 -1" in result.summary


def test_mctp_diff_protocol_mode_changed():
    base = ServerMgmtReport(protocol_mode=ProtocolMode.MCTP)
    cand = ServerMgmtReport(protocol_mode=ProtocolMode.IPMB)

    result = MCTPDiffEngine.compare(base, cand)
    assert result.is_identical is False
    assert result.protocol_mode_changed is True
    assert result.baseline_protocol_mode == "mctp"
    assert result.candidate_protocol_mode == "ipmb"
    assert "協定模式由 mctp 變更為 ipmb" in result.summary


def test_mctp_diff_type_error():
    with pytest.raises(TypeError, match="ServerMgmtReport"):
        MCTPDiffEngine.compare("invalid", ServerMgmtReport())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="ServerMgmtReport"):
        MCTPDiffEngine.compare(ServerMgmtReport(), 123)  # type: ignore[arg-type]


def test_mctp_diff_with_parsed_text():
    raw_base = """
01 08 0A C8 00 80 00 01
"""
    raw_cand = """
01 08 0A C8 00 80 00 01
01 08 0A C9 00 80 00 02
"""
    rep_base = ServerMgmtParser.parse_text_dump(raw_base)
    rep_cand = ServerMgmtParser.parse_text_dump(raw_cand)

    result = MCTPDiffEngine.compare(rep_base, rep_cand)
    assert isinstance(result, MCTPDiffResult)
    assert result.message_count_delta == 1
    assert result.is_identical is False

