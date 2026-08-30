from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ServerMgmtReport


@dataclass(frozen=True)
class MCTPStatistics:
    """Statistical summary of MCTP and IPMB decoded traffic."""

    total_packets: int = 0
    total_messages: int = 0
    reassembly_success_rate: float = 0.0
    ipmb_frame_count: int = 0
    checksum_error_count: int = 0
    eid_matrix: dict[str, int] = field(default_factory=dict)
    message_type_distribution: dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    warning_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert statistics to dictionary suitable for JSON serialization."""
        return {
            "total_packets": self.total_packets,
            "total_messages": self.total_messages,
            "reassembly_success_rate": self.reassembly_success_rate,
            "ipmb_frame_count": self.ipmb_frame_count,
            "checksum_error_count": self.checksum_error_count,
            "eid_matrix": dict(self.eid_matrix),
            "message_type_distribution": dict(self.message_type_distribution),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


def compute_mctp_statistics(report: ServerMgmtReport) -> MCTPStatistics:
    """Compute traffic, reassembly, and error statistics for an MCTP/IPMB report."""
    if not isinstance(report, ServerMgmtReport):
        raise TypeError("report must be a ServerMgmtReport instance")

    total_packets = len(report.mctp_packets)

    messages = report.mctp_messages
    total_messages = len(messages)

    if total_messages > 0:
        complete_count = sum(1 for m in messages if m.is_complete)
        reassembly_success_rate = complete_count / total_messages
    else:
        reassembly_success_rate = 0.0

    ipmb_frame_count = len(report.ipmb_frames)
    checksum_error_count = sum(
        1 for f in report.ipmb_frames if not f.checksum1_valid or not f.checksum2_valid
    )

    eid_matrix: dict[str, int] = {}
    for pkt in report.mctp_packets:
        key = f"({pkt.src_eid}, {pkt.dest_eid})"
        eid_matrix[key] = eid_matrix.get(key, 0) + 1

    message_type_distribution: dict[str, int] = {}
    if messages:
        for msg in messages:
            message_type_distribution[msg.msg_type_name] = (
                message_type_distribution.get(msg.msg_type_name, 0) + 1
            )
    elif report.mctp_packets:
        for pkt in report.mctp_packets:
            message_type_distribution[pkt.msg_type_name] = (
                message_type_distribution.get(pkt.msg_type_name, 0) + 1
            )

    errors = (
        report.errors
        if getattr(report, "errors", None)
        else (getattr(report, "source_errors", None) or [])
    )
    error_count = len(errors)

    warnings = getattr(report, "warnings", None) or []
    warning_count = len(warnings)

    return MCTPStatistics(
        total_packets=total_packets,
        total_messages=total_messages,
        reassembly_success_rate=reassembly_success_rate,
        ipmb_frame_count=ipmb_frame_count,
        checksum_error_count=checksum_error_count,
        eid_matrix=eid_matrix,
        message_type_distribution=message_type_distribution,
        error_count=error_count,
        warning_count=warning_count,
    )


__all__ = ["MCTPStatistics", "compute_mctp_statistics"]
