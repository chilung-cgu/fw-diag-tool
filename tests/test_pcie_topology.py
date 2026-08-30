from __future__ import annotations

from types import SimpleNamespace

from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    BridgeBusInfo,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)
from fw_diag_tool.pcie.topology import (
    PCIeNode,
    build_topology,
    topology_to_mermaid,
    topology_to_text_tree,
)


def config(bdf: str, **kwargs: object) -> PCIeConfigSpace:
    return PCIeConfigSpace(raw_data=bytes(64), bdf=bdf, **kwargs)


def bridge(bdf: str, secondary: int, subordinate: int) -> PCIeConfigSpace:
    return config(
        bdf,
        header_type=HeaderType.TYPE_1_BRIDGE,
        bridge_bus=BridgeBusInfo(0, secondary, subordinate, 0, 0, 0, 0, 0, 0, 0),
    )


def test_node_is_mutable_and_children_default_is_independent() -> None:
    first = PCIeNode(0, 0, 0)
    second = PCIeNode(0, 0, 1)
    first.children.append(second)
    assert first.children == [second]
    assert second.children == []


def test_build_topology_returns_empty_for_empty_input() -> None:
    assert build_topology([]) == []


def test_build_topology_parses_domain_bdf() -> None:
    roots = build_topology([config("0000:02:03.4")])
    assert [(n.bus, n.device, n.function) for n in roots] == [(2, 3, 4)]


def test_build_topology_parses_two_part_bdf() -> None:
    roots = build_topology([config("02:03.4")])
    assert (roots[0].bus, roots[0].device, roots[0].function) == (2, 3, 4)


def test_bridge_range_attaches_downstream_device() -> None:
    root = bridge("00:01.0", 1, 1)
    endpoint = config("01:00.0", vendor_id=0x8086, device_id=0x1234)
    roots = build_topology([endpoint, root])
    assert roots == [next(node for node in roots if node.bus == 0)]
    assert roots[0].children[0].bus == 1


def test_nested_bridge_uses_most_specific_range() -> None:
    outer = bridge("00:01.0", 1, 4)
    inner = bridge("01:02.0", 2, 2)
    endpoint = config("02:00.0")
    roots = build_topology([endpoint, inner, outer])
    assert roots[0] is not None
    assert roots[0].children[0].bus == 1
    assert roots[0].children[0].device == 2
    assert roots[0].children[0].children[0].bus == 2


def test_devices_outside_bridge_range_remain_roots() -> None:
    root = bridge("00:01.0", 1, 1)
    endpoint = config("02:00.0")
    roots = build_topology([root, endpoint])
    assert [node.bus for node in roots] == [0, 2]


def test_nodes_are_sorted_by_bdf() -> None:
    roots = build_topology([config("03:00.0"), config("01:02.0"), config("01:01.0")])
    assert [(node.bus, node.device) for node in roots] == [(1, 1), (1, 2), (3, 0)]


def test_link_fields_are_copied_from_link_info() -> None:
    cfg = config("00:00.0", link_info=PCIeLinkInfo(current_speed_str="16 GT/s", current_width=4))
    node = build_topology([cfg])[0]
    assert node.link_speed == "16 GT/s"
    assert node.link_width == 4


def test_link_fields_support_flat_attributes() -> None:
    cfg = SimpleNamespace(
        bdf="00:00.0",
        vendor_id=1,
        device_id=2,
        class_name="Endpoint",
        link_speed="Gen4",
        link_width=8,
    )
    node = build_topology([cfg])[0]  # type: ignore[arg-type]
    assert (node.link_speed, node.link_width) == ("Gen4", 8)


def test_active_aer_errors_highlight_node() -> None:
    aer = AERAnalysisResult(0x100, 0, 0, 0, 0, 0, 0, [], active_uncorr_fatal_count=1)
    node = build_topology([config("00:00.0", aer_analysis=aer)])[0]
    assert node.has_errors


def test_degraded_link_highlights_node() -> None:
    link = PCIeLinkInfo(is_degraded=True)
    node = build_topology([config("00:00.0", link_info=link)])[0]
    assert node.has_errors


def test_text_tree_contains_bdf_connectors_and_error_marker() -> None:
    root = bridge("00:01.0", 1, 1)
    child = config("01:00.0", class_name="Network Controller")
    child.aer_errors = {"UR": True}  # type: ignore[attr-defined]
    text = topology_to_text_tree(build_topology([root, child]))
    assert "[00:01.0]" in text
    assert "└── [01:00.0]" in text
    assert "⚠" in text


def test_text_tree_honors_indent() -> None:
    text = topology_to_text_tree(build_topology([config("00:00.0")]), indent=2)
    assert text.startswith("  [00:00.0]")


def test_mermaid_contains_graph_and_edges() -> None:
    roots = build_topology([bridge("00:01.0", 1, 1), config("01:00.0")])
    mermaid = topology_to_mermaid(roots)
    assert mermaid.startswith("graph TD")
    assert "-->" in mermaid
    assert "[01:00.0]" in mermaid


def test_mermaid_escapes_double_quotes() -> None:
    node = PCIeNode(0, 0, 0, class_name='Vendor "Device"')
    mermaid = topology_to_mermaid([node])
    assert "Vendor 'Device'" in mermaid


def test_invalid_bdf_is_ignored() -> None:
    cfg = config("not-a-bdf")
    assert build_topology([cfg]) == []
