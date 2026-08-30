from __future__ import annotations

from dataclasses import dataclass

from .models import ServerMgmtReport


@dataclass(frozen=True)
class MCTPEndpoint:
    eid: int
    message_types_seen: frozenset[str]
    packet_count: int
    role: str


@dataclass(frozen=True)
class MCTPLink:
    src_eid: int
    dst_eid: int
    message_count: int
    avg_payload_size: float | None


@dataclass(frozen=True)
class MCTPTopology:
    endpoints: tuple[MCTPEndpoint, ...]
    links: tuple[MCTPLink, ...]
    total_endpoints: int
    total_links: int


def build_eid_topology(report: ServerMgmtReport) -> MCTPTopology:
    """Build endpoint and directed-link aggregates from decoded traffic."""
    if not isinstance(report, ServerMgmtReport):
        raise TypeError("report must be a ServerMgmtReport instance")

    endpoint_types: dict[int, set[str]] = {}
    endpoint_counts: dict[int, int] = {}
    source_eids: set[int] = set()
    destination_eids: set[int] = set()
    link_counts: dict[tuple[int, int], int] = {}
    link_payload_totals: dict[tuple[int, int], int] = {}

    def add_traffic(
        src_eid: int,
        dst_eid: int,
        message_type: str,
        payload_size: int,
    ) -> None:
        endpoint_types.setdefault(src_eid, set()).add(message_type)
        endpoint_types.setdefault(dst_eid, set()).add(message_type)
        endpoint_counts[src_eid] = endpoint_counts.get(src_eid, 0) + 1
        if dst_eid != src_eid:
            endpoint_counts[dst_eid] = endpoint_counts.get(dst_eid, 0) + 1
        source_eids.add(src_eid)
        destination_eids.add(dst_eid)

        pair = (src_eid, dst_eid)
        link_counts[pair] = link_counts.get(pair, 0) + 1
        link_payload_totals[pair] = link_payload_totals.get(pair, 0) + payload_size

    for packet in report.mctp_packets:
        add_traffic(
            packet.src_eid,
            packet.dest_eid,
            packet.msg_type_name,
            len(packet.payload),
        )
    for frame in report.ipmb_frames:
        add_traffic(frame.rq_addr, frame.rs_addr, "IPMB", len(frame.data))

    endpoints = tuple(
        MCTPEndpoint(
            eid=eid,
            message_types_seen=frozenset(endpoint_types[eid]),
            packet_count=endpoint_counts[eid],
            role=(
                "both"
                if eid in source_eids and eid in destination_eids
                else "requester"
                if eid in source_eids
                else "responder"
                if eid in destination_eids
                else "unknown"
            ),
        )
        for eid in sorted(endpoint_types)
    )
    links = tuple(
        MCTPLink(
            src_eid=src_eid,
            dst_eid=dst_eid,
            message_count=count,
            avg_payload_size=link_payload_totals[(src_eid, dst_eid)] / count
            if count
            else None,
        )
        for (src_eid, dst_eid), count in sorted(link_counts.items())
    )
    return MCTPTopology(
        endpoints=endpoints,
        links=links,
        total_endpoints=len(endpoints),
        total_links=len(links),
    )


def topology_to_mermaid(topo: MCTPTopology) -> str:
    """Render a topology as a deterministic Mermaid flowchart."""
    lines = ["flowchart LR"]
    endpoint_ids: dict[int, str] = {}
    for endpoint in topo.endpoints:
        node_id = f"EID_{endpoint.eid}"
        endpoint_ids[endpoint.eid] = node_id
        types = ", ".join(sorted(endpoint.message_types_seen)) or "-"
        label = (
            f"EID 0x{endpoint.eid:02X}<br/>"
            f"{endpoint.role}<br/>"
            f"{endpoint.packet_count} packet(s)<br/>"
            f"{types}"
        ).replace('"', "'")
        lines.append(f'    {node_id}["{label}"]')
    for link in topo.links:
        src = endpoint_ids.get(link.src_eid, f"EID_{link.src_eid}")
        dst = endpoint_ids.get(link.dst_eid, f"EID_{link.dst_eid}")
        average = (
            f"; avg {link.avg_payload_size:.1f} B"
            if link.avg_payload_size is not None
            else ""
        )
        lines.append(f"    {src} -->|{link.message_count} message(s){average}| {dst}")
    return "\n".join(lines)


def topology_to_text(topo: MCTPTopology) -> str:
    """Render a compact human-readable topology summary."""
    lines = [
        "MCTP EID Topology",
        f"Endpoints: {topo.total_endpoints}",
    ]
    for endpoint in topo.endpoints:
        types = ", ".join(sorted(endpoint.message_types_seen)) or "-"
        lines.append(
            f"- EID 0x{endpoint.eid:02X} ({endpoint.role}): "
            f"{endpoint.packet_count} packet(s); types: {types}"
        )
    lines.append(f"Links: {topo.total_links}")
    for link in topo.links:
        average = (
            f"; avg payload {link.avg_payload_size:.1f} B"
            if link.avg_payload_size is not None
            else ""
        )
        lines.append(
            f"- 0x{link.src_eid:02X} -> 0x{link.dst_eid:02X}: "
            f"{link.message_count} message(s){average}"
        )
    return "\n".join(lines)


__all__ = [
    "MCTPEndpoint",
    "MCTPLink",
    "MCTPTopology",
    "build_eid_topology",
    "topology_to_mermaid",
    "topology_to_text",
]
