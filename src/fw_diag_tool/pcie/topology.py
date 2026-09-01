from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import PCIeConfigSpace


@dataclass
class PCIeNode:
    bus: int
    device: int
    function: int
    vendor_id: int | None = None
    device_id: int | None = None
    class_name: str = ""
    link_speed: str | None = None
    link_width: int | None = None
    children: list[PCIeNode] = field(default_factory=list)
    has_errors: bool = False


_BDF_RE = re.compile(
    r"^(?:[0-9a-fA-F]{4}:)?(?P<bus>[0-9a-fA-F]{2}):(?P<device>[0-9a-fA-F]{2})\.(?P<function>[0-7])$"
)


def _bdf_parts(config: Any) -> tuple[int, int, int] | None:
    bdf = getattr(config, "bdf", None)
    if isinstance(bdf, str):
        match = _BDF_RE.search(bdf.strip())
        if match:
            return tuple(int(match.group(name), 16) for name in ("bus", "device", "function"))  # type: ignore[return-value]
    values = (
        getattr(config, "bus", None),
        getattr(config, "device", None),
        getattr(config, "function", None),
    )
    if all(isinstance(value, int) for value in values):
        return values  # type: ignore[return-value]
    return None


def _link_values(config: Any) -> tuple[str | None, int | None]:
    speed = getattr(config, "link_speed", None)
    width = getattr(config, "link_width", None)
    link_info = getattr(config, "link_info", None)
    if link_info is not None:
        if speed is None:
            speed = getattr(link_info, "current_speed_str", None)
        if width is None:
            width = getattr(link_info, "current_width", None)
    if speed is not None and not isinstance(speed, str):
        speed = str(speed)
    if not isinstance(width, int):
        width = None
    return speed, width


def _has_errors(config: Any) -> bool:
    aer_errors = getattr(config, "aer_errors", None)
    if isinstance(aer_errors, dict) and aer_errors:
        return True
    aer = getattr(config, "aer_analysis", None)
    if aer is not None:
        if any(
            getattr(aer, field_name, 0) > 0
            for field_name in (
                "active_uncorr_fatal_count",
                "active_uncorr_nonfatal_count",
                "active_corr_count",
            )
        ):
            return True
        if any(getattr(error, "is_active", False) for error in getattr(aer, "uncorr_errors", [])):
            return True
        if any(getattr(error, "is_active", False) for error in getattr(aer, "corr_errors", [])):
            return True
    link_info = getattr(config, "link_info", None)
    if bool(getattr(config, "link_degraded", False)) or bool(
        getattr(link_info, "is_degraded", False)
    ):
        return True
    return bool(getattr(config, "data_quality_issues", []))


def _bridge_range(config: Any) -> tuple[int, int] | None:
    secondary = getattr(config, "secondary_bus", None)
    subordinate = getattr(config, "subordinate_bus", None)
    bridge_bus = getattr(config, "bridge_bus", None)
    if bridge_bus is not None:
        secondary = getattr(bridge_bus, "secondary_bus", secondary)
        subordinate = getattr(bridge_bus, "subordinate_bus", subordinate)
    if isinstance(secondary, int) and isinstance(subordinate, int) and secondary <= subordinate:
        return secondary, subordinate
    return None


def build_topology(configs: list[PCIeConfigSpace]) -> list[PCIeNode]:
    """Build a bus hierarchy using Type 1 bridge secondary/subordinate ranges."""
    entries: list[tuple[PCIeNode, tuple[int, int, int] | None, Any]] = []
    for config in configs:
        parts = _bdf_parts(config)
        if parts is None:
            continue
        speed, width = _link_values(config)
        node = PCIeNode(
            bus=parts[0],
            device=parts[1],
            function=parts[2],
            vendor_id=getattr(config, "vendor_id", None),
            device_id=getattr(config, "device_id", None),
            class_name=str(getattr(config, "class_name", "") or ""),
            link_speed=speed,
            link_width=width,
            has_errors=_has_errors(config),
        )
        entries.append((node, parts, config))

    bridges = [
        (node, parts, _bridge_range(config))
        for node, parts, config in entries
        if _bridge_range(config) is not None
    ]
    roots: list[PCIeNode] = []
    for node, parts, _config in entries:
        assert parts is not None
        candidates = [
            (parent, parent_parts, bus_range)
            for parent, parent_parts, bus_range in bridges
            if parent is not node
            and parent_parts is not None
            and bus_range is not None
            and bus_range[0] <= parts[0] <= bus_range[1]
            and parent_parts[0] < parts[0]
        ]
        if candidates:
            parent, _parent_parts, _range = max(
                candidates, key=lambda item: (item[2][0], -item[2][1])
            )
            parent.children.append(node)
        else:
            roots.append(node)

    key = lambda item: (item.bus, item.device, item.function)
    roots.sort(key=key)
    for node, _parts, _config in entries:
        node.children.sort(key=key)
    return roots


def _node_label(node: PCIeNode) -> str:
    bdf = f"{node.bus:02X}:{node.device:02X}.{node.function:X}"
    ids = "N/A"
    if node.vendor_id is not None or node.device_id is not None:
        vendor = f"0x{node.vendor_id:04X}" if node.vendor_id is not None else "N/A"
        device = f"0x{node.device_id:04X}" if node.device_id is not None else "N/A"
        ids = f"{vendor}:{device}"
    details = [f"[{bdf}]", ids]
    if node.class_name:
        details.append(node.class_name)
    if node.link_speed:
        link = node.link_speed
        if node.link_width is not None:
            link += f" x{node.link_width}"
        details.append(link)
    if node.has_errors:
        details.append("⚠")
    return " ".join(details)


def topology_to_text_tree(roots: list[PCIeNode], indent: int = 0) -> str:
    lines: list[str] = []

    def visit(node: PCIeNode, prefix: str, connector: str) -> None:
        lines.append(f"{prefix}{connector}{_node_label(node)}")
        child_prefix = prefix + (
            "    " if not connector else ("    " if connector == "└── " else "│   ")
        )
        for index, child in enumerate(node.children):
            visit(child, child_prefix, "└── " if index == len(node.children) - 1 else "├── ")

    base = " " * max(0, indent)
    for index, root in enumerate(roots):
        visit(
            root, base, "" if len(roots) == 1 else ("└── " if index == len(roots) - 1 else "├── ")
        )
    return "\n".join(lines)


def topology_to_mermaid(roots: list[PCIeNode]) -> str:
    lines = ["graph TD"]
    nodes: list[PCIeNode] = []

    def collect(node: PCIeNode) -> None:
        nodes.append(node)
        for child in node.children:
            collect(child)

    for root in roots:
        collect(root)
    ids = {id(node): f"n{index}" for index, node in enumerate(nodes)}
    for node in nodes:
        label = _node_label(node).replace('"', "'")
        lines.append(f'    {ids[id(node)]}["{label}"]')
        for child in node.children:
            lines.append(f"    {ids[id(node)]} --> {ids[id(child)]}")
    return "\n".join(lines)


__all__ = ["PCIeNode", "build_topology", "topology_to_mermaid", "topology_to_text_tree"]
