from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.mctp.models import IPMBFrame, MCTPPacket, ServerMgmtReport
from fw_diag_tool.mctp.topology import (
    MCTPEndpoint,
    MCTPLink,
    MCTPTopology,
    build_eid_topology,
    topology_to_mermaid,
    topology_to_text,
)


def packet(
    src: int, dst: int, msg_type: str = "PLDM", payload: list[int] | None = None
) -> MCTPPacket:
    return MCTPPacket(
        dest_eid=dst,
        src_eid=src,
        som=True,
        eom=True,
        pkt_seq=0,
        to=True,
        msg_tag=0,
        msg_type=1,
        msg_type_name=msg_type,
        payload=payload or [],
    )


def frame(src: int, dst: int, data: list[int] | None = None) -> IPMBFrame:
    return IPMBFrame(
        rs_addr=dst,
        netfn=7,
        netfn_name="App (Response)",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=src,
        rq_seq=0,
        rq_lun=0,
        cmd=1,
        cmd_name="Get Device ID",
        data=data or [],
    )


def test_empty_report_returns_empty_topology() -> None:
    topology = build_eid_topology(ServerMgmtReport())
    assert topology == MCTPTopology((), (), 0, 0)


def test_single_packet_creates_endpoints_and_link() -> None:
    topology = build_eid_topology(ServerMgmtReport(mctp_packets=[packet(0, 8, payload=[1, 2])]))
    assert topology.total_endpoints == 2
    assert topology.total_links == 1
    assert topology.links[0] == MCTPLink(0, 8, 1, 2.0)


def test_multiple_packets_aggregate_endpoints() -> None:
    report = ServerMgmtReport(mctp_packets=[packet(0, 8), packet(0, 8), packet(8, 0)])
    topology = build_eid_topology(report)
    assert topology.total_endpoints == 2
    assert {endpoint.packet_count for endpoint in topology.endpoints} == {3}


def test_roles_classify_source_and_destination() -> None:
    report = ServerMgmtReport(mctp_packets=[packet(1, 2), packet(2, 3)])
    endpoints = {endpoint.eid: endpoint for endpoint in build_eid_topology(report).endpoints}
    assert endpoints[1].role == "requester"
    assert endpoints[2].role == "both"
    assert endpoints[3].role == "responder"


def test_message_types_are_tracked_per_endpoint() -> None:
    report = ServerMgmtReport(mctp_packets=[packet(1, 2, "PLDM"), packet(1, 3, "SPDM")])
    endpoints = {endpoint.eid: endpoint for endpoint in build_eid_topology(report).endpoints}
    assert endpoints[1].message_types_seen == frozenset({"PLDM", "SPDM"})
    assert endpoints[2].message_types_seen == frozenset({"PLDM"})


def test_duplicate_links_are_aggregated() -> None:
    topology = build_eid_topology(ServerMgmtReport(mctp_packets=[packet(1, 2), packet(1, 2)]))
    assert len(topology.links) == 1
    assert topology.links[0].message_count == 2


def test_link_average_payload_size() -> None:
    report = ServerMgmtReport(
        mctp_packets=[packet(1, 2, payload=[1]), packet(1, 2, payload=[1, 2, 3])]
    )
    assert build_eid_topology(report).links[0].avg_payload_size == 2.0


def test_self_loop_counts_endpoint_once() -> None:
    topology = build_eid_topology(ServerMgmtReport(mctp_packets=[packet(4, 4, payload=[1])]))
    assert topology.endpoints[0].packet_count == 1
    assert topology.endpoints[0].role == "both"


def test_ipmb_frames_create_ipmb_endpoints_and_link() -> None:
    topology = build_eid_topology(ServerMgmtReport(ipmb_frames=[frame(0x20, 0x81, [0, 1])]))
    assert {endpoint.eid for endpoint in topology.endpoints} == {0x20, 0x81}
    assert topology.endpoints[0].message_types_seen == frozenset({"IPMB"})
    assert topology.links[0].avg_payload_size == 2.0


def test_mixed_mctp_and_ipmb_traffic_merges_shared_eids() -> None:
    report = ServerMgmtReport(mctp_packets=[packet(0x20, 8)], ipmb_frames=[frame(0x20, 0x81)])
    topology = build_eid_topology(report)
    endpoint = next(endpoint for endpoint in topology.endpoints if endpoint.eid == 0x20)
    assert endpoint.message_types_seen == frozenset({"PLDM", "IPMB"})
    assert endpoint.role == "requester"


def test_mermaid_output_is_flowchart() -> None:
    topology = build_eid_topology(ServerMgmtReport(mctp_packets=[packet(0, 8)]))
    mermaid = topology_to_mermaid(topology)
    assert mermaid.startswith("flowchart LR")
    assert "EID_0" in mermaid and "EID_8" in mermaid
    assert "-->" in mermaid


def test_mermaid_empty_topology_is_valid() -> None:
    assert topology_to_mermaid(build_eid_topology(ServerMgmtReport())) == "flowchart LR"


def test_text_output_contains_counts_and_roles() -> None:
    topology = build_eid_topology(ServerMgmtReport(mctp_packets=[packet(0, 8)]))
    text = topology_to_text(topology)
    assert "MCTP EID Topology" in text
    assert "Endpoints: 2" in text
    assert "Links: 1" in text
    assert "requester" in text and "responder" in text


def test_dataclasses_are_frozen() -> None:
    endpoint = MCTPEndpoint(1, frozenset({"PLDM"}), 1, "requester")
    link = MCTPLink(1, 2, 1, 0.0)
    topology = MCTPTopology((endpoint,), (link,), 1, 1)
    with pytest.raises(FrozenInstanceError):
        endpoint.eid = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        link.message_count = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        topology.total_links = 2  # type: ignore[misc]


def test_invalid_report_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="ServerMgmtReport"):
        build_eid_topology(object())  # type: ignore[arg-type]


def test_endpoints_and_links_are_sorted_deterministically() -> None:
    report = ServerMgmtReport(mctp_packets=[packet(8, 2), packet(4, 1)])
    topology = build_eid_topology(report)
    assert [endpoint.eid for endpoint in topology.endpoints] == [1, 2, 4, 8]
    assert [(link.src_eid, link.dst_eid) for link in topology.links] == [(4, 1), (8, 2)]
