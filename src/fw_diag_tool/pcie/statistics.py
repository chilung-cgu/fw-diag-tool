from __future__ import annotations

import re
from dataclasses import dataclass, field

from .constants import PCI_BASE_CLASSES
from .models import DmesgAEREvent, PCIeConfigSpace

_SPEED_CODE_MAP = {
    1: "Gen1",
    2: "Gen2",
    3: "Gen3",
    4: "Gen4",
    5: "Gen5",
    6: "Gen6",
}


@dataclass(frozen=True)
class PCIeStatistics:
    device_count: int = 0
    total_aer_errors: int = 0
    uncorrectable_count: int = 0
    correctable_count: int = 0
    error_rate_per_sec: float | None = None
    link_degradation_count: int = 0
    topology_summary: dict[str, int] = field(default_factory=dict)
    link_speed_distribution: dict[str, int] = field(default_factory=dict)


def compute_pcie_statistics(
    configs: list[PCIeConfigSpace] | None = None,
    dmesg_events: list[DmesgAEREvent] | None = None,
) -> PCIeStatistics:
    """Compute comprehensive statistics across PCIe configuration spaces and dmesg AER events."""
    cfg_list = configs or []
    event_list = dmesg_events or []

    device_count = len(cfg_list)
    uncorrectable_count = 0
    correctable_count = 0
    link_degradation_count = 0
    topology_summary: dict[str, int] = {}
    link_speed_distribution: dict[str, int] = {}

    for cfg in cfg_list:
        # Topology / Device class
        class_label = cfg.class_name
        if not class_label:
            class_label = PCI_BASE_CLASSES.get(
                cfg.base_class, f"Unknown Class (0x{cfg.base_class:02X})"
            )
        topology_summary[class_label] = topology_summary.get(class_label, 0) + 1

        # Link information
        if cfg.link_info:
            if cfg.link_info.is_degraded:
                link_degradation_count += 1

            gen_name: str | None = None
            if cfg.link_info.current_speed_code in _SPEED_CODE_MAP:
                gen_name = _SPEED_CODE_MAP[cfg.link_info.current_speed_code]
            elif cfg.link_info.current_speed_str:
                m = re.search(r"Gen(\d+)", cfg.link_info.current_speed_str, re.IGNORECASE)
                if m:
                    gen_name = f"Gen{m.group(1)}"
                elif cfg.link_info.current_speed_str != "Unknown":
                    gen_name = cfg.link_info.current_speed_str

            if gen_name:
                link_speed_distribution[gen_name] = (
                    link_speed_distribution.get(gen_name, 0) + 1
                )

        # AER from config space
        if cfg.aer_analysis:
            if cfg.aer_analysis.uncorr_errors:
                uncorrectable_count += sum(
                    1 for e in cfg.aer_analysis.uncorr_errors if e.is_active
                )
            else:
                uncorrectable_count += (
                    cfg.aer_analysis.active_uncorr_fatal_count
                    + cfg.aer_analysis.active_uncorr_nonfatal_count
                )

            if cfg.aer_analysis.corr_errors:
                correctable_count += sum(
                    1 for e in cfg.aer_analysis.corr_errors if e.is_active
                )
            else:
                correctable_count += cfg.aer_analysis.active_corr_count

    # AER from dmesg events
    for ev in event_list:
        sev = (ev.severity or "").lower()
        if "fatal" in sev or "uncorr" in sev:
            uncorrectable_count += 1
        elif "corr" in sev:
            correctable_count += 1
        else:
            err_lower = (ev.error_name or "").lower()
            if any(
                c in err_lower
                for c in [
                    "badtlp",
                    "baddllp",
                    "rxerr",
                    "replay",
                    "advisory",
                    "hdrlog",
                    "receiver error",
                ]
            ):
                correctable_count += 1
            else:
                uncorrectable_count += 1

    total_aer_errors = uncorrectable_count + correctable_count

    # Calculate error rate from dmesg timestamps
    error_rate_per_sec: float | None = None
    if event_list:
        timestamps: list[float] = []
        for ev in event_list:
            if ev.timestamp:
                clean = ev.timestamp.strip("[] ")
                try:
                    timestamps.append(float(clean))
                except (ValueError, TypeError):
                    pass
        if len(timestamps) >= 2:
            duration = max(timestamps) - min(timestamps)
            if duration > 0:
                error_rate_per_sec = round(len(timestamps) / duration, 4)

    return PCIeStatistics(
        device_count=device_count,
        total_aer_errors=total_aer_errors,
        uncorrectable_count=uncorrectable_count,
        correctable_count=correctable_count,
        error_rate_per_sec=error_rate_per_sec,
        link_degradation_count=link_degradation_count,
        topology_summary=topology_summary,
        link_speed_distribution=link_speed_distribution,
    )
